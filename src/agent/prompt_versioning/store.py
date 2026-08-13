# -*- coding: utf-8 -*-
"""File-backed durable store for prompt / Skill artifact history."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple

try:  # POSIX process lock.
    import fcntl
except ImportError:  # pragma: no cover - Windows uses msvcrt below.
    fcntl = None

try:  # Windows process lock.
    import msvcrt
except ImportError:  # pragma: no cover - POSIX uses fcntl above.
    msvcrt = None

from src.agent.prompt_versioning.types import ArtifactKind, ArtifactSnapshot

INDEX_FILENAME = "index.json"
LOCK_FILENAME = ".index.lock"
STORE_SCHEMA_VERSION = 1
MAX_INDEX_BYTES = 64 * 1024 * 1024
MAX_ARTIFACTS = 4096


class PromptArtifactStoreError(RuntimeError):
    """Raised when persisted history is unreadable or violates its contract."""


def _artifact_key(kind: ArtifactKind | str, artifact_id: str) -> str:
    kind_value = kind.value if isinstance(kind, ArtifactKind) else str(kind)
    return f"{kind_value}:{str(artifact_id).strip()}"


class PromptArtifactStore:
    """Thread-safe JSON index of ArtifactSnapshot aggregates under a root dir."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self._index_path = self.root / INDEX_FILENAME
        self._lock = threading.RLock()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _exclusive_process_lock(self) -> Iterator[None]:
        """Serialize read-modify-write transactions across processes."""
        self._ensure_root()
        lock_path = self.root / LOCK_FILENAME
        with lock_path.open("a+b") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            elif msvcrt is not None:  # pragma: no cover - Windows only.
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:  # pragma: no cover - unsupported Python platform.
                raise PromptArtifactStoreError(
                    "No supported process-lock implementation is available"
                )
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                elif msvcrt is not None:  # pragma: no cover - Windows only.
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    def _read_index_unlocked(self) -> Dict[str, dict]:
        if not self._index_path.is_file():
            return {}
        try:
            if self._index_path.stat().st_size > MAX_INDEX_BYTES:
                raise PromptArtifactStoreError("Prompt artifact index exceeds the size limit")
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        except PromptArtifactStoreError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise PromptArtifactStoreError(
                f"Prompt artifact index is unreadable: {self._index_path}"
            ) from exc
        if not isinstance(raw, dict):
            raise PromptArtifactStoreError("Prompt artifact index must be a JSON object")
        if raw.get("schema_version") != STORE_SCHEMA_VERSION:
            raise PromptArtifactStoreError(
                f"Unsupported prompt artifact store schema: {raw.get('schema_version')!r}"
            )
        artifacts = raw.get("artifacts")
        if not isinstance(artifacts, dict):
            raise PromptArtifactStoreError("Prompt artifact index is missing artifacts")
        if len(artifacts) > MAX_ARTIFACTS:
            raise PromptArtifactStoreError("Prompt artifact index exceeds the artifact limit")
        result: Dict[str, dict] = {}
        for key, value in artifacts.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise PromptArtifactStoreError("Prompt artifact index contains an invalid entry")
            result[key] = value
        return result

    @staticmethod
    def _snapshot_from_raw(key: str, raw: dict) -> ArtifactSnapshot:
        try:
            snapshot = ArtifactSnapshot.from_mapping(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise PromptArtifactStoreError(
                f"Prompt artifact snapshot is invalid: {key}"
            ) from exc
        expected_key = _artifact_key(snapshot.kind, snapshot.artifact_id)
        if key != expected_key:
            raise PromptArtifactStoreError(
                f"Prompt artifact key mismatch: expected {expected_key!r}, got {key!r}"
            )
        return snapshot

    def _write_index_unlocked(self, artifacts: Dict[str, dict]) -> None:
        self._ensure_root()
        if len(artifacts) > MAX_ARTIFACTS:
            raise PromptArtifactStoreError("Prompt artifact index exceeds the artifact limit")
        payload = json.dumps(
            {
                "schema_version": STORE_SCHEMA_VERSION,
                "artifacts": artifacts,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        if len(payload.encode("utf-8")) > MAX_INDEX_BYTES:
            raise PromptArtifactStoreError("Prompt artifact index exceeds the size limit")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{INDEX_FILENAME}.",
            suffix=".tmp",
            dir=str(self.root),
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._index_path)
            if os.name != "nt":
                directory_fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    def get(
        self,
        kind: ArtifactKind | str,
        artifact_id: str,
    ) -> Optional[ArtifactSnapshot]:
        """Return one snapshot or None when absent."""
        key = _artifact_key(kind, artifact_id)
        with self._lock:
            with self._exclusive_process_lock():
                artifacts = self._read_index_unlocked()
                raw = artifacts.get(key)
                if raw is None:
                    return None
                return self._snapshot_from_raw(key, raw)

    def update(
        self,
        kind: ArtifactKind | str,
        artifact_id: str,
        updater: Callable[[Optional[ArtifactSnapshot]], ArtifactSnapshot],
    ) -> ArtifactSnapshot:
        """Atomically update one snapshot under a process-wide file lock."""
        key = _artifact_key(kind, artifact_id)
        with self._lock:
            with self._exclusive_process_lock():
                artifacts = self._read_index_unlocked()
                raw = artifacts.get(key)
                existing = self._snapshot_from_raw(key, raw) if raw is not None else None
                updated = updater(existing)
                updated.validate()
                if _artifact_key(updated.kind, updated.artifact_id) != key:
                    raise PromptArtifactStoreError("Artifact updater changed the storage key")
                artifacts[key] = updated.to_dict(include_content=True)
                self._write_index_unlocked(artifacts)
                return updated

    def list(
        self,
        *,
        kind: Optional[ArtifactKind | str] = None,
    ) -> List[ArtifactSnapshot]:
        """Return all snapshots, optionally filtered by kind."""
        kind_filter: Optional[str] = None
        if kind is not None:
            kind_filter = kind.value if isinstance(kind, ArtifactKind) else str(kind)
        results: List[ArtifactSnapshot] = []
        with self._lock:
            with self._exclusive_process_lock():
                artifacts = self._read_index_unlocked()
                for key, raw in artifacts.items():
                    if kind_filter is not None and str(raw.get("kind") or "") != kind_filter:
                        continue
                    results.append(self._snapshot_from_raw(key, raw))
        results.sort(key=lambda item: (item.kind.value, item.artifact_id))
        return results

    def clear(self) -> None:
        """Remove all stored artifacts (tests / maintenance)."""
        with self._lock:
            with self._exclusive_process_lock():
                if self._index_path.is_file():
                    try:
                        self._index_path.unlink()
                    except FileNotFoundError:
                        pass

    def keys(self) -> Tuple[str, ...]:
        """Return sorted store keys (kind:artifact_id)."""
        with self._lock:
            with self._exclusive_process_lock():
                return tuple(sorted(self._read_index_unlocked().keys()))


__all__ = [
    "INDEX_FILENAME",
    "LOCK_FILENAME",
    "PromptArtifactStoreError",
    "STORE_SCHEMA_VERSION",
    "PromptArtifactStore",
]
