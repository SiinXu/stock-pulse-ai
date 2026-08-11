# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Agent-guided onboarding: rule-based profile → plan → non-secret config apply.

Design notes
------------
* Rule-based plan generation is the **default and authoritative** engine.
* LLM refinement is never invented: when no model is available the plan stays
  ``engine="rules"`` with an honest ``llm_note``. Prefer-LLM never fabricates
  secrets or fake "AI" output.
* Config writes always go through :class:`SystemConfigService.update`.
* Secret-bearing keys are rejected at plan and apply time.
* Built-in preset config maps mirror W10-03 official presets so this service
  stays useful before #819 merges; when ``src.services.config_presets`` is
  importable we reuse it instead of duplicating catalog data.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.report_language import SUPPORTED_REPORT_LANGUAGES
from src.services.demo_analysis_fixture import build_demo_analysis
from src.services.local_runtime_detect import (
    LocalRuntimeDetectResult,
    detect_local_runtime_from_config_map,
)
from src.services.system_config_service import (
    ConfigConflictError,
    ConfigValidationError,
    SystemConfigService,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

PROFILE_SCHEMA_VERSION = 1
PLAN_SCHEMA_VERSION = 1
FIRST_RUN_READINESS_SCHEMA_VERSION = 1
ONBOARDING_STATE_FILENAME = "onboarding_state.json"

_LEGACY_PRIMARY_MODEL_KEYS = frozenset(
    {
        "GEMINI_MODEL",
        "ANTHROPIC_MODEL",
        "OPENAI_MODEL",
        "OLLAMA_MODEL",
        "ANSPIRE_LLM_MODEL",
    }
)

_FRESH_ENV_IGNORED_KEYS = frozenset(
    {
        "ADMIN_AUTH_ENABLED",
        "DATABASE_PATH",
        "ENV_FILE",
        "HOST",
        "PORT",
        "LOG_LEVEL",
        "LOG_DIR",
        "LOCAL_RUNTIME_AUTO_DETECT",
        "LOCAL_RUNTIME_DETECT_TIMEOUT_SECONDS",
    }
)

EXPERIENCE_STAGES = frozenset({"beginner", "report_reader", "has_system"})
MARKETS = frozenset({"cn", "hk", "us"})
GOALS = frozenset(
    {
        "daily_push",
        "pre_post_market",
        "holdings_risk",
        "strategy_validation",
    }
)
HOLDINGS = frozenset({"none", "watchlist", "bookkeeping"})
INTERACTIONS = frozenset({"push", "web", "chat"})
RISK_TONES = frozenset({"conservative", "balanced", "assertive"})
INFRASTRUCTURES = frozenset({"cloud_key", "local_models", "free_only"})
REPORT_LANGUAGES = frozenset(SUPPORTED_REPORT_LANGUAGES)

FEATURE_STAGES = ("L0", "L1", "L2", "L3")

_SECRET_KEY_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")
_SECRET_KEY_SUFFIXES = ("_EXTRA_HEADERS",)
_SECRET_KEY_EXACT = frozenset({"LITELLM_CONFIG"})

# Seed symbols used only when STOCK_LIST is empty (never overwrite a user list).
_MARKET_SEED_SYMBOLS: Dict[str, str] = {
    "cn": "600519",
    "hk": "hk00700",
    "us": "AAPL",
}

# Fallback preset config maps aligned with W10-03 (#819). Prefer live catalog.
_FALLBACK_PRESET_CONFIG: Dict[str, Dict[str, str]] = {
    "local-first": {
        "GENERATION_BACKEND": "litellm",
        "GENERATION_FALLBACK_BACKEND": "litellm",
        "LLM_CONFIG_MODE": "channels",
        "LLM_OLLAMA_PROVIDER": "ollama",
        "LLM_OLLAMA_PROTOCOL": "ollama",
        "LLM_OLLAMA_ENABLED": "true",
        "LLM_OLLAMA_DISPLAY_NAME": "Ollama (local)",
        "AGENT_GENERATION_BACKEND": "auto",
    },
    "cli-backends": {
        "GENERATION_BACKEND": "codex_cli",
        "GENERATION_FALLBACK_BACKEND": "litellm",
        "AGENT_FEATURES_ACKNOWLEDGED_OFF": "true",
        "AGENT_GENERATION_BACKEND": "auto",
    },
    "cloud-balanced": {
        "GENERATION_BACKEND": "litellm",
        "GENERATION_FALLBACK_BACKEND": "litellm",
        "LLM_CONFIG_MODE": "channels",
        "AGENT_GENERATION_BACKEND": "auto",
        "NEWS_STRATEGY_PROFILE": "short",
    },
    "power-user": {
        "LLM_CONFIG_MODE": "auto",
    },
}

_FALLBACK_PRESET_META: Dict[str, Dict[str, Any]] = {
    "local-first": {
        "display_name": "Local-first (Ollama / Model Pack)",
        "beginner_mode": True,
    },
    "cli-backends": {
        "display_name": "CLI backends (Codex / Claude Code / OpenCode)",
        "beginner_mode": True,
    },
    "cloud-balanced": {
        "display_name": "Cloud balanced",
        "beginner_mode": True,
    },
    "power-user": {
        "display_name": "Custom / advanced",
        "beginner_mode": False,
    },
}


class OnboardingPlanError(Exception):
    """Base domain error for onboarding plan operations."""

    error_code = "onboarding_plan_error"

    def __init__(self, message: str, *, error_code: Optional[str] = None) -> None:
        super().__init__(message)
        if error_code:
            self.error_code = error_code


class OnboardingProfileValidationError(OnboardingPlanError):
    """Raised when the intake profile fails schema validation."""

    error_code = "onboarding_profile_invalid"

    def __init__(
        self,
        message: str,
        *,
        issues: Optional[Sequence[Mapping[str, Any]]] = None,
        error_code: Optional[str] = None,
    ) -> None:
        super().__init__(message, error_code=error_code)
        self.issues = [dict(item) for item in (issues or ())]


class OnboardingSecretRejectedError(OnboardingPlanError):
    """Raised when a secret-bearing key would be written by onboarding."""

    error_code = "onboarding_secret_rejected"


def is_secret_config_key(key: str) -> bool:
    """Return True when a config key must never be written by onboarding."""
    normalized = str(key or "").strip().upper()
    if not normalized:
        return True
    if normalized in _SECRET_KEY_EXACT:
        return True
    if any(normalized.endswith(suffix) for suffix in _SECRET_KEY_SUFFIXES):
        return True
    if any(marker in normalized for marker in _SECRET_KEY_MARKERS):
        return True
    return False


def is_fresh_environment(
    config_map: Mapping[str, str] | None,
    *,
    onboarding_applied: bool = False,
) -> bool:
    """Return True only when we are confident this install has no prior product setup.

    Conservative by design: any evidence of prior configuration returns False so
    existing users are never force-switched into beginner first-run defaults.
    """
    if onboarding_applied:
        return False
    values = {
        str(key).strip().upper(): str(value or "").strip()
        for key, value in dict(config_map or {}).items()
    }
    if not values:
        return True
    for key, value in values.items():
        if not value:
            continue
        if key in _FRESH_ENV_IGNORED_KEYS:
            continue
        if is_secret_config_key(key):
            return False
        if key in {
            "STOCK_LIST",
            "REPORT_LANGUAGE",
            "GENERATION_BACKEND",
            "GENERATION_FALLBACK_BACKEND",
            "LLM_CONFIG_MODE",
            "NEWS_STRATEGY_PROFILE",
            "LLM_OLLAMA_ENABLED",
            "LLM_OLLAMA_BASE_URL",
            "LLM_OLLAMA_DISPLAY_NAME",
            "MARKET_REVIEW_ENABLED",
            "MARKET_REVIEW_REGION",
        }:
            return False
        return False
    return True


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _snapshot_id(payload: Mapping[str, Any]) -> str:
    """Return a stable identifier for one bounded readiness projection."""
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _normalize_string_list(
    values: Any,
    *,
    allowed: frozenset[str],
    field_name: str,
    required: bool = False,
) -> List[str]:
    if values is None:
        values = []
    if not isinstance(values, (list, tuple)):
        raise OnboardingProfileValidationError(
            f"{field_name} must be a list",
            issues=[{"field": field_name, "code": "type_error", "message": "expected list"}],
        )
    normalized: List[str] = []
    seen: set[str] = set()
    for raw in values:
        item = str(raw or "").strip().lower()
        if not item:
            continue
        if item not in allowed:
            raise OnboardingProfileValidationError(
                f"Invalid {field_name} value: {item}",
                issues=[{
                    "field": field_name,
                    "code": "enum_error",
                    "message": f"unsupported value {item}",
                    "allowed": sorted(allowed),
                }],
            )
        if item not in seen:
            seen.add(item)
            normalized.append(item)
    if required and not normalized:
        raise OnboardingProfileValidationError(
            f"{field_name} requires at least one value",
            issues=[{"field": field_name, "code": "required", "message": "empty"}],
        )
    return normalized


def _normalize_enum(value: Any, *, allowed: frozenset[str], field_name: str, default: str) -> str:
    if value is None or str(value).strip() == "":
        return default
    item = str(value).strip().lower()
    if item not in allowed:
        raise OnboardingProfileValidationError(
            f"Invalid {field_name}: {item}",
            issues=[{
                "field": field_name,
                "code": "enum_error",
                "message": f"unsupported value {item}",
                "allowed": sorted(allowed),
            }],
        )
    return item


def normalize_profile(raw: Mapping[str, Any] | None) -> Dict[str, Any]:
    """Validate and normalize a versioned UserOnboardingProfile."""
    source = dict(raw or {})
    schema_version = int(source.get("schema_version") or PROFILE_SCHEMA_VERSION)
    if schema_version != PROFILE_SCHEMA_VERSION:
        raise OnboardingProfileValidationError(
            f"Unsupported profile schema_version: {schema_version}",
            issues=[{
                "field": "schema_version",
                "code": "unsupported_version",
                "message": f"expected {PROFILE_SCHEMA_VERSION}",
            }],
        )
    experience = _normalize_enum(
        source.get("experience_stage"),
        allowed=EXPERIENCE_STAGES,
        field_name="experience_stage",
        default="beginner",
    )
    markets = _normalize_string_list(
        source.get("markets"),
        allowed=MARKETS,
        field_name="markets",
        required=True,
    )
    goals = _normalize_string_list(source.get("goals"), allowed=GOALS, field_name="goals")
    holdings = _normalize_enum(
        source.get("holdings"),
        allowed=HOLDINGS,
        field_name="holdings",
        default="none",
    )
    interaction = _normalize_enum(
        source.get("interaction"),
        allowed=INTERACTIONS,
        field_name="interaction",
        default="web",
    )
    risk = _normalize_enum(
        source.get("risk_tone"),
        allowed=RISK_TONES,
        field_name="risk_tone",
        default="balanced",
    )
    infrastructure = _normalize_enum(
        source.get("infrastructure"),
        allowed=INFRASTRUCTURES,
        field_name="infrastructure",
        default="cloud_key",
    )
    report_language = _normalize_enum(
        source.get("report_language"),
        allowed=REPORT_LANGUAGES,
        field_name="report_language",
        default="zh",
    )
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "experience_stage": experience,
        "markets": markets,
        "goals": goals,
        "holdings": holdings,
        "interaction": interaction,
        "risk_tone": risk,
        "infrastructure": infrastructure,
        "report_language": report_language,
    }


