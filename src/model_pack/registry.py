"""Persistent presentation metadata for validated Model Pack imports."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple

from src.model_pack.manifest import LICENSE_ID_PATTERN, MODEL_ID_PATTERN


MODEL_PACK_REGISTRY_SCHEMA_VERSION = 1
MODEL_PACK_REGISTRY_FILENAME = "model_pack_registry.json"
MAX_MODEL_PACK_REGISTRY_BYTES = 1024 * 1024
_RUNTIME_IDENTITY_LENGTH = 64


def default_model_pack_registry_path() -> Path:
    """Place metadata beside the existing configured application database."""
    database_path = Path(
        os.getenv("DATABASE_PATH", "./data/stock_analysis.db")
    ).expanduser()
    return database_path.parent / MODEL_PACK_REGISTRY_FILENAME


def _validated_entry(raw: Any) -> Dict[str, Any] | None:
    """Return one bounded registry entry or reject it without partial data."""
    if not isinstance(raw, dict) or set(raw) != {
        "runtime_identity",
        "model_id",
        "display_name",
        "minimum_memory_gb",
        "license_id",
    }:
        return None
    runtime_identity = str(raw.get("runtime_identity") or "").strip().lower()
    model_id = str(raw.get("model_id") or "").strip()
    display_name = str(raw.get("display_name") or "").strip()
    license_id = str(raw.get("license_id") or "").strip()
    minimum_memory_gb = raw.get("minimum_memory_gb")
    if (
        len(runtime_identity) != _RUNTIME_IDENTITY_LENGTH
        or any(character not in "0123456789abcdef" for character in runtime_identity)
        or MODEL_ID_PATTERN.fullmatch(model_id) is None
        or not 1 <= len(display_name) <= 160
        or any(ord(character) < 32 for character in display_name)
        or LICENSE_ID_PATTERN.fullmatch(license_id) is None
        or not isinstance(minimum_memory_gb, int)
        or isinstance(minimum_memory_gb, bool)
        or not 1 <= minimum_memory_gb <= 2048
    ):
        return None
    return {
        "runtime_identity": runtime_identity,
        "model_id": model_id,
        "display_name": display_name,
        "minimum_memory_gb": minimum_memory_gb,
        "license_id": license_id,
    }


class ModelPackRegistry:
    """Store bounded manifest presentation fields per configured Ollama runtime."""

    def __init__(self, path: Path | None = None) -> None:
        """Bind one atomic owner-only registry path."""
        self._path = Path(path) if path is not None else default_model_pack_registry_path()
        self._lock = threading.RLock()

    @staticmethod
    def _key(entry: Mapping[str, Any]) -> tuple[str, str]:
        """Return the case-insensitive runtime/model registry key."""
        return (
            str(entry["runtime_identity"]).lower(),
            str(entry["model_id"]).lower(),
        )

    def _read_locked(self) -> Tuple[Dict[str, Any], ...]:
        """Read valid bounded entries while failing closed on corruption."""
        try:
            size = self._path.stat().st_size
        except FileNotFoundError:
            return ()
        except OSError:
            return ()
        if size < 1 or size > MAX_MODEL_PACK_REGISTRY_BYTES:
            return ()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return ()
        if (
            not isinstance(raw, dict)
            or raw.get("schema_version") != MODEL_PACK_REGISTRY_SCHEMA_VERSION
            or not isinstance(raw.get("models"), list)
        ):
            return ()
        entries: Dict[tuple[str, str], Dict[str, Any]] = {}
        for candidate in raw["models"]:
            entry = _validated_entry(candidate)
            if entry is not None:
                entries[self._key(entry)] = entry
        return tuple(entries[key] for key in sorted(entries))

    def _write_locked(self, entries: Iterable[Mapping[str, Any]]) -> None:
        """Atomically write deterministically ordered registry entries."""
        ordered = sorted(
            (dict(entry) for entry in entries),
            key=lambda entry: self._key(entry),
        )
        payload = json.dumps(
            {
                "schema_version": MODEL_PACK_REGISTRY_SCHEMA_VERSION,
                "models": ordered,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > MAX_MODEL_PACK_REGISTRY_BYTES:
            raise OSError("Model Pack metadata registry exceeds its size limit")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.",
            suffix=".tmp",
            dir=str(self._path.parent),
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as file_obj:
                file_obj.write(payload)
                file_obj.flush()
                os.fsync(file_obj.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self._path)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    def register(
        self,
        *,
        runtime_identity: str,
        model_id: str,
        display_name: str,
        minimum_memory_gb: int,
        license_id: str,
    ) -> Dict[str, Any]:
        """Upsert only fields already validated by the Model Pack contract."""
        entry = _validated_entry(
            {
                "runtime_identity": runtime_identity,
                "model_id": model_id,
                "display_name": display_name,
                "minimum_memory_gb": minimum_memory_gb,
                "license_id": license_id,
            }
        )
        if entry is None:
            raise ValueError("Invalid Model Pack registry metadata")
        with self._lock:
            entries = {self._key(item): item for item in self._read_locked()}
            entries[self._key(entry)] = entry
            self._write_locked(entries.values())
        return dict(entry)

    def list_for_runtime(self, runtime_identity: str) -> Tuple[Dict[str, Any], ...]:
        """Return detached metadata for one opaque configured runtime identity."""
        normalized = str(runtime_identity or "").strip().lower()
        if (
            len(normalized) != _RUNTIME_IDENTITY_LENGTH
            or any(character not in "0123456789abcdef" for character in normalized)
        ):
            return ()
        with self._lock:
            return tuple(
                {
                    "model_id": entry["model_id"],
                    "display_name": entry["display_name"],
                    "minimum_memory_gb": entry["minimum_memory_gb"],
                    "license_id": entry["license_id"],
                }
                for entry in self._read_locked()
                if entry["runtime_identity"] == normalized
            )


__all__ = [
    "MAX_MODEL_PACK_REGISTRY_BYTES",
    "MODEL_PACK_REGISTRY_FILENAME",
    "MODEL_PACK_REGISTRY_SCHEMA_VERSION",
    "ModelPackRegistry",
    "default_model_pack_registry_path",
]
