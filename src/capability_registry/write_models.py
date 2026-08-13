# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Typed contracts for the write-side capability control plane.

The read-only inventory (``capability-inventory/v1``) continues to project live
owners. This module owns operator-declared capability entries used for
registration, dependency resolution, and task-aware routing metadata.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Literal, Optional, Tuple

WRITE_SCHEMA_VERSION = "capability-write-registry/v1"
WriteCapabilityDomain = Literal[
    "data", "tool", "skill", "pipeline", "llm", "persona",
]
WriteCapabilityType = Literal[
    "data_provider",
    "data_method",
    "agent_tool",
    "analysis_skill",
    "pipeline_stage",
    "llm_model",
    "persona_role",
]
WriteCapabilityStatus = Literal["active", "retired"]

_WRITE_DOMAINS = frozenset(
    {"data", "tool", "skill", "pipeline", "llm", "persona"}
)
_WRITE_TYPES_BY_DOMAIN: Dict[str, frozenset[str]] = {
    "data": frozenset({"data_provider", "data_method"}),
    "tool": frozenset({"agent_tool"}),
    "skill": frozenset({"analysis_skill"}),
    "pipeline": frozenset({"pipeline_stage"}),
    "llm": frozenset({"llm_model"}),
    "persona": frozenset({"persona_role"}),
}
_STATUSES = frozenset({"active", "retired"})

MAX_WRITE_ENTRIES = 1024
MAX_TAG_COUNT = 32
MAX_DEP_COUNT = 64
MAX_STRING = 256
MAX_VERSION = 64
MAX_ID = 256
MAX_DISPLAY = 200
MAX_TAGS_STRING = 64


