# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Task-aware model routing with explainable decisions.

Explicit per-task pins always win. When routing is enabled, active LLM
capabilities from the write registry are scored by task tags and policy.
When routing is disabled or no candidate matches, the router falls back to
the existing configured model assignment with an explicit reason code.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional, Sequence

from src.capability_registry.write_models import (
    ROUTING_POLICIES,
    TASK_CLASS_PREFERRED_TAGS,
    TASK_CLASSES,
    RouteCandidate,
    TaskRouteDecision,
    WriteCapabilityEntry,
    WriteRegistrySnapshot,
)

Clock = Callable[[], datetime]

_PIN_ATTR_BY_TASK: Dict[str, tuple[str, ...]] = {
    "report": ("litellm_model",),
    "agent": ("agent_litellm_model", "litellm_model"),
    "vision": ("vision_model", "litellm_model"),
    "market_review": ("litellm_model",),
    "cheap_scan": ("litellm_model",),
    "deep_reasoning": ("litellm_model",),
    "coding": ("agent_litellm_model", "litellm_model"),
}

_OPTIONAL_TASK_PIN_ATTR: Dict[str, str] = {
    "report": "task_routing_pin_report",
    "agent": "task_routing_pin_agent",
    "vision": "task_routing_pin_vision",
    "market_review": "task_routing_pin_market_review",
    "cheap_scan": "task_routing_pin_cheap_scan",
    "deep_reasoning": "task_routing_pin_deep_reasoning",
    "coding": "task_routing_pin_coding",
}


def normalize_task_class(value: str) -> str:
    text = (value or "").strip().lower()
    if text not in TASK_CLASSES:
        raise ValueError(
            f"unsupported task_class {value!r}; allowed: {', '.join(TASK_CLASSES)}"
        )
    return text


def normalize_routing_policy(value: str) -> str:
    text = (value or "").strip().lower() or "quality"
    if text not in ROUTING_POLICIES:
        raise ValueError(
            f"unsupported routing policy {value!r}; "
            f"allowed: {', '.join(ROUTING_POLICIES)}"
        )
    return text


