"""Layered cache for normalized daily provider data.

This module is both a speed cache (default ``auto`` mode) and the local-first
market-data store for offline / privacy workflows (``local_only`` / ``refresh``).

Storage choice: reuse the existing process memory + atomic JSON-table layout under
``PROVIDER_DAILY_CACHE_DIR``. No new database dependency is introduced so desktop
and low-friction installs keep working without extra runtime requirements.
"""

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
from enum import Enum
from io import StringIO
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

import pandas as pd


logger = logging.getLogger(__name__)


_CACHE_SCHEMA_VERSION = 1
_CACHE_ENABLED_DEFAULT = True
_CACHE_DIR_DEFAULT = "data/provider_cache/daily"
_MEMORY_TTL_SECONDS_DEFAULT = 60.0
_PERSISTENT_TTL_SECONDS_DEFAULT = 3600.0
_STALE_IF_ERROR_SECONDS_DEFAULT = 86400.0
_MEMORY_MAX_ENTRIES_DEFAULT = 256
_MARKET_DATA_MODE_ENV = "PROVIDER_MARKET_DATA_MODE"
_DEFAULT_REQUIRED_FIELDS: Tuple[str, ...] = ("daily_ohlcv",)


class MarketDataFetchMode(str, Enum):
    """Three-way local-first market data policy.

    - ``auto`` (default): prefer fresh local data; miss may go upstream.
    - ``local_only``: use only the local store; miss raises structured error;
      **never** performs network fetch.
    - ``refresh``: always fetch upstream and update the local store.
    """

    AUTO = "auto"
    LOCAL_ONLY = "local_only"
    REFRESH = "refresh"


def parse_market_data_fetch_mode(raw_value: Optional[str]) -> MarketDataFetchMode:
    """Parse a mode string; invalid values fall back to ``auto`` with a warning."""
    if raw_value is None or not str(raw_value).strip():
        return MarketDataFetchMode.AUTO
    normalized = str(raw_value).strip().lower().replace("-", "_")
    for mode in MarketDataFetchMode:
        if mode.value == normalized:
            return mode
    logger.warning(
        "Invalid market data fetch mode name=%s value=%s; using default auto",
        _MARKET_DATA_MODE_ENV,
        raw_value,
    )
    return MarketDataFetchMode.AUTO


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
    fetch_mode: MarketDataFetchMode = MarketDataFetchMode.AUTO

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
            fetch_mode=parse_market_data_fetch_mode(os.getenv(_MARKET_DATA_MODE_ENV)),
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

    key: DailyCacheKey
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


@dataclass(frozen=True)
class LocalDataMissing:
    """Structured description of what local market data is absent.

    Callers and UX layers should surface these fields so operators know what
    to warm into the local store (symbol, window, fields) instead of a bare
    "insufficient data" string.
    """

    symbol: str
    start_date: str
    end_date: str
    days: int
    fields: Tuple[str, ...]
    mode: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "days": self.days,
            "fields": list(self.fields),
            "mode": self.mode,
            "reason": self.reason,
        }


class LocalDataMissingError(Exception):
    """Raised when ``local_only`` mode cannot satisfy a request from local data."""

    def __init__(self, missing: LocalDataMissing) -> None:
        self.missing = missing
        fields = ",".join(missing.fields) if missing.fields else "-"
        start = missing.start_date or "-"
        end = missing.end_date or "-"
        message = (
            f"Local market data missing for symbol={missing.symbol} "
            f"start_date={start} end_date={end} days={missing.days} "
            f"fields={fields} (mode={missing.mode}, reason={missing.reason})"
        )
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        return self.missing.to_dict()