def resolve_feature_stage(profile: Mapping[str, Any]) -> str:
    """Map intake answers to L0–L3 feature curve."""
    experience = str(profile.get("experience_stage") or "beginner")
    holdings = str(profile.get("holdings") or "none")
    interaction = str(profile.get("interaction") or "web")
    if experience == "beginner":
        return "L0"
    if experience == "report_reader":
        return "L1" if holdings in {"none", "watchlist"} else "L2"
    # has_system
    if interaction == "chat" or "strategy_validation" in (profile.get("goals") or []):
        return "L3"
    if holdings == "bookkeeping":
        return "L2"
    return "L1"


def resolve_preset_id(profile: Mapping[str, Any]) -> str:
    """Choose a recommended preset id from infrastructure + experience."""
    infrastructure = str(profile.get("infrastructure") or "cloud_key")
    experience = str(profile.get("experience_stage") or "beginner")
    if infrastructure == "local_models":
        return "local-first"
    if infrastructure == "free_only":
        # Free sources only: prefer local/cli without inventing cloud keys.
        return "cli-backends"
    if experience == "has_system":
        return "power-user"
    return "cloud-balanced"


def _load_preset_catalog() -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, Any]]]:
    """Prefer W10-03 config_presets when present; otherwise use fallback maps."""
    try:
        from src.services.config_presets import (  # type: ignore[attr-defined]
            get_official_preset,
            list_official_presets,
        )

        configs: Dict[str, Dict[str, str]] = {}
        meta: Dict[str, Dict[str, Any]] = {}
        for preset in list_official_presets():
            preset_id = str(preset.get("id") or "")
            if not preset_id:
                continue
            configs[preset_id] = {
                str(k).upper(): str(v)
                for k, v in dict(preset.get("config_values") or {}).items()
                if not is_secret_config_key(str(k))
            }
            features = dict(preset.get("features") or {})
            meta[preset_id] = {
                "display_name": str(preset.get("display_name") or preset_id),
                "beginner_mode": bool(features.get("beginner_mode", True)),
            }
        # Ensure fallback ids still resolve if catalog is partial.
        for preset_id, values in _FALLBACK_PRESET_CONFIG.items():
            configs.setdefault(preset_id, dict(values))
            meta.setdefault(preset_id, dict(_FALLBACK_PRESET_META[preset_id]))
        # Touch get_official_preset so static analyzers keep the import used.
        _ = get_official_preset
        return configs, meta
    except Exception as exc:  # broad-exception: fallback_recorded - presets module optional until #819
        log_safe_exception(
            logger,
            "Onboarding falling back to built-in preset maps",
            exc,
            error_code="onboarding_preset_fallback",
        )
        return (
            {key: dict(value) for key, value in _FALLBACK_PRESET_CONFIG.items()},
            {key: dict(value) for key, value in _FALLBACK_PRESET_META.items()},
        )


