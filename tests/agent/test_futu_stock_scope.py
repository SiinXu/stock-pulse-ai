"""Keep broker-sourced symbols aligned with Agent stock-scope identities."""

from src.agent.stock_scope import _normalize_stock_code


def test_agent_scope_uses_shared_broker_symbol_normalization() -> None:
    assert _normalize_stock_code("SH.600519") == "600519"
    assert _normalize_stock_code("HK.00700") == "HK00700"
    assert _normalize_stock_code("AAPL.US") == "AAPL"
