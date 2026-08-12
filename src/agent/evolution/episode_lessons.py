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


__all__ = [
    "EpisodeLessonSink",
    "InMemoryEpisodeLessonSink",
    "lesson_to_episode_dict",
    "merge_episode_lessons",
    "record_reflection_lessons",
    "reflection_result_to_episode_lessons",
]