def _require_bounded_str(
    value: Any,
    *,
    name: str,
    maximum: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    text = value.strip()
    if not text and not allow_empty:
        raise ValueError(f"{name} must be a non-empty string")
    if len(text) > maximum:
        raise ValueError(f"{name} exceeds max length {maximum}")
    return text


def _require_token_tuple(
    values: Any,
    *,
    name: str,
    maximum_items: int,
    maximum_item_length: int,
) -> Tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{name} must be a list of strings")
    if len(values) > maximum_items:
        raise ValueError(f"{name} has too many items")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _require_bounded_str(
            item, name=f"{name} item", maximum=maximum_item_length
        )
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return tuple(cleaned)


def parse_dependency_token(token: str) -> tuple[str, str, str]:
    """Return ``(capability_id, operator, version)`` for one dependency token."""

    text = _require_bounded_str(token, name="dependency", maximum=MAX_STRING)
    for op in (">=", "~=", "==", "@"):
        if op in text:
            left, right = text.split(op, 1)
            dep_id = _require_bounded_str(left, name="dependency id", maximum=MAX_ID)
            version = _require_bounded_str(
                right, name="dependency version", maximum=MAX_VERSION
            )
            return dep_id, op, version
    return text, "", ""


def _parse_version_parts(version: str) -> tuple[int, ...]:
    cleaned = version.strip().lstrip("vV")
    if not cleaned:
        raise ValueError("version is empty")
    parts: list[int] = []
    for piece in cleaned.split("."):
        if not piece.isdigit():
            raise ValueError(f"non-numeric version segment: {piece}")
        parts.append(int(piece))
    if not parts:
        raise ValueError("version has no numeric parts")
    return tuple(parts)


def versions_compatible(
    installed: str,
    *,
    operator: str,
    required: str,
) -> bool:
    """Return whether ``installed`` satisfies ``operator``/``required``."""

    if not operator:
        return True
    if operator in {"@", "=="}:
        return installed.strip() == required.strip()
    try:
        left = _parse_version_parts(installed)
        right = _parse_version_parts(required)
    except ValueError:
        return False
    width = max(len(left), len(right))
    left_p = left + (0,) * (width - len(left))
    right_p = right + (0,) * (width - len(right))
    if operator == ">=":
        return left_p >= right_p
    if operator == "~=":
        if len(right) >= 2:
            return left_p[0] == right_p[0] and left_p[1] == right_p[1] and left_p >= right_p
        return left_p[0] == right_p[0] and left_p >= right_p
    return False


@dataclass(frozen=True, slots=True)
class WriteCapabilityEntry:
    """One operator-declared capability in the write-side registry."""

    capability_id: str
    domain: WriteCapabilityDomain
    capability_type: WriteCapabilityType
    version: str
    status: WriteCapabilityStatus
    provider: str
    display_name: str = ""
    dependencies: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()
    scopes: Tuple[str, ...] = ()
    markets: Tuple[str, ...] = ()
    model_route: str = ""
    cost_tier: str = ""
    latency_class: str = ""
    registered_at: str = ""
    updated_at: str = ""
    retired_at: Optional[str] = None
    generation: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capability_id",
            _require_bounded_str(self.capability_id, name="capability_id", maximum=MAX_ID),
        )
        if self.domain not in _WRITE_DOMAINS:
            raise ValueError("domain is invalid")
        allowed = _WRITE_TYPES_BY_DOMAIN[self.domain]
        if self.capability_type not in allowed:
            raise ValueError("capability_type does not match domain")
        object.__setattr__(
            self,
            "version",
            _require_bounded_str(self.version, name="version", maximum=MAX_VERSION),
        )
        if self.status not in _STATUSES:
            raise ValueError("status is invalid")
        object.__setattr__(
            self,
            "provider",
            _require_bounded_str(self.provider, name="provider", maximum=128),
        )
        object.__setattr__(
            self,
            "display_name",
            _require_bounded_str(
                self.display_name or self.capability_id,
                name="display_name",
                maximum=MAX_DISPLAY,
            ),
        )
        object.__setattr__(
            self,
            "dependencies",
            _require_token_tuple(
                self.dependencies,
                name="dependencies",
                maximum_items=MAX_DEP_COUNT,
                maximum_item_length=MAX_STRING,
            ),
        )
        for dep in self.dependencies:
            parse_dependency_token(dep)
        object.__setattr__(
            self,
            "tags",
            _require_token_tuple(
                self.tags,
                name="tags",
                maximum_items=MAX_TAG_COUNT,
                maximum_item_length=MAX_TAGS_STRING,
            ),
        )
        object.__setattr__(
            self,
            "scopes",
            _require_token_tuple(
                self.scopes,
                name="scopes",
                maximum_items=MAX_TAG_COUNT,
                maximum_item_length=128,
            ),
        )
        object.__setattr__(
            self,
            "markets",
            _require_token_tuple(
                self.markets,
                name="markets",
                maximum_items=MAX_TAG_COUNT,
                maximum_item_length=128,
            ),
        )
        object.__setattr__(
            self,
            "model_route",
            _require_bounded_str(
                self.model_route, name="model_route", maximum=MAX_STRING, allow_empty=True
            ),
        )
        object.__setattr__(
            self,
            "cost_tier",
            _require_bounded_str(
                self.cost_tier, name="cost_tier", maximum=32, allow_empty=True
            ),
        )
        object.__setattr__(
            self,
            "latency_class",
            _require_bounded_str(
                self.latency_class, name="latency_class", maximum=32, allow_empty=True
            ),
        )
        if self.domain == "llm" and self.status == "active" and not self.model_route:
            raise ValueError("active llm capabilities require model_route")
        if type(self.generation) is not int or self.generation < 1:
            raise ValueError("generation must be a positive integer")
        if self.status == "retired" and not self.retired_at:
            raise ValueError("retired entries require retired_at")
        if self.status == "active" and self.retired_at is not None:
            raise ValueError("active entries must not carry retired_at")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> "WriteCapabilityEntry":
        if not isinstance(raw, dict):
            raise ValueError("capability entry must be an object")
        return cls(
            capability_id=raw.get("capability_id", ""),
            domain=raw.get("domain", ""),  # type: ignore[arg-type]
            capability_type=raw.get("capability_type", ""),  # type: ignore[arg-type]
            version=str(raw.get("version", "")),
            status=raw.get("status", "active"),  # type: ignore[arg-type]
            provider=str(raw.get("provider", "")),
            display_name=str(raw.get("display_name", "") or ""),
            dependencies=tuple(raw.get("dependencies") or ()),
            tags=tuple(raw.get("tags") or ()),
            scopes=tuple(raw.get("scopes") or ()),
            markets=tuple(raw.get("markets") or ()),
            model_route=str(raw.get("model_route", "") or ""),
            cost_tier=str(raw.get("cost_tier", "") or ""),
            latency_class=str(raw.get("latency_class", "") or ""),
            registered_at=str(raw.get("registered_at", "") or ""),
            updated_at=str(raw.get("updated_at", "") or ""),
            retired_at=(
                None
                if raw.get("retired_at") in (None, "")
                else str(raw.get("retired_at"))
            ),
            generation=int(raw.get("generation") or 1),
        )


