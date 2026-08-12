# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.services.event_triggered_analysis import (
    EventTriggerBudgetState,
    EventTriggeredAnalysisService,
    build_suggested_action,
    reset_event_trigger_budget_state_for_tests,
)


def _config(**overrides):
    base = dict(
        event_triggered_analysis_enabled=False,
        event_trigger_cooldown_minutes=180,
        event_trigger_default_pipeline="standard",
        event_trigger_max_per_hour=5,
        event_trigger_max_per_day=20,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestEventTriggeredAnalysisGates:
    def setup_method(self) -> None:
        reset_event_trigger_budget_state_for_tests()

    def test_default_disabled(self) -> None:
        service = EventTriggeredAnalysisService(state=EventTriggerBudgetState())
        decision = service.maybe_submit(
            config=_config(),
            stock_code="600519",
            alert_type="corporate_event",
            notification_policy={"auto_analysis": True},
        )
        assert decision.status == "disabled"
        assert decision.submitted is False

    def test_requires_rule_opt_in(self) -> None:
        service = EventTriggeredAnalysisService(state=EventTriggerBudgetState())
        decision = service.maybe_submit(
            config=_config(event_triggered_analysis_enabled=True),
            stock_code="600519",
            alert_type="corporate_event",
            notification_policy={},
        )
        assert decision.status == "rule_opt_in_required"

    def test_submit_with_budget_and_debounce(self) -> None:
        submission = MagicMock()
        submission.submit.return_value = SimpleNamespace(
            accepted_tasks=(SimpleNamespace(task_id="t1"),),
            duplicate_errors=(),
        )
        now = {"t": 1_000_000.0}
        state = EventTriggerBudgetState()
        service = EventTriggeredAnalysisService(
            state=state,
            submission_service=submission,
            now_provider=lambda: now["t"],
            security_audit_factory=lambda: MagicMock(),
        )
        config = _config(
            event_triggered_analysis_enabled=True,
            event_trigger_cooldown_minutes=30,
            event_trigger_max_per_hour=1,
        )
        first = service.maybe_submit(
            config=config,
            stock_code="600519",
            alert_type="corporate_event",
            rule_id=9,
            notification_policy={"auto_analysis": True},
            trigger_reason="earnings",
        )
        assert first.status == "submitted"
        assert first.submitted is True
        assert first.task_ids == ("t1",)

        second = service.maybe_submit(
            config=config,
            stock_code="600519",
            alert_type="corporate_event",
            rule_id=9,
            notification_policy={"auto_analysis": True},
        )
        assert second.status == "debounced"

        # Stay inside the hourly window so the first submission still counts.
        now["t"] += 31 * 60
        third = service.maybe_submit(
            config=config,
            stock_code="000001",
            alert_type="volume_spike",
            rule_id=10,
            notification_policy={"auto_analysis": True},
        )
        assert third.status == "budget_exceeded"


class TestSuggestedAction:
    def test_corporate_event_links_and_relevance(self) -> None:
        action = build_suggested_action(
            stock_code="600519",
            alert_type="corporate_event",
            impact_context={"affected": {"in_portfolio": True, "in_watchlist": True}},
            event_context={"source_url": "https://example.com/a"},
            auto_analysis={"status": "disabled", "submitted": False},
            report_language="en",
        )
        assert action["action_code"] == "review_thesis"
        assert action["deep_links"]["stock_detail"].endswith("/stocks/600519")
        assert "portfolio" in action["relevance"]
        assert action["auto_analysis"]["status"] == "disabled"
