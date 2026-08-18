# -*- coding: utf-8 -*-
"""User-facing run-diagnostic summary export.

Export is a pure projection from persisted or in-memory snapshots. It must not
mutate the input snapshot, raw result, or analysis outcome.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.services.diagnostics.schema import (
    RunDiagnosticComponent,
    RunDiagnosticSummary,
    sanitize_diagnostic_text,
)

_SUMMARY_STATUS_LABELS = {
    "normal": "正常",
    "degraded": "部分降级",
    "failed": "失败",
    "unknown": "未知",
}
_ANALYSIS_INPUT_STATUS_MESSAGES = {
    "missing": "未进入本次分析输入",
    "partial": "本次分析输入仅部分可用",
    "fallback": "本次分析输入使用降级数据",
    "stale": "本次分析输入使用过期数据",
    "estimated": "本次分析输入使用估算数据",
    "fetch_failed": "输入块显示抓取失败",
    "not_supported": "输入块标记为不支持",
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _component(
    key: str,
    label: str,
    status: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> RunDiagnosticComponent:
    clean_details = {
        key: value
        for key, value in (details or {}).items()
        if value is not None
    }
    return RunDiagnosticComponent(
        key=key,
        label=label,
        status=status,
        message=message,
        details=clean_details,
    )


def _analysis_context_overview(context_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    overview = context_snapshot.get("analysis_context_pack_overview")
    if not isinstance(overview, dict):
        overview = context_snapshot.get("analysisContextPackOverview")
    return overview if isinstance(overview, dict) else {}


def _analysis_input_block(
    context_snapshot: Dict[str, Any],
    block_key: str,
) -> Dict[str, Any]:
    blocks = _analysis_context_overview(context_snapshot).get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, dict) and block.get("key") == block_key:
                return block
    if isinstance(blocks, dict):
        block = blocks.get(block_key)
        if isinstance(block, dict):
            return block
    return {}


def _analysis_input_status_message(block: Dict[str, Any]) -> Optional[str]:
    status = str(block.get("status") or "").strip()
    if status == "available" or not status:
        return None
    return _ANALYSIS_INPUT_STATUS_MESSAGES.get(status, f"输入块状态为 {status}")


def _list_text(value: Any, *, limit: int = 5) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = str(item).strip() if item is not None else ""
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _reconcile_daily_provider_with_analysis_input(
    component: RunDiagnosticComponent,
    context_snapshot: Dict[str, Any],
) -> RunDiagnosticComponent:
    input_block = _analysis_input_block(context_snapshot, "daily_bars")
    input_message = _analysis_input_status_message(input_block)
    if not input_message or component.status not in {"ok", "degraded"}:
        return component

    details = dict(component.details or {})
    details.update(
        {
            "provider_run_status": component.status,
            "analysis_input_block": "daily_bars",
            "analysis_input_status": input_block.get("status"),
            "analysis_input_source": input_block.get("source"),
            "analysis_input_missing_reasons": _list_text(
                input_block.get("missing_reasons")
            ),
            "evidence_scope": "provider_run_vs_analysis_input",
        }
    )
    provider = details.get("provider") or "unknown"
    return _component(
        component.key,
        component.label,
        "degraded",
        f"{component.label}{provider} 成功，但{input_message}",
        details,
    )


def _provider_component(
    *,
    key: str,
    label: str,
    data_type: str,
    provider_runs: List[Dict[str, Any]],
) -> RunDiagnosticComponent:
    runs = [
        run for run in provider_runs
        if isinstance(run, dict) and run.get("data_type") == data_type
    ]
    if not runs:
        return _component(key, label, "unknown", f"{label}未记录诊断信息")

    successes = [run for run in runs if run.get("success") is True]
    failures = [run for run in runs if run.get("success") is False]
    last_run = runs[-1]
    if successes:
        success_run = successes[-1]
        provider = success_run.get("provider") or "unknown"
        record_count = success_run.get("record_count")
        details = {
            "provider": provider,
            "attempts": len(runs),
            "record_count": record_count,
            "fallback_to": next(
                (run.get("fallback_to") for run in failures if run.get("fallback_to")),
                None,
            ),
        }
        details = {key: value for key, value in details.items() if value is not None}
        if failures:
            return _component(
                key,
                label,
                "degraded",
                f"{label}{provider} 成功，前置数据源失败后已继续",
                details,
            )
        return _component(
            key,
            label,
            "ok",
            f"{label}{provider} 成功",
            details,
        )

    message = (
        last_run.get("error_message_sanitized")
        or last_run.get("error_type")
        or "所有数据源尝试失败"
    )
    return _component(
        key,
        label,
        "failed",
        f"{label}失败：{message}",
        {
            "attempts": len(runs),
            "provider": last_run.get("provider"),
            "error_type": last_run.get("error_type"),
        },
    )


def _news_component(context_snapshot: Dict[str, Any], raw_result: Dict[str, Any]) -> RunDiagnosticComponent:
    label = "新闻搜索"
    input_block = _analysis_input_block(context_snapshot, "news")
    input_message = _analysis_input_status_message(input_block)
    has_retrieval_news = "news_retrieval_content" in context_snapshot
    has_snapshot_news = has_retrieval_news or "news_content" in context_snapshot
    news_result_count = context_snapshot.get("news_result_count")
    if isinstance(news_result_count, int):
        if news_result_count > 0:
            if input_message:
                return _component(
                    "news",
                    label,
                    "degraded",
                    f"新闻检索返回 {news_result_count} 条结果，但新闻{input_message}；报告页相关资讯可能来自后续检索或历史持久化",
                    {
                        "record_count": news_result_count,
                        "analysis_input_block": "news",
                        "analysis_input_status": input_block.get("status"),
                        "analysis_input_missing_reasons": _list_text(
                            input_block.get("missing_reasons")
                        ),
                        "evidence_scope": "retrieval_vs_analysis_input",
                    },
                )
            return _component(
                "news",
                label,
                "ok",
                f"新闻检索返回 {news_result_count} 条结果",
                {"record_count": news_result_count},
            )
        return _component("news", label, "degraded", "新闻搜索无结果", {"record_count": 0})
    if input_message:
        return _component(
            "news",
            label,
            "unknown",
            f"新闻{input_message}；报告页相关资讯可能来自后续检索或历史持久化",
            {
                "analysis_input_block": "news",
                "analysis_input_status": input_block.get("status"),
                "analysis_input_missing_reasons": _list_text(
                    input_block.get("missing_reasons")
                ),
                "evidence_scope": "analysis_input_only",
            },
        )
    if has_snapshot_news and not has_retrieval_news:
        return _component("news", label, "unknown", "新闻检索未记录原始证据，可能未尝试或未启用")
    return _component("news", label, "unknown", "新闻搜索未记录诊断信息")


def _llm_component(diagnostics: Dict[str, Any], raw_result: Dict[str, Any]) -> RunDiagnosticComponent:
    label = "LLM"
    runs = [
        run for run in _as_list(diagnostics.get("llm_runs"))
        if isinstance(run, dict)
    ]
    if runs:
        successes = [run for run in runs if run.get("success") is True]
        failures = [run for run in runs if run.get("success") is False]
        last_run = runs[-1]
        if successes:
            success_run = successes[-1]
            model = success_run.get("model") or raw_result.get("model_used") or "unknown"
            status = "degraded" if failures or success_run.get("fallback_model") else "ok"
            message = f"LLM {model} 成功"
            if status == "degraded":
                message = f"LLM {model} 成功，期间发生过失败或模型切换"
            return _component(
                "llm",
                label,
                status,
                message,
                {
                    "model": model,
                    "tokens": success_run.get("tokens"),
                    "duration_ms": success_run.get("duration_ms"),
                    "fallback_model": success_run.get("fallback_model"),
                },
            )
        return _component(
            "llm",
            label,
            "failed",
            f"LLM 失败：{last_run.get('error_message_sanitized') or last_run.get('error_type') or '未知错误'}",
            {"model": last_run.get("model"), "error_type": last_run.get("error_type")},
        )

    if raw_result:
        if raw_result.get("success") is False:
            return _component(
                "llm",
                label,
                "failed",
                f"LLM 失败：{sanitize_diagnostic_text(raw_result.get('error_message')) or '未知错误'}",
            )
        model = raw_result.get("model_used")
        if model:
            return _component("llm", label, "ok", f"LLM {model} 成功", {"model": model})
        if raw_result.get("analysis_summary"):
            return _component("llm", label, "ok", "LLM 成功，模型未记录")
    return _component("llm", label, "unknown", "LLM 未记录诊断信息")


def _notification_component(diagnostics: Dict[str, Any]) -> RunDiagnosticComponent:
    label = "通知"
    runs = [
        run for run in _as_list(diagnostics.get("notification_runs"))
        if isinstance(run, dict)
    ]
    if not runs:
        return _component("notification", label, "unknown", "通知结果未记录")

    skipped = [run for run in runs if run.get("status") in {"skipped", "not_configured"}]
    successes = [run for run in runs if run.get("success") is True]
    failures = [run for run in runs if run.get("success") is False and run not in skipped]
    channels = [run.get("channel") for run in runs if run.get("channel")]
    if successes and failures:
        return _component(
            "notification",
            label,
            "degraded",
            "部分通知渠道失败，其余渠道已发送",
            {"channels": channels, "failed": [run.get("channel") for run in failures]},
        )
    if successes:
        return _component(
            "notification",
            label,
            "ok",
            "通知发送成功",
            {"channels": channels},
        )
    if skipped and not failures:
        status = "not_configured" if any(run.get("status") == "not_configured" for run in skipped) else "skipped"
        return _component(
            "notification",
            label,
            status,
            "通知未配置或本次跳过",
            {"channels": channels},
        )
    last_failure = failures[-1] if failures else runs[-1]
    return _component(
        "notification",
        label,
        "failed",
        f"通知失败：{last_failure.get('error_message_sanitized') or last_failure.get('status') or '未知错误'}",
        {"channels": channels},
    )


def _history_component(
    diagnostics: Dict[str, Any],
    report_saved: Optional[bool],
) -> RunDiagnosticComponent:
    label = "历史保存"
    runs = [
        run for run in _as_list(diagnostics.get("history_runs"))
        if isinstance(run, dict)
    ]
    if runs:
        last_run = runs[-1]
        if last_run.get("report_saved") is True:
            return _component(
                "history",
                label,
                "ok",
                "报告历史已保存",
                {"analysis_history_id": last_run.get("analysis_history_id")},
            )
        return _component(
            "history",
            label,
            "failed",
            f"报告历史保存失败：{last_run.get('error_message_sanitized') or '未知错误'}",
        )
    if report_saved is True:
        return _component("history", label, "ok", "报告历史已保存")
    if report_saved is False:
        return _component("history", label, "failed", "报告历史保存失败")
    return _component("history", label, "unknown", "历史保存未记录诊断信息")


def _data_quality_component(diagnostics: Dict[str, Any]) -> RunDiagnosticComponent:
    """Project typed validation evidence into the user-facing run summary."""
    evidence = [
        item
        for item in _as_list(diagnostics.get("data_quality_evidence"))
        if isinstance(item, dict)
    ]
    if not evidence:
        return _component(
            "data_quality",
            "数据质量",
            "unknown",
            "未记录数据质量校验证据",
        )
    rejected = [item for item in evidence if item.get("rejected") is True]
    findings = [
        item
        for item in evidence
        if item.get("severity") in {"warn", "reject"}
    ]
    codes = sorted(
        {
            str(issue.get("code"))
            for item in findings
            for issue in _as_list(item.get("issues"))
            if isinstance(issue, dict) and issue.get("code")
        }
    )[:12]
    details = {
        "schema_version": evidence[-1].get("schema_version"),
        "evidence_count": len(evidence),
        "rejected_count": len(rejected),
        "reason_codes": codes,
    }
    if rejected:
        return _component(
            "data_quality",
            "数据质量",
            "degraded",
            "数据质量校验拒绝了一个或多个候选数据源，并继续执行既有降级链",
            details,
        )
    if findings:
        return _component(
            "data_quality",
            "数据质量",
            "degraded",
            "数据质量校验发现警告，证据已传递到分析上下文",
            details,
        )
    return _component(
        "data_quality",
        "数据质量",
        "ok",
        "数据质量校验未发现问题",
        details,
    )


def build_run_diagnostic_summary(
    *,
    context_snapshot: Optional[Any] = None,
    raw_result: Optional[Any] = None,
    report_saved: Optional[bool] = None,
    query_id: Optional[str] = None,
    stock_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a user-facing diagnostic summary from persisted or in-memory evidence."""
    snapshot = _as_dict(context_snapshot)
    raw = _as_dict(raw_result)
    diagnostics = _as_dict(snapshot.get("diagnostics"))
    provider_runs = [
        run for run in _as_list(diagnostics.get("provider_runs"))
        if isinstance(run, dict)
    ]
    llm_runs = [
        run for run in _as_list(diagnostics.get("llm_runs"))
        if isinstance(run, dict)
    ]

    daily_data_component = _provider_component(
        key="daily_data",
        label="日线数据",
        data_type="daily_data",
        provider_runs=provider_runs,
    )
    components = {
        "realtime_quote": _provider_component(
            key="realtime_quote",
            label="实时行情",
            data_type="realtime_quote",
            provider_runs=provider_runs,
        ),
        "daily_data": _reconcile_daily_provider_with_analysis_input(
            daily_data_component,
            snapshot,
        ),
        "news": _news_component(snapshot, raw),
        "data_quality": _data_quality_component(diagnostics),
        "llm": _llm_component(diagnostics, raw),
        "notification": _notification_component(diagnostics),
        "history": _history_component(diagnostics, report_saved),
    }

    has_evidence = bool(snapshot or raw or diagnostics or report_saved is not None)
    has_core_diagnostic_runs = bool(provider_runs or llm_runs)
    if not has_evidence or not diagnostics:
        status = "unknown"
    elif components["llm"].status == "failed" or components["history"].status == "failed":
        status = "failed"
    elif any(component.status in {"failed", "degraded"} for component in components.values()):
        status = "degraded"
    elif all(component.status == "unknown" for component in components.values()):
        status = "unknown"
    elif not has_core_diagnostic_runs:
        status = "unknown"
    else:
        status = "normal"

    if status == "unknown":
        reason = "旧报告或诊断证据不足，无法判断本次运行状态"
    else:
        reason = next(
            (
                component.message
                for component in components.values()
                if component.status == "failed"
            ),
            next(
                (
                    component.message
                    for component in components.values()
                    if component.status == "degraded"
                ),
                _SUMMARY_STATUS_LABELS[status],
            ),
        )

    trace_id = diagnostics.get("trace_id") or snapshot.get("trace_id") or raw.get("trace_id")
    resolved_query_id = query_id or diagnostics.get("query_id") or snapshot.get("query_id") or raw.get("query_id")
    resolved_stock_code = (
        stock_code
        or diagnostics.get("stock_code")
        or snapshot.get("stock_code")
        or raw.get("code")
        or raw.get("stock_code")
    )

    return RunDiagnosticSummary(
        trace_id=trace_id,
        task_id=diagnostics.get("task_id"),
        query_id=resolved_query_id,
        stock_code=resolved_stock_code,
        trigger_source=diagnostics.get("trigger_source") or snapshot.get("trigger_source"),
        status=status,
        status_label=_SUMMARY_STATUS_LABELS[status],
        reason=reason,
        components=components,
    ).to_dict()


def format_copyable_diagnostics(summary: Dict[str, Any]) -> str:
    """Format a sanitized plain-text diagnostic payload for issue reports."""
    components = _as_dict(summary.get("components"))

    def _component_line(key: str) -> str:
        component = _as_dict(components.get(key))
        message = sanitize_diagnostic_text(component.get("message"), max_length=160) or "unknown"
        return f"{key}: {component.get('status', 'unknown')} - {message}"

    lines = [
        f"trace_id: {summary.get('trace_id') or 'unknown'}",
        f"query_id: {summary.get('query_id') or 'unknown'}",
        f"stock_code: {summary.get('stock_code') or 'unknown'}",
        f"trigger_source: {summary.get('trigger_source') or 'unknown'}",
        f"data_status: {summary.get('status', 'unknown')}",
        _component_line("realtime_quote"),
        _component_line("daily_data"),
        _component_line("news"),
        _component_line("data_quality"),
        _component_line("llm"),
        _component_line("notification"),
        _component_line("history"),
        f"reason: {sanitize_diagnostic_text(summary.get('reason'), max_length=160) or 'unknown'}",
    ]
    return "\n".join(lines)