def _feature_path_for_stage(stage: str) -> Dict[str, Any]:
    paths: Dict[str, Dict[str, Any]] = {
        "L0": {
            "stage": "L0",
            "label": "Cold start",
            "primary_path": [
                "Configure a model channel or local backend",
                "Run one-symbol analysis from the watchlist seed",
                "Read the conclusion and risk sections of the report",
            ],
            "emphasize": ["home", "analysis_workbench", "settings_model_watchlist"],
            "defer": ["signal_center_full", "committee", "plugins", "multi_agent"],
        },
        "L1": {
            "stage": "L1",
            "label": "Daily reader",
            "primary_path": [
                "Batch the watchlist and open market review",
                "Configure notification test when ready",
                "Compare today's report with history",
            ],
            "emphasize": ["home", "history", "market_review", "notifications"],
            "defer": ["complex_alert_rules", "outcome_stats"],
        },
        "L2": {
            "stage": "L2",
            "label": "Holdings user",
            "primary_path": [
                "Import or bookkeep portfolio positions",
                "Review portfolio risk summary",
                "One-click analysis on held symbols",
            ],
            "emphasize": ["portfolio", "price_alerts", "analysis_workbench"],
            "defer": ["multi_agent", "custom_skills"],
        },
        "L3": {
            "stage": "L3",
            "label": "Research user",
            "primary_path": [
                "Use Agent chat for research questions",
                "Explore strategy Skills and the signal pool",
                "Run a lightweight backtest when ready",
            ],
            "emphasize": ["chat", "decision_signals", "backtest", "skills"],
            "defer": ["committee_high_cost_default_off"],
        },
    }
    return dict(paths.get(stage) or paths["L0"])


