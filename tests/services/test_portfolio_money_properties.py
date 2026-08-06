# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fixed-seed property-style invariant tests for portfolio ledger money math.

These tests treat ``portfolio_service.py`` replay semantics as the contract
and exercise randomized operation sequences under deterministic seeds
(stdlib ``random.Random`` only; no Hypothesis dependency).

Invariants covered:
1. Balance conservation across cash / trade / corporate-action sequences
2. Scoped idempotency (same scoped op twice == once; cross-account isolation)
3. FX pair isolation and multi-currency conversion consistency
4. Projection-after-write consistency (live snapshot vs persisted daily snapshot)

Oracle notes:
- Same-day event order in the service is cash → corporate action → trade.
  The independent ledger oracle reconstructs balances from persisted events
  using that order, not API call order.
"""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import select

from src.config import Config
from src.services.portfolio_service import (
    PortfolioIdempotencyConflictError,
    PortfolioService,
)
from src.storage import DatabaseManager, PortfolioDailySnapshot

# Fixed seeds → identical sequences and outcomes on every run.
PROPERTY_SEEDS: Tuple[int, ...] = (20260805, 424242, 8675309)
SEQUENCE_LENGTH = 36
AS_OF = date(2026, 1, 20)
BASE_DAY = date(2026, 1, 2)
SYMBOL = "600519"
MARKET = "cn"
CURRENCY = "CNY"
FLOAT_PLACES = 5
EPS = 1e-6


@dataclass
class PositionLot:
    quantity: float
    unit_cost: float


@dataclass
class LedgerOracle:
    """Independent reconstruction of cash / positions / PnL from events.

    Mirrors ``PortfolioService._replay_account`` money rules for a single
    base-currency book (identity FX). Used as the conservation oracle.
    """

    cash_by_currency: DefaultDict[str, float] = field(
        default_factory=lambda: defaultdict(float)
    )
    fifo_lots: DefaultDict[Tuple[str, str, str], List[PositionLot]] = field(
        default_factory=lambda: defaultdict(list)
    )
    avg_qty: DefaultDict[Tuple[str, str, str], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    avg_cost: DefaultDict[Tuple[str, str, str], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    fees_paid: float = 0.0
    taxes_paid: float = 0.0
    realized_local: float = 0.0

    def held_qty(self, key: Tuple[str, str, str], cost_method: str) -> float:
        if cost_method == "fifo":
            return sum(lot.quantity for lot in self.fifo_lots.get(key, []))
        return float(self.avg_qty.get(key, 0.0))

    def local_cash(self, currency: str = CURRENCY) -> float:
        return float(self.cash_by_currency.get(currency, 0.0))

    def apply_cash(self, *, direction: str, amount: float, currency: str) -> None:
        if direction == "in":
            self.cash_by_currency[currency] += amount
        else:
            self.cash_by_currency[currency] -= amount

    def apply_buy(
        self,
        *,
        key: Tuple[str, str, str],
        quantity: float,
        price: float,
        fee: float,
        tax: float,
        cost_method: str,
    ) -> None:
        currency = key[2]
        gross = quantity * price
        self.cash_by_currency[currency] -= gross + fee + tax
        self.fees_paid += fee
        self.taxes_paid += tax
        if cost_method == "fifo":
            unit_cost = (gross + fee + tax) / quantity
            self.fifo_lots[key].append(PositionLot(quantity=quantity, unit_cost=unit_cost))
        else:
            self.avg_qty[key] += quantity
            self.avg_cost[key] += gross + fee + tax

    def apply_sell(
        self,
        *,
        key: Tuple[str, str, str],
        quantity: float,
        price: float,
        fee: float,
        tax: float,
        cost_method: str,
    ) -> None:
        currency = key[2]
        proceeds_net = quantity * price - fee - tax
        self.cash_by_currency[currency] += proceeds_net
        self.fees_paid += fee
        self.taxes_paid += tax
        cost_basis = self._consume(key=key, quantity=quantity, cost_method=cost_method)
        self.realized_local += proceeds_net - cost_basis

    def apply_dividend(
        self, *, key: Tuple[str, str, str], per_share: float, cost_method: str
    ) -> None:
        qty = self.held_qty(key, cost_method)
        if qty > EPS and per_share > 0:
            self.cash_by_currency[key[2]] += qty * per_share

    def apply_split(
        self, *, key: Tuple[str, str, str], ratio: float, cost_method: str
    ) -> None:
        if abs(ratio - 1.0) <= EPS:
            return
        if cost_method == "fifo":
            for lot in self.fifo_lots[key]:
                lot.quantity *= ratio
                lot.unit_cost /= ratio
        else:
            self.avg_qty[key] *= ratio

    def _consume(
        self,
        *,
        key: Tuple[str, str, str],
        quantity: float,
        cost_method: str,
    ) -> float:
        remaining = quantity
        cost_basis = 0.0
        if cost_method == "fifo":
            lots = self.fifo_lots[key]
            while remaining > EPS and lots:
                lot = lots[0]
                take = min(lot.quantity, remaining)
                cost_basis += take * lot.unit_cost
                lot.quantity -= take
                remaining -= take
                if lot.quantity <= EPS:
                    lots.pop(0)
        else:
            qty = self.avg_qty[key]
            total_cost = self.avg_cost[key]
            if qty <= EPS:
                return 0.0
            unit = total_cost / qty
            cost_basis = unit * quantity
            self.avg_qty[key] = qty - quantity
            self.avg_cost[key] = total_cost - cost_basis
            if self.avg_qty[key] <= EPS:
                self.avg_qty[key] = 0.0
                self.avg_cost[key] = 0.0
        return cost_basis


def _parse_iso_date(value: Any) -> date:
    if isinstance(value, date) and value.__class__ is date:
        return value
    if hasattr(value, "date") and callable(value.date):
        try:
            return value.date()  # datetime → date
        except Exception:
            pass
    return date.fromisoformat(str(value)[:10])


class PortfolioMoneyPropertiesTestCase(unittest.TestCase):
    """Deterministic randomized sequences over portfolio money mutations."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.db_path = Path(self.temp_dir.name) / "portfolio_money_props.db"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.service = PortfolioService()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def _save_close(self, symbol: str, on_date: date, close: float) -> None:
        df = pd.DataFrame(
            [
                {
                    "date": on_date,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": 1.0,
                    "amount": close,
                    "pct_chg": 0.0,
                }
            ]
        )
        self.db.save_daily_data(df, code=symbol, data_source="unit-test")

    def _create_cn_account(
        self, *, name: str = "Props", owner_id: Optional[str] = None
    ) -> int:
        account = self.service.create_account(
            name=name,
            broker="Demo",
            market=MARKET,
            base_currency=CURRENCY,
            owner_id=owner_id,
        )
        return int(account["id"])

    def _snapshot(
        self,
        *,
        account_id: int,
        as_of: date = AS_OF,
        cost_method: str = "fifo",
    ) -> Dict[str, Any]:
        return self.service.get_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            include_realtime=False,
        )

    def _account_row(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        self.assertEqual(len(snapshot["accounts"]), 1)
        return snapshot["accounts"][0]

    def _event_counts(self, account_id: int) -> Tuple[int, int, int]:
        trades = self.service.list_trade_events(
            account_id=account_id, page=1, page_size=1
        )
        cash = self.service.list_cash_ledger_events(
            account_id=account_id, page=1, page_size=1
        )
        corps = self.service.list_corporate_action_events(
            account_id=account_id, page=1, page_size=1
        )
        return int(trades["total"]), int(cash["total"]), int(corps["total"])

    def _load_persisted_snapshot(
        self,
        *,
        account_id: int,
        as_of: date,
        cost_method: str,
    ) -> PortfolioDailySnapshot:
        with DatabaseManager.get_instance().get_session() as session:
            row = session.execute(
                select(PortfolioDailySnapshot).where(
                    PortfolioDailySnapshot.account_id == account_id,
                    PortfolioDailySnapshot.snapshot_date == as_of,
                    PortfolioDailySnapshot.cost_method == cost_method,
                )
            ).scalar_one()
            session.expunge(row)
            return row

    def _list_all_events(
        self, account_id: int
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        def _all(list_fn) -> List[Dict[str, Any]]:
            page = 1
            page_size = 100
            items: List[Dict[str, Any]] = []
            while True:
                payload = list_fn(account_id=account_id, page=page, page_size=page_size)
                batch = list(payload["items"])
                items.extend(batch)
                if len(items) >= int(payload["total"]) or not batch:
                    break
                page += 1
            return items

        trades = _all(self.service.list_trade_events)
        cash = _all(self.service.list_cash_ledger_events)
        corps = _all(self.service.list_corporate_action_events)
        return trades, cash, corps

    def _oracle_from_events(
        self,
        *,
        account_id: int,
        cost_method: str,
        as_of: date = AS_OF,
    ) -> Tuple[LedgerOracle, int, int, int]:
        trades, cash_rows, corps = self._list_all_events(account_id)
        events: List[Tuple[str, date, int, Dict[str, Any]]] = []
        for row in cash_rows:
            event_date = _parse_iso_date(row["event_date"])
            if event_date > as_of:
                continue
            events.append(("cash", event_date, int(row["id"]), row))
        for row in trades:
            event_date = _parse_iso_date(row["trade_date"])
            if event_date > as_of:
                continue
            events.append(("trade", event_date, int(row["id"]), row))
        for row in corps:
            event_date = _parse_iso_date(row["effective_date"])
            if event_date > as_of:
                continue
            events.append(("corp", event_date, int(row["id"]), row))

        # Match PortfolioService._replay_account: cash → corp → trade.
        priority = {"cash": 0, "corp": 1, "trade": 2}
        events.sort(key=lambda item: (item[1], priority[item[0]], item[2]))

        oracle = LedgerOracle()
        for event_type, _event_date, _event_id, row in events:
            if event_type == "cash":
                oracle.apply_cash(
                    direction=str(row["direction"]).strip().lower(),
                    amount=float(row["amount"]),
                    currency=str(row["currency"]).strip().upper(),
                )
                continue
            if event_type == "trade":
                key = (
                    self.service._normalize_symbol_for_position(str(row["symbol"])),
                    self.service._normalize_market(str(row["market"])),
                    self.service._normalize_currency(str(row["currency"])),
                )
                side = str(row["side"]).strip().lower()
                qty = float(row["quantity"])
                price = float(row["price"])
                fee = float(row.get("fee") or 0.0)
                tax = float(row.get("tax") or 0.0)
                if side == "buy":
                    oracle.apply_buy(
                        key=key,
                        quantity=qty,
                        price=price,
                        fee=fee,
                        tax=tax,
                        cost_method=cost_method,
                    )
                elif side == "sell":
                    oracle.apply_sell(
                        key=key,
                        quantity=qty,
                        price=price,
                        fee=fee,
                        tax=tax,
                        cost_method=cost_method,
                    )
                else:
                    raise AssertionError(f"unexpected side {side!r}")
                continue
            if event_type == "corp":
                key = (
                    self.service._normalize_symbol_for_position(str(row["symbol"])),
                    self.service._normalize_market(str(row["market"])),
                    self.service._normalize_currency(str(row["currency"])),
                )
                action = str(row["action_type"]).strip().lower()
                if action == "cash_dividend":
                    oracle.apply_dividend(
                        key=key,
                        per_share=float(row.get("cash_dividend_per_share") or 0.0),
                        cost_method=cost_method,
                    )
                elif action == "split_adjustment":
                    oracle.apply_split(
                        key=key,
                        ratio=float(row.get("split_ratio") or 0.0),
                        cost_method=cost_method,
                    )
                else:
                    raise AssertionError(f"unexpected corp action {action!r}")

        return oracle, len(trades), len(cash_rows), len(corps)

    def _assert_equity_identity(self, account: Dict[str, Any], *, label: str) -> None:
        cash = float(account["total_cash"])
        mv = float(account["total_market_value"])
        equity = float(account["total_equity"])
        self.assertAlmostEqual(
            equity,
            cash + mv,
            places=FLOAT_PLACES,
            msg=f"{label}: total_equity must equal total_cash + total_market_value",
        )

    def _assert_oracle_matches_snapshot(
        self,
        *,
        account: Dict[str, Any],
        oracle: LedgerOracle,
        cost_method: str,
        label: str,
    ) -> None:
        self.assertAlmostEqual(
            float(account["total_cash"]),
            oracle.local_cash(CURRENCY),
            places=FLOAT_PLACES,
            msg=f"{label}: cash diverged from event-order oracle",
        )
        self.assertAlmostEqual(
            float(account["fee_total"]),
            oracle.fees_paid,
            places=FLOAT_PLACES,
            msg=f"{label}: fee_total diverged from event-order oracle",
        )
        self.assertAlmostEqual(
            float(account["tax_total"]),
            oracle.taxes_paid,
            places=FLOAT_PLACES,
            msg=f"{label}: tax_total diverged from event-order oracle",
        )
        self.assertAlmostEqual(
            float(account["realized_pnl"]),
            oracle.realized_local,
            places=FLOAT_PLACES,
            msg=f"{label}: realized_pnl diverged from event-order oracle",
        )
        held = oracle.held_qty((SYMBOL, MARKET, CURRENCY), cost_method)
        positions = account["positions"]
        if held <= EPS:
            self.assertEqual(positions, [], msg=f"{label}: expected no open positions")
        else:
            self.assertEqual(len(positions), 1, msg=f"{label}: expected one open position")
            self.assertAlmostEqual(
                float(positions[0]["quantity"]),
                held,
                places=FLOAT_PLACES,
                msg=f"{label}: open quantity mismatch",
            )

    def _available_qty(self, account_id: int, as_of_date: date) -> float:
        key = (
            self.service._normalize_symbol_for_position(SYMBOL),
            MARKET,
            CURRENCY,
        )
        return float(
            self.service._calculate_available_quantity(
                account_id=account_id,
                key=key,
                as_of_date=as_of_date,
            )
        )

    def _run_randomized_sequence(
        self,
        *,
        seed: int,
        cost_method: str,
        length: int = SEQUENCE_LENGTH,
    ) -> Tuple[int, LedgerOracle, Dict[str, Any], int, int, int]:
        rng = random.Random(seed)
        account_id = self._create_cn_account(name=f"seq-{seed}-{cost_method}")
        day_offset = 0
        op_serial = 0
        unique_cash_ops = 0
        unique_trade_ops = 0
        unique_corp_ops = 0

        for i in range(length + 5):
            px = 80.0 + (i % 17) * 3.0
            self._save_close(SYMBOL, BASE_DAY + timedelta(days=i), px)
        self._save_close(SYMBOL, AS_OF, 80.0 + ((length + 2) % 17) * 3.0)

        deposit = float(rng.randint(50_000, 200_000))
        self.service.record_cash_ledger(
            account_id=account_id,
            event_date=BASE_DAY,
            direction="in",
            amount=deposit,
            currency=CURRENCY,
            operation_id=f"seed-{seed}-deposit",
        )
        unique_cash_ops += 1

        for _step in range(length):
            day_offset = min(day_offset + rng.randint(0, 1), (AS_OF - BASE_DAY).days)
            event_date = BASE_DAY + timedelta(days=day_offset)
            held = self._available_qty(account_id, event_date)

            choices = ["cash_in", "buy", "noop_idempotent_cash"]
            if held > EPS:
                choices.extend(["sell", "dividend", "split"])
            if rng.random() < 0.25:
                choices.append("cash_out")

            weights = []
            for choice in choices:
                if choice in {"buy", "cash_in", "sell"}:
                    weights.append(3)
                elif choice == "noop_idempotent_cash":
                    weights.append(2)
                else:
                    weights.append(1)
            op = rng.choices(choices, weights=weights, k=1)[0]
            op_serial += 1

            if op == "cash_in":
                amount = float(rng.randint(100, 5000))
                oid = f"seed-{seed}-cash-in-{op_serial}"
                first = self.service.record_cash_ledger(
                    account_id=account_id,
                    event_date=event_date,
                    direction="in",
                    amount=amount,
                    currency=CURRENCY,
                    operation_id=oid,
                )
                second = self.service.record_cash_ledger(
                    account_id=account_id,
                    event_date=event_date,
                    direction="in",
                    amount=amount,
                    currency=CURRENCY,
                    operation_id=oid,
                )
                self.assertEqual(second, first)
                unique_cash_ops += 1

            elif op == "cash_out":
                amount = float(rng.randint(10, 2000))
                oid = f"seed-{seed}-cash-out-{op_serial}"
                first = self.service.record_cash_ledger(
                    account_id=account_id,
                    event_date=event_date,
                    direction="out",
                    amount=amount,
                    currency=CURRENCY,
                    operation_id=oid,
                )
                second = self.service.record_cash_ledger(
                    account_id=account_id,
                    event_date=event_date,
                    direction="out",
                    amount=amount,
                    currency=CURRENCY,
                    operation_id=oid,
                )
                self.assertEqual(second, first)
                unique_cash_ops += 1

            elif op == "buy":
                qty = float(rng.choice([10, 20, 50, 100]))
                price = float(rng.randint(50, 150))
                fee = float(rng.choice([0.0, 1.0, 2.5]))
                tax = float(rng.choice([0.0, 0.5, 1.0]))
                oid = f"seed-{seed}-buy-{op_serial}"
                kwargs = dict(
                    account_id=account_id,
                    symbol=SYMBOL,
                    trade_date=event_date,
                    side="buy",
                    quantity=qty,
                    price=price,
                    fee=fee,
                    tax=tax,
                    market=MARKET,
                    currency=CURRENCY,
                    operation_id=oid,
                )
                first = self.service.record_trade(**kwargs)
                second = self.service.record_trade(**kwargs)
                self.assertEqual(second, first)
                unique_trade_ops += 1

            elif op == "sell":
                available = self._available_qty(account_id, event_date)
                if available <= EPS:
                    continue
                candidates = [
                    q for q in (10.0, 20.0, 50.0, 100.0) if q <= available + EPS
                ]
                sell_qty = (
                    float(rng.choice(candidates)) if candidates else float(available)
                )
                sell_qty = min(sell_qty, available)
                if sell_qty <= EPS:
                    continue
                price = float(rng.randint(50, 150))
                fee = float(rng.choice([0.0, 1.0, 2.5]))
                tax = float(rng.choice([0.0, 0.5, 1.0]))
                oid = f"seed-{seed}-sell-{op_serial}"
                kwargs = dict(
                    account_id=account_id,
                    symbol=SYMBOL,
                    trade_date=event_date,
                    side="sell",
                    quantity=sell_qty,
                    price=price,
                    fee=fee,
                    tax=tax,
                    market=MARKET,
                    currency=CURRENCY,
                    operation_id=oid,
                )
                first = self.service.record_trade(**kwargs)
                second = self.service.record_trade(**kwargs)
                self.assertEqual(second, first)
                unique_trade_ops += 1

            elif op == "dividend":
                available = self._available_qty(account_id, event_date)
                if available <= EPS:
                    continue
                per_share = float(rng.choice([0.1, 0.5, 1.0, 2.0]))
                oid = f"seed-{seed}-div-{op_serial}"
                kwargs = dict(
                    account_id=account_id,
                    symbol=SYMBOL,
                    effective_date=event_date,
                    action_type="cash_dividend",
                    market=MARKET,
                    currency=CURRENCY,
                    cash_dividend_per_share=per_share,
                    operation_id=oid,
                )
                first = self.service.record_corporate_action(**kwargs)
                second = self.service.record_corporate_action(**kwargs)
                self.assertEqual(second, first)
                unique_corp_ops += 1

            elif op == "split":
                available = self._available_qty(account_id, event_date)
                if available <= EPS:
                    continue
                ratio = float(rng.choice([2.0, 0.5, 1.5]))
                oid = f"seed-{seed}-split-{op_serial}"
                kwargs = dict(
                    account_id=account_id,
                    symbol=SYMBOL,
                    effective_date=event_date,
                    action_type="split_adjustment",
                    market=MARKET,
                    currency=CURRENCY,
                    split_ratio=ratio,
                    operation_id=oid,
                )
                first = self.service.record_corporate_action(**kwargs)
                second = self.service.record_corporate_action(**kwargs)
                self.assertEqual(second, first)
                unique_corp_ops += 1

            elif op == "noop_idempotent_cash":
                amount = float(rng.randint(10, 200))
                oid = f"seed-{seed}-idem-cash-{op_serial}"
                first = self.service.record_cash_ledger(
                    account_id=account_id,
                    event_date=event_date,
                    direction="in",
                    amount=amount,
                    currency=CURRENCY,
                    operation_id=oid,
                )
                second = self.service.record_cash_ledger(
                    account_id=account_id,
                    event_date=event_date,
                    direction="in",
                    amount=amount,
                    currency=CURRENCY,
                    operation_id=oid,
                )
                self.assertEqual(second, first)
                unique_cash_ops += 1

        snapshot = self._snapshot(account_id=account_id, cost_method=cost_method)
        oracle, trade_n, cash_n, corp_n = self._oracle_from_events(
            account_id=account_id,
            cost_method=cost_method,
        )
        self.assertEqual(trade_n, unique_trade_ops)
        self.assertEqual(cash_n, unique_cash_ops)
        self.assertEqual(corp_n, unique_corp_ops)
        return account_id, oracle, snapshot, trade_n, cash_n, corp_n

    def test_randomized_sequence_conserves_cash_and_equity_fifo(self) -> None:
        for seed in PROPERTY_SEEDS:
            with self.subTest(seed=seed, cost_method="fifo"):
                _account_id, oracle, snapshot, _t, _c, _k = self._run_randomized_sequence(
                    seed=seed,
                    cost_method="fifo",
                )
                account = self._account_row(snapshot)
                label = f"fifo seed={seed}"
                self._assert_equity_identity(account, label=label)
                self._assert_oracle_matches_snapshot(
                    account=account,
                    oracle=oracle,
                    cost_method="fifo",
                    label=label,
                )

    def test_randomized_sequence_conserves_cash_and_equity_avg(self) -> None:
        for seed in PROPERTY_SEEDS:
            with self.subTest(seed=seed, cost_method="avg"):
                _account_id, oracle, snapshot, _t, _c, _k = self._run_randomized_sequence(
                    seed=seed + 17,
                    cost_method="avg",
                )
                account = self._account_row(snapshot)
                label = f"avg seed={seed}"
                self._assert_equity_identity(account, label=label)
                self._assert_oracle_matches_snapshot(
                    account=account,
                    oracle=oracle,
                    cost_method="avg",
                    label=label,
                )

    def test_closed_book_equity_equals_net_external_plus_realized(self) -> None:
        """After full liquidation on distinct dates, wealth identity holds.

        cash = deposits - withdrawals + realized + dividends
        equity = cash (no open market value)
        """

        for seed in PROPERTY_SEEDS:
            with self.subTest(seed=seed):
                rng = random.Random(seed + 99)
                account_id = self._create_cn_account(name=f"closed-{seed}")
                cost_method = "fifo"

                for i in range(12):
                    self._save_close(SYMBOL, BASE_DAY + timedelta(days=i), 100.0 + i)
                self._save_close(SYMBOL, AS_OF, 110.0)

                deposits = 100_000.0
                withdrawals = 0.0
                day = BASE_DAY

                self.service.record_cash_ledger(
                    account_id=account_id,
                    event_date=day,
                    direction="in",
                    amount=deposits,
                    currency=CURRENCY,
                    operation_id=f"closed-{seed}-dep",
                )

                for i in range(6):
                    day = BASE_DAY + timedelta(days=i + 1)
                    available = self._available_qty(account_id, day)
                    if available < EPS or rng.random() < 0.65:
                        qty = float(rng.choice([10, 20, 50]))
                        price = float(rng.randint(90, 120))
                        fee = float(rng.choice([0.0, 1.0]))
                        self.service.record_trade(
                            account_id=account_id,
                            symbol=SYMBOL,
                            trade_date=day,
                            side="buy",
                            quantity=qty,
                            price=price,
                            fee=fee,
                            tax=0.0,
                            market=MARKET,
                            currency=CURRENCY,
                            operation_id=f"closed-{seed}-buy-{i}",
                        )
                    else:
                        qty = min(available, float(rng.choice([10, 20, 50])))
                        if qty <= EPS:
                            continue
                        price = float(rng.randint(90, 120))
                        fee = float(rng.choice([0.0, 1.0]))
                        tax = float(rng.choice([0.0, 0.5]))
                        self.service.record_trade(
                            account_id=account_id,
                            symbol=SYMBOL,
                            trade_date=day,
                            side="sell",
                            quantity=qty,
                            price=price,
                            fee=fee,
                            tax=tax,
                            market=MARKET,
                            currency=CURRENCY,
                            operation_id=f"closed-{seed}-sell-{i}",
                        )

                day = BASE_DAY + timedelta(days=8)
                available = self._available_qty(account_id, day)
                dividends = 0.0
                if available > EPS:
                    per_share = 1.0
                    dividends = available * per_share
                    self.service.record_corporate_action(
                        account_id=account_id,
                        symbol=SYMBOL,
                        effective_date=day,
                        action_type="cash_dividend",
                        market=MARKET,
                        currency=CURRENCY,
                        cash_dividend_per_share=per_share,
                        operation_id=f"closed-{seed}-div",
                    )

                day = BASE_DAY + timedelta(days=9)
                available = self._available_qty(account_id, day)
                if available > EPS:
                    self.service.record_trade(
                        account_id=account_id,
                        symbol=SYMBOL,
                        trade_date=day,
                        side="sell",
                        quantity=available,
                        price=110.0,
                        fee=0.0,
                        tax=0.0,
                        market=MARKET,
                        currency=CURRENCY,
                        operation_id=f"closed-{seed}-liq",
                    )

                oracle, _t, _c, _k = self._oracle_from_events(
                    account_id=account_id,
                    cost_method=cost_method,
                )
                if oracle.local_cash() > 1000:
                    withdrawals = 500.0
                    self.service.record_cash_ledger(
                        account_id=account_id,
                        event_date=BASE_DAY + timedelta(days=10),
                        direction="out",
                        amount=withdrawals,
                        currency=CURRENCY,
                        operation_id=f"closed-{seed}-wd",
                    )
                    oracle, _t, _c, _k = self._oracle_from_events(
                        account_id=account_id,
                        cost_method=cost_method,
                    )

                snapshot = self._snapshot(account_id=account_id, cost_method=cost_method)
                account = self._account_row(snapshot)
                label = f"closed seed={seed}"
                self._assert_equity_identity(account, label=label)
                self.assertEqual(account["positions"], [], msg=f"{label}: not fully closed")
                self.assertAlmostEqual(
                    float(account["total_market_value"]),
                    0.0,
                    places=FLOAT_PLACES,
                )
                self._assert_oracle_matches_snapshot(
                    account=account,
                    oracle=oracle,
                    cost_method=cost_method,
                    label=label,
                )

                expected_cash = (
                    deposits - withdrawals + float(account["realized_pnl"]) + dividends
                )
                self.assertAlmostEqual(
                    float(account["total_cash"]),
                    expected_cash,
                    places=FLOAT_PLACES,
                    msg=f"{label}: closed-book wealth identity failed",
                )
                self.assertAlmostEqual(
                    float(account["total_equity"]),
                    expected_cash,
                    places=FLOAT_PLACES,
                    msg=f"{label}: closed equity should equal cash",
                )

    def test_idempotency_is_scoped_per_account(self) -> None:
        a1 = self._create_cn_account(name="scope-a", owner_id="owner-a")
        a2 = self._create_cn_account(name="scope-b", owner_id="owner-b")
        operation_id = "shared-client-op-1"

        r1 = self.service.record_cash_ledger(
            account_id=a1,
            event_date=BASE_DAY,
            direction="in",
            amount=1000.0,
            currency=CURRENCY,
            operation_id=operation_id,
        )
        r1_again = self.service.record_cash_ledger(
            account_id=a1,
            event_date=BASE_DAY,
            direction="in",
            amount=1000.0,
            currency=CURRENCY,
            operation_id=operation_id,
        )
        self.assertEqual(r1_again, r1)

        r2 = self.service.record_cash_ledger(
            account_id=a2,
            event_date=BASE_DAY,
            direction="in",
            amount=1000.0,
            currency=CURRENCY,
            operation_id=operation_id,
        )
        self.assertNotEqual(r2["id"], r1["id"])

        _, cash1, _ = self._event_counts(a1)
        _, cash2, _ = self._event_counts(a2)
        self.assertEqual(cash1, 1)
        self.assertEqual(cash2, 1)

        snap1 = self._account_row(self._snapshot(account_id=a1))
        snap2 = self._account_row(self._snapshot(account_id=a2))
        self.assertAlmostEqual(float(snap1["total_cash"]), 1000.0, places=FLOAT_PLACES)
        self.assertAlmostEqual(float(snap2["total_cash"]), 1000.0, places=FLOAT_PLACES)

    def test_idempotency_conflict_does_not_mutate_ledger(self) -> None:
        account_id = self._create_cn_account(name="conflict")
        operation_id = "conflict-op-1"
        self.service.record_cash_ledger(
            account_id=account_id,
            event_date=BASE_DAY,
            direction="in",
            amount=1000.0,
            currency=CURRENCY,
            operation_id=operation_id,
        )
        with self.assertRaises(PortfolioIdempotencyConflictError):
            self.service.record_cash_ledger(
                account_id=account_id,
                event_date=BASE_DAY,
                direction="in",
                amount=2000.0,
                currency=CURRENCY,
                operation_id=operation_id,
            )
        _, cash_count, _ = self._event_counts(account_id)
        self.assertEqual(cash_count, 1)
        account = self._account_row(self._snapshot(account_id=account_id))
        self.assertAlmostEqual(float(account["total_cash"]), 1000.0, places=FLOAT_PLACES)

    def test_fx_pair_isolation_and_multi_currency_conversion(self) -> None:
        cn_id = self._create_cn_account(name="fx-cn")
        self.service.record_cash_ledger(
            account_id=cn_id,
            event_date=BASE_DAY,
            direction="in",
            amount=10_000.0,
            currency="CNY",
            operation_id="fx-cn-dep",
        )

        us_like = self.service.create_account(
            name="fx-us-cash",
            broker="Demo",
            market="us",
            base_currency="CNY",
        )
        us_id = int(us_like["id"])
        self.service.record_cash_ledger(
            account_id=us_id,
            event_date=BASE_DAY,
            direction="in",
            amount=1_000.0,
            currency="USD",
            operation_id="fx-us-dep",
        )
        self.service.record_trade(
            account_id=us_id,
            symbol="AAPL",
            trade_date=BASE_DAY + timedelta(days=1),
            side="buy",
            quantity=10,
            price=100.0,
            fee=0.0,
            tax=0.0,
            market="us",
            currency="USD",
            operation_id="fx-us-buy",
        )
        self._save_close("AAPL", AS_OF, 110.0)

        self.service.repo.save_fx_rate(
            from_currency="USD",
            to_currency="CNY",
            rate_date=BASE_DAY,
            rate=7.0,
            source="manual",
            is_stale=False,
        )

        snap_cn_before = self._account_row(self._snapshot(account_id=cn_id))
        snap_us_before = self._account_row(self._snapshot(account_id=us_id))
        self.assertAlmostEqual(
            float(snap_cn_before["total_cash"]), 10_000.0, places=FLOAT_PLACES
        )
        self.assertAlmostEqual(
            float(snap_us_before["total_cash"]), 0.0, places=FLOAT_PLACES
        )
        self.assertAlmostEqual(
            float(snap_us_before["total_market_value"]),
            7700.0,
            places=FLOAT_PLACES,
        )
        self.assertFalse(snap_us_before["fx_stale"])

        self.service.repo.save_fx_rate(
            from_currency="EUR",
            to_currency="CNY",
            rate_date=BASE_DAY,
            rate=8.0,
            source="manual",
            is_stale=False,
        )
        self.service.repo.save_fx_rate(
            from_currency="EUR",
            to_currency="USD",
            rate_date=BASE_DAY,
            rate=1.1,
            source="manual",
            is_stale=False,
        )

        snap_cn_after = self._account_row(self._snapshot(account_id=cn_id))
        snap_us_after = self._account_row(self._snapshot(account_id=us_id))

        for field_name in (
            "total_cash",
            "total_market_value",
            "total_equity",
            "realized_pnl",
            "unrealized_pnl",
            "fee_total",
            "tax_total",
        ):
            self.assertAlmostEqual(
                float(snap_cn_before[field_name]),
                float(snap_cn_after[field_name]),
                places=FLOAT_PLACES,
                msg=f"CN account field {field_name} changed after unrelated FX write",
            )
            self.assertAlmostEqual(
                float(snap_us_before[field_name]),
                float(snap_us_after[field_name]),
                places=FLOAT_PLACES,
                msg=f"USD account field {field_name} changed after unrelated FX write",
            )

        self.service.repo.save_fx_rate(
            from_currency="USD",
            to_currency="CNY",
            rate_date=BASE_DAY,
            rate=7.5,
            source="manual",
            is_stale=False,
        )
        snap_cn_reprice = self._account_row(self._snapshot(account_id=cn_id))
        snap_us_reprice = self._account_row(self._snapshot(account_id=us_id))
        self.assertAlmostEqual(
            float(snap_cn_reprice["total_cash"]),
            10_000.0,
            places=FLOAT_PLACES,
            msg="CNY-only account must ignore USD/CNY rate changes",
        )
        self.assertAlmostEqual(
            float(snap_us_reprice["total_market_value"]),
            10 * 110.0 * 7.5,
            places=FLOAT_PLACES,
            msg="USD account must reprice via the updated USD/CNY rate",
        )

    def test_fx_inverse_rate_matches_direct_for_cash_conversion(self) -> None:
        for seed in PROPERTY_SEEDS:
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                rate = round(rng.uniform(6.0, 8.0), 4)
                amount = float(rng.randint(100, 10_000))

                account = self.service.create_account(
                    name=f"fx-inv-{seed}",
                    broker="Demo",
                    market="us",
                    base_currency="CNY",
                )
                aid = int(account["id"])
                self.service.record_cash_ledger(
                    account_id=aid,
                    event_date=BASE_DAY,
                    direction="in",
                    amount=amount,
                    currency="USD",
                    operation_id=f"fx-inv-dep-{seed}",
                )
                self.service.repo.save_fx_rate(
                    from_currency="CNY",
                    to_currency="USD",
                    rate_date=BASE_DAY,
                    rate=1.0 / rate,
                    source="manual",
                    is_stale=False,
                )
                snap = self._account_row(self._snapshot(account_id=aid))
                expected = amount * rate
                self.assertAlmostEqual(
                    float(snap["total_cash"]),
                    expected,
                    places=4,
                    msg=f"inverse FX conversion failed seed={seed} rate={rate}",
                )
                self.assertFalse(snap["fx_stale"])

    def test_projection_after_write_matches_live_replay(self) -> None:
        for seed in PROPERTY_SEEDS:
            with self.subTest(seed=seed):
                account_id, oracle, snapshot, _t, _c, _k = self._run_randomized_sequence(
                    seed=seed + 101,
                    cost_method="fifo",
                    length=24,
                )
                account = self._account_row(snapshot)
                label = f"projection seed={seed}"

                persisted = self._load_persisted_snapshot(
                    account_id=account_id,
                    as_of=AS_OF,
                    cost_method="fifo",
                )
                for field_name, attr in (
                    ("total_cash", "total_cash"),
                    ("total_market_value", "total_market_value"),
                    ("total_equity", "total_equity"),
                    ("realized_pnl", "realized_pnl"),
                    ("unrealized_pnl", "unrealized_pnl"),
                    ("fee_total", "fee_total"),
                    ("tax_total", "tax_total"),
                ):
                    self.assertAlmostEqual(
                        float(getattr(persisted, attr)),
                        float(account[field_name]),
                        places=FLOAT_PLACES,
                        msg=f"{label}: persisted {field_name} != live",
                    )

                again = self._account_row(
                    self._snapshot(account_id=account_id, cost_method="fifo")
                )
                for field_name in (
                    "total_cash",
                    "total_market_value",
                    "total_equity",
                    "realized_pnl",
                    "unrealized_pnl",
                    "fee_total",
                    "tax_total",
                ):
                    self.assertAlmostEqual(
                        float(account[field_name]),
                        float(again[field_name]),
                        places=FLOAT_PLACES,
                        msg=f"{label}: re-projection drift on {field_name}",
                    )

                self._assert_oracle_matches_snapshot(
                    account=again,
                    oracle=oracle,
                    cost_method="fifo",
                    label=label,
                )
                self._assert_equity_identity(again, label=label)

    def test_aggregate_snapshot_sums_account_projections_under_fx(self) -> None:
        cn_id = self._create_cn_account(name="agg-cn")
        self.service.record_cash_ledger(
            account_id=cn_id,
            event_date=BASE_DAY,
            direction="in",
            amount=5_000.0,
            currency="CNY",
            operation_id="agg-cn-dep",
        )

        us_account = self.service.create_account(
            name="agg-us",
            broker="Demo",
            market="us",
            base_currency="USD",
        )
        us_id = int(us_account["id"])
        self.service.record_cash_ledger(
            account_id=us_id,
            event_date=BASE_DAY,
            direction="in",
            amount=1_000.0,
            currency="USD",
            operation_id="agg-us-dep",
        )
        self.service.repo.save_fx_rate(
            from_currency="USD",
            to_currency="CNY",
            rate_date=BASE_DAY,
            rate=7.0,
            source="manual",
            is_stale=False,
        )

        self._snapshot(account_id=cn_id)
        self._snapshot(account_id=us_id)
        aggregate = self.service.get_portfolio_snapshot(
            account_id=None,
            as_of=AS_OF,
            cost_method="fifo",
            include_realtime=False,
        )
        self.assertEqual(aggregate["currency"], "CNY")
        self.assertEqual(aggregate["account_count"], 2)
        self.assertAlmostEqual(
            float(aggregate["total_cash"]),
            5_000.0 + 1_000.0 * 7.0,
            places=FLOAT_PLACES,
        )
        self.assertAlmostEqual(
            float(aggregate["total_equity"]),
            float(aggregate["total_cash"]) + float(aggregate["total_market_value"]),
            places=FLOAT_PLACES,
        )


if __name__ == "__main__":
    unittest.main()
