# -*- coding: utf-8 -*-
"""Per-symbol research timeline aggregation (runs, chat, signals, hypotheses).

Merges bounded slices from independent sources with a stable cursor so callers
never need a full-table load. Hypothesis workspace (#1130) is optional: when the
storage/service surface is absent the source reports ``unavailable`` rather than
inventing empty success for a capability that is not shipped.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import and_, desc, or_, select

from src.storage import (
    AnalysisHistory,
    ConversationMessage,
    DatabaseManager,
    DecisionSignalRecord,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

RESEARCH_TIMELINE_KINDS = frozenset(
    {"analysis_run", "chat", "signal", "hypothesis"}
)
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_CURSOR_LENGTH = 512
_CURSOR_VERSION = 1


class ResearchTimelineValidationError(ValueError):
    """Caller-supplied stock code or cursor failed validation."""

    def __init__(self, message: str, *, error_code: str = "validation_error") -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class ResearchTimelineNode:
    """One ordered research event for a single symbol."""

    id: str
    kind: str
    occurred_at: str
    title: str
    summary: Optional[str]
    direction: Optional[str]
    confidence: Optional[float]
    status: Optional[str]
    link: Dict[str, Any]
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "occurred_at": self.occurred_at,
            "title": self.title,
            "summary": self.summary,
            "direction": self.direction,
            "confidence": self.confidence,
            "status": self.status,
            "link": dict(self.link),
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class ResearchTimelinePage:
    """Cursor page of research timeline nodes plus per-source honesty flags."""

    stock_code: str
    items: List[ResearchTimelineNode]
    next_cursor: Optional[str]
    has_more: bool
    limit: int
    sources: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "items": [item.to_dict() for item in self.items],
            "next_cursor": self.next_cursor,
            "has_more": self.has_more,
            "limit": self.limit,
            "sources": dict(self.sources),
        }


class ResearchTimelineService:
    """Aggregate per-symbol research activity without full multi-source scans."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    def list_timeline(
        self,
        stock_code: str,
        *,
        cursor: Optional[str] = None,
        limit: int = DEFAULT_LIMIT,
        kinds: Optional[Sequence[str]] = None,
    ) -> ResearchTimelinePage:
        display_code = self._normalize_display_code(stock_code)
        code_candidates = self._code_filter_candidates(display_code)
        if not code_candidates:
            code_candidates = [display_code]

        safe_limit = max(1, min(int(limit), MAX_LIMIT))
        # Overscan one extra row per source so has_more does not false-positive
        # when a source returns exactly `limit` and is exhausted.
        fetch_limit = safe_limit + 1
        kind_filter = self._normalize_kinds(kinds)
        cursor_key = self._decode_cursor(cursor) if cursor else None

        sources: Dict[str, str] = {
            "analysis_run": "empty",
            "chat": "empty",
            "signal": "empty",
            "hypothesis": "unavailable",
        }
        candidates: List[ResearchTimelineNode] = []
        source_overscan: Dict[str, bool] = {
            "analysis_run": False,
            "chat": False,
            "signal": False,
            "hypothesis": False,
        }

        if "analysis_run" in kind_filter:
            nodes, status = self._load_analysis_nodes(
                code_candidates=code_candidates,
                display_code=display_code,
                cursor_key=cursor_key,
                limit=fetch_limit,
            )
            sources["analysis_run"] = status
            source_overscan["analysis_run"] = len(nodes) >= fetch_limit
            candidates.extend(nodes)

        if "chat" in kind_filter:
            nodes, status = self._load_chat_nodes(
                code_candidates=code_candidates,
                display_code=display_code,
                cursor_key=cursor_key,
                limit=fetch_limit,
            )
            sources["chat"] = status
            source_overscan["chat"] = len(nodes) >= fetch_limit
            candidates.extend(nodes)

        if "signal" in kind_filter:
            nodes, status = self._load_signal_nodes(
                code_candidates=code_candidates,
                display_code=display_code,
                cursor_key=cursor_key,
                limit=fetch_limit,
            )
            sources["signal"] = status
            source_overscan["signal"] = len(nodes) >= fetch_limit
            candidates.extend(nodes)

        if "hypothesis" in kind_filter:
            nodes, status = self._load_hypothesis_nodes(
                code_candidates=code_candidates,
                display_code=display_code,
                cursor_key=cursor_key,
                limit=fetch_limit,
            )
            sources["hypothesis"] = status
            source_overscan["hypothesis"] = len(nodes) >= fetch_limit
            candidates.extend(nodes)

        ordered = sorted(candidates, key=self._node_sort_key, reverse=True)
        page_items = ordered[:safe_limit]
        has_more = len(ordered) > safe_limit or any(
            source_overscan.get(kind) for kind in kind_filter
        )
        next_cursor = (
            self._encode_cursor(page_items[-1])
            if has_more and page_items
            else None
        )
        return ResearchTimelinePage(
            stock_code=display_code,
            items=page_items,
            next_cursor=next_cursor,
            has_more=has_more,
            limit=safe_limit,
            sources=sources,
        )

    def _normalize_display_code(self, stock_code: str) -> str:
        from src.services.history_service import HistoryService
        from src.services.stock_code_utils import canonicalize_analysis_stock_code

        raw = str(stock_code or "").strip()
        if not raw:
            raise ResearchTimelineValidationError(
                "Stock code is required",
                error_code="empty_stock_code",
            )
        canonical = canonicalize_analysis_stock_code(raw)
        if canonical is None:
            raise ResearchTimelineValidationError(
                f"'{raw}' is not a valid stock code format",
                error_code="invalid_stock_code",
            )
        return HistoryService._display_stock_code(canonical)

    @staticmethod
    def _code_filter_candidates(stock_code: str) -> List[str]:
        from src.services.history_service import HistoryService

        return HistoryService._history_code_filter_candidates(stock_code)

    @staticmethod
    def _normalize_kinds(kinds: Optional[Sequence[str]]) -> frozenset[str]:
        if not kinds:
            return RESEARCH_TIMELINE_KINDS
        selected = {
            str(kind).strip().lower()
            for kind in kinds
            if str(kind or "").strip()
        }
        unknown = selected - RESEARCH_TIMELINE_KINDS
        if unknown:
            raise ResearchTimelineValidationError(
                f"Unsupported timeline kinds: {', '.join(sorted(unknown))}",
                error_code="invalid_kind",
            )
        return frozenset(selected) if selected else RESEARCH_TIMELINE_KINDS

    def _load_analysis_nodes(
        self,
        *,
        code_candidates: Sequence[str],
        display_code: str,
        cursor_key: Optional[Tuple[datetime, str]],
        limit: int,
    ) -> Tuple[List[ResearchTimelineNode], str]:
        try:
            with self.db.get_session() as session:
                conditions = [AnalysisHistory.code.in_(list(code_candidates))]
                if cursor_key is not None:
                    conditions.append(
                        self._sql_before_cursor(
                            AnalysisHistory.created_at,
                            AnalysisHistory.id,
                            cursor_key,
                            kind="analysis_run",
                        )
                    )
                stmt = (
                    select(AnalysisHistory)
                    .where(and_(*conditions))
                    .order_by(desc(AnalysisHistory.created_at), desc(AnalysisHistory.id))
                    .limit(limit)
                )
                rows = list(session.execute(stmt).scalars().all())
        except Exception as exc:
            log_safe_exception(
                logger,
                "Research timeline analysis query failed",
                exc,
                error_code="research_timeline_analysis_failed",
                context={"stock_code": display_code},
            )
            return [], "error"

        if not rows:
            return [], "empty"

        nodes: List[ResearchTimelineNode] = []
        for row in rows:
            record_id = int(row.id)
            node_id = f"analysis_run:{record_id}"
            occurred = self._normalize_datetime(row.created_at)
            if cursor_key is not None and not self._is_before_cursor(
                (occurred, node_id), cursor_key
            ):
                continue
            direction = self._first_text(row.trend_prediction, row.operation_advice)
            confidence = self._clamp_unit_interval(
                self._confidence_from_sentiment(row.sentiment_score)
            )
            summary = self._first_text(row.analysis_summary, row.operation_advice)
            title = self._first_text(row.operation_advice, row.trend_prediction) or "Analysis run"
            nodes.append(
                ResearchTimelineNode(
                    id=node_id,
                    kind="analysis_run",
                    occurred_at=occurred.isoformat(),
                    title=title,
                    summary=summary,
                    direction=direction,
                    confidence=confidence,
                    status=None,
                    link={
                        "type": "analysis_history",
                        "record_id": record_id,
                        "query_id": row.query_id,
                        "stock_code": display_code,
                    },
                    meta={
                        "report_type": row.report_type,
                        "sentiment_score": row.sentiment_score,
                        "operation_advice": row.operation_advice,
                        "trend_prediction": row.trend_prediction,
                        "stock_name": row.name,
                    },
                )
            )
        return nodes, "ok" if nodes else "empty"

    def _load_chat_nodes(
        self,
        *,
        code_candidates: Sequence[str],
        display_code: str,
        cursor_key: Optional[Tuple[datetime, str]],
        limit: int,
    ) -> Tuple[List[ResearchTimelineNode], str]:
        patterns = self._chat_context_patterns(code_candidates)
        if not patterns:
            return [], "empty"
        try:
            with self.db.get_session() as session:
                pattern_clause = or_(
                    *[ConversationMessage.context_json.contains(pattern) for pattern in patterns]
                )
                conditions = [
                    ConversationMessage.role == "user",
                    ConversationMessage.context_json.is_not(None),
                    pattern_clause,
                ]
                if cursor_key is not None:
                    conditions.append(
                        self._sql_before_cursor(
                            ConversationMessage.created_at,
                            ConversationMessage.id,
                            cursor_key,
                            kind="chat",
                        )
                    )
                stmt = (
                    select(ConversationMessage)
                    .where(and_(*conditions))
                    .order_by(
                        desc(ConversationMessage.created_at),
                        desc(ConversationMessage.id),
                    )
                    .limit(limit)
                )
                rows = list(session.execute(stmt).scalars().all())
        except Exception as exc:
            log_safe_exception(
                logger,
                "Research timeline chat query failed",
                exc,
                error_code="research_timeline_chat_failed",
                context={"stock_code": display_code},
            )
            return [], "error"

        if not rows:
            return [], "empty"

        nodes: List[ResearchTimelineNode] = []
        for row in rows:
            context = self._load_json_object(row.context_json)
            if not self._context_matches_stock(context, code_candidates):
                continue
            message_id = int(row.id)
            node_id = f"chat:{message_id}"
            occurred = self._normalize_datetime(row.created_at)
            if cursor_key is not None and not self._is_before_cursor(
                (occurred, node_id), cursor_key
            ):
                continue
            content = " ".join(str(row.content or "").split())
            summary = content[:240] + ("…" if len(content) > 240 else "") if content else None
            title = "Chat turn"
            if context and context.get("agent_mode") == "research":
                title = "Deep research chat"
            nodes.append(
                ResearchTimelineNode(
                    id=node_id,
                    kind="chat",
                    occurred_at=occurred.isoformat(),
                    title=title,
                    summary=summary,
                    direction=None,
                    confidence=None,
                    status=None,
                    link={
                        "type": "chat_session",
                        "session_id": row.session_id,
                        "message_id": message_id,
                        "turn_id": row.turn_id,
                        "stock_code": display_code,
                    },
                    meta={
                        "session_id": row.session_id,
                        "turn_id": row.turn_id,
                        "agent_mode": (
                            context.get("agent_mode") if isinstance(context, dict) else None
                        ),
                    },
                )
            )
        return nodes, "ok" if nodes else "empty"

    def _load_signal_nodes(
        self,
        *,
        code_candidates: Sequence[str],
        display_code: str,
        cursor_key: Optional[Tuple[datetime, str]],
        limit: int,
    ) -> Tuple[List[ResearchTimelineNode], str]:
        try:
            with self.db.get_session() as session:
                conditions = [DecisionSignalRecord.stock_code.in_(list(code_candidates))]
                if cursor_key is not None:
                    conditions.append(
                        self._sql_before_cursor(
                            DecisionSignalRecord.created_at,
                            DecisionSignalRecord.id,
                            cursor_key,
                            kind="signal",
                        )
                    )
                stmt = (
                    select(DecisionSignalRecord)
                    .where(and_(*conditions))
                    .order_by(
                        desc(DecisionSignalRecord.created_at),
                        desc(DecisionSignalRecord.id),
                    )
                    .limit(limit)
                )
                rows = list(session.execute(stmt).scalars().all())
        except Exception as exc:
            log_safe_exception(
                logger,
                "Research timeline signal query failed",
                exc,
                error_code="research_timeline_signal_failed",
                context={"stock_code": display_code},
            )
            return [], "error"

        if not rows:
            return [], "empty"

        nodes: List[ResearchTimelineNode] = []
        for row in rows:
            signal_id = int(row.id)
            node_id = f"signal:{signal_id}"
            occurred = self._normalize_datetime(row.created_at)
            if cursor_key is not None and not self._is_before_cursor(
                (occurred, node_id), cursor_key
            ):
                continue
            action = self._first_text(row.action_label, row.action)
            title = f"Signal · {action}" if action else "Decision signal"
            confidence = self._clamp_unit_interval(self._optional_float(row.confidence))
            nodes.append(
                ResearchTimelineNode(
                    id=node_id,
                    kind="signal",
                    occurred_at=occurred.isoformat(),
                    title=title,
                    summary=self._first_text(row.reason, row.risk_summary),
                    direction=action,
                    confidence=confidence,
                    status=row.status,
                    link={
                        "type": "decision_signal",
                        "signal_id": signal_id,
                        "stock_code": display_code,
                        "source_report_id": row.source_report_id,
                    },
                    meta={
                        "action": row.action,
                        "action_label": row.action_label,
                        "horizon": row.horizon,
                        "market": row.market,
                        "status": row.status,
                        "source_type": row.source_type,
                    },
                )
            )
        return nodes, "ok" if nodes else "empty"

    def _load_hypothesis_nodes(
        self,
        *,
        code_candidates: Sequence[str],
        display_code: str,
        cursor_key: Optional[Tuple[datetime, str]],
        limit: int,
    ) -> Tuple[List[ResearchTimelineNode], str]:
        """Optional #1130 feed. Absent workspace → unavailable (not a fake empty)."""
        try:
            from src.services import hypothesis_service as hypothesis_module  # type: ignore
        except Exception:
            return [], "unavailable"

        list_fn = getattr(hypothesis_module, "list_hypothesis_timeline_nodes", None)
        if not callable(list_fn):
            service_cls = getattr(hypothesis_module, "HypothesisService", None)
            if service_cls is None:
                return [], "unavailable"
            try:
                service = service_cls(self.db)
                list_fn = getattr(service, "list_timeline_nodes", None)
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "Hypothesis timeline service init failed",
                    exc,
                    error_code="research_timeline_hypothesis_failed",
                    context={"stock_code": display_code},
                )
                return [], "error"
            if not callable(list_fn):
                return [], "unavailable"

        call_kwargs = {
            "stock_code": display_code,
            "code_candidates": list(code_candidates) if code_candidates else [display_code],
            "cursor_key": cursor_key,
            "limit": limit,
        }
        try:
            raw_nodes = list_fn(**call_kwargs)
        except TypeError:
            try:
                raw_nodes = list_fn(display_code, limit=limit)
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "Hypothesis timeline query failed",
                    exc,
                    error_code="research_timeline_hypothesis_failed",
                    context={"stock_code": display_code},
                )
                return [], "error"
        except Exception as exc:
            log_safe_exception(
                logger,
                "Hypothesis timeline query failed",
                exc,
                error_code="research_timeline_hypothesis_failed",
                context={"stock_code": display_code},
            )
            return [], "error"

        nodes = self._coerce_hypothesis_nodes(raw_nodes, display_code=display_code)
        if cursor_key is not None:
            nodes = [
                node
                for node in nodes
                if self._is_before_cursor(self._node_sort_key(node), cursor_key)
            ]
        nodes = sorted(nodes, key=self._node_sort_key, reverse=True)[:limit]
        if not nodes:
            return [], "empty"
        return nodes, "ok"

    def _coerce_hypothesis_nodes(
        self,
        raw_nodes: Any,
        *,
        display_code: str,
    ) -> List[ResearchTimelineNode]:
        if not isinstance(raw_nodes, (list, tuple)):
            return []
        nodes: List[ResearchTimelineNode] = []
        for raw in raw_nodes:
            if isinstance(raw, ResearchTimelineNode):
                if raw.kind == "hypothesis":
                    nodes.append(raw)
                continue
            if not isinstance(raw, Mapping):
                continue
            node_id = str(raw.get("id") or "").strip()
            occurred_raw = raw.get("occurred_at")
            if not node_id or not occurred_raw:
                continue
            try:
                occurred = self._normalize_datetime(
                    datetime.fromisoformat(str(occurred_raw).replace("Z", "+00:00"))
                    if not isinstance(occurred_raw, datetime)
                    else occurred_raw
                )
            except ValueError:
                continue
            link = raw.get("link") if isinstance(raw.get("link"), Mapping) else {}
            meta = raw.get("meta") if isinstance(raw.get("meta"), Mapping) else {}
            nodes.append(
                ResearchTimelineNode(
                    id=node_id if node_id.startswith("hypothesis:") else f"hypothesis:{node_id}",
                    kind="hypothesis",
                    occurred_at=occurred.isoformat(),
                    title=str(raw.get("title") or "Hypothesis"),
                    summary=(
                        str(raw.get("summary")).strip()
                        if raw.get("summary") is not None
                        else None
                    ),
                    direction=(
                        str(raw.get("direction")).strip()
                        if raw.get("direction") is not None
                        else None
                    ),
                    confidence=self._clamp_unit_interval(
                        self._optional_float(raw.get("confidence"))
                    ),
                    status=(
                        str(raw.get("status")).strip()
                        if raw.get("status") is not None
                        else None
                    ),
                    link={
                        "type": "hypothesis",
                        "stock_code": display_code,
                        **{str(k): v for k, v in link.items()},
                    },
                    meta=dict(meta),
                )
            )
        return nodes

    @staticmethod
    def _chat_context_patterns(code_candidates: Sequence[str]) -> List[str]:
        patterns: List[str] = []
        for code in code_candidates:
            text = str(code or "").strip()
            if not text:
                continue
            for pattern in (
                f'"stock_code": "{text}"',
                f'"stock_code":"{text}"',
            ):
                if pattern not in patterns:
                    patterns.append(pattern)
        return patterns

    @staticmethod
    def _context_matches_stock(
        context: Optional[Mapping[str, Any]],
        code_candidates: Sequence[str],
    ) -> bool:
        if not isinstance(context, Mapping):
            return False
        raw = context.get("stock_code")
        if raw is None:
            return False
        value = str(raw).strip().upper()
        if not value:
            return False
        allowed = {str(code).strip().upper() for code in code_candidates if str(code).strip()}
        if value in allowed:
            return True
        try:
            from src.services.history_service import HistoryService

            expanded = {
                str(code).strip().upper()
                for code in HistoryService._history_code_filter_candidates(value)
            }
        except Exception:
            expanded = {value}
        return bool(expanded & allowed)

    @staticmethod
    def _load_json_object(raw: Optional[str]) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _first_text(*values: Any) -> Optional[str]:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    @staticmethod
    def _clamp_unit_interval(value: Optional[float]) -> Optional[float]:
        if value is None or value != value:
            return None
        if value < 0.0 or value > 1.0:
            return None
        return value

    @staticmethod
    def _confidence_from_sentiment(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            score = float(value)
        except (TypeError, ValueError):
            return None
        if score != score:
            return None
        if 0.0 <= score <= 1.0:
            return score
        if 0.0 <= score <= 100.0:
            return score / 100.0
        return None

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if parsed != parsed:
            return None
        # Accept unit interval or legacy 0-100 scores for cross-source compare fields.
        if 0.0 <= parsed <= 1.0:
            return parsed
        if 0.0 <= parsed <= 100.0:
            return parsed / 100.0
        return None

    @staticmethod
    def _normalize_datetime(value: Optional[datetime]) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None or value.utcoffset() is None:
            return value.astimezone().astimezone(timezone.utc)
        return value.astimezone(timezone.utc)

    def _sql_before_cursor(
        self,
        created_col: Any,
        id_col: Any,
        cursor_key: Tuple[datetime, str],
        *,
        kind: str,
    ) -> Any:
        cursor_at, cursor_id = cursor_key
        # Analysis/chat/signal timestamps are stored as server-local naive values.
        # Convert the cursor (always aware) into the same local-naive domain for SQL.
        naive_at = cursor_at.astimezone().replace(tzinfo=None)
        cursor_kind, _, cursor_raw_id = cursor_id.partition(":")
        if cursor_kind == kind and cursor_raw_id:
            try:
                numeric_id = int(cursor_raw_id)
            except ValueError:
                numeric_id = None
            if numeric_id is not None:
                return or_(
                    created_col < naive_at,
                    and_(created_col == naive_at, id_col < numeric_id),
                )
        return created_col <= naive_at

    @staticmethod
    def _is_before_cursor(
        node_key: Tuple[datetime, str],
        cursor_key: Tuple[datetime, str],
    ) -> bool:
        return node_key < cursor_key

    @staticmethod
    def _node_sort_key(node: ResearchTimelineNode) -> Tuple[datetime, str]:
        try:
            occurred = datetime.fromisoformat(node.occurred_at)
        except ValueError:
            occurred = datetime.min.replace(tzinfo=timezone.utc)
        if occurred.tzinfo is None or occurred.utcoffset() is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        return occurred.astimezone(timezone.utc), node.id

    def _encode_cursor(self, node: ResearchTimelineNode) -> str:
        payload = json.dumps(
            {
                "v": _CURSOR_VERSION,
                "occurred_at": node.occurred_at,
                "id": node.id,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    def _decode_cursor(self, cursor: str) -> Tuple[datetime, str]:
        normalized = str(cursor or "").strip()
        if not normalized or len(normalized) > MAX_CURSOR_LENGTH:
            raise ResearchTimelineValidationError(
                "Invalid research timeline cursor",
                error_code="invalid_cursor",
            )
        try:
            padded = normalized + "=" * (-len(normalized) % 4)
            raw = base64.urlsafe_b64decode(padded)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("v") != _CURSOR_VERSION:
                raise ValueError("unsupported cursor version")
            node_id = str(payload.get("id") or "").strip()
            if not node_id or ":" not in node_id:
                raise ValueError("invalid cursor id")
            kind = node_id.split(":", 1)[0]
            if kind not in RESEARCH_TIMELINE_KINDS:
                raise ValueError("invalid cursor kind")
            occurred = datetime.fromisoformat(str(payload.get("occurred_at") or ""))
            if occurred.tzinfo is None or occurred.utcoffset() is None:
                raise ValueError("cursor timestamp must include an offset")
            return occurred.astimezone(timezone.utc), node_id
        except (
            binascii.Error,
            json.JSONDecodeError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            raise ResearchTimelineValidationError(
                "Invalid research timeline cursor",
                error_code="invalid_cursor",
            ) from exc
