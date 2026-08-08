# -*- coding: utf-8 -*-
"""Deterministic tests for Today's Focus selection (Issue #157 / T26)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Sequence

from src.services.todays_focus_service import (
    DEFAULT_MAX_FOCUS_ITEMS,
    FocusEvidence,
    FocusItem,
    TodaysFocusService,
    format_reason_display,
    polish_reason_display_with_llm,
    select_focus_items,
)


def _ev(code, reason, detail="x", *, weight=None, priority=None):
    kwargs = {"code": code, "reason_code": reason, "detail": detail, "weight_pct": weight}
    if priority is not None:
        kwargs["priority"] = priority
    return FocusEvidence(**kwargs)


def test_empty_evidences_never_padded():
    assert select_focus_items([], max_items=5) == []


def test_hard_cap_truncates_without_padding():
    evidences = [
        _ev("A", "alert_triggered", "a"),
        _ev("B", "alert_triggered", "b"),
        _ev("C", "corporate_event", "c"),
        _ev("D", "analysis_reversal", "d"),
        _ev("E", "high_weight_move", "e", weight=20.0),
        _ev("F", "high_weight_move", "f", weight=15.0),
    ]
    items = select_focus_items(evidences, max_items=5)
    assert len(items) == 5
    assert "F" not in {i.code for i in items}


def test_priority_orders_alerts_above_weight_moves():
    items = select_focus_items([
        _ev("LOW", "high_weight_move", "w", weight=50.0),
        _ev("HIGH", "alert_triggered", "alert"),
    ], max_items=5)
    assert [i.code for i in items] == ["HIGH", "LOW"]


def test_same_symbol_merges_secondary_reasons():
    items = select_focus_items([
        _ev("AAPL", "high_weight_move", "w", weight=30.0),
        _ev("AAPL", "alert_triggered", "price break"),
        _ev("AAPL", "analysis_reversal", "buy → sell"),
    ], max_items=5)
    assert len(items) == 1
    assert items[0].reason_code == "alert_triggered"
    assert set(items[0].secondary_reason_codes) == {"high_weight_move", "analysis_reversal"}


def test_llm_polish_cannot_change_selection_set():
    evidences = [_ev("AAA", "alert_triggered", "a"), _ev("BBB", "corporate_event", "b")]
    selected = select_focus_items(evidences, max_items=5)

    def malicious_llm(text: str) -> str:
        return f"POLISHED:{text}"

    polished = select_focus_items(evidences, max_items=5, llm_call=malicious_llm)
    assert [i.code for i in polished] == [i.code for i in selected]
    assert [i.reason_code for i in polished] == [i.reason_code for i in selected]
    assert all(i.reason_display.startswith("POLISHED:") for i in polished)


def test_llm_polish_membership_guard_on_direct_hook():
    base = [FocusItem(code="X", reason_code="alert_triggered", reason_display="Alert triggered: x", priority=100)]
    out = polish_reason_display_with_llm(base, llm_call=lambda _t: "y")
    assert [i.code for i in out] == ["X"]
    assert out[0].reason_display == "y"


def test_format_reason_display_language():
    en = format_reason_display("alert_triggered", "breakout", language="en")
    zh = format_reason_display("alert_triggered", "breakout", language="zh")
    assert "breakout" in en and "breakout" in zh
    assert "告警" in zh


def test_service_empty_status_with_zero_cost_contract():
    service = TodaysFocusService(
        config_provider=lambda: SimpleNamespace(stock_list=[], report_language="en"),
        alert_service=SimpleNamespace(list_triggers=lambda **_k: {"items": []}),
        portfolio_service=SimpleNamespace(get_portfolio_snapshot=lambda **_k: {"accounts": [], "positions": []}),
        signal_changes_loader=lambda code, limit=2: [],
        clock=lambda: datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc),
    )
    payload = service.build_focus(max_items=5)
    assert payload["status"] == "empty"
    assert payload["items"] == []
    assert payload["empty_reason"] == "no_deterministic_signals"
    assert payload["cost_contract"]["zero_extra_fetch"] is True
    assert payload["max_items"] == DEFAULT_MAX_FOCUS_ITEMS


def test_service_injected_evidences_respect_cap_and_no_padding():
    service = TodaysFocusService(clock=lambda: datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc))
    evidences = [_ev(f"S{i}", "alert_triggered", str(i)) for i in range(3)]
    payload = service.build_focus(max_items=5, evidences=evidences)
    assert payload["status"] == "ok"
    assert payload["item_count"] == 3


def test_service_alert_and_reversal_collectors():
    class FakeAlerts:
        def list_triggers(self, **_kwargs):
            return {"items": [
                {"id": 1, "rule_id": 9, "target": "600519", "reason": "price above MA", "triggered_at": "2026-08-09T01:00:00", "status": "triggered"},
                {"id": 2, "rule_id": 10, "target": "OUTSIDER", "reason": "noise", "status": "triggered"},
            ]}

    class FakePortfolio:
        def get_portfolio_snapshot(self, **_kwargs):
            return {"accounts": [{"positions": [
                {"symbol": "AAPL", "market_value_base": 50_000, "unrealized_pnl_pct": 8.5, "name": "Apple"},
                {"symbol": "TINY", "market_value_base": 1_000, "unrealized_pnl_pct": 20.0},
            ]}]}

    def signals(code: str, limit: int = 2):
        if code == "600519":
            return [{"action": "sell", "query_id": "q2"}, {"action": "buy", "query_id": "q1"}]
        return []

    service = TodaysFocusService(
        config_provider=lambda: SimpleNamespace(stock_list=["600519", "AAPL"], report_language="en"),
        alert_service=FakeAlerts(),
        portfolio_service=FakePortfolio(),
        signal_changes_loader=signals,
        clock=lambda: datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc),
    )
    payload = service.build_focus(max_items=5)
    codes = {item["code"] for item in payload["items"]}
    assert "600519" in codes and "AAPL" in codes
    assert "OUTSIDER" not in codes and "TINY" not in codes
    row = next(i for i in payload["items"] if i["code"] == "600519")
    assert row["reason_code"] == "alert_triggered"
    assert "analysis_reversal" in row["secondary_reason_codes"]
    assert payload["cost_contract"]["zero_extra_fetch"] is True


def test_service_does_not_call_llm_by_default():
    calls = []
    service = TodaysFocusService(clock=lambda: datetime(2026, 8, 9, tzinfo=timezone.utc))
    service.build_focus(evidences=[_ev("Z", "alert_triggered", "z")])
    assert calls == []
    service.build_focus(evidences=[_ev("Z", "alert_triggered", "z")], llm_call=lambda t: calls.append(t) or t)
    assert calls
