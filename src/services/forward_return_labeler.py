# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""CLI-invoked research-only forward-return episode labeler (Issue #1096).

Invocation is the only gate: there is no config-registry key and no scheduler.
Labels are written to the ``agent_episode_forward_returns`` sidecar. Append-only
``agent_episodes`` and resolver ``prediction_outcome`` rows are never updated.
Missing bars skip the row; prices are never fabricated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_forward_return_repo import (
    FORWARD_RETURN_BUCKETS,
    FORWARD_RETURN_HORIZONS,
    AgentForwardReturnRepository,
    validate_forward_return_horizon,
)
from src.schemas.agent_episode import AGENT_EPISODE_MAX_PAGE_SIZE, AgentEpisode
from src.schemas.prediction_actuals import ACTUALS_STATUS_OK, FIELD_RETURN
from src.storage import DatabaseManager


Window = Tuple[date, date]
WindowResolver = Callable[[AgentEpisode, str], Optional[Window]]
FetchFn = Callable[..., Any]


@dataclass(frozen=True)
class ForwardReturnLabelerSummary:
    """Deterministic counts for one CLI invocation."""

    as_of: str
    horizons: Tuple[str, ...]
    scanned: int = 0
    labeled: int = 0
    updated: int = 0
    skipped_missing_bars: int = 0
    skipped_not_due: int = 0
    skipped_incomplete: int = 0
    dry_run: bool = False
    noop: bool = True

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["horizons"] = list(self.horizons)
        return payload


@dataclass
class _MutableCounts:
    scanned: int = 0
    labeled: int = 0
    updated: int = 0
    skipped_missing_bars: int = 0
    skipped_not_due: int = 0
    skipped_incomplete: int = 0


def bucket_for_return_pct(horizon: str, return_pct: float) -> str:
    """Map a finite close-to-close percent return onto an allowlisted bucket."""
    canonical_horizon = validate_forward_return_horizon(horizon)
    if isinstance(return_pct, bool):
        raise ValueError("return_pct must be a finite number")
    value = float(return_pct)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("return_pct must be finite")
    if value > 0:
        direction = "up"
    elif value < 0:
        direction = "down"
    else:
        direction = "flat"
    bucket = f"{canonical_horizon}_{direction}"
    if bucket not in FORWARD_RETURN_BUCKETS:
        raise ValueError(f"unsupported forward_return_bucket: {bucket!r}")
    return bucket


def _as_utc_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).date()
        return value.astimezone(timezone.utc).date()
    if isinstance(value, date):
        return value
    return None


def _parse_as_of(value: Any) -> date:
    if isinstance(value, datetime):
        return _as_utc_date(value) or value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        raise ValueError("as_of is required")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("as_of must be YYYY-MM-DD") from exc


def _normalize_horizons(horizons: Optional[Sequence[str]]) -> Tuple[str, ...]:
    if horizons is None:
        items = ("1d",)
    else:
        items = tuple(validate_forward_return_horizon(item) for item in horizons)
    if not items:
        items = ("1d",)
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    unknown = [item for item in seen if item not in FORWARD_RETURN_HORIZONS]
    if unknown:
        raise ValueError(f"unsupported forward-return horizon: {unknown[0]!r}")
    return tuple(seen)


def default_resolve_window(episode: AgentEpisode, horizon: str) -> Optional[Window]:
    """Reuse the prediction trading-session helper. Never approximate calendar days."""
    stamp = episode.completed_at or episode.started_at or episode.created_at
    symbol = str(episode.symbol or "").strip()
    market = str(episode.market or "").strip().lower()
    if stamp is None or not symbol or not market:
        return None
    from src.core.prediction_resolve_after import (  # local import: calendar is optional at test inject
        ResolveAfterError,
        compute_resolve_after,
    )

    try:
        result = compute_resolve_after(
            market,
            stamp,
            horizon,
            stock_code=symbol,
        )
    except (ResolveAfterError, TypeError, ValueError):
        return None
    if result.calendar_approx:
        return None
    anchor = result.anchor_session
    target = result.target_session
    if not isinstance(anchor, date) or not isinstance(target, date):
        return None
    if target < anchor:
        return None
    return anchor, target


