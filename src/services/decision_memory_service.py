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

Hit / miss / neutral classifications are the authoritative values already stored
on ``DecisionSignalOutcomeRecord`` by ``DecisionSignalOutcomeService``; this
module reuses them and never re-derives what counts as a hit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
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


@dataclass(frozen=True)
class PastSignalRecall:
    """One past signal with its authoritative forward outcome (a fact)."""

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

    @property
    def same_stock_decided(self) -> int:
        return self.same_stock_hits + self.same_stock_misses


class DecisionMemoryService:
    """Build historical decision reflections from stored signals and outcomes."""

    def __init__(
        self,
        *,
        signal_repo: Any = None,
        outcome_repo: Any = None,
        outcome_service: Any = None,
    ):
        # Lazy defaults keep import cost off the analyzer/prompt import path.
        self._signal_repo = signal_repo
        self._outcome_repo = outcome_repo
        self._outcome_service = outcome_service

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

        if lookback <= 0:
            return None

        reference_now = now or utc_naive_now()
        min_age = max(0, int(min_age_days))
        cutoff = reference_now - timedelta(days=min_age)

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
            page_size=max(1, int(lookback)),
        )
        if not signals:
            return None

        signal_by_id = {int(s.id): s for s in signals}
        outcome_rows = self.outcome_repo.list_outcomes_for_signals(
            signal_ids=list(signal_by_id.keys()),
            engine_version=DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
        )
        decided_rows = [
            row
            for row in outcome_rows
            if getattr(row, "eval_status", None) == "completed"
            and getattr(row, "outcome", None) in {"hit", "miss", "neutral"}
        ]
        if not decided_rows:
            return None

        aggregate = self.outcome_service.aggregate_outcome_rows(decided_rows)
        hits = int(aggregate.get("hit", 0))
        misses = int(aggregate.get("miss", 0))
        neutrals = int(aggregate.get("neutral", 0))
        decided = hits + misses

        # Guardrail 1: suppress the rate when decided samples are below threshold.
        hit_rate = (
            aggregate.get("hit_rate_pct")
            if decided >= max(1, int(min_samples))
            else None
        )

        window_start, window_end = self._window_bounds(decided_rows, signal_by_id)
        recent_calls = self._recent_calls(decided_rows, signal_by_id)
        actions_present = {call.action for call in recent_calls}
        pattern = self._pattern_calibration(actions_present, min_samples)

        return DecisionReflection(
            stock_code=normalized_code,
            market=str(normalized_market or getattr(signals[0], "market", "") or ""),
            lookback=int(lookback),
            min_samples=max(1, int(min_samples)),
            window_start=window_start,
            window_end=window_end,
            same_stock_total=len(decided_rows),
            same_stock_hits=hits,
            same_stock_misses=misses,
            same_stock_neutrals=neutrals,
            same_stock_hit_rate_pct=hit_rate,
            recent_calls=recent_calls,
            pattern_calibration=pattern,
        )

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
    ) -> Tuple[PastSignalRecall, ...]:
        """One representative decided outcome per signal, newest first.

        When a signal has outcomes across multiple horizons, keep the longest
        evaluated window so the recall reflects the most complete forward view.
        """

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
            calls.append(
                PastSignalRecall(
                    signal_id=sid,
                    created_at=getattr(signal, "created_at", None) or datetime.min,
                    action=str(getattr(signal, "action", "") or ""),
                    horizon=getattr(row, "horizon", None),
                    outcome=str(getattr(row, "outcome", "") or ""),
                    stock_return_pct=getattr(row, "stock_return_pct", None),
                    memorable=bool(getattr(signal, "memorable", False)),
                )
            )
        calls.sort(key=lambda c: c.created_at, reverse=True)
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
            stats = self.outcome_service.get_stats()
        except Exception as exc:  # broad-exception: fallback_recorded - pattern calibration is optional; same-stock memory still stands.
            logger.debug("Pattern calibration stats unavailable: %s", exc)
            return tuple()

        threshold = max(1, int(min_samples))
        buckets: List[PatternCalibrationBucket] = []
        for bucket in stats.get("breakdowns", {}).get("action", []) or []:
            action = str(bucket.get("value") or "")
            if action not in actions:
                continue
            decided = int(bucket.get("hit", 0)) + int(bucket.get("miss", 0))
            rate = bucket.get("hit_rate_pct")
            if decided < threshold or rate is None:
                continue
            buckets.append(
                PatternCalibrationBucket(
                    action=action,
                    hit_rate_pct=float(rate),
                    sample_size=decided,
                )
            )
        buckets.sort(key=lambda b: (-b.sample_size, b.action))
        return tuple(buckets)


