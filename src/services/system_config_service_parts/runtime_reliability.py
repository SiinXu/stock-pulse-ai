"""Transactional runtime activation and last-known-good config snapshots."""

from __future__ import annotations

import errno
import hashlib
import io
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from dotenv import dotenv_values

from src.config import Config, setup_env
from src.core.config_manager import ConfigManager
from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeEnvSnapshot:
    """Exact persisted environment state for one runtime config version."""

    exists: bool
    content: str


class RuntimeConfigActivationError(RuntimeError):
    """Raised after candidate activation fails and restoration is attempted."""

    def __init__(self, *, rollback_succeeded: bool) -> None:
        super().__init__("Runtime configuration activation failed")
        self.rollback_succeeded = rollback_succeeded


class LastGoodConfigUnavailableError(RuntimeError):
    """Raised when no valid last-known-good snapshot can be restored."""


class RuntimeConfigTransaction:
    """Serialize persisted writes, runtime publication, and one-step rollback."""

    _SNAPSHOT_FORMAT = 1
    _DERIVED_PROCESS_ENV_KEYS = frozenset({
        "HTTP_PROXY",
        "http_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
    })

    def __init__(
        self,
        *,
        manager: ConfigManager,
        reload_runtime_singletons: Callable[[], None],
    ) -> None:
        self._manager = manager
        self._reload_runtime_singletons = reload_runtime_singletons
        Config._capture_bootstrap_runtime_env_overrides()
        self._bootstrap_process_env_overrides = {
            key: os.environ[key]
            for key in Config._BOOTSTRAP_RUNTIME_ENV_OVERRIDES
            if key in os.environ
        }
        self._active_snapshot = self._read_env_snapshot()
        self._active_version = manager.get_config_version()

    @property
    def lock(self) -> Any:
        """Return the manager's shared per-path reentrant transaction lock."""
        return self._manager._lock

    @property
    def last_good_path(self) -> Path:
        """Return the local, gitignored last-known-good snapshot path."""
        env_path = self._manager.env_path
        path_digest = hashlib.sha256(str(env_path.resolve()).encode("utf-8")).hexdigest()[:12]
        return env_path.parent / f".env.last-good-{path_digest}"

    def activate_persisted_candidate(
        self,
        *,
        redaction_values: Iterable[Any] = (),
    ) -> List[str]:
        """Build and publish the persisted candidate or restore the active state."""
        previous_config = Config.get_instance()
        candidate_snapshot = self._read_env_snapshot()
        process_env_snapshot = self._capture_process_env(
            self._affected_process_env_keys(
                self._active_snapshot,
                candidate_snapshot,
            )
        )

        try:
            self._prepare_process_env_for_snapshot(
                previous_snapshot=self._active_snapshot,
                target_snapshot=candidate_snapshot,
            )
            setup_env(override=True)
            self._restore_bootstrap_process_env_overrides()
            candidate_config = Config._load_from_env()
            warnings = candidate_config.validate()
            Config._instance = candidate_config
            self._reload_runtime_singletons()
            if candidate_snapshot != self._active_snapshot:
                self._write_last_good_snapshot(
                    snapshot=self._active_snapshot,
                    config_version=self._active_version,
                )
        except Exception as exc:  # broad-exception: cleanup - restore the complete active config transaction
            rollback_succeeded = self._restore_runtime(
                snapshot=self._active_snapshot,
                config=previous_config,
                process_env_snapshot=process_env_snapshot,
                redaction_values=redaction_values,
            )
            raise RuntimeConfigActivationError(
                rollback_succeeded=rollback_succeeded,
            ) from exc

        self._active_snapshot = candidate_snapshot
        self._active_version = self._manager.get_config_version()
        return warnings

    def read_last_good_snapshot(self) -> RuntimeEnvSnapshot:
        """Read and validate the persisted last-known-good snapshot envelope."""
        path = self.last_good_path
        if not path.exists():
            raise LastGoodConfigUnavailableError("No last-known-good configuration is available")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LastGoodConfigUnavailableError(
                "The last-known-good configuration snapshot is unreadable"
            ) from exc
        if not isinstance(payload, dict) or payload.get("format") != self._SNAPSHOT_FORMAT:
            raise LastGoodConfigUnavailableError(
                "The last-known-good configuration snapshot format is invalid"
            )
        exists = payload.get("env_exists")
        content = payload.get("content")
        if not isinstance(exists, bool) or not isinstance(content, str):
            raise LastGoodConfigUnavailableError(
                "The last-known-good configuration snapshot is incomplete"
            )
        return RuntimeEnvSnapshot(exists=exists, content=content)

    def mark_persisted_config_active(self) -> None:
        """Synchronize state after a dedicated path reloads the whole Config."""
        self._active_snapshot = self._read_env_snapshot()
        self._active_version = self._manager.get_config_version()

    def rollback_to_last_good(
        self,
        *,
        target_snapshot: RuntimeEnvSnapshot,
        redaction_values: Iterable[Any] = (),
    ) -> Tuple[str, List[str], List[str]]:
        """Restore the last-known-good snapshot and retain the current version as backup."""
        previous_config = Config.get_instance()
        previous_snapshot = self._active_snapshot
        previous_version = self._active_version
        current_persisted_snapshot = self._read_env_snapshot()
        current_map = self.snapshot_config_map(current_persisted_snapshot)
        target_map = self.snapshot_config_map(target_snapshot)
        process_env_snapshot = self._capture_process_env(
            self._affected_process_env_keys(
                current_persisted_snapshot,
                target_snapshot,
            )
        )
        changed_keys = sorted(
            key
            for key in set(current_map) | set(target_map)
            if current_map.get(key) != target_map.get(key)
        )

        try:
            self._restore_env_snapshot(target_snapshot)
            self._prepare_process_env_for_snapshot(
                previous_snapshot=current_persisted_snapshot,
                target_snapshot=target_snapshot,
            )
            setup_env(override=True)
            self._restore_bootstrap_process_env_overrides()
            candidate_config = Config._load_from_env()
            warnings = candidate_config.validate()
            Config._instance = candidate_config
            self._reload_runtime_singletons()
            self._write_last_good_snapshot(
                snapshot=previous_snapshot,
                config_version=previous_version,
            )
        except Exception as exc:  # broad-exception: cleanup - restore the pre-rollback active config
            rollback_succeeded = self._restore_runtime(
                snapshot=previous_snapshot,
                config=previous_config,
                process_env_snapshot=process_env_snapshot,
                redaction_values=redaction_values,
            )
            raise RuntimeConfigActivationError(
                rollback_succeeded=rollback_succeeded,
            ) from exc

        self._active_snapshot = target_snapshot
        self._active_version = self._manager.get_config_version()
        return self._active_version, changed_keys, warnings

    @staticmethod
    def snapshot_config_map(snapshot: RuntimeEnvSnapshot) -> Dict[str, str]:
        """Parse one exact snapshot without interpolation or environment expansion."""
        if not snapshot.exists:
            return {}
        values = dotenv_values(stream=io.StringIO(snapshot.content), interpolate=False)
        return {
            str(key).upper(): "" if value is None else str(value)
            for key, value in values.items()
            if key is not None
        }

    def _read_env_snapshot(self) -> RuntimeEnvSnapshot:
        path = self._manager.env_path
        if not path.exists():
            return RuntimeEnvSnapshot(exists=False, content="")
        return RuntimeEnvSnapshot(
            exists=True,
            content=path.read_text(encoding="utf-8"),
        )

    def _write_last_good_snapshot(
        self,
        *,
        snapshot: RuntimeEnvSnapshot,
        config_version: str,
    ) -> None:
        payload = {
            "format": self._SNAPSHOT_FORMAT,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "config_version": config_version,
            "env_exists": snapshot.exists,
            "content": snapshot.content,
        }
        self._atomic_write_text(
            self.last_good_path,
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        )

    def _restore_runtime(
        self,
        *,
        snapshot: RuntimeEnvSnapshot,
        config: Config,
        process_env_snapshot: Dict[str, Optional[str]],
        redaction_values: Iterable[Any],
    ) -> bool:
        state_restored = False
        try:
            self._restore_env_snapshot(snapshot)
            self._restore_process_env(process_env_snapshot)
            Config._instance = config
            state_restored = True
            self._reload_runtime_singletons()
            return True
        except Exception as exc:  # broad-exception: cleanup - record restoration failure without secrets
            Config._instance = config
            cache_reset_succeeded = False
            try:
                self._reload_runtime_singletons()
                cache_reset_succeeded = True
            except Exception as reset_exc:  # broad-exception: cleanup - record stale runtime cache risk
                log_safe_exception(
                    logger,
                    "Runtime singleton restoration failed",
                    reset_exc,
                    error_code="runtime_singleton_restoration_failed",
                    redaction_values=redaction_values,
                )
            log_safe_exception(
                logger,
                "Runtime configuration restoration failed",
                exc,
                error_code="runtime_configuration_restoration_failed",
                redaction_values=redaction_values,
            )
            return state_restored and cache_reset_succeeded

    @classmethod
    def _affected_process_env_keys(
        cls,
        *snapshots: RuntimeEnvSnapshot,
    ) -> set[str]:
        keys = set(cls._DERIVED_PROCESS_ENV_KEYS)
        for snapshot in snapshots:
            keys.update(cls.snapshot_config_map(snapshot))
        return keys

    @staticmethod
    def _capture_process_env(keys: Iterable[str]) -> Dict[str, Optional[str]]:
        return {key: os.environ.get(key) for key in keys}

    @staticmethod
    def _restore_process_env(snapshot: Dict[str, Optional[str]]) -> None:
        for key, value in snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _restore_bootstrap_process_env_overrides(self) -> None:
        for key, value in self._bootstrap_process_env_overrides.items():
            os.environ[key] = value

    def _prepare_process_env_for_snapshot(
        self,
        *,
        previous_snapshot: RuntimeEnvSnapshot,
        target_snapshot: RuntimeEnvSnapshot,
    ) -> None:
        previous_keys = set(self.snapshot_config_map(previous_snapshot))
        target_keys = set(self.snapshot_config_map(target_snapshot))
        for key in previous_keys - target_keys:
            bootstrap_value = self._bootstrap_process_env_overrides.get(key)
            if bootstrap_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = bootstrap_value

    def _restore_env_snapshot(self, snapshot: RuntimeEnvSnapshot) -> None:
        path = self._manager.env_path
        if not snapshot.exists:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        self._atomic_write_text(path, snapshot.content)

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path_digest = hashlib.sha256(
            str(path.resolve()).encode("utf-8")
        ).hexdigest()[:12]
        temp_path = path.parent / f".env.runtime-config-{path_digest}.tmp"
        try:
            temp_fd = os.open(
                temp_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            with os.fdopen(temp_fd, "w", encoding="utf-8", newline="\n") as file_obj:
                os.fchmod(file_obj.fileno(), 0o600)
                file_obj.write(content)
                file_obj.flush()
                os.fsync(file_obj.fileno())
            try:
                os.replace(temp_path, path)
            except OSError as exc:
                if exc.errno not in {errno.EBUSY, errno.EXDEV}:
                    raise
                path_fd = os.open(
                    path,
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                    0o600,
                )
                with os.fdopen(path_fd, "w", encoding="utf-8", newline="\n") as file_obj:
                    os.fchmod(file_obj.fileno(), 0o600)
                    file_obj.write(content)
                    file_obj.flush()
                    os.fsync(file_obj.fileno())
            path.chmod(0o600)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def build_connectivity_failure_issue(result: Dict[str, Any]) -> Dict[str, Any]:
    """Map a redacted smoke-test failure into the config validation contract."""
    status = result.get("status") if isinstance(result.get("status"), dict) else {}
    error_code = str(status.get("last_error_code") or "unknown_backend_error")
    return {
        "key": "GENERATION_BACKEND",
        "code": "connectivity_probe_failed",
        "severity": "error",
        "message": sanitize_diagnostic_text(
            result.get("message") or "Generation backend connectivity validation failed",
            max_length=500,
        ),
        "expected": "successful generation backend smoke test",
        "actual": "failed",
        "details": {
            "error_code": error_code,
            "backend_id": str(status.get("backend_id") or "unknown"),
            "health_status": str(status.get("health_status") or "failed"),
        },
    }


def build_auth_rollback_issue(
    *,
    current_map: Dict[str, str],
    target_map: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """Keep one-step rollback from bypassing the dedicated auth endpoint."""
    key = "ADMIN_AUTH_ENABLED"
    if current_map.get(key, "") == target_map.get(key, ""):
        return None
    return {
        "key": key,
        "code": "auth_settings_endpoint_required",
        "severity": "error",
        "message": (
            "The last-known-good snapshot has a different ADMIN_AUTH_ENABLED value. "
            "Restore authentication state through /api/v1/auth/settings first."
        ),
        "expected": "unchanged value or dedicated auth settings endpoint",
        "actual": "different snapshot value",
    }


def log_config_audit(
    *,
    actor: str,
    operation: str,
    outcome: str,
    keys: Iterable[str],
    config_version: Optional[str],
) -> None:
    """Emit a value-free operational audit record for configuration changes."""
    normalized_actor = re.sub(r"[^A-Za-z0-9_.:-]+", "_", actor or "unknown")[:64]
    payload = {
        "actor": normalized_actor or "unknown",
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config_version": config_version,
        "keys": sorted({str(key).upper() for key in keys}),
        "operation": operation,
        "outcome": outcome,
    }
    logger.info("System configuration audit %s", json.dumps(payload, sort_keys=True))