@dataclass(frozen=True)
class MarketDataResolveResult:
    """Outcome of a mode-aware local-first resolve."""

    frame: pd.DataFrame
    source_name: str
    mode: str
    from_cache: bool
    is_stale: bool
    layer: str


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
            "local_only_hits": 0,
            "local_only_misses": 0,
            "refresh_fetches": 0,
        }

    @classmethod
    def from_env(cls) -> "DailyDataCache":
        return cls(DailyCacheConfig.from_env())

    @property
    def fetch_mode(self) -> MarketDataFetchMode:
        return self.config.fetch_mode

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

    def _is_beyond_fresh_ttl(self, age_seconds: float) -> bool:
        if self.config.persistent_ttl_seconds <= 0:
            return True
        return age_seconds > self.config.persistent_ttl_seconds

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
        fetch_mode: Optional[str] = None,
    ) -> pd.DataFrame:
        frame = entry.frame.copy(deep=True)
        meta: Dict[str, Any] = {
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
        if fetch_mode is not None:
            meta["fetch_mode"] = fetch_mode
        frame.attrs["provider_cache"] = meta
        return frame

    def _build_read(
        self,
        entry: _DailyCacheEntry,
        *,
        layer: str,
        now: float,
        is_stale: bool,
        fetch_mode: Optional[str] = None,
    ) -> DailyCacheRead:
        age_seconds = self._age_seconds(now, entry.stored_at)
        return DailyCacheRead(
            key=entry.key,
            frame=self._annotated_copy(
                entry,
                cache_hit=True,
                layer=layer,
                age_seconds=age_seconds,
                is_stale=is_stale,
                fetch_mode=fetch_mode,
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
            "hits=%d misses=%d stale_hits=%d writes=%d invalidations=%d "
            "local_only_hits=%d local_only_misses=%d refresh_fetches=%d",
            event,
            layer,
            self._stats["hits"],
            self._stats["misses"],
            self._stats["stale_hits"],
            self._stats["writes"],
            self._stats["invalidations"],
            self._stats["local_only_hits"],
            self._stats["local_only_misses"],
            self._stats["refresh_fetches"],
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

    def lookup_local_store(self, key: DailyCacheKey) -> Optional[DailyCacheRead]:
        """Return any local entry regardless of fresh TTL (local-store semantics).

        Used by ``local_only`` mode: presence in the local store is enough to
        serve offline analysis. ``is_stale`` still reflects whether the entry is
        beyond the configured fresh TTL so callers can surface freshness.
        """
        if not self.config.enabled:
            return None

        now = self._clock()
        digest = key.digest()
        mode_value = self.config.fetch_mode.value
        with self._lock:
            memory_entry = self._memory.get(digest)
            if memory_entry is not None and memory_entry.key != key:
                memory_entry = None
            persistent_entry = self._read_persistent(key)
            entry = self._newer_entry(memory_entry, persistent_entry)
            if entry is None:
                return None
            layer = "memory" if entry is memory_entry else "persistent"
            if entry is persistent_entry and memory_entry is not entry:
                self._remember(digest, entry)
            age_seconds = self._age_seconds(now, entry.stored_at)
            is_stale = self._is_beyond_fresh_ttl(age_seconds)
            return self._build_read(
                entry,
                layer=layer,
                now=now,
                is_stale=is_stale,
                fetch_mode=mode_value,
            )

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
            fetch_mode=self.config.fetch_mode.value,
        )

    def use_stale(self, read: DailyCacheRead) -> Optional[DailyCacheRead]:
        """Revalidate and record a last-good value after the provider chain fails."""
        with self._lock:
            now = self._clock()
            current_age = self._age_seconds(now, read.stored_at)
            if not self._is_stale_eligible(current_age):
                self._record_event("stale_expired", read.layer)
                return None
            refreshed = self._build_read(
                _DailyCacheEntry(
                    key=read.key,
                    frame=read.frame,
                    source_name=read.source_name,
                    stored_at=read.stored_at,
                ),
                layer=read.layer,
                now=now,
                is_stale=True,
            )
            self._stats["stale_hits"] += 1
            self._record_event("stale_hit", read.layer)
        return refreshed

    def build_local_missing(
        self,
        key: DailyCacheKey,
        *,
        fields: Sequence[str] = _DEFAULT_REQUIRED_FIELDS,
        reason: str = "no_local_entry",
    ) -> LocalDataMissing:
        """Build a structured missing-data payload for ``local_only`` failures."""
        normalized_fields = tuple(
            str(item).strip() for item in fields if str(item).strip()
        ) or _DEFAULT_REQUIRED_FIELDS
        return LocalDataMissing(
            symbol=key.symbol,
            start_date=key.start_date,
            end_date=key.end_date,
            days=key.days,
            fields=normalized_fields,
            mode=MarketDataFetchMode.LOCAL_ONLY.value,
            reason=reason,
        )

    def resolve(
        self,
        key: DailyCacheKey,
        *,
        network_fetch: Optional[Callable[[], Tuple[pd.DataFrame, str]]] = None,
        required_fields: Sequence[str] = _DEFAULT_REQUIRED_FIELDS,
        mode: Optional[MarketDataFetchMode] = None,
    ) -> MarketDataResolveResult:
        """Resolve daily data under the configured (or explicit) fetch mode.

        ``network_fetch`` must perform the upstream call when invoked. In
        ``local_only`` mode this callable is **never** invoked, even if provided.
        Callers that integrate with ``DataFetcherManager.get_daily_data`` should
        pass a callback that runs the existing provider chain (see Integration
        Point in the PR for T14).
        """
        active_mode = mode or self.config.fetch_mode
        mode_value = active_mode.value

        if active_mode is MarketDataFetchMode.LOCAL_ONLY:
            return self._resolve_local_only(
                key,
                required_fields=required_fields,
            )

        if active_mode is MarketDataFetchMode.REFRESH:
            return self._resolve_refresh(
                key,
                network_fetch=network_fetch,
                mode_value=mode_value,
            )

        return self._resolve_auto(
            key,
            network_fetch=network_fetch,
            mode_value=mode_value,
        )

    def _resolve_local_only(
        self,
        key: DailyCacheKey,
        *,
        required_fields: Sequence[str],
    ) -> MarketDataResolveResult:
        # Hard guarantee: no network path is entered from this branch.
        if not self.config.enabled:
            missing = self.build_local_missing(
                key,
                fields=required_fields,
                reason="cache_disabled",
            )
            with self._lock:
                self._stats["local_only_misses"] += 1
                self._record_event("local_only_miss", "disabled")
            raise LocalDataMissingError(missing)

        local = self.lookup_local_store(key)
        if local is None:
            missing = self.build_local_missing(
                key,
                fields=required_fields,
                reason="no_local_entry",
            )
            with self._lock:
                self._stats["local_only_misses"] += 1
                self._record_event("local_only_miss", "none")
            raise LocalDataMissingError(missing)

        with self._lock:
            self._stats["local_only_hits"] += 1
            self._stats["hits"] += 1
            self._record_event("local_only_hit", local.layer)
        return MarketDataResolveResult(
            frame=local.frame,
            source_name=local.source_name,
            mode=MarketDataFetchMode.LOCAL_ONLY.value,
            from_cache=True,
            is_stale=local.is_stale,
            layer=local.layer,
        )

    def _resolve_refresh(
        self,
        key: DailyCacheKey,
        *,
        network_fetch: Optional[Callable[[], Tuple[pd.DataFrame, str]]],
        mode_value: str,
    ) -> MarketDataResolveResult:
        if network_fetch is None:
            raise ValueError(
                "network_fetch is required when PROVIDER_MARKET_DATA_MODE=refresh"
            )
        frame, source_name = network_fetch()
        if frame is None or (isinstance(frame, pd.DataFrame) and frame.empty):
            raise ValueError("network_fetch returned empty daily data in refresh mode")
        annotated = self.store(key, frame, source_name)
        with self._lock:
            self._stats["refresh_fetches"] += 1
            self._record_event("refresh_fetch", "provider")
        return MarketDataResolveResult(
            frame=annotated,
            source_name=source_name,
            mode=mode_value,
            from_cache=False,
            is_stale=False,
            layer="provider",
        )

    def _resolve_auto(
        self,
        key: DailyCacheKey,
        *,
        network_fetch: Optional[Callable[[], Tuple[pd.DataFrame, str]]],
        mode_value: str,
    ) -> MarketDataResolveResult:
        lookup = self.lookup(key)
        if lookup.fresh is not None:
            return MarketDataResolveResult(
                frame=lookup.fresh.frame,
                source_name=lookup.fresh.source_name,
                mode=mode_value,
                from_cache=True,
                is_stale=False,
                layer=lookup.fresh.layer,
            )
        if network_fetch is None:
            raise ValueError(
                "network_fetch is required when PROVIDER_MARKET_DATA_MODE=auto "
                "and no fresh local entry exists"
            )
        frame, source_name = network_fetch()
        if frame is None or (isinstance(frame, pd.DataFrame) and frame.empty):
            raise ValueError("network_fetch returned empty daily data in auto mode")
        annotated = self.store(key, frame, source_name)
        return MarketDataResolveResult(
            frame=annotated,
            source_name=source_name,
            mode=mode_value,
            from_cache=False,
            is_stale=False,
            layer="provider",
        )

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