def _seed_stock_list(markets: Sequence[str]) -> str:
    seeds = [_MARKET_SEED_SYMBOLS[m] for m in markets if m in _MARKET_SEED_SYMBOLS]
    if not seeds:
        seeds = [_MARKET_SEED_SYMBOLS["cn"]]
    # Preserve market order, unique.
    seen: set[str] = set()
    ordered: List[str] = []
    for symbol in seeds:
        if symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)
    return ",".join(ordered)


def _market_review_region(markets: Sequence[str]) -> str:
    has_cn = "cn" in markets
    has_hk = "hk" in markets
    has_us = "us" in markets
    if has_cn and (has_hk or has_us):
        return "both"
    if has_cn:
        return "cn"
    return "both"


def _todo_items(profile: Mapping[str, Any], *, current: Mapping[str, str]) -> List[Dict[str, Any]]:
    todos: List[Dict[str, Any]] = []
    infrastructure = str(profile.get("infrastructure") or "cloud_key")
    has_primary = bool(
        (current.get("LITELLM_MODEL") or "").strip()
        or (current.get("LLM_CHANNELS") or "").strip()
        or (current.get("GENERATION_BACKEND") or "").strip()
        in {"codex_cli", "claude_code_cli", "opencode_cli"}
    )
    if not has_primary:
        if infrastructure == "cloud_key":
            todos.append({
                "id": "paste_cloud_key",
                "priority": 1,
                "title": "Paste a cloud provider API key",
                "description": (
                    "Onboarding never invents keys. Open Settings → AI model / "
                    "Connections and paste your provider credential."
                ),
                "href": "/settings?section=ai_model&source=onboarding",
                "kind": "secret_guide",
            })
        elif infrastructure == "local_models":
            todos.append({
                "id": "start_local_model",
                "priority": 1,
                "title": "Start a local model runtime",
                "description": (
                    "Enable Ollama or a Model Pack, then pick a ready local model. "
                    "No cloud API key is required for local-first."
                ),
                "href": "/settings?section=ai_model&source=onboarding",
                "kind": "setup",
            })
        else:
            todos.append({
                "id": "configure_cli_backend",
                "priority": 1,
                "title": "Configure a free/local generation backend",
                "description": (
                    "Use a local CLI backend or free data path. Secrets are never "
                    "auto-filled."
                ),
                "href": "/settings?section=ai_model&source=onboarding",
                "kind": "setup",
            })
    if not (current.get("STOCK_LIST") or "").strip():
        todos.append({
            "id": "confirm_watchlist",
            "priority": 2,
            "title": "Confirm the seed watchlist",
            "description": "A market-based seed list is proposed; edit it anytime in Settings.",
            "href": "/settings?section=base&source=onboarding",
            "kind": "config",
        })
    if "daily_push" in (profile.get("goals") or []) or str(profile.get("interaction")) == "push":
        todos.append({
            "id": "optional_notification",
            "priority": 3,
            "title": "Optional: test a notification channel",
            "description": "Notification credentials stay manual. Use Settings → Notifications to paste and test.",
            "href": "/settings?section=notification&source=onboarding",
            "kind": "secret_guide",
        })
    return todos


