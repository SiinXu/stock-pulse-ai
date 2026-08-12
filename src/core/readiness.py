# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Structured readiness / self-check results for data, LLM, and queue.

This module is the single composition point for pre-run and operator readiness
projections. It reuses existing observational probes (setup status, data-provider
runtime status, generation-backend cheap status, task-queue stats, local-runtime
detect) rather than inventing parallel health logic.

Hard rules:
- Failures are explicit: probe exceptions and timeouts never become ``ok``.
- Checks are side-effect free (no config writes, no model smoke unless a caller
  injects one).
- Each check runs under a bounded timeout so readiness never stalls startup.
- Startup paths must not call :func:`build_readiness_report` automatically;
  this API is on-demand only.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "readiness_v1"
READINESS_STATUSES = frozenset({"ok", "degraded", "failed"})

DEFAULT_CHECK_TIMEOUT_SECONDS = 1.0
MIN_CHECK_TIMEOUT_SECONDS = 0.1
MAX_CHECK_TIMEOUT_SECONDS = 5.0

_QUEUE_DEGRADED_PENDING_RATIO = 3.0
_QUEUE_FAILED_PENDING_RATIO = 10.0

CheckProbe = Callable[[], "ReadinessCheck"]


@dataclass(frozen=True)
class ReadinessCheck:
    """One structured readiness dimension."""

    key: str
    status: str
    reason_code: str
    reason: str
    suggestion: Optional[str] = None
    required: bool = True
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    timed_out: bool = False

    def __post_init__(self) -> None:
        status = str(self.status or "").strip().lower()
        if status not in READINESS_STATUSES:
            raise ValueError(f"unsupported readiness status: {self.status!r}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "key", str(self.key or "").strip())
        object.__setattr__(
            self,
            "reason_code",
            str(self.reason_code or "unknown").strip() or "unknown",
        )
        object.__setattr__(self, "reason", str(self.reason or "").strip() or self.reason_code)
        if self.suggestion is not None:
            suggestion = str(self.suggestion).strip()
            object.__setattr__(self, "suggestion", suggestion or None)
        if self.details is None:
            object.__setattr__(self, "details", {})

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if not payload.get("details"):
            payload.pop("details", None)
        if payload.get("suggestion") is None:
            payload.pop("suggestion", None)
        if payload.get("duration_ms") is None:
            payload.pop("duration_ms", None)
        if not payload.get("timed_out"):
            payload.pop("timed_out", None)
        return payload


@dataclass(frozen=True)
class ReadinessReport:
    """Aggregate readiness snapshot for diagnostics and first-run consumers."""

    schema_version: str
    status: str
    generated_at: str
    checks: List[ReadinessCheck]
    summary: str
    partial: bool = False
    timeout_seconds: float = DEFAULT_CHECK_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        status = str(self.status or "").strip().lower()
        if status not in READINESS_STATUSES:
            raise ValueError(f"unsupported readiness status: {self.status!r}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "schema_version", str(self.schema_version or SCHEMA_VERSION))
        object.__setattr__(self, "checks", list(self.checks or []))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "generated_at": self.generated_at,
            "summary": self.summary,
            "partial": bool(self.partial),
            "timeout_seconds": float(self.timeout_seconds),
            "checks": [check.to_dict() for check in self.checks],
        }


def parse_readiness_check_timeout_seconds(
    raw: Any,
    *,
    default: float = DEFAULT_CHECK_TIMEOUT_SECONDS,
) -> float:
    """Parse and clamp the per-check readiness timeout."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value != value:  # NaN
        return default
    return max(MIN_CHECK_TIMEOUT_SECONDS, min(float(value), MAX_CHECK_TIMEOUT_SECONDS))


def resolve_readiness_check_timeout_seconds(
    config: Any | None = None,
    *,
    env_map: Mapping[str, Any] | None = None,
) -> float:
    """Resolve timeout from Config, env map, or the shared default."""
    if config is not None:
        attr = getattr(config, "readiness_check_timeout_seconds", None)
        if attr is not None:
            return parse_readiness_check_timeout_seconds(attr)
    if env_map is not None and "READINESS_CHECK_TIMEOUT_SECONDS" in env_map:
        return parse_readiness_check_timeout_seconds(
            env_map.get("READINESS_CHECK_TIMEOUT_SECONDS")
        )
    try:
        from src.config import get_config

        cfg = get_config()
        return parse_readiness_check_timeout_seconds(
            getattr(cfg, "readiness_check_timeout_seconds", DEFAULT_CHECK_TIMEOUT_SECONDS)
        )
    except Exception as exc:  # broad-exception: fallback_recorded - keep readiness usable offline
        log_safe_exception(
            logger,
            "Readiness timeout config lookup failed; using default",
            exc,
            error_code="readiness_timeout_config_lookup_failed",
            level=logging.DEBUG,
        )
        return DEFAULT_CHECK_TIMEOUT_SECONDS


def aggregate_readiness_status(checks: Sequence[ReadinessCheck]) -> str:
    """Aggregate check statuses without fail-open defaults.

    - Any **required** ``failed`` check → overall ``failed``
    - Else any ``failed`` or ``degraded`` check → overall ``degraded``
    - Else ``ok`` (empty check list is ``failed`` — never invent readiness)
    """
    items = list(checks or [])
    if not items:
        return "failed"
    if any(check.required and check.status == "failed" for check in items):
        return "failed"
    if any(check.status in {"failed", "degraded"} for check in items):
        return "degraded"
    return "ok"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_text(value: Any, *, max_length: int = 240) -> str:
    text = sanitize_diagnostic_text(value, max_length=max_length)
    if text is None:
        return ""
    return str(text)


def _run_check_with_timeout(
    probe: CheckProbe,
    *,
    key: str,
    required: bool,
    timeout_seconds: float,
) -> ReadinessCheck:
    """Execute one probe under a hard timeout; never promote failures to ok."""
    started = time.perf_counter()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"readiness_{key}")
    try:
        future = executor.submit(probe)
        try:
            result = future.result(timeout=timeout_seconds)
        except FuturesTimeoutError:
            future.cancel()
            duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
            return ReadinessCheck(
                key=key,
                status="failed" if required else "degraded",
                reason_code="check_timeout",
                reason=(
                    f"Readiness check {key!r} exceeded timeout "
                    f"({timeout_seconds:.2f}s) and was aborted."
                ),
                suggestion=(
                    "Retry later, or raise READINESS_CHECK_TIMEOUT_SECONDS slightly "
                    "if probes are legitimately slow. Do not treat a timeout as ready."
                ),
                required=required,
                details={"timeout_seconds": timeout_seconds},
                duration_ms=duration_ms,
                timed_out=True,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - fail closed
            duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
            log_safe_exception(
                logger,
                "Readiness check raised",
                exc,
                error_code="readiness_check_raised",
                context={"check_key": key},
            )
            return ReadinessCheck(
                key=key,
                status="failed" if required else "degraded",
                reason_code="check_exception",
                reason=_safe_text(exc) or f"Readiness check {key!r} raised an exception.",
                suggestion=(
                    "Inspect server logs for readiness_check_raised and fix the underlying dependency."
                ),
                required=required,
                details={"exception_type": type(exc).__name__},
                duration_ms=duration_ms,
                timed_out=False,
            )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
    if not isinstance(result, ReadinessCheck):
        return ReadinessCheck(
            key=key,
            status="failed" if required else "degraded",
            reason_code="invalid_check_result",
            reason=f"Readiness probe for {key!r} returned a non-ReadinessCheck value.",
            suggestion="Fix the readiness probe implementation; result type must be ReadinessCheck.",
            required=required,
            details={"result_type": type(result).__name__},
            duration_ms=duration_ms,
            timed_out=False,
        )

    status = result.status
    if status not in READINESS_STATUSES:
        status = "failed" if required else "degraded"
    return ReadinessCheck(
        key=result.key or key,
        status=status,
        reason_code=result.reason_code,
        reason=result.reason,
        suggestion=result.suggestion,
        required=bool(result.required if result.required is not None else required),
        details=dict(result.details or {}),
        duration_ms=result.duration_ms if result.duration_ms is not None else duration_ms,
        timed_out=bool(result.timed_out),
    )


def project_setup_check_to_readiness(setup_check: Mapping[str, Any]) -> ReadinessCheck:
    """Project one SystemConfig setup-status check into the readiness schema."""
    key = str(setup_check.get("key") or "setup").strip() or "setup"
    required = bool(setup_check.get("required"))
    raw_status = str(setup_check.get("status") or "").strip().lower()
    message = _safe_text(setup_check.get("message")) or f"Setup check {key}"
    next_step = setup_check.get("next_step")
    suggestion = _safe_text(next_step) if next_step not in (None, "") else None

    if raw_status in {"configured", "inherited"}:
        status = "ok"
        reason_code = f"setup_{raw_status}"
    elif raw_status == "optional":
        status = "ok"
        reason_code = "setup_optional"
    elif raw_status == "needs_action":
        status = "failed" if required else "degraded"
        reason_code = "setup_needs_action"
    else:
        status = "failed" if required else "degraded"
        reason_code = "setup_status_unknown"

    return ReadinessCheck(
        key=key,
        status=status,
        reason_code=reason_code,
        reason=message,
        suggestion=suggestion,
        required=required,
        details={
            "setup_status": raw_status or None,
            "category": setup_check.get("category"),
            "title": setup_check.get("title"),
        },
    )


def check_data_providers(
    *,
    status_payload: Mapping[str, Any] | None = None,
    status_factory: Callable[[], Mapping[str, Any]] | None = None,
) -> ReadinessCheck:
    """Project live data-provider runtime status into readiness (no network writes)."""
    try:
        payload = (
            dict(status_payload)
            if status_payload is not None
            else dict((status_factory or _default_data_provider_status)())
        )
    except Exception as exc:  # broad-exception: fallback_recorded - fail closed
        log_safe_exception(
            logger,
            "Data provider readiness probe failed",
            exc,
            error_code="readiness_data_providers_probe_failed",
        )
        return ReadinessCheck(
            key="data_providers",
            status="failed",
            reason_code="data_provider_probe_failed",
            reason=_safe_text(exc) or "Data provider readiness probe failed.",
            suggestion=(
                "Start the API/analysis process so DataFetcherManager is live, "
                "then retry readiness."
            ),
            required=True,
            details={"exception_type": type(exc).__name__},
        )

    source_state = str(payload.get("source_state") or "").strip().lower()
    error_code = payload.get("error_code")
    error_message = _safe_text(payload.get("error_message"))
    providers = list(payload.get("providers") or [])
    markets = list(payload.get("markets") or [])

    if source_state in {"not_initialized", "error"} or payload.get("error_code"):
        return ReadinessCheck(
            key="data_providers",
            status="failed",
            reason_code=str(error_code or f"data_source_{source_state or 'error'}"),
            reason=error_message
            or "Data provider runtime is unavailable; readiness cannot claim data is ready.",
            suggestion=(
                "Ensure the analysis/API process has initialized DataFetcherManager, "
                "then open Data Sources Hub or retry this check."
            ),
            required=True,
            details={
                "source_state": source_state or None,
                "partial": bool(payload.get("partial")),
                "provider_count": len(providers),
            },
        )

    if not providers:
        return ReadinessCheck(
            key="data_providers",
            status="failed",
            reason_code="no_providers_registered",
            reason="No market-data providers are registered in the live runtime.",
            suggestion="Verify data_provider registration and process composition root binding.",
            required=True,
            details={"source_state": source_state or None, "provider_count": 0},
        )

    unavailable_markets = [
        str(item.get("market") or "")
        for item in markets
        if str(item.get("quality") or "").lower() == "unavailable"
    ]
    degraded_markets = [
        str(item.get("market") or "")
        for item in markets
        if str(item.get("quality") or "").lower() == "degraded"
    ]
    available_providers = [
        item
        for item in providers
        if item.get("available") is True
        or str(item.get("health_status") or "").lower()
        in {"ok", "healthy", "unknown", "not_tested", ""}
    ]
    explicitly_down = [
        item
        for item in providers
        if item.get("available") is False
        or str(item.get("health_status") or "").lower()
        in {"unavailable", "circuit_open", "failed", "error"}
    ]

    if unavailable_markets and len(unavailable_markets) >= max(1, len(markets)):
        return ReadinessCheck(
            key="data_providers",
            status="failed",
            reason_code="all_markets_unavailable",
            reason="Every overview market chain currently lacks an eligible provider.",
            suggestion="Inspect provider health, credentials, and circuit breakers in Data Sources Hub.",
            required=True,
            details={
                "source_state": source_state or None,
                "unavailable_markets": unavailable_markets,
                "provider_count": len(providers),
                "explicitly_down_count": len(explicitly_down),
            },
        )

    if unavailable_markets or degraded_markets or (
        explicitly_down and len(explicitly_down) == len(providers)
    ):
        if explicitly_down and len(explicitly_down) == len(providers):
            return ReadinessCheck(
                key="data_providers",
                status="failed",
                reason_code="all_providers_unavailable",
                reason="All registered providers report unavailable or open circuits.",
                suggestion="Restore at least one baseline provider before relying on market data.",
                required=True,
                details={
                    "source_state": source_state or None,
                    "provider_count": len(providers),
                    "explicitly_down_count": len(explicitly_down),
                    "unavailable_markets": unavailable_markets,
                    "degraded_markets": degraded_markets,
                },
            )
        return ReadinessCheck(
            key="data_providers",
            status="degraded",
            reason_code="partial_provider_degradation",
            reason="Some markets or providers are degraded or unavailable; others remain usable.",
            suggestion=(
                "Review degraded markets in Data Sources Hub; baseline scrapers may still serve dry-run paths."
            ),
            required=True,
            details={
                "source_state": source_state or None,
                "provider_count": len(providers),
                "available_provider_count": len(available_providers),
                "unavailable_markets": unavailable_markets,
                "degraded_markets": degraded_markets,
            },
        )

    return ReadinessCheck(
        key="data_providers",
        status="ok",
        reason_code="providers_ready",
        reason="Live data-provider runtime is initialized with registered providers.",
        suggestion=None,
        required=True,
        details={
            "source_state": source_state or "ok",
            "provider_count": len(providers),
            "market_count": len(markets),
            "partial": bool(payload.get("partial")),
        },
    )


def check_llm_runtime(
    *,
    setup_status: Mapping[str, Any] | None = None,
    setup_status_factory: Callable[[], Mapping[str, Any]] | None = None,
    generation_status: Mapping[str, Any] | None = None,
    generation_status_factory: Callable[[], Mapping[str, Any]] | None = None,
) -> ReadinessCheck:
    """Compose LLM readiness from setup projection + cheap generation backend status."""
    try:
        setup = (
            dict(setup_status)
            if setup_status is not None
            else dict((setup_status_factory or _default_setup_status)())
        )
    except Exception as exc:  # broad-exception: fallback_recorded - fail closed
        log_safe_exception(
            logger,
            "LLM setup readiness probe failed",
            exc,
            error_code="readiness_llm_setup_probe_failed",
        )
        return ReadinessCheck(
            key="llm",
            status="failed",
            reason_code="llm_setup_probe_failed",
            reason=_safe_text(exc) or "Failed to load setup status for LLM readiness.",
            suggestion="Verify SystemConfigService can read saved/runtime config, then retry.",
            required=True,
            details={"exception_type": type(exc).__name__},
        )

    checks = {
        str(item.get("key") or ""): item
        for item in list(setup.get("checks") or [])
        if isinstance(item, Mapping)
    }
    primary = checks.get("llm_primary") or {}
    primary_status = str(primary.get("status") or "").strip().lower()
    primary_message = _safe_text(primary.get("message")) or "Primary model check unavailable."
    primary_next = _safe_text(primary.get("next_step")) or None

    gen_payload: Mapping[str, Any] | None = None
    gen_error: Optional[str] = None
    try:
        gen_payload = (
            dict(generation_status)
            if generation_status is not None
            else dict((generation_status_factory or _default_generation_backend_status)())
        )
    except Exception as exc:  # broad-exception: fallback_recorded - record, do not invent ok
        log_safe_exception(
            logger,
            "Generation backend readiness probe failed",
            exc,
            error_code="readiness_generation_backend_probe_failed",
        )
        gen_error = _safe_text(exc) or type(exc).__name__

    primary_backend = None
    primary_available: Optional[bool] = None
    if gen_payload is not None:
        primary_block = gen_payload.get("primary")
        if isinstance(primary_block, Mapping):
            primary_backend = primary_block.get("backend_id")
            if "available" in primary_block:
                primary_available = bool(primary_block.get("available"))
            health = str(primary_block.get("health_status") or "").strip().lower()
            if health in {"failed", "error", "unavailable"}:
                primary_available = False

    details: Dict[str, Any] = {
        "setup_primary_status": primary_status or None,
        "primary_backend_id": primary_backend,
        "primary_available": primary_available,
        "generation_probe_error": gen_error,
        "ready_for_smoke": setup.get("ready_for_smoke"),
    }

    if gen_error and primary_status in {"configured", "inherited"}:
        return ReadinessCheck(
            key="llm",
            status="failed",
            reason_code="generation_backend_probe_failed",
            reason=(
                "Primary model appears configured, but generation-backend status "
                f"could not be read: {gen_error}"
            ),
            suggestion="Inspect generation backend configuration and retry readiness.",
            required=True,
            details=details,
        )

    if primary_status in {"configured", "inherited"}:
        if primary_available is False:
            return ReadinessCheck(
                key="llm",
                status="failed",
                reason_code="primary_backend_unavailable",
                reason=(
                    "Configured primary generation backend is unavailable"
                    + (f" ({primary_backend})." if primary_backend else ".")
                ),
                suggestion=(
                    primary_next
                    or "Fix the primary generation backend (CLI on PATH / API route) before full AI analysis."
                ),
                required=True,
                details=details,
            )
        return ReadinessCheck(
            key="llm",
            status="ok",
            reason_code="primary_model_configured",
            reason=primary_message,
            suggestion=primary_next,
            required=True,
            details=details,
        )

    if primary_status == "needs_action":
        return ReadinessCheck(
            key="llm",
            status="degraded",
            reason_code="primary_model_missing",
            reason=primary_message,
            suggestion=(
                primary_next
                or "Configure a primary model, apply a local Ollama profile, or use data-only dry-run."
            ),
            required=True,
            details=details,
        )

    if primary_status == "optional":
        return ReadinessCheck(
            key="llm",
            status="ok",
            reason_code="primary_model_optional",
            reason=primary_message,
            suggestion=primary_next,
            required=True,
            details=details,
        )

    return ReadinessCheck(
        key="llm",
        status="failed",
        reason_code="primary_model_status_unknown",
        reason=primary_message or "Primary LLM readiness could not be determined.",
        suggestion=primary_next or "Open setup status and configure a primary model.",
        required=True,
        details=details,
    )


def check_task_queue(
    *,
    queue: Any | None = None,
    queue_factory: Callable[[], Any] | None = None,
) -> ReadinessCheck:
    """Observe task-queue capacity without mutating enqueue/worker state."""
    try:
        live = queue if queue is not None else (queue_factory or _default_task_queue)()
    except Exception as exc:  # broad-exception: fallback_recorded - fail closed
        log_safe_exception(
            logger,
            "Task queue readiness resolve failed",
            exc,
            error_code="readiness_task_queue_resolve_failed",
        )
        return ReadinessCheck(
            key="task_queue",
            status="failed",
            reason_code="task_queue_resolve_failed",
            reason=_safe_text(exc) or "Task queue could not be resolved.",
            suggestion="Ensure AnalysisTaskQueue can initialize, then retry readiness.",
            required=True,
            details={"exception_type": type(exc).__name__},
        )

    if live is None:
        return ReadinessCheck(
            key="task_queue",
            status="failed",
            reason_code="task_queue_missing",
            reason="Task queue instance is missing; async analysis cannot be accepted.",
            suggestion="Start the API process that owns AnalysisTaskQueue.",
            required=True,
        )

    if bool(getattr(live, "_shutdown", False)):
        return ReadinessCheck(
            key="task_queue",
            status="failed",
            reason_code="task_queue_shutdown",
            reason="Task queue is shut down and is not accepting work.",
            suggestion="Restart the API/worker process to restore the task queue.",
            required=True,
        )

    try:
        max_workers = int(getattr(live, "max_workers", 0) or 0)
        stats = dict(live.get_task_stats()) if hasattr(live, "get_task_stats") else {}
        pending = int(stats.get("pending") or 0)
        processing = int(stats.get("processing") or 0)
    except Exception as exc:  # broad-exception: fallback_recorded - fail closed
        log_safe_exception(
            logger,
            "Task queue stats probe failed",
            exc,
            error_code="readiness_task_queue_stats_failed",
        )
        return ReadinessCheck(
            key="task_queue",
            status="failed",
            reason_code="task_queue_stats_failed",
            reason=_safe_text(exc) or "Task queue stats could not be read.",
            suggestion="Inspect AnalysisTaskQueue internals; do not assume capacity is healthy.",
            required=True,
            details={"exception_type": type(exc).__name__},
        )

    if max_workers < 1:
        return ReadinessCheck(
            key="task_queue",
            status="failed",
            reason_code="task_queue_no_workers",
            reason="Task queue reports zero workers; analysis tasks cannot run.",
            suggestion="Set MAX_WORKERS to a positive integer and restart the process.",
            required=True,
            details={"max_workers": max_workers, "stats": stats},
        )

    inflight = pending + processing
    ratio = float(inflight) / float(max_workers)
    details = {
        "max_workers": max_workers,
        "pending": pending,
        "processing": processing,
        "inflight": inflight,
        "inflight_per_worker": round(ratio, 3),
        "stats": stats,
    }

    if ratio >= _QUEUE_FAILED_PENDING_RATIO:
        return ReadinessCheck(
            key="task_queue",
            status="failed",
            reason_code="task_queue_saturated",
            reason=(
                f"Task queue is saturated ({inflight} inflight across "
                f"{max_workers} workers)."
            ),
            suggestion="Wait for drain, cancel stuck tasks, or raise MAX_WORKERS carefully.",
            required=True,
            details=details,
        )

    if ratio >= _QUEUE_DEGRADED_PENDING_RATIO:
        return ReadinessCheck(
            key="task_queue",
            status="degraded",
            reason_code="task_queue_busy",
            reason=f"Task queue is busy ({inflight} inflight across {max_workers} workers).",
            suggestion="New tasks may wait; reduce concurrency or wait for completions.",
            required=True,
            details=details,
        )

    return ReadinessCheck(
        key="task_queue",
        status="ok",
        reason_code="task_queue_ready",
        reason=(
            f"Task queue is accepting work ({max_workers} workers; "
            f"{inflight} inflight)."
        ),
        suggestion=None,
        required=True,
        details=details,
    )


def check_dependencies_from_setup(
    *,
    setup_status: Mapping[str, Any] | None = None,
    setup_status_factory: Callable[[], Mapping[str, Any]] | None = None,
    keys: Sequence[str] = ("storage", "notification", "llm_agent", "stock_list"),
) -> List[ReadinessCheck]:
    """Project selected setup checks into readiness."""
    try:
        setup = (
            dict(setup_status)
            if setup_status is not None
            else dict((setup_status_factory or _default_setup_status)())
        )
    except Exception as exc:  # broad-exception: fallback_recorded - fail closed for required deps
        log_safe_exception(
            logger,
            "Dependency setup readiness probe failed",
            exc,
            error_code="readiness_dependencies_setup_probe_failed",
        )
        return [
            ReadinessCheck(
                key="dependencies",
                status="failed",
                reason_code="dependencies_setup_probe_failed",
                reason=_safe_text(exc) or "Failed to load setup status for dependency checks.",
                suggestion="Verify SystemConfigService and retry readiness.",
                required=True,
                details={"exception_type": type(exc).__name__},
            )
        ]

    by_key = {
        str(item.get("key") or ""): item
        for item in list(setup.get("checks") or [])
        if isinstance(item, Mapping)
    }
    results: List[ReadinessCheck] = []
    for key in keys:
        item = by_key.get(key)
        if item is None:
            required = key in {"storage", "stock_list"}
            results.append(
                ReadinessCheck(
                    key=key,
                    status="failed" if required else "degraded",
                    reason_code="setup_check_missing",
                    reason=f"Setup status did not include check {key!r}.",
                    suggestion="Upgrade the server or inspect SystemConfigService setup projection.",
                    required=required,
                )
            )
            continue
        results.append(project_setup_check_to_readiness(item))
    return results


def _default_data_provider_status() -> Mapping[str, Any]:
    from src.services.data_provider_runtime_status_service import (
        build_data_provider_runtime_status,
    )

    return build_data_provider_runtime_status()


def _default_setup_status() -> Mapping[str, Any]:
    from src.services.system_config_service import SystemConfigService

    return SystemConfigService().get_setup_status()


def _default_generation_backend_status() -> Mapping[str, Any]:
    from src.services.system_config_service import SystemConfigService

    return SystemConfigService().get_generation_backend_status()


def _default_task_queue() -> Any:
    from src.services.task_queue import get_task_queue

    return get_task_queue()


def _summary_for(status: str, checks: Sequence[ReadinessCheck]) -> str:
    failed = [c.key for c in checks if c.status == "failed"]
    degraded = [c.key for c in checks if c.status == "degraded"]
    if status == "ok":
        return "All readiness checks passed."
    if status == "failed":
        focus = failed or degraded
        return "Readiness failed: " + ", ".join(focus)
    if degraded or failed:
        parts = []
        if failed:
            parts.append("failed=" + ",".join(failed))
        if degraded:
            parts.append("degraded=" + ",".join(degraded))
        return "Readiness degraded (" + "; ".join(parts) + ")."
    return "Readiness degraded."


def build_readiness_report(
    *,
    timeout_seconds: float | None = None,
    include_dependency_checks: bool = True,
    data_provider_status: Mapping[str, Any] | None = None,
    data_provider_status_factory: Callable[[], Mapping[str, Any]] | None = None,
    setup_status: Mapping[str, Any] | None = None,
    setup_status_factory: Callable[[], Mapping[str, Any]] | None = None,
    generation_status: Mapping[str, Any] | None = None,
    generation_status_factory: Callable[[], Mapping[str, Any]] | None = None,
    task_queue: Any | None = None,
    task_queue_factory: Callable[[], Any] | None = None,
    config: Any | None = None,
) -> ReadinessReport:
    """Run structured readiness checks under per-check timeouts.

    Not for process startup. Callers must invoke this explicitly.
    """
    effective_timeout = (
        parse_readiness_check_timeout_seconds(timeout_seconds)
        if timeout_seconds is not None
        else resolve_readiness_check_timeout_seconds(config)
    )

    shared_setup: Mapping[str, Any] | None = setup_status
    if shared_setup is None and setup_status_factory is not None:
        try:
            shared_setup = dict(setup_status_factory())
        except Exception as exc:  # broad-exception: fallback_recorded - per-check fail-closed
            log_safe_exception(
                logger,
                "Shared setup status load failed for readiness",
                exc,
                error_code="readiness_shared_setup_failed",
            )
            shared_setup = None

    if shared_setup is None and setup_status is None and setup_status_factory is None:
        try:
            shared_setup = dict(_default_setup_status())
        except Exception as exc:  # broad-exception: fallback_recorded - per-check fail-closed
            log_safe_exception(
                logger,
                "Default setup status load failed for readiness",
                exc,
                error_code="readiness_default_setup_failed",
            )
            shared_setup = None

    def _data_probe() -> ReadinessCheck:
        return check_data_providers(
            status_payload=data_provider_status,
            status_factory=data_provider_status_factory,
        )

    def _llm_probe() -> ReadinessCheck:
        return check_llm_runtime(
            setup_status=shared_setup,
            setup_status_factory=None if shared_setup is not None else setup_status_factory,
            generation_status=generation_status,
            generation_status_factory=generation_status_factory,
        )

    def _queue_probe() -> ReadinessCheck:
        return check_task_queue(
            queue=task_queue,
            queue_factory=task_queue_factory,
        )

    probes: List[tuple[str, bool, CheckProbe]] = [
        ("data_providers", True, _data_probe),
        ("llm", True, _llm_probe),
        ("task_queue", True, _queue_probe),
    ]

    checks: List[ReadinessCheck] = []
    for key, required, probe in probes:
        checks.append(
            _run_check_with_timeout(
                probe,
                key=key,
                required=required,
                timeout_seconds=effective_timeout,
            )
        )

    if include_dependency_checks:
        def _deps_probe() -> ReadinessCheck:
            items = check_dependencies_from_setup(
                setup_status=shared_setup,
                setup_status_factory=None if shared_setup is not None else setup_status_factory,
            )
            return ReadinessCheck(
                key="dependencies_bundle",
                status=aggregate_readiness_status(items),
                reason_code="dependencies_bundle",
                reason="dependency bundle",
                required=any(item.required for item in items),
                details={"items": [item.to_dict() for item in items]},
            )

        bundled = _run_check_with_timeout(
            _deps_probe,
            key="dependencies_bundle",
            required=True,
            timeout_seconds=effective_timeout,
        )
        if bundled.timed_out or bundled.reason_code in {
            "check_exception",
            "invalid_check_result",
        }:
            checks.append(
                ReadinessCheck(
                    key="dependencies",
                    status=bundled.status,
                    reason_code=bundled.reason_code,
                    reason=bundled.reason,
                    suggestion=bundled.suggestion,
                    required=True,
                    details=dict(bundled.details or {}),
                    duration_ms=bundled.duration_ms,
                    timed_out=bundled.timed_out,
                )
            )
        else:
            raw_items = list((bundled.details or {}).get("items") or [])
            if not raw_items:
                checks.append(
                    ReadinessCheck(
                        key="dependencies",
                        status="failed",
                        reason_code="dependencies_empty",
                        reason="Dependency readiness bundle returned no checks.",
                        suggestion="Inspect setup status projection.",
                        required=True,
                        duration_ms=bundled.duration_ms,
                    )
                )
            else:
                for item in raw_items:
                    try:
                        checks.append(
                            ReadinessCheck(
                                key=str(item.get("key") or "dependency"),
                                status=str(item.get("status") or "failed"),
                                reason_code=str(item.get("reason_code") or "unknown"),
                                reason=str(item.get("reason") or "Dependency check failed."),
                                suggestion=item.get("suggestion"),
                                required=bool(item.get("required", False)),
                                details=dict(item.get("details") or {}),
                                duration_ms=bundled.duration_ms,
                                timed_out=False,
                            )
                        )
                    except Exception as exc:  # broad-exception: fallback_recorded - fail closed item
                        checks.append(
                            ReadinessCheck(
                                key=str((item or {}).get("key") or "dependency"),
                                status="failed",
                                reason_code="dependency_item_invalid",
                                reason=_safe_text(exc) or "Invalid dependency readiness item.",
                                required=True,
                                duration_ms=bundled.duration_ms,
                            )
                        )

    overall = aggregate_readiness_status(checks)
    partial = any(check.timed_out for check in checks) or any(
        check.reason_code.endswith("_failed") or check.reason_code.endswith("_exception")
        for check in checks
    )
    if not checks:
        overall = "failed"
        partial = True

    return ReadinessReport(
        schema_version=SCHEMA_VERSION,
        status=overall,
        generated_at=_utc_now_iso(),
        checks=checks,
        summary=_summary_for(overall, checks),
        partial=partial,
        timeout_seconds=effective_timeout,
    )


def readiness_report_to_diagnostic_components(
    report: ReadinessReport | Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Project a readiness report into run-diagnostics-style component dicts."""
    if isinstance(report, ReadinessReport):
        checks = report.checks
    else:
        checks = [
            ReadinessCheck(
                key=str(item.get("key") or "check"),
                status=str(item.get("status") or "failed"),
                reason_code=str(item.get("reason_code") or "unknown"),
                reason=str(item.get("reason") or ""),
                suggestion=item.get("suggestion"),
                required=bool(item.get("required", True)),
                details=dict(item.get("details") or {}),
                duration_ms=item.get("duration_ms"),
                timed_out=bool(item.get("timed_out")),
            )
            for item in list(report.get("checks") or [])
            if isinstance(item, Mapping)
        ]

    components: Dict[str, Dict[str, Any]] = {}
    for check in checks:
        details = dict(check.details or {})
        if check.suggestion:
            details["suggestion"] = check.suggestion
        if check.reason_code:
            details["reason_code"] = check.reason_code
        if check.timed_out:
            details["timed_out"] = True
        components[check.key] = {
            "key": check.key,
            "label": check.key.replace("_", " ").title(),
            "status": check.status,
            "message": check.reason,
            "details": details,
        }
    return components


__all__ = [
    "SCHEMA_VERSION",
    "READINESS_STATUSES",
    "DEFAULT_CHECK_TIMEOUT_SECONDS",
    "MIN_CHECK_TIMEOUT_SECONDS",
    "MAX_CHECK_TIMEOUT_SECONDS",
    "ReadinessCheck",
    "ReadinessReport",
    "parse_readiness_check_timeout_seconds",
    "resolve_readiness_check_timeout_seconds",
    "aggregate_readiness_status",
    "project_setup_check_to_readiness",
    "check_data_providers",
    "check_llm_runtime",
    "check_task_queue",
    "check_dependencies_from_setup",
    "build_readiness_report",
    "readiness_report_to_diagnostic_components",
]
