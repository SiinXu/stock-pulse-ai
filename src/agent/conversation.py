# -*- coding: utf-8 -*-
"""
Conversation Manager for Agent multi-turn chat.

Manages conversation sessions with TTL, storing message history and context.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.storage import get_db

logger = logging.getLogger(__name__)

MARKET_CONTEXT_KEYS = ("stock_code", "stock_name", "report_language")


def _select_market_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep only low-sensitivity fields needed to continue a stock chat."""
    source = context or {}
    return {
        key: source[key]
        for key in MARKET_CONTEXT_KEYS
        if source.get(key) not in (None, "")
    }


@dataclass
class ConversationSession:
    """A single multi-turn conversation session."""
    session_id: str
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    _context_lock: threading.RLock = field(
        default_factory=threading.RLock,
        repr=False,
        compare=False,
    )

    def add_message(self, role: str, content: str) -> int:
        """Add a message to the session history."""
        message_id = get_db().save_conversation_message(self.session_id, role, content)
        with self._context_lock:
            self.last_active = datetime.now()
        return message_id

    def update_context(self, key: str, value: Any):
        """Update session context."""
        with self._context_lock:
            self.context[key] = value
            self.last_active = datetime.now()

    def update_market_context(self, context: Optional[Dict[str, Any]]) -> None:
        """Replace cached stock identity fields for the next chat turn."""
        selected = _select_market_context(context)
        with self._context_lock:
            for key in MARKET_CONTEXT_KEYS:
                self.context.pop(key, None)
            self.context.update(selected)
            self.last_active = datetime.now()

    def get_market_context(self) -> Dict[str, Any]:
        """Rebuild the active stock context from persisted visible user turns.

        Persisted history is authoritative for symbol switches and survives a
        process restart. The in-memory cache only restores explicit request
        fields such as a report-provided stock name. An empty database history
        clears the cache, matching session deletion semantics.
        """
        messages = get_db().get_visible_conversation_messages(self.session_id)
        if not messages:
            self.update_market_context({})
            return {}

        from src.agent.stock_scope import resolve_stock_scope

        replayed: Dict[str, Any] = {}
        history_has_stock_scope = False
        for message in messages:
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, str) or not content:
                continue
            resolution = resolve_stock_scope(content, replayed)
            replayed = _select_market_context(resolution.effective_context)
            scope = resolution.stock_scope
            if scope is not None and (
                scope.allowed_stock_codes or scope.mode in {"switch", "compare"}
            ):
                history_has_stock_scope = True

        with self._context_lock:
            cached = _select_market_context(self.context)
        replayed_code = replayed.get("stock_code")
        cached_code = cached.get("stock_code")
        if replayed_code:
            if cached_code == replayed_code and cached.get("stock_name"):
                replayed["stock_name"] = cached["stock_name"]
            if cached.get("report_language"):
                replayed["report_language"] = cached["report_language"]
        elif not history_has_stock_scope:
            replayed.update(cached)
        elif cached.get("report_language"):
            replayed["report_language"] = cached["report_language"]
        self.update_market_context(replayed)
        return dict(replayed)

    def get_history(self) -> List[Dict[str, Any]]:
        """Get message history."""
        messages = get_db().get_conversation_history(self.session_id)
        return messages


class ConversationManager:
    """Manages multiple conversation sessions with TTL."""
    
    def __init__(self, ttl_minutes: int = 30):
        self._sessions: Dict[str, ConversationSession] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
        self._lock = threading.RLock()

    def get_or_create(self, session_id: str) -> ConversationSession:
        """Get an existing session or create a new one."""
        with self._lock:
            self._cleanup_expired()

            if session_id not in self._sessions:
                self._sessions[session_id] = ConversationSession(session_id=session_id)
                logger.info(f"Created new conversation session: {session_id}")
            else:
                # Update last active time
                self._sessions[session_id].last_active = datetime.now()

            return self._sessions[session_id]

    def add_message(self, session_id: str, role: str, content: str) -> int:
        """Add a message to a session."""
        session = self.get_or_create(session_id)
        return session.add_message(role, content)

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get message history for a session."""
        session = self.get_or_create(session_id)
        return session.get_history()

    def clear(self, session_id: str):
        """Clear a session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Cleared conversation session: {session_id}")
        # We don't delete from DB here to keep history, or we could add a delete method.
        # For now, just clear from memory.

    def _cleanup_expired(self):
        """Remove expired sessions."""
        with self._lock:
            now = datetime.now()
            expired = [
                sid for sid, session in self._sessions.items()
                if now - session.last_active > self.ttl
            ]
            for sid in expired:
                del self._sessions[sid]
                logger.info(f"Cleaned up expired conversation session: {sid}")


# Global instance
conversation_manager = ConversationManager()
