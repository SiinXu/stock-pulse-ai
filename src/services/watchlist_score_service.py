# -*- coding: utf-8 -*-
"""Watchlist AI score aggregation from existing analysis + decision signals (Issue #147 / T25).

Route A: reuse stored analysis history and active decision signals. Never invents a
score when a symbol has no analysis history, and never triggers a new LLM call.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from sqlalchemy import desc, select

from src.services.stock_code_utils import canonicalize_analysis_stock_code
from src.storage import DatabaseManager
from src.storage_parts.schema import AnalysisHistory, DecisionSignalRecord

# Public contract values
SCORE_STATUS_SCORED = "scored"
SCORE_STATUS_UNANALYZED = "unanalyzed"
SORT_MANUAL = "manual"
SORT_SCORE_DESC = "score_desc"
SORT_SCORE_ASC = "score_asc"
ALLOWED_SORT_MODES = frozenset({SORT_MANUAL, SORT_SCORE_DESC, SORT_SCORE_ASC})
SCORING_MODE_AGGREGATE_EXISTING = "aggregate_existing"

# Blend weights when both analysis sentiment and an active signal are present.
_WEIGHT_SENTIMENT = 0.75
_WEIGHT_SIGNAL = 0.25

# Map decision-signal actions to a 0-100 style contribution (explainable only).
_ACTION_SCORE_HINT: Mapping[str, int] = {
    "strong_buy": 90,
    "buy": 75,
    "hold": 50,
    "watch": 45,
    "sell": 25,
    "strong_sell": 10,
}

_MAX_CODES = 200


class WatchlistScoreService:
    """Aggregate per-symbol watchlist scores from stored history and signals."""

    def __init__(
        self,
        *,
        db_manager: Optional[DatabaseManager] = None,
        analysis_loader: Optional[Callable[[Sequence[str]], Mapping[str, Any]]] = None,
        signal_loader: Optional[Callable[[Sequence[str]], Mapping[str, Any]]] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._db_manager = db_manager
        self._analysis_loader = analysis_loader
        self._signal_loader = signal_loader
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def db(self) -> DatabaseManager:
        if self._db_manager is None:
            self._db_manager = DatabaseManager()
        return self._db_manager

    def score_symbols(
        self,
        stock_codes: Optional[Sequence[str]] = None,
        *,
        sort: str = SORT_MANUAL,
    ) -> Dict[str, Any]:
        """Score symbols from existing analysis + signals.

        Parameters
        ----------
        stock_codes:
            Ordered watchlist codes. Empty/None yields an empty item list.
        sort:
            ``manual`` keeps input order (default). ``score_desc`` / ``score_asc``
            reorder scored items while keeping unanalyzed rows after scored ones
            and preserving relative order within each band when scores tie.
        """
        sort_mode = self._normalize_sort(sort)
        ordered_codes = self._normalize_input_codes(stock_codes)
        if not ordered_codes:
            return self._empty_payload(sort_mode)

        # Canonical + raw forms so a single batch query covers code variants.
        query_codes = self._expand_query_codes(ordered_codes)
        analyses, analysis_queries = self._load_latest_analyses(query_codes)
        signals, signal_queries = self._load_latest_active_signals(query_codes)

        items: List[Dict[str, Any]] = []
        for code in ordered_codes:
            match_key = self._match_key(code)
            analysis = analyses.get(match_key)
            signal = signals.get(match_key)
            items.append(self._build_item(stock_code=code, analysis=analysis, signal=signal))

        ordered = self.order_items(items, sort_mode=sort_mode, input_codes=ordered_codes)
        return {
            "scoring_mode": SCORING_MODE_AGGREGATE_EXISTING,
            "sort": sort_mode,
            "items": ordered,
            "query_count": {
                "analysis": analysis_queries,
                "signals": signal_queries,
            },
            "disclaimer": (
                "Scores aggregate existing analysis and decision-signal history. "
                "They are not investment advice and may lag the market."
            ),
        }

    @staticmethod
    def order_items(
        items: Sequence[Mapping[str, Any]],
        *,
        sort_mode: str = SORT_MANUAL,
        input_codes: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Order score items. Default ``manual`` preserves the input watchlist order."""
        mode = WatchlistScoreService._normalize_sort(sort_mode)
        rows = [dict(item) for item in items]
        if mode == SORT_MANUAL:
            if input_codes is None:
                return rows
            index = {str(code): i for i, code in enumerate(input_codes)}
            rows.sort(key=lambda row: index.get(str(row.get("stock_code")), len(index)))
            return rows

        reverse = mode == SORT_SCORE_DESC

        def _sort_key(row: Mapping[str, Any]) -> tuple:
            status = str(row.get("status") or "")
            scored = 0 if status == SCORE_STATUS_SCORED else 1
            score = row.get("score")
            # Unanalyzed always after scored; among scored use numeric score.
            numeric = float(score) if isinstance(score, (int, float)) else float("-inf")
            if not reverse:
                # Ascending: lower score first among scored.
                return (scored, numeric if scored == 0 else float("inf"))
            # Descending: higher score first.
            return (scored, -numeric if scored == 0 else float("inf"))

        # Stable sort: ties keep relative order (manual order within equal scores).
        if input_codes is not None:
            index = {str(code): i for i, code in enumerate(input_codes)}
            rows.sort(
                key=lambda row: (
                    *_sort_key(row),
                    index.get(str(row.get("stock_code")), len(index)),
                )
            )
        else:
            rows.sort(key=_sort_key)
        return rows

    # ---- loaders ---------------------------------------------------------

    def _load_latest_analyses(
        self, query_codes: Sequence[str]
    ) -> tuple[Dict[str, Any], int]:
        if self._analysis_loader is not None:
            loaded = dict(self._analysis_loader(query_codes) or {})
            return self._rekey_by_match(loaded), 1
        if not query_codes:
            return {}, 0
        with self.db.get_session() as session:
            rows = session.execute(
                select(AnalysisHistory)
                .where(AnalysisHistory.code.in_(list(query_codes)))
                .order_by(desc(AnalysisHistory.created_at), desc(AnalysisHistory.id))
            ).scalars().all()
        latest: Dict[str, Any] = {}
        for row in rows:
            key = self._match_key(getattr(row, "code", "") or "")
            if key and key not in latest:
                latest[key] = row
        return latest, 1

    def _load_latest_active_signals(
        self, query_codes: Sequence[str]
    ) -> tuple[Dict[str, Any], int]:
        if self._signal_loader is not None:
            loaded = dict(self._signal_loader(query_codes) or {})
            return self._rekey_by_match(loaded), 1
        if not query_codes:
            return {}, 0
        with self.db.get_session() as session:
            rows = session.execute(
                select(DecisionSignalRecord)
                .where(
                    DecisionSignalRecord.status == "active",
                    DecisionSignalRecord.stock_code.in_(list(query_codes)),
                )
                .order_by(
                    desc(DecisionSignalRecord.created_at),
                    desc(DecisionSignalRecord.id),
                )
            ).scalars().all()
        latest: Dict[str, Any] = {}
        for row in rows:
            key = self._match_key(getattr(row, "stock_code", "") or "")
            if key and key not in latest:
                latest[key] = row
        return latest, 1

    # ---- item construction -----------------------------------------------

    def _build_item(
        self,
        *,
        stock_code: str,
        analysis: Any,
        signal: Any,
    ) -> Dict[str, Any]:
        if analysis is None:
            return {
                "stock_code": stock_code,
                "status": SCORE_STATUS_UNANALYZED,
                "score": None,
                "as_of": None,
                "age_days": None,
                "analysis_id": None,
                "operation_advice": None,
                "factors": [],
                "freshness": "none",
            }

        sentiment = getattr(analysis, "sentiment_score", None)
        if sentiment is None:
            # History row without a score is still "unanalyzed" for scoring purposes —
            # never invent 0.
            return {
                "stock_code": stock_code,
                "status": SCORE_STATUS_UNANALYZED,
                "score": None,
                "as_of": self._iso(getattr(analysis, "created_at", None)),
                "age_days": self._age_days(getattr(analysis, "created_at", None)),
                "analysis_id": getattr(analysis, "id", None),
                "operation_advice": getattr(analysis, "operation_advice", None),
                "factors": [],
                "freshness": self._freshness_label(getattr(analysis, "created_at", None)),
            }

        sentiment_int = int(sentiment)
        factors: List[Dict[str, Any]] = [
            {
                "key": "analysis_sentiment",
                "label": "Analysis sentiment score",
                "value": sentiment_int,
                "detail": self._analysis_detail(analysis),
            }
        ]
        signal_component: Optional[float] = None
        if signal is not None:
            action = str(getattr(signal, "action", "") or "").strip().lower()
            hint = _ACTION_SCORE_HINT.get(action)
            confidence = getattr(signal, "confidence", None)
            if hint is not None:
                if isinstance(confidence, (int, float)):
                    # Blend action hint with confidence toward neutral 50.
                    conf = max(0.0, min(1.0, float(confidence)))
                    signal_component = hint * conf + 50.0 * (1.0 - conf)
                else:
                    signal_component = float(hint)
            factors.append(
                {
                    "key": "decision_signal",
                    "label": "Active decision signal",
                    "value": action or "unknown",
                    "detail": self._signal_detail(signal),
                }
            )

        if signal_component is None:
            composite = float(sentiment_int)
        else:
            composite = (
                _WEIGHT_SENTIMENT * float(sentiment_int)
                + _WEIGHT_SIGNAL * float(signal_component)
            )
        score = int(round(max(0.0, min(100.0, composite))))
        created_at = getattr(analysis, "created_at", None)
        return {
            "stock_code": stock_code,
            "status": SCORE_STATUS_SCORED,
            "score": score,
            "as_of": self._iso(created_at),
            "age_days": self._age_days(created_at),
            "analysis_id": getattr(analysis, "id", None),
            "operation_advice": getattr(analysis, "operation_advice", None),
            "factors": factors,
            "freshness": self._freshness_label(created_at),
        }

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _normalize_sort(sort: Optional[str]) -> str:
        value = str(sort or SORT_MANUAL).strip().lower()
        if value not in ALLOWED_SORT_MODES:
            raise ValueError(
                f"Unsupported sort mode: {sort!r}. "
                f"Allowed: {', '.join(sorted(ALLOWED_SORT_MODES))}"
            )
        return value

    @staticmethod
    def _normalize_input_codes(stock_codes: Optional[Sequence[str]]) -> List[str]:
        if not stock_codes:
            return []
        ordered: List[str] = []
        seen: set[str] = set()
        for raw in stock_codes:
            if raw is None:
                continue
            code = str(raw).strip()
            if not code:
                continue
            key = WatchlistScoreService._match_key(code)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(code)
            if len(ordered) >= _MAX_CODES:
                break
        return ordered

    @classmethod
    def _expand_query_codes(cls, codes: Sequence[str]) -> List[str]:
        expanded: List[str] = []
        seen: set[str] = set()
        for code in codes:
            for candidate in (code, cls._match_key(code)):
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    expanded.append(candidate)
        return expanded

    @staticmethod
    def _match_key(code: str) -> str:
        canonical = canonicalize_analysis_stock_code(code)
        if canonical:
            return canonical
        return str(code or "").strip().upper()

    def _rekey_by_match(self, loaded: Mapping[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for raw_key, value in loaded.items():
            key = self._match_key(str(raw_key))
            if key and key not in result:
                result[key] = value
        return result

    def _age_days(self, created_at: Any) -> Optional[int]:
        if created_at is None:
            return None
        now = self._clock()
        if isinstance(created_at, datetime):
            created = created_at
        else:
            return None
        if created.tzinfo is None and now.tzinfo is not None:
            created = created.replace(tzinfo=timezone.utc)
        elif created.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        delta = now - created
        return max(0, int(delta.total_seconds() // 86400))

    def _freshness_label(self, created_at: Any) -> str:
        age = self._age_days(created_at)
        if age is None:
            return "unknown"
        if age <= 0:
            return "today"
        if age == 1:
            return "1d"
        if age <= 3:
            return f"{age}d"
        if age <= 7:
            return "stale_week"
        return "stale"

    @staticmethod
    def _iso(value: Any) -> Optional[str]:
        if isinstance(value, datetime):
            return value.isoformat()
        return None

    @staticmethod
    def _analysis_detail(analysis: Any) -> str:
        parts: List[str] = []
        advice = getattr(analysis, "operation_advice", None)
        if advice:
            parts.append(f"advice={advice}")
        report_type = getattr(analysis, "report_type", None)
        if report_type:
            parts.append(f"report_type={report_type}")
        created = getattr(analysis, "created_at", None)
        if isinstance(created, datetime):
            parts.append(f"as_of={created.date().isoformat()}")
        return "; ".join(parts) if parts else "from latest analysis history"

    @staticmethod
    def _signal_detail(signal: Any) -> str:
        parts: List[str] = []
        label = getattr(signal, "action_label", None)
        if label:
            parts.append(f"label={label}")
        confidence = getattr(signal, "confidence", None)
        if isinstance(confidence, (int, float)):
            parts.append(f"confidence={float(confidence):.2f}")
        created = getattr(signal, "created_at", None)
        if isinstance(created, datetime):
            parts.append(f"signal_at={created.date().isoformat()}")
        signal_id = getattr(signal, "id", None)
        if signal_id is not None:
            parts.append(f"signal_id={signal_id}")
        return "; ".join(parts) if parts else "active decision signal"

    @staticmethod
    def _empty_payload(sort_mode: str) -> Dict[str, Any]:
        return {
            "scoring_mode": SCORING_MODE_AGGREGATE_EXISTING,
            "sort": sort_mode,
            "items": [],
            "query_count": {"analysis": 0, "signals": 0},
            "disclaimer": (
                "Scores aggregate existing analysis and decision-signal history. "
                "They are not investment advice and may lag the market."
            ),
        }
