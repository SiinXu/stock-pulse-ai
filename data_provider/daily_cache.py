"""Range-aware local-first storage for normalized daily provider data.

The manager owns orchestration through :meth:`DailyDataCache.resolve`: ``auto``
uses a fresh local range before the provider chain and may use an eligible
stale range after total provider failure, ``local_only`` never enters the
provider callback, and ``refresh`` calls the provider chain once and persists
only a successful result.
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
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from io import StringIO
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

import pandas as pd

from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)


_CACHE_SCHEMA_VERSION = 2
_LEGACY_CACHE_SCHEMA_VERSION = 1
_CACHE_ENABLED_DEFAULT = True
_CACHE_DIR_DEFAULT = "data/provider_cache/daily"
_MEMORY_TTL_SECONDS_DEFAULT = 60.0
_PERSISTENT_TTL_SECONDS_DEFAULT = 3600.0
_STALE_IF_ERROR_SECONDS_DEFAULT = 86400.0
_MEMORY_MAX_ENTRIES_DEFAULT = 256
_PERSISTENT_MAX_AGE_SECONDS_DEFAULT = 90 * 86400.0
_PERSISTENT_MAX_ENTRIES_DEFAULT = 512
_LOCAL_ONLY_MAX_AGE_SECONDS_DEFAULT = 30 * 86400.0
_ROLLOVER_GRACE_DAYS_DEFAULT = 1
_MARKET_DATA_MODE_ENV = "PROVIDER_MARKET_DATA_MODE"

# Only normalized market-data columns may cross the persistence boundary.
# Adding a field requires an explicit schema review and a schema-id change if
# existing readers could interpret the value differently.
PERSISTED_DAILY_COLUMN_ALLOWLIST: Tuple[str, ...] = (
    "date",
    "code",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "pct_chg",
    "ma5",
    "ma10",
    "ma20",
    "volume_ratio",
)
REQUIRED_DAILY_COLUMNS: Tuple[str, ...] = (
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "pct_chg",
)
_REQUIRED_FIELD_GROUPS = {"daily_ohlcv": REQUIRED_DAILY_COLUMNS}
_DEFAULT_REQUIRED_FIELDS: Tuple[str, ...] = ("daily_ohlcv",)


class MarketDataFetchMode(str, Enum):
    """Manager-level daily-data fetch policy."""

    AUTO = "auto"
    LOCAL_ONLY = "local_only"
    REFRESH = "refresh"


class _IncompatibleCacheIdentity(ValueError):
    """A valid cache file owned by another adjustment/schema identity."""


def parse_market_data_fetch_mode(raw_value: Optional[str]) -> MarketDataFetchMode:
    """Parse the configured mode and fail closed on an ambiguous value."""

    if raw_value is None or not str(raw_value).strip():
        return MarketDataFetchMode.AUTO
    normalized = str(raw_value).strip().lower().replace("-", "_")
    try:
        return MarketDataFetchMode(normalized)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in MarketDataFetchMode)
        raise ValueError(
            f"Invalid {_MARKET_DATA_MODE_ENV}={raw_value!r}; expected one of: {allowed}. "
            "Fix or unset the value before starting market-data workflows."
        ) from exc


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
    """Runtime policy for daily-data cache layers and persistent retention."""

    enabled: bool = _CACHE_ENABLED_DEFAULT
    directory: Path = Path(_CACHE_DIR_DEFAULT)
    memory_ttl_seconds: float = _MEMORY_TTL_SECONDS_DEFAULT
    persistent_ttl_seconds: float = _PERSISTENT_TTL_SECONDS_DEFAULT
    stale_if_error_seconds: float = _STALE_IF_ERROR_SECONDS_DEFAULT
    memory_max_entries: int = _MEMORY_MAX_ENTRIES_DEFAULT
    fetch_mode: MarketDataFetchMode = MarketDataFetchMode.AUTO
    persistent_max_age_seconds: float = _PERSISTENT_MAX_AGE_SECONDS_DEFAULT
    persistent_max_entries: int = _PERSISTENT_MAX_ENTRIES_DEFAULT
    local_only_max_age_seconds: float = _LOCAL_ONLY_MAX_AGE_SECONDS_DEFAULT
    rollover_grace_days: int = _ROLLOVER_GRACE_DAYS_DEFAULT

    def __post_init__(self) -> None:
        if self.local_only_max_age_seconds <= 0:
            raise ValueError(
                "PROVIDER_DAILY_CACHE_LOCAL_ONLY_MAX_AGE_SECONDS must be greater than zero"
            )

    @classmethod
    def from_env(cls) -> "DailyCacheConfig":
        directory_value = os.getenv("PROVIDER_DAILY_CACHE_DIR", "").strip()
        return cls(
            enabled=_read_bool_env("PROVIDER_DAILY_CACHE_ENABLED", _CACHE_ENABLED_DEFAULT),
            directory=Path(directory_value or _CACHE_DIR_DEFAULT).expanduser(),
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
            persistent_max_age_seconds=_read_non_negative_float_env(
                "PROVIDER_DAILY_CACHE_PERSISTENT_MAX_AGE_SECONDS",
                _PERSISTENT_MAX_AGE_SECONDS_DEFAULT,
            ),
            persistent_max_entries=_read_positive_int_env(
                "PROVIDER_DAILY_CACHE_PERSISTENT_MAX_ENTRIES",
                _PERSISTENT_MAX_ENTRIES_DEFAULT,
            ),
            local_only_max_age_seconds=_read_non_negative_float_env(
                "PROVIDER_DAILY_CACHE_LOCAL_ONLY_MAX_AGE_SECONDS",
                _LOCAL_ONLY_MAX_AGE_SECONDS_DEFAULT,
            ),
            rollover_grace_days=_read_positive_int_env(
                "PROVIDER_DAILY_CACHE_ROLLOVER_GRACE_DAYS",
                _ROLLOVER_GRACE_DAYS_DEFAULT,
            ),
        )


@dataclass(frozen=True)
class DailyCacheKey:
    """Normalized request plus identities that must never be mixed."""

    symbol: str
    start_date: str
    end_date: str
    days: int
    adjustment: str = "provider_default"
    schema_id: str = "normalized_daily_v1"
    allow_end_rollover: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "days": self.days,
            "adjustment": self.adjustment,
            "schema_id": self.schema_id,
            "allow_end_rollover": self.allow_end_rollover,
        }

    def legacy_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "days": self.days,
        }

    def identity_dict(self) -> Dict[str, str]:
        return {
            "symbol": self.symbol,
            "adjustment": self.adjustment,
            "schema_id": self.schema_id,
        }

    def digest(self) -> str:
        material = json.dumps(
            self.to_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def identity_digest(self) -> str:
        material = json.dumps(
            self.identity_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def symbol_digest(self) -> str:
        return hashlib.sha256(self.symbol.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class LocalDataMissing:
    """Executable description of absent columns and date ranges."""

    symbol: str
    start_date: str
    end_date: str
    days: int
    fields: Tuple[str, ...]
    missing_ranges: Tuple[Tuple[str, str], ...]
    mode: str
    reason: str
    available_start_date: Optional[str] = None
    available_end_date: Optional[str] = None
    age_seconds: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "days": self.days,
            "fields": list(self.fields),
            "missing_ranges": [
                {"start_date": start, "end_date": end}
                for start, end in self.missing_ranges
            ],
            "mode": self.mode,
            "reason": self.reason,
            "available_start_date": self.available_start_date,
            "available_end_date": self.available_end_date,
            "age_seconds": self.age_seconds,
        }


class LocalDataMissingError(Exception):
    """Raised when the manager's local-only path cannot satisfy a request."""

    error_code = "local_market_data_missing"

    def __init__(self, missing: LocalDataMissing) -> None:
        self.missing = missing
        fields = ",".join(missing.fields) if missing.fields else "-"
        ranges = ",".join(f"{start}..{end}" for start, end in missing.missing_ranges) or "-"
        super().__init__(
            f"Local market data missing for symbol={missing.symbol} "
            f"start_date={missing.start_date or '-'} end_date={missing.end_date or '-'} "
            f"days={missing.days} fields={fields} missing_ranges={ranges} "
            f"(mode={missing.mode}, reason={missing.reason})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return self.missing.to_dict()


@dataclass(frozen=True)
class DailyCacheRead:
    key: DailyCacheKey
    frame: pd.DataFrame
    source_name: str
    layer: str
    age_seconds: float
    is_stale: bool
    stored_at: float


@dataclass(frozen=True)
class DailyCacheLookup:
    fresh: Optional[DailyCacheRead]
    stale: Optional[DailyCacheRead]
    missing: Optional[LocalDataMissing] = None


@dataclass(frozen=True)
class MarketDataResolveResult:
    frame: pd.DataFrame
    source_name: str
    mode: str
    from_cache: bool
    is_stale: bool
    layer: str
    age_seconds: float = 0.0
    provider_failure_count: int = 0


@dataclass
class _DailyCacheEntry:
    key: DailyCacheKey
    frame: pd.DataFrame
    source_name: str
    stored_at: float
    coverage_ranges: Tuple[Tuple[str, str], ...]


class DailyDataCache:
    """Bounded memory cache backed by atomic range-aware JSON tables."""

    def __init__(
        self,
        config: Optional[DailyCacheConfig] = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config or DailyCacheConfig.from_env()
        self._clock = clock
        self._lock = RLock()
        self._request_locks: Dict[str, RLock] = {}
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
            "pruned_entries": 0,
            "schema_v1_reads": 0,
        }

    @classmethod
    def from_env(cls) -> "DailyDataCache":
        return cls(DailyCacheConfig.from_env())

    @property
    def fetch_mode(self) -> MarketDataFetchMode:
        return self.config.fetch_mode

    @contextmanager
    def request_guard(self, key: DailyCacheKey) -> Iterator[None]:
        """Serialize one identity's lookup/fetch/store cycle within a manager."""

        digest = key.identity_digest()
        with self._lock:
            guard = self._request_locks.setdefault(digest, RLock())
        with guard:
            yield

    @staticmethod
    def _age_seconds(now: float, stored_at: float) -> float:
        return max(0.0, now - stored_at)

    def _is_stale_eligible(self, age_seconds: float) -> bool:
        if self.config.stale_if_error_seconds <= 0:
            return False
        maximum_age = self.config.persistent_ttl_seconds + self.config.stale_if_error_seconds
        return self.config.persistent_ttl_seconds < age_seconds <= maximum_age

    @staticmethod
    def _parse_date(value: str) -> datetime:
        return datetime.strptime(value, "%Y-%m-%d")

    @classmethod
    def _normalize_ranges(
        cls, ranges: Sequence[Tuple[str, str]]
    ) -> Tuple[Tuple[str, str], ...]:
        parsed: List[Tuple[datetime, datetime]] = []
        for start, end in ranges:
            start_dt = cls._parse_date(str(start))
            end_dt = cls._parse_date(str(end))
            if start_dt > end_dt:
                raise ValueError("cache coverage start is after end")
            parsed.append((start_dt, end_dt))
        parsed.sort(key=lambda item: (item[0], item[1]))
        merged: List[Tuple[datetime, datetime]] = []
        for start_dt, end_dt in parsed:
            if merged and start_dt <= merged[-1][1] + timedelta(days=1):
                merged[-1] = (merged[-1][0], max(merged[-1][1], end_dt))
            else:
                merged.append((start_dt, end_dt))
        return tuple(
            (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            for start, end in merged
        )

    @classmethod
    def _missing_ranges(
        cls,
        key: DailyCacheKey,
        coverage_ranges: Sequence[Tuple[str, str]],
        *,
        rollover_grace_days: int,
    ) -> Tuple[Tuple[str, str], ...]:
        request_start = cls._parse_date(key.start_date)
        request_end = cls._parse_date(key.end_date)
        cursor = request_start
        missing: List[Tuple[str, str]] = []
        normalized = cls._normalize_ranges(coverage_ranges)
        for index, (raw_start, raw_end) in enumerate(normalized):
            start = cls._parse_date(raw_start)
            end = cls._parse_date(raw_end)
            if index == len(normalized) - 1 and key.allow_end_rollover:
                end += timedelta(days=rollover_grace_days)
            if end < cursor or start > request_end:
                continue
            if start > cursor:
                missing_end = min(request_end, start - timedelta(days=1))
                missing.append(
                    (cursor.strftime("%Y-%m-%d"), missing_end.strftime("%Y-%m-%d"))
                )
            cursor = max(cursor, end + timedelta(days=1))
            if cursor > request_end:
                break
        if cursor <= request_end:
            missing.append(
                (cursor.strftime("%Y-%m-%d"), request_end.strftime("%Y-%m-%d"))
            )
        return tuple(missing)

    @staticmethod
    def _expanded_required_fields(fields: Sequence[str]) -> Tuple[str, ...]:
        expanded: List[str] = []
        for raw_field in fields:
            field = str(raw_field).strip()
            if not field:
                continue
            for column in _REQUIRED_FIELD_GROUPS.get(field, (field,)):
                if column not in expanded:
                    expanded.append(column)
        return tuple(expanded or REQUIRED_DAILY_COLUMNS)

    @staticmethod
    def _sanitize_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise ValueError("empty daily market-data frame")
        allowed = [column for column in frame.columns if str(column) in PERSISTED_DAILY_COLUMN_ALLOWLIST]
        sanitized = frame.loc[:, allowed].copy(deep=True)
        if "date" not in sanitized.columns:
            raise ValueError("daily market-data frame is missing date")
        sanitized["date"] = pd.to_datetime(sanitized["date"], errors="coerce")
        sanitized = sanitized.dropna(subset=["date"])
        if sanitized.empty:
            raise ValueError("daily market-data frame has no valid dates")
        sanitized = (
            sanitized.sort_values("date", kind="mergesort")
            .drop_duplicates(subset=["date"], keep="last")
            .reset_index(drop=True)
        )
        return sanitized

    @classmethod
    def _missing_required_fields(
        cls,
        frame: pd.DataFrame,
        required_fields: Sequence[str],
    ) -> Tuple[str, ...]:
        expanded = cls._expanded_required_fields(required_fields)
        return tuple(field for field in expanded if field not in frame.columns)

    @staticmethod
    def _slice_frame(frame: pd.DataFrame, key: DailyCacheKey) -> pd.DataFrame:
        dates = pd.to_datetime(frame["date"], errors="coerce")
        start = pd.Timestamp(key.start_date)
        end = pd.Timestamp(key.end_date)
        sliced = frame.loc[(dates >= start) & (dates <= end)].copy(deep=True)
        return (
            sliced.sort_values("date", kind="mergesort")
            .drop_duplicates(subset=["date"], keep="last")
            .reset_index(drop=True)
        )

    @staticmethod
    def _annotated_copy(
        entry: _DailyCacheEntry,
        frame: pd.DataFrame,
        *,
        cache_hit: bool,
        layer: str,
        age_seconds: float,
        is_stale: bool,
        fetch_mode: Optional[str] = None,
    ) -> pd.DataFrame:
        result = frame.copy(deep=True)
        meta: Dict[str, Any] = {
            "cache_hit": cache_hit,
            "layer": layer,
            "is_stale": is_stale,
            "stale_seconds": int(age_seconds),
            "stored_at": datetime.fromtimestamp(entry.stored_at, tz=timezone.utc).isoformat(),
            "source": entry.source_name,
        }
        if fetch_mode is not None:
            meta["fetch_mode"] = fetch_mode
        result.attrs["provider_cache"] = meta
        return result

    def _cache_path(self, key: DailyCacheKey) -> Path:
        filename = f"{key.symbol_digest()}-{key.identity_digest()}.json"
        return self.config.directory / filename

    def _candidate_paths(self, key: DailyCacheKey) -> List[Path]:
        if not self.config.directory.is_dir():
            return []
        return sorted(self.config.directory.glob(f"{key.symbol_digest()}-*.json"))

    def _entry_from_v2_payload(
        self, payload: Dict[str, Any], key: DailyCacheKey
    ) -> _DailyCacheEntry:
        identity = payload.get("identity")
        if identity != key.identity_dict():
            raise _IncompatibleCacheIdentity("cache identity mismatch")
        stored_at = float(payload["stored_at"])
        if not math.isfinite(stored_at) or stored_at < 0:
            raise ValueError("invalid cache timestamp")
        source_name = payload["source_name"]
        if not isinstance(source_name, str) or not source_name:
            raise ValueError("invalid cache source")
        persisted_allowlist = payload.get("column_allowlist")
        if persisted_allowlist != list(PERSISTED_DAILY_COLUMN_ALLOWLIST):
            raise ValueError("cache column allowlist mismatch")
        columns = payload.get("columns")
        records = payload.get("records")
        if not isinstance(columns, list) or not isinstance(records, list):
            raise TypeError("invalid cache records")
        if any(column not in PERSISTED_DAILY_COLUMN_ALLOWLIST for column in columns):
            raise ValueError("cache contains a non-allowlisted column")
        frame = pd.DataFrame.from_records(records, columns=columns)
        frame = self._sanitize_frame(frame)
        coverage_payload = payload.get("coverage_ranges")
        if not isinstance(coverage_payload, list):
            raise TypeError("invalid cache coverage")
        coverage_ranges = self._normalize_ranges(
            [(str(item["start_date"]), str(item["end_date"])) for item in coverage_payload]
        )
        return _DailyCacheEntry(
            key=key,
            frame=frame,
            source_name=source_name,
            stored_at=stored_at,
            coverage_ranges=coverage_ranges,
        )

    def _entry_from_v1_payload(
        self, payload: Dict[str, Any], key: DailyCacheKey
    ) -> _DailyCacheEntry:
        if (
            key.adjustment != "provider_default"
            or key.schema_id != "normalized_daily_v1"
        ):
            raise _IncompatibleCacheIdentity(
                "legacy cache has no compatible adjustment/schema identity"
            )
        legacy_key = payload.get("key")
        if not isinstance(legacy_key, dict) or legacy_key.get("symbol") != key.symbol:
            raise ValueError("legacy cache symbol mismatch")
        stored_at = float(payload["stored_at"])
        source_name = payload["source_name"]
        frame_payload = payload["dataframe"]
        if not math.isfinite(stored_at) or stored_at < 0:
            raise ValueError("invalid legacy cache timestamp")
        if not isinstance(source_name, str) or not source_name:
            raise ValueError("invalid legacy cache source")
        if not isinstance(frame_payload, str):
            raise TypeError("invalid legacy cache frame")
        frame = self._sanitize_frame(pd.read_json(StringIO(frame_payload), orient="table"))
        coverage_ranges = self._normalize_ranges(
            [(str(legacy_key["start_date"]), str(legacy_key["end_date"]))]
        )
        self._stats["schema_v1_reads"] += 1
        return _DailyCacheEntry(
            key=key,
            frame=frame,
            source_name=source_name,
            stored_at=stored_at,
            coverage_ranges=coverage_ranges,
        )

    def _read_path(self, path: Path, key: DailyCacheKey) -> Optional[_DailyCacheEntry]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            schema_version = payload.get("schema_version")
            if schema_version == _CACHE_SCHEMA_VERSION:
                return self._entry_from_v2_payload(payload, key)
            if schema_version == _LEGACY_CACHE_SCHEMA_VERSION:
                return self._entry_from_v1_payload(payload, key)
            raise ValueError("unsupported cache schema")
        except _IncompatibleCacheIdentity:
            # Candidate discovery is symbol-wide so schema-v1 exact-request
            # entries can migrate into the range table. A valid schema-v2 file
            # for another adjustment/schema identity must be left untouched.
            return None
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "provider_cache event=read_error data_type=daily_data cache_file=%s error_type=%s",
                path.name[:40],
                type(exc).__name__,
            )
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("provider_cache event=cleanup_error data_type=daily_data")
            return None

    def _read_persistent(self, key: DailyCacheKey) -> Optional[_DailyCacheEntry]:
        entries_with_names = [
            (entry, path.name)
            for path in self._candidate_paths(key)
            for entry in [self._read_path(path, key)]
            if entry is not None
        ]
        if not entries_with_names:
            return None
        newest, _newest_name = max(
            entries_with_names,
            key=lambda item: (item[0].stored_at, item[1]),
        )
        # Concatenate oldest to newest so deterministic keep-last
        # deduplication always preserves the newest stored observation. Filename
        # order is only a stable tie-breaker, never a freshness proxy.
        compatible = [
            entry
            for entry, _path_name in sorted(
                entries_with_names,
                key=lambda item: (item[0].stored_at, item[1]),
            )
            if entry.source_name == newest.source_name
        ]
        frames = [entry.frame for entry in compatible]
        ranges = [item for entry in compatible for item in entry.coverage_ranges]
        return _DailyCacheEntry(
            key=key,
            frame=self._sanitize_frame(pd.concat(frames, ignore_index=True)),
            source_name=newest.source_name,
            stored_at=newest.stored_at,
            coverage_ranges=self._normalize_ranges(ranges),
        )

    def _write_persistent(self, entry: _DailyCacheEntry) -> bool:
        temp_path: Optional[Path] = None
        try:
            self.config.directory.mkdir(parents=True, exist_ok=True)
            frame = self._sanitize_frame(entry.frame)
            records = json.loads(
                frame.to_json(orient="records", date_format="iso", date_unit="ms")
            )
            payload = {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "identity": entry.key.identity_dict(),
                "source_name": entry.source_name,
                "stored_at": entry.stored_at,
                "coverage_ranges": [
                    {"start_date": start, "end_date": end}
                    for start, end in entry.coverage_ranges
                ],
                "column_allowlist": list(PERSISTED_DAILY_COLUMN_ALLOWLIST),
                "columns": list(frame.columns),
                "records": records,
            }
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.config.directory,
                prefix=f".{entry.key.identity_digest()[:12]}-",
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
                "provider_cache event=write_error data_type=daily_data cache_key=%s error_type=%s",
                entry.key.identity_digest()[:12],
                type(exc).__name__,
            )
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return False

    def _prune_persistent(self, now: float) -> int:
        if not self.config.directory.is_dir():
            return 0
        candidates: List[Tuple[float, str, Path]] = []
        for path in sorted(self.config.directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                stored_at = float(payload["stored_at"])
                if not math.isfinite(stored_at) or stored_at < 0:
                    raise ValueError("invalid timestamp")
                candidates.append((stored_at, path.name, path))
            except (OSError, UnicodeError, ValueError, KeyError, TypeError):
                candidates.append((-1.0, path.name, path))
        removals = {
            path
            for stored_at, _name, path in candidates
            if self.config.persistent_max_age_seconds > 0
            and now - stored_at > self.config.persistent_max_age_seconds
        }
        retained = [item for item in candidates if item[2] not in removals]
        overflow = max(0, len(retained) - self.config.persistent_max_entries)
        removals.update(path for _stored_at, _name, path in sorted(retained)[:overflow])
        removed = 0
        for path in sorted(removals, key=lambda item: item.name):
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                logger.warning("provider_cache event=prune_error data_type=daily_data")
        self._stats["pruned_entries"] += removed
        return removed

    def _remember(self, entry: _DailyCacheEntry) -> None:
        digest = entry.key.identity_digest()
        self._memory[digest] = _DailyCacheEntry(
            key=entry.key,
            frame=entry.frame.copy(deep=True),
            source_name=entry.source_name,
            stored_at=entry.stored_at,
            coverage_ranges=entry.coverage_ranges,
        )
        self._memory.move_to_end(digest)
        while len(self._memory) > self.config.memory_max_entries:
            self._memory.popitem(last=False)

    def _newest_entry(self, key: DailyCacheKey) -> Tuple[Optional[_DailyCacheEntry], str]:
        digest = key.identity_digest()
        memory_entry = self._memory.get(digest)
        persistent_entry = self._read_persistent(key)
        if memory_entry is None and persistent_entry is None:
            return None, "none"
        if persistent_entry is None or (
            memory_entry is not None and memory_entry.stored_at >= persistent_entry.stored_at
        ):
            return memory_entry, "memory"
        self._remember(persistent_entry)
        return persistent_entry, "persistent"

    def _build_missing(
        self,
        key: DailyCacheKey,
        *,
        missing_fields: Sequence[str],
        missing_ranges: Sequence[Tuple[str, str]],
        reason: str,
        entry: Optional[_DailyCacheEntry] = None,
        age_seconds: Optional[float] = None,
    ) -> LocalDataMissing:
        available_start = None
        available_end = None
        if entry is not None and entry.coverage_ranges:
            available_start = entry.coverage_ranges[0][0]
            available_end = entry.coverage_ranges[-1][1]
        return LocalDataMissing(
            symbol=key.symbol,
            start_date=key.start_date,
            end_date=key.end_date,
            days=key.days,
            fields=tuple(missing_fields),
            missing_ranges=tuple(missing_ranges),
            mode=MarketDataFetchMode.LOCAL_ONLY.value,
            reason=reason,
            available_start_date=available_start,
            available_end_date=available_end,
            age_seconds=None if age_seconds is None else int(age_seconds),
        )

    def _inspect_entry(
        self,
        key: DailyCacheKey,
        entry: _DailyCacheEntry,
        *,
        required_fields: Sequence[str],
        layer: str,
        now: float,
        fetch_mode: Optional[str] = None,
        fresh_ttl_seconds: Optional[float] = None,
    ) -> Tuple[Optional[DailyCacheRead], LocalDataMissing]:
        expanded_fields = self._expanded_required_fields(required_fields)
        missing_fields = tuple(field for field in expanded_fields if field not in entry.frame.columns)
        missing_ranges = self._missing_ranges(
            key,
            entry.coverage_ranges,
            rollover_grace_days=self.config.rollover_grace_days,
        )
        age_seconds = self._age_seconds(now, entry.stored_at)
        reason = (
            "missing_fields_and_ranges"
            if missing_fields and missing_ranges
            else "missing_fields"
            if missing_fields
            else "missing_ranges"
            if missing_ranges
            else "complete"
        )
        missing = self._build_missing(
            key,
            missing_fields=missing_fields,
            missing_ranges=missing_ranges,
            reason=reason,
            entry=entry,
            age_seconds=age_seconds,
        )
        if missing_fields or missing_ranges:
            return None, missing
        sliced = self._slice_frame(entry.frame, key)
        if sliced.empty:
            missing = self._build_missing(
                key,
                missing_fields=(),
                missing_ranges=((key.start_date, key.end_date),),
                reason="no_rows_in_covered_window",
                entry=entry,
                age_seconds=age_seconds,
            )
            return None, missing
        effective_fresh_ttl = (
            self.config.persistent_ttl_seconds
            if fresh_ttl_seconds is None
            else fresh_ttl_seconds
        )
        is_stale = effective_fresh_ttl <= 0 or age_seconds > effective_fresh_ttl
        return (
            DailyCacheRead(
                key=key,
                frame=self._annotated_copy(
                    entry,
                    sliced,
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
            ),
            missing,
        )

    def _record_event(self, event: str, layer: str) -> None:
        logger.info(
            "provider_cache event=%s data_type=daily_data layer=%s hits=%d misses=%d "
            "stale_hits=%d writes=%d local_only_hits=%d local_only_misses=%d",
            event,
            layer,
            self._stats["hits"],
            self._stats["misses"],
            self._stats["stale_hits"],
            self._stats["writes"],
            self._stats["local_only_hits"],
            self._stats["local_only_misses"],
        )

    def lookup(
        self,
        key: DailyCacheKey,
        *,
        required_fields: Sequence[str] = _DEFAULT_REQUIRED_FIELDS,
    ) -> DailyCacheLookup:
        """Return a complete fresh range and an eligible complete stale range."""

        if not self.config.enabled:
            missing = self._build_missing(
                key,
                missing_fields=self._expanded_required_fields(required_fields),
                missing_ranges=((key.start_date, key.end_date),),
                reason="cache_disabled",
            )
            return DailyCacheLookup(fresh=None, stale=None, missing=missing)
        now = self._clock()
        with self._lock:
            self._prune_persistent(now)
            memory_entry = self._memory.get(key.identity_digest())
            persistent_entry = self._read_persistent(key)
            if memory_entry is None and persistent_entry is None:
                missing = self._build_missing(
                    key,
                    missing_fields=self._expanded_required_fields(required_fields),
                    missing_ranges=((key.start_date, key.end_date),),
                    reason="no_local_entry",
                )
                self._stats["misses"] += 1
                self._record_event("miss", "none")
                return DailyCacheLookup(fresh=None, stale=None, missing=missing)

            inspected: List[Tuple[_DailyCacheEntry, str, Optional[DailyCacheRead], LocalDataMissing]] = []
            if memory_entry is not None:
                memory_read, memory_missing = self._inspect_entry(
                    key,
                    memory_entry,
                    required_fields=required_fields,
                    layer="memory",
                    now=now,
                    fresh_ttl_seconds=self.config.memory_ttl_seconds,
                )
                inspected.append(
                    (memory_entry, "memory", memory_read, memory_missing)
                )
                if (
                    memory_read is not None
                    and self.config.memory_ttl_seconds > 0
                    and memory_read.age_seconds <= self.config.memory_ttl_seconds
                ):
                    self._memory.move_to_end(key.identity_digest())
                    self._stats["hits"] += 1
                    self._record_event("hit", "memory")
                    return DailyCacheLookup(
                        fresh=memory_read,
                        stale=None,
                        missing=None,
                    )

            if persistent_entry is not None:
                persistent_read, persistent_missing = self._inspect_entry(
                    key,
                    persistent_entry,
                    required_fields=required_fields,
                    layer="persistent",
                    now=now,
                    fresh_ttl_seconds=self.config.persistent_ttl_seconds,
                )
                inspected.append(
                    (
                        persistent_entry,
                        "persistent",
                        persistent_read,
                        persistent_missing,
                    )
                )
                if (
                    persistent_read is not None
                    and self.config.persistent_ttl_seconds > 0
                    and persistent_read.age_seconds
                    <= self.config.persistent_ttl_seconds
                ):
                    self._remember(persistent_entry)
                    self._stats["hits"] += 1
                    self._record_event("hit", "persistent")
                    return DailyCacheLookup(
                        fresh=persistent_read,
                        stale=None,
                        missing=None,
                    )

            self._stats["misses"] += 1
            complete_stale = [
                (entry, layer, read)
                for entry, layer, read, _missing in inspected
                if read is not None and self._is_stale_eligible(read.age_seconds)
            ]
            stale = None
            if complete_stale:
                _entry, layer, stale = max(
                    complete_stale,
                    key=lambda item: item[0].stored_at,
                )
                self._record_event("miss", layer)
            else:
                self._record_event("incomplete", "none")
            newest = max(inspected, key=lambda item: item[0].stored_at)
            return DailyCacheLookup(
                fresh=None,
                stale=stale,
                missing=newest[3],
            )

    def _lookup_local_complete(
        self,
        key: DailyCacheKey,
        *,
        required_fields: Sequence[str] = _DEFAULT_REQUIRED_FIELDS,
    ) -> Tuple[Optional[DailyCacheRead], LocalDataMissing]:
        """Inspect one local candidate under the explicit offline age policy."""

        if not self.config.enabled:
            return (
                None,
                self.build_local_missing(
                    key,
                    fields=required_fields,
                    reason="cache_disabled",
                ),
            )
        now = self._clock()
        with self._lock:
            self._prune_persistent(now)
            entry, layer = self._newest_entry(key)
            if entry is None:
                return (
                    None,
                    self.build_local_missing(key, fields=required_fields),
                )
            read, missing = self._inspect_entry(
                key,
                entry,
                required_fields=required_fields,
                layer=layer,
                now=now,
                fetch_mode=MarketDataFetchMode.LOCAL_ONLY.value,
            )
            if read is None:
                return None, missing
            if (
                self.config.local_only_max_age_seconds > 0
                and read.age_seconds > self.config.local_only_max_age_seconds
            ):
                return (
                    None,
                    self._build_missing(
                        key,
                        missing_fields=(),
                        missing_ranges=(),
                        reason="local_entry_too_old",
                        entry=entry,
                        age_seconds=read.age_seconds,
                    ),
                )
            return read, missing

    def lookup_local_store(
        self,
        key: DailyCacheKey,
        *,
        required_fields: Sequence[str] = _DEFAULT_REQUIRED_FIELDS,
    ) -> Optional[DailyCacheRead]:
        """Return a complete local range within the explicit offline max age."""

        read, _missing = self._lookup_local_complete(
            key,
            required_fields=required_fields,
        )
        return read

    def store(self, key: DailyCacheKey, frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
        """Allowlist, merge compatible ranges, and atomically persist success."""

        if not isinstance(source_name, str) or not source_name.strip():
            raise ValueError("daily market-data source name must be non-empty")
        stored_at = self._clock()
        sanitized = self._sanitize_frame(frame)
        requested_range = self._normalize_ranges(((key.start_date, key.end_date),))
        entry = _DailyCacheEntry(
            key=key,
            frame=sanitized,
            source_name=source_name,
            stored_at=stored_at,
            coverage_ranges=requested_range,
        )
        if self.config.enabled:
            with self._lock:
                existing = self._read_persistent(key)
                if existing is None:
                    existing = self._memory.get(key.identity_digest())
                if existing is not None and existing.source_name == source_name:
                    entry = _DailyCacheEntry(
                        key=key,
                        frame=self._sanitize_frame(
                            pd.concat([existing.frame, sanitized], ignore_index=True)
                        ),
                        source_name=source_name,
                        stored_at=stored_at,
                        coverage_ranges=self._normalize_ranges(
                            (*existing.coverage_ranges, *requested_range)
                        ),
                    )
                self._remember(entry)
                if self._write_persistent(entry):
                    self._stats["writes"] += 1
                self._prune_persistent(stored_at)
                self._record_event("write", "memory_persistent")
        return self._annotated_copy(
            entry,
            sanitized,
            cache_hit=False,
            layer="provider",
            age_seconds=0.0,
            is_stale=False,
            fetch_mode=self.config.fetch_mode.value,
        )

    def use_stale(self, read: DailyCacheRead) -> Optional[DailyCacheRead]:
        """Revalidate stale eligibility after the provider chain finishes failing."""

        with self._lock:
            age_seconds = self._age_seconds(self._clock(), read.stored_at)
            if not self._is_stale_eligible(age_seconds):
                self._record_event("stale_expired", read.layer)
                return None
            frame = read.frame.copy(deep=True)
            metadata = dict(frame.attrs.get("provider_cache") or {})
            metadata.update({"is_stale": True, "stale_seconds": int(age_seconds)})
            frame.attrs["provider_cache"] = metadata
            self._stats["stale_hits"] += 1
            self._record_event("stale_hit", read.layer)
            return DailyCacheRead(
                key=read.key,
                frame=frame,
                source_name=read.source_name,
                layer=read.layer,
                age_seconds=age_seconds,
                is_stale=True,
                stored_at=read.stored_at,
            )

    def build_local_missing(
        self,
        key: DailyCacheKey,
        *,
        fields: Sequence[str] = _DEFAULT_REQUIRED_FIELDS,
        reason: str = "no_local_entry",
    ) -> LocalDataMissing:
        return self._build_missing(
            key,
            missing_fields=self._expanded_required_fields(fields),
            missing_ranges=((key.start_date, key.end_date),),
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
        """Resolve the complete daily-data contract for all three manager modes."""

        active_mode = mode or self.config.fetch_mode
        mode_value = active_mode.value
        with self.request_guard(key):
            if active_mode is MarketDataFetchMode.LOCAL_ONLY:
                local, missing = self._lookup_local_complete(
                    key,
                    required_fields=required_fields,
                )
                if local is None:
                    with self._lock:
                        self._stats["local_only_misses"] += 1
                        self._record_event("local_only_miss", missing.reason)
                    raise LocalDataMissingError(missing)
                with self._lock:
                    self._stats["local_only_hits"] += 1
                    self._stats["hits"] += 1
                    self._record_event("local_only_hit", local.layer)
                return MarketDataResolveResult(
                    frame=local.frame,
                    source_name=local.source_name,
                    mode=mode_value,
                    from_cache=True,
                    is_stale=local.is_stale,
                    layer=local.layer,
                    age_seconds=local.age_seconds,
                )

            if network_fetch is None:
                raise ValueError(
                    f"network_fetch is required when {_MARKET_DATA_MODE_ENV}={mode_value}"
                )

            lookup = DailyCacheLookup(fresh=None, stale=None)
            if active_mode is MarketDataFetchMode.AUTO:
                lookup = self.lookup(key, required_fields=required_fields)
                if lookup.fresh is not None:
                    fresh = lookup.fresh
                    return MarketDataResolveResult(
                        frame=fresh.frame,
                        source_name=fresh.source_name,
                        mode=mode_value,
                        from_cache=True,
                        is_stale=False,
                        layer=fresh.layer,
                        age_seconds=fresh.age_seconds,
                    )

            try:
                frame, source_name = network_fetch()
                sanitized = self._sanitize_frame(frame)
                missing_fields = self._missing_required_fields(
                    sanitized,
                    required_fields,
                )
                if missing_fields:
                    raise ValueError(
                        "network_fetch returned daily data without required fields: "
                        + ",".join(missing_fields)
                    )
            except Exception as exc:  # broad-exception: fallback_recorded - total provider failure is re-raised unless an eligible stale range is recorded and returned
                log_safe_exception(
                    logger,
                    "Daily provider chain failed",
                    exc,
                    error_code="daily_provider_chain_failed",
                    level=logging.INFO,
                    context={"mode": mode_value},
                )
                provider_failure_count = int(
                    getattr(exc, "provider_failure_count", 0)
                )
                if active_mode is MarketDataFetchMode.AUTO and lookup.stale is not None:
                    stale = self.use_stale(lookup.stale)
                    if stale is not None:
                        return MarketDataResolveResult(
                            frame=stale.frame,
                            source_name=stale.source_name,
                            mode=mode_value,
                            from_cache=True,
                            is_stale=True,
                            layer=stale.layer,
                            age_seconds=stale.age_seconds,
                            provider_failure_count=provider_failure_count,
                        )
                raise

            annotated = self.store(key, sanitized, source_name)
            if active_mode is MarketDataFetchMode.REFRESH:
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

    def invalidate(self, symbol: Optional[str] = None) -> int:
        """Remove both cache layers, optionally for one normalized symbol."""

        removed = 0
        with self._lock:
            for digest, entry in list(self._memory.items()):
                if symbol is None or entry.key.symbol == symbol:
                    self._memory.pop(digest, None)
                    removed += 1
            if self.config.directory.is_dir():
                pattern = "*.json"
                if symbol is not None:
                    prefix = hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:16]
                    pattern = f"{prefix}-*.json"
                for path in sorted(self.config.directory.glob(pattern)):
                    try:
                        path.unlink()
                        removed += 1
                    except FileNotFoundError:
                        continue
                    except OSError as exc:
                        logger.warning(
                            "provider_cache event=invalidate_error data_type=daily_data error_type=%s",
                            type(exc).__name__,
                        )
            self._stats["invalidations"] += removed
            self._record_event("invalidate", "all" if symbol is None else "symbol")
        return removed

    def stats_snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._stats)
