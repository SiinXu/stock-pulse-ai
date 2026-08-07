# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persisted per-plugin enable/disable state for the lifecycle manager.

Trusted-plugin model: this store only records operator intent for plugins that
are already registered through the existing discovery path (built-ins and
``PLUGINS_DIR``). It never fetches remote code and never auto-enables newly
discovered package directories.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Mapping

from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text


logger = logging.getLogger(__name__)

STATE_SCHEMA_VERSION = 1
DEFAULT_STATE_FILENAME = "plugin_lifecycle_state.json"
ENV_STATE_PATH = "PLUGIN_STATE_PATH"


def resolve_default_state_path() -> Path:
    """Resolve the on-disk state path from env or the database data directory."""

    configured = os.getenv(ENV_STATE_PATH)
    if isinstance(configured, str) and configured.strip():
        return Path(configured.strip()).expanduser()
    database_path = os.getenv("DATABASE_PATH", "./data/stock_analysis.db")
    data_dir = Path(str(database_path)).expanduser().parent
    return data_dir / DEFAULT_STATE_FILENAME


def _running_under_pytest() -> bool:
    """Detect pytest so default managers do not share a process-wide state file."""

    return (
        os.getenv("PYTEST_CURRENT_TEST") is not None
        or "pytest" in sys.modules
        or os.getenv("STOCKPULSE_PLUGIN_STATE_MEMORY", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )


class PluginLifecycleStateStore:
    """Thread-safe denylist of disabled plugin IDs with optional JSON persistence.

    Missing IDs are treated as enabled so existing ``load_all`` behavior remains
    the default for reviewed plugins. Operators disable explicitly; the denylist
    is what survives process restarts when a path is configured.
    """

    def __init__(self, path: str | Path | None = None, *, persist: bool = True) -> None:
        self._path: Path | None
        if path is None:
            self._path = None
        else:
            self._path = Path(path).expanduser()
        self._persist = bool(persist) and self._path is not None
        self._lock = threading.RLock()
        self._disabled: set[str] = set()
        if self._persist:
            self._load_from_disk()

    @classmethod
    def from_env(cls) -> "PluginLifecycleStateStore":
        """Build the process store using ``PLUGIN_STATE_PATH`` or the data dir.

        Explicit ``PLUGIN_STATE_PATH`` always wins. Otherwise production defaults
        to the database data directory, while pytest runs use an in-memory store
        so suite cases do not couple through a shared file.
        """

        configured = os.getenv(ENV_STATE_PATH)
        if isinstance(configured, str) and configured.strip():
            return cls(Path(configured.strip()).expanduser(), persist=True)
        if _running_under_pytest():
            return cls.memory()
        return cls(resolve_default_state_path(), persist=True)

    @classmethod
    def memory(cls) -> "PluginLifecycleStateStore":
        """Return a non-persistent store for isolated unit tests."""

        return cls(path=None, persist=False)

    @property
    def path(self) -> Path | None:
        """Return the configured persistence path, if any."""

        return self._path

    def is_disabled(self, plugin_id: str) -> bool:
        """Return whether the plugin is explicitly disabled by operator intent."""

        with self._lock:
            return plugin_id in self._disabled

    def desired_enabled(self, plugin_id: str) -> bool:
        """Return the persisted desired enabled flag (default True)."""

        return not self.is_disabled(plugin_id)

    def disabled_plugin_ids(self) -> frozenset[str]:
        """Return a snapshot of every explicitly disabled plugin ID."""

        with self._lock:
            return frozenset(self._disabled)

    def set_disabled(self, plugin_id: str, disabled: bool) -> None:
        """Record operator intent and persist when a path is configured."""

        if type(plugin_id) is not str or not plugin_id:
            raise ValueError("plugin_id must be a non-empty string")
        with self._lock:
            if disabled:
                self._disabled.add(plugin_id)
            else:
                self._disabled.discard(plugin_id)
            if self._persist:
                self._write_to_disk()

    def _load_from_disk(self) -> None:
        path = self._path
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            log_safe_exception(
                logger,
                "Plugin lifecycle state could not be read; treating all as enabled",
                exc,
                error_code="plugin_state_unavailable",
                context={
                    "path": sanitize_diagnostic_text(str(path), max_length=256) or "state",
                },
            )
            return
        if not isinstance(payload, Mapping):
            return
        version = payload.get("version")
        if version not in (None, STATE_SCHEMA_VERSION, 1):
            logger.warning(
                "Plugin lifecycle state version unsupported; ignoring file",
                extra={"error_code": "plugin_state_version_unsupported"},
            )
            return
        disabled_raw = payload.get("disabled_plugin_ids", [])
        if not isinstance(disabled_raw, list):
            return
        disabled: set[str] = set()
        for item in disabled_raw:
            if type(item) is str and item:
                disabled.add(item)
        self._disabled = disabled

    def _write_to_disk(self) -> None:
        path = self._path
        if path is None:
            return
        payload = {
            "version": STATE_SCHEMA_VERSION,
            "disabled_plugin_ids": sorted(self._disabled),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tmp_path.replace(path)
        except OSError as exc:
            log_safe_exception(
                logger,
                "Plugin lifecycle state could not be written",
                exc,
                error_code="plugin_state_write_failed",
                context={
                    "path": sanitize_diagnostic_text(str(path), max_length=256) or "state",
                },
            )
