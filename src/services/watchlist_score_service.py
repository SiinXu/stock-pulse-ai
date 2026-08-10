# -*- coding: utf-8 -*-
"""Bounded watchlist scoring from existing analysis and decision signals."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone, tzinfo
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from sqlalchemy import case, desc, func, or_, select

from src.repositories.decision_signal_repo import DecisionSignalRepository
from src.services.stock_code_utils import resolve_daily_stock_identity
from src.storage import DatabaseManager, to_utc_naive_datetime
from src.storage_parts.schema import AnalysisHistory, DecisionSignalRecord

SCORE_STATUS_SCORED = "scored"
SCORE_STATUS_UNANALYZED = "unanalyzed"
SORT_MANUAL = "manual"
SORT_SCORE_DESC = "score_desc"
SORT_SCORE_ASC = "score_asc"
ALLOWED_SORT_MODES = frozenset({SORT_MANUAL, SORT_SCORE_DESC, SORT_SCORE_ASC})
SCORING_MODE_AGGREGATE_EXISTING = "aggregate_existing"
FORMULA_VERSION = "watchlist_score_v1"

_WEIGHT_SENTIMENT = 0.75
_WEIGHT_SIGNAL = 0.25
_ACTION_SCORE_HINT: Mapping[str, int] = {
    "strong_buy": 90,
    "buy": 75,
    "hold": 50,
    "watch": 45,
    "sell": 25,
    "strong_sell": 10,
}
_MAX_CODES = 200
_STOCK_CODE_RE = re.compile(r"^[A-Za-z0-9^][A-Za-z0-9.^_-]{0,15}$")


class WatchlistScoreService:
    """Aggregate a versioned, explainable score without triggering an LLM."""

    def __init__(
        self,
        *,
        db_manager: Optional[DatabaseManager] = None,
        analysis_loader: Optional[Callable[[Sequence[str]], Mapping[str, Any]]] = None,
        signal_loader: Optional[Callable[[Sequence[str]], Mapping[str, Any]]] = None,
        clock: Optional[Callable[[], datetime]] = None,
        analysis_timezone: Optional[tzinfo] = None,
    ) -> None:
        self._db_manager = db_manager
        self._analysis_loader = analysis_loader
        self._signal_loader = signal_loader
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._analysis_timezone = analysis_timezone

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
        sort_mode = self._normalize_sort(sort)
        ordered_codes = self._normalize_input_codes(stock_codes)
        if not ordered_codes:
            return self._empty_payload(sort_mode)

        candidate_to_key, code_to_key = self._query_identity_plan(ordered_codes)
        query_codes = list(candidate_to_key)
        analyses, analysis_queries, analysis_rows = self._load_latest_analyses(
            query_codes,
            candidate_to_key,
        )
        signals, signal_queries, signal_rows = self._load_latest_active_signals(
            query_codes,
            candidate_to_key,
            analyses,
        )

        items = [
            self._build_item(
                stock_code=code,
                analysis=analyses.get(code_to_key[code]),
                signal=signals.get(code_to_key[code]),
            )
            for code in ordered_codes
        ]
        return {
            "formula_version": FORMULA_VERSION,
            "scoring_mode": SCORING_MODE_AGGREGATE_EXISTING,
            "sort": sort_mode,
            "items": self.order_items(items, sort_mode=sort_mode, input_codes=ordered_codes),
            "query_count": {"analysis": analysis_queries, "signals": signal_queries},
            "source_rows": {"analysis": analysis_rows, "signals": signal_rows},
            "disclaimer_key": "watchlist_score.disclaimer",
        }

    @staticmethod
    def order_items(
        items: Sequence[Mapping[str, Any]],
        *,
        sort_mode: str = SORT_MANUAL,
        input_codes: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        mode = WatchlistScoreService._normalize_sort(sort_mode)
        rows = [dict(item) for item in items]
        manual_index = {
            str(code): index for index, code in enumerate(input_codes or ())
        }
        if mode == SORT_MANUAL:
            if input_codes is not None:
                rows.sort(key=lambda row: manual_index.get(str(row.get("stock_code")), len(manual_index)))
            return rows

        descending = mode == SORT_SCORE_DESC

        def sort_key(row: Mapping[str, Any]) -> tuple[int, float, int]:
            scored = 0 if row.get("status") == SCORE_STATUS_SCORED else 1
            raw_score = row.get("score")
            numeric = float(raw_score) if isinstance(raw_score, (int, float)) else 0.0
            score_key = -numeric if descending else numeric
            return (
                scored,
                score_key if scored == 0 else 0.0,
                manual_index.get(str(row.get("stock_code")), len(manual_index)),
            )

        rows.sort(key=sort_key)
        return rows

    def _load_latest_analyses(
        self,
        query_codes: Sequence[str],
        candidate_to_key: Mapping[str, str],
    ) -> tuple[Dict[str, Any], int, int]:
        if self._analysis_loader is not None:
            loaded = dict(self._analysis_loader(query_codes) or {})
            rekeyed = self._rekey_loaded(loaded)
            return rekeyed, 1, len(rekeyed)
        if not query_codes:
            return {}, 0, 0

        identity_case = case(candidate_to_key, value=AnalysisHistory.code)
        ranked = (
            select(
                AnalysisHistory.id.label("row_id"),
                identity_case.label("identity_key"),
                func.row_number().over(
                    partition_by=identity_case,
                    order_by=(desc(AnalysisHistory.created_at), desc(AnalysisHistory.id)),
                ).label("row_rank"),
            )
            .where(AnalysisHistory.code.in_(list(query_codes)))
            .subquery()
        )
        with self.db.get_session() as session:
            rows = session.execute(
                select(AnalysisHistory, ranked.c.identity_key)
                .join(ranked, AnalysisHistory.id == ranked.c.row_id)
                .where(ranked.c.row_rank == 1)
            ).all()
        result = {str(identity_key): row for row, identity_key in rows}
        return result, 1, len(rows)

    def _load_latest_active_signals(
        self,
        query_codes: Sequence[str],
        candidate_to_key: Mapping[str, str],
        analyses: Mapping[str, Any],
    ) -> tuple[Dict[str, Any], int, int]:
        if self._signal_loader is not None:
            loaded = dict(self._signal_loader(query_codes) or {})
            rekeyed = self._rekey_loaded(loaded)
            return rekeyed, 1, len(rekeyed)
        if not query_codes:
            return {}, 0, 0

        now = self._now_utc()
        # Use the canonical lifecycle authority before selecting active rows.
        DecisionSignalRepository(self.db).expire_due_signals(now=now)
        now_naive = to_utc_naive_datetime(now)
        identity_case = case(candidate_to_key, value=DecisionSignalRecord.stock_code)
        report_by_candidate = {
            candidate: self._positive_int(getattr(analyses.get(identity_key), "id", None))
            for candidate, identity_key in candidate_to_key.items()
        }
        report_by_candidate = {
            candidate: report_id
            for candidate, report_id in report_by_candidate.items()
            if report_id is not None
        }
        if not report_by_candidate:
            return {}, 1, 0
        report_case = case(report_by_candidate, value=DecisionSignalRecord.stock_code)
        ranked = (
            select(
                DecisionSignalRecord.id.label("row_id"),
                identity_case.label("identity_key"),
                func.row_number().over(
                    partition_by=identity_case,
                    order_by=(
                        desc(DecisionSignalRecord.created_at),
                        desc(DecisionSignalRecord.id),
                    ),
                ).label("row_rank"),
            )
            .where(
                DecisionSignalRecord.status == "active",
                DecisionSignalRecord.source_type == "analysis",
                DecisionSignalRecord.stock_code.in_(list(query_codes)),
                DecisionSignalRecord.source_report_id == report_case,
                or_(
                    DecisionSignalRecord.expires_at.is_(None),
                    DecisionSignalRecord.expires_at > now_naive,
                ),
            )
            .subquery()
        )
        with self.db.get_session() as session:
            rows = session.execute(
                select(DecisionSignalRecord, ranked.c.identity_key)
                .join(ranked, DecisionSignalRecord.id == ranked.c.row_id)
                .where(ranked.c.row_rank == 1)
            ).all()
        result = {str(identity_key): row for row, identity_key in rows}
        return result, 1, len(rows)

    def _build_item(self, *, stock_code: str, analysis: Any, signal: Any) -> Dict[str, Any]:
        if analysis is None:
            return self._unanalyzed_item(stock_code)

        analysis_at = self._analysis_datetime(getattr(analysis, "created_at", None))
        analysis_id = self._positive_int(getattr(analysis, "id", None))
        base = {
            "stock_code": stock_code,
            "as_of": analysis_at,
            "age_days": self._age_days(analysis_at),
            "analysis_id": analysis_id,
            "operation_advice": self._optional_text(getattr(analysis, "operation_advice", None), 64),
            "freshness": self._freshness_label(analysis_at),
        }
        sentiment = self._finite_number(getattr(analysis, "sentiment_score", None), 0.0, 100.0)
        if sentiment is None:
            return {
                **base,
                "status": SCORE_STATUS_UNANALYZED,
                "score": None,
                "factors": [self._analysis_factor(analysis, analysis_at, "ignored", "invalid_sentiment")],
                "degraded_reasons": ["invalid_sentiment"],
            }

        factors = [self._analysis_factor(analysis, analysis_at, "applied", None)]
        degraded: List[str] = []
        signal_component: Optional[float] = None
        if signal is not None:
            signal_component, signal_factor, reason = self._evaluate_signal(
                signal,
                analysis_id=analysis_id,
            )
            factors.append(signal_factor)
            if reason:
                degraded.append(reason)

        composite = sentiment
        if signal_component is not None:
            composite = _WEIGHT_SENTIMENT * sentiment + _WEIGHT_SIGNAL * signal_component
        return {
            **base,
            "status": SCORE_STATUS_SCORED,
            "score": int(round(min(100.0, max(0.0, composite)))),
            "factors": factors,
            "degraded_reasons": degraded,
        }

    def _evaluate_signal(
        self,
        signal: Any,
        *,
        analysis_id: Optional[int],
    ) -> tuple[Optional[float], Dict[str, Any], Optional[str]]:
        reason: Optional[str] = None
        status = str(getattr(signal, "status", "active") or "").lower()
        expires_at = self._signal_datetime(getattr(signal, "expires_at", None))
        source_type = str(getattr(signal, "source_type", "") or "").lower()
        source_report_id = self._positive_int(getattr(signal, "source_report_id", None))
        action = str(getattr(signal, "action", "") or "").strip().lower()
        confidence_raw = getattr(signal, "confidence", None)

        if status != "active":
            reason = "inactive_signal"
        elif expires_at is not None and expires_at <= self._now_utc():
            reason = "expired_signal"
        elif source_type != "analysis" or analysis_id is None or source_report_id != analysis_id:
            reason = "incoherent_signal_source"
        elif action not in _ACTION_SCORE_HINT:
            reason = "unknown_signal_action"

        confidence: Optional[float] = None
        if reason is None and confidence_raw is not None:
            confidence = self._finite_number(confidence_raw, 0.0, 1.0)
            if confidence is None:
                reason = "invalid_signal_confidence"

        component: Optional[float] = None
        if reason is None:
            hint = float(_ACTION_SCORE_HINT[action])
            component = hint if confidence is None else hint * confidence + 50.0 * (1.0 - confidence)

        factor = {
            "key": "decision_signal",
            "status": "ignored" if reason else "applied",
            "value": action or "unknown",
            "params": {
                "confidence": confidence,
                "profile": self._optional_text(getattr(signal, "decision_profile", None), 24),
            },
            "reason": reason,
            "source": {
                "id": self._positive_int(getattr(signal, "id", None)),
                "source_report_id": source_report_id,
                "profile": self._optional_text(getattr(signal, "decision_profile", None), 24),
                "as_of": self._signal_datetime(getattr(signal, "created_at", None)),
                "expires_at": expires_at,
                "formula_version": FORMULA_VERSION,
            },
        }
        return component, factor, reason

    def _analysis_factor(
        self,
        analysis: Any,
        analysis_at: Optional[datetime],
        status: str,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "key": "analysis_sentiment",
            "status": status,
            "value": (
                getattr(analysis, "sentiment_score", None)
                if status == "applied"
                else None
            ),
            "params": {
                "operation_advice": self._optional_text(getattr(analysis, "operation_advice", None), 64),
                "report_type": self._optional_text(getattr(analysis, "report_type", None), 32),
            },
            "reason": reason,
            "source": {
                "id": self._positive_int(getattr(analysis, "id", None)),
                "source_report_id": self._positive_int(getattr(analysis, "id", None)),
                "profile": None,
                "as_of": analysis_at,
                "expires_at": None,
                "formula_version": FORMULA_VERSION,
            },
        }

    @staticmethod
    def _normalize_sort(sort: Optional[str]) -> str:
        value = str(sort or SORT_MANUAL).strip().lower()
        if value not in ALLOWED_SORT_MODES:
            raise ValueError("Unsupported watchlist score sort mode")
        return value

    @classmethod
    def _normalize_input_codes(cls, stock_codes: Optional[Sequence[str]]) -> List[str]:
        if not stock_codes:
            return []
        if len(stock_codes) > _MAX_CODES:
            raise ValueError("stock_codes must contain at most 200 symbols")
        ordered: List[str] = []
        seen: set[str] = set()
        for raw in stock_codes:
            code = str(raw or "").strip().upper()
            if not _STOCK_CODE_RE.fullmatch(code):
                raise ValueError("stock_codes contains an invalid symbol")
            identity = resolve_daily_stock_identity(code)
            if identity is None:
                raise ValueError("stock_codes contains an unsupported symbol")
            key = cls._identity_key_from_resolved(identity.market, identity.normalized_code)
            if key in seen:
                raise ValueError("stock_codes must not contain duplicate market identities")
            seen.add(key)
            ordered.append(code)
        return ordered

    @classmethod
    def _query_identity_plan(
        cls,
        codes: Sequence[str],
    ) -> tuple[Dict[str, str], Dict[str, str]]:
        candidate_to_key: Dict[str, str] = {}
        ambiguous: set[str] = set()
        code_to_key: Dict[str, str] = {}
        for code in codes:
            identity = resolve_daily_stock_identity(code)
            if identity is None:
                raise ValueError("stock_codes contains an unsupported symbol")
            key = cls._identity_key_from_resolved(identity.market, identity.normalized_code)
            code_to_key[code] = key
            for candidate in identity.code_candidates:
                normalized_candidate = str(candidate).strip().upper()
                existing = candidate_to_key.get(normalized_candidate)
                if existing is not None and existing != key:
                    ambiguous.add(normalized_candidate)
                else:
                    candidate_to_key[normalized_candidate] = key
        for candidate in ambiguous:
            candidate_to_key.pop(candidate, None)
        return candidate_to_key, code_to_key

    @staticmethod
    def _identity_key_from_resolved(market: str, normalized_code: str) -> str:
        return f"{market}:{normalized_code}"

    @classmethod
    def _identity_key(cls, code: str) -> str:
        identity = resolve_daily_stock_identity(code)
        if identity is None:
            return str(code or "").strip().upper()
        return cls._identity_key_from_resolved(identity.market, identity.normalized_code)

    @classmethod
    def _rekey_loaded(cls, loaded: Mapping[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for raw_key, value in loaded.items():
            key = cls._identity_key(str(raw_key))
            result.setdefault(key, value)
        return result

    def _now_utc(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _analysis_datetime(self, value: Any) -> Optional[datetime]:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(timezone.utc)
        if self._analysis_timezone is not None:
            return value.replace(tzinfo=self._analysis_timezone).astimezone(timezone.utc)
        try:
            return value.astimezone(timezone.utc)
        except (OverflowError, OSError):
            return value.replace(tzinfo=timezone.utc)

    @staticmethod
    def _signal_datetime(value: Any) -> Optional[datetime]:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _age_days(self, created_at: Optional[datetime]) -> Optional[int]:
        if created_at is None:
            return None
        seconds = (self._now_utc() - created_at).total_seconds()
        return max(0, int(seconds // 86400))

    def _freshness_label(self, created_at: Optional[datetime]) -> str:
        age = self._age_days(created_at)
        if age is None:
            return "unknown"
        if age == 0:
            return "today"
        if age <= 3:
            return "recent"
        if age <= 7:
            return "stale_week"
        return "stale"

    @staticmethod
    def _finite_number(value: Any, minimum: float, maximum: float) -> Optional[float]:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < minimum or numeric > maximum:
            return None
        return numeric

    @staticmethod
    def _positive_int(value: Any) -> Optional[int]:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        return value

    @staticmethod
    def _optional_text(value: Any, max_length: int) -> Optional[str]:
        if value in (None, ""):
            return None
        return str(value)[:max_length]

    @staticmethod
    def _unanalyzed_item(stock_code: str) -> Dict[str, Any]:
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
            "degraded_reasons": [],
        }

    @staticmethod
    def _empty_payload(sort_mode: str) -> Dict[str, Any]:
        return {
            "formula_version": FORMULA_VERSION,
            "scoring_mode": SCORING_MODE_AGGREGATE_EXISTING,
            "sort": sort_mode,
            "items": [],
            "query_count": {"analysis": 0, "signals": 0},
            "source_rows": {"analysis": 0, "signals": 0},
            "disclaimer_key": "watchlist_score.disclaimer",
        }
