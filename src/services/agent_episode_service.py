# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Feature-flagged, fail-soft agent evolution episode log (Issue #1090)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.schemas.agent_episode import (
    AGENT_EPISODE_DEFAULT_MAX_ROWS,
    AGENT_EPISODE_DEFAULT_RETENTION_DAYS,
    AGENT_EPISODE_MAX_PAGE_SIZE,
    AGENT_EPISODE_MAX_TRAJECTORY_STEPS,
    AgentEpisode,
    AgentEpisodeCreate,
    AgentEpisodePage,
    EpisodeLesson,
    EpisodeOutcomeLabels,
    TrajectoryStepSummary,
)
from src.schemas.memory_forget_policy import (
    EpisodeForgetResult,
    MemoryForgetError,
    resolve_episode_forget_policy,
)
from src.services.agent_trajectory_eval_service import (
    duration_to_ms,
    normalize_tool_arguments,
)
from src.utils.sanitize import log_safe_exception, redact_sensitive_data

logger = logging.getLogger(__name__)


def is_agent_episode_log_enabled(config: Any = None) -> bool:
    return config is not None and getattr(config, "agent_episode_log_enabled", None) is True


def _policy_int(config: Any, name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = getattr(config, name, None) if config is not None else None
    try:
        value = int(raw) if raw is not None else int(default)
    except (TypeError, ValueError):
        value = int(default)
    return max(minimum, min(maximum, value))


class AgentEpisodeService:
    def __init__(
        self,
        repository: Optional[AgentEpisodeRepository] = None,
        *,
        config: Any = None,
    ) -> None:
        # Keep the default-off path free of database initialization and migration
        # side effects. The production repository is created only for an enabled
        # write or an explicit query call.
        self._repository = repository
        self._config = config

    def _get_repository(self) -> AgentEpisodeRepository:
        if self._repository is None:
            self._repository = AgentEpisodeRepository()
        return self._repository

    def record_episode(
        self,
        episode: AgentEpisodeCreate | Mapping[str, Any],
        *,
        config: Any = None,
    ) -> Optional[AgentEpisode]:
        cfg = config if config is not None else self._config
        if not is_agent_episode_log_enabled(cfg):
            return None
        try:
            create = (
                episode
                if isinstance(episode, AgentEpisodeCreate)
                else AgentEpisodeCreate.model_validate(episode)
            )
            create = self._sanitize_create(create)
            stored = self._get_repository().append(create)
            self._maybe_apply_forgetting(cfg, symbol=stored.symbol)
            return stored
        except Exception as exc:  # broad-exception: fallback_recorded - episode append must never fail analysis
            log_safe_exception(
                logger,
                "agent_episode_record_failed",
                exc,
                error_code="agent_episode_record_failed",
                context={
                    "run_id": getattr(episode, "run_id", None)
                    if not isinstance(episode, Mapping)
                    else episode.get("run_id"),
                },
            )
            return None

    def record_from_agent_result(
        self,
        *,
        result: Any,
        run_id: Optional[str] = None,
        mode: str = "single",
        symbol: Optional[str] = None,
        market: Optional[str] = None,
        lessons: Optional[Sequence[Mapping[str, Any]]] = None,
        outcome_labels: Optional[Mapping[str, Any]] = None,
        config: Any = None,
        started_at: Optional[datetime] = None,
    ) -> Optional[AgentEpisode]:
        cfg = config if config is not None else self._config
        if not is_agent_episode_log_enabled(cfg):
            return None
        try:
            resolved_run_id = str(run_id or getattr(result, "run_id", None) or uuid.uuid4().hex).strip()
            facts = getattr(result, "runtime_facts", None)
            soul_version = None
            soul_hash = None
            if facts is not None:
                soul_version = getattr(facts, "soul_version", None)
                soul_hash = getattr(facts, "soul_hash", None)
                if callable(getattr(facts, "to_metadata", None)):
                    meta = facts.to_metadata() or {}
                    soul_version = soul_version or meta.get("soul_version")
                    soul_hash = soul_hash or meta.get("soul_hash")
            trajectory = compact_trajectory_summary(getattr(result, "tool_calls_log", None) or [])
            payload: Dict[str, Any] = {
                "episode_id": f"ep-{uuid.uuid4().hex}",
                "run_id": resolved_run_id,
                "mode": str(mode or "single").strip().lower() or "single",
                "symbol": symbol,
                "market": market,
                "started_at": started_at,
                "completed_at": datetime.now(timezone.utc),
                "success": bool(getattr(result, "success", False)),
                "soul_version": soul_version,
                "soul_hash": soul_hash,
                "trajectory_summary": trajectory,
                "lessons": list(lessons or []),
                "outcome_labels": outcome_labels,
            }
            return self.record_episode(payload, config=cfg)
        except Exception as exc:  # broad-exception: fallback_recorded - result projection must never fail analysis
            log_safe_exception(
                logger,
                "agent_episode_record_from_result_failed",
                exc,
                error_code="agent_episode_record_from_result_failed",
                context={"mode": mode, "symbol": symbol},
            )
            return None

    def get_by_run_id(
        self,
        run_id: str,
        *,
        limit: int = AGENT_EPISODE_MAX_PAGE_SIZE,
    ) -> List[AgentEpisode]:
        return self._get_repository().get_by_run_id(run_id, limit=limit)

    def get_by_episode_id(self, episode_id: str) -> Optional[AgentEpisode]:
        return self._get_repository().get_by_episode_id(episode_id)

    def query(self, **filters: Any) -> AgentEpisodePage:
        return self._get_repository().query(**filters)

    def list_for_replay(self, episode_ids: Sequence[str]) -> List[AgentEpisode]:
        return self._get_repository().list_for_replay(episode_ids)

    def forget_symbol(
        self,
        symbol: str,
        *,
        cutoff: Optional[datetime] = None,
        retention_days: Optional[int] = None,
        max_rows: Optional[int] = None,
        now: Optional[datetime] = None,
        dry_run: bool = False,
    ) -> EpisodeForgetResult:
        """Apply an explicit per-symbol forget pass.

        Missing cutoff and max_rows is no-policy and deletes nothing. Invalid
        or unscoped policy raises. Persistence failures raise; this path is
        not fail-soft. Analysis still uses ``_maybe_apply_forgetting``.
        """
        repository = self._get_repository()
        clock_now = now if now is not None else repository._clock()
        decision = resolve_episode_forget_policy(
            symbol=symbol,
            cutoff=cutoff,
            retention_days=retention_days,
            now=clock_now,
            max_rows=max_rows,
            dry_run=dry_run,
        )
        if decision.error_code:
            raise MemoryForgetError(
                decision.reason or "invalid episode forget policy",
                error_code=decision.error_code,
            )
        result = repository.apply_forget(decision)
        logger.info(
            "agent_episode_forget_applied deleted_count=%s remaining_count=%s "
            "symbol=%s dry_run=%s",
            result.deleted_count,
            result.remaining_count,
            result.symbol,
            result.dry_run,
        )
        return result

    def _sanitize_create(self, episode: AgentEpisodeCreate) -> AgentEpisodeCreate:
        lessons: List[EpisodeLesson] = []
        for lesson in episode.lessons:
            data = redact_sensitive_data(lesson.model_dump(mode="python"))
            if isinstance(data, dict):
                lessons.append(EpisodeLesson.model_validate(data))
        outcome = episode.outcome_labels
        if outcome is not None:
            redacted = redact_sensitive_data(outcome.model_dump(mode="python"))
            outcome = EpisodeOutcomeLabels.model_validate(redacted) if isinstance(redacted, dict) else None
        return episode.model_copy(update={"lessons": lessons, "outcome_labels": outcome, "soul_charter": None})

    def _maybe_apply_forgetting(self, config: Any, *, symbol: Optional[str]) -> None:
        if not isinstance(symbol, str) or not symbol.strip():
            return
        retention_days = _policy_int(
            config, "agent_episode_retention_days", AGENT_EPISODE_DEFAULT_RETENTION_DAYS,
            minimum=1, maximum=3650,
        )
        max_rows = _policy_int(
            config, "agent_episode_max_rows", AGENT_EPISODE_DEFAULT_MAX_ROWS,
            minimum=100, maximum=1_000_000,
        )
        try:
            repository = self._get_repository()
            decision = resolve_episode_forget_policy(
                symbol=symbol,
                retention_days=retention_days,
                now=repository._clock(),
                max_rows=max_rows,
            )
            if decision.error_code or not decision.apply:
                return
            result = repository.apply_forget(decision)
            logger.info(
                "agent_episode_forget_applied deleted_count=%s remaining_count=%s "
                "symbol=%s dry_run=%s",
                result.deleted_count,
                result.remaining_count,
                result.symbol,
                result.dry_run,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - forgetting is fail-soft after append
            log_safe_exception(
                logger, "agent_episode_forget_failed", exc,
                error_code="agent_episode_forget_failed",
                context={"symbol": symbol},
            )


def compact_trajectory_summary(tool_calls: Sequence[Mapping[str, Any] | Any]) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    for index, raw in enumerate(list(tool_calls)[:AGENT_EPISODE_MAX_TRAJECTORY_STEPS]):
        if not isinstance(raw, Mapping):
            continue
        entry = dict(raw)
        tool = entry.get("tool") or entry.get("name")
        if not isinstance(tool, str) or not tool.strip():
            continue
        success = entry.get("success")
        if not isinstance(success, bool):
            continue
        fingerprint = None
        arguments = entry.get("arguments")
        if arguments is not None:
            try:
                canonical = normalize_tool_arguments(redact_sensitive_data(arguments))
                fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
            except (TypeError, ValueError):
                fingerprint = None
        duration_ms = duration_to_ms(entry.get("duration"))
        raw_step = entry.get("step")
        step_no = (
            raw_step
            if isinstance(raw_step, int)
            and not isinstance(raw_step, bool)
            and 0 <= raw_step <= 10_000
            else index + 1
        )
        summary: Dict[str, Any] = {"step": step_no, "tool": tool.strip()[:128], "success": success}
        if isinstance(entry.get("cached"), bool):
            summary["cached"] = entry["cached"]
        if isinstance(entry.get("timeout"), bool):
            summary["timeout"] = entry["timeout"]
        if isinstance(entry.get("guarded"), bool):
            summary["guarded"] = entry["guarded"]
        if duration_ms is not None:
            summary["duration_ms"] = duration_ms
        if fingerprint:
            summary["argument_fingerprint"] = fingerprint
        steps.append(TrajectoryStepSummary.model_validate(summary).model_dump(mode="python"))
    return steps


def try_record_agent_episode_from_result(
    *,
    result: Any,
    config: Any = None,
    run_id: Optional[str] = None,
    mode: str = "single",
    context: Optional[Mapping[str, Any]] = None,
    started_at: Optional[datetime] = None,
) -> Optional[AgentEpisode]:
    if not is_agent_episode_log_enabled(config):
        return None
    try:
        ctx = context if isinstance(context, Mapping) else {}
        symbol = ctx.get("stock_code") or ctx.get("symbol")
        market = ctx.get("market")
        correlated_run_id = run_id or ctx.get("run_id") or ctx.get("task_id")
        symbol = symbol.strip() if isinstance(symbol, str) and symbol.strip() else None
        market = market.strip().lower() if isinstance(market, str) and market.strip() else None
        return AgentEpisodeService(config=config).record_from_agent_result(
            result=result,
            run_id=str(correlated_run_id).strip() if correlated_run_id else None,
            mode=mode,
            symbol=symbol,
            market=market,
            config=config,
            started_at=started_at,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - helper must never alter agent control flow
        log_safe_exception(
            logger,
            "agent_episode_helper_failed",
            exc,
            error_code="agent_episode_helper_failed",
            context={"mode": mode},
        )
        return None


__all__ = [
    "AgentEpisodeService",
    "compact_trajectory_summary",
    "is_agent_episode_log_enabled",
    "try_record_agent_episode_from_result",
]
