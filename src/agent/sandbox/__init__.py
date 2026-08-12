# -*- coding: utf-8 -*-
"""Safe simulation sandbox for agent and strategy experiments.

Division of labor (Issues #247 / #202 / #442 vs backtest V30):

- **Sandbox** owns simulation context and repository-level safety: isolated
  config, fake clock, read-only or snapshot data, SIMULATION labels, and hard
  fences that block known production DecisionSignal / decision-memory /
  notification / portfolio writes.
- **Backtest** owns historical validation methodology (forward windows,
  engine versioning, performance metrics over analysis history).

This in-process runner accepts trusted callables and is not an OS or ToolSurface
security boundary. Passing a run never grants production authority; promotion
produces a reviewable receipt only.
"""

from __future__ import annotations

from src.agent.sandbox.clock import FakeClock
from src.agent.sandbox.context import (
    SandboxContext,
    SandboxDataMode,
    active_sandbox_context,
    get_active_sandbox,
    is_sandbox_active,
    require_sandbox_inactive_for_production_write,
)
from src.agent.sandbox.data_access import SandboxDataAccess, SandboxDataAccessError
from src.agent.sandbox.effects import (
    BlockedExternalEffect,
    ExternalEffectFence,
    SandboxExternalEffectBlocked,
    get_blocked_external_effects,
)
from src.agent.sandbox.policy import (
    SANDBOX_ISOLATION_POLICY,
    SIMULATION_BANNER_EN,
    SIMULATION_BANNER_ZH,
    SIMULATION_LABEL,
    SANDBOX_MODE,
    get_sandbox_isolation_policy,
)
from src.agent.sandbox.promotion import (
    PROMOTION_RECEIPT_SCHEMA_VERSION,
    PromotionReceipt,
    build_promotion_receipt,
)
from src.agent.sandbox.runner import (
    SandboxRunRequest,
    SandboxRunResult,
    SandboxRunner,
    run_agent_variant_in_sandbox,
)
from src.agent.sandbox.trace import (
    SANDBOX_TRACE_SCHEMA_VERSION,
    SandboxTrace,
    SandboxTraceEvent,
    build_sandbox_trace,
)

__all__ = (
    "BlockedExternalEffect",
    "ExternalEffectFence",
    "FakeClock",
    "PROMOTION_RECEIPT_SCHEMA_VERSION",
    "PromotionReceipt",
    "SANDBOX_ISOLATION_POLICY",
    "SANDBOX_MODE",
    "SANDBOX_TRACE_SCHEMA_VERSION",
    "SIMULATION_BANNER_EN",
    "SIMULATION_BANNER_ZH",
    "SIMULATION_LABEL",
    "SandboxContext",
    "SandboxDataAccess",
    "SandboxDataAccessError",
    "SandboxDataMode",
    "SandboxExternalEffectBlocked",
    "SandboxRunRequest",
    "SandboxRunResult",
    "SandboxRunner",
    "SandboxTrace",
    "SandboxTraceEvent",
    "active_sandbox_context",
    "build_promotion_receipt",
    "build_sandbox_trace",
    "get_active_sandbox",
    "get_blocked_external_effects",
    "get_sandbox_isolation_policy",
    "is_sandbox_active",
    "require_sandbox_inactive_for_production_write",
    "run_agent_variant_in_sandbox",
)
