# -*- coding: utf-8 -*-
"""Active sandbox context (isolated config + clock + data binding)."""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Dict, Iterator, Literal, Mapping, Optional, Union

from src.agent.sandbox.clock import FakeClock
from src.agent.sandbox.policy import (
    SANDBOX_ISOLATION_POLICY,
    SANDBOX_MODE,
    SIMULATION_BANNER_EN,
    SIMULATION_BANNER_ZH,
    SIMULATION_LABEL,
    get_sandbox_isolation_policy,
    simulation_markers,
)

SandboxDataMode = Literal["readonly_live", "snapshot"]

_ACTIVE_SANDBOX: ContextVar[Optional["SandboxContext"]] = ContextVar(
    "agent_sandbox_active_context",
    default=None,
)


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _stable_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SandboxContext:
    """Isolated sandbox run envelope.

    Always labeled SIMULATION. Holds a fake clock, isolated config overlay,
    and a data binding mode (read-only live market data or an immutable
    snapshot). Activating the context arms the external-effect fence.
    """

    sandbox_run_id: str
    clock: FakeClock
    data_mode: SandboxDataMode = "readonly_live"
    snapshot: Mapping[str, Any] = field(default_factory=dict)
    config_overlay: Mapping[str, Any] = field(default_factory=dict)
    agent_variant_id: str = "default"
    source_data_window: Optional[Mapping[str, Any]] = None
    language: str = "en"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot", _deep_freeze(dict(self.snapshot or {})))
        object.__setattr__(
            self, "config_overlay", _deep_freeze(dict(self.config_overlay or {}))
        )
        if self.source_data_window is not None:
            object.__setattr__(
                self,
                "source_data_window",
                _deep_freeze(dict(self.source_data_window)),
            )
        if self.data_mode not in ("readonly_live", "snapshot"):
            raise ValueError(f"unsupported sandbox data_mode: {self.data_mode}")
        if self.data_mode == "snapshot" and not self.snapshot:
            raise ValueError("snapshot data_mode requires a non-empty snapshot")

    @classmethod
    def create(
        cls,
        *,
        clock: Optional[FakeClock] = None,
        fixed_now: Optional[Union[datetime, str]] = None,
        data_mode: SandboxDataMode = "readonly_live",
        snapshot: Optional[Mapping[str, Any]] = None,
        config_overlay: Optional[Mapping[str, Any]] = None,
        agent_variant_id: str = "default",
        source_data_window: Optional[Mapping[str, Any]] = None,
        language: str = "en",
        sandbox_run_id: Optional[str] = None,
    ) -> "SandboxContext":
        if clock is None:
            if fixed_now is None:
                fixed_now = datetime.now(timezone.utc)
            clock = FakeClock.fixed(fixed_now)
        return cls(
            sandbox_run_id=sandbox_run_id or uuid.uuid4().hex,
            clock=clock,
            data_mode=data_mode,
            snapshot=dict(snapshot or {}),
            config_overlay=dict(config_overlay or {}),
            agent_variant_id=str(agent_variant_id or "default"),
            source_data_window=source_data_window,
            language=language,
        )

    @property
    def mode(self) -> str:
        return SANDBOX_MODE

    @property
    def label(self) -> str:
        return SIMULATION_LABEL

    @property
    def isolation_policy(self) -> Dict[str, Any]:
        return get_sandbox_isolation_policy()

    @property
    def config_digest(self) -> str:
        return _stable_digest(
            {
                "agent_variant_id": self.agent_variant_id,
                "config_overlay": dict(self.config_overlay),
                "data_mode": self.data_mode,
                "source_data_window": (
                    dict(self.source_data_window)
                    if self.source_data_window is not None
                    else None
                ),
            }
        )

    def markers(self) -> Dict[str, str]:
        return simulation_markers(language=self.language)

    def banner(self) -> str:
        markers = self.markers()
        return markers["banner"]

    def public_metadata(self) -> Dict[str, Any]:
        """Metadata suitable for traces, API responses, and UI banners."""
        return {
            "mode": self.mode,
            "label": self.label,
            "sandbox_run_id": self.sandbox_run_id,
            "agent_variant_id": self.agent_variant_id,
            "config_digest": self.config_digest,
            "data_mode": self.data_mode,
            "clock_now": self.clock.isoformat(),
            "source_data_window": (
                dict(self.source_data_window)
                if self.source_data_window is not None
                else None
            ),
            "isolation_policy": self.isolation_policy,
            "banner_en": SIMULATION_BANNER_EN,
            "banner_zh": SIMULATION_BANNER_ZH,
            "banner": self.banner(),
            "simulation": True,
        }


def get_active_sandbox() -> Optional[SandboxContext]:
    return _ACTIVE_SANDBOX.get()


def is_sandbox_active() -> bool:
    return get_active_sandbox() is not None


def require_sandbox_inactive_for_production_write(effect: str) -> None:
    """Raise when a production write is attempted under an active sandbox."""
    ctx = get_active_sandbox()
    if ctx is None:
        return
    from src.agent.sandbox.effects import (
        SandboxExternalEffectBlocked,
        record_blocked_external_effect,
    )

    record_blocked_external_effect(
        effect=effect,
        sandbox_run_id=ctx.sandbox_run_id,
        detail="production write refused while sandbox is active",
    )
    raise SandboxExternalEffectBlocked(
        effect=effect,
        sandbox_run_id=ctx.sandbox_run_id,
        message=(
            f"Sandbox refuses production external effect {effect!r} "
            f"(run_id={ctx.sandbox_run_id}). Results are SIMULATION only."
        ),
    )


@contextmanager
def active_sandbox_context(context: SandboxContext) -> Iterator[SandboxContext]:
    """Activate ``context`` for the current task and arm the effect fence."""
    if not isinstance(context, SandboxContext):
        raise TypeError("context must be a SandboxContext")
    existing = get_active_sandbox()
    if existing is not None:
        raise RuntimeError(
            "nested sandbox contexts are not supported "
            f"(active={existing.sandbox_run_id})"
        )
    from src.agent.sandbox.effects import ExternalEffectFence

    token: Token = _ACTIVE_SANDBOX.set(context)
    fence = ExternalEffectFence(sandbox_run_id=context.sandbox_run_id)
    fence_token = fence.activate()
    try:
        yield context
    finally:
        fence.deactivate(fence_token)
        _ACTIVE_SANDBOX.reset(token)


# Silence unused import warning for policy constant re-export consumers.
_ = SANDBOX_ISOLATION_POLICY
