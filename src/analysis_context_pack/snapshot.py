# -*- coding: utf-8 -*-
"""Versioned immutable analysis-context snapshots (Issue #182).

Extends the existing AnalysisContextPack projection with a per-run seal:
one snapshot identity, a content digest, frozen market-input bags, and
helpers that block in-place mutation while stages write isolated outputs.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.schemas.analysis_context_pack import (
    PACK_VERSION,
    AnalysisContextPack,
    new_analysis_context_snapshot_id,
)
from src.task_execution import FrozenMapping, deep_freeze, deep_thaw


# Market / pack input keys that multi-agent stages must share read-only.
SNAPSHOT_DATA_KEYS: frozenset[str] = frozenset(
    {
        "realtime_quote",
        "daily_history",
        "chip_distribution",
        "trend_result",
        "news_context",
        "analysis_context_pack",
        "fundamental_context",
    }
)

AUDIT_META_KEYS: Tuple[str, ...] = (
    "snapshot_id",
    "snapshot_revision",
    "pack_version",
    "as_of",
    "content_digest",
    "created_at",
)


class SnapshotMutationError(TypeError):
    """Raised when code attempts to mutate a sealed analysis-context snapshot."""


class SnapshotConsistencyError(ValueError):
    """Raised when concurrent readers observe inconsistent snapshot identity."""


@dataclass(frozen=True)
class AnalysisContextSnapshot:
    """Immutable shared snapshot for one analysis run."""

    snapshot_id: str
    snapshot_revision: int
    pack_version: str
    as_of: Optional[str]
    content_digest: str
    pack: Mapping[str, Any]
    data: Mapping[str, Any]
    created_at: Optional[str] = None

    def read_data(self, key: str, default: Any = None) -> Any:
        """Return a detached mutable copy of one sealed data field."""
        if key not in self.data:
            return default
        return deep_thaw(self.data[key])

    def read_pack(self) -> Dict[str, Any]:
        """Return a detached mutable copy of the sealed pack payload."""
        return deep_thaw(self.pack)

    def audit_metadata(self) -> Dict[str, Any]:
        """Low-sensitivity identity fields for diagnostics and audit trails."""
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_revision": self.snapshot_revision,
            "pack_version": self.pack_version,
            "as_of": self.as_of,
            "content_digest": self.content_digest,
            "created_at": self.created_at,
        }

    def fingerprint(self) -> str:
        return self.content_digest


def normalize_snapshot_value(value: Any) -> Any:
    """Project a runtime value into a JSON-safe structure suitable for freeze."""
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return getattr(value, "value", str(value))
    if isinstance(value, (datetime, date)):
        text = value.isoformat()
        if isinstance(value, datetime) and value.tzinfo is not None:
            return text.replace("+00:00", "Z")
        return text
    if isinstance(value, Mapping):
        return {
            str(key): normalize_snapshot_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [normalize_snapshot_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [normalize_snapshot_value(item) for item in value]
        return sorted(normalized, key=lambda item: repr(item))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json")
        except TypeError:
            dumped = model_dump()
        return normalize_snapshot_value(dumped)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return normalize_snapshot_value(to_dict())
    raise TypeError(
        f"Unsupported analysis-context snapshot value: {type(value).__name__}"
    )


def compute_content_digest(payload: Mapping[str, Any]) -> str:
    """Stable SHA-256 digest over a normalized JSON payload."""
    encoded = json.dumps(
        normalize_snapshot_value(dict(payload)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_pack_as_of(pack: AnalysisContextPack | Mapping[str, Any]) -> Optional[str]:
    """Pick the latest ISO timestamp among block/item stamps and pack created_at."""
    payload = (
        pack.model_dump(mode="json")
        if isinstance(pack, AnalysisContextPack)
        else dict(pack)
    )
    candidates: List[str] = []
    as_of = payload.get("as_of")
    if isinstance(as_of, str) and as_of.strip():
        candidates.append(as_of.strip())
    created_at = payload.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        candidates.append(created_at.strip())
    blocks = payload.get("blocks")
    if isinstance(blocks, Mapping):
        for block in blocks.values():
            if not isinstance(block, Mapping):
                continue
            block_ts = block.get("timestamp")
            if isinstance(block_ts, str) and block_ts.strip():
                candidates.append(block_ts.strip())
            items = block.get("items")
            if not isinstance(items, Mapping):
                continue
            for item in items.values():
                if not isinstance(item, Mapping):
                    continue
                item_ts = item.get("timestamp")
                if isinstance(item_ts, str) and item_ts.strip():
                    candidates.append(item_ts.strip())
    if not candidates:
        return None
    return max(candidates, key=_timestamp_sort_key)


def stamp_pack_snapshot_identity(
    pack: AnalysisContextPack,
    *,
    snapshot_id: Optional[str] = None,
    snapshot_revision: int = 1,
    as_of: Optional[str] = None,
    data: Optional[Mapping[str, Any]] = None,
) -> AnalysisContextPack:
    """Fill per-run snapshot identity and content digest on a built pack."""
    if snapshot_revision < 1:
        raise ValueError("snapshot_revision must be >= 1")
    resolved_id = (snapshot_id or pack.snapshot_id or new_analysis_context_snapshot_id()).strip()
    resolved_as_of = as_of if as_of is not None else (pack.as_of or derive_pack_as_of(pack))
    metadata = dict(pack.metadata or {})
    identity_payload = {
        "subject": pack.subject.model_dump(mode="json"),
        "pack_version": pack.pack_version,
        "phase": pack.phase,
        "blocks": {
            key: block.model_dump(mode="json") for key, block in (pack.blocks or {}).items()
        },
        "data_quality": pack.data_quality.model_dump(mode="json"),
        "as_of": resolved_as_of,
        "data": normalize_snapshot_value(dict(data or {})),
    }
    digest = compute_content_digest(identity_payload)
    metadata["content_digest"] = digest
    metadata["snapshot_sealed"] = True
    return pack.model_copy(
        update={
            "snapshot_id": resolved_id,
            "snapshot_revision": int(snapshot_revision),
            "as_of": resolved_as_of,
            "metadata": metadata,
        },
        deep=True,
    )


def seal_analysis_context_snapshot(
    pack: AnalysisContextPack | Mapping[str, Any],
    data: Optional[Mapping[str, Any]] = None,
    *,
    snapshot_id: Optional[str] = None,
    snapshot_revision: Optional[int] = None,
    as_of: Optional[str] = None,
) -> AnalysisContextSnapshot:
    """Seal pack + market inputs into one immutable shared snapshot."""
    if isinstance(pack, AnalysisContextPack):
        stamped = stamp_pack_snapshot_identity(
            pack,
            snapshot_id=snapshot_id,
            snapshot_revision=snapshot_revision or pack.snapshot_revision or 1,
            as_of=as_of,
            data=data,
        )
        pack_payload = stamped.model_dump(mode="json")
        resolved_id = stamped.snapshot_id
        resolved_revision = stamped.snapshot_revision
        resolved_as_of = stamped.as_of
        pack_version = stamped.pack_version
        created_at = pack_payload.get("created_at")
        digest = str((stamped.metadata or {}).get("content_digest") or "")
    else:
        pack_payload = normalize_snapshot_value(dict(pack))
        if not isinstance(pack_payload, dict):
            raise TypeError("pack mapping must normalize to a dict")
        resolved_id = str(
            snapshot_id
            or pack_payload.get("snapshot_id")
            or new_analysis_context_snapshot_id()
        ).strip()
        resolved_revision = int(
            snapshot_revision
            if snapshot_revision is not None
            else pack_payload.get("snapshot_revision") or 1
        )
        if resolved_revision < 1:
            raise ValueError("snapshot_revision must be >= 1")
        resolved_as_of = (
            as_of
            if as_of is not None
            else pack_payload.get("as_of") or derive_pack_as_of(pack_payload)
        )
        pack_version = str(pack_payload.get("pack_version") or PACK_VERSION)
        created_at = pack_payload.get("created_at")
        pack_payload["snapshot_id"] = resolved_id
        pack_payload["snapshot_revision"] = resolved_revision
        pack_payload["as_of"] = resolved_as_of
        pack_payload["pack_version"] = pack_version
        metadata = pack_payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            pack_payload["metadata"] = metadata
        digest = compute_content_digest(
            {
                "subject": pack_payload.get("subject"),
                "pack_version": pack_version,
                "phase": pack_payload.get("phase"),
                "blocks": pack_payload.get("blocks"),
                "data_quality": pack_payload.get("data_quality"),
                "as_of": resolved_as_of,
                "data": normalize_snapshot_value(dict(data or {})),
            }
        )
        metadata["content_digest"] = digest
        metadata["snapshot_sealed"] = True

    normalized_data = _select_snapshot_data(data)
    frozen_pack = deep_freeze(normalize_snapshot_value(pack_payload))
    frozen_data = deep_freeze(normalized_data)
    if not digest:
        digest = compute_content_digest(
            {
                "pack": normalize_snapshot_value(pack_payload),
                "data": normalized_data,
            }
        )
    return AnalysisContextSnapshot(
        snapshot_id=resolved_id,
        snapshot_revision=resolved_revision,
        pack_version=pack_version,
        as_of=resolved_as_of if isinstance(resolved_as_of, str) else None,
        content_digest=digest,
        pack=frozen_pack,
        data=frozen_data,
        created_at=created_at if isinstance(created_at, str) else None,
    )


def assert_snapshots_consistent(
    left: AnalysisContextSnapshot,
    right: AnalysisContextSnapshot,
) -> None:
    """Fail fast when two stage readers do not share the same sealed snapshot."""
    if left.snapshot_id != right.snapshot_id:
        raise SnapshotConsistencyError(
            "analysis context snapshot_id mismatch across stages"
        )
    if left.snapshot_revision != right.snapshot_revision:
        raise SnapshotConsistencyError(
            "analysis context snapshot_revision mismatch across stages"
        )
    if left.content_digest != right.content_digest:
        raise SnapshotConsistencyError(
            "analysis context content_digest mismatch across stages"
        )


def concurrent_snapshot_reads(
    snapshot: AnalysisContextSnapshot,
    *,
    keys: Optional[Sequence[str]] = None,
    workers: int = 4,
) -> List[Dict[str, Any]]:
    """Read the same sealed snapshot from multiple workers (test helper)."""
    if workers < 1:
        raise ValueError("workers must be >= 1")
    selected = list(keys) if keys is not None else list(snapshot.data.keys())
    barrier = threading.Barrier(workers)
    results: List[Optional[Dict[str, Any]]] = [None] * workers
    errors: List[BaseException] = []
    lock = threading.Lock()

    def _worker(index: int) -> None:
        try:
            barrier.wait(timeout=5)
            payload = {
                "audit": snapshot.audit_metadata(),
                "data": {key: snapshot.read_data(key) for key in selected},
                "pack": snapshot.read_pack(),
            }
            results[index] = payload
        except BaseException as exc:  # noqa: BLE001 - surface worker failures in tests
            with lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=_worker, args=(index,), name=f"snapshot-reader-{index}")
        for index in range(workers)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    if errors:
        raise errors[0]
    if any(item is None for item in results):
        raise RuntimeError("concurrent snapshot read did not complete")
    first = results[0]
    assert first is not None
    for other in results[1:]:
        assert other is not None
        if other["audit"] != first["audit"]:
            raise SnapshotConsistencyError("concurrent readers saw different audit metadata")
        if other["data"] != first["data"]:
            raise SnapshotConsistencyError("concurrent readers saw different data payloads")
        if other["pack"] != first["pack"]:
            raise SnapshotConsistencyError("concurrent readers saw different pack payloads")
    return [item for item in results if item is not None]


def freeze_market_data_mapping(data: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a mapping with snapshot market keys replaced by frozen values."""
    frozen: Dict[str, Any] = dict(data)
    for key in SNAPSHOT_DATA_KEYS:
        if key not in frozen or frozen[key] is None:
            continue
        frozen[key] = deep_freeze(normalize_snapshot_value(frozen[key]))
    return frozen


def is_frozen_snapshot_value(value: Any) -> bool:
    """Return True when *value* is a deeply frozen container."""
    return isinstance(value, (FrozenMapping, tuple, frozenset))


def _select_snapshot_data(data: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(data, Mapping):
        return {}
    selected: Dict[str, Any] = {}
    for key in SNAPSHOT_DATA_KEYS:
        if key not in data or data[key] is None:
            continue
        selected[key] = normalize_snapshot_value(data[key])
    return selected


def _timestamp_sort_key(value: str) -> str:
    text = value.strip()
    if text.endswith("Z"):
        return text[:-1] + "+00:00"
    return text


__all__ = [
    "AUDIT_META_KEYS",
    "AnalysisContextSnapshot",
    "SNAPSHOT_DATA_KEYS",
    "SnapshotConsistencyError",
    "SnapshotMutationError",
    "assert_snapshots_consistent",
    "compute_content_digest",
    "concurrent_snapshot_reads",
    "derive_pack_as_of",
    "freeze_market_data_mapping",
    "is_frozen_snapshot_value",
    "normalize_snapshot_value",
    "seal_analysis_context_snapshot",
    "stamp_pack_snapshot_identity",
]
