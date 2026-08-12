# -*- coding: utf-8 -*-
"""Project typed reflection lessons into episode storage shapes (Issue #1094).

Reuses the episode lesson projection introduced by the evolution episode log
(#1090 / PR #1210). When the episode service is not yet merged, callers can
still materialize serializable lesson payloads and an in-memory sink.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence

from src.agent.evolution.lessons import (
    LESSON_KINDS,
    ReflectionLesson,
    ReflectionResult,
)
from src.agent.public_contract import sanitize_agent_diagnostic

_MAX_LESSONS = 8
_MAX_REMEDY = 300
_MAX_KIND = 64
_MAX_SOURCE = 64
_MAX_REF = 128


def lesson_to_episode_dict(lesson: ReflectionLesson) -> Dict[str, Any]:
    """Map a typed ``ReflectionLesson`` into the episode-storage projection."""
    kind = str(lesson.kind)
    if kind not in LESSON_KINDS:
        kind = "other"
    payload: Dict[str, Any] = {
        "kind": kind[:_MAX_KIND],
        "severity": lesson.severity if lesson.severity in {"low", "medium", "high"} else "medium",
    }
    if lesson.claim_ref:
        payload["claim_ref"] = str(lesson.claim_ref)[:_MAX_REF]
    if lesson.remedy:
        payload["remedy"] = sanitize_agent_diagnostic(str(lesson.remedy))[:_MAX_REMEDY]
    if lesson.source_step:
        payload["source_step"] = str(lesson.source_step)[:_MAX_SOURCE]
    return payload


def reflection_result_to_episode_lessons(
    result: Optional[ReflectionResult],
    *,
    max_lessons: int = _MAX_LESSONS,
) -> List[Dict[str, Any]]:
    """Extract bounded episode lesson dicts from a reflection result."""
    if result is None:
        return []
    out: List[Dict[str, Any]] = []
    for lesson in result.lessons[:max_lessons]:
        out.append(lesson_to_episode_dict(lesson))
    return out


def merge_episode_lessons(
    *groups: Sequence[Dict[str, Any]],
    max_lessons: int = _MAX_LESSONS,
) -> List[Dict[str, Any]]:
    """Deduplicate lesson dicts by kind (first severity/remedy wins)."""
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for group in groups:
        for item in group:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip()
            if not kind or kind not in LESSON_KINDS or kind in seen:
                continue
            seen.add(kind)
            payload: Dict[str, Any] = {
                "kind": kind,
                "severity": item.get("severity")
                if item.get("severity") in {"low", "medium", "high"}
                else "medium",
            }
            if item.get("claim_ref"):
                payload["claim_ref"] = str(item["claim_ref"])[:_MAX_REF]
            if item.get("remedy"):
                payload["remedy"] = sanitize_agent_diagnostic(str(item["remedy"]))[
                    :_MAX_REMEDY
                ]
            if item.get("source_step"):
                payload["source_step"] = str(item["source_step"])[:_MAX_SOURCE]
            out.append(payload)
            if len(out) >= max_lessons:
                return out
    return out


class EpisodeLessonSink(Protocol):
    """Minimal sink used by multi-level reflection when recording lessons."""

    def append_lessons(
        self,
        *,
        run_id: str,
        episode_id: Optional[str],
        lessons: Sequence[Dict[str, Any]],
        layer: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None: ...


@dataclass
class InMemoryEpisodeLessonSink:
    """Test / offline sink that accumulates episode lesson records."""

    records: List[Dict[str, Any]] = field(default_factory=list)

    def append_lessons(
        self,
        *,
        run_id: str,
        episode_id: Optional[str],
        lessons: Sequence[Dict[str, Any]],
        layer: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.records.append(
            {
                "run_id": run_id,
                "episode_id": episode_id,
                "layer": layer,
                "lessons": list(lessons),
                "meta": dict(meta or {}),
            }
        )

    def as_episodes(self) -> List[Dict[str, Any]]:
        """Flatten sink records into meta-review episode samples."""
        episodes: List[Dict[str, Any]] = []
        for record in self.records:
            episodes.append(
                {
                    "run_id": record.get("run_id"),
                    "episode_id": record.get("episode_id") or record.get("run_id"),
                    "lessons": list(record.get("lessons") or []),
                    "layer": record.get("layer"),
                    "meta": dict(record.get("meta") or {}),
                }
            )
        return episodes


def record_reflection_lessons(
    sink: Optional[EpisodeLessonSink],
    result: ReflectionResult,
    *,
    layer: str,
    run_id: Optional[str] = None,
    episode_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Project lessons and optionally append them to an episode sink."""
    lessons = reflection_result_to_episode_lessons(result)
    if sink is not None and lessons:
        resolved_run = (
            run_id
            or result.run_id
            or (meta or {}).get("run_id")
            or "unknown-run"
        )
        sink.append_lessons(
            run_id=str(resolved_run),
            episode_id=episode_id or result.episode_id,
            lessons=lessons,
            layer=layer,
            meta=meta,
        )
    return lessons


def try_append_lessons_to_episode_service(
    *,
    run_id: str,
    lessons: Sequence[Dict[str, Any]],
    config: Any = None,
    mode: str = "single",
    symbol: Optional[str] = None,
    layer: str = "trajectory",
    success: Optional[bool] = None,
    trajectory_summary: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[str]:
    """Best-effort append into AgentEpisodeService when #1090/#1210 is present.

    Returns the stored episode_id, or ``None`` when the service is unavailable,
    disabled, or the append fails (fail-soft; never raises into analysis).
    """
    if not lessons and not trajectory_summary:
        return None
    try:
        from src.services.agent_episode_service import (  # type: ignore
            AgentEpisodeService,
            is_agent_episode_log_enabled,
        )
    except Exception:
        return None
    if not is_agent_episode_log_enabled(config):
        return None
    try:
        import uuid
        from datetime import datetime, timezone

        episode_id = f"ep-{uuid.uuid4().hex}"
        payload: Dict[str, Any] = {
            "episode_id": episode_id,
            "run_id": str(run_id or episode_id),
            "mode": str(mode or "single")[:32],
            "lessons": list(lessons or [])[:8],
            "trajectory_summary": list(trajectory_summary or [])[:64],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        if symbol:
            payload["symbol"] = str(symbol)[:32]
        if success is not None:
            payload["success"] = bool(success)
        # Keep layer as an outcome label extra when supported.
        payload["outcome_labels"] = {
            "extra": {"reflection_layer": str(layer)[:64]},
        }
        service = AgentEpisodeService(config=config)
        stored = service.record_episode(payload, config=config)
        if stored is None:
            return None
        return getattr(stored, "episode_id", None) or episode_id
    except Exception:
        return None


__all__ = [
    "EpisodeLessonSink",
    "InMemoryEpisodeLessonSink",
    "lesson_to_episode_dict",
    "merge_episode_lessons",
    "record_reflection_lessons",
    "reflection_result_to_episode_lessons",
    "try_append_lessons_to_episode_service",
]
