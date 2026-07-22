# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit, deterministic loader for trusted external plugin directories."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

from .manager import PluginManager, PluginState
from .manifest import PluginManifest, split_entrypoint
from .plugin import Plugin


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExternalPluginResult:
    """Safe per-candidate result returned by external discovery."""

    candidate: str
    plugin_id: str | None
    success: bool
    state: PluginState | None
    error_code: str | None = None


class ExternalPluginLoader:
    """Import direct child plugins only when an explicit caller supplies a root."""

    def __init__(self, manager: PluginManager) -> None:
        if not isinstance(manager, PluginManager):
            raise TypeError("manager must be a PluginManager")
        self._manager = manager

    def register_from_directory(
        self,
        plugins_dir: str | Path | None,
    ) -> tuple[ExternalPluginResult, ...]:
        """Import and register direct child plugins without invoking ``onload``."""

        if plugins_dir is None or (isinstance(plugins_dir, str) and not plugins_dir.strip()):
            return ()
        if not isinstance(plugins_dir, (str, Path)):
            return (
                ExternalPluginResult(
                    candidate="plugins_dir",
                    plugin_id=None,
                    success=False,
                    state=None,
                    error_code="external_plugins_directory_invalid",
                ),
            )
        try:
            root = Path(plugins_dir).expanduser()
            if not root.is_dir():
                return (
                    ExternalPluginResult(
                        candidate="plugins_dir",
                        plugin_id=None,
                        success=False,
                        state=None,
                        error_code="external_plugins_directory_unavailable",
                    ),
                )
            candidates = tuple(
                sorted(
                    (
                        candidate
                        for candidate in root.iterdir()
                        if candidate.is_dir() and not candidate.is_symlink()
                    ),
                    key=lambda candidate: candidate.name,
                )
            )
        except (OSError, RuntimeError) as exc:
            log_safe_exception(
                logger,
                "External plugin directory scan failed",
                exc,
                error_code="external_plugins_directory_unavailable",
            )
            return (
                ExternalPluginResult(
                    candidate="plugins_dir",
                    plugin_id=None,
                    success=False,
                    state=None,
                    error_code="external_plugins_directory_unavailable",
                ),
            )
        results: list[ExternalPluginResult] = []
        for candidate in candidates:
            candidate_name = sanitize_diagnostic_text(candidate.name, max_length=128) or "plugin"
            try:
                result = self._register_candidate(candidate)
            except Exception as exc:  # broad-exception: fallback_recorded - Unexpected candidate failures are safely recorded so later plugins still load.
                log_safe_exception(
                    logger,
                    "External plugin candidate failed",
                    exc,
                    error_code="external_candidate_failed",
                    context={"candidate": candidate_name},
                )
                result = self._failure(candidate_name, "external_candidate_failed")
            results.append(result)
        return tuple(results)

    def _register_candidate(self, candidate: Path) -> ExternalPluginResult:
        candidate_name = sanitize_diagnostic_text(candidate.name, max_length=128) or "plugin"
        manifest_path = candidate / "manifest.json"
        try:
            manifest_text = manifest_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            log_safe_exception(
                logger,
                "External plugin manifest could not be read",
                exc,
                error_code="external_manifest_unavailable",
                context={"candidate": candidate_name},
            )
            return self._failure(candidate_name, "external_manifest_unavailable")
        try:
            manifest_payload = json.loads(manifest_text)
        except json.JSONDecodeError:
            return self._failure(candidate_name, "external_manifest_invalid")
        try:
            manifest = PluginManifest.model_validate(manifest_payload)
        except ValidationError:
            return self._failure(candidate_name, "external_manifest_invalid")

        compatibility_error = self._manager.compatibility_error(manifest)
        if compatibility_error is not None:
            return self._failure(
                candidate_name,
                compatibility_error,
                plugin_id=manifest.id,
            )
        if self._manager.contains(manifest.id):
            snapshot = self._manager.snapshot(manifest.id)
            return ExternalPluginResult(
                candidate=candidate_name,
                plugin_id=manifest.id,
                success=False,
                state=None if snapshot is None else snapshot.state,
                error_code="plugin_id_conflict",
            )

        relative_path, class_name = split_entrypoint(manifest.entrypoint)
        try:
            candidate_root = candidate.resolve(strict=True)
            entrypoint_path = (candidate_root / Path(*relative_path.parts)).resolve(strict=True)
        except FileNotFoundError:
            return self._failure(
                candidate_name,
                "external_entrypoint_missing",
                plugin_id=manifest.id,
            )
        except (OSError, RuntimeError) as exc:
            log_safe_exception(
                logger,
                "External plugin entrypoint could not be resolved",
                exc,
                error_code="external_entrypoint_unavailable",
                context={"candidate": candidate_name, "plugin_id": manifest.id},
            )
            return self._failure(
                candidate_name,
                "external_entrypoint_unavailable",
                plugin_id=manifest.id,
            )
        if candidate_root not in entrypoint_path.parents or not entrypoint_path.is_file():
            return self._failure(
                candidate_name,
                "external_entrypoint_unsafe",
                plugin_id=manifest.id,
            )

        module_name = self._module_name(manifest, entrypoint_path)
        module = None
        try:
            spec = importlib.util.spec_from_file_location(module_name, entrypoint_path)
            if spec is None or spec.loader is None:
                return self._failure(
                    candidate_name,
                    "external_import_unavailable",
                    plugin_id=manifest.id,
                )
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as exc:  # broad-exception: fallback_recorded - External import failures are safely recorded and isolated per candidate.
            self._remove_module(module_name, module)
            log_safe_exception(
                logger,
                "External plugin import failed",
                exc,
                error_code="external_import_failed",
                context={"candidate": candidate_name, "plugin_id": manifest.id},
            )
            return self._failure(
                candidate_name,
                "external_import_failed",
                plugin_id=manifest.id,
            )

        try:
            plugin_class = getattr(module, class_name)
            valid_class = isinstance(plugin_class, type) and issubclass(plugin_class, Plugin)
        except Exception as exc:  # broad-exception: fallback_recorded - Entrypoint lookup failures are safely recorded and isolated per candidate.
            self._remove_module(module_name, module)
            log_safe_exception(
                logger,
                "External plugin entrypoint lookup failed",
                exc,
                error_code="external_entrypoint_invalid",
                context={"candidate": candidate_name, "plugin_id": manifest.id},
            )
            return self._failure(
                candidate_name,
                "external_entrypoint_invalid",
                plugin_id=manifest.id,
            )
        if not valid_class:
            self._remove_module(module_name, module)
            return self._failure(
                candidate_name,
                "external_entrypoint_invalid",
                plugin_id=manifest.id,
            )

        try:
            plugin = plugin_class(manifest)
        except Exception as exc:  # broad-exception: fallback_recorded - External constructor failures are safely recorded and isolated per candidate.
            self._remove_module(module_name, module)
            log_safe_exception(
                logger,
                "External plugin construction failed",
                exc,
                error_code="external_constructor_failed",
                context={"candidate": candidate_name, "plugin_id": manifest.id},
            )
            return self._failure(
                candidate_name,
                "external_constructor_failed",
                plugin_id=manifest.id,
            )

        registration = self._manager.register(plugin, source="external")
        if not registration.success:
            self._remove_module(module_name, module)
        return ExternalPluginResult(
            candidate=candidate_name,
            plugin_id=manifest.id,
            success=registration.success,
            state=registration.state,
            error_code=registration.error_code,
        )

    @staticmethod
    def _module_name(manifest: PluginManifest, entrypoint_path: Path) -> str:
        identity = f"{manifest.id}\x00{manifest.version}\x00{entrypoint_path}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        return f"_stockpulse_external_plugin_{digest}"

    @staticmethod
    def _remove_module(module_name: str, module: object | None) -> None:
        if module is not None and sys.modules.get(module_name) is module:
            del sys.modules[module_name]

    @staticmethod
    def _failure(
        candidate: str,
        error_code: str,
        *,
        plugin_id: str | None = None,
    ) -> ExternalPluginResult:
        return ExternalPluginResult(
            candidate=candidate,
            plugin_id=plugin_id,
            success=False,
            state=None,
            error_code=error_code,
        )
