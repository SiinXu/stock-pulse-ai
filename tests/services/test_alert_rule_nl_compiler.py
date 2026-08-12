# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from src.services.alert_rule_nl_compiler import compile_alert_rule_nl


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

    def test_compile_price_cross(self) -> None:
        result = compile_alert_rule_nl("AAPL price above 200")
        assert result.outcome == "success"
        assert result.rule["alert_type"] == "price_cross"
        assert result.rule["parameters"]["direction"] == "above"
        assert result.rule["parameters"]["price"] == 200.0

    def test_compile_volume_spike(self) -> None:
        result = compile_alert_rule_nl("300750 成交量异动 2.5倍")
        assert result.outcome == "success"
        assert result.rule["alert_type"] == "volume_spike"
        assert result.rule["parameters"]["multiplier"] == 2.5

    def test_need_clarification_without_symbol(self) -> None:
        result = compile_alert_rule_nl("price above 100")
        assert result.outcome == "need_clarification"
        assert "stock_code" in result.clarifications

    def test_reject_code_like(self) -> None:
        result = compile_alert_rule_nl("import os; os.system('rm -rf /')")
        assert result.outcome == "rejected"
        assert result.rejected_reason == "code_like_input"

    @pytest.mark.parametrize("digits", ["9" * 400, "1" + "0" * 400])
    def test_reject_non_finite_numeric_parameters(self, digits: str) -> None:
        result = compile_alert_rule_nl(f"AAPL price above {digits}")

        assert result.outcome == "rejected"
        assert result.rejected_reason == "invalid_parameters"
        assert result.message == "numeric parameters must be finite"
