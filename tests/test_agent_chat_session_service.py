# -*- coding: utf-8 -*-
"""Agent Chat session service tests."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.services.agent_chat_session_service import AgentChatSessionService
from src.storage import DatabaseManager


@pytest.fixture(autouse=True)
def _reset_database_singleton():
    DatabaseManager.reset_instance()
    yield
    DatabaseManager.reset_instance()


def test_skill_selection_distinguishes_inherit_clear_and_explicit() -> None:
    db = DatabaseManager(db_url="sqlite:///:memory:")
    service = AgentChatSessionService(db)
    config = SimpleNamespace()

    new_selection = service.resolve_skill_selection(config, "new-session", None)
    assert new_selection.effective_skill_ids is None
    assert new_selection.selected_skill_ids_update is None

    db.save_conversation_user_turn(
        "saved-session",
        "question",
        ["technical", "risk"],
    )
    inherited = service.resolve_skill_selection(config, "saved-session", None)
    assert inherited.effective_skill_ids == ["technical", "risk"]
    assert inherited.selected_skill_ids_update is None

    cleared = service.resolve_skill_selection(config, "saved-session", [])
    assert cleared.effective_skill_ids == []
    assert cleared.selected_skill_ids_update == []

    with patch(
        "src.services.agent_chat_session_service.normalize_requested_skill_ids",
        return_value=["technical"],
    ) as normalize:
        explicit = service.resolve_skill_selection(
            config,
            "saved-session",
            [" technical ", "technical", "unknown"],
        )

    assert explicit.effective_skill_ids == ["technical"]
    assert explicit.selected_skill_ids_update == ["technical"]
    normalize.assert_called_once_with(
        config,
        [" technical ", "technical", "unknown"],
    )


def test_all_invalid_nonempty_selection_inherits_without_clearing_state() -> None:
    db = DatabaseManager(db_url="sqlite:///:memory:")
    service = AgentChatSessionService(db)
    config = SimpleNamespace()
    db.save_conversation_user_turn(
        "saved-session",
        "first question",
        ["technical"],
    )

    with patch(
        "src.services.agent_chat_session_service.normalize_requested_skill_ids",
        return_value=[],
    ):
        inherited = service.resolve_skill_selection(
            config,
            "saved-session",
            ["old_technical"],
        )

    assert inherited.effective_skill_ids == ["technical"]
    assert inherited.selected_skill_ids_update is None

    db.save_conversation_user_turn(
        "saved-session",
        "follow-up",
        inherited.selected_skill_ids_update,
    )
    assert db.get_conversation_session_selected_skill_ids("saved-session") == [
        "technical"
    ]


def test_all_invalid_nonempty_selection_uses_implicit_default_without_state() -> None:
    db = DatabaseManager(db_url="sqlite:///:memory:")
    service = AgentChatSessionService(db)

    with patch(
        "src.services.agent_chat_session_service.normalize_requested_skill_ids",
        return_value=[],
    ):
        inherited = service.resolve_skill_selection(
            SimpleNamespace(),
            "new-session",
            ["unknown"],
        )

    assert inherited.effective_skill_ids is None
    assert inherited.selected_skill_ids_update is None
    assert db.get_conversation_session_selected_skill_ids("new-session") is None


def test_session_detail_preserves_missing_persisted_state() -> None:
    db = DatabaseManager(db_url="sqlite:///:memory:")
    service = AgentChatSessionService(db)
    session_id = "legacy-service-session"
    db.save_conversation_message(session_id, "user", "legacy question")

    detail = service.get_session_detail(
        session_id,
        limit=100,
    )

    assert [message["content"] for message in detail.messages] == ["legacy question"]
    assert detail.selected_skill_ids is None
    assert db.get_conversation_session_selected_skill_ids(session_id) is None


def test_research_turn_is_persisted_in_chat_session_history() -> None:
    db = DatabaseManager(db_url="sqlite:///:memory:")
    service = AgentChatSessionService(db)

    service.record_research_start(
        session_id="research-session",
        question="What is the moat?",
        stock_code="AAPL",
        turn_id="research-turn-1",
    )
    service.record_research_success(
        session_id="research-session",
        content="The research report.",
    )

    sessions = service.list_sessions(limit=10, user_id=None)
    detail = service.get_session_detail("research-session", limit=100)

    assert sessions[0]["session_id"] == "research-session"
    assert sessions[0]["title"] == "What is the moat?"
    assert sessions[0]["message_count"] == 2
    assert [(message["role"], message["content"]) for message in detail.messages] == [
        ("user", "What is the moat?"),
        ("assistant", "The research report."),
    ]
    assert detail.messages[0]["turn_id"] == "research-turn-1"


def test_research_failure_is_exposed_as_a_stable_history_error() -> None:
    db = DatabaseManager(db_url="sqlite:///:memory:")
    service = AgentChatSessionService(db)

    service.record_research_start(
        session_id="failed-research-session",
        question="Research this failure",
        stock_code=None,
        turn_id="research-turn-failed",
    )
    service.record_research_failure(session_id="failed-research-session")

    detail = service.get_session_detail("failed-research-session", limit=100)

    assert detail.messages[1]["content"] == "Agent research failed"
    assert detail.messages[1]["error"] == "agent_research_failed"
    assert detail.messages[1]["params"] == {}
