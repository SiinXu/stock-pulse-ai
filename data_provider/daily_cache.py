"""Layered cache for normalized daily provider data."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import tempfile
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Optional

import pandas as pd


logger = logging.getLogger(__name__)


_CACHE_SCHEMA_VERSION = 1
_CACHE_ENABLED_DEFAULT = True
_CACHE_DIR_DEFAULT = "data/provider_cache/daily"
_MEMORY_TTL_SECONDS_DEFAULT = 60.0
_PERSISTENT_TTL_SECONDS_DEFAULT = 3600.0
_STALE_IF_ERROR_SECONDS_DEFAULT = 86400.0
_MEMORY_MAX_ENTRIES_DEFAULT = 256


def _read_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    logger.warning("Invalid boolean cache configuration name=%s; using default", name)
    return default


def _read_non_negative_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning("Invalid numeric cache configuration name=%s; using default", name)
        return default
    if not math.isfinite(value) or value < 0:
        logger.warning("Out-of-range cache configuration name=%s; using default", name)
        return default
    return value


def _read_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("Invalid integer cache configuration name=%s; using default", name)
        return default
    if value < 1:
        logger.warning("Out-of-range cache configuration name=%s; using default", name)
        return default
    return value


@dataclass(frozen=True)
class DailyCacheConfig:
    """Runtime policy for daily-data cache layers."""

    enabled: bool = _CACHE_ENABLED_DEFAULT
    directory: Path = Path(_CACHE_DIR_DEFAULT)
    memory_ttl_seconds: float = _MEMORY_TTL_SECONDS_DEFAULT
    persistent_ttl_seconds: float = _PERSISTENT_TTL_SECONDS_DEFAULT
    stale_if_error_seconds: float = _STALE_IF_ERROR_SECONDS_DEFAULT
    memory_max_entries: int = _MEMORY_MAX_ENTRIES_DEFAULT

    @classmethod
    def from_env(cls) -> "DailyCacheConfig":
        directory_value = os.getenv("PROVIDER_DAILY_CACHE_DIR", "").strip()
        directory = Path(directory_value or _CACHE_DIR_DEFAULT).expanduser()
        return cls(
            enabled=_read_bool_env(
                "PROVIDER_DAILY_CACHE_ENABLED",
                _CACHE_ENABLED_DEFAULT,
            ),
            directory=directory,
            memory_ttl_seconds=_read_non_negative_float_env(
                "PROVIDER_DAILY_CACHE_MEMORY_TTL_SECONDS",
                _MEMORY_TTL_SECONDS_DEFAULT,
            ),
            persistent_ttl_seconds=_read_non_negative_float_env(
                "PROVIDER_DAILY_CACHE_PERSISTENT_TTL_SECONDS",
                _PERSISTENT_TTL_SECONDS_DEFAULT,
            ),
            stale_if_error_seconds=_read_non_negative_float_env(
                "PROVIDER_DAILY_CACHE_STALE_IF_ERROR_SECONDS",
                _STALE_IF_ERROR_SECONDS_DEFAULT,
            ),
            memory_max_entries=_read_positive_int_env(
                "PROVIDER_DAILY_CACHE_MEMORY_MAX_ENTRIES",
                _MEMORY_MAX_ENTRIES_DEFAULT,
            ),
        )


@dataclass(frozen=True)
class DailyCacheKey:
    """Stable request identity shared by both cache layers."""

    symbol: str
    start_date: str
    end_date: str
    days: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "days": self.days,
        }

    def digest(self) -> str:
        material = json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def symbol_digest(self) -> str:
        return hashlib.sha256(self.symbol.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class DailyCacheRead:
    """One immutable cache read candidate."""

    frame: pd.DataFrame
    source_name: str
    layer: str
    age_seconds: float
    is_stale: bool
    stored_at: float


@dataclass(frozen=True)
class DailyCacheLookup:
    """Fresh hit plus an optional last-good candidate for provider failure."""

    fresh: Optional[DailyCacheRead]
    stale: Optional[DailyCacheRead]


@dataclass
class _DailyCacheEntry:
    key: DailyCacheKey
    frame: pd.DataFrame
    source_name: str
    stored_at: float


class DailyDataCache:
    """Bounded L1 memory cache backed by an atomic local JSON-table store."""

    def __init__(
        self,
        config: Optional[DailyCacheConfig] = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config or DailyCacheConfig.from_env()
        self._clock = clock
        self._lock = RLock()
        self._memory: "OrderedDict[str, _DailyCacheEntry]" = OrderedDict()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "stale_hits": 0,
            "writes": 0,
            "invalidations": 0,
        }

    @classmethod
    def from_env(cls) -> "DailyDataCache":
        return cls(DailyCacheConfig.from_env())

    @staticmethod
    def _age_seconds(now: float, stored_at: float) -> float:
        return max(0.0, now - stored_at)

    def _is_stale_eligible(self, age_seconds: float) -> bool:
        if self.config.stale_if_error_seconds <= 0:
            return False
        maximum_age = (
            self.config.persistent_ttl_seconds
            + self.config.stale_if_error_seconds
        )
        return self.config.persistent_ttl_seconds < age_seconds <= maximum_age

    @staticmethod
    def _newer_entry(
        first: Optional[_DailyCacheEntry],
        second: Optional[_DailyCacheEntry],
    ) -> Optional[_DailyCacheEntry]:
        if first is None:
            return second
        if second is None or first.stored_at >= second.stored_at:
            return first
        return second

    @staticmethod
    def _annotated_copy(
        entry: _DailyCacheEntry,
        *,
        cache_hit: bool,
        layer: str,
        age_seconds: float,
        is_stale: bool,
    ) -> pd.DataFrame:
        frame = entry.frame.copy(deep=True)
        frame.attrs["provider_cache"] = {
            "cache_hit": cache_hit,
            "layer": layer,
            "is_stale": is_stale,
            "stale_seconds": int(age_seconds),
            "stored_at": datetime.fromtimestamp(
                entry.stored_at,
                tz=timezone.utc,
            ).isoformat(),
            "source": entry.source_name,
        }
        return frame

    def _build_read(
        self,
        entry: _DailyCacheEntry,
        *,
        layer: str,
        now: float,
        is_stale: bool,
    ) -> DailyCacheRead:
        age_seconds = self._age_seconds(now, entry.stored_at)
        return DailyCacheRead(
            frame=self._annotated_copy(
                entry,
                cache_hit=True,
                layer=layer,
                age_seconds=age_seconds,
                is_stale=is_stale,
            ),
            source_name=entry.source_name,
            layer=layer,
            age_seconds=age_seconds,
            is_stale=is_stale,
            stored_at=entry.stored_at,
        )

    def _cache_path(self, key: DailyCacheKey) -> Path:
        filename = f"{key.symbol_digest()}-{key.digest()}.json"
        return self.config.directory / filename

    def _read_persistent(self, key: DailyCacheKey) -> Optional[_DailyCacheEntry]:
        path = self._cache_path(key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != _CACHE_SCHEMA_VERSION:
                raise ValueError("unsupported cache schema")
            if payload.get("key") != key.to_dict():
                raise ValueError("cache key mismatch")
            stored_at = float(payload["stored_at"])
            if not math.isfinite(stored_at) or stored_at < 0:
                raise ValueError("invalid cache timestamp")
            source_name = payload["source_name"]
            if not isinstance(source_name, str) or not source_name:
                raise ValueError("invalid cache source")
            frame_payload = payload["dataframe"]
            if not isinstance(frame_payload, str):
                raise TypeError("invalid cache frame")
            frame = pd.read_json(StringIO(frame_payload), orient="table")
            if frame.empty:
                raise ValueError("empty cache frame")
            return _DailyCacheEntry(
                key=key,
                frame=frame,
                source_name=source_name,
                stored_at=stored_at,
            )
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "provider_cache event=read_error data_type=daily_data "
                "cache_key=%s error_type=%s",
                key.digest()[:12],
                type(exc).__name__,
            )
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    "provider_cache event=cleanup_error data_type=daily_data "
                    "cache_key=%s",
                    key.digest()[:12],
                )
            return None

    def _write_persistent(self, entry: _DailyCacheEntry) -> bool:
        key_digest = entry.key.digest()
        temp_path: Optional[Path] = None
        try:
            self.config.directory.mkdir(parents=True, exist_ok=True)
            frame_payload = entry.frame.to_json(
                orient="table",
                date_format="iso",
                date_unit="ms",
            )
            payload = {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "key": entry.key.to_dict(),
                "stored_at": entry.stored_at,
                "source_name": entry.source_name,
                "dataframe": frame_payload,
            }
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.config.directory,
                prefix=f".{key_digest[:12]}-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
                temp_path = Path(handle.name)
            os.replace(temp_path, self._cache_path(entry.key))
            return True
        except (OSError, TypeError, ValueError, OverflowError) as exc:
            logger.warning(
                "provider_cache event=write_error data_type=daily_data "
                "cache_key=%s error_type=%s",
                key_digest[:12],
                type(exc).__name__,
            )
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return False

    def _record_event(self, event: str, layer: str) -> None:
        logger.info(
            "provider_cache event=%s data_type=daily_data layer=%s "
            "hits=%d misses=%d stale_hits=%d writes=%d invalidations=%d",
            event,
            layer,
            self._stats["hits"],
            self._stats["misses"],
            self._stats["stale_hits"],
            self._stats["writes"],
            self._stats["invalidations"],
        )

    def lookup(self, key: DailyCacheKey) -> DailyCacheLookup:
        """Return a fresh cache hit and retain stale data only as a fallback."""
        if not self.config.enabled:
            return DailyCacheLookup(fresh=None, stale=None)

        now = self._clock()
        digest = key.digest()
        with self._lock:
            memory_entry = self._memory.get(digest)
            stale_entry: Optional[_DailyCacheEntry] = None
            stale_layer = "none"
            if memory_entry is not None and memory_entry.key == key:
                memory_age = self._age_seconds(now, memory_entry.stored_at)
                if (
                    self.config.memory_ttl_seconds > 0
                    and memory_age <= self.config.memory_ttl_seconds
                ):
                    self._memory.move_to_end(digest)
                    self._stats["hits"] += 1
                    self._record_event("hit", "memory")
                    return DailyCacheLookup(
                        fresh=self._build_read(
                            memory_entry,
                            layer="memory",
                            now=now,
                            is_stale=False,
                        ),
                        stale=None,
                    )
                if self._is_stale_eligible(memory_age):
                    stale_entry = memory_entry
                    stale_layer = "memory"

            persistent_entry = self._read_persistent(key)
            if persistent_entry is not None:
                persistent_age = self._age_seconds(now, persistent_entry.stored_at)
                if (
                    self.config.persistent_ttl_seconds > 0
                    and persistent_age <= self.config.persistent_ttl_seconds
                ):
                    self._remember(digest, persistent_entry)
                    self._stats["hits"] += 1
                    self._record_event("hit", "persistent")
                    return DailyCacheLookup(
                        fresh=self._build_read(
                            persistent_entry,
                            layer="persistent",
                            now=now,
                            is_stale=False,
                        ),
                        stale=None,
                    )
                if self._is_stale_eligible(persistent_age):
                    newer = self._newer_entry(stale_entry, persistent_entry)
                    if newer is persistent_entry:
                        stale_layer = "persistent"
                    stale_entry = newer

            self._stats["misses"] += 1
            self._record_event("miss", "none")
            stale_read = None
            if stale_entry is not None:
                stale_read = self._build_read(
                    stale_entry,
                    layer=stale_layer,
                    now=now,
                    is_stale=True,
                )
            return DailyCacheLookup(fresh=None, stale=stale_read)

    def _remember(self, digest: str, entry: _DailyCacheEntry) -> None:
        self._memory[digest] = _DailyCacheEntry(
            key=entry.key,
            frame=entry.frame.copy(deep=True),
            source_name=entry.source_name,
            stored_at=entry.stored_at,
        )
        self._memory.move_to_end(digest)
        while len(self._memory) > self.config.memory_max_entries:
            self._memory.popitem(last=False)

    def store(
        self,
        key: DailyCacheKey,
        frame: pd.DataFrame,
        source_name: str,
    ) -> pd.DataFrame:
        """Store one successful provider result and return an annotated copy."""
        stored_at = self._clock()
        entry = _DailyCacheEntry(
            key=key,
            frame=frame.copy(deep=True),
            source_name=source_name,
            stored_at=stored_at,
        )
        if self.config.enabled:
            with self._lock:
                self._remember(key.digest(), entry)
                if self._write_persistent(entry):
                    self._stats["writes"] += 1
                self._record_event("write", "memory_persistent")
        return self._annotated_copy(
            entry,
            cache_hit=False,
            layer="provider",
            age_seconds=0.0,
            is_stale=False,
        )

    def use_stale(self, read: DailyCacheRead) -> DailyCacheRead:
        """Record that providers failed and the retained last-good value was used."""
        with self._lock:
            self._stats["stale_hits"] += 1
            self._record_event("stale_hit", read.layer)
        return read

    def invalidate(self, symbol: Optional[str] = None) -> int:
        """Remove all layer entries, optionally limited to one normalized symbol."""
        removed = 0
        with self._lock:
            for digest, entry in list(self._memory.items()):
                if symbol is None or entry.key.symbol == symbol:
                    self._memory.pop(digest, None)
                    removed += 1

            if self.config.directory.is_dir():
                if symbol is None:
                    candidates = self.config.directory.glob("*.json")
                else:
                    symbol_prefix = hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:16]
                    candidates = self.config.directory.glob(f"{symbol_prefix}-*.json")
                for path in candidates:
                    try:
                        path.unlink()
                        removed += 1
                    except FileNotFoundError:
                        continue
                    except OSError as exc:
                        logger.warning(
                            "provider_cache event=invalidate_error data_type=daily_data "
                            "error_type=%s",
                            type(exc).__name__,
                        )

            self._stats["invalidations"] += removed
            self._record_event("invalidate", "all" if symbol is None else "symbol")
        return removed

    def stats_snapshot(self) -> Dict[str, int]:
        """Return manager-local cache counters without exposing cache keys."""
        with self._lock:
            return dict(self._stats)