# --------------------------------------------------------------------------
# Rendering: prompt injection block and user-facing report section.
# Kept dependency-free so the analyzer/notification import paths stay light.
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
            lines.append("- Recent evaluated calls (newest first):")
            for call in reflection.recent_calls:
                horizon = f" / {call.horizon}" if call.horizon else ""
                star = " *(memorable)*" if call.memorable else ""
                lines.append(
                    f"  - {call.created_at.date().isoformat()} "
                    f"{_action_label(call.action, lang)}{horizon}: "
                    f"{_outcome_label(call.outcome, lang)} ({_fmt_return(call.stock_return_pct)}){star}"
                )
        if reflection.pattern_calibration:
            lines.append("- Track record for these kinds of call (all recorded outcomes):")
            for bucket in reflection.pattern_calibration:
                lines.append(
                    f"  - {_action_label(bucket.action, lang)} calls hit "
                    f"{bucket.hit_rate_pct:.1f}% (n={bucket.sample_size})."
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
        lines.append("- 近期已评估的判断（由新到旧）：")
        for call in reflection.recent_calls:
            horizon = f" / {call.horizon}" if call.horizon else ""
            star = "（重点）" if call.memorable else ""
            lines.append(
                f"  - {call.created_at.date().isoformat()} "
                f"{_action_label(call.action, lang)}{horizon}："
                f"{_outcome_label(call.outcome, lang)}（{_fmt_return(call.stock_return_pct)}）{star}"
            )
    if reflection.pattern_calibration:
        lines.append("- 同类判断的整体战绩（全部已记录结果）：")
        for bucket in reflection.pattern_calibration:
            lines.append(
                f"  - {_action_label(bucket.action, lang)}类判断命中率 "
                f"{bucket.hit_rate_pct:.1f}%（n={bucket.sample_size}）。"
            )
    return lines


def format_decision_memory_prompt_section(
    reflection: Optional[DecisionReflection],
    *,
    report_language: str = "zh",
) -> str:
    """Render the reflection as a prompt block, or '' when there is nothing."""

    if reflection is None:
        return ""
    lang = _lang(report_language)
    title = "Historical Decision Reflection" if lang == "en" else "历史决策复盘"
    guardrail = _PROMPT_GUARDRAIL_EN if lang == "en" else _PROMPT_GUARDRAIL_ZH
    body = "\n".join(_reflection_lines(reflection, lang))
    return f"\n\n## 🧭 {title}\n\n{body}\n\n> {guardrail}\n"


def render_decision_memory_report_section(
    reflection: Optional[DecisionReflection],
    *,
    report_language: str = "zh",
) -> str:
    """Render the reflection as a user-facing report section, or ''."""

    if reflection is None:
        return ""
    lang = _lang(report_language)
    title = "Historical Decision Reflection" if lang == "en" else "历史决策复盘"
    note = (
        "Calibrates confidence from past outcomes; it does not change the call above."
        if lang == "en"
        else "基于历史结果校准置信度，不改变上方结论。"
    )
    body = "\n".join(_reflection_lines(reflection, lang))
    return f"### 🧭 {title}\n\n{body}\n\n_{note}_"
