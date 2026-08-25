# -*- coding: utf-8 -*-
"""Historical decision memory and reflection for new analyses (Issue #118).

This module reads past DecisionSignals that already have forward outcomes for a
stock and distills them into a compact "Historical Decision Reflection" that is
injected into the analysis prompt and rendered as a report section.

Design guardrails (Issue #118 acceptance criteria):

1. Minimum sample threshold: an aggregate hit-rate is only surfaced once its
   bucket has at least ``min_samples`` decided (hit+miss) outcomes. Individual
   past calls are facts and are always listed, but rate statistics below the
   threshold are suppressed as noise.
2. Window annotation: every reflection states the time window its statistics are
   drawn from, so a rate learned in one regime is never presented as timeless.
3. Confidence-only adjustment: the reflection carries no directional
   recommendation. It exists to calibrate confidence and add caution, never to
   flip or override the current directional decision. The structure below has no
   action/direction field by construction, and the rendered guidance says so.

Injection contract (READ-path renderer filter for #118 / PR #1270; layered
memory isolation #1017 / #250). This is **not** the #1119 write-admission
policy in ``src.schemas.memory_write_policy``:

- Only **admitted** structured outcome facts may reach the prompt. Free-form
  signal ``reason`` / user notes never enter the reflection payload.
- Every injected call retains provenance (``signal_id``).
- Prompt payload is size-capped and wrapped as untrusted data via
  ``isolate_untrusted_memory_body``.
- Global toggle ``DECISION_MEMORY_ENABLED`` (and per-request ``use_memory``)
  disables the path with zero extra work.
- Do not route this inject filter through the persist write policy. Outcome
  keys are required here and would be rejected on opinion writes.

Hit / miss / neutral classifications are the authoritative values already stored
on ``DecisionSignalOutcomeRecord`` by ``DecisionSignalOutcomeService``; this
module reuses them and never re-derives what counts as a hit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Confidence-only guardrail notice injected into the prompt. Kept as a module
# constant so tests can assert the non-override contract is always present.
_PROMPT_GUARDRAIL_ZH = (
    "以上为历史校准信息，仅用于调整本次结论的置信度与风险提示；"
    "不得据此翻转或否决你基于当前数据得出的方向判断。"
)
_PROMPT_GUARDRAIL_EN = (
    "The above is historical calibration only: use it to adjust the confidence "
    "and caution of this call, never to flip or override the directional "
    "decision you reach from current data."
)

# Quota / admission hard caps (Issue #118 + #1119 episodic size-cap contract).
_MAX_SIGNAL_SCAN = 40
_MAX_SCAN_MULTIPLIER = 8
_MAX_PATTERN_BUCKETS = 3
_MAX_LOOKBACK = 40
_MAX_MIN_AGE_DAYS = 365
_MAX_MIN_SAMPLES = 1_000
_MAX_SIGNAL_ID = (2**63) - 1
_MAX_PATTERN_SAMPLE_SIZE = 1_000_000_000
_MAX_ABS_RETURN_PCT = 1_000_000.0
_MAX_PROMPT_CHARS = 6_000
_ADMITTED_OUTCOMES = frozenset({"hit", "miss", "neutral"})
_ADMITTED_ACTIONS = frozenset(
    {"buy", "add", "hold", "reduce", "sell", "watch", "avoid", "alert"}
)
_ADMITTED_HORIZONS = frozenset({"1d", "3d", "5d", "10d"})
_SAFE_ACTION_RE_ALPHABET = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)
_SAFE_HORIZON_RE_ALPHABET = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)


@dataclass(frozen=True)
class PastSignalRecall:
    """One past signal with its authoritative forward outcome (a fact).

    Admission requires ``signal_id`` provenance and a completed outcome enum.
    Free-form reason / user notes are intentionally absent.
    """

    signal_id: int
    created_at: datetime
    action: str
    horizon: Optional[str]
    outcome: str  # "hit" | "miss" | "neutral" (authoritative, already stored)
    stock_return_pct: Optional[float]
    memorable: bool = False


@dataclass(frozen=True)
class PatternCalibrationBucket:
    """Track-record hit-rate for a kind of call (per action), above threshold."""

    action: str
    hit_rate_pct: float
    sample_size: int  # decided outcomes (hit + miss), always >= min_samples


@dataclass(frozen=True)
class DecisionReflection:
    """Compact same-stock memory plus pattern-level calibration.

    Deliberately has no action/direction field: reflection may inform confidence
    and caution, never direction (guardrail 3).

    ``source_signal_ids`` is the provenance trail for every admitted call so
    consumers can trace the reflection back to stored DecisionSignals.
    ``admitted`` is True only after ``admit_decision_memory`` has filtered the
    payload; raw builder output sets it False until admission runs.
    """

    stock_code: str
    market: str
    lookback: int
    min_samples: int
    window_start: date
    window_end: date
    same_stock_total: int
    same_stock_hits: int
    same_stock_misses: int
    same_stock_neutrals: int
    # None when decided samples are below ``min_samples`` (guardrail 1).
    same_stock_hit_rate_pct: Optional[float]
    recent_calls: Tuple[PastSignalRecall, ...] = field(default_factory=tuple)
    pattern_calibration: Tuple[PatternCalibrationBucket, ...] = field(default_factory=tuple)
    source_signal_ids: Tuple[int, ...] = field(default_factory=tuple)
    truncated: bool = False
    admitted: bool = False

    @property
    def same_stock_decided(self) -> int:
        return self.same_stock_hits + self.same_stock_misses


def _safe_token(value: Optional[str], alphabet: frozenset, *, max_len: int = 32) -> str:
    """Bound free-form-ish tokens to a safe alphabet before prompt render."""
    if value is None:
        return ""
    text_value = str(value).strip()
    if not text_value:
        return ""
    return "".join(ch for ch in text_value if ch in alphabet)[:max_len]


def _bounded_plain_int(
    value: Any,
    *,
    minimum: int,
    maximum: int,
) -> Optional[int]:
    """Return a bounded real int, rejecting bools and coercion surprises."""

    if type(value) is not int or value < minimum or value > maximum:
        return None
    return value


def _valid_window(reflection: DecisionReflection) -> Optional[Tuple[date, date]]:
    start = getattr(reflection, "window_start", None)
    end = getattr(reflection, "window_end", None)
    if type(start) is not date or type(end) is not date or start > end:
        return None
    return start, end


def admit_decision_memory(
    reflection: Optional[DecisionReflection],
    *,
    max_calls: Optional[int] = None,
) -> Optional[DecisionReflection]:
    """Admit a reflection for prompt/report injection (READ path, #118).

    This renderer filter is not the #1119 persist write policy. Episodic
    outcome summaries are size-capped and provenance-required. Free-form signal
    text never enters. Returns None when nothing admits, so callers never
    inject a non-admitted payload.
    """
    if reflection is None:
        return None

    lookback = _bounded_plain_int(
        getattr(reflection, "lookback", None),
        minimum=1,
        maximum=_MAX_LOOKBACK,
    )
    min_samples = _bounded_plain_int(
        getattr(reflection, "min_samples", None),
        minimum=1,
        maximum=_MAX_MIN_SAMPLES,
    )
    if lookback is None or min_samples is None:
        return None
    limit = min(lookback, _MAX_SIGNAL_SCAN)
    if max_calls is not None:
        requested_limit = _bounded_plain_int(
            max_calls,
            minimum=1,
            maximum=_MAX_LOOKBACK,
        )
        if requested_limit is None:
            return None
        limit = min(limit, requested_limit)

    raw_calls = getattr(reflection, "recent_calls", None)
    if not isinstance(raw_calls, (list, tuple)):
        return None

    admitted_calls: List[PastSignalRecall] = []
    seen_ids: set = set()
    for call in raw_calls:
        if len(admitted_calls) >= limit:
            break
        signal_id = getattr(call, "signal_id", None)
        if (
            type(signal_id) is not int
            or signal_id <= 0
            or signal_id > _MAX_SIGNAL_ID
        ):
            continue
        if signal_id in seen_ids:
            continue
        outcome = str(getattr(call, "outcome", "") or "")
        if outcome not in _ADMITTED_OUTCOMES:
            continue
        action = _safe_token(
            getattr(call, "action", None), _SAFE_ACTION_RE_ALPHABET
        ).lower()
        if action not in _ADMITTED_ACTIONS:
            continue
        horizon_raw = getattr(call, "horizon", None)
        horizon = _safe_token(
            horizon_raw, _SAFE_HORIZON_RE_ALPHABET
        ).lower() or None
        if horizon not in _ADMITTED_HORIZONS:
            horizon = None
        ret = getattr(call, "stock_return_pct", None)
        if ret is not None:
            try:
                ret_f = float(ret)
                if (
                    not math.isfinite(ret_f)
                    or ret_f < -100.0
                    or ret_f > _MAX_ABS_RETURN_PCT
                ):
                    ret = None
                else:
                    ret = ret_f
            except (TypeError, ValueError, OverflowError):
                ret = None
        created = getattr(call, "created_at", None)
        if not isinstance(created, datetime):
            continue
        admitted_calls.append(
            PastSignalRecall(
                signal_id=signal_id,
                created_at=created,
                action=action,
                horizon=horizon,
                outcome=outcome,
                stock_return_pct=ret,
                memorable=bool(getattr(call, "memorable", False)),
            )
        )
        seen_ids.add(signal_id)

    if not admitted_calls:
        return None

    admitted_actions = {call.action for call in admitted_calls}
    raw_patterns = getattr(reflection, "pattern_calibration", None)
    if not isinstance(raw_patterns, (list, tuple)):
        raw_patterns = ()
    admitted_patterns: List[PatternCalibrationBucket] = []
    seen_pattern_actions: set = set()
    for bucket in raw_patterns:
        if len(admitted_patterns) >= _MAX_PATTERN_BUCKETS:
            break
        action = _safe_token(
            getattr(bucket, "action", None), _SAFE_ACTION_RE_ALPHABET
        ).lower()
        sample_size = getattr(bucket, "sample_size", 0)
        rate = getattr(bucket, "hit_rate_pct", None)
        if (
            action not in admitted_actions
            or action in seen_pattern_actions
            or type(sample_size) is not int
            or sample_size < min_samples
            or sample_size > _MAX_PATTERN_SAMPLE_SIZE
        ):
            continue
        if rate is None:
            continue
        try:
            rate_f = float(rate)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(rate_f) or rate_f < 0.0 or rate_f > 100.0:
            continue
        admitted_patterns.append(
            PatternCalibrationBucket(
                action=action,
                hit_rate_pct=rate_f,
                sample_size=sample_size,
            )
        )
        seen_pattern_actions.add(action)

    source_ids = tuple(call.signal_id for call in admitted_calls)
    hits = sum(1 for call in admitted_calls if call.outcome == "hit")
    misses = sum(1 for call in admitted_calls if call.outcome == "miss")
    neutrals = sum(1 for call in admitted_calls if call.outcome == "neutral")
    decided = hits + misses
    hit_rate: Optional[float]
    if decided >= min_samples:
        hit_rate = round(100.0 * hits / decided, 2)
    else:
        hit_rate = None

    # truncated means lookback omitted older candidates — not admission drops.
    truncated = bool(reflection.truncated)

    # Keep builder window when the listed set is unchanged; otherwise fall back
    # to admitted call created_at dates.
    trusted_window = _valid_window(reflection)
    if len(admitted_calls) == len(raw_calls) and trusted_window is not None:
        window_start, window_end = trusted_window
    else:
        dates = [
            call.created_at.date()
            for call in admitted_calls
            if isinstance(call.created_at, datetime)
        ]
        if dates:
            window_start, window_end = min(dates), max(dates)
        else:
            if trusted_window is None:
                return None
            window_start, window_end = trusted_window

    return DecisionReflection(
        stock_code=str(reflection.stock_code or ""),
        market=str(reflection.market or ""),
        lookback=lookback,
        min_samples=min_samples,
        window_start=window_start,
        window_end=window_end,
        same_stock_total=len(admitted_calls),
        same_stock_hits=hits,
        same_stock_misses=misses,
        same_stock_neutrals=neutrals,
        same_stock_hit_rate_pct=hit_rate,
        recent_calls=tuple(admitted_calls),
        pattern_calibration=tuple(admitted_patterns),
        source_signal_ids=source_ids,
        truncated=truncated,
        admitted=True,
    )


class DecisionMemoryService:
    """Build historical decision reflections from stored signals and outcomes."""

    def __init__(
        self,
        *,
        signal_repo: Any = None,
        outcome_repo: Any = None,
        outcome_service: Any = None,
        flag_repo: Any = None,
    ):
        # Lazy defaults keep import cost off the analyzer/prompt import path.
        self._signal_repo = signal_repo
        self._outcome_repo = outcome_repo
        self._outcome_service = outcome_service
        self._flag_repo = flag_repo

    # ---- dependency accessors (lazily constructed) ----

    @property
    def signal_repo(self) -> Any:
        if self._signal_repo is None:
            from src.repositories.decision_signal_repo import DecisionSignalRepository

            self._signal_repo = DecisionSignalRepository()
        return self._signal_repo

    @property
    def outcome_repo(self) -> Any:
        if self._outcome_repo is None:
            from src.repositories.decision_signal_outcome_repo import (
                DecisionSignalOutcomeRepository,
            )

            self._outcome_repo = DecisionSignalOutcomeRepository()
        return self._outcome_repo

    @property
    def outcome_service(self) -> Any:
        if self._outcome_service is None:
            from src.services.decision_signal_outcome_service import (
                DecisionSignalOutcomeService,
            )

            self._outcome_service = DecisionSignalOutcomeService()
        return self._outcome_service

    @property
    def flag_repo(self) -> Any:
        if self._flag_repo is None:
            from src.repositories.decision_signal_memory_flag_repo import (
                DecisionSignalMemoryFlagRepository,
            )

            self._flag_repo = DecisionSignalMemoryFlagRepository()
        return self._flag_repo

    # ---- signal memory curation flags (memorable / ignored) ----

    def get_flag(self, signal_id: int) -> Dict[str, Any]:
        """Return the curation flags for a signal (defaults when unset)."""
        signal_id_norm = self._require_signal_id(signal_id)
        row = self.flag_repo.get(signal_id=signal_id_norm)
        return self._serialize_flag(signal_id_norm, row)

    def set_flag(
        self,
        signal_id: int,
        *,
        memorable: Optional[bool] = None,
        ignored: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Upsert the curation flags for a signal.

        Only the provided fields change; omitted fields keep their stored value
        (or default False when no row exists yet).
        """
        signal_id_norm = self._require_signal_id(signal_id)
        existing = self.flag_repo.get(signal_id=signal_id_norm)
        current_memorable = bool(getattr(existing, "memorable", False))
        current_ignored = bool(getattr(existing, "ignored", False))
        row = self.flag_repo.upsert(
            {
                "signal_id": signal_id_norm,
                "memorable": current_memorable if memorable is None else bool(memorable),
                "ignored": current_ignored if ignored is None else bool(ignored),
            }
        )
        return self._serialize_flag(signal_id_norm, row)

    def _require_signal_id(self, signal_id: int) -> int:
        from src.services.decision_signal_service import DecisionSignalNotFoundError

        try:
            signal_id_int = int(signal_id)
        except (TypeError, ValueError):
            raise DecisionSignalNotFoundError(f"Decision signal not found: {signal_id}")
        if signal_id_int <= 0:
            raise DecisionSignalNotFoundError(f"Decision signal not found: {signal_id}")
        if self.signal_repo.get(signal_id_int) is None:
            raise DecisionSignalNotFoundError(f"Decision signal not found: {signal_id_int}")
        return signal_id_int

    @staticmethod
    def _serialize_flag(signal_id: int, row: Any) -> Dict[str, Any]:
        created_at = getattr(row, "created_at", None)
        updated_at = getattr(row, "updated_at", None)
        return {
            "signal_id": signal_id,
            "memorable": bool(getattr(row, "memorable", False)),
            "ignored": bool(getattr(row, "ignored", False)),
            "created_at": created_at.isoformat() if created_at is not None else None,
            "updated_at": updated_at.isoformat() if updated_at is not None else None,
        }

    # ---- core ----

    def build_reflection(
        self,
        *,
        stock_code: str,
        market: Optional[str],
        lookback: int,
        min_age_days: int,
        min_samples: int,
        now: Optional[datetime] = None,
    ) -> Optional[DecisionReflection]:
        """Return a reflection for the stock, or None when there is no history.

        Returns None (zero extra work beyond one indexed lookup) whenever no
        past evaluated signals exist, so callers pay nothing when there is no
        history to reflect on.
        """

        from src.services.decision_signal_outcome_service import (
            DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
        )
        from src.services.decision_signal_service import DecisionSignalService
        from src.storage import utc_naive_now

        lookback_n = _bounded_plain_int(
            lookback,
            minimum=0,
            maximum=_MAX_LOOKBACK,
        )
        min_age = _bounded_plain_int(
            min_age_days,
            minimum=0,
            maximum=_MAX_MIN_AGE_DAYS,
        )
        min_samples_n = _bounded_plain_int(
            min_samples,
            minimum=1,
            maximum=_MAX_MIN_SAMPLES,
        )
        if lookback_n is None or min_age is None or min_samples_n is None:
            return None
        if lookback_n == 0:
            return None
        if now is not None and not isinstance(now, datetime):
            return None

        reference_now = now or utc_naive_now()
        if reference_now.tzinfo is not None:
            reference_now = reference_now.astimezone(timezone.utc).replace(tzinfo=None)
        cutoff = reference_now - timedelta(days=min_age)
        scan_size = min(
            _MAX_SIGNAL_SCAN,
            max(lookback_n * _MAX_SCAN_MULTIPLIER, lookback_n),
        )

        normalized_code = DecisionSignalService.normalize_stock_code_for_signal(
            stock_code, market=market
        )
        if not normalized_code:
            return None
        normalized_market = DecisionSignalService._normalize_optional_market(market)

        signals, _ = self.signal_repo.list(
            stock_codes=[normalized_code],
            market=normalized_market,
            created_to=cutoff,
            page=1,
            page_size=scan_size,
        )
        if not signals:
            return None

        signal_by_id = {int(s.id): s for s in signals}

        # User curation: ignored signals are excluded from memory entirely;
        # memorable signals are highlighted and preferred in the recall list.
        flags = self.flag_repo.list_for_signals(signal_ids=list(signal_by_id.keys()))
        ignored_ids = {int(f.signal_id) for f in flags if getattr(f, "ignored", False)}
        memorable_ids = {int(f.signal_id) for f in flags if getattr(f, "memorable", False)}
        eligible_ids = [sid for sid in signal_by_id if sid not in ignored_ids]
        if not eligible_ids:
            return None

        outcome_rows = self.outcome_repo.list_outcomes_for_signals(
            signal_ids=eligible_ids,
            engine_version=DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
        )
        decided_rows = [
            row
            for row in outcome_rows
            if getattr(row, "eval_status", None) == "completed"
            and getattr(row, "outcome", None) in _ADMITTED_OUTCOMES
        ]
        if not decided_rows:
            return None

        # One representative outcome per signal, then lookback-cap. Same-stock
        # rates are computed only over this listed set so stats never include
        # non-listed scan history (review contract for #118).
        all_calls = self._recent_calls(decided_rows, signal_by_id, memorable_ids)
        truncated = len(all_calls) > lookback_n
        recent_calls = all_calls[:lookback_n]
        if not recent_calls:
            return None

        hits = sum(1 for call in recent_calls if call.outcome == "hit")
        misses = sum(1 for call in recent_calls if call.outcome == "miss")
        neutrals = sum(1 for call in recent_calls if call.outcome == "neutral")
        decided = hits + misses
        # Guardrail 1: suppress the rate when decided samples are below threshold.
        hit_rate = (
            round(100.0 * hits / decided, 2) if decided >= min_samples_n else None
        )

        # Window is drawn only from the listed lookback signals' outcome anchors
        # (regime annotation), never from non-listed scan leftovers.
        listed_ids = {call.signal_id for call in recent_calls}
        listed_rows = [
            row for row in decided_rows if int(row.signal_id) in listed_ids
        ]
        window_start, window_end = self._window_bounds(listed_rows, signal_by_id)
        actions_present = {call.action for call in recent_calls}
        pattern = self._pattern_calibration(actions_present, min_samples_n)

        raw = DecisionReflection(
            stock_code=normalized_code,
            market=str(normalized_market or getattr(signals[0], "market", "") or ""),
            lookback=lookback_n,
            min_samples=min_samples_n,
            window_start=window_start,
            window_end=window_end,
            same_stock_total=len(recent_calls),
            same_stock_hits=hits,
            same_stock_misses=misses,
            same_stock_neutrals=neutrals,
            same_stock_hit_rate_pct=hit_rate,
            recent_calls=recent_calls,
            pattern_calibration=pattern,
            source_signal_ids=tuple(call.signal_id for call in recent_calls),
            truncated=truncated,
            admitted=False,
        )
        # Inject path must never bypass admission (#1119).
        return admit_decision_memory(raw, max_calls=lookback_n)

    # ---- helpers ----

    @staticmethod
    def _row_anchor_date(row: Any) -> Optional[date]:
        anchor = getattr(row, "anchor_date", None)
        if isinstance(anchor, datetime):
            return anchor.date()
        if isinstance(anchor, date):
            return anchor
        return None

    def _window_bounds(
        self,
        decided_rows: Sequence[Any],
        signal_by_id: Dict[int, Any],
    ) -> Tuple[date, date]:
        dates: List[date] = []
        for row in decided_rows:
            anchor = self._row_anchor_date(row)
            if anchor is None:
                created = getattr(signal_by_id.get(int(row.signal_id)), "created_at", None)
                if isinstance(created, datetime):
                    anchor = created.date()
            if anchor is not None:
                dates.append(anchor)
        if not dates:
            today = date.today()
            return today, today
        return min(dates), max(dates)


    def _recent_calls(
        self,
        decided_rows: Sequence[Any],
        signal_by_id: Dict[int, Any],
        memorable_ids: Optional[set] = None,
    ) -> Tuple[PastSignalRecall, ...]:
        """One representative decided outcome per signal.

        When a signal has outcomes across multiple horizons, keep the longest
        evaluated window so the recall reflects the most complete forward view.
        Memorable-flagged calls are ordered first, then most recent first.
        """

        memorable = memorable_ids or set()
        horizon_rank = {"1d": 1, "3d": 3, "5d": 5, "10d": 10}
        best_by_signal: Dict[int, Any] = {}
        for row in decided_rows:
            sid = int(row.signal_id)
            current = best_by_signal.get(sid)
            if current is None:
                best_by_signal[sid] = row
                continue
            if horizon_rank.get(getattr(row, "horizon", ""), 0) > horizon_rank.get(
                getattr(current, "horizon", ""), 0
            ):
                best_by_signal[sid] = row

        calls: List[PastSignalRecall] = []
        for sid, row in best_by_signal.items():
            signal = signal_by_id.get(sid)
            if signal is None:
                continue
            created_at = getattr(signal, "created_at", None)
            if not isinstance(created_at, datetime):
                continue
            calls.append(
                PastSignalRecall(
                    signal_id=sid,
                    created_at=created_at,
                    action=str(getattr(signal, "action", "") or ""),
                    horizon=getattr(row, "horizon", None),
                    outcome=str(getattr(row, "outcome", "") or ""),
                    stock_return_pct=getattr(row, "stock_return_pct", None),
                    memorable=sid in memorable,
                )
            )
        calls.sort(
            key=lambda c: (
                not c.memorable,
                -c.created_at.timestamp(),
                -c.signal_id,
            )
        )
        return tuple(calls)

    def _pattern_calibration(
        self,
        actions_present: Sequence[str],
        min_samples: int,
    ) -> Tuple[PatternCalibrationBucket, ...]:
        """Global per-action hit-rate for the kinds of call seen on this stock.

        Only buckets whose decided (hit+miss) sample is at least ``min_samples``
        are returned (guardrail 1). Reuses the authoritative outcome stats.
        """

        actions = {a for a in actions_present if a}
        if not actions:
            return tuple()
        try:
            # Memory owns a separate decided-sample threshold, so it needs the
            # authoritative raw rate rather than the public dashboard's floor.
            stats = self.outcome_service.get_stats(publish=False)
        except Exception as exc:  # broad-exception: fallback_recorded - pattern calibration is optional; same-stock memory still stands.
            from src.utils.sanitize import log_safe_exception

            log_safe_exception(
                logger,
                "Pattern calibration stats unavailable",
                exc,
                error_code="decision_memory_pattern_stats_failed",
                level=logging.DEBUG,
            )
            return tuple()

        threshold = _bounded_plain_int(
            min_samples,
            minimum=1,
            maximum=_MAX_MIN_SAMPLES,
        )
        if threshold is None or not isinstance(stats, dict):
            return tuple()
        breakdowns = stats.get("breakdowns")
        if not isinstance(breakdowns, dict):
            return tuple()
        action_rows = breakdowns.get("action")
        if not isinstance(action_rows, (list, tuple)):
            return tuple()
        buckets: List[PatternCalibrationBucket] = []
        for bucket in action_rows:
            if not isinstance(bucket, dict):
                continue
            action = str(bucket.get("value") or "")
            if action not in actions:
                continue
            hit = _bounded_plain_int(
                bucket.get("hit", 0),
                minimum=0,
                maximum=_MAX_PATTERN_SAMPLE_SIZE,
            )
            miss = _bounded_plain_int(
                bucket.get("miss", 0),
                minimum=0,
                maximum=_MAX_PATTERN_SAMPLE_SIZE,
            )
            if hit is None or miss is None:
                continue
            decided = hit + miss
            rate = bucket.get("hit_rate_pct")
            if decided < threshold or rate is None:
                continue
            try:
                rate_f = float(rate)
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(rate_f) or rate_f < 0.0 or rate_f > 100.0:
                continue
            buckets.append(
                PatternCalibrationBucket(
                    action=action,
                    hit_rate_pct=rate_f,
                    sample_size=decided,
                )
            )
        buckets.sort(key=lambda b: (-b.sample_size, b.action))
        return tuple(buckets[:_MAX_PATTERN_BUCKETS])


# --------------------------------------------------------------------------
# Rendering: prompt injection block and user-facing report section.
# Prompt path depends on memory_isolation; report path stays lightweight.
# --------------------------------------------------------------------------

_ACTION_LABELS = {
    "zh": {
        "buy": "买入",
        "add": "加仓",
        "hold": "持有",
        "reduce": "减仓",
        "sell": "卖出",
        "watch": "观察",
        "avoid": "回避",
        "alert": "提示",
    },
    "en": {
        "buy": "Buy",
        "add": "Add",
        "hold": "Hold",
        "reduce": "Reduce",
        "sell": "Sell",
        "watch": "Watch",
        "avoid": "Avoid",
        "alert": "Alert",
    },
}
_OUTCOME_LABELS = {
    "zh": {"hit": "命中", "miss": "偏离", "neutral": "中性"},
    "en": {"hit": "Hit", "miss": "Miss", "neutral": "Neutral"},
}


def _lang(report_language: Optional[str]) -> str:
    value = str(report_language or "zh").lower()
    return "en" if value.startswith("en") else "zh"


def _action_label(action: str, lang: str) -> str:
    return _ACTION_LABELS[lang].get(action, action or "-")


def _outcome_label(outcome: str, lang: str) -> str:
    return _OUTCOME_LABELS[lang].get(outcome, outcome or "-")


def _fmt_return(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}%"


def _call_provenance(call: PastSignalRecall) -> str:
    return f"signal_id={int(call.signal_id)}"


def _reflection_lines(reflection: DecisionReflection, lang: str) -> List[str]:
    """Shared body used by both prompt and report renderers."""

    window = f"{reflection.window_start.isoformat()} ~ {reflection.window_end.isoformat()}"
    lines: List[str] = []
    if lang == "en":
        if reflection.same_stock_hit_rate_pct is not None:
            lines.append(
                f"- Same-stock track record ({window}): "
                f"{reflection.same_stock_hits}/{reflection.same_stock_decided} decided calls hit "
                f"({reflection.same_stock_hit_rate_pct:.1f}%), "
                f"{reflection.same_stock_neutrals} neutral."
            )
        else:
            lines.append(
                f"- Same-stock track record ({window}): "
                f"{reflection.same_stock_hits} hit / {reflection.same_stock_misses} miss / "
                f"{reflection.same_stock_neutrals} neutral across {reflection.same_stock_total} evaluated "
                f"call(s) — too few decided samples (< {reflection.min_samples}) for a reliable rate."
            )
        if reflection.recent_calls:
            lines.append(
                "- Recent evaluated calls (memorable first, then newest; "
                "provenance in brackets):"
            )
            for call in reflection.recent_calls:
                horizon = f" / {call.horizon}" if call.horizon else ""
                star = " *(memorable)*" if call.memorable else ""
                lines.append(
                    f"  - {call.created_at.date().isoformat()} "
                    f"{_action_label(call.action, lang)}{horizon}: "
                    f"{_outcome_label(call.outcome, lang)} ({_fmt_return(call.stock_return_pct)}) "
                    f"[{_call_provenance(call)}]{star}"
                )
        if reflection.pattern_calibration:
            lines.append("- Track record for these kinds of call (all recorded outcomes):")
            for bucket in reflection.pattern_calibration:
                lines.append(
                    f"  - {_action_label(bucket.action, lang)} calls hit "
                    f"{bucket.hit_rate_pct:.1f}% (n={bucket.sample_size})."
                )
        if reflection.source_signal_ids:
            ids = ",".join(str(sid) for sid in reflection.source_signal_ids)
            lines.append(f"- Source signal ids: {ids}")
        if reflection.truncated:
            lines.append(
                f"- Note: same-stock rate and list both use the lookback={reflection.lookback} "
                f"admitted set; additional evaluated history was omitted by lookback."
            )
        return lines

    if reflection.same_stock_hit_rate_pct is not None:
        lines.append(
            f"- 本股历史战绩（{window}）："
            f"已判定 {reflection.same_stock_decided} 次中命中 {reflection.same_stock_hits} 次"
            f"（{reflection.same_stock_hit_rate_pct:.1f}%），中性 {reflection.same_stock_neutrals} 次。"
        )
    else:
        lines.append(
            f"- 本股历史战绩（{window}）："
            f"共 {reflection.same_stock_total} 次已评估，命中 {reflection.same_stock_hits} / "
            f"偏离 {reflection.same_stock_misses} / 中性 {reflection.same_stock_neutrals} —— "
            f"已判定样本不足（< {reflection.min_samples}），暂不给出胜率。"
        )
    if reflection.recent_calls:
        lines.append("- 近期已评估的判断（重点优先，其余由新到旧；方括号为来源）：")
        for call in reflection.recent_calls:
            horizon = f" / {call.horizon}" if call.horizon else ""
            star = "（重点）" if call.memorable else ""
            lines.append(
                f"  - {call.created_at.date().isoformat()} "
                f"{_action_label(call.action, lang)}{horizon}："
                f"{_outcome_label(call.outcome, lang)}（{_fmt_return(call.stock_return_pct)}）"
                f"[{_call_provenance(call)}]{star}"
            )
    if reflection.pattern_calibration:
        lines.append("- 同类判断的整体战绩（全部已记录结果）：")
        for bucket in reflection.pattern_calibration:
            lines.append(
                f"  - {_action_label(bucket.action, lang)}类判断命中率 "
                f"{bucket.hit_rate_pct:.1f}%（n={bucket.sample_size}）。"
            )
    if reflection.source_signal_ids:
        ids = ",".join(str(sid) for sid in reflection.source_signal_ids)
        lines.append(f"- 来源 signal_id：{ids}")
    if reflection.truncated:
        lines.append(
            f"- 说明：本股胜率与列表均只使用 lookback={reflection.lookback} "
            f"准入集合；其余已评估记录因 lookback 未纳入。"
        )
    return lines


def format_decision_memory_prompt_section(
    reflection: Optional[DecisionReflection],
    *,
    report_language: str = "zh",
) -> str:
    """Render the reflection as an isolated untrusted prompt block, or ''.

    Always runs admission first so non-admitted / free-form payloads cannot
    reach the model. Isolation uses the shared memory isolation contract
    (BEGIN/END markers + data-only directive).
    """

    # ``admitted`` is audit metadata, not an authority bit. Re-run admission on
    # every public render so a hand-built dataclass cannot forge trusted status.
    admitted = admit_decision_memory(reflection)
    if admitted is None:
        return ""
    lang = _lang(report_language)
    title = "Historical Decision Reflection" if lang == "en" else "历史决策复盘"
    guardrail = _PROMPT_GUARDRAIL_EN if lang == "en" else _PROMPT_GUARDRAIL_ZH
    body = "\n".join(_reflection_lines(admitted, lang))
    from src.agent.memory_isolation import isolate_untrusted_memory_body

    isolated = isolate_untrusted_memory_body(body, max_chars=_MAX_PROMPT_CHARS)
    return f"\n\n## 🧭 {title}\n\n{isolated}\n\n> {guardrail}\n"


def render_decision_memory_report_section(
    reflection: Optional[DecisionReflection],
    *,
    report_language: str = "zh",
) -> str:
    """Render the reflection as a user-facing report section, or ''."""

    admitted = admit_decision_memory(reflection)
    if admitted is None:
        return ""
    lang = _lang(report_language)
    title = "Historical Decision Reflection" if lang == "en" else "历史决策复盘"
    note = (
        "Calibrates confidence from past outcomes; it does not change the call above. "
        "Source signal ids are listed for auditability."
        if lang == "en"
        else "基于历史结果校准置信度，不改变上方结论；来源 signal_id 可追溯。"
    )
    body = "\n".join(_reflection_lines(admitted, lang))
    return f"### 🧭 {title}\n\n{body}\n\n_{note}_"
