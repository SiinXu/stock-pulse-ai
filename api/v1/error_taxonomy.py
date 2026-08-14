# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Canonical API error taxonomy for stable codes.

Integrates with existing ``error`` codes in the version-one envelope: callers
keep emitting the same machine-readable ``error`` string; this module maps each
known code to a category, severity, and default user action. Unknown codes fall
back to ``internal`` so envelopes stay classifiable without inventing new codes.

See docs/api-error-taxonomy.md (EN: docs/api-error-taxonomy_EN.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Literal, Mapping, Optional

ErrorCategory = Literal[
    "auth",
    "credential",
    "rate_quota",
    "provider_network",
    "timeout",
    "validation",
    "busy",
    "config_conflict",
    "capability",
    "notification",
    "not_found",
    "outbound_policy",
    "internal",
]

ErrorSeverity = Literal["info", "warning", "error", "critical"]
ErrorAction = Literal["retry", "settings", "login", "docs", "none"]

ERROR_CATEGORIES: FrozenSet[str] = frozenset({
    "auth", "credential", "rate_quota", "provider_network", "timeout",
    "validation", "busy", "config_conflict", "capability", "notification",
    "not_found", "outbound_policy", "internal",
})
ERROR_SEVERITIES: FrozenSet[str] = frozenset({"info", "warning", "error", "critical"})
ERROR_ACTIONS: FrozenSet[str] = frozenset({"retry", "settings", "login", "docs", "none"})

_DOCS_LLM = "docs/LLM_CONFIG_GUIDE.md"
_DOCS_BEGINNER = "docs/beginner-client-setup.md"
_DOCS_LOCAL_ONLY = "docs/local-only-mode.md"
_DOCS_SECURITY = "docs/security-baseline.md"


@dataclass(frozen=True)
class ErrorClassification:
    category: ErrorCategory
    severity: ErrorSeverity
    default_action: ErrorAction
    docs_path: Optional[str] = None


def _entry(
    category: ErrorCategory,
    severity: ErrorSeverity,
    default_action: ErrorAction,
    docs_path: Optional[str] = None,
) -> ErrorClassification:
    return ErrorClassification(category, severity, default_action, docs_path)


ERROR_CODE_TAXONOMY: Mapping[str, ErrorClassification] = {
    "unauthorized": _entry("auth", "error", "login"),
    "auth_disabled": _entry("auth", "error", "settings", _DOCS_SECURITY),
    "security_audit_auth_required": _entry("auth", "error", "settings", _DOCS_SECURITY),
    "reasoning_trace_auth_required": _entry("auth", "error", "settings", _DOCS_SECURITY),
    "audit_export_auth_required": _entry("auth", "error", "settings", _DOCS_SECURITY),
    "evidence_chain_auth_required": _entry("auth", "error", "settings", _DOCS_SECURITY),
    "research_pack_auth_required": _entry("auth", "error", "settings", _DOCS_SECURITY),
    "env_backup_access_denied": _entry("auth", "error", "settings"),
    "approval_auth_required": _entry("auth", "error", "settings", _DOCS_SECURITY),
    "password_required": _entry("credential", "error", "retry"),
    "current_required": _entry("credential", "error", "retry"),
    "password_mismatch": _entry("credential", "error", "retry"),
    "password_already_set": _entry("credential", "warning", "settings"),
    "invalid_password": _entry("credential", "error", "login"),
    "not_changeable": _entry("credential", "warning", "docs", _DOCS_BEGINNER),
    "rate_limited": _entry("rate_quota", "warning", "retry"),
    "quota_exceeded": _entry("rate_quota", "error", "docs", _DOCS_LLM),
    "insufficient_balance": _entry("rate_quota", "error", "docs", _DOCS_LLM),
    "rate_limit": _entry("rate_quota", "warning", "retry"),
    "upstream_network": _entry("provider_network", "error", "retry"),
    "local_connection_failed": _entry("provider_network", "error", "retry"),
    "network_error": _entry("provider_network", "error", "retry"),
    "dns_error": _entry("provider_network", "error", "retry"),
    "connection_refused": _entry("provider_network", "error", "retry"),
    "tls_error": _entry("provider_network", "error", "retry"),
    "alphasift_screen_failed": _entry("provider_network", "error", "retry"),
    "agent_stream_failed": _entry("provider_network", "error", "retry"),
    "provider_failure": _entry("provider_network", "error", "retry"),
    "upstream_timeout": _entry("timeout", "warning", "retry"),
    "timeout": _entry("timeout", "warning", "retry"),
    "agent_stream_timeout": _entry("timeout", "warning", "retry"),
    "validation_error": _entry("validation", "error", "none"),
    "invalid_params": _entry("validation", "error", "none"),
    "validation_failed": _entry("validation", "error", "none"),
    "invalid_import_file": _entry("validation", "error", "none"),
    "unsupported_alert_type": _entry("validation", "error", "none"),
    "operation_id_mismatch": _entry("validation", "error", "none"),
    "api_response_validation_failed": _entry("validation", "error", "retry"),
    "invalid_stock_or_name": _entry("validation", "error", "none"),
    "missing_stock_params": _entry("validation", "error", "none"),
    "analysis_batch_limit_exceeded": _entry("validation", "error", "none"),
    "empty_stock_code": _entry("validation", "error", "none"),
    "sync_mode_batch_unsupported": _entry("validation", "error", "none"),
    "invalid_stock_code": _entry("validation", "error", "none"),
    "missing_upload_file": _entry("validation", "error", "none"),
    "missing_import_text": _entry("validation", "error", "none"),
    "unsupported_type": _entry("validation", "error", "none"),
    "unsupported_content_type": _entry("validation", "error", "none"),
    "file_too_large": _entry("validation", "error", "none"),
    "portfolio_oversell": _entry("validation", "error", "none"),
    "duplicate_task": _entry("busy", "warning", "none"),
    "duplicate_market_review": _entry("busy", "warning", "none"),
    "scheduler_busy": _entry("busy", "warning", "retry"),
    "portfolio_busy": _entry("busy", "warning", "retry"),
    "config_conflict": _entry("config_conflict", "warning", "retry"),
    "config_version_conflict": _entry("config_conflict", "warning", "retry"),
    "conflict": _entry("config_conflict", "warning", "retry"),
    "idempotency_conflict": _entry("config_conflict", "warning", "retry"),
    "agent_disabled": _entry("capability", "error", "settings"),
    "llm_not_configured": _entry("capability", "error", "settings", _DOCS_LLM),
    "model_tool_incompatible": _entry("capability", "error", "settings", _DOCS_LLM),
    "invalid_tool_call": _entry("capability", "error", "settings", _DOCS_LLM),
    "alphasift_disabled": _entry("capability", "error", "settings"),
    "alphasift_unavailable": _entry("capability", "error", "settings"),
    "alphasift_install_failed": _entry("capability", "error", "settings"),
    "alphasift_install_spec_missing": _entry("capability", "error", "settings"),
    "alphasift_install_spec_not_allowed": _entry("capability", "error", "settings"),
    "alphasift_adapter_unavailable": _entry("capability", "error", "settings"),
    "capability_unsupported": _entry("capability", "error", "docs", _DOCS_BEGINNER),
    "reasoning_trace_export_disabled": _entry("capability", "warning", "settings"),
    "audit_export_disabled": _entry("capability", "warning", "settings"),
    "evidence_chain_disabled": _entry("capability", "warning", "settings"),
    "research_pack_export_disabled": _entry("capability", "warning", "settings"),
    "research_pack_limit_exceeded": _entry("capability", "warning", "settings"),
    "share_image_content_too_large": _entry("capability", "warning", "settings"),
    "share_image_unavailable": _entry("capability", "warning", "docs", _DOCS_BEGINNER),
    "rollback_unavailable": _entry("capability", "warning", "none"),
    "no_channels": _entry("notification", "error", "settings"),
    "notification_channel_test_failed": _entry("notification", "error", "settings"),
    "config_missing": _entry("notification", "error", "settings"),
    "config_invalid": _entry("notification", "error", "settings"),
    "send_failed": _entry("notification", "error", "retry"),
    "not_found": _entry("not_found", "warning", "none"),
    "alphasift_screen_task_not_found": _entry("not_found", "warning", "retry"),
    "security_audit_unavailable": _entry("not_found", "error", "retry"),
    "local_only_mode_blocked": _entry("outbound_policy", "error", "settings", _DOCS_LOCAL_ONLY),
    "metadata_host_blocked": _entry("outbound_policy", "error", "settings", _DOCS_LOCAL_ONLY),
    "local_host_blocked": _entry("outbound_policy", "error", "settings", _DOCS_LOCAL_ONLY),
    "restricted_ip_blocked": _entry("outbound_policy", "error", "settings", _DOCS_LOCAL_ONLY),
    "private_ip_blocked": _entry("outbound_policy", "error", "settings", _DOCS_LOCAL_ONLY),
    "ssrf_blocked": _entry("outbound_policy", "error", "settings", _DOCS_SECURITY),
    "private_dns_address": _entry("outbound_policy", "error", "settings", _DOCS_LOCAL_ONLY),
    "dns_resolution_failed": _entry("outbound_policy", "error", "retry"),
    "unexpected_dns_target": _entry("outbound_policy", "error", "settings", _DOCS_SECURITY),
    "request_blocked": _entry("outbound_policy", "error", "settings", _DOCS_SECURITY),
    "provider_blocked": _entry("outbound_policy", "error", "settings", _DOCS_LOCAL_ONLY),
    "agent_chat_failed": _entry("provider_network", "error", "retry"),
    "agent_research_failed": _entry("provider_network", "error", "retry"),
    "analysis_failed": _entry("internal", "error", "retry"),
    "internal_error": _entry("internal", "critical", "retry"),
}

UNKNOWN_ERROR_CLASSIFICATION = _entry("internal", "error", "retry")


def normalize_error_code(code: Optional[str]) -> str:
    if code is None:
        return "unknown_error"
    trimmed = str(code).strip()
    return trimmed or "unknown_error"


def classify_error_code(code: Optional[str]) -> ErrorClassification:
    return ERROR_CODE_TAXONOMY.get(normalize_error_code(code), UNKNOWN_ERROR_CLASSIFICATION)


def is_classified_error_code(code: Optional[str]) -> bool:
    return normalize_error_code(code) in ERROR_CODE_TAXONOMY


def taxonomy_fields_for_code(code: Optional[str]) -> Dict[str, str]:
    classification = classify_error_code(code)
    return {"category": classification.category, "severity": classification.severity}


def registered_error_codes() -> FrozenSet[str]:
    return frozenset(ERROR_CODE_TAXONOMY.keys())