@dataclass(frozen=True, slots=True)
class WriteRegistrySnapshot:
    """Versioned write-side registry snapshot."""

    schema_version: str = WRITE_SCHEMA_VERSION
    generation: int = 0
    as_of: str = ""
    entries: Tuple[WriteCapabilityEntry, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != WRITE_SCHEMA_VERSION:
            raise ValueError("unsupported write registry schema version")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be a non-negative integer")
        if len(self.entries) > MAX_WRITE_ENTRIES:
            raise ValueError("write registry exceeds entry capacity")
        ids = [entry.capability_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("write registry capability ids must be unique")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generation": self.generation,
            "as_of": self.as_of,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def active_by_id(self) -> Dict[str, WriteCapabilityEntry]:
        return {
            entry.capability_id: entry
            for entry in self.entries
            if entry.status == "active"
        }


@dataclass(frozen=True, slots=True)
class DependencyIssue:
    """One unresolved or incompatible dependency."""

    dependency: str
    capability_id: str
    reason_code: str
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    """Outcome of dependency and version compatibility resolution."""

    capability_id: str
    ready: bool
    reason_code: str
    satisfied: Tuple[str, ...] = ()
    issues: Tuple[DependencyIssue, ...] = ()
    checked_against_generation: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "ready": self.ready,
            "reason_code": self.reason_code,
            "satisfied": list(self.satisfied),
            "issues": [issue.to_dict() for issue in self.issues],
            "checked_against_generation": self.checked_against_generation,
        }


TaskClass = Literal[
    "report",
    "agent",
    "vision",
    "market_review",
    "cheap_scan",
    "deep_reasoning",
    "coding",
]
RoutingPolicy = Literal["quality", "cost", "local_first"]

TASK_CLASSES: Tuple[str, ...] = (
    "report",
    "agent",
    "vision",
    "market_review",
    "cheap_scan",
    "deep_reasoning",
    "coding",
)
ROUTING_POLICIES: Tuple[str, ...] = ("quality", "cost", "local_first")

TASK_CLASS_PREFERRED_TAGS: Dict[str, Tuple[str, ...]] = {
    "report": ("reasoning",),
    "agent": ("reasoning", "coding"),
    "vision": ("vision",),
    "market_review": ("reasoning",),
    "cheap_scan": ("cost:low", "latency:fast"),
    "deep_reasoning": ("reasoning", "quality:high"),
    "coding": ("coding",),
}


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    """One scored model candidate considered by the router."""

    capability_id: str
    model_route: str
    score: int
    tags: Tuple[str, ...] = ()
    reasons: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TaskRouteDecision:
    """Explainable task-aware model routing decision."""

    schema_version: str = "task-route-decision/v1"
    task_class: str = "report"
    policy: str = "quality"
    selected_model: str = ""
    selected_capability_id: str = ""
    reason_code: str = "no_candidate"
    explain: Tuple[str, ...] = ()
    candidates: Tuple[RouteCandidate, ...] = ()
    pin_source: str = ""
    fallback_used: bool = False
    routing_enabled: bool = False
    as_of: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_class": self.task_class,
            "policy": self.policy,
            "selected_model": self.selected_model,
            "selected_capability_id": self.selected_capability_id,
            "reason_code": self.reason_code,
            "explain": list(self.explain),
            "candidates": [item.to_dict() for item in self.candidates],
            "pin_source": self.pin_source,
            "fallback_used": self.fallback_used,
            "routing_enabled": self.routing_enabled,
            "as_of": self.as_of,
        }
