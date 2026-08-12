# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Durable, fail-closed store for write-side capability declarations."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from src.capability_registry.write_models import (
    MAX_WRITE_ENTRIES,
    WRITE_SCHEMA_VERSION,
    WriteCapabilityEntry,
    WriteRegistrySnapshot,
)

Clock = Callable[[], datetime]

WRITE_REGISTRY_FILENAME = "capability_write_registry.json"
MAX_WRITE_REGISTRY_BYTES = 2 * 1024 * 1024


class WriteRegistryStoreError(RuntimeError):
    """Stable failure for write-registry persistence problems."""

    def __init__(self, error_code: str, message: str = "") -> None:
        super().__init__(message or error_code)
        self.error_code = error_code


def default_write_registry_path() -> Path:
    """Place the write registry beside the configured application database."""

    override = (os.getenv("CAPABILITY_WRITE_REGISTRY_PATH") or "").strip()
    if override:
        return Path(override).expanduser()
    database_path = Path(
        os.getenv("DATABASE_PATH", "./data/stock_analysis.db")
    ).expanduser()
    return database_path.parent / WRITE_REGISTRY_FILENAME


class CapabilityWriteStore:
    """Atomic JSON owner for capability declarations."""

    def __init__(self, path: Path | None = None, *, clock: Clock | None = None) -> None:
        self._path = Path(path) if path is not None else default_write_registry_path()
        self._lock = threading.RLock()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def path(self) -> Path:
        return self._path

    def _now_iso(self) -> str:
        return self._clock().astimezone(timezone.utc).isoformat()

    def load(self) -> WriteRegistrySnapshot:
        """Load the registry, failing closed on corruption."""

        with self._lock:
            return self._load_locked()

    def _load_locked(self) -> WriteRegistrySnapshot:
        try:
            size = self._path.stat().st_size
        except FileNotFoundError:
            return WriteRegistrySnapshot(as_of=self._now_iso())
        except OSError as exc:
            raise WriteRegistryStoreError(
                "write_registry_unreadable",
                "capability write registry path is unreadable",
            ) from exc
        if size < 1:
            return WriteRegistrySnapshot(as_of=self._now_iso())
        if size > MAX_WRITE_REGISTRY_BYTES:
            raise WriteRegistryStoreError(
                "write_registry_too_large",
                "capability write registry exceeds size limit",
            )
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
            RecursionError,
        ) as exc:
            raise WriteRegistryStoreError(
                "write_registry_corrupt",
                "capability write registry is corrupt or unreadable",
            ) from exc
        if not isinstance(raw, dict):
            raise WriteRegistryStoreError(
                "write_registry_corrupt",
                "capability write registry root must be an object",
            )
        if raw.get("schema_version") != WRITE_SCHEMA_VERSION:
            raise WriteRegistryStoreError(
                "write_registry_schema_unsupported",
                "capability write registry schema version is unsupported",
            )
        generation = raw.get("generation", 0)
        if type(generation) is not int or generation < 0:
            raise WriteRegistryStoreError(
                "write_registry_corrupt",
                "capability write registry generation is invalid",
            )
        entries_raw = raw.get("entries")
        if not isinstance(entries_raw, list):
            raise WriteRegistryStoreError(
                "write_registry_corrupt",
                "capability write registry entries must be a list",
            )
        if len(entries_raw) > MAX_WRITE_ENTRIES:
            raise WriteRegistryStoreError(
                "write_registry_too_large",
                "capability write registry exceeds entry capacity",
            )
        try:
            entries = tuple(
                WriteCapabilityEntry.from_dict(item) for item in entries_raw
            )
            return WriteRegistrySnapshot(
                generation=generation,
                as_of=str(raw.get("as_of") or self._now_iso()),
                entries=entries,
            )
        except (TypeError, ValueError) as exc:
            raise WriteRegistryStoreError(
                "write_registry_corrupt",
                f"capability write registry entry invalid: {exc}",
            ) from exc

    def _write_locked(self, snapshot: WriteRegistrySnapshot) -> None:
        payload = json.dumps(
            snapshot.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > MAX_WRITE_REGISTRY_BYTES:
            raise WriteRegistryStoreError(
                "write_registry_too_large",
                "capability write registry payload exceeds size limit",
            )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.",
            suffix=".tmp",
            dir=str(self._path.parent),
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self._path)
        except OSError as exc:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
            raise WriteRegistryStoreError(
                "write_registry_persist_failed",
                "capability write registry could not be persisted",
            ) from exc
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    def replace_entries(
        self,
        entries: Iterable[WriteCapabilityEntry],
        *,
        generation: int,
    ) -> WriteRegistrySnapshot:
        """Atomically replace all entries at the given generation."""

        ordered = tuple(
            sorted(entries, key=lambda item: (item.domain, item.capability_id))
        )
        if len(ordered) > MAX_WRITE_ENTRIES:
            raise WriteRegistryStoreError(
                "write_registry_too_large",
                "capability write registry exceeds entry capacity",
            )
        snapshot = WriteRegistrySnapshot(
            generation=generation,
            as_of=self._now_iso(),
            entries=ordered,
        )
        with self._lock:
            self._write_locked(snapshot)
            return snapshot

    def get(self, capability_id: str) -> Optional[WriteCapabilityEntry]:
        snapshot = self.load()
        for entry in snapshot.entries:
            if entry.capability_id == capability_id:
                return entry
        return None
