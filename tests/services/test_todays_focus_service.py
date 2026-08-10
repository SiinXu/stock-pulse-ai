# -*- coding: utf-8 -*-
"""Contract and counterexample tests for Today's Focus (Issue #157 / T26)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from api.v1.schemas.todays_focus import TodaysFocusResponse
from src.services.todays_focus_service import (
    DEFAULT_MAX_FOCUS_ITEMS,
    FocusEvidence,
    TodaysFocusService,
    format_reason_display,
    select_focus_items,
)

NOW = datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)


def _evidence_payload(reason: str, observed_at: datetime = NOW) -> Dict[str, Any]:
    common = {"observed_at": observed_at.isoformat()}
    if reason == "alert_triggered":
        return {
            **common,
            "type": "alert",
            "trigger_id": 1,
            "rule_id": 9,
            "status": "triggered",
        }
    if reason == "analysis_reversal":
        return {
            **common,
            "type": "analysis",
            "record_id": 2,
            "query_id": "q-2",
            "previous_observed_at": (observed_at - timedelta(days=1)).isoformat(),
            "previous_action": "buy",
            "latest_action": "sell",
        }
    if reason == "corporate_event":
        return {
            **common,
            "type": "corporate_event",
            "event_id": "event-1",
            "href": "/events/event-1",
        }
    raise AssertionError(f"unsupported test reason: {reason}")


def _ev(
    code: str,
    reason: str,
    detail: str = "x",
    *,
    observed_at: datetime = NOW,
    weight: float | None = None,
    priority: int | None = None,
) -> FocusEvidence:
    kwargs: Dict[str, Any] = {
        "code": code,
        "reason_code": reason,
        "detail": detail,
        "evidence": _evidence_payload(reason, observed_at),
        "weight_pct": weight,
    }
    if priority is not None:
        kwargs["priority"] = priority
    return FocusEvidence(**kwargs)


class EmptyAlertRepository:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def list_recent_triggered_for_targets(self, **kwargs: Any) -> List[Any]:
        self.calls.append(kwargs)
        return []


class EmptyPortfolioRepository:
    def __init__(self, rows: List[Dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.calls = 0

    def list_cached_positions(self, **_kwargs: Any) -> List[Dict[str, Any]]:
        self.calls += 1
        return self.rows


def _service(
    *,
    alerts: Any | None = None,
    portfolio: Any | None = None,
    history: Any | None = None,
    stock_list: List[str] | None = None,
) -> TodaysFocusService:
    return TodaysFocusService(
        config_provider=lambda: SimpleNamespace(
            stock_list=stock_list or [],
            report_language="en",
            daily_brief_timezone="Asia/Shanghai",
        ),
        alert_repository=alerts or EmptyAlertRepository(),
        portfolio_repository=portfolio or EmptyPortfolioRepository(),
        signal_changes_batch_loader=history or (lambda _codes, **_kwargs: {}),
        clock=lambda: NOW,
    )


def test_empty_evidences_never_padded() -> None:
    assert select_focus_items([], max_items=5) == []


def test_hard_cap_and_priority_are_stable_without_lifetime_pnl_reason() -> None:
    evidences = [
        _ev("A", "alert_triggered", "a"),
        _ev("B", "alert_triggered", "b"),
        _ev("C", "corporate_event", "c"),
        _ev("D", "analysis_reversal", "d"),
        _ev("E", "corporate_event", "e"),
        _ev("F", "analysis_reversal", "f"),
    ]
    items = select_focus_items(evidences, max_items=5)
    assert len(items) == 5
    assert "F" not in {item.code for item in items}
    assert items[0].reason_code == "alert_triggered"
    with pytest.raises(ValueError, match="unsupported reason_code"):
        FocusEvidence(
            code="G",
            reason_code="high_weight_move",
            detail="lifetime P&L",
            evidence=_evidence_payload("alert_triggered"),
        )


def test_same_symbol_merges_only_typed_secondary_reasons() -> None:
    items = select_focus_items(
        [
            _ev("AAPL", "corporate_event", "earnings"),
            _ev("AAPL", "alert_triggered", "price break"),
            _ev("AAPL", "analysis_reversal", "buy to sell"),
        ],
        max_items=5,
    )
    assert len(items) == 1
    assert items[0].reason_code == "alert_triggered"
    assert set(items[0].secondary_reason_codes) == {
        "corporate_event",
        "analysis_reversal",
    }


def test_llm_polish_cannot_change_selection_or_evidence() -> None:
    evidences = [
        _ev("AAA", "alert_triggered", "a"),
        _ev("BBB", "corporate_event", "b"),
    ]
    selected = select_focus_items(evidences, max_items=5)
    polished = select_focus_items(
        evidences,
        max_items=5,
        llm_call=lambda text: f"POLISHED:{text}",
    )
    assert [(item.code, item.reason_code, item.evidence) for item in polished] == [
        (item.code, item.reason_code, item.evidence) for item in selected
    ]
    assert all(item.reason_display.startswith("POLISHED:") for item in polished)


def test_format_reason_display_language() -> None:
    en = format_reason_display("alert_triggered", "breakout", language="en")
    zh = format_reason_display("alert_triggered", "breakout", language="zh")
    assert "breakout" in en and "breakout" in zh
    assert "告警" in zh


def test_service_empty_status_uses_executable_today_and_read_only_contract() -> None:
    payload = _service().build_focus(max_items=5)
    assert payload["status"] == "empty"
    assert payload["items"] == []
    assert payload["empty_reason"] == "no_fresh_deterministic_signals"
    assert payload["temporal_policy"] == {
        "semantics": "local_calendar_day",
        "timezone": "Asia/Shanghai",
        "local_date": "2026-08-09",
        "window_start": "2026-08-08T16:00:00+00:00",
        "window_end": "2026-08-09T08:00:00+00:00",
        "naive_timestamp_policy": "assume_utc",
        "missing_timestamp_policy": "exclude",
        "non_trading_day_policy": "same_local_day_only",
    }
    assert payload["cost_contract"]["database_writes"] == 0
    assert payload["cost_contract"]["provider_calls"] == 0
    assert payload["cost_contract"]["read_only"] is True
    assert payload["max_items"] == DEFAULT_MAX_FOCUS_ITEMS
    TodaysFocusResponse.model_validate(payload)


def test_stale_and_failed_alerts_are_excluded_and_query_is_targeted() -> None:
    class AlertRepository:
        def __init__(self) -> None:
            self.calls: List[Dict[str, Any]] = []

        def list_recent_triggered_for_targets(self, **kwargs: Any) -> List[Dict[str, Any]]:
            self.calls.append(kwargs)
            return [
                {
                    "id": 1,
                    "rule_id": 9,
                    "target": "AAPL",
                    "reason": "stale",
                    "triggered_at": "2026-08-08T15:59:59+00:00",
                    "status": "triggered",
                },
                {
                    "id": 2,
                    "rule_id": 9,
                    "target": "AAPL",
                    "reason": "failed",
                    "triggered_at": NOW,
                    "status": "failed",
                },
                {
                    "id": 3,
                    "rule_id": 9,
                    "target": "AAPL",
                    "reason": "fresh",
                    "triggered_at": NOW,
                    "status": "triggered",
                },
            ]

    alerts = AlertRepository()
    payload = _service(alerts=alerts, stock_list=["AAPL"]).build_focus()
    assert [item["evidence"]["trigger_id"] for item in payload["items"]] == [3]
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["per_target_limit"] == 1
    assert "AAPL" in alerts.calls[0]["targets"]
    assert alerts.calls[0]["triggered_since"] == datetime(
        2026, 8, 8, 16, 0, tzinfo=timezone.utc
    )


def test_more_than_fifty_unrelated_alerts_cannot_hide_target_trigger() -> None:
    class TargetedRepository:
        def list_recent_triggered_for_targets(self, **kwargs: Any) -> List[Dict[str, Any]]:
            assert len(kwargs["targets"]) <= 5
            return [
                {
                    "id": 77,
                    "rule_id": 5,
                    "target": "AAPL",
                    "reason": "targeted query result",
                    "triggered_at": NOW,
                    "status": "triggered",
                }
            ]

        def list_triggers(self, **_kwargs: Any) -> Any:
            raise AssertionError("the unfiltered first-page query must not be used")

    payload = _service(alerts=TargetedRepository(), stock_list=["AAPL"]).build_focus()
    assert payload["items"][0]["evidence"]["trigger_id"] == 77


def test_hk_aliases_join_alert_and_analysis_evidence() -> None:
    class Alerts:
        def list_recent_triggered_for_targets(self, **_kwargs: Any) -> List[Dict[str, Any]]:
            return [
                {
                    "id": 8,
                    "rule_id": 1,
                    "target": "00700.HK",
                    "reason": "fresh",
                    "triggered_at": NOW,
                    "status": "triggered",
                }
            ]

    def history(codes: List[str], **_kwargs: Any) -> Dict[str, List[Dict[str, Any]]]:
        assert codes == ["HK00700"]
        return {
            "HK00700": [
                {"record_id": 12, "created_at": NOW, "action": "sell"},
                {
                    "record_id": 11,
                    "created_at": NOW - timedelta(days=89),
                    "action": "buy",
                },
            ]
        }

    payload = _service(
        alerts=Alerts(),
        history=history,
        stock_list=["00700.HK"],
    ).build_focus()
    assert [item["code"] for item in payload["items"]] == ["HK00700"]
    assert payload["items"][0]["secondary_reason_codes"] == ["analysis_reversal"]


def test_analysis_latest_must_be_today_and_watch_to_avoid_is_not_a_reversal() -> None:
    def history(_codes: List[str], **_kwargs: Any) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "STALE": [
                {"record_id": 3, "created_at": NOW - timedelta(days=1), "action": "sell"},
                {"record_id": 2, "created_at": NOW - timedelta(days=2), "action": "buy"},
            ],
            "LABELS": [
                {"record_id": 5, "created_at": NOW, "action": "avoid"},
                {"record_id": 4, "created_at": NOW - timedelta(days=1), "action": "watch"},
            ],
        }

    payload = _service(history=history, stock_list=["STALE", "LABELS"]).build_focus()
    assert payload["items"] == []


def test_history_is_one_bounded_batch_call_and_type_error_is_not_retried() -> None:
    calls: List[Dict[str, Any]] = []

    def history(codes: List[str], **kwargs: Any) -> Any:
        calls.append({"codes": codes, **kwargs})
        raise TypeError("internal storage bug")

    payload = _service(history=history, stock_list=["AAPL", "MSFT"]).build_focus()
    assert len(calls) == 1
    assert calls[0]["limit"] == 2
    assert calls[0]["created_at_from"] == NOW - timedelta(days=90)
    assert payload["status"] == "degraded"
    assert payload["degraded_sources"] == ["analysis_history"]


def test_portfolio_cache_is_read_once_and_lifetime_pnl_never_qualifies() -> None:
    portfolio = EmptyPortfolioRepository(
        [{"symbol": "AAPL", "unrealized_pnl_pct": 900.0, "market_value": 50_000}]
    )
    payload = _service(portfolio=portfolio).build_focus()
    assert portfolio.calls == 1
    assert payload["universe_contract"]["symbol_count"] == 1
    assert payload["items"] == []
    assert all(
        item.get("reason_code") != "high_weight_move" for item in payload["items"]
    )


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_weight_is_rejected_before_json_serialization(invalid: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        _ev("AAPL", "alert_triggered", weight=invalid)

    valid = _service().build_focus(evidences=[_ev("AAPL", "alert_triggered")])
    valid["items"][0]["weight_pct"] = invalid
    with pytest.raises(ValidationError):
        TodaysFocusResponse.model_validate(valid)
