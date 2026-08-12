# -*- coding: utf-8 -*-
"""Promotion receipt builder (review required, never auto-authority).

A passing sandbox run produces a reviewable evidence receipt. It never
grants production execution authority. First-live-run guard and human or
explicit-rule review remain mandatory (Issue #247 acceptance).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.agent.sandbox.context import SandboxContext, validate_sandbox_json
from src.agent.sandbox.policy import SANDBOX_MODE, SIMULATION_LABEL
from src.agent.sandbox.trace import SandboxTrace
from src.utils.sanitize import redact_sensitive_data, redact_sensitive_text

PROMOTION_RECEIPT_SCHEMA_VERSION = "sandbox-promotion-receipt-v1"

VALID_ASSUMPTION_CLASSES = frozenset({"observed", "inferred", "not_checked"})
VALID_FIRST_LIVE_GUARDS = frozenset(
    {"notification_only", "small_scope", "human_approval_required"}
)

_FAIL_CLOSED_RISK_BOUNDARY = {
    "force_paper_only": True,
    "allow_real_orders": False,
    "allow_real_notifications": False,
}
_NO_PRODUCTION_AUTHORITY_SCOPE = {
    "may_touch": [],
    "may_not_touch": [
        "decision_signal",
        "decision_memory",
        "real_notification",
        "real_order",
        "production_portfolio",
    ],
    "declared": False,
}


@dataclass(frozen=True)
class PromotionReceipt:
    """Reviewable promotion artifact — never an automatic release token."""

    schema_version: str
    sandbox_run_id: str
    source_data_window: Optional[Mapping[str, Any]]
    config_digest: str
    agent_variant_id: str
    simulated_actions: tuple
    blocked_external_effects: tuple
    assumptions: tuple
    rejected_actions: tuple
    risk_boundary: Mapping[str, Any]
    production_authority_scope: Mapping[str, Any]
    first_live_run_guard: str
    rollback_condition: str
    review_required: bool = True
    auto_promote: bool = False
    label: str = SIMULATION_LABEL
    mode: str = SANDBOX_MODE
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sandbox_run_id": self.sandbox_run_id,
            "source_data_window": (
                dict(self.source_data_window)
                if self.source_data_window is not None
                else None
            ),
            "config_digest": self.config_digest,
            "agent_variant_id": self.agent_variant_id,
            "simulated_actions": [dict(item) for item in self.simulated_actions],
            "blocked_external_effects": [
                dict(item) for item in self.blocked_external_effects
            ],
            "assumptions": [dict(item) for item in self.assumptions],
            "rejected_actions": [dict(item) for item in self.rejected_actions],
            "risk_boundary": dict(self.risk_boundary),
            "production_authority_scope": dict(self.production_authority_scope),
            "first_live_run_guard": self.first_live_run_guard,
            "rollback_condition": self.rollback_condition,
            "review_required": self.review_required,
            "auto_promote": self.auto_promote,
            "label": self.label,
            "mode": self.mode,
            "simulation": True,
            "metadata": dict(self.metadata),
        }


def build_promotion_receipt(
    *,
    context: SandboxContext,
    trace: Optional[SandboxTrace] = None,
    simulated_actions: Optional[Sequence[Mapping[str, Any]]] = None,
    blocked_external_effects: Optional[Sequence[Mapping[str, Any]]] = None,
    rejected_actions: Optional[Sequence[Mapping[str, Any]]] = None,
    assumptions: Optional[Sequence[Mapping[str, Any]]] = None,
    risk_boundary: Optional[Mapping[str, Any]] = None,
    production_authority_scope: Optional[Mapping[str, Any]] = None,
    first_live_run_guard: str = "human_approval_required",
    rollback_condition: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> PromotionReceipt:
    """Build a complete promotion receipt; always review-gated."""
    guard = str(first_live_run_guard or "human_approval_required").strip()
    if guard not in VALID_FIRST_LIVE_GUARDS:
        raise ValueError(
            f"first_live_run_guard must be one of {sorted(VALID_FIRST_LIVE_GUARDS)}"
        )
    if risk_boundary is not None and dict(risk_boundary) != _FAIL_CLOSED_RISK_BOUNDARY:
        raise ValueError("risk_boundary cannot grant or alter production authority")
    if (
        production_authority_scope is not None
        and dict(production_authority_scope) != _NO_PRODUCTION_AUTHORITY_SCOPE
    ):
        raise ValueError(
            "production_authority_scope must remain explicitly empty and undeclared"
        )

    normalized_assumptions = _normalize_assumptions(assumptions)
    actions = list(simulated_actions or ())
    blocked = list(blocked_external_effects or ())
    rejected = list(rejected_actions or ())
    if trace is not None:
        if not actions:
            actions = list(trace.simulated_actions)
        if not blocked:
            blocked = list(trace.blocked_external_effects)
        if not rejected:
            rejected = list(trace.rejected_actions)
    actions = _redacted_mapping_rows(actions, "simulated_actions")
    blocked = _redacted_mapping_rows(blocked, "blocked_external_effects")
    rejected = _redacted_mapping_rows(rejected, "rejected_actions")
    validate_sandbox_json(metadata or {}, field_name="promotion.metadata")
    safe_metadata = redact_sensitive_data(dict(metadata or {}))
    if not isinstance(safe_metadata, Mapping):
        raise ValueError("promotion.metadata could not be safely serialized")
    public_source_window = context.public_metadata()["source_data_window"]

    return PromotionReceipt(
        schema_version=PROMOTION_RECEIPT_SCHEMA_VERSION,
        sandbox_run_id=context.sandbox_run_id,
        source_data_window=public_source_window,
        config_digest=context.config_digest,
        agent_variant_id=context.agent_variant_id,
        simulated_actions=tuple(dict(item) for item in actions),
        blocked_external_effects=tuple(dict(item) for item in blocked),
        assumptions=tuple(normalized_assumptions),
        rejected_actions=tuple(dict(item) for item in rejected),
        risk_boundary=dict(_FAIL_CLOSED_RISK_BOUNDARY),
        production_authority_scope=dict(_NO_PRODUCTION_AUTHORITY_SCOPE),
        first_live_run_guard=guard,
        rollback_condition=redact_sensitive_text(
            rollback_condition
            or (
                "Reopen sandbox review if live readback diverges from sandbox "
                "trace outcomes, blocked-effect set, or assumption classifications."
            )
        )[:1000],
        review_required=True,
        auto_promote=False,
        metadata={
            "trace_schema_version": (
                trace.schema_version if trace is not None else None
            ),
            "data_mode": context.data_mode,
            **dict(safe_metadata),
        },
    )


def _normalize_assumptions(
    assumptions: Optional[Sequence[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    if not assumptions:
        return [
            {
                "name": "production_write_fence",
                "classification": "observed",
                "detail": "Sandbox external-effect fence is active for this run.",
            },
            {
                "name": "live_market_completeness",
                "classification": "not_checked",
                "detail": "Sandbox does not assert full live market coverage.",
            },
        ]
    out: List[Dict[str, Any]] = []
    for item in assumptions:
        if not isinstance(item, Mapping):
            continue
        classification = str(item.get("classification") or "not_checked")
        if classification not in VALID_ASSUMPTION_CLASSES:
            classification = "not_checked"
        out.append(
            {
                "name": redact_sensitive_text(item.get("name") or "assumption")[:160],
                "classification": classification,
                "detail": redact_sensitive_text(item.get("detail") or "")[:1000],
            }
        )
    return out


def _redacted_mapping_rows(
    values: Sequence[Mapping[str, Any]],
    field_name: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, item in enumerate(values):
        if not isinstance(item, Mapping):
            raise ValueError(f"{field_name}[{index}] must be a mapping")
        validate_sandbox_json(item, field_name=f"{field_name}[{index}]")
        safe_item = redact_sensitive_data(dict(item))
        if not isinstance(safe_item, Mapping):
            raise ValueError(
                f"{field_name}[{index}] could not be safely serialized"
            )
        rows.append(dict(safe_item))
    validate_sandbox_json(rows, field_name=field_name)
    return rows