def _config_bool(config: Any, attr: str, default: bool = False) -> bool:
    raw = getattr(config, attr, default) if config is not None else default
    if isinstance(raw, bool):
        return raw
    text = str(raw or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def _config_str(config: Any, attr: str) -> str:
    if config is None:
        return ""
    return str(getattr(config, attr, "") or "").strip()


def _explicit_task_pin(config: Any, task_class: str) -> tuple[str, str]:
    """Return an optional per-task pin that always overrides automatic routing."""

    optional_attr = _OPTIONAL_TASK_PIN_ATTR.get(task_class)
    if optional_attr:
        value = _config_str(config, optional_attr)
        if value:
            return value, optional_attr.upper()
    return "", ""


def _configured_model_fallback(config: Any, task_class: str) -> tuple[str, str]:
    """Return the existing task model assignment used when routing yields no pick."""

    attr_to_env = {
        "litellm_model": "LITELLM_MODEL",
        "agent_litellm_model": "AGENT_LITELLM_MODEL",
        "vision_model": "VISION_MODEL",
    }
    for attr in _PIN_ATTR_BY_TASK.get(task_class, ()):
        value = _config_str(config, attr)
        if value:
            return value, attr_to_env.get(attr, attr.upper())
    return "", ""


def _is_local_route(route: str, tags: Sequence[str]) -> bool:
    lowered = route.lower()
    if "local" in tags or "local-first" in tags:
        return True
    return any(
        token in lowered
        for token in ("ollama/", "local/", "localhost", "127.0.0.1")
    )


def _score_candidate(
    entry: WriteCapabilityEntry,
    *,
    task_class: str,
    policy: str,
) -> tuple[int, tuple[str, ...]]:
    preferred = TASK_CLASS_PREFERRED_TAGS.get(task_class, ())
    tags = set(entry.tags)
    if entry.cost_tier:
        tags.add(f"cost:{entry.cost_tier}")
    if entry.latency_class:
        tags.add(f"latency:{entry.latency_class}")
    reasons: list[str] = []
    score = 0

    for tag in preferred:
        if tag in tags:
            score += 10
            reasons.append(f"tag_match:{tag}")

    if policy == "quality":
        if "quality:high" in tags:
            score += 8
            reasons.append("policy_quality_high")
        if "reasoning" in tags:
            score += 4
            reasons.append("policy_quality_reasoning")
        if entry.cost_tier == "high":
            score += 1
    elif policy == "cost":
        if "cost:low" in tags or entry.cost_tier == "low":
            score += 12
            reasons.append("policy_cost_low")
        elif entry.cost_tier == "medium":
            score += 4
            reasons.append("policy_cost_medium")
        if "latency:fast" in tags or entry.latency_class == "fast":
            score += 3
            reasons.append("policy_cost_fast")
    elif policy == "local_first":
        if _is_local_route(entry.model_route, tuple(tags)):
            score += 15
            reasons.append("policy_local")
        if "cost:low" in tags or entry.cost_tier == "low":
            score += 4
            reasons.append("policy_local_cost_low")

    if entry.model_route:
        score += 1
    return score, tuple(reasons)


def _active_llm_entries(
    snapshot: WriteRegistrySnapshot,
) -> list[WriteCapabilityEntry]:
    return [
        entry
        for entry in snapshot.entries
        if entry.domain == "llm"
        and entry.status == "active"
        and entry.model_route
    ]


def resolve_task_model_route(
    task_class: str,
    *,
    config: Any = None,
    write_snapshot: WriteRegistrySnapshot | None = None,
    policy: str | None = None,
    clock: Clock | None = None,
    available_routes: Iterable[str] | None = None,
) -> TaskRouteDecision:
    """Select a model for ``task_class`` and return an explainable decision."""

    now = (clock or (lambda: datetime.now(timezone.utc)))().astimezone(
        timezone.utc
    ).isoformat()
    normalized_task = normalize_task_class(task_class)
    routing_enabled = _config_bool(config, "task_routing_enabled", default=False)
    resolved_policy = normalize_routing_policy(
        policy
        if policy is not None
        else (_config_str(config, "task_routing_policy") or "quality")
    )

    pin_model, pin_source = _explicit_task_pin(config, normalized_task)
    explain: list[str] = []

    if pin_model:
        explain.append(f"manual_pin from {pin_source}={pin_model}")
        return TaskRouteDecision(
            task_class=normalized_task,
            policy=resolved_policy,
            selected_model=pin_model,
            selected_capability_id="",
            reason_code="manual_pin",
            explain=tuple(explain),
            candidates=(),
            pin_source=pin_source,
            fallback_used=False,
            routing_enabled=routing_enabled,
            as_of=now,
        )

    if not routing_enabled:
        fallback_model, fallback_source = _configured_model_fallback(
            config, normalized_task
        )
        if fallback_model:
            explain.append(
                f"task_routing_enabled=false; using configured {fallback_source}"
            )
            return TaskRouteDecision(
                task_class=normalized_task,
                policy=resolved_policy,
                selected_model=fallback_model,
                reason_code="routing_disabled_configured_fallback",
                explain=tuple(explain),
                pin_source=fallback_source,
                fallback_used=True,
                routing_enabled=False,
                as_of=now,
            )
        explain.append("task_routing_enabled=false; no automatic selection")
        return TaskRouteDecision(
            task_class=normalized_task,
            policy=resolved_policy,
            selected_model="",
            reason_code="routing_disabled",
            explain=tuple(explain),
            routing_enabled=False,
            as_of=now,
        )

    snapshot = write_snapshot or WriteRegistrySnapshot(as_of=now)
    llm_entries = _active_llm_entries(snapshot)
    if not llm_entries:
        fallback_model, fallback_source = _configured_model_fallback(
            config, normalized_task
        )
        explain.append("no active llm capabilities in write registry")
        if fallback_model:
            explain.append(f"fallback to configured {fallback_source}")
            return TaskRouteDecision(
                task_class=normalized_task,
                policy=resolved_policy,
                selected_model=fallback_model,
                reason_code="no_llm_capabilities_configured_fallback",
                explain=tuple(explain),
                pin_source=fallback_source,
                fallback_used=True,
                routing_enabled=True,
                as_of=now,
            )
        return TaskRouteDecision(
            task_class=normalized_task,
            policy=resolved_policy,
            selected_model="",
            reason_code="no_llm_capabilities",
            explain=tuple(explain),
            routing_enabled=True,
            as_of=now,
        )

    allowed: Optional[set[str]] = None
    if available_routes is not None:
        allowed = {str(item).strip() for item in available_routes if str(item).strip()}

    scored: list[RouteCandidate] = []
    for entry in llm_entries:
        if allowed is not None and entry.model_route not in allowed:
            explain.append(
                f"skip {entry.capability_id}: model_route not in available routes"
            )
            continue
        score, reasons = _score_candidate(
            entry, task_class=normalized_task, policy=resolved_policy
        )
        preferred = TASK_CLASS_PREFERRED_TAGS.get(normalized_task, ())
        tags = set(entry.tags)
        if entry.cost_tier:
            tags.add(f"cost:{entry.cost_tier}")
        if entry.latency_class:
            tags.add(f"latency:{entry.latency_class}")
        has_preferred = any(tag in tags for tag in preferred) if preferred else True
        is_local = _is_local_route(entry.model_route, tuple(tags))
        if not has_preferred and not (resolved_policy == "local_first" and is_local):
            explain.append(
                f"skip {entry.capability_id}: missing preferred tags {preferred}"
            )
            continue
        scored.append(
            RouteCandidate(
                capability_id=entry.capability_id,
                model_route=entry.model_route,
                score=score,
                tags=tuple(sorted(tags)),
                reasons=reasons,
            )
        )

    scored.sort(
        key=lambda item: (-item.score, item.capability_id, item.model_route)
    )
    if not scored:
        fallback_model, fallback_source = _configured_model_fallback(
            config, normalized_task
        )
        explain.append("no candidate satisfied task tags/policy constraints")
        if fallback_model:
            explain.append(f"fallback to configured {fallback_source}")
            return TaskRouteDecision(
                task_class=normalized_task,
                policy=resolved_policy,
                selected_model=fallback_model,
                reason_code="no_matching_candidate_configured_fallback",
                explain=tuple(explain),
                candidates=(),
                pin_source=fallback_source,
                fallback_used=True,
                routing_enabled=True,
                as_of=now,
            )
        return TaskRouteDecision(
            task_class=normalized_task,
            policy=resolved_policy,
            selected_model="",
            reason_code="no_matching_candidate",
            explain=tuple(explain),
            candidates=(),
            routing_enabled=True,
            as_of=now,
        )

    best = scored[0]
    explain.append(
        f"selected {best.capability_id} route={best.model_route} score={best.score}"
    )
    for reason in best.reasons:
        explain.append(reason)
    return TaskRouteDecision(
        task_class=normalized_task,
        policy=resolved_policy,
        selected_model=best.model_route,
        selected_capability_id=best.capability_id,
        reason_code="policy_match",
        explain=tuple(explain),
        candidates=tuple(scored[:8]),
        pin_source="",
        fallback_used=False,
        routing_enabled=True,
        as_of=now,
    )


def decision_for_diagnostics(decision: TaskRouteDecision) -> Dict[str, Any]:
    """Bounded dict safe to embed in run diagnostics / API responses."""

    payload = decision.to_dict()
    payload["candidates"] = payload.get("candidates", [])[:8]
    payload["explain"] = list(payload.get("explain") or [])[:32]
    return payload
