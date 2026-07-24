"""Offline contract tests for the read-only Futu portfolio adapter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.brokers.futu import portfolio


class _Table:
    def __init__(self, rows):
        self._rows = rows

    def iterrows(self):
        return iter(enumerate(self._rows))


class _TradeContext:
    def __init__(self, account_rows, positions_by_account):
        self.account_rows = account_rows
        self.positions_by_account = positions_by_account
        self.closed = False
        self.position_calls = []

    def get_acc_list(self):
        return 0, _Table(self.account_rows)

    def position_list_query(self, *, trd_env, acc_id, refresh_cache):
        self.position_calls.append((trd_env, acc_id, refresh_cache))
        return 0, _Table(self.positions_by_account.get(acc_id, []))

    def close(self):
        self.closed = True


class _QuoteContext:
    def __init__(self, stock_types):
        self.stock_types = stock_types
        self.calls = []
        self.closed = False

    def get_stock_basicinfo(self, market, *, stock_type, code_list):
        self.calls.append((market, stock_type, list(code_list)))
        rows = [
            {"code": code, "stock_type": self.stock_types[code]}
            for code in code_list
            if code in self.stock_types
        ]
        return 0, _Table(rows)

    def close(self):
        self.closed = True


def _row(**overrides):
    values = {
        "acc_id": 101,
        "trd_env": "REAL",
        "acc_status": "ACTIVE",
        "acc_role": "NORMAL",
        "security_firm": "FUTUSECURITIES",
    }
    values.update(overrides)
    return values


def _position(code, qty=1, side="LONG"):
    return {"code": code, "qty": qty, "position_side": side}


def _fake_api(account_rows, positions_by_account, stock_types):
    trade_contexts = []
    quote_contexts = []

    def trade_factory(**_kwargs):
        context = _TradeContext(account_rows, positions_by_account)
        trade_contexts.append(context)
        return context

    def quote_factory(**_kwargs):
        context = _QuoteContext(stock_types)
        quote_contexts.append(context)
        return context

    api = portfolio._FutuApi(
        OpenQuoteContext=quote_factory,
        OpenSecTradeContext=trade_factory,
        Market=SimpleNamespace(SH="SH", SZ="SZ", HK="HK", US="US"),
        RET_OK=0,
        SecurityFirm=SimpleNamespace(NONE="NONE", FUTUSECURITIES="FUTUSECURITIES"),
        SecurityType=SimpleNamespace(STOCK="STOCK"),
        TrdEnv=SimpleNamespace(REAL="REAL"),
        TrdMarket=SimpleNamespace(NONE="NONE"),
    )
    return api, trade_contexts, quote_contexts


def test_loads_only_supported_nonzero_long_stocks_and_closes_contexts(monkeypatch) -> None:
    monkeypatch.delenv("FUTU_ACC_ID", raising=False)
    api, trade_contexts, quote_contexts = _fake_api(
        [_row(), _row(acc_id=202, acc_role="MASTER")],
        {
            101: [
                _position("SH.600519"),
                _position("HK.00700", qty=2),
                _position("US.AAPL", qty=3),
                _position(None, side="SHORT"),
                _position("US.ZERO", qty=0),
                _position("US.SPY"),
            ],
            202: [
                _position("US.AAPL", qty=4),
                _position("JP.7203"),
            ],
        },
        {
            "SH.600519": "STOCK",
            "HK.00700": "STOCK",
            "US.AAPL": "STOCK",
            "US.SPY": "ETF",
        },
    )

    with patch.object(portfolio, "_load_futu_api", return_value=api):
        assert portfolio.load_futu_stock_codes() == ["600519", "HK00700", "AAPL"]

    assert len(trade_contexts) == 3
    assert all(context.closed for context in trade_contexts)
    assert len(quote_contexts) == 1
    assert quote_contexts[0].closed
    assert [call[1] for context in trade_contexts for call in context.position_calls] == [
        101,
        202,
    ]
    assert all(call[2] is True for context in trade_contexts for call in context.position_calls)


def test_empty_real_portfolio_is_preserved(monkeypatch) -> None:
    monkeypatch.delenv("FUTU_ACC_ID", raising=False)
    api, _trade_contexts, quote_contexts = _fake_api([_row()], {101: []}, {})

    with patch.object(portfolio, "_load_futu_api", return_value=api):
        assert portfolio.load_futu_stock_codes() == []

    assert quote_contexts == []


def test_configured_account_selects_one_active_real_account(monkeypatch) -> None:
    monkeypatch.setenv("FUTU_ACC_ID", "202")
    api, trade_contexts, _quote_contexts = _fake_api(
        [_row(), _row(acc_id=202, acc_role="MASTER")],
        {101: [_position("US.MSFT")], 202: [_position("US.AAPL")]},
        {"US.MSFT": "STOCK", "US.AAPL": "STOCK"},
    )

    with patch.object(portfolio, "_load_futu_api", return_value=api):
        assert portfolio.load_futu_stock_codes() == ["AAPL"]

    assert [call[1] for context in trade_contexts for call in context.position_calls] == [202]


@pytest.mark.parametrize(
    "account",
    [
        _row(trd_env="SIMULATE"),
        _row(acc_status="DISABLED"),
        _row(acc_role="CHILD"),
    ],
)
def test_rejects_when_no_eligible_real_account(account, monkeypatch) -> None:
    monkeypatch.delenv("FUTU_ACC_ID", raising=False)
    api, _trade_contexts, _quote_contexts = _fake_api([account], {}, {})

    with patch.object(portfolio, "_load_futu_api", return_value=api), pytest.raises(
        portfolio.FutuPortfolioError,
        match="No ACTIVE REAL",
    ):
        portfolio.load_futu_stock_codes()


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_rejects_invalid_configured_account_id(value, monkeypatch) -> None:
    monkeypatch.setenv("FUTU_ACC_ID", value)
    api, trade_contexts, _quote_contexts = _fake_api([_row()], {}, {})

    with patch.object(portfolio, "_load_futu_api", return_value=api), pytest.raises(
        portfolio.FutuPortfolioError,
        match="positive integer",
    ):
        portfolio.load_futu_stock_codes()

    assert trade_contexts == []


def test_short_and_unknown_sides_are_skipped_before_field_validation(monkeypatch) -> None:
    monkeypatch.delenv("FUTU_ACC_ID", raising=False)
    api, _trade_contexts, quote_contexts = _fake_api(
        [_row()],
        {101: [_position(None, qty=None, side="SHORT"), _position(None, qty=None, side="N/A")]},
        {},
    )

    with patch.object(portfolio, "_load_futu_api", return_value=api):
        assert portfolio.load_futu_stock_codes() == []

    assert quote_contexts == []


@pytest.mark.parametrize("quantity", [None, True, float("nan"), float("inf"), "bad"])
def test_rejects_invalid_nonzero_long_quantity(quantity, monkeypatch) -> None:
    monkeypatch.delenv("FUTU_ACC_ID", raising=False)
    api, _trade_contexts, _quote_contexts = _fake_api(
        [_row()],
        {101: [_position("US.AAPL", qty=quantity)]},
        {"US.AAPL": "STOCK"},
    )

    with patch.object(portfolio, "_load_futu_api", return_value=api), pytest.raises(
        portfolio.FutuPortfolioError,
        match="invalid position quantity",
    ):
        portfolio.load_futu_stock_codes()


@pytest.mark.parametrize("code", [None, "", "AAPL", ".AAPL", "US."])
def test_rejects_invalid_nonzero_long_code(code, monkeypatch) -> None:
    monkeypatch.delenv("FUTU_ACC_ID", raising=False)
    api, _trade_contexts, _quote_contexts = _fake_api(
        [_row()],
        {101: [_position(code)]},
        {},
    )

    with patch.object(portfolio, "_load_futu_api", return_value=api), pytest.raises(
        portfolio.FutuPortfolioError,
        match="invalid non-zero position code",
    ):
        portfolio.load_futu_stock_codes()


def test_rejects_partial_or_unknown_security_classification(monkeypatch) -> None:
    monkeypatch.delenv("FUTU_ACC_ID", raising=False)
    api, _trade_contexts, _quote_contexts = _fake_api(
        [_row()],
        {101: [_position("US.AAPL"), _position("US.MSFT")]},
        {"US.AAPL": "STOCK", "US.MSFT": "UNKNOWN"},
    )

    with patch.object(portfolio, "_load_futu_api", return_value=api), pytest.raises(
        portfolio.FutuPortfolioError,
        match="definitive security type",
    ):
        portfolio.load_futu_stock_codes()


def test_connection_settings_use_safe_defaults_and_reject_ipv6(monkeypatch) -> None:
    monkeypatch.delenv("FUTU_OPEND_HOST", raising=False)
    monkeypatch.delenv("FUTU_OPEND_PORT", raising=False)
    assert portfolio._connection_settings() == (
        portfolio.DEFAULT_OPEND_HOST,
        portfolio.DEFAULT_OPEND_PORT,
    )

    monkeypatch.setenv("FUTU_OPEND_HOST", "::1")
    with pytest.raises(portfolio.FutuPortfolioError, match="IPv4"):
        portfolio._connection_settings()


def test_unknown_security_firm_fails_before_opening_context(monkeypatch) -> None:
    monkeypatch.setenv("FUTU_SECURITY_FIRM", "UNKNOWN_FIRM")
    api, trade_contexts, _quote_contexts = _fake_api([_row()], {}, {})

    with patch.object(portfolio, "_load_futu_api", return_value=api), pytest.raises(
        portfolio.FutuPortfolioError,
        match="Unsupported FUTU_SECURITY_FIRM",
    ):
        portfolio.load_futu_stock_codes()

    assert trade_contexts == []