def _today_plan(stage: str, profile: Mapping[str, Any]) -> List[Dict[str, str]]:
    base = [
        {
            "id": "step_model",
            "title": "Finish model readiness",
            "detail": "Complete the secret checklist or local model step so analysis can run.",
        },
        {
            "id": "step_analyze",
            "title": "Analyze one watchlist symbol",
            "detail": "Open Analysis Workbench and run a single-symbol report.",
        },
        {
            "id": "step_read",
            "title": "Read conclusion and risk",
            "detail": "Focus on conclusion, risk, and evidence — not buy/sell orders.",
        },
    ]
    if stage in {"L1", "L2", "L3"}:
        base[1] = {
            "id": "step_analyze",
            "title": "Run watchlist batch or market review",
            "detail": "Use batch analysis or market review for daily rhythm.",
        }
    if stage in {"L2", "L3"} and str(profile.get("holdings")) == "bookkeeping":
        base.append({
            "id": "step_portfolio",
            "title": "Open Portfolio snapshot",
            "detail": "Import or bookkeep holdings after the first successful report.",
        })
    return base


def _week_plan(stage: str) -> List[Dict[str, str]]:
    return [
        {
            "day": "2",
            "title": "Compare with history",
            "detail": "Re-open yesterday's report and note what changed.",
        },
        {
            "day": "3",
            "title": "Notification test (optional)",
            "detail": "Only after you intentionally paste a channel credential.",
        },
        {
            "day": "4+",
            "title": "Unlock the next stage feature",
            "detail": {
                "L0": "Stay on Home + Analysis until the first successful report.",
                "L1": "Open market review regularly; keep advanced alerts deferred.",
                "L2": "Use Portfolio risk summary after holdings exist.",
                "L3": "Try Agent chat / signals when ready; leave committee off by default.",
            }.get(stage, "Follow the stage path without enabling high-cost modes by default."),
        },
    ]


