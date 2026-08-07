# -*- coding: utf-8 -*-
"""Deterministic tests for corporate event alerts and impact context."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services.event_alerts import (
    CorporateEventAlert,
    build_impact_context,
    classify_corporate_event_text,
    evaluate_corporate_event_alert,
    format_impact_context_excerpt,
    normalize_corporate_event_parameters,
)


def _item(
    *,
    title: str,
    summary: str = "",
    item_id: int = 1,
    hours_ago: float = 1.0,
) -> SimpleNamespace:
    stamp = datetime.now() - timedelta(hours=hours_ago)
    return SimpleNamespace(
        id=item_id,
        title=title,
        summary=summary,
        url="https://example.com/news/1?token=secret",
        source_name="unit-test",
        published_at=stamp,
        fetched_at=stamp,
    )


class TestNormalizeCorporateEventParameters:
    def test_defaults(self) -> None:
        params = normalize_corporate_event_parameters({})
        assert params["event_categories"] == [
            "earnings",
            "shareholder",
            "mna",
            "regulatory",
            "analyst",
        ]
        assert params["lookback_hours"] == 24
        assert params["min_items"] == 1

    def test_rejects_unknown_category(self) -> None:
        with pytest.raises(ValueError, match="event_categories only supports"):
            normalize_corporate_event_parameters({"event_categories": ["rumor"]})

    def test_lookback_bounds(self) -> None:
        with pytest.raises(ValueError, match="lookback_hours"):
            normalize_corporate_event_parameters({"lookback_hours": 0})
        with pytest.raises(ValueError, match="lookback_hours"):
            normalize_corporate_event_parameters({"lookback_hours": 999})


class TestClassifyAndEvaluate:
    def test_classify_earnings_bilingual(self) -> None:
        assert "earnings" in classify_corporate_event_text("公司发布2025年年报")
        assert "earnings" in classify_corporate_event_text("Q2 earnings beat estimates")

    def test_trigger_firing_on_matching_intelligence(self) -> None:
        rule = CorporateEventAlert(
            stock_code="600519",
            parameters={"event_categories": ["earnings"], "lookback_hours": 24, "min_items": 1},
            metadata={"persisted_rule_id": 11},
        )
        result = evaluate_corporate_event_alert(
            rule,
            items=[_item(title="贵州茅台发布年度业绩预告", summary="净利润增长")],
        )
        assert result["triggered"] is True
        assert result["record_status"] == "triggered"
        assert result["data_source"] == "intelligence_items"
        assert result["observed_value"] == 1.0
        assert result["threshold"] == 1.0
        event_context = result["diagnostics"]["event_context"]
        assert event_context["event_category"] == "earnings"
        assert "what_happened" in event_context
        assert "why_it_matters" in event_context
        assert "token=***" in (event_context.get("source_url") or "")

    def test_not_triggered_when_category_filtered_out(self) -> None:
        rule = CorporateEventAlert(
            stock_code="600519",
            parameters={"event_categories": ["regulatory"], "lookback_hours": 24},
            metadata={"persisted_rule_id": 12},
        )
        result = evaluate_corporate_event_alert(
            rule,
            items=[_item(title="分析师上调目标价", summary="rating upgrade")],
        )
        assert result["triggered"] is False
        assert result["status"] == "not_triggered"
        assert result["observed_value"] == 0.0

    def test_no_items_is_skipped(self) -> None:
        rule = CorporateEventAlert(
            stock_code="AAPL",
            parameters={},
            metadata={"persisted_rule_id": 13},
        )
        result = evaluate_corporate_event_alert(rule, items=[])
        assert result["triggered"] is False
        assert result["record_status"] == "skipped"
        assert result["data_source"] == "intelligence_items"

    def test_repo_failure_is_evaluation_error(self) -> None:
        rule = CorporateEventAlert(stock_code="AAPL", parameters={}, metadata={"persisted_rule_id": 14})
        repo = MagicMock()
        repo.list_items.side_effect = RuntimeError("db down")
        result = evaluate_corporate_event_alert(rule, intelligence_repo=repo)
        assert result["triggered"] is False
        assert result["status"] == "evaluation_error"
        assert result["record_status"] == "failed"


class TestImpactContext:
    def test_context_assembly_with_holdings_and_watchlist(self) -> None:
        config = SimpleNamespace(stock_list=["600519", "AAPL"], refresh_stock_list=lambda: None)
        portfolio = MagicMock()
        portfolio.get_portfolio_snapshot.return_value = {
            "accounts": [
                {
                    "id": 1,
                    "total_equity": 100000.0,
                    "positions": [
                        {
                            "symbol": "600519",
                            "quantity": 100,
                            "market_value_base": 15000.0,
                        }
                    ],
                }
            ]
        }
        context = build_impact_context(
            stock_code="600519",
            event_context={
                "what_happened": "年度业绩预告",
                "why_it_matters": "可能重定价盈利预期",
                "event_category": "earnings",
            },
            config=config,
            portfolio_service=portfolio,
            analysis_records=[SimpleNamespace(summary="持有观望，关注财报兑现")],
            report_language="zh",
        )
        assert context["what_happened"] == "年度业绩预告"
        assert context["affected"]["in_watchlist"] is True
        assert context["affected"]["in_portfolio"] is True
        assert context["affected"]["weight_pct"] == 15.0
        assert context["related_analysis"]
        assert context["degraded"] is False
        portfolio.get_portfolio_snapshot.assert_called_once()
        assert portfolio.get_portfolio_snapshot.call_args.kwargs["include_realtime"] is False

    def test_no_context_degradation(self) -> None:
        portfolio = MagicMock()
        portfolio.get_portfolio_snapshot.side_effect = RuntimeError("portfolio unavailable")
        context = build_impact_context(
            stock_code="AAPL",
            event_context=None,
            config=SimpleNamespace(stock_list=[]),
            portfolio_service=portfolio,
            analysis_records=[],
            report_language="en",
        )
        assert context["affected"]["in_portfolio"] is False
        assert context["degraded"] is True
        assert context["what_happened"] is None
        excerpt = format_impact_context_excerpt(context, report_language="en")
        assert "Impact context" in excerpt
        assert "partial context" in excerpt

    def test_format_excerpt_zh(self) -> None:
        excerpt = format_impact_context_excerpt(
            {
                "what_happened": "年报发布",
                "why_it_matters": "影响估值",
                "event_category": "earnings",
                "affected": {"in_portfolio": True, "in_watchlist": True, "weight_pct": 12.5},
                "related_analysis": "关注业绩兑现",
            },
            report_language="zh",
        )
        assert "影响上下文" in excerpt
        assert "发生了什么" in excerpt
        assert "持仓权重" in excerpt
