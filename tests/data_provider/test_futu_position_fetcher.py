# -*- coding: utf-8 -*-
"""Deterministic tests for Futu OpenD position fetch and import mapping."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from data_provider import futu_position_fetcher as fetcher


class _Table:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows

    def iterrows(self):
        for index, row in enumerate(self._rows):
            yield index, row


class _TradeContext:
    def __init__(self, account_rows, positions_by_account) -> None:
        self.account_rows = account_rows
        self.positions_by_account = positions_by_account
        self.closed = False

    def get_acc_list(self):
        return 0, _Table(self.account_rows)

    def position_list_query(self, *, trd_env, acc_id, refresh_cache):
        assert trd_env == "REAL"
        assert refresh_cache is True
        return 0, _Table(self.positions_by_account.get(acc_id, []))

    def close(self) -> None:
        self.closed = True


class _QuoteContext:
    def __init__(self, stock_types: Dict[str, str]) -> None:
        self.stock_types = stock_types
        self.closed = False

    def get_stock_basicinfo(self, market, *, stock_type, code_list):
        assert stock_type == "STOCK"
        return 0, _Table(
            [
                {"code": code, "stock_type": self.stock_types[code]}
                for code in code_list
                if code in self.stock_types
            ]
        )

    def close(self) -> None:
        self.closed = True


def _account(
    acc_id: int,
    *,
    trd_env: str = "REAL",
    acc_status: str = "ACTIVE",
    acc_role: str = "NORMAL",
    security_firm: str = "FUTUSECURITIES",
) -> Dict[str, Any]:
    return {
        "acc_id": acc_id,
        "trd_env": trd_env,
        "acc_status": acc_status,
        "acc_role": acc_role,
        "security_firm": security_firm,
    }


def _position(
    code: Optional[str],
    qty: Any = 1,
    side: str = "LONG",
    *,
    cost_price: Any = 10.0,
    nominal_price: Any = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "code": code,
        "qty": qty,
        "position_side": side,
        "cost_price": cost_price,
    }
    if nominal_price is not None:
        row["nominal_price"] = nominal_price
    return row


def _fake_api(
    account_rows: List[Dict[str, Any]],
    positions_by_account: Dict[int, List[Dict[str, Any]]],
    stock_types: Dict[str, str],
    *,
    fail_connect: bool = False,
):
    trade_contexts: List[_TradeContext] = []
    quote_contexts: List[_QuoteContext] = []

    def open_trade_context(*, filter_trdmarket, host, port, security_firm):
        if fail_connect:
            raise ConnectionError("OpenD connection refused")
        context = _TradeContext(account_rows, positions_by_account)
        trade_contexts.append(context)
        return context

    def open_quote_context(*, host, port):
        context = _QuoteContext(stock_types)
        quote_contexts.append(context)
        return context

    api = fetcher._FutuApi(
        OpenQuoteContext=open_quote_context,
        OpenSecTradeContext=open_trade_context,
        Market=SimpleNamespace(US="US", HK="HK", SH="SH", SZ="SZ", JP="JP"),
        RET_OK=0,
        SecurityFirm=SimpleNamespace(
            NONE="N/A",
            FUTUSECURITIES="FUTUSECURITIES",
            FUTUSG="FUTUSG",
        ),
        SecurityType=SimpleNamespace(STOCK="STOCK"),
        TrdEnv=SimpleNamespace(REAL="REAL"),
        TrdMarket=SimpleNamespace(NONE="NONE"),
    )
    return api, trade_contexts, quote_contexts


def test_fetch_maps_long_stocks_and_skips_non_stocks(monkeypatch) -> None:
    monkeypatch.delenv("FUTU_ACC_ID", raising=False)
    api, _, _ = _fake_api(
        [_account(101), _account(202, trd_env="SIMULATE")],
        {
            101: [
                _position("SH.600519", qty=100, cost_price=1500.5),
                _position("HK.00700", qty=20, cost_price=300.0),
                _position("US.AAPL", qty=5, cost_price=190.0),
                _position("US.SPY", qty=2, cost_price=400.0),
                _position("US.ZERO", qty=0, cost_price=1.0),
                _position("US.SHORT", qty=3, side="SHORT", cost_price=1.0),
            ],
        },
        {
            "SH.600519": "STOCK",
            "HK.00700": "STOCK",
            "US.AAPL": "STOCK",
            "US.SPY": "ETF",
            "US.ZERO": "STOCK",
            "US.SHORT": "STOCK",
        },
    )

    positions = fetcher.fetch_futu_positions(api=api)
    assert [(p.symbol, p.quantity, p.cost_price, p.currency) for p in positions] == [
        ("600519", 100.0, 1500.5, "CNY"),
        ("HK00700", 20.0, 300.0, "HKD"),
        ("AAPL", 5.0, 190.0, "USD"),
    ]


def test_positions_to_import_records_are_stable_and_idempotent_keys() -> None:
    positions = [
        fetcher.FutuPosition(
            futu_acc_id=101,
            futu_code="US.AAPL",
            symbol="AAPL",
            market="US",
            quantity=5.0,
            cost_price=190.0,
            currency="USD",
        )
    ]
    records = fetcher.positions_to_import_records(positions, as_of=date(2026, 8, 6))
    assert len(records) == 1
    record = records[0]
    assert record["side"] == "buy"
    assert record["trade_date"] == date(2026, 8, 6)
    assert record["trade_uid"] == "futu:101:AAPL:5.00000000:190.00000000"
    assert record["dedup_hash"]
    again = fetcher.positions_to_import_records(positions, as_of=date(2026, 8, 6))
    assert again[0]["trade_uid"] == record["trade_uid"]
    assert again[0]["dedup_hash"] == record["dedup_hash"]


def test_unreachable_opend_raises_actionable_error(monkeypatch) -> None:
    monkeypatch.delenv("FUTU_ACC_ID", raising=False)
    api, _, _ = _fake_api([], {}, {}, fail_connect=True)
    with pytest.raises(fetcher.FutuPositionFetchError, match="unreachable|OpenD"):
        fetcher.fetch_futu_positions(api=api)


def test_uses_nominal_price_when_cost_missing(monkeypatch) -> None:
    monkeypatch.delenv("FUTU_ACC_ID", raising=False)
    api, _, _ = _fake_api(
        [_account(101)],
        {
            101: [
                _position(
                    "US.MSFT",
                    qty=2,
                    cost_price=0,
                    nominal_price=420.25,
                )
            ]
        },
        {"US.MSFT": "STOCK"},
    )
    positions = fetcher.fetch_futu_positions(api=api)
    assert len(positions) == 1
    assert positions[0].cost_price == 420.25