class OnboardingPlanService:
    """Generate and apply agent-guided onboarding plans."""

    def __init__(
        self,
        *,
        system_config_service: SystemConfigService,
        state_path: Optional[Path] = None,
    ) -> None:
        self._system_config = system_config_service
        if state_path is not None:
            self._state_path = Path(state_path)
        else:
            env_path = getattr(getattr(system_config_service, "_manager", None), "env_path", None)
            base = Path(env_path).parent if env_path is not None else Path.cwd()
            self._state_path = base / ONBOARDING_STATE_FILENAME

    def _read_current_config_map(self) -> Dict[str, str]:
        raw = self._system_config._manager.read_config_map()  # noqa: SLF001 - intentional SCS reuse
        return {str(key).upper(): str(value) for key, value in raw.items()}

    def build_plan(
        self,
        raw_profile: Mapping[str, Any] | None,
        *,
        model_available: bool = False,
        prefer_llm: bool = False,
    ) -> Dict[str, Any]:
        """Build a deterministic, auditable config + learning plan from a profile."""
        profile = normalize_profile(raw_profile)
        current = self._read_current_config_map()
        feature_stage = resolve_feature_stage(profile)
        preset_id = resolve_preset_id(profile)
        preset_configs, preset_meta = _load_preset_catalog()
        preset_values = dict(preset_configs.get(preset_id) or {})
        meta = dict(preset_meta.get(preset_id) or {"display_name": preset_id, "beginner_mode": True})

        desired: Dict[str, str] = dict(preset_values)
        desired["REPORT_LANGUAGE"] = str(profile.get("report_language") or "zh")
        if "daily_push" in profile["goals"] or "pre_post_market" in profile["goals"]:
            desired["MARKET_REVIEW_ENABLED"] = "true"
            desired["MARKET_REVIEW_REGION"] = _market_review_region(profile["markets"])
        if not (current.get("STOCK_LIST") or "").strip():
            desired["STOCK_LIST"] = _seed_stock_list(profile["markets"])

        # Never include secrets in the plan.
        for key in list(desired.keys()):
            if is_secret_config_key(key):
                del desired[key]

        changes: List[Dict[str, str]] = []
        for key, new_value in sorted(desired.items()):
            old_value = current.get(key, "")
            if str(old_value) != str(new_value):
                changes.append({
                    "key": key,
                    "from": str(old_value),
                    "to": str(new_value),
                })

        engine = "rules"
        llm_note = (
            "Rule-based plan used. No model is configured, so LLM refinement was skipped."
            if prefer_llm and not model_available
            else (
                "Rule-based plan is authoritative. LLM refinement is available but optional "
                "and was not required for this deterministic plan."
                if prefer_llm and model_available
                else "Rule-based plan (default). LLM is optional and not required for onboarding."
            )
        )

        plan = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "engine": engine,
            "llm_note": llm_note,
            "model_available": bool(model_available),
            "prefer_llm": bool(prefer_llm),
            "profile": profile,
            "feature_stage": feature_stage,
            "feature_path": _feature_path_for_stage(feature_stage),
            "recommended_preset_id": preset_id,
            "recommended_preset_name": str(meta.get("display_name") or preset_id),
            "beginner_mode_recommended": bool(meta.get("beginner_mode", True)),
            "config_changes": changes,
            "config_items": [{"key": item["key"], "value": item["to"]} for item in changes],
            "todos": _todo_items(profile, current=current),
            "today_plan": _today_plan(feature_stage, profile),
            "week_plan": _week_plan(feature_stage),
            "disclaimer": (
                "StockPulse teaches product setup and research workflows. "
                "This plan never places buy/sell orders and never invents API keys."
            ),
            "generated_at": _utc_now_iso(),
        }
        return plan

    def apply_plan(
        self,
        raw_profile: Mapping[str, Any] | None,
        *,
        config_version: str,
        model_available: bool = False,
        prefer_llm: bool = False,
        confirm: bool = True,
        actor: str = "onboarding_plan_service",
    ) -> Dict[str, Any]:
        """Apply non-secret recommended config via SystemConfigService and persist profile."""
        if not confirm:
            raise OnboardingProfileValidationError(
                "Apply requires explicit confirm=true",
                issues=[{"field": "confirm", "code": "required", "message": "must be true"}],
            )
        plan = self.build_plan(
            raw_profile,
            model_available=model_available,
            prefer_llm=prefer_llm,
        )
        items = list(plan.get("config_items") or [])
        for item in items:
            if is_secret_config_key(str(item.get("key") or "")):
                raise OnboardingSecretRejectedError(
                    f"Refusing to write secret key via onboarding: {item.get('key')}"
                )

        applied_keys: List[str] = []
        new_version = config_version
        update_payload: Dict[str, Any] = {
            "success": True,
            "applied_count": 0,
            "updated_keys": [],
            "config_version": config_version,
            "message": "No non-secret config changes required",
        }
        if items:
            try:
                update_payload = self._system_config.update(
                    config_version=config_version,
                    items=items,
                    reload_now=True,
                    validate_connectivity=False,
                    actor=actor,
                )
            except (ConfigValidationError, ConfigConflictError):
                raise
            except Exception as exc:  # broad-exception: fallback_recorded - surface as internal
                log_safe_exception(
                    logger,
                    "Onboarding config apply failed",
                    exc,
                    error_code="onboarding_apply_failed",
                )
                raise
            applied_keys = list(update_payload.get("updated_keys") or [])
            new_version = str(
                update_payload.get("config_version")
                or update_payload.get("new_config_version")
                or config_version
            )

        state = {
            "profile": plan["profile"],
            "plan": plan,
            "applied_at": _utc_now_iso(),
            "applied_keys": applied_keys,
            "config_version": new_version,
            "status": "applied",
        }
        self._write_state(state)
        return {
            "success": True,
            "config_version": new_version,
            "applied_keys": applied_keys,
            "applied_count": len(applied_keys),
            "plan": plan,
            "profile": plan["profile"],
            "update": update_payload,
            "message": (
                "Onboarding plan applied"
                if applied_keys
                else "Onboarding profile saved; no non-secret config changes required"
            ),
        }

    def get_state(self) -> Optional[Dict[str, Any]]:
        """Return persisted onboarding state, or None when unset."""
        if not self._state_path.exists():
            return None
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception as exc:  # broad-exception: fallback_recorded - corrupt state → empty
            log_safe_exception(
                logger,
                "Failed to read onboarding state",
                exc,
                error_code="onboarding_state_read_failed",
            )
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def get_first_run_readiness(
        self,
        *,
        detect_requester: Any = None,
    ) -> Dict[str, Any]:
        """Compose zero-config first-run guidance without mutating configuration.

        Detection uses the existing loopback Ollama probe with a short timeout.
        Failures degrade to the offline demo path; this method never writes
        ``.env`` or onboarding state.
        """
        current = self._read_current_config_map()
        state = self.get_state()
        onboarding_applied = bool(
            isinstance(state, dict) and str(state.get("status") or "") == "applied"
        )
        fresh = is_fresh_environment(current, onboarding_applied=onboarding_applied)

        # Reuse SystemConfigService's authoritative setup projection so an API
        # key without a model/route, an empty channel scaffold, or a missing CLI
        # executable cannot be mistaken for a runnable primary model.
        effective = self._system_config._build_setup_effective_config_map()  # noqa: SLF001

        try:
            detect = detect_local_runtime_from_config_map(
                effective,
                requester=detect_requester,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - first-run must not fail hard
            log_safe_exception(
                logger,
                "First-run local runtime detect raised; degrading to demo path",
                exc,
                error_code="onboarding_first_run_detect_failed",
            )
            detect = LocalRuntimeDetectResult(
                available=False,
                reason="probe_failed",
                detect_enabled=True,
            )

        primary_check = self._system_config._build_setup_primary_llm_check(  # noqa: SLF001
            effective,
            local_detect=detect,
        )
        _resolved_model, model_source = self._system_config._resolve_setup_primary_model(  # noqa: SLF001
            effective
        )
        legacy_model_is_explicit = any(
            str(effective.get(key) or "").strip() for key in _LEGACY_PRIMARY_MODEL_KEYS
        )
        has_model = (
            str(primary_check.get("status") or "") == "configured"
            and (model_source != "legacy" or legacy_model_is_explicit)
        )

        preset_configs, _preset_meta = _load_preset_catalog()
        local_preset_values = {
            str(k).upper(): str(v)
            for k, v in dict(preset_configs.get("local-first") or {}).items()
            if not is_secret_config_key(str(k))
        }

        suggested_profile: Dict[str, str] = {}
        recommended_preset_id: Optional[str] = None

        models = list(detect.models or [])
        local_reachable = bool(detect.available)
        local_models_available = bool(models)
        local_runnable = local_reachable and local_models_available

        if has_model:
            primary_path = "configured"
            beginner_mode_recommended = False
            primary_cta = "continue"
            reason_code = "primary_model_configured"
            reason_params: Dict[str, str] = {}
        elif local_runnable:
            primary_path = "local_ollama"
            beginner_mode_recommended = fresh
            primary_cta = "open_local_setup"
            reason_code = "local_model_ready"
            reason_params = {"models": ", ".join(models[:3])}
            recommended_preset_id = "local-first"
            suggested_profile = dict(local_preset_values)
            for key, value in dict(detect.suggested_profile or {}).items():
                key_u = str(key or "").strip().upper()
                val = str(value or "").strip()
                if key_u and val and not is_secret_config_key(key_u):
                    suggested_profile[key_u] = val
        else:
            primary_path = "demo"
            beginner_mode_recommended = fresh
            primary_cta = "view_demo"
            if local_reachable:
                reason_code = "local_runtime_no_models"
            elif not detect.detect_enabled:
                reason_code = "local_detect_disabled"
            else:
                reason_code = "local_runtime_unavailable"
            reason_params = {}

        public_local_runtime = {
            "reachable": local_reachable,
            "models_available": local_models_available,
            "runnable": local_runnable,
            "backend": detect.backend,
            "base_url": detect.base_url,
            "models": models,
            "suggested_profile": dict(detect.suggested_profile or {}) if local_runnable else {},
            "reason_code": (
                "ollama_ready"
                if local_runnable
                else "ollama_no_models"
                if local_reachable
                else "detect_disabled"
                if not detect.detect_enabled
                else "ollama_unreachable"
            ),
            "detect_enabled": bool(detect.detect_enabled),
        }
        snapshot_payload = {
            "schema_version": FIRST_RUN_READINESS_SCHEMA_VERSION,
            "is_fresh_environment": fresh,
            "has_primary_model": has_model,
            "beginner_mode_recommended": beginner_mode_recommended,
            "primary_path": primary_path,
            "primary_cta": primary_cta,
            "reason_code": reason_code,
            "reason_params": reason_params,
            "local_runtime": public_local_runtime,
            "recommended_preset_id": recommended_preset_id,
            "suggested_profile": suggested_profile,
            "demo_available": True,
            "config_mutated": False,
            "existing_config_untouched": True,
        }
        return {
            **snapshot_payload,
            "snapshot_id": _snapshot_id(snapshot_payload),
            "generated_at": _utc_now_iso(),
        }

    def get_demo_analysis(self, *, report_language: str = "zh") -> Dict[str, Any]:
        """Return the offline sample analysis fixture (always ``is_sample=True``)."""
        return build_demo_analysis(report_language=report_language)

    def reset_state(self) -> Dict[str, Any]:
        """Delete persisted profile/plan; does not roll back config writes."""
        existed = self._state_path.exists()
        if existed:
            try:
                self._state_path.unlink()
            except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
                log_safe_exception(
                    logger,
                    "Failed to delete onboarding state",
                    exc,
                    error_code="onboarding_state_delete_failed",
                )
                raise OnboardingPlanError(
                    "Failed to reset onboarding state",
                    error_code="onboarding_state_delete_failed",
                ) from exc
        return {
            "success": True,
            "reset": existed,
            "message": "Onboarding profile reset" if existed else "No onboarding profile stored",
        }

    def _write_state(self, state: Mapping[str, Any]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self._state_path)
