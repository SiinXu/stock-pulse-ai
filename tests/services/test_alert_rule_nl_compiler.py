# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from src.services.alert_rule_nl_compiler import (
    _MAX_COOLDOWN_SECONDS,
    compile_alert_rule_nl,
)
from src.services.alert_worker import MAX_DB_ALERT_COOLDOWN_SECONDS


class TestAlertRuleNlCompiler:
    def test_compile_corporate_event_preserves_categories(self) -> None:
        result = compile_alert_rule_nl("600519 财报公告触发深度分析", auto_analysis=True)
        assert result.outcome == "success"
        assert result.rule is not None
        assert result.rule["alert_type"] == "corporate_event"
        params = result.rule["parameters"]
        assert "event_categories" in params
        assert params["event_categories"]
        assert "lookback_hours" in params
        assert "min_items" in params
        assert result.rule["notification_policy"]["auto_analysis"] is True
        assert result.ir == {
            "symbol": "600519",
            "metric": "corporate_event",
            "comparator": "any",
            "threshold": 1,
            "cooldown": None,
        }

    def test_compile_price_cross(self) -> None:
        result = compile_alert_rule_nl("AAPL price above 200")
        assert result.outcome == "success"
        assert result.rule["alert_type"] == "price_cross"
        assert result.rule["parameters"]["direction"] == "above"
        assert result.rule["parameters"]["price"] == 200.0
        assert result.ir == {
            "symbol": "AAPL",
            "metric": "price_cross",
            "comparator": "above",
            "threshold": 200.0,
            "cooldown": None,
        }
        assert "cooldown_policy" not in result.rule

    def test_compile_volume_spike(self) -> None:
        result = compile_alert_rule_nl("300750 成交量异动 2.5倍")
        assert result.outcome == "success"
        assert result.rule["alert_type"] == "volume_spike"
        assert result.rule["parameters"]["multiplier"] == 2.5
        assert result.ir["comparator"] == "gte"
        assert result.ir["threshold"] == 2.5

    def test_compile_price_cross_with_cooldown_clause(self) -> None:
        result = compile_alert_rule_nl("AAPL price above 200 cooldown 30 minutes")
        assert result.outcome == "success"
        assert result.rule["parameters"]["price"] == 200.0
        assert result.rule["cooldown_policy"] == {"cooldown_seconds": 1800}
        assert result.ir["symbol"] == "AAPL"
        assert result.ir["metric"] == "price_cross"
        assert result.ir["comparator"] == "above"
        assert result.ir["threshold"] == 200.0
        assert result.ir["cooldown"] == 1800

    def test_compile_chinese_cooldown_is_stripped_from_threshold(self) -> None:
        result = compile_alert_rule_nl("600519 股价高于 1800 冷却 1 小时")
        assert result.outcome == "success"
        assert result.rule["parameters"]["price"] == 1800.0
        assert result.rule["cooldown_policy"] == {"cooldown_seconds": 3600}
        assert result.ir["cooldown"] == 3600

    def test_need_clarification_without_symbol(self) -> None:
        result = compile_alert_rule_nl("price above 100")
        assert result.outcome == "need_clarification"
        assert "stock_code" in result.clarifications

    def test_need_clarification_for_ambiguous_cooldown(self) -> None:
        result = compile_alert_rule_nl("AAPL price above 200 cooldown")
        assert result.outcome == "need_clarification"
        assert "cooldown_duration" in result.clarifications

    def test_reject_code_like(self) -> None:
        result = compile_alert_rule_nl("import os; os.system('rm -rf /')")
        assert result.outcome == "rejected"
        assert result.rejected_reason == "code_like_input"

    @pytest.mark.parametrize(
        "phrase",
        [
            "import os; os.system('rm -rf /')",
            "AAPL price above 200; eval('os.system(1)')",
            "exec('print(1)') AAPL price above 200",
            "AAPL price above 200 __import__('os')",
        ],
    )
    def test_malicious_expression_is_rejected_without_executing(self, phrase: str, monkeypatch) -> None:
        called: list[str] = []

        def _boom(name: str):
            def _inner(*_args, **_kwargs):
                called.append(name)
                raise AssertionError(f"{name} must not run")

            return _inner

        monkeypatch.setattr("builtins.eval", _boom("eval"))
        monkeypatch.setattr("builtins.exec", _boom("exec"))
        result = compile_alert_rule_nl(phrase)
        assert result.outcome == "rejected"
        assert result.rejected_reason == "code_like_input"
        assert result.rule is None
        assert called == []

    def test_reject_unmonitorable_phrase(self) -> None:
        result = compile_alert_rule_nl("AAPL make me rich tomorrow")
        assert result.outcome == "rejected"
        assert result.rejected_reason == "unsupported_metric"
        assert "supported monitor metric" in result.message.lower()

    def test_reject_cooldown_above_worker_maximum(self) -> None:
        assert _MAX_COOLDOWN_SECONDS == MAX_DB_ALERT_COOLDOWN_SECONDS
        result = compile_alert_rule_nl("AAPL price above 200 cooldown 366 days")
        assert result.outcome == "rejected"
        assert result.rejected_reason == "invalid_parameters"
        assert "365 days" in result.message

    @pytest.mark.parametrize("digits", ["9" * 400, "1" + "0" * 400])
    def test_reject_non_finite_numeric_parameters(self, digits: str) -> None:
        result = compile_alert_rule_nl(f"AAPL price above {digits}")

        assert result.outcome == "rejected"
        assert result.rejected_reason == "invalid_parameters"
        assert result.message == "numeric parameters must be finite"
