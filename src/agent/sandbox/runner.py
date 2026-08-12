# -*- coding: utf-8 -*-
"""Sandbox runner for agent / strategy variants.

Runs an agent variant under an active SandboxContext so that:
- config overlay + fake clock + data access are isolated
- all outputs are labeled SIMULATION
- production decision / notification writes are fenced
- traces stay production-isomorphic for comparison
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from src.agent.sandbox.context import (
    SandboxContext,
    active_sandbox_context,
)
from src.agent.sandbox.data_access import SandboxDataAccess
from src.agent.sandbox.effects import get_blocked_external_effects
from src.agent.sandbox.policy import SIMULATION_LABEL
from src.agent.sandbox.promotion import PromotionReceipt, build_promotion_receipt
from src.agent.sandbox.trace import SandboxTrace, build_sandbox_trace


VariantCallable = Callable[
    ["SandboxRunRequest", SandboxContext, SandboxDataAccess],
    Mapping[str, Any],
]


@dataclass(frozen=True)
class SandboxRunRequest:
    """One agent-variant sandbox execution request."""

    prompt: str
    agent_variant_id: str = "default"
    config_overlay: Mapping[str, Any] = field(default_factory=dict)
    stock_code: Optional[str] = None
    market: Optional[str] = None
    language: str = "en"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SandboxRunResult:
    """Sandbox outcome: labeled content, isomorphic trace, promotion receipt."""

    success: bool
    content: str
    context: SandboxContext
    trace: SandboxTrace
    simulated_actions: tuple = ()
    rejected_actions: tuple = ()
    blocked_external_effects: tuple = ()
    promotion_receipt: Optional[PromotionReceipt] = None
    error: Optional[str] = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "content": self.content,
            "simulation": True,
            "label": SIMULATION_LABEL,
            "mode": self.context.mode,
            "sandbox_run_id": self.context.sandbox_run_id,
            "agent_variant_id": self.context.agent_variant_id,
            "config_digest": self.context.config_digest,
            "banner": self.context.banner(),
            "trace": self.trace.to_dict(),
            "simulated_actions": [dict(item) for item in self.simulated_actions],
            "rejected_actions": [dict(item) for item in self.rejected_actions],
            "blocked_external_effects": [
                dict(item) for item in self.blocked_external_effects
            ],
            "promotion_receipt": (
                self.promotion_receipt.to_dict()
                if self.promotion_receipt is not None
                else None
            ),
            "error": self.error,
            "raw": dict(self.raw),
            "metadata": self.context.public_metadata(),
        }


class SandboxRunner:
    """Execute one or more agent variants inside a safe sandbox."""

    def __init__(
        self,
        *,
        variant_callable: Optional[VariantCallable] = None,
        live_reader: Optional[Callable[[str, Mapping[str, Any]], Any]] = None,
    ) -> None:
        self._variant_callable = variant_callable or _default_variant_callable
        self._live_reader = live_reader

    def run(
        self,
        request: SandboxRunRequest,
        *,
        context: Optional[SandboxContext] = None,
        emit_promotion_receipt: bool = True,
    ) -> SandboxRunResult:
        ctx = context or SandboxContext.create(
            config_overlay=dict(request.config_overlay or {}),
            agent_variant_id=request.agent_variant_id,
            language=request.language,
        )
        if (
            ctx.agent_variant_id != request.agent_variant_id
            or dict(ctx.config_overlay) != dict(request.config_overlay or {})
        ):
            ctx = SandboxContext.create(
                clock=ctx.clock.snapshot(),
                data_mode=ctx.data_mode,
                snapshot=dict(ctx.snapshot),
                config_overlay=dict(request.config_overlay or {}),
                agent_variant_id=request.agent_variant_id,
                source_data_window=(
                    dict(ctx.source_data_window)
                    if ctx.source_data_window is not None
                    else None
                ),
                language=request.language or ctx.language,
                sandbox_run_id=ctx.sandbox_run_id,
            )

        with active_sandbox_context(ctx) as active:
            data = SandboxDataAccess(context=active, live_reader=self._live_reader)
            try:
                raw = dict(self._variant_callable(request, active, data) or {})
                success = bool(raw.get("success", True))
                content = _ensure_simulation_label(
                    str(raw.get("content") or ""),
                    banner=active.banner(),
                )
                events = list(raw.get("events") or ())
                tool_calls = list(raw.get("tool_calls") or ())
                simulated_actions = list(raw.get("simulated_actions") or ())
                rejected_actions = list(raw.get("rejected_actions") or ())
                error = (
                    str(raw["error"]) if raw.get("error") is not None else None
                )
                if not success and error is None:
                    error = "sandbox_variant_failed"
            except Exception as exc:  # noqa: BLE001 — surface as labeled failure
                success = False
                content = _ensure_simulation_label(
                    f"Sandbox variant error: {exc}",
                    banner=active.banner(),
                )
                events = []
                tool_calls = []
                simulated_actions = []
                rejected_actions = []
                error = str(exc)
                raw = {"exception_type": type(exc).__name__}

            blocked = [item.to_dict() for item in get_blocked_external_effects()]
            if not simulated_actions:
                simulated_actions = [
                    {
                        "action": "sandbox_variant_run",
                        "agent_variant_id": active.agent_variant_id,
                        "simulation": True,
                    }
                ]

            trace = build_sandbox_trace(
                active,
                events=events,
                tool_calls=tool_calls,
                simulated_actions=simulated_actions,
                blocked_external_effects=blocked,
                rejected_actions=rejected_actions,
                metadata={
                    "prompt_present": bool(request.prompt),
                    "stock_code": request.stock_code,
                    "market": request.market,
                    **dict(request.metadata or {}),
                },
            )
            receipt = None
            if emit_promotion_receipt:
                receipt = build_promotion_receipt(
                    context=active,
                    trace=trace,
                    simulated_actions=simulated_actions,
                    blocked_external_effects=blocked,
                    rejected_actions=rejected_actions,
                )
            return SandboxRunResult(
                success=success,
                content=content,
                context=active,
                trace=trace,
                simulated_actions=tuple(dict(item) for item in simulated_actions),
                rejected_actions=tuple(dict(item) for item in rejected_actions),
                blocked_external_effects=tuple(blocked),
                promotion_receipt=receipt,
                error=error,
                raw=raw,
            )

    def compare_variants(
        self,
        request: SandboxRunRequest,
        variants: Sequence[Mapping[str, Any]],
        *,
        base_context: Optional[SandboxContext] = None,
    ) -> List[SandboxRunResult]:
        """Run the same prompt under multiple agent config variants."""
        if len(variants) < 1:
            raise ValueError("variants must contain at least one config")
        results: List[SandboxRunResult] = []
        for index, variant in enumerate(variants):
            variant_id = str(
                variant.get("agent_variant_id")
                or variant.get("id")
                or f"variant-{index + 1}"
            )
            overlay = dict(
                variant.get("config_overlay") or variant.get("config") or {}
            )
            per_request = SandboxRunRequest(
                prompt=request.prompt,
                agent_variant_id=variant_id,
                config_overlay=overlay,
                stock_code=request.stock_code,
                market=request.market,
                language=request.language,
                metadata={
                    **dict(request.metadata or {}),
                    "comparison_index": index,
                    "comparison_size": len(variants),
                },
            )
            ctx = None
            if base_context is not None:
                ctx = SandboxContext.create(
                    clock=base_context.clock.snapshot(),
                    data_mode=base_context.data_mode,
                    snapshot=dict(base_context.snapshot),
                    config_overlay=overlay,
                    agent_variant_id=variant_id,
                    source_data_window=(
                        dict(base_context.source_data_window)
                        if base_context.source_data_window is not None
                        else None
                    ),
                    language=request.language or base_context.language,
                )
            results.append(self.run(per_request, context=ctx))
        return results


def run_agent_variant_in_sandbox(
    request: SandboxRunRequest,
    *,
    context: Optional[SandboxContext] = None,
    variant_callable: Optional[VariantCallable] = None,
    live_reader: Optional[Callable[[str, Mapping[str, Any]], Any]] = None,
) -> SandboxRunResult:
    """Convenience wrapper for a single sandbox variant run."""
    return SandboxRunner(
        variant_callable=variant_callable,
        live_reader=live_reader,
    ).run(request, context=context)


def _default_variant_callable(
    request: SandboxRunRequest,
    context: SandboxContext,
    data: SandboxDataAccess,
) -> Mapping[str, Any]:
    """Deterministic no-LLM default used by unit tests and dry harnesses."""
    _ = data
    clock_now = context.clock.isoformat()
    return {
        "success": True,
        "content": (
            f"{context.banner()}\n"
            f"Sandbox agent variant {context.agent_variant_id!r} processed "
            f"prompt under config_digest={context.config_digest} at {clock_now}."
        ),
        "events": [
            {
                "event_type": "agent.phase_start",
                "name": "sandbox_variant",
                "sequence": 0,
                "timestamp": clock_now,
                "status": "ok",
            },
            {
                "event_type": "agent.decision",
                "name": "sandbox_decision",
                "sequence": 1,
                "timestamp": clock_now,
                "status": "simulated",
                "attrs": {
                    "agent_variant_id": context.agent_variant_id,
                    "simulation": True,
                },
            },
            {
                "event_type": "agent.phase_end",
                "name": "sandbox_variant",
                "sequence": 2,
                "timestamp": clock_now,
                "status": "ok",
            },
        ],
        "tool_calls": [],
        "simulated_actions": [
            {
                "action": "emit_simulation_decision",
                "agent_variant_id": context.agent_variant_id,
                "prompt_excerpt": (request.prompt or "")[:120],
                "simulation": True,
            }
        ],
        "rejected_actions": [],
    }


def _ensure_simulation_label(content: str, *, banner: str) -> str:
    text = content or ""
    if SIMULATION_LABEL in text or "[模拟]" in text or banner in text:
        return text
    if not text.strip():
        return banner
    return f"{banner}\n{text}"
