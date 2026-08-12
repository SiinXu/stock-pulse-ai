# -*- coding: utf-8 -*-
"""Tests for high-disagreement alert emission (#134)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from src.services.high_disagreement_alert import (
    build_high_disagreement_alert_text,
    build_history_entry_href,
    extract_disagreement_handling_record,
    maybe_send_high_disagreement_alert,
    should_emit_high_disagreement_alert,
)


def _sample_record(
    *,
    score: float = 0.72,
    high_disagreement: bool = True,
    enabled: bool = True,
) -> Dict[str, Any]:
    return {
        "enabled": enabled,
        "high_disagreement": high_disagreement,
        "verdict_mode": "split",
        "escalation": "escalate_split",
        "resolution_status": "unresolved",
        "disagreement_score": score,
        "points": [
            {
                "source": "strategy",
                "kind": "directional_opposition",
                "severity": "high",
                "participants": ["momentum", "value"],
            },
            {
                "source": "role",
                "kind": "mixed_directional_signals",
                "severity": "medium",
                "participants": ["technical", "risk"],
            },
        ],
        "policy": {
            "method": "threshold_escalation",
            "majority_vote_used": False,
            "applied_final_signal": "hold",
        },
    }


class ExtractRecordTests(unittest.TestCase):
    def test_extracts_from_dashboard_disagreement_handling(self) -> None:
        record = _sample_record()
        result = SimpleNamespace(dashboard={"disagreement_handling": record})
        extracted = extract_disagreement_handling_record(result)
        self.assertIsNotNone(extracted)
        assert extracted is not None
        self.assertEqual(extracted["disagreement_score"], 0.72)
        self.assertTrue(extracted["high_disagreement"])

    def test_extracts_from_strategy_synthesis_nested_record(self) -> None:
        record = _sample_record(score=0.81)
        result = SimpleNamespace(
            dashboard={
                "strategy_synthesis": {
                    "final_signal": "hold",
                    "disagreement_handling": record,
                }
            }
        )
        extracted = extract_disagreement_handling_record(result)
        self.assertIsNotNone(extracted)
        assert extracted is not None
        self.assertEqual(extracted["disagreement_score"], 0.81)

    def test_does_not_invent_record_from_conflict_severity_alone(self) -> None:
        result = SimpleNamespace(
            dashboard={
                "strategy_synthesis": {
                    "conflict_severity": "high",
                    "conflicts": [{"conflict_type": "directional_opposition"}],
                }
            }
        )
        self.assertIsNone(extract_disagreement_handling_record(result))

    def test_disabled_record_is_ignored(self) -> None:
        result = SimpleNamespace(
            dashboard={"disagreement_handling": _sample_record(enabled=False)}
        )
        self.assertIsNone(extract_disagreement_handling_record(result))


class ThresholdPolicyTests(unittest.TestCase):
    def test_score_at_or_above_threshold_triggers(self) -> None:
        record = _sample_record(score=0.6, high_disagreement=False)
        self.assertTrue(should_emit_high_disagreement_alert(record, threshold=0.6))
        self.assertFalse(should_emit_high_disagreement_alert(record, threshold=0.61))

    def test_score_below_threshold_not_bypassed_by_high_flag(self) -> None:
        """Raising the threshold must suppress low-score records even if flagged high."""
        record = _sample_record(score=0.4, high_disagreement=True)
        self.assertFalse(should_emit_high_disagreement_alert(record, threshold=0.6))

    def test_high_flag_used_only_when_score_absent(self) -> None:
        record = {
            "enabled": True,
            "high_disagreement": True,
            "points": [],
        }
        self.assertTrue(should_emit_high_disagreement_alert(record, threshold=0.6))
        record_low = {
            "enabled": True,
            "high_disagreement": False,
            "points": [],
        }
        self.assertFalse(should_emit_high_disagreement_alert(record_low, threshold=0.6))

    def test_missing_record_does_not_trigger(self) -> None:
        self.assertFalse(should_emit_high_disagreement_alert(None, threshold=0.6))


class AlertContentTests(unittest.TestCase):
    def test_content_includes_points_and_entry_link(self) -> None:
        text = build_high_disagreement_alert_text(
            stock_code="600519",
            stock_name="贵州茅台",
            record=_sample_record(),
            history_id=42,
            report_language="en",
        )
        self.assertIn("High Disagreement Alert", text)
        self.assertIn("600519", text)
        self.assertIn("directional_opposition", text)
        self.assertIn("momentum", text)
        self.assertIn("/research/analysis?segment=history&recordId=42", text)

    def test_zh_labels_when_report_language_zh(self) -> None:
        text = build_high_disagreement_alert_text(
            stock_code="600519",
            stock_name="贵州茅台",
            record=_sample_record(),
            history_id=1,
            report_language="zh",
        )
        self.assertIn("高分歧告警", text)
        self.assertIn("分歧要点", text)

    def test_history_href_rejects_invalid_ids(self) -> None:
        self.assertIsNone(build_history_entry_href(None))
        self.assertIsNone(build_history_entry_href(0))
        self.assertIsNone(build_history_entry_href(-1))
        self.assertEqual(
            build_history_entry_href(7),
            "/research/analysis?segment=history&recordId=7",
        )

    def test_history_href_absolute_when_webui_host_usable(self) -> None:
        config = SimpleNamespace(webui_host="127.0.0.1", webui_port=8000)
        self.assertEqual(
            build_history_entry_href(7, config=config),
            "http://127.0.0.1:8000/research/analysis?segment=history&recordId=7",
        )
        bind_all = SimpleNamespace(webui_host="0.0.0.0", webui_port=8000)
        self.assertEqual(
            build_history_entry_href(7, config=bind_all),
            "/research/analysis?segment=history&recordId=7",
        )


class EmitAlertTests(unittest.TestCase):
    def _result(self, record: Optional[Dict[str, Any]] = None) -> SimpleNamespace:
        dashboard: Dict[str, Any] = {}
        if record is not None:
            dashboard["disagreement_handling"] = record
        return SimpleNamespace(
            code="AAPL",
            name="Apple",
            report_language="en",
            query_id="q-test-1",
            dashboard=dashboard,
        )

    def test_sends_via_alert_route_when_threshold_exceeded(self) -> None:
        calls: List[Dict[str, Any]] = []

        class _Notifier:
            def send_with_results(self, content: str, **kwargs: Any) -> Any:
                calls.append({"content": content, **kwargs})
                return SimpleNamespace(success=True, status="sent", dispatched=True)

        config = SimpleNamespace(
            high_disagreement_alerts_enabled=True,
            high_disagreement_threshold=0.6,
            report_language="en",
        )
        ok = maybe_send_high_disagreement_alert(
            self._result(_sample_record(score=0.8)),
            history_id=99,
            config=config,
            notifier=_Notifier(),
        )
        self.assertTrue(ok)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["route_type"], "alert")
        self.assertEqual(calls[0]["severity"], "warning")
        self.assertIn("recordId=99", calls[0]["content"])
        self.assertIn("directional_opposition", calls[0]["content"])

    def test_skips_when_alerts_disabled(self) -> None:
        notifier = MagicMock()
        config = SimpleNamespace(
            high_disagreement_alerts_enabled=False,
            high_disagreement_threshold=0.6,
        )
        ok = maybe_send_high_disagreement_alert(
            self._result(_sample_record()),
            history_id=1,
            config=config,
            notifier=notifier,
        )
        self.assertFalse(ok)
        notifier.send_with_results.assert_not_called()
        notifier.send.assert_not_called()

    def test_skips_when_no_disagreement_record(self) -> None:
        notifier = MagicMock()
        config = SimpleNamespace(
            high_disagreement_alerts_enabled=True,
            high_disagreement_threshold=0.6,
        )
        ok = maybe_send_high_disagreement_alert(
            self._result(None),
            history_id=1,
            config=config,
            notifier=notifier,
        )
        self.assertFalse(ok)
        notifier.send_with_results.assert_not_called()

    def test_channel_failure_does_not_raise(self) -> None:
        class _BoomNotifier:
            def send_with_results(self, content: str, **kwargs: Any) -> Any:
                raise RuntimeError("channel down")

        config = SimpleNamespace(
            high_disagreement_alerts_enabled=True,
            high_disagreement_threshold=0.6,
            report_language="en",
        )
        ok = maybe_send_high_disagreement_alert(
            self._result(_sample_record()),
            history_id=5,
            config=config,
            notifier=_BoomNotifier(),
        )
        self.assertFalse(ok)

    def test_score_below_threshold_without_high_flag_skips(self) -> None:
        notifier = MagicMock()
        config = SimpleNamespace(
            high_disagreement_alerts_enabled=True,
            high_disagreement_threshold=0.6,
        )
        ok = maybe_send_high_disagreement_alert(
            self._result(_sample_record(score=0.4, high_disagreement=False)),
            history_id=1,
            config=config,
            notifier=notifier,
        )
        self.assertFalse(ok)
        notifier.send_with_results.assert_not_called()

    def test_score_below_threshold_with_high_flag_skips(self) -> None:
        """Counterexample from PR review: threshold must remain effective."""
        notifier = MagicMock()
        config = SimpleNamespace(
            high_disagreement_alerts_enabled=True,
            high_disagreement_threshold=0.6,
        )
        ok = maybe_send_high_disagreement_alert(
            self._result(_sample_record(score=0.4, high_disagreement=True)),
            history_id=1,
            config=config,
            notifier=notifier,
        )
        self.assertFalse(ok)
        notifier.send_with_results.assert_not_called()

    def test_skips_when_outbound_notifications_disabled(self) -> None:
        """Counterexample: --no-notify / send_notification=false must not push."""
        notifier = MagicMock()
        config = SimpleNamespace(
            high_disagreement_alerts_enabled=True,
            high_disagreement_threshold=0.6,
        )
        ok = maybe_send_high_disagreement_alert(
            self._result(_sample_record(score=0.9)),
            history_id=1,
            config=config,
            notifier=notifier,
            outbound_notifications_enabled=False,
        )
        self.assertFalse(ok)
        notifier.send_with_results.assert_not_called()
        notifier.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