class ForwardReturnLabeler:
    """Batch-label eligible episodes through ActualsFetcher. Invocation is the gate."""

    def __init__(
        self,
        *,
        db_manager: Optional[DatabaseManager] = None,
        episode_repo: Optional[AgentEpisodeRepository] = None,
        label_repo: Optional[AgentForwardReturnRepository] = None,
        fetcher: Any = None,
        fetch_fn: Optional[FetchFn] = None,
        resolve_window: Optional[WindowResolver] = None,
        fetcher_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._db = db_manager
        self._episode_repo = episode_repo
        self._label_repo = label_repo
        self._fetcher = fetcher
        self._fetch_fn = fetch_fn
        self._resolve_window = resolve_window or default_resolve_window
        self._fetcher_factory = fetcher_factory

    def _episodes(self) -> AgentEpisodeRepository:
        if self._episode_repo is None:
            self._episode_repo = AgentEpisodeRepository(self._db)
        return self._episode_repo

    def _labels(self) -> AgentForwardReturnRepository:
        if self._label_repo is None:
            self._label_repo = AgentForwardReturnRepository(self._db)
        return self._label_repo

    def _fetch(self, **kwargs: Any) -> Any:
        if self._fetch_fn is not None:
            return self._fetch_fn(**kwargs)
        if self._fetcher is None:
            if self._fetcher_factory is not None:
                self._fetcher = self._fetcher_factory()
            else:
                from src.services.actuals_fetcher import ActualsFetcher

                self._fetcher = ActualsFetcher()
        return self._fetcher.fetch(**kwargs)

    def label(
        self,
        *,
        as_of: Any,
        horizons: Optional[Sequence[str]] = None,
        run_id: Optional[str] = None,
        limit: int = AGENT_EPISODE_MAX_PAGE_SIZE,
        dry_run: bool = False,
    ) -> ForwardReturnLabelerSummary:
        as_of_date = _parse_as_of(as_of)
        canonical_horizons = _normalize_horizons(horizons)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        bound = min(limit, AGENT_EPISODE_MAX_PAGE_SIZE)
        episodes = self._load_episodes(run_id=run_id, limit=bound)
        counts = _MutableCounts()
        if not episodes:
            return ForwardReturnLabelerSummary(
                as_of=as_of_date.isoformat(),
                horizons=canonical_horizons,
                dry_run=dry_run,
                noop=True,
            )
        for episode in episodes:
            counts.scanned += 1
            self._label_episode(
                episode,
                as_of=as_of_date,
                horizons=canonical_horizons,
                dry_run=dry_run,
                counts=counts,
            )
        return ForwardReturnLabelerSummary(
            as_of=as_of_date.isoformat(),
            horizons=canonical_horizons,
            scanned=counts.scanned,
            labeled=counts.labeled,
            updated=counts.updated,
            skipped_missing_bars=counts.skipped_missing_bars,
            skipped_not_due=counts.skipped_not_due,
            skipped_incomplete=counts.skipped_incomplete,
            dry_run=dry_run,
            noop=counts.labeled == 0 and counts.updated == 0,
        )

    def _load_episodes(
        self,
        *,
        run_id: Optional[str],
        limit: int,
    ) -> List[AgentEpisode]:
        repo = self._episodes()
        key = str(run_id or "").strip()
        if key:
            return repo.get_by_run_id(key, limit=limit)
        page = repo.query(offset=0, limit=limit)
        return list(page.items)

    def _label_episode(
        self,
        episode: AgentEpisode,
        *,
        as_of: date,
        horizons: Sequence[str],
        dry_run: bool,
        counts: _MutableCounts,
    ) -> None:
        symbol = str(episode.symbol or "").strip()
        market = str(episode.market or "").strip().lower() or None
        if not symbol:
            counts.skipped_incomplete += 1
            return
        for horizon in horizons:
            window = self._resolve_window(episode, horizon)
            if window is None:
                counts.skipped_incomplete += 1
                continue
            anchor, target = window
            if target > as_of:
                counts.skipped_not_due += 1
                continue
            snapshot = self._fetch(
                symbol=symbol,
                market=market,
                as_of=anchor,
                end=target,
                field_set=(FIELD_RETURN,),
            )
            if not self._scoreable_snapshot(snapshot):
                counts.skipped_missing_bars += 1
                continue
            try:
                bucket = bucket_for_return_pct(horizon, float(snapshot.return_pct))
            except (TypeError, ValueError):
                counts.skipped_missing_bars += 1
                continue
            existing = self._labels().get_by_episode_horizon(episode.episode_id, horizon)
            if existing is not None and existing.forward_return_bucket == bucket:
                continue
            if dry_run:
                if existing is None:
                    counts.labeled += 1
                else:
                    counts.updated += 1
                continue
            self._labels().upsert(
                episode_id=episode.episode_id,
                run_id=episode.run_id,
                horizon=horizon,
                forward_return_bucket=bucket,
            )
            if existing is None:
                counts.labeled += 1
            else:
                counts.updated += 1

    @staticmethod
    def _scoreable_snapshot(snapshot: Any) -> bool:
        if snapshot is None:
            return False
        status = getattr(snapshot, "status", None)
        ok = getattr(snapshot, "ok", None)
        if ok is False or (status is not None and status != ACTUALS_STATUS_OK):
            return False
        return_pct = getattr(snapshot, "return_pct", None)
        if return_pct is None or isinstance(return_pct, bool):
            return False
        try:
            value = float(return_pct)
        except (TypeError, ValueError):
            return False
        if value != value or value in (float("inf"), float("-inf")):
            return False
        as_of_bar = getattr(snapshot, "as_of_bar", None)
        end_bar = getattr(snapshot, "end_bar", None)
        if as_of_bar is None or end_bar is None:
            return False
        return True
