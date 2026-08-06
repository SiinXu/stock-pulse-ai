# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Recommended config presets and stockpulse-profile YAML import/export.

Security rule (enforced in code + tests + docs):
  Profiles NEVER export secret values. Secret-bearing keys are excluded on
  export and rejected on import. Apply always goes through SystemConfigService.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import yaml

from src.core.config_registry import get_field_definition
from src.llm.backend_registry import LOCAL_CLI_GENERATION_BACKEND_IDS
from src.services.config_presets import (
    MAX_PROFILE_YAML_BYTES,
    PROFILE_API_VERSION,
    PROFILE_KIND,
    get_official_preset,
    is_exportable_config_key,
    is_secret_config_key,
    list_official_presets,
)
from src.services.system_config_service import (
    ConfigConflictError,
    ConfigValidationError,
    SystemConfigService,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class ConfigProfileError(Exception):
    """Base domain error for config profile operations."""

    error_code = "config_profile_error"

    def __init__(self, message: str, *, error_code: Optional[str] = None) -> None:
        super().__init__(message)
        if error_code:
            self.error_code = error_code


class ConfigProfileValidationError(ConfigProfileError):
    """Raised when profile YAML fails schema or security validation."""

    error_code = "config_profile_validation_failed"

    def __init__(
        self,
        message: str,
        *,
        issues: Optional[Sequence[Mapping[str, Any]]] = None,
        error_code: Optional[str] = None,
    ) -> None:
        super().__init__(message, error_code=error_code)
        self.issues = [dict(item) for item in (issues or ())]


class ConfigProfileNotFoundError(ConfigProfileError):
    """Raised when a preset id is unknown."""

    error_code = "config_profile_not_found"


class ConfigProfileService:
    """List/rank presets, export/import stockpulse-profile YAML, apply via SCS."""

    def __init__(
        self,
        *,
        system_config_service: SystemConfigService,
        strategies_dir: Optional[Path] = None,
        which_executable: Optional[Callable[[str], Optional[str]]] = None,
        ollama_probe: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._system_config = system_config_service
        self._strategies_dir = Path(strategies_dir or Path.cwd() / "strategies")
        self._which = which_executable or shutil.which
        self._ollama_probe = ollama_probe

    def list_presets(self) -> Dict[str, Any]:
        """Return official presets with local-first recommendation ranking."""
        detection = self._detect_runtimes()
        ranked = self._rank_presets(detection)
        recommended_id = ranked[0]["id"] if ranked else None
        return {
            "recommended_preset_id": recommended_id,
            "detection": detection,
            "presets": ranked,
        }

    def preview_preset_apply(self, preset_id: str, *, config_version: str) -> Dict[str, Any]:
        """Preview non-secret config changes for applying one official preset."""
        preset = get_official_preset(preset_id)
        if preset is None:
            raise ConfigProfileNotFoundError(f"Unknown preset: {preset_id}")
        self._guard_version(config_version)
        desired = self._preset_to_config_map(preset)
        current = self._read_exportable_config_map()
        changes = self._diff_config_maps(current, desired)
        return {
            "preset_id": preset["id"],
            "display_name": preset["display_name"],
            "config_version": config_version,
            "features": dict(preset.get("features") or {}),
            "changes": changes,
            "change_count": len(changes),
        }

    def apply_preset(
        self,
        preset_id: str,
        *,
        config_version: str,
        reload_now: bool = True,
        actor: str = "config_profile_service",
    ) -> Dict[str, Any]:
        """Apply one official preset through SystemConfigService.update."""
        preset = get_official_preset(preset_id)
        if preset is None:
            raise ConfigProfileNotFoundError(f"Unknown preset: {preset_id}")
        desired = self._preset_to_config_map(preset)
        if any(is_secret_config_key(key) for key in desired):
            raise ConfigProfileValidationError(
                "Preset contains secret keys and cannot be applied",
                error_code="config_profile_secret_rejected",
            )
        current = self._read_exportable_config_map()
        changes = self._diff_config_maps(current, desired)
        items = [{"key": item["key"], "value": item["to"]} for item in changes]
        if not items:
            return {
                "preset_id": preset["id"],
                "display_name": preset["display_name"],
                "applied": False,
                "config_version": config_version,
                "new_config_version": config_version,
                "updated_keys": [],
                "changes": [],
                "features": dict(preset.get("features") or {}),
                "message": "Preset already matches current non-secret configuration",
            }
        try:
            result = self._system_config.update(
                config_version=config_version,
                items=items,
                mask_token="******",
                reload_now=reload_now,
                validate_connectivity=False,
                actor=actor,
            )
        except ConfigValidationError as exc:
            raise ConfigProfileValidationError(
                "Preset apply failed validation",
                issues=getattr(exc, "issues", None) or [],
                error_code="config_profile_apply_validation_failed",
            ) from exc
        except ConfigConflictError:
            raise
        return {
            "preset_id": preset["id"],
            "display_name": preset["display_name"],
            "applied": True,
            "config_version": config_version,
            "new_config_version": result.get("config_version") or config_version,
            "updated_keys": list(result.get("updated_keys") or []),
            "changes": changes,
            "features": dict(preset.get("features") or {}),
            "message": "Preset applied",
        }

    def export_profile(
        self,
        *,
        name: str = "current",
        display_name: str = "Current configuration",
        description: str = "Exported non-secret StockPulse configuration profile",
    ) -> Dict[str, Any]:
        """Export non-secret configuration as stockpulse-profile YAML."""
        config_map = self._read_exportable_config_map()
        safe_config = {
            key: value
            for key, value in config_map.items()
            if is_exportable_config_key(key) and not is_secret_config_key(key)
        }
        strategies_enabled = self._split_csv(safe_config.get("AGENT_SKILLS", ""))
        document = {
            "apiVersion": PROFILE_API_VERSION,
            "kind": PROFILE_KIND,
            "metadata": {
                "name": name,
                "displayName": display_name,
                "description": description,
                "version": "1.0.0",
                "tags": ["exported"],
            },
            "spec": {
                "llm": {
                    "preferenceOrder": self._infer_preference_order(safe_config),
                    "config": safe_config,
                },
                "strategies": {"enabled": strategies_enabled},
                "features": {"beginnerMode": False},
                "requirements": {},
            },
        }
        yaml_text = yaml.safe_dump(
            document,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
        if len(yaml_text.encode("utf-8")) > MAX_PROFILE_YAML_BYTES:
            raise ConfigProfileValidationError(
                "Exported profile exceeds size limit",
                error_code="config_profile_too_large",
            )
        self._assert_yaml_has_no_secret_keys(document)
        payload = self._system_config.get_config(include_schema=False)
        return {
            "content": yaml_text,
            "config_version": str(payload.get("config_version") or ""),
            "filename": f"stockpulse-profile-{name}.yaml",
            "keys_exported": sorted(safe_config.keys()),
            "keys_redacted": self._count_redacted_keys(payload),
        }

    def preview_import(self, *, content: str, config_version: str) -> Dict[str, Any]:
        """Validate profile YAML and preview the config diff without writing."""
        self._guard_version(config_version)
        document = self._parse_and_validate_profile(content)
        desired = self._profile_to_config_map(document)
        current = self._read_exportable_config_map()
        changes = self._diff_config_maps(current, desired)
        metadata = document.get("metadata") or {}
        return {
            "valid": True,
            "config_version": config_version,
            "name": str(metadata.get("name") or ""),
            "display_name": str(metadata.get("displayName") or metadata.get("name") or ""),
            "description": str(metadata.get("description") or ""),
            "features": dict((document.get("spec") or {}).get("features") or {}),
            "changes": changes,
            "change_count": len(changes),
            "issues": [],
        }

    def apply_import(
        self,
        *,
        content: str,
        config_version: str,
        reload_now: bool = True,
        actor: str = "config_profile_service",
    ) -> Dict[str, Any]:
        """Validate and apply a stockpulse-profile YAML via SystemConfigService."""
        document = self._parse_and_validate_profile(content)
        desired = self._profile_to_config_map(document)
        current = self._read_exportable_config_map()
        changes = self._diff_config_maps(current, desired)
        items = [{"key": item["key"], "value": item["to"]} for item in changes]
        metadata = document.get("metadata") or {}
        if not items:
            return {
                "applied": False,
                "config_version": config_version,
                "new_config_version": config_version,
                "updated_keys": [],
                "changes": [],
                "name": str(metadata.get("name") or ""),
                "features": dict((document.get("spec") or {}).get("features") or {}),
                "message": "Imported profile already matches current non-secret configuration",
            }
        try:
            result = self._system_config.update(
                config_version=config_version,
                items=items,
                mask_token="******",
                reload_now=reload_now,
                validate_connectivity=False,
                actor=actor,
            )
        except ConfigValidationError as exc:
            raise ConfigProfileValidationError(
                "Profile import failed validation",
                issues=getattr(exc, "issues", None) or [],
                error_code="config_profile_apply_validation_failed",
            ) from exc
        except ConfigConflictError:
            raise
        return {
            "applied": True,
            "config_version": config_version,
            "new_config_version": result.get("config_version") or config_version,
            "updated_keys": list(result.get("updated_keys") or []),
            "changes": changes,
            "name": str(metadata.get("name") or ""),
            "features": dict((document.get("spec") or {}).get("features") or {}),
            "message": "Profile imported",
        }

    def _detect_runtimes(self) -> Dict[str, Any]:
        effective = self._effective_config_map()
        return {
            "ollama_healthy": self._probe_ollama(effective),
            "model_pack_present": self._probe_model_pack(),
            "cli_detected": sorted(self._probe_cli_backends()),
            "cloud_ready": self._probe_cloud_credentials(effective),
        }

    def _rank_presets(self, detection: Mapping[str, Any]) -> List[Dict[str, Any]]:
        scores: Dict[str, int] = {
            "local-first": 10,
            "cli-backends": 10,
            "cloud-balanced": 10,
            "power-user": 0,
        }
        if detection.get("ollama_healthy") or detection.get("model_pack_present"):
            scores["local-first"] += 100
        if detection.get("cli_detected"):
            scores["cli-backends"] += 80
        if detection.get("cloud_ready"):
            scores["cloud-balanced"] += 40
        if not any(
            (
                detection.get("ollama_healthy"),
                detection.get("model_pack_present"),
                detection.get("cli_detected"),
                detection.get("cloud_ready"),
            )
        ):
            scores["local-first"] += 20
            scores["cloud-balanced"] += 15

        ranked: List[Dict[str, Any]] = []
        for preset in list_official_presets():
            item = dict(preset)
            item["recommended"] = False
            item["score"] = int(scores.get(str(item["id"]), 0))
            item["meets_requirements"] = self._meets_requirements(
                item.get("requirements") or {},
                detection,
            )
            ranked.append(item)
        ranked.sort(key=lambda row: (-int(row["score"]), str(row["id"])))
        if ranked:
            ranked[0]["recommended"] = True
        return ranked

    def _meets_requirements(
        self,
        requirements: Mapping[str, Any],
        detection: Mapping[str, Any],
    ) -> bool:
        if requirements.get("needs_ollama") and not (
            detection.get("ollama_healthy") or detection.get("model_pack_present")
        ):
            return False
        if requirements.get("needs_cli") and not detection.get("cli_detected"):
            return False
        if requirements.get("needs_cloud_key") and not detection.get("cloud_ready"):
            return False
        return True

    def _probe_ollama(self, effective: Mapping[str, str]) -> bool:
        if self._ollama_probe is not None:
            try:
                return bool(self._ollama_probe())
            except Exception as exc:  # broad-exception: fallback_recorded - detection is advisory
                log_safe_exception(
                    logger,
                    "Ollama probe failed during preset ranking",
                    exc,
                    error_code="config_profile_ollama_probe_failed",
                    level=logging.DEBUG,
                )
                return False
        if (effective.get("LLM_OLLAMA_ENABLED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return True
        if (effective.get("LLM_OLLAMA_MODELS") or "").strip():
            return True
        if (effective.get("OLLAMA_API_BASE") or "").strip():
            return True
        if "ollama" in {
            part.strip().lower()
            for part in (effective.get("LLM_CHANNELS") or "").split(",")
            if part.strip()
        }:
            return True
        return False

    def _probe_model_pack(self) -> bool:
        try:
            from src.model_pack import ModelPackRegistry

            registry = ModelPackRegistry()
            if hasattr(registry, "list_all"):
                return bool(registry.list_all())  # type: ignore[attr-defined]
            if hasattr(registry, "list"):
                return bool(registry.list())  # type: ignore[attr-defined]
        except Exception as exc:  # broad-exception: fallback_recorded - detection is advisory
            log_safe_exception(
                logger,
                "Model pack probe failed during preset ranking",
                exc,
                error_code="config_profile_model_pack_probe_failed",
                level=logging.DEBUG,
            )
        return False

    def _probe_cli_backends(self) -> List[str]:
        detected: List[str] = []
        binary_by_backend = {
            "codex_cli": "codex",
            "claude_code_cli": "claude",
            "opencode_cli": "opencode",
        }
        for backend_id in LOCAL_CLI_GENERATION_BACKEND_IDS:
            binary = binary_by_backend.get(backend_id)
            if not binary:
                continue
            try:
                if self._which(binary):
                    detected.append(backend_id)
            except Exception as exc:  # broad-exception: fallback_recorded - detection is advisory
                log_safe_exception(
                    logger,
                    "CLI probe failed during preset ranking",
                    exc,
                    error_code="config_profile_cli_probe_failed",
                    level=logging.DEBUG,
                    context={"backend_id": backend_id},
                )
        return detected

    def _probe_cloud_credentials(self, effective: Mapping[str, str]) -> bool:
        for key, value in effective.items():
            if not value or not str(value).strip():
                continue
            upper = str(key).upper()
            if is_secret_config_key(upper) and any(
                marker in upper for marker in ("API_KEY", "API_KEYS", "TOKEN")
            ):
                field = get_field_definition(upper, value_hint=str(value))
                if field.get("is_sensitive"):
                    return True
        return False

    def _parse_and_validate_profile(self, content: str) -> Dict[str, Any]:
        raw = content if isinstance(content, str) else str(content or "")
        if not raw.strip():
            raise ConfigProfileValidationError(
                "Profile YAML is empty",
                error_code="config_profile_empty",
            )
        if len(raw.encode("utf-8")) > MAX_PROFILE_YAML_BYTES:
            raise ConfigProfileValidationError(
                "Profile YAML exceeds size limit",
                error_code="config_profile_too_large",
            )
        try:
            document = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ConfigProfileValidationError(
                "Profile YAML is not valid YAML",
                error_code="config_profile_yaml_invalid",
            ) from exc
        if not isinstance(document, dict):
            raise ConfigProfileValidationError(
                "Profile root must be a mapping",
                error_code="config_profile_root_invalid",
            )
        api_version = str(document.get("apiVersion") or "").strip()
        kind = str(document.get("kind") or "").strip()
        if api_version != PROFILE_API_VERSION:
            raise ConfigProfileValidationError(
                f"Unsupported apiVersion: {api_version or '(missing)'}",
                error_code="config_profile_api_version_unsupported",
            )
        if kind != PROFILE_KIND:
            raise ConfigProfileValidationError(
                f"Unsupported kind: {kind or '(missing)'}",
                error_code="config_profile_kind_unsupported",
            )
        metadata = document.get("metadata")
        if not isinstance(metadata, dict):
            raise ConfigProfileValidationError(
                "metadata must be a mapping",
                error_code="config_profile_metadata_invalid",
            )
        if not str(metadata.get("name") or "").strip():
            raise ConfigProfileValidationError(
                "metadata.name is required",
                error_code="config_profile_name_required",
            )
        spec = document.get("spec")
        if not isinstance(spec, dict):
            raise ConfigProfileValidationError(
                "spec must be a mapping",
                error_code="config_profile_spec_invalid",
            )
        self._assert_yaml_has_no_secret_keys(document)
        for banned in ("scripts", "hooks", "commands", "exec", "shell"):
            if banned in document or banned in spec:
                raise ConfigProfileValidationError(
                    f"Profile must not contain executable field: {banned}",
                    error_code="config_profile_executable_rejected",
                )
        return document

    def _assert_yaml_has_no_secret_keys(self, document: Mapping[str, Any]) -> None:
        offenders: List[str] = []

        def walk(node: Any, path: str = "") -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    key_text = str(key)
                    child_path = f"{path}.{key_text}" if path else key_text
                    if is_secret_config_key(key_text):
                        offenders.append(child_path)
                    if key_text.upper() == "CONFIG" and isinstance(value, dict):
                        for config_key in value:
                            if is_secret_config_key(str(config_key)):
                                offenders.append(f"{child_path}.{config_key}")
                    walk(value, child_path)
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, f"{path}[{index}]")

        walk(document)
        if offenders:
            raise ConfigProfileValidationError(
                "Profile must not contain secret keys",
                issues=[
                    {
                        "severity": "error",
                        "key": key,
                        "message": "Secret keys are not allowed in stockpulse-profile YAML",
                        "error_code": "config_profile_secret_rejected",
                    }
                    for key in offenders
                ],
                error_code="config_profile_secret_rejected",
            )

    def _profile_to_config_map(self, document: Mapping[str, Any]) -> Dict[str, str]:
        spec = document.get("spec") or {}
        llm = spec.get("llm") if isinstance(spec, dict) else {}
        config: Dict[str, Any] = {}
        if isinstance(llm, dict) and isinstance(llm.get("config"), dict):
            config = dict(llm.get("config") or {})
        result: Dict[str, str] = {}
        for key, value in config.items():
            upper = str(key).strip().upper()
            if not upper or is_secret_config_key(upper):
                continue
            if not is_exportable_config_key(upper):
                continue
            result[upper] = "" if value is None else str(value)

        strategies = spec.get("strategies") if isinstance(spec, dict) else {}
        if isinstance(strategies, dict):
            enabled = strategies.get("enabled") or []
            if isinstance(enabled, list):
                cleaned = [str(item).strip() for item in enabled if str(item).strip()]
                if cleaned:
                    result["AGENT_SKILLS"] = ",".join(cleaned)
                    known = self._known_strategy_ids()
                    if known:
                        filtered = [item for item in cleaned if item in known]
                        if filtered:
                            result["AGENT_SKILLS"] = ",".join(filtered)
                        else:
                            result.pop("AGENT_SKILLS", None)
        return result

    def _preset_to_config_map(self, preset: Mapping[str, Any]) -> Dict[str, str]:
        values = {
            str(key).upper(): str(value)
            for key, value in (preset.get("config_values") or {}).items()
            if not is_secret_config_key(str(key))
        }
        strategies = (preset.get("strategies") or {}).get("enabled") or []
        if strategies:
            values["AGENT_SKILLS"] = ",".join(str(item) for item in strategies if str(item).strip())
        if preset.get("id") == "local-first":
            channels = self._split_csv(values.get("LLM_CHANNELS", ""))
            current = self._read_exportable_config_map()
            existing = self._split_csv(current.get("LLM_CHANNELS", ""))
            merged = list(dict.fromkeys([*existing, *channels, "ollama"]))
            values["LLM_CHANNELS"] = ",".join(merged)
        return values

    def _known_strategy_ids(self) -> set[str]:
        if not self._strategies_dir.exists():
            return set()
        ids: set[str] = set()
        for path in self._strategies_dir.glob("*.yaml"):
            ids.add(path.stem)
        for path in self._strategies_dir.glob("*.yml"):
            ids.add(path.stem)
        return ids

    def _read_exportable_config_map(self) -> Dict[str, str]:
        payload = self._system_config.get_config(include_schema=False)
        result: Dict[str, str] = {}
        for item in payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip().upper()
            if not key or not is_exportable_config_key(key):
                continue
            if bool(item.get("is_masked")) or is_secret_config_key(key):
                continue
            result[key] = str(item.get("value") or "")
        return result

    def _effective_config_map(self) -> Dict[str, str]:
        payload = self._system_config.get_config(include_schema=False)
        result: Dict[str, str] = {}
        for item in payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip().upper()
            if key:
                result[key] = str(item.get("value") or "")
        return result

    def _count_redacted_keys(self, payload: Mapping[str, Any]) -> int:
        count = 0
        for item in payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip().upper()
            if not key:
                continue
            if is_secret_config_key(key) or bool(item.get("is_masked")):
                count += 1
        return count

    def _diff_config_maps(
        self,
        current: Mapping[str, str],
        desired: Mapping[str, str],
    ) -> List[Dict[str, str]]:
        changes: List[Dict[str, str]] = []
        for key in sorted(desired.keys()):
            if is_secret_config_key(key):
                continue
            before = str(current.get(key, ""))
            after = str(desired.get(key, ""))
            if before != after:
                changes.append({"key": key, "from": before, "to": after})
        return changes

    def _infer_preference_order(self, config: Mapping[str, str]) -> List[str]:
        backend = (config.get("GENERATION_BACKEND") or "litellm").strip().lower()
        if backend in LOCAL_CLI_GENERATION_BACKEND_IDS:
            return ["cli", "ollama", "model_pack", "cloud"]
        if "ollama" in (config.get("LITELLM_MODEL") or "").lower():
            return ["ollama", "model_pack", "cli", "cloud"]
        if "ollama" in {
            part.strip().lower()
            for part in (config.get("LLM_CHANNELS") or "").split(",")
            if part.strip()
        }:
            return ["ollama", "model_pack", "cli", "cloud"]
        return ["cloud", "cli", "ollama", "model_pack"]

    def _guard_version(self, config_version: str) -> None:
        payload = self._system_config.get_config(include_schema=False)
        current = str(payload.get("config_version") or "")
        if str(config_version or "") != current:
            raise ConfigConflictError(current_version=current)

    @staticmethod
    def _split_csv(raw: str) -> List[str]:
        return [part.strip() for part in str(raw or "").split(",") if part.strip()]


__all__ = [
    "ConfigProfileError",
    "ConfigProfileNotFoundError",
    "ConfigProfileService",
    "ConfigProfileValidationError",
]
