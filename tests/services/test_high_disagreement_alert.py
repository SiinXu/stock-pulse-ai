# -*- coding: utf-8 -*-
"""Tests for high-disagreement alert emission (#134)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from src.services.high_disagreement_alert import (
    DISAGREEMENT_HANDLING_SCHEMA_VERSION,
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
        "schema_version": DISAGREEMENT_HANDLING_SCHEMA_VERSION,
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

    def test_missing_enabled_marker_is_not_authoritative(self) -> None:
        record = _sample_record()
        record.pop("enabled")
        result = SimpleNamespace(dashboard={"disagreement_handling": record})
        self.assertIsNone(extract_disagreement_handling_record(result))

    def test_unversioned_or_unknown_contract_is_not_authoritative(self) -> None:
        record = _sample_record()
        record.pop("schema_version")
        result = SimpleNamespace(dashboard={"disagreement_handling": record})
        self.assertIsNone(extract_disagreement_handling_record(result))

        record["schema_version"] = "disagreement-handling-v2"
        self.assertIsNone(extract_disagreement_handling_record(result))

    def test_bounded_raw_result_walk_handles_nested_and_cyclic_mappings(self) -> None:
        record = _sample_record(score=0.84)
        nested = {"raw_result": {"dashboard": {"disagreement_handling": record}}}
        self.assertEqual(
            extract_disagreement_handling_record(nested)["disagreement_score"],
            0.84,
        )
        cyclic: Dict[str, Any] = {}
        cyclic["raw_result"] = cyclic
        self.assertIsNone(extract_disagreement_handling_record(cyclic))


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
            "schema_version": DISAGREEMENT_HANDLING_SCHEMA_VERSION,
            "enabled": True,
            "high_disagreement": True,
            "points": [],
        }
        self.assertTrue(should_emit_high_disagreement_alert(record, threshold=0.6))
        record_low = {
            "schema_version": DISAGREEMENT_HANDLING_SCHEMA_VERSION,
            "enabled": True,
            "high_disagreement": False,
            "points": [],
        }
        self.assertFalse(should_emit_high_disagreement_alert(record_low, threshold=0.6))

    def test_missing_record_does_not_trigger(self) -> None:
        self.assertFalse(should_emit_high_disagreement_alert(None, threshold=0.6))

    def test_unknown_contract_version_does_not_trigger(self) -> None:
        record = _sample_record()
        record["schema_version"] = "disagreement-handling-v2"
        self.assertFalse(should_emit_high_disagreement_alert(record, threshold=0.6))

    def test_non_finite_values_use_deterministic_policy(self) -> None:
        record = _sample_record(score=0.59, high_disagreement=False)
        self.assertFalse(should_emit_high_disagreement_alert(record, threshold=float("nan")))
        self.assertFalse(should_emit_high_disagreement_alert(record, threshold=float("inf")))
        record["disagreement_score"] = float("inf")
        record["high_disagreement"] = "true"
        self.assertFalse(should_emit_high_disagreement_alert(record, threshold=0.6))


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

    def test_history_href_rejects_unsafe_origins_and_invalid_ports(self) -> None:
        for host, port in (
            ("evil.example/path", 8000),
            ("user@example.com", 8000),
            ("good.example\n.evil", 8000),
            ("localhost", 70000),
            ("localhost", True),
        ):
            config = SimpleNamespace(webui_host=host, webui_port=port)
            self.assertEqual(
                build_history_entry_href(7, config=config),
                "/research/analysis?segment=history&recordId=7",
            )
        ipv6 = SimpleNamespace(webui_host="::1", webui_port=8000)
        self.assertEqual(
            build_history_entry_href(7, config=ipv6),
            "http://[::1]:8000/research/analysis?segment=history&recordId=7",
        )

    def test_alert_text_bounds_untrusted_record_fields(self) -> None:
        record = _sample_record()
        record["verdict_mode"] = "v" * 10_000
        record["points"] = [
            {
                "source": "s" * 10_000,
                "kind": "k" * 10_000,
                "severity": "x" * 10_000,
                "participants": ["p" * 10_000] * 100,
            }
        ] * 100
        text = build_high_disagreement_alert_text(
            stock_code="A" * 10_000,
            stock_name="N" * 10_000,
            record=record,
            report_language="en",
        )
        self.assertLess(len(text), 12_000)
        self.assertNotIn("A" * 33, text)
        self.assertNotIn("N" * 129, text)


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
        from src.notification import NotificationDispatchResult

        calls: List[Dict[str, Any]] = []

        class _Notifier:
            def send_with_results(self, content: str, **kwargs: Any) -> Any:
                calls.append({"content": content, **kwargs})
                return NotificationDispatchResult(
                    dispatched=True,
                    success=True,
                    status="sent",
                )

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

    def test_duck_typed_sent_success_is_not_treated_as_alert_success(self) -> None:
        class _Notifier:
            def send_with_results(self, content: str, **kwargs: Any) -> Any:
                return SimpleNamespace(status="sent", success=True, dispatched=True)

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
        self.assertFalse(ok)

    def test_mixed_channel_results_stay_success_with_partial_signal(self) -> None:
        from src.notification import ChannelAttemptResult, NotificationDispatchResult

        class _Notifier:
            def send_with_results(self, content: str, **kwargs: Any) -> Any:
                return NotificationDispatchResult(
                    dispatched=True,
                    success=True,
                    status="partial_failed",
                    channel_results=[
                        ChannelAttemptResult(
                            channel="wechat",
                            success=False,
                            error_code="exception",
                        ),
                        ChannelAttemptResult(channel="custom", success=True),
                    ],
                )

        config = SimpleNamespace(
            high_disagreement_alerts_enabled=True,
            high_disagreement_threshold=0.6,
            report_language="en",
        )
        with self.assertLogs("src.services.high_disagreement_alert", level="WARNING") as captured:
            ok = maybe_send_high_disagreement_alert(
                self._result(_sample_record(score=0.8)),
                history_id=99,
                config=config,
                notifier=_Notifier(),
            )
        self.assertTrue(ok)
        self.assertTrue(
            any("partial_failed" in line and "wechat" in line for line in captured.output)
        )

    def test_real_composed_config_properties_are_consumed(self) -> None:
        from src.config import Config

        from src.notification import NotificationDispatchResult

        notifier = MagicMock(spec_set=["send_with_results", "send"])
        notifier.send_with_results.return_value = NotificationDispatchResult(
            dispatched=True,
            success=True,
            status="sent",
        )
        config = Config(
            high_disagreement_alerts_enabled=True,
            high_disagreement_threshold=0.6,
        )
        self.assertTrue(
            maybe_send_high_disagreement_alert(
                self._result(_sample_record(score=0.8)),
                history_id=12,
                config=config,
                notifier=notifier,
            )
        )
        notifier.send_with_results.assert_called_once()

    def test_skips_when_alerts_disabled(self) -> None:
        notifier = MagicMock(spec_set=["send_with_results", "send"])
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

    def test_non_boolean_config_and_delivery_values_fail_closed(self) -> None:
        notifier = MagicMock(spec_set=["send_with_results", "send"])
        config = SimpleNamespace(
            high_disagreement_alerts_enabled="true",
            high_disagreement_threshold=0.6,
        )
        self.assertFalse(
            maybe_send_high_disagreement_alert(
                self._result(_sample_record()),
                history_id=1,
                config=config,
                notifier=notifier,
            )
        )
        config.high_disagreement_alerts_enabled = True
        self.assertFalse(
            maybe_send_high_disagreement_alert(
                self._result(_sample_record()),
                history_id=1,
                config=config,
                notifier=notifier,
                outbound_notifications_enabled=1,
            )
        )
        notifier.send_with_results.assert_not_called()

    def test_skips_when_no_disagreement_record(self) -> None:
        notifier = MagicMock(spec_set=["send_with_results", "send"])
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

    def test_skips_when_injected_config_is_missing(self) -> None:
        notifier = MagicMock(spec_set=["send_with_results", "send"])
        ok = maybe_send_high_disagreement_alert(
            self._result(_sample_record()),
            history_id=1,
            config=None,
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
        notifier = MagicMock(spec_set=["send_with_results", "send"])
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
        notifier = MagicMock(spec_set=["send_with_results", "send"])
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
        notifier = MagicMock(spec_set=["send_with_results", "send"])
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
