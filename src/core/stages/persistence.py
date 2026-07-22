# -*- coding: utf-8 -*-
"""Persistence and diagnostic snapshot stages for the stock analysis pipeline."""

import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from data_provider.base import is_bse_code, normalize_stock_code
from data_provider.realtime_types import ChipDistribution
from src.analysis_context_pack_overview import render_analysis_context_pack_overview
from src.analysis_context_pack_prompt import format_analysis_context_pack_prompt_section
from src.analyzer import AnalysisResult
from src.core.pipeline_stage_results import (
    PipelinePersistValue,
    PipelineStageName,
    PipelineStageResult,
    PipelineStageStatus,
)
from src.market_phase_summary import MARKET_PHASE_SUMMARY_KEY
from src.services.analysis_context_builder import (
    AnalysisContextBuilder,
    PipelineAnalysisArtifacts,
)
from src.services.decision_signal_extractor import (
    extract_and_persist_from_analysis_result,
)
from src.services.decision_signal_summary import summarize_decision_signal
from src.services.intelligence_service import IntelligenceService
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    get_current_diagnostic_context,
    record_history_run,
    sanitize_diagnostic_text,
)
from src.stock_analyzer import TrendAnalysisResult
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger("src.core.pipeline")


def _symbol_scope_lookup_values(code: str, market: str) -> List[str]:
    """Return accepted persisted-intelligence symbol spellings for lookup."""
    raw = str(code or "").strip()
    normalized = normalize_stock_code(raw) if raw else ""
    values: List[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            values.append(text)

    def add_case_variants(value: str) -> None:
        text = str(value or "").strip()
        if not text:
            return
        add(text)
        add(text.upper())
        add(text.lower())

    add_case_variants(normalized)
    add_case_variants(raw)

    normalized_upper = normalized.upper()
    if normalized_upper.startswith("HK") and normalized_upper[2:].isdigit():
        digits = normalized_upper[2:]
        trimmed_digits = digits.lstrip("0") or digits
        add_case_variants(normalized_upper)
        add_case_variants(digits)
        add_case_variants(trimmed_digits)
        add_case_variants(f"HK{trimmed_digits}")
        add_case_variants(f"{trimmed_digits}.HK")
        add_case_variants(f"{digits}.HK")
        return values

    if (market or "").strip().lower() != "cn":
        return values
    if not (normalized.isdigit() and len(normalized) == 6):
        return values

    raw_upper = raw.upper()
    exchange = ""
    if raw_upper.startswith(("SH", "SS")) or raw_upper.endswith((".SH", ".SS")):
        exchange = "SH"
    elif raw_upper.startswith("SZ") or raw_upper.endswith(".SZ"):
        exchange = "SZ"
    elif raw_upper.startswith("BJ") or raw_upper.endswith(".BJ"):
        exchange = "BJ"
    elif is_bse_code(normalized):
        exchange = "BJ"
    elif normalized.startswith(("5", "6", "9")):
        exchange = "SH"
    else:
        exchange = "SZ"

    add_case_variants(f"{exchange}{normalized}")
    add_case_variants(f"{exchange}.{normalized}")
    add_case_variants(f"{normalized}.{exchange}")
    if exchange == "SH":
        add_case_variants(f"SS.{normalized}")
        add_case_variants(f"{normalized}.SS")
    return values


class _PersistenceStageMixin:
    """Provide history persistence and diagnostic snapshot stages."""

    def _build_context_snapshot(
        self,
        enhanced_context: Dict[str, Any],
        news_content: Optional[str],
        realtime_quote: Any,
        chip_data: Optional[ChipDistribution],
        news_result_count: Optional[int] = None,
        analysis_context_pack_overview: Optional[Dict[str, Any]] = None,
        market_phase_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        构建分析上下文快照
        """
        snapshot = {
            "enhanced_context": self._without_runtime_prompt_context(enhanced_context),
            "news_content": news_content,
            "realtime_quote_raw": self._safe_to_dict(realtime_quote),
            "chip_distribution_raw": self._safe_to_dict(chip_data),
        }
        market_structure_context = enhanced_context.get("market_structure_context")
        if isinstance(market_structure_context, dict):
            snapshot["market_structure_context"] = market_structure_context
        if news_content is not None:
            snapshot["news_retrieval_content"] = news_content
        if news_result_count is not None:
            snapshot["news_result_count"] = news_result_count
        if analysis_context_pack_overview is not None:
            snapshot["analysis_context_pack_overview"] = analysis_context_pack_overview
        if market_phase_summary is not None:
            snapshot[MARKET_PHASE_SUMMARY_KEY] = market_phase_summary
        diagnostic_snapshot = current_diagnostic_snapshot()
        if diagnostic_snapshot is not None:
            snapshot["diagnostics"] = diagnostic_snapshot
        if self.analysis_skills is not None:
            snapshot["skills"] = list(self.analysis_skills)
        return snapshot

    def _persist_analysis_history_stage(
        self,
        *,
        result: AnalysisResult,
        query_id: str,
        report_type: str,
        news_content: Optional[str],
        context_snapshot_factory: Callable[[], Dict[str, Any]],
        portfolio_context: Optional[Dict[str, Any]],
        failure_reason: str,
        failure_message: str,
        failure_error_code: str,
    ) -> PipelineStageResult[PipelinePersistValue]:
        """Persist one analysis once for a stable query and return its stage result."""

        def _persist() -> PipelineStageResult[PipelinePersistValue]:
            context_snapshot: Dict[str, Any] = {}
            saved_history_id: Any = None
            persistence_error: Optional[BaseException] = None
            try:
                context_snapshot = context_snapshot_factory()
                result.diagnostic_context_snapshot = context_snapshot
                saved_history_id = self.db.save_analysis_history(
                    result=result,
                    query_id=query_id,
                    report_type=report_type,
                    news_content=news_content,
                    context_snapshot=context_snapshot,
                    save_snapshot=self.save_context_snapshot,
                )
                valid_saved_history_id = (
                    isinstance(saved_history_id, int)
                    and not isinstance(saved_history_id, bool)
                    and saved_history_id > 0
                )
                if valid_saved_history_id:
                    self._extract_decision_signal_after_history_save(
                        result=result,
                        query_id=query_id,
                        source_report_id=saved_history_id,
                        report_type=report_type,
                        context_snapshot=context_snapshot,
                        portfolio_context=portfolio_context,
                    )
            except Exception as exc:  # broad-exception: fallback_recorded - History failure remains isolated after the side-effect fence records whether a write committed.
                persistence_error = exc
                valid_saved_history_id = False
                record_history_run(
                    report_saved=False,
                    metadata_saved=False,
                    error_message=exc,
                )
                log_safe_exception(
                    logger,
                    failure_message,
                    exc,
                    error_code=failure_error_code,
                    level=logging.WARNING,
                    context={"stock_code": getattr(result, "code", None)},
                )

            persistence_succeeded = bool(saved_history_id)
            value = PipelinePersistValue(
                saved=persistence_succeeded,
                history_id=(
                    saved_history_id if valid_saved_history_id else None
                ),
                context_snapshot=context_snapshot,
            )
            if persistence_succeeded:
                return PipelineStageResult(
                    stage=PipelineStageName.PERSIST,
                    status=PipelineStageStatus.SUCCESS,
                    value=value,
                    side_effect_committed=True,
                    error=persistence_error,
                )
            return PipelineStageResult.failed(
                PipelineStageName.PERSIST,
                value=value,
                error=persistence_error,
                retryable=True,
                reason=failure_reason,
            )

        persistence_result = self._get_pipeline_stage_runner().run(
            PipelineStageName.PERSIST,
            _persist,
            retryable=True,
            side_effect_key=(
                "analysis_history",
                query_id,
                getattr(result, "code", None),
                report_type,
            ),
        )
        if not persistence_result.reused:
            persistence_value = persistence_result.value
            if persistence_result.error is None:
                record_history_run(
                    report_saved=bool(persistence_value and persistence_value.saved),
                    metadata_saved=bool(persistence_value and persistence_value.saved),
                    analysis_history_id=(
                        persistence_value.history_id
                        if persistence_value is not None
                        else None
                    ),
                )
        return persistence_result

    def _extract_decision_signal_after_history_save(
        self,
        *,
        result: AnalysisResult,
        query_id: str,
        source_report_id: int,
        report_type: str,
        context_snapshot: Dict[str, Any],
        portfolio_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Best-effort DecisionSignal extraction after analysis history is saved."""

        assert (
            isinstance(source_report_id, int)
            and not isinstance(source_report_id, bool)
            and source_report_id > 0
        )

        try:
            diagnostic_context = get_current_diagnostic_context()
            trace_id = (
                getattr(diagnostic_context, "trace_id", None)
                or getattr(self, "trace_id", None)
                or query_id
            )
            signal_result = extract_and_persist_from_analysis_result(
                result,
                context_snapshot=context_snapshot,
                source_report_id=source_report_id,
                trace_id=str(trace_id),
                query_source=getattr(self, "query_source", None) or "system",
                report_type=report_type,
                portfolio_context=portfolio_context,
                profile_source="auto_default",
            )
            if isinstance(signal_result, dict):
                summary = summarize_decision_signal(
                    signal_result.get("item"),
                    report_language=getattr(result, "report_language", None),
                )
                if summary:
                    setattr(result, "decision_signal_summary", summary)
        except Exception as exc:  # broad-exception: fallback_recorded - Decision-signal extraction failures are logged after history persistence.
            log_safe_exception(
                logger,
                "Decision signal extraction failed after history save",
                exc,
                error_code="pipeline_decision_signal_extraction_failed",
                level=logging.WARNING,
                context={
                    "query_id": query_id,
                    "stock_code": getattr(result, "code", None),
                },
            )

    @staticmethod
    def _build_notification_run_snapshot(
        *,
        channel: str,
        status: str,
        success: bool,
        attempts: int = 1,
        error_message: Optional[Any] = None,
    ) -> Dict[str, Any]:
        payload = {
            "channel": channel,
            "status": status,
            "success": success,
            "attempts": attempts,
            "created_at": datetime.now().isoformat(),
        }
        sanitized_error = sanitize_diagnostic_text(error_message)
        if sanitized_error:
            payload["error_message_sanitized"] = sanitized_error
        return payload

    def _activate_delivery_diagnostic_context(
        self,
        results: List[AnalysisResult],
    ):
        """Activate an isolated delivery trace nested under any caller context."""
        try:
            first_result = results[0] if results else None
            context_snapshot = (
                getattr(first_result, "diagnostic_context_snapshot", None)
                if first_result is not None
                else None
            )
            existing_diagnostics = (
                context_snapshot.get("diagnostics")
                if isinstance(context_snapshot, dict)
                else None
            )
            single_result = len(results) == 1
            inherited_trace_id = (
                existing_diagnostics.get("trace_id")
                if single_result and isinstance(existing_diagnostics, dict)
                else None
            )
            inherited_query_id = (
                getattr(first_result, "query_id", None)
                if single_result and first_result is not None
                else None
            )
            delivery_id = (
                getattr(self, "trace_id", None)
                or getattr(self, "query_id", None)
                or inherited_trace_id
                or f"delivery_{uuid.uuid4().hex}"
            )
            return activate_run_diagnostic_context(
                trace_id=delivery_id,
                query_id=(
                    getattr(self, "query_id", None)
                    or inherited_query_id
                    or delivery_id
                ),
                stock_code=(
                    getattr(first_result, "code", None)
                    if single_result and first_result is not None
                    else None
                ),
                trigger_source=getattr(self, "query_source", None),
                scope="pipeline_delivery",
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Delivery context failures are logged and leave delivery behavior unchanged.
            log_safe_exception(
                logger,
                "Pipeline delivery diagnostic context activation failed",
                exc,
                error_code="pipeline_delivery_context_activation_failed",
                level=logging.WARNING,
                context={"result_count": len(results)},
            )
            return None

    @staticmethod
    def _merge_delivery_diagnostic_snapshot(
        item: AnalysisResult,
        delivery_snapshot: Dict[str, Any],
        notification_run: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Merge delivery-only runs into one result without replacing analysis runs."""
        raw_context_snapshot = getattr(item, "diagnostic_context_snapshot", None)
        context_snapshot = (
            dict(raw_context_snapshot)
            if isinstance(raw_context_snapshot, dict)
            else {}
        )
        raw_diagnostics = context_snapshot.get("diagnostics")
        diagnostics = dict(raw_diagnostics) if isinstance(raw_diagnostics, dict) else {}
        diagnostics.setdefault(
            "trace_id",
            getattr(item, "trace_id", None)
            or getattr(item, "query_id", None)
            or delivery_snapshot.get("trace_id"),
        )
        diagnostics.setdefault("query_id", getattr(item, "query_id", None))
        diagnostics.setdefault("stock_code", getattr(item, "code", None))

        for field_name in ("notification_runs", "pipeline_stage_runs"):
            raw_existing_runs = diagnostics.get(field_name)
            existing_runs = (
                list(raw_existing_runs)
                if isinstance(raw_existing_runs, list)
                else []
            )
            if field_name == "notification_runs":
                candidate_runs = (
                    [notification_run] if notification_run is not None else []
                )
            else:
                candidates = delivery_snapshot.get(field_name)
                candidate_runs = (
                    list(candidates) if isinstance(candidates, list) else []
                )
            for candidate in candidate_runs:
                if not isinstance(candidate, dict):
                    continue
                payload = dict(candidate)
                if field_name == "notification_runs" and not payload.get("trace_id"):
                    payload["trace_id"] = delivery_snapshot.get("trace_id")
                if payload not in existing_runs:
                    existing_runs.append(payload)
            diagnostics[field_name] = existing_runs

        context_snapshot["diagnostics"] = diagnostics
        item.diagnostic_context_snapshot = context_snapshot
        return diagnostics

    def _refresh_saved_diagnostic_snapshot(
        self,
        *,
        result: Optional[AnalysisResult] = None,
        results: Optional[List[AnalysisResult]] = None,
        fallback_code: Optional[str] = None,
        notification_run: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Patch persisted history with the latest fail-open diagnostic snapshot."""
        if not getattr(self, "save_context_snapshot", True):
            return

        db = getattr(self, "db", None)
        updater = getattr(db, "update_analysis_history_diagnostics", None)
        if not callable(updater):
            return

        diagnostic_snapshot = current_diagnostic_snapshot()
        target_results = list(results or ([] if result is None else [result]))
        if diagnostic_snapshot is not None and (
            results is not None
            or diagnostic_snapshot.get("scope") == "pipeline_delivery"
        ):
            for item in target_results:
                query_id = (
                    getattr(item, "query_id", None)
                    or getattr(self, "query_id", None)
                )
                if not query_id:
                    continue
                code = getattr(item, "code", None) or fallback_code
                try:
                    merged_diagnostics = self._merge_delivery_diagnostic_snapshot(
                        item,
                        diagnostic_snapshot,
                        notification_run,
                    )
                    updater(
                        query_id=query_id,
                        code=code,
                        diagnostics=merged_diagnostics,
                    )
                except Exception as exc:  # broad-exception: optional_metadata - Delivery diagnostics are best-effort and cannot change delivery outcomes.
                    log_safe_exception(
                        logger,
                        "Delivery diagnostic snapshot update failed; continuing without the update",
                        exc,
                        error_code="pipeline_delivery_snapshot_update_failed",
                        level=logging.WARNING,
                        context={"query_id": query_id, "stock_code": code},
                    )
            return

        if diagnostic_snapshot is not None:
            query_id = (
                diagnostic_snapshot.get("query_id")
                or getattr(result, "query_id", None)
                or getattr(self, "query_id", None)
            )
            code = (
                getattr(result, "code", None)
                or fallback_code
                or diagnostic_snapshot.get("stock_code")
            )
            if not query_id:
                return
            try:
                updater(query_id=query_id, code=code, diagnostics=diagnostic_snapshot)
            except Exception as exc:  # broad-exception: optional_metadata - Run diagnostics are best-effort and cannot change analysis outcomes.
                log_safe_exception(
                    logger,
                    "Run diagnostic snapshot update failed; continuing without the update",
                    exc,
                    error_code="pipeline_diagnostic_snapshot_update_failed",
                    level=logging.WARNING,
                    context={"query_id": query_id, "stock_code": code},
                )
            return

        if notification_run is None:
            return

        for item in target_results:
            query_id = getattr(item, "query_id", None) or getattr(self, "query_id", None)
            if not query_id:
                continue
            code = getattr(item, "code", None) or fallback_code
            try:
                updater(
                    query_id=query_id,
                    code=code,
                    notification_runs=[notification_run],
                )
            except Exception as exc:  # broad-exception: optional_metadata - Notification diagnostics are best-effort and cannot change delivery outcomes.
                log_safe_exception(
                    logger,
                    "Notification diagnostic snapshot update failed; continuing without the update",
                    exc,
                    error_code="pipeline_notification_snapshot_update_failed",
                    level=logging.WARNING,
                    context={"query_id": query_id, "stock_code": code},
                )

    def _load_persisted_intelligence_context(
        self,
        *,
        code: str,
        stock_name: str,
        market: str,
        limit: int = 6,
    ) -> Optional[str]:
        """Load locally persisted intelligence as fail-open evidence context."""
        try:
            service = IntelligenceService(config=self.config)
            service.refresh_auto_sources()
            days = max(1, int(self.config.get_effective_news_window_days() or 1))
            collected: list[Dict[str, Any]] = []
            seen_urls: set[str] = set()
            symbol_filters = [
                {"scope_type": "symbol", "scope_value": scope_value, "market": market}
                for scope_value in _symbol_scope_lookup_values(code, market)
            ]
            for filters in symbol_filters + [{"scope_type": "market", "market": market}]:
                payload = service.list_items(published_days=days, page=1, page_size=limit, **filters)
                for item in payload.get("items", []):
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url") or "")
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    collected.append(item)
                    if len(collected) >= limit:
                        break
                if len(collected) >= limit:
                    break
            if not collected:
                return None
            lines = [f"## 本地资讯证据池（{stock_name}/{code}）"]
            for idx, item in enumerate(collected[:limit], 1):
                title = str(item.get("title") or "未命名资讯").strip()
                summary = str(item.get("summary") or "").strip()
                source = str(item.get("source") or item.get("source_name") or "local-intel").strip()
                published = str(item.get("published_at") or "").strip()
                url = str(item.get("url") or "").strip()
                meta = " / ".join(part for part in (source, published) if part)
                lines.append(f"{idx}. {title}" + (f"（{meta}）" if meta else ""))
                if summary:
                    lines.append(f"   摘要：{summary[:220]}")
                if url and not url.startswith("no-url:intel:"):
                    lines.append(f"   来源：{url}")
            return "\n".join(lines)
        except Exception as exc:  # broad-exception: fallback_recorded - Local-evidence failures are logged and analysis continues without optional context.
            log_safe_exception(
                logger,
                "Local intelligence evidence load failed; continuing without local evidence",
                exc,
                error_code="pipeline_local_intelligence_load_failed",
                level=logging.DEBUG,
                context={"stock_code": code, "market": market},
            )
            return None

    def _build_legacy_analysis_artifacts(
        self,
        *,
        code: str,
        stock_name: str,
        market: str,
        phase: Optional[Dict[str, Any]],
        context: Dict[str, Any],
        enhanced_context: Dict[str, Any],
        realtime_quote: Any,
        trend_result: Optional[TrendAnalysisResult],
        chip_data: Optional[ChipDistribution],
        fundamental_context: Optional[Dict[str, Any]],
        news_context: Optional[str],
        news_result_count: Optional[int],
        query_id: str,
        portfolio_context: Optional[Dict[str, Any]] = None,
    ) -> PipelineAnalysisArtifacts:
        return PipelineAnalysisArtifacts(
            code=code,
            stock_name=stock_name,
            market=market,
            phase=phase,
            base_context=context,
            enhanced_context=enhanced_context,
            realtime_quote=realtime_quote,
            trend_result=trend_result,
            chip_data=chip_data,
            fundamental_context=fundamental_context,
            news_context=news_context,
            news_result_count=news_result_count,
            metadata={
                "query_id": query_id,
                "trigger_source": self.query_source,
            },
            portfolio_context=dict(portfolio_context) if isinstance(portfolio_context, dict) else None,
        )

    def _build_agent_analysis_artifacts(
        self,
        *,
        code: str,
        stock_name: str,
        market: str,
        phase: Optional[Dict[str, Any]],
        initial_context: Dict[str, Any],
        fundamental_context: Optional[Dict[str, Any]],
        query_id: str,
        base_context: Optional[Dict[str, Any]] = None,
        portfolio_context: Optional[Dict[str, Any]] = None,
    ) -> PipelineAnalysisArtifacts:
        context_candidate = base_context
        if not isinstance(context_candidate, dict):
            context_candidate = initial_context.get("analysis_context")
        if isinstance(context_candidate, dict) and context_candidate:
            daily_context = dict(context_candidate)
            daily_context.setdefault("code", code)
            if stock_name:
                daily_context.setdefault("stock_name", stock_name)
        else:
            daily_context = {
                "code": code,
                "stock_name": stock_name,
                "data_missing": True,
                "today": {},
                "yesterday": {},
            }

        return PipelineAnalysisArtifacts(
            code=code,
            stock_name=stock_name,
            market=market,
            phase=phase,
            base_context=daily_context,
            enhanced_context={},
            realtime_quote=initial_context.get("realtime_quote"),
            trend_result=initial_context.get("trend_result"),
            chip_data=initial_context.get("chip_distribution"),
            fundamental_context=fundamental_context,
            news_context=initial_context.get("news_context"),
            news_result_count=None,
            metadata={
                "query_id": query_id,
                "trigger_source": self.query_source,
            },
            portfolio_context=dict(portfolio_context) if isinstance(portfolio_context, dict) else None,
        )

    def _build_analysis_context_pack_outputs(
        self,
        artifacts: PipelineAnalysisArtifacts,
        *,
        report_language: str,
        code: str,
        query_id: str,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        try:
            pack = AnalysisContextBuilder.build(artifacts)
            summary = format_analysis_context_pack_prompt_section(
                pack,
                report_language=report_language,
            )
            overview = render_analysis_context_pack_overview(
                pack,
                report_language=report_language,
            )
            return summary, overview
        except Exception as exc:  # broad-exception: fallback_recorded - Context-pack failures are logged and fall back to empty optional context.
            log_safe_exception(
                logger,
                "Analysis context pack output generation failed",
                exc,
                error_code="pipeline_analysis_context_pack_failed",
                level=logging.WARNING,
                context={"stock_code": code, "query_id": query_id},
            )
            return "", None

    @staticmethod
    def _without_runtime_prompt_context(context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a shallow copy without runtime-only prompt context.

        Market phase and AnalysisContextPack summaries are prompt inputs only.
        P4 stores only the separately rendered public overview at snapshot top level.
        """
        sanitized = dict(context)
        sanitized.pop("market_phase_context", None)
        sanitized.pop("portfolio_context", None)
        sanitized.pop("analysis_context_pack", None)
        sanitized.pop("analysis_context_pack_summary", None)
        sanitized.pop("daily_market_context_summary", None)
        enhanced_context = sanitized.get("enhanced_context")
        if isinstance(enhanced_context, dict):
            enhanced_context = dict(enhanced_context)
            enhanced_context.pop("daily_market_context_summary", None)
            sanitized["enhanced_context"] = enhanced_context
        return sanitized

    _without_market_phase_context = _without_runtime_prompt_context

    @staticmethod
    def _safe_to_dict(value: Any) -> Optional[Dict[str, Any]]:
        """
        安全转换为字典
        """
        if value is None:
            return None
        if hasattr(value, "to_dict"):
            try:
                return value.to_dict()
            except Exception:  # broad-exception: optional_metadata - Best-effort metadata conversion falls back to no snapshot payload.
                return None
        if hasattr(value, "__dict__"):
            try:
                return dict(value.__dict__)
            except Exception:  # broad-exception: optional_metadata - Best-effort metadata conversion falls back to no snapshot payload.
                return None
        return None

    def _build_query_context(self, query_id: Optional[str] = None) -> Dict[str, str]:
        """Build the low-sensitivity requester provenance persisted with a query."""
        effective_query_id = query_id or self.query_id or ""

        context: Dict[str, str] = {
            "query_id": effective_query_id,
            "query_source": self.query_source or "",
        }

        request_context = getattr(self, "request_context", None)
        if request_context:
            context.update({
                "requester_platform": request_context.requester_platform,
                "requester_user_id": request_context.requester_user_id,
                "requester_user_name": request_context.requester_user_name,
                "requester_chat_id": request_context.requester_chat_id,
                "requester_message_id": request_context.requester_message_id,
                "requester_query": request_context.requester_query,
            })

        return context
