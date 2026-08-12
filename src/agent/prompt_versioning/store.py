# -*- coding: utf-8 -*-
"""File-backed durable store for prompt / Skill artifact history."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from src.agent.prompt_versioning.types import ArtifactKind, ArtifactSnapshot

INDEX_FILENAME = "index.json"
STORE_SCHEMA_VERSION = 1


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

    def _read_index_unlocked(self) -> Dict[str, dict]:
        if not self._index_path.is_file():
            return {}
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        artifacts = raw.get("artifacts")
        if not isinstance(artifacts, dict):
            return {}
        result: Dict[str, dict] = {}
        for key, value in artifacts.items():
            if isinstance(key, str) and isinstance(value, dict):
                result[key] = value
        return result

    def _write_index_unlocked(self, artifacts: Dict[str, dict]) -> None:
        self._ensure_root()
        payload = json.dumps(
            {
                "schema_version": STORE_SCHEMA_VERSION,
                "artifacts": artifacts,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
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
            artifacts = self._read_index_unlocked()
            raw = artifacts.get(key)
            if raw is None:
                return None
            try:
                return ArtifactSnapshot.from_mapping(raw)
            except (KeyError, TypeError, ValueError):
                return None

    def put(self, snapshot: ArtifactSnapshot) -> ArtifactSnapshot:
        """Upsert one snapshot and persist the index."""
        key = _artifact_key(snapshot.kind, snapshot.artifact_id)
        payload = snapshot.to_dict(include_content=True)
        with self._lock:
            artifacts = self._read_index_unlocked()
            artifacts[key] = payload
            self._write_index_unlocked(artifacts)
        return snapshot

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
            artifacts = self._read_index_unlocked()
            for raw in artifacts.values():
                if not isinstance(raw, dict):
                    continue
                if kind_filter is not None and str(raw.get("kind") or "") != kind_filter:
                    continue
                try:
                    results.append(ArtifactSnapshot.from_mapping(raw))
                except (KeyError, TypeError, ValueError):
                    continue
        results.sort(key=lambda item: (item.kind.value, item.artifact_id))
        return results

    def clear(self) -> None:
        """Remove all stored artifacts (tests / maintenance)."""
        with self._lock:
            if self._index_path.is_file():
                try:
                    self._index_path.unlink()
                except FileNotFoundError:
                    pass
            elif self.root.is_dir():
                # Keep empty root; no-op when nothing persisted yet.
                pass

    def keys(self) -> Tuple[str, ...]:
        """Return sorted store keys (kind:artifact_id)."""
        with self._lock:
            return tuple(sorted(self._read_index_unlocked().keys()))


__all__ = [
    "INDEX_FILENAME",
    "STORE_SCHEMA_VERSION",
    "PromptArtifactStore",
]
