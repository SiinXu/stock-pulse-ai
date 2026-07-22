# -*- coding: utf-8 -*-
"""Report construction and service contracts for the analysis API."""

from tests.analysis_api_contract_support import (
    AnalysisService,
    MagicMock,
    ReportType,
    SimpleNamespace,
    TaskStatus,
    _analysis_context_pack_overview,
    _build_analysis_report,
    _handle_sync_analysis,
    _load_sync_fundamental_sources,
    _market_phase_summary,
    _market_structure_context,
    activate_test_environment,
    datetime,
    get_analysis_status,
    json,
    patch,
    restore_test_environment,
    unittest,
)


def setUpModule() -> None:
    activate_test_environment()


def tearDownModule() -> None:
    restore_test_environment()


class AnalysisApiContractTestCase(unittest.TestCase):
    def test_report_type_full_maps_to_full_pipeline_mode(self) -> None:
        service = object.__new__(AnalysisService)
        pipeline_instance = MagicMock()
        pipeline_instance.process_single_stock.return_value = object()

        with patch("src.config.get_config", return_value=SimpleNamespace()), \
             patch("src.core.pipeline.StockAnalysisPipeline", return_value=pipeline_instance), \
             patch.object(AnalysisService, "_build_analysis_response", return_value={"stock_code": "600519"}):
            result = AnalysisService.analyze_stock(service, "600519", report_type="full", query_id="q1")

        self.assertEqual(result, {"stock_code": "600519"})
        self.assertEqual(
            pipeline_instance.process_single_stock.call_args.kwargs["report_type"],
            ReportType.FULL,

        )

    def test_analysis_service_passes_request_skills_to_pipeline(self) -> None:
        service = object.__new__(AnalysisService)
        pipeline_instance = MagicMock()
        pipeline_instance.process_single_stock.return_value = object()
        request_skills = ["growth_quality"]

        with patch("src.config.get_config", return_value=SimpleNamespace()), \
             patch("src.core.pipeline.StockAnalysisPipeline", return_value=pipeline_instance) as pipeline_cls, \
             patch.object(AnalysisService, "_build_analysis_response", return_value={"stock_code": "600519"}):
            result = AnalysisService.analyze_stock(
                service,
                "600519",
                report_type="full",
                query_id="q1",
                skills=request_skills,
            )

        self.assertEqual(result, {"stock_code": "600519"})
        self.assertEqual(pipeline_cls.call_args.kwargs["analysis_skills"], request_skills)

    def test_analysis_service_passes_request_context_to_pipeline(self) -> None:
        from src.schemas.request_context import (
            AnalysisRequestContext,
            NotificationReplyTarget,
        )

        service = object.__new__(AnalysisService)
        pipeline_instance = MagicMock()
        pipeline_instance.process_single_stock.return_value = object()
        request_context = AnalysisRequestContext(
            requester_platform="feishu",
            requester_chat_id="chat-1",
            reply_targets=(NotificationReplyTarget("feishu", "chat-1"),),
        )

        with patch("src.config.get_config", return_value=SimpleNamespace()), \
             patch("src.core.pipeline.StockAnalysisPipeline", return_value=pipeline_instance) as pipeline_cls, \
             patch.object(AnalysisService, "_build_analysis_response", return_value={"stock_code": "600519"}):
            result = AnalysisService.analyze_stock(
                service,
                "600519",
                report_type="full",
                query_id="q1",
                request_context=request_context,
            )

        self.assertEqual(result, {"stock_code": "600519"})
        self.assertIs(pipeline_cls.call_args.kwargs["request_context"], request_context)

    def test_report_type_full_is_preserved_in_response_metadata(self) -> None:
        service = AnalysisService()
        pipeline_instance = MagicMock()
        pipeline_instance.process_single_stock.return_value = SimpleNamespace(
            code="600519",
            name="贵州茅台",
            current_price=1234.56,
            change_pct=1.23,
            model_used="test-model",
            analysis_summary="summary",
            operation_advice="hold",
            trend_prediction="up",
            sentiment_score=80,
            news_summary="news",
            technical_analysis="tech",
            fundamental_analysis="fundamental",
            risk_warning="risk",
            get_sniper_points=lambda: {},
        )

        with patch("src.config.get_config", return_value=SimpleNamespace()), \
             patch("src.core.pipeline.StockAnalysisPipeline", return_value=pipeline_instance):
            result = service.analyze_stock("600519", report_type="full", query_id="q1", send_notification=False)

        self.assertEqual(result["report"]["meta"]["report_type"], "full")

    def test_analysis_service_returns_none_and_records_last_error_for_unsuccessful_pipeline_result(self) -> None:
        service = AnalysisService()
        pipeline_instance = MagicMock()
        pipeline_instance.process_single_stock.return_value = SimpleNamespace(
            success=False,
            error_message="LLM stream interrupted",
        )

        with patch("src.config.get_config", return_value=SimpleNamespace()), \
             patch("src.core.pipeline.StockAnalysisPipeline", return_value=pipeline_instance):
            result = service.analyze_stock("600519", report_type="detailed", query_id="q1", send_notification=False)

        self.assertIsNone(result)
        self.assertEqual(service.last_error, "LLM stream interrupted")

    def test_handle_sync_analysis_uses_service_last_error_for_failed_pipeline_result(self) -> None:
        if _handle_sync_analysis is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        service_instance = MagicMock()
        service_instance.analyze_stock.return_value = None
        service_instance.last_error = "LLM stream interrupted"

        with patch("src.services.analysis_service.AnalysisService", return_value=service_instance):
            with self.assertRaises(Exception) as ctx:
                _handle_sync_analysis(
                    "600519",
                    SimpleNamespace(
                        report_type="detailed",
                        force_refresh=False,
                        notify=True,
                        analysis_phase="auto",
                    ),
                )

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(
            ctx.exception.detail,
            {
                "error": "analysis_failed",
                "message": "LLM stream interrupted",
                "params": {},
                "details": None,
                "detail": None,
                "trace_id": None,
            },
        )

    def test_handle_sync_analysis_response_exposes_overview(self) -> None:
        if _handle_sync_analysis is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        overview = _analysis_context_pack_overview()
        phase_summary = _market_phase_summary()
        service_instance = MagicMock()
        service_instance.analyze_stock.return_value = {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "report": {
                "meta": {"stock_code": "600519", "report_language": "zh"},
                "summary": {"analysis_summary": "summary"},
                "strategy": {},
                "details": {"news_summary": "news"},
            },
        }

        with patch("uuid.uuid4", return_value=SimpleNamespace(hex="q-sync-overview")), \
             patch("src.services.analysis_service.AnalysisService", return_value=service_instance), \
             patch(
                 "api.v1.endpoints.analysis._load_sync_fundamental_sources",
                 return_value=(
                     {
                         "enhanced_context": {"code": "600519"},
                         "analysis_context_pack_overview": overview,
                         "market_phase_summary": phase_summary,
                     },
                     None,
                     None,
                 ),
             ):
            result = _handle_sync_analysis(
                "600519",
                SimpleNamespace(
                    report_type="detailed",
                    force_refresh=False,
                    notify=True,
                    skills=None,
                    analysis_phase="intraday",
                ),
            )

        self.assertEqual(
            service_instance.analyze_stock.call_args.kwargs["analysis_phase"],
            "intraday",
        )
        details = result.report["details"]
        self.assertEqual(result.report["meta"]["market_phase_summary"]["phase"], "intraday")
        self.assertEqual(
            details["analysis_context_pack_overview"]["metadata"]["trigger_source"],
            "api",
        )
        self.assertEqual(
            details["analysis_context_pack_overview"]["data_quality"]["overall_score"],
            88,
        )
        self.assertNotIn("analysis_context_pack_overview", details["context_snapshot"])
        self.assertNotIn("market_phase_summary", details["context_snapshot"])

    def test_handle_sync_analysis_restores_market_structure_from_raw_result_snapshot(self) -> None:
        if _handle_sync_analysis is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        market_structure = _market_structure_context()
        service_instance = MagicMock()
        service_instance.analyze_stock.return_value = {
            "stock_code": "300024",
            "stock_name": "机器人",
            "report": {
                "meta": {"stock_code": "300024", "report_language": "zh"},
                "summary": {"analysis_summary": "summary"},
                "strategy": {},
                "details": {"news_summary": "news"},
            },
        }

        with patch("uuid.uuid4", return_value=SimpleNamespace(hex="q-sync-market-structure")), \
             patch("src.services.analysis_service.AnalysisService", return_value=service_instance), \
             patch(
                 "api.v1.endpoints.analysis._load_sync_fundamental_sources",
                 return_value=(
                     None,
                     None,
                     {
                         "model_used": "test-model",
                         "report_language": "zh",
                         "market_structure_context": market_structure,
                     },
                 ),
             ):
            result = _handle_sync_analysis(
                "300024",
                SimpleNamespace(
                    report_type="detailed",
                    force_refresh=False,
                    notify=True,
                    skills=None,
                    analysis_phase="intraday",
                ),
            )

        self.assertEqual(
            result.report["details"]["market_structure"]["market_theme_context"]["active_themes"][0]["name"],
            "机器人概念",
        )

    def test_handle_sync_analysis_carries_market_structure_from_service_without_fallback(self) -> None:
        if _handle_sync_analysis is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        market_structure = _market_structure_context()
        service = AnalysisService()
        service_result = service._build_analysis_response(
            SimpleNamespace(
                code="300024",
                name="机器人",
                current_price=999.9,
                change_pct=1.1,
                model_used="test-model",
                analysis_summary="summary",
                operation_advice="持有",
                trend_prediction="震荡",
                sentiment_score=80,
                news_summary="news",
                technical_analysis="tech",
                fundamental_analysis="fundamental",
                risk_warning="risk",
                market_structure_context=market_structure,
                to_dict=lambda: {
                    "analysis_summary": "summary",
                    "operation_advice": "持有",
                    "trend_prediction": "震荡",
                    "sentiment_score": 80,
                    "report_language": "zh",
                    "news_summary": "news",
                    "technical_analysis": "tech",
                    "fundamental_analysis": "fundamental",
                    "risk_warning": "risk",
                    "market_structure_context": market_structure,
                },
            ),
            "q-sync-no-history",
            report_type="detailed",
        )
        service_instance = MagicMock()
        service_instance.analyze_stock.return_value = service_result

        with patch("uuid.uuid4", return_value=SimpleNamespace(hex="q-sync-no-history")), \
             patch("src.services.analysis_service.AnalysisService", return_value=service_instance), \
             patch(
                 "api.v1.endpoints.analysis._load_sync_fundamental_sources",
                 return_value=(None, None, None),
             ):
            result = _handle_sync_analysis(
                "300024",
                SimpleNamespace(
                    report_type="detailed",
                    force_refresh=False,
                    notify=True,
                    skills=None,
                    analysis_phase="intraday",
                ),
            )

        self.assertIsNotNone(result)
        self.assertEqual(
            result.report["details"]["market_structure"]["market_theme_context"]["active_themes"][0]["name"],
            "机器人概念",
        )
        self.assertEqual(
            result.report["details"]["raw_result"]["market_structure_context"]["market_theme_context"]["active_themes"][0]["name"],
            "机器人概念",
        )
        self.assertNotIn(
            "raw_result",
            result.report["details"]["raw_result"],
        )

    def test_build_analysis_response_localizes_placeholder_stock_name_for_english(self) -> None:
        service = AnalysisService()
        result = service._build_analysis_response(
            SimpleNamespace(
                code="AAPL",
                name="股票AAPL",
                current_price=180.35,
                change_pct=1.04,
                model_used="test-model",
                analysis_summary="Momentum remains constructive.",
                operation_advice="Buy",
                trend_prediction="Bullish",
                sentiment_score=78,
                news_summary="news",
                technical_analysis="tech",
                fundamental_analysis="fundamental",
                risk_warning="risk",
                report_language="en",
                get_sniper_points=lambda: {},
            ),
            "q1",
            report_type="full",
        )

        self.assertEqual(result["stock_name"], "Unnamed Stock")
        self.assertEqual(result["report"]["meta"]["stock_name"], "Unnamed Stock")

    def test_build_analysis_response_does_not_use_model_news_summary_as_retrieval_evidence(self) -> None:
        service = AnalysisService()
        result = service._build_analysis_response(
            SimpleNamespace(
                code="600519",
                name="贵州茅台",
                current_price=1234.56,
                change_pct=1.23,
                model_used="test-model",
                analysis_summary="summary",
                operation_advice="hold",
                trend_prediction="up",
                sentiment_score=80,
                news_summary="model generated news summary",
                technical_analysis="tech",
                fundamental_analysis="fundamental",
                risk_warning="risk",
                get_sniper_points=lambda: {},
            ),
            "q1",
            report_type="full",
        )

        news_component = result["diagnostic_summary"]["components"]["news"]
        self.assertEqual(news_component["status"], "unknown")

    def test_build_analysis_response_includes_market_phase_summary_from_result_snapshot(self) -> None:
        service = AnalysisService()
        phase_summary = _market_phase_summary()

        result = service._build_analysis_response(
            SimpleNamespace(
                code="600519",
                name="贵州茅台",
                current_price=1234.56,
                change_pct=1.23,
                model_used="test-model",
                analysis_summary="summary",
                operation_advice="hold",
                trend_prediction="up",
                sentiment_score=80,
                news_summary="news",
                technical_analysis="tech",
                fundamental_analysis="fundamental",
                risk_warning="risk",
                diagnostic_context_snapshot={"market_phase_summary": phase_summary},
                get_sniper_points=lambda: {},
            ),
            "q1",
            report_type="full",
        )

        self.assertEqual(
            result["report"]["meta"]["market_phase_summary"]["phase"],
            "intraday",
        )

    def test_build_analysis_response_includes_market_structure_in_raw_result(self) -> None:
        service = AnalysisService()
        market_structure = _market_structure_context()

        def _raw_result() -> dict:
            return {
                "analysis_summary": "summary",
                "operation_advice": "持有",
                "trend_prediction": "震荡",
                "sentiment_score": 80,
                "report_language": "zh",
                "news_summary": "news",
                "technical_analysis": "tech",
                "fundamental_analysis": "fundamental",
                "risk_warning": "risk",
                "market_structure_context": market_structure,
            }

        result = service._build_analysis_response(
            SimpleNamespace(
                code="300024",
                name="机器人",
                current_price=999.9,
                change_pct=1.01,
                model_used="test-model",
                analysis_summary="summary",
                operation_advice="持有",
                trend_prediction="震荡",
                sentiment_score=80,
                news_summary="news",
                technical_analysis="tech",
                fundamental_analysis="fundamental",
                risk_warning="risk",
                market_structure_context=market_structure,
                to_dict=_raw_result,
            ),
            "q-build-response",
            report_type="detailed",
        )

        self.assertEqual(
            result["report"]["details"]["raw_result"]["market_structure_context"]["market_theme_context"]["active_themes"][0]["name"],
            "机器人概念",
        )

    def test_analysis_service_passes_analysis_phase_to_pipeline(self) -> None:
        service = AnalysisService()
        pipeline_instance = MagicMock()
        pipeline_instance.process_single_stock.return_value = SimpleNamespace(
            success=True,
            code="600519",
            name="贵州茅台",
            current_price=1234.56,
            change_pct=1.23,
            model_used="test-model",
            analysis_summary="summary",
            operation_advice="hold",
            trend_prediction="up",
            sentiment_score=80,
            news_summary="news",
            technical_analysis="tech",
            fundamental_analysis="fundamental",
            risk_warning="risk",
            get_sniper_points=lambda: {},
        )

        with patch("src.config.get_config", return_value=SimpleNamespace()), patch(
            "src.core.pipeline.StockAnalysisPipeline",
            return_value=pipeline_instance,
        ) as pipeline_cls:
            result = service.analyze_stock(
                "600519",
                report_type="detailed",
                send_notification=False,
                analysis_phase="postmarket",
            )

        self.assertIsNotNone(result)
        self.assertEqual(pipeline_cls.call_args.kwargs["analysis_phase"], "postmarket")

    def test_build_analysis_report_extracts_fundamental_fields_from_snapshot(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        report = _build_analysis_report(
            report_data={
                "meta": {},
                "summary": {},
                "strategy": {},
                "details": {"news_summary": "news"},
            },
            query_id="q1",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot={
                "enhanced_context": {
                    "fundamental_context": {
                        "earnings": {
                            "data": {
                                "financial_report": {"report_date": "2025-12-31", "revenue": 1000},
                                "dividend": {"ttm_dividend_yield_pct": 2.5},
                            }
                        }
                    }
                }
            },
            fallback_fundamental_payload=None,
        )

        self.assertEqual(report.details.financial_report["report_date"], "2025-12-31")
        self.assertEqual(report.details.dividend_metrics["ttm_dividend_yield_pct"], 2.5)

    def test_build_analysis_report_derives_decision_action_fields(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        report = _build_analysis_report(
            report_data={
                "meta": {"report_type": "detailed", "report_language": "zh"},
                "summary": {
                    "analysis_summary": "等待确认",
                    "operation_advice": "不建议买入",
                    "trend_prediction": "震荡",
                    "sentiment_score": 45,
                },
                "strategy": {},
                "details": {"decision_type": "buy"},
            },
            query_id="q1",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot=None,
            fallback_fundamental_payload=None,
        )

        self.assertEqual(report.summary.operation_advice, "不建议买入")
        self.assertEqual(report.summary.action, "avoid")
        self.assertEqual(report.summary.action_label, "回避")

    def test_build_analysis_report_aligns_score_and_legacy_advice(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        report = _build_analysis_report(
            report_data={
                "meta": {"report_type": "detailed", "report_language": "zh"},
                "summary": {
                    "analysis_summary": "等待确认",
                    "operation_advice": "持有",
                    "sentiment_score": 72,
                },
                "strategy": {},
                "details": {},
            },
            query_id="q2",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot=None,
            fallback_fundamental_payload=None,
        )

        self.assertEqual(report.summary.action, "buy")
        self.assertEqual(report.summary.action_label, "买入")

    def test_build_analysis_report_reads_decision_action_from_raw_result(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        report = _build_analysis_report(
            report_data={
                "meta": {"report_type": "detailed", "report_language": "zh"},
                "summary": {
                    "analysis_summary": "等待确认",
                    "operation_advice": "持有观察",
                    "action": "buy",
                    "trend_prediction": "震荡",
                    "sentiment_score": 45,
                },
                "strategy": {},
                "details": {
                    "action": "sell",
                    "raw_result": {
                        "operation_advice": "持有观察",
                        "action": "watch",
                        "report_language": "zh",
                    },
                },
            },
            query_id="q1",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot=None,
            fallback_fundamental_payload=None,
        )

        self.assertEqual(report.summary.action, "watch")
        self.assertEqual(report.summary.action_label, "观望")

    def test_build_analysis_report_stringifies_strategy_price_fields(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        report = _build_analysis_report(
            report_data={
                "meta": {},
                "summary": {},
                "strategy": {
                    "ideal_buy": 10.0,
                    "secondary_buy": None,
                    "stop_loss": 9.5,
                    "take_profit": 11.6,
                },
                "details": {},
            },
            query_id="q1",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot=None,
            fallback_fundamental_payload=None,
        )

        self.assertEqual(report.strategy.ideal_buy, "10.0")
        self.assertIsNone(report.strategy.secondary_buy)
        self.assertEqual(report.strategy.stop_loss, "9.5")
        self.assertEqual(report.strategy.take_profit, "11.6")

    def test_build_analysis_report_extracts_related_board_fields_from_snapshot(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        report = _build_analysis_report(
            report_data={
                "meta": {},
                "summary": {},
                "strategy": {},
                "details": {},
            },
            query_id="q1",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot={
                "enhanced_context": {
                    "fundamental_context": {
                        "belong_boards": [{"name": "白酒", "type": "行业"}],
                        "boards": {
                            "data": {
                                "top": [{"name": "白酒", "change_pct": 2.5}],
                                "bottom": [],
                            }
                        },
                    }
                }
            },
            fallback_fundamental_payload=None,
        )

        self.assertEqual(report.details.belong_boards, [{"name": "白酒", "type": "行业"}])
        self.assertEqual(report.details.sector_rankings["top"][0]["name"], "白酒")
        self.assertEqual(report.details.sector_rankings["top"][0]["change_pct"], 2.5)

    def test_build_analysis_report_exposes_overview_but_sanitizes_snapshot(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        overview = _analysis_context_pack_overview()
        phase_summary = _market_phase_summary()
        report = _build_analysis_report(
            report_data={
                "meta": {},
                "summary": {},
                "strategy": {},
                "details": {"news_summary": "news"},
            },
            query_id="q1",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot={
                "enhanced_context": {
                    "code": "600519",
                    "portfolio_context": {
                        "quantity": 100,
                        "avg_cost": 1800,
                        "unrealized_pnl_base": 5000,
                    },
                },
                "portfolio_context": {"total_cost": 180000},
                "analysis_context_pack_overview": overview,
                "market_phase_summary": {
                    **phase_summary,
                    "market_phase_context": {"raw": True},
                },
            },
            fallback_fundamental_payload=None,
        )

        self.assertIsNotNone(report.meta.market_phase_summary)
        self.assertEqual(report.meta.market_phase_summary.phase, "intraday")
        self.assertEqual(
            report.details.analysis_context_pack_overview.metadata.trigger_source,
            "api",
        )
        self.assertEqual(
            report.details.analysis_context_pack_overview.data_quality.overall_score,
            88,
        )
        self.assertEqual(
            report.details.analysis_context_pack_overview.blocks[1].missing_reasons,
            ["news_context_missing"],
        )
        self.assertNotIn(
            "analysis_context_pack_overview",
            report.details.context_snapshot,
        )
        self.assertNotIn(
            "market_phase_summary",
            report.details.context_snapshot,
        )
        self.assertNotIn(
            "portfolio_context",
            report.details.context_snapshot,
        )
        self.assertNotIn(
            "portfolio_context",
            report.details.context_snapshot["enhanced_context"],
        )
        self.assertNotIn("avg_cost", str(report.details.context_snapshot))

    def test_build_analysis_report_falls_back_to_sanitized_report_meta_phase_summary(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        phase_summary = {
            **_market_phase_summary(),
            "warnings": ["api_key=secret"],
            "market_phase_context": {"raw": True},
        }

        report = _build_analysis_report(
            report_data={
                "meta": {"market_phase_summary": phase_summary},
                "summary": {},
                "strategy": {},
                "details": {},
            },
            query_id="q-meta-phase",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot=None,
            fallback_fundamental_payload=None,
        )

        self.assertIsNotNone(report.meta.market_phase_summary)
        self.assertEqual(report.meta.market_phase_summary.phase, "intraday")
        self.assertEqual(report.meta.market_phase_summary.warnings, ["[REDACTED]"])

    def test_build_analysis_report_prefers_snapshot_phase_summary_over_report_meta(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        snapshot_summary = _market_phase_summary()
        report = _build_analysis_report(
            report_data={
                "meta": {
                    "market_phase_summary": {
                        **snapshot_summary,
                        "phase": "postmarket",
                    },
                },
                "summary": {},
                "strategy": {},
                "details": {},
            },
            query_id="q-snapshot-phase",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot={"market_phase_summary": snapshot_summary},
            fallback_fundamental_payload=None,
        )

        self.assertIsNotNone(report.meta.market_phase_summary)
        self.assertEqual(report.meta.market_phase_summary.phase, "intraday")

    def test_build_analysis_report_repairs_bare_kr_code_and_phase_summary(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        persisted_phase_summary = {
            **_market_phase_summary(),
            "phase": "postmarket",
            "market_local_time": "2025-01-02T16:10:00+09:00",
            "session_date": "2025-01-02",
            "effective_daily_bar_date": "2025-01-02",
            "is_market_open_now": False,
            "is_partial_bar": False,
            "minutes_to_open": 900,
            "minutes_to_close": None,
            "trigger_source": "scheduled_job",
            "analysis_intent": "postmarket",
            "warnings": ["legacy_snapshot"],
        }

        with patch("api.v1.endpoints.analysis.resolve_index_stock_code", return_value="005930.KS"):
            report = _build_analysis_report(
                report_data={
                    "meta": {"stock_code": "005930"},
                    "summary": {},
                    "strategy": {},
                    "details": {},
                },
                query_id="q-kr-phase",
                stock_code="005930",
                stock_name="三星电子",
                context_snapshot={"market_phase_summary": persisted_phase_summary},
                fallback_fundamental_payload=None,
            )

        self.assertEqual(report.meta.stock_code, "005930.KS")
        self.assertIsNotNone(report.meta.market_phase_summary)
        self.assertEqual(report.meta.market_phase_summary.market, "kr")
        self.assertEqual(report.meta.market_phase_summary.phase, "postmarket")
        self.assertEqual(
            report.meta.market_phase_summary.market_local_time,
            "2025-01-02T16:10:00+09:00",
        )
        self.assertEqual(report.meta.market_phase_summary.session_date, "2025-01-02")
        self.assertEqual(
            report.meta.market_phase_summary.effective_daily_bar_date,
            "2025-01-02",
        )
        self.assertEqual(report.meta.market_phase_summary.trigger_source, "scheduled_job")
        self.assertEqual(report.meta.market_phase_summary.analysis_intent, "postmarket")

    def test_build_analysis_report_rebuilds_legacy_cn_market_summary_for_kr_code(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        legacy_cn_summary = {
            **_market_phase_summary(),
            "market": "cn",
            "phase": "intraday",
            "market_local_time": "2026-03-27T10:00:00+08:00",
            "session_date": "2026-03-27",
            "effective_daily_bar_date": "2026-03-26",
            "analysis_intent": "intraday",
            "trigger_source": "history_snapshot",
            "warnings": ["legacy_cn_snapshot"],
        }

        with patch("api.v1.endpoints.analysis.resolve_index_stock_code", return_value="005930.KS"):
            report = _build_analysis_report(
                report_data={
                    "meta": {"stock_code": "005930"},
                    "summary": {},
                    "strategy": {},
                    "details": {},
                },
                query_id="q-kr-legacy-cn",
                stock_code="005930",
                stock_name="三星电子",
                context_snapshot={"market_phase_summary": legacy_cn_summary},
                fallback_fundamental_payload=None,
            )

        self.assertIsNotNone(report.meta.market_phase_summary)
        self.assertEqual(report.meta.stock_code, "005930.KS")
        self.assertEqual(report.meta.market_phase_summary.market, "kr")
        self.assertTrue(report.meta.market_phase_summary.market_local_time.endswith("+09:00"))
        self.assertIn("legacy_cn_snapshot", report.meta.market_phase_summary.warnings)

    def test_build_analysis_report_merges_partial_top_level_context_with_fallback(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        report = _build_analysis_report(
            report_data={
                "meta": {},
                "summary": {},
                "strategy": {},
                "details": {},
            },
            query_id="q1",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot={
                "fundamental_context": {
                    "belong_boards": [{"name": "白酒", "type": "行业"}],
                    "boards": {
                        "data": {
                            "top": [{"name": "白酒", "change_pct": 2.5}],
                            "bottom": [],
                        }
                    },
                }
            },
            fallback_fundamental_payload={
                "earnings": {
                    "data": {
                        "financial_report": {"report_date": "2025-12-31", "revenue": 1000},
                        "dividend": {"ttm_dividend_yield_pct": 2.6},
                    }
                }
            },
        )

        self.assertEqual(report.details.belong_boards, [{"name": "白酒", "type": "行业"}])
        self.assertEqual(report.details.sector_rankings["top"][0]["name"], "白酒")
        self.assertEqual(report.details.financial_report["report_date"], "2025-12-31")
        self.assertEqual(report.details.dividend_metrics["ttm_dividend_yield_pct"], 2.6)

    def test_build_analysis_report_keeps_fallback_when_snapshot_has_empty_placeholders(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        report = _build_analysis_report(
            report_data={
                "meta": {},
                "summary": {},
                "strategy": {},
                "details": {},
            },
            query_id="q1",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot={
                "fundamental_context": {
                    "belong_boards": [],
                    "boards": {},
                    "earnings": {},
                },
                "enhanced_context": {
                    "fundamental_context": {
                        "earnings": {"data": {}},
                    }
                },
            },
            fallback_fundamental_payload={
                "belong_boards": [{"name": "白酒", "type": "行业"}],
                "boards": {
                    "data": {
                        "top": [{"name": "白酒", "change_pct": 2.5}],
                        "bottom": [],
                    }
                },
                "earnings": {
                    "data": {
                        "financial_report": {"report_date": "2025-12-31", "revenue": 1000},
                        "dividend": {"ttm_dividend_yield_pct": 2.6},
                    }
                },
            },
        )

        self.assertEqual(report.details.belong_boards, [{"name": "白酒", "type": "行业"}])
        self.assertEqual(report.details.sector_rankings["top"][0]["name"], "白酒")
        self.assertEqual(report.details.financial_report["report_date"], "2025-12-31")
        self.assertEqual(report.details.dividend_metrics["ttm_dividend_yield_pct"], 2.6)

    def test_build_analysis_report_normalizes_related_board_payloads(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        report = _build_analysis_report(
            report_data={
                "meta": {},
                "summary": {},
                "strategy": {},
                "details": {},
            },
            query_id="q1",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot={
                "enhanced_context": {
                    "fundamental_context": {
                        "belong_boards": [
                            {"name": " 白酒 ", "type": " 行业 ", "code": " BK0815 "},
                            {"name": "   "},
                            "bad-item",
                        ],
                        "boards": {
                            "data": {
                                "top": {"name": "坏数据"},
                                "bottom": [
                                    {"name": " 消费 ", "change_pct": "-1.2%"},
                                    {"name": None, "change_pct": 1},
                                    "bad-item",
                                ],
                            }
                        },
                    }
                }
            },
            fallback_fundamental_payload=None,
        )

        self.assertEqual(
            report.details.belong_boards,
            [{"name": "白酒", "type": "行业", "code": "BK0815"}],
        )
        self.assertEqual(
            report.details.sector_rankings,
            {
                "top": [],
                "bottom": [{"name": "消费", "change_pct": -1.2}],
            },
        )

    def test_build_analysis_report_keeps_failed_board_rankings_unavailable(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        report = _build_analysis_report(
            report_data={
                "meta": {},
                "summary": {},
                "strategy": {},
                "details": {},
            },
            query_id="q1",
            stock_code="600519",
            stock_name="贵州茅台",
            context_snapshot={
                "enhanced_context": {
                    "fundamental_context": {
                        "belong_boards": [{"name": "白酒"}],
                        "boards": {
                            "status": "failed",
                            "data": {},
                        },
                    }
                }
            },
            fallback_fundamental_payload=None,
        )

        self.assertEqual(report.details.belong_boards, [{"name": "白酒"}])
        self.assertIsNone(report.details.sector_rankings)

    def test_build_analysis_report_preserves_report_language(self) -> None:
        if _build_analysis_report is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        report = _build_analysis_report(
            report_data={
                "meta": {"report_language": "en"},
                "summary": {"analysis_summary": "English output"},
                "strategy": {},
                "details": {},
            },
            query_id="q1",
            stock_code="AAPL",
            stock_name="Apple",
            context_snapshot={"report_language": "zh"},
            fallback_fundamental_payload=None,
        )

        self.assertEqual(report.meta.report_language, "en")

    def test_load_sync_fundamental_sources_uses_query_and_code_for_fallback(self) -> None:
        if _load_sync_fundamental_sources is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        mock_db = MagicMock()
        raw_result_payload = {
            "model_used": "test-model",
            "report_language": "zh",
            "market_structure_context": _market_structure_context(),
        }
        mock_db.get_analysis_history.return_value = [
            SimpleNamespace(
                context_snapshot=None,
                raw_result=json.dumps(raw_result_payload, ensure_ascii=False),
            )
        ]
        fallback_payload = {
            "earnings": {
                "data": {
                    "financial_report": {"report_date": "2025-12-31"},
                    "dividend": {"ttm_dividend_yield_pct": 2.1},
                }
            }
        }
        mock_db.get_latest_fundamental_snapshot.return_value = fallback_payload

        with patch("src.storage.DatabaseManager.get_instance", return_value=mock_db):
            context_snapshot, fundamental_snapshot, raw_result_snapshot = _load_sync_fundamental_sources(
                query_id="q_sync_001",
                stock_code="600519",
            )

        self.assertIsNone(context_snapshot)
        self.assertEqual(fundamental_snapshot, fallback_payload)
        self.assertEqual(raw_result_snapshot, raw_result_payload)
        mock_db.get_analysis_history.assert_called_once_with(
            query_id="q_sync_001",
            code="600519",
            limit=1,
        )
        mock_db.get_latest_fundamental_snapshot.assert_called_once_with(
            query_id="q_sync_001",
            code="600519",
        )

    def test_get_analysis_status_reads_price_fields_from_context_snapshot_preserving_zero_change_pct(self) -> None:
        if get_analysis_status is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        record = SimpleNamespace(
            id=1,
            code="600519",
            name="贵州茅台",
            report_type="detailed",
            created_at=datetime(2026, 4, 10, 12, 0, 0),
            raw_result=json.dumps({"model_used": "test-model", "report_language": "zh"}),
            context_snapshot=json.dumps(
                {
                    "enhanced_context": {
                        "realtime": {
                            "price": 1234.5,
                            "change_pct": 0.0,
                            "change_60d": 9.99,
                        }
                    },
                    "realtime_quote_raw": {
                        "price": 999.9,
                        "change_pct": 8.88,
                        "pct_chg": 7.77,
                    },
                }
            ),
            sentiment_score=80,
            operation_advice="持有",
            trend_prediction="震荡上行",
            analysis_summary="summary",
            ideal_buy=None,
            secondary_buy=None,
            stop_loss=None,
            take_profit=None,
        )
        mock_db = MagicMock()
        mock_db.get_analysis_history.return_value = [record]

        with patch("api.v1.endpoints.analysis.get_task_queue") as queue_mock, \
             patch("src.storage.DatabaseManager.get_instance", return_value=mock_db):
            queue_mock.return_value.get_task.return_value = None
            status = get_analysis_status("task_123")

        self.assertEqual(status.status, "completed")
        self.assertEqual(status.result.report["meta"]["current_price"], 1234.5)
        self.assertEqual(status.result.report["meta"]["change_pct"], 0.0)
        self.assertEqual(status.result.report["meta"]["model_used"], "test-model")

    def test_get_analysis_status_restores_market_structure_from_raw_result_without_snapshot(self) -> None:
        if get_analysis_status is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        market_structure = {
            "schema_version": "market-structure-v1",
            "status": "partial",
            "market": "cn",
            "market_theme_context": {
                "schema_version": "market-theme-v1",
                "status": "partial",
                "market": "cn",
                "active_themes": [{"name": "机器人概念"}],
            },
            "stock_market_position": {
                "schema_version": "stock-market-position-v1",
                "status": "partial",
                "stock_code": "300024",
                "market": "cn",
                "primary_theme": {"name": "机器人概念"},
            },
        }
        record = SimpleNamespace(
            id=1,
            code="300024",
            name="机器人",
            report_type="detailed",
            created_at=datetime(2026, 4, 10, 12, 0, 0),
            raw_result=json.dumps(
                {
                    "model_used": "test-model",
                    "report_language": "zh",
                    "market_structure_context": market_structure,
                }
            ),
            context_snapshot=None,
            sentiment_score=80,
            operation_advice="持有",
            trend_prediction="震荡上行",
            analysis_summary="summary",
            ideal_buy=None,
            secondary_buy=None,
            stop_loss=None,
            take_profit=None,
        )
        mock_db = MagicMock()
        mock_db.get_analysis_history.return_value = [record]
        mock_db.get_latest_fundamental_snapshot.return_value = None

        with patch("api.v1.endpoints.analysis.get_task_queue") as queue_mock, \
             patch("src.storage.DatabaseManager.get_instance", return_value=mock_db):
            queue_mock.return_value.get_task.return_value = None
            status = get_analysis_status("task_market_structure_raw_1")

        self.assertEqual(status.status, "completed")
        self.assertEqual(
            status.result.report["details"]["market_structure"]["market_theme_context"]["active_themes"][0]["name"],
            "机器人概念",
        )

    def test_get_analysis_status_completed_db_snapshot_includes_agent_snapshot_board_details(self) -> None:
        if get_analysis_status is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        overview = _analysis_context_pack_overview()
        phase_summary = _market_phase_summary()
        record = SimpleNamespace(
            id=1,
            code="600519",
            name="贵州茅台",
            report_type="detailed",
            created_at=datetime(2026, 4, 10, 12, 0, 0),
            raw_result=json.dumps({"model_used": "test-model", "report_language": "zh"}),
            context_snapshot=json.dumps(
                {
                    "fundamental_context": {
                        "belong_boards": [{"name": "白酒", "type": "行业"}],
                        "boards": {
                            "data": {
                                "top": [{"name": "白酒", "change_pct": 2.8}],
                                "bottom": [],
                            }
                        },
                    },
                    "realtime_quote": {
                        "price": 1888.0,
                        "change_pct": 1.56,
                    },
                    "analysis_context_pack_overview": overview,
                    "market_phase_summary": {
                        **phase_summary,
                        "quote_timestamp": "not-public",
                    },
                }
            ),
            news_content="news",
            sentiment_score=80,
            operation_advice="持有",
            trend_prediction="震荡上行",
            analysis_summary="summary",
            ideal_buy=None,
            secondary_buy=None,
            stop_loss=None,
            take_profit=None,
        )
        mock_db = MagicMock()
        mock_db.get_analysis_history.return_value = [record]
        mock_db.get_latest_fundamental_snapshot.return_value = None

        with patch("api.v1.endpoints.analysis.get_task_queue") as queue_mock, \
             patch("src.storage.DatabaseManager.get_instance", return_value=mock_db):
            queue_mock.return_value.get_task.return_value = None
            status = get_analysis_status("task_agent_snapshot_1")

        self.assertEqual(status.status, "completed")
        self.assertEqual(status.result.report["meta"]["current_price"], 1888.0)
        self.assertEqual(status.result.report["meta"]["change_pct"], 1.56)
        self.assertIsNone(status.analysis_phase)
        self.assertEqual(
            status.result.report["meta"]["market_phase_summary"]["phase"],
            "intraday",
        )
        self.assertEqual(
            status.result.report["details"]["belong_boards"],
            [{"name": "白酒", "type": "行业"}],
        )
        self.assertEqual(
            status.result.report["details"]["sector_rankings"]["top"][0]["name"],
            "白酒",
        )
        self.assertEqual(
            status.result.report["details"]["analysis_context_pack_overview"]["metadata"]["trigger_source"],
            "api",
        )
        self.assertEqual(
            status.result.report["details"]["analysis_context_pack_overview"]["data_quality"]["overall_score"],
            88,
        )
        self.assertNotIn(
            "analysis_context_pack_overview",
            status.result.report["details"]["context_snapshot"],
        )
        self.assertNotIn(
            "market_phase_summary",
            status.result.report["details"]["context_snapshot"],
        )

    def test_get_analysis_status_in_memory_task_enriches_agent_snapshot_board_details(self) -> None:
        if get_analysis_status is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        overview = _analysis_context_pack_overview()
        phase_summary = _market_phase_summary()
        context_snapshot = {
            "fundamental_context": {
                "belong_boards": [{"name": "白酒", "type": "行业"}],
                "boards": {
                    "data": {
                        "top": [{"name": "白酒", "change_pct": 2.8}],
                        "bottom": [],
                    }
                },
            },
            "realtime_quote": {
                "price": 1888.0,
                "change_pct": 1.56,
            },
            "analysis_context_pack_overview": overview,
            "market_phase_summary": phase_summary,
        }
        task = SimpleNamespace(
            task_id="task_agent_snapshot_in_memory_1",
            stock_code="600519",
            stock_name="贵州茅台",
            status=TaskStatus.COMPLETED,
            progress=100,
            result={
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "report": {
                    "meta": {
                        "query_id": "task_agent_snapshot_in_memory_1",
                        "stock_code": "600519",
                        "stock_name": "贵州茅台",
                        "report_type": "detailed",
                        "report_language": "zh",
                        "created_at": "2026-04-10T12:00:00",
                        "model_used": "test-model",
                    },
                    "summary": {"analysis_summary": "summary"},
                    "details": {"news_summary": "news"},
                },
            },
            error=None,
            original_query=None,
            selection_source=None,
            analysis_phase="auto",
            skills=None,
            created_at=datetime(2026, 4, 10, 12, 0, 0),
            completed_at=datetime(2026, 4, 10, 12, 1, 0),
        )
        record = SimpleNamespace(context_snapshot=json.dumps(context_snapshot))
        mock_db = MagicMock()
        mock_db.get_analysis_history.return_value = [record]
        mock_db.get_latest_fundamental_snapshot.return_value = None

        with patch("api.v1.endpoints.analysis.get_task_queue") as queue_mock, \
             patch("src.storage.DatabaseManager.get_instance", return_value=mock_db):
            queue_mock.return_value.get_task.return_value = task
            status = get_analysis_status("task_agent_snapshot_in_memory_1")

        self.assertEqual(status.status, "completed")
        self.assertEqual(status.result.report["meta"]["current_price"], 1888.0)
        self.assertEqual(status.result.report["meta"]["change_pct"], 1.56)
        self.assertEqual(
            status.result.report["meta"]["market_phase_summary"]["phase"],
            "intraday",
        )
        self.assertEqual(
            status.result.report["details"]["belong_boards"],
            [{"name": "白酒", "type": "行业"}],
        )
        self.assertEqual(
            status.result.report["details"]["sector_rankings"]["top"][0]["name"],
            "白酒",
        )
        self.assertEqual(
            status.result.report["details"]["analysis_context_pack_overview"]["metadata"]["trigger_source"],
            "api",
        )
        self.assertEqual(
            status.result.report["details"]["analysis_context_pack_overview"]["data_quality"]["overall_score"],
            88,
        )
        self.assertNotIn(
            "analysis_context_pack_overview",
            status.result.report["details"]["context_snapshot"],
        )
        self.assertNotIn(
            "market_phase_summary",
            status.result.report["details"]["context_snapshot"],
        )
        mock_db.get_analysis_history.assert_called_once_with(
            query_id="task_agent_snapshot_in_memory_1",
            code="600519",
            limit=1,
        )

    def test_get_analysis_status_in_memory_task_without_db_snapshot_preserves_service_phase_summary(self) -> None:
        if get_analysis_status is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        phase_summary = _market_phase_summary()
        task = SimpleNamespace(
            task_id="task_no_snapshot_in_memory_1",
            stock_code="600519",
            stock_name="贵州茅台",
            status=TaskStatus.COMPLETED,
            progress=100,
            analysis_phase="intraday",
            result={
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "report": {
                    "meta": {
                        "query_id": "task_no_snapshot_in_memory_1",
                        "stock_code": "600519",
                        "stock_name": "贵州茅台",
                        "market_phase_summary": phase_summary,
                    },
                    "summary": {"analysis_summary": "summary"},
                },
            },
            error=None,
            original_query=None,
            selection_source=None,
            skills=None,
            created_at=datetime(2026, 4, 10, 12, 0, 0),
            completed_at=datetime(2026, 4, 10, 12, 1, 0),
        )

        with patch("api.v1.endpoints.analysis.get_task_queue") as queue_mock, \
             patch(
                 "api.v1.endpoints.analysis._load_sync_fundamental_sources",
                 return_value=(None, None, None),
             ) as load_sources:
            queue_mock.return_value.get_task.return_value = task
            status = get_analysis_status("task_no_snapshot_in_memory_1")

        self.assertEqual(status.status, "completed")
        self.assertEqual(status.analysis_phase, "intraday")
        self.assertIsNotNone(status.result)
        self.assertEqual(
            status.result.report["meta"]["market_phase_summary"]["phase"],
            "intraday",
        )
        load_sources.assert_called_once_with(
            query_id="task_no_snapshot_in_memory_1",
            stock_code="600519",
        )
