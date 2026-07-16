"""Canary regressions for Bot log and public-response boundaries."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.commands.analyze import AnalyzeCommand
from bot.commands.base import BotCommand
from bot.commands.history import HistoryCommand
from bot.commands.research import ResearchCommand
from bot.commands.strategies import StrategiesCommand
from bot.dispatcher import CommandDispatcher
from bot.handler import handle_webhook, handle_webhook_async
from bot.models import BotMessage, BotResponse, ChatType, WebhookResponse
from bot.platforms.dingtalk import DingtalkPlatform
from bot.platforms.dingtalk_stream import (
    AckMessage,
    DINGTALK_STREAM_PUBLIC_ERROR,
    DingtalkStreamHandler,
)
from bot.platforms.discord import DiscordPlatform
from bot.platforms.feishu_stream import FeishuReplyClient, FeishuStreamHandler


CANARY = "bot-canary-secret-c01"
PRIVATE_HOST = "private.bot.invalid"
SENSITIVE_DIAGNOSTIC = (
    f"Authorization: Bearer {CANARY} api_key={CANARY} "
    f"https://{PRIVATE_HOST}/v1?token={CANARY}"
)


def _message(content: str, *, user_name: str = "tester") -> BotMessage:
    return BotMessage(
        platform="feishu",
        message_id="message-1",
        user_id="user-1",
        user_name=user_name,
        chat_id="chat-1",
        chat_type=ChatType.PRIVATE,
        content=content,
        raw_content=content,
        mentioned=True,
        timestamp=datetime.now(),
    )


def _assert_canary_absent(text: str) -> None:
    assert CANARY not in text
    assert PRIVATE_HOST not in text


class _FailingCommand(BotCommand):
    @property
    def name(self) -> str:
        return "explode"

    @property
    def aliases(self) -> list[str]:
        return []

    @property
    def description(self) -> str:
        return "failure fixture"

    @property
    def usage(self) -> str:
        return "/explode"

    def execute(self, message: BotMessage, args: list[str]) -> BotResponse:
        raise RuntimeError(SENSITIVE_DIAGNOSTIC)


def test_dispatcher_hides_arguments_usernames_and_exception_diagnostics(caplog) -> None:
    dispatcher = CommandDispatcher()
    dispatcher.register(_FailingCommand())
    message = _message(
        f"/explode api_key={CANARY}",
        user_name=f"user-{CANARY}",
    )
    caplog.set_level(logging.DEBUG, logger="bot.dispatcher")

    sync_response = dispatcher.dispatch(message)
    async_response = asyncio.run(dispatcher.dispatch_async(message))

    assert sync_response.text == "❌ 错误：命令执行失败，请稍后重试"
    assert async_response.text == sync_response.text
    _assert_canary_absent(sync_response.text)
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    _assert_canary_absent(rendered)
    assert "argument_count=1" in rendered
    assert all(record.exc_info is None for record in caplog.records)


def test_dispatcher_does_not_log_natural_language_input_or_invalid_llm_output(caplog) -> None:
    dispatcher = CommandDispatcher()
    chat_command = MagicMock(spec=BotCommand)
    chat_command.name = "chat"
    chat_command.aliases = []
    chat_command.execute.return_value = BotResponse.text_response("ok")
    dispatcher.register(chat_command)
    message = _message(f"analyze AAPL api_key={CANARY}")
    caplog.set_level(logging.DEBUG, logger="bot.dispatcher")

    config = SimpleNamespace(agent_nl_routing=True, agent_mode=True)
    with patch("src.config.get_config", return_value=config), patch.object(
        CommandDispatcher,
        "_parse_intent_via_llm_sync",
        return_value={"intent": "chat", "codes": [], "strategy": None},
    ):
        response = dispatcher.dispatch(message)
    CommandDispatcher._parse_intent_payload(f"not-json {SENSITIVE_DIAGNOSTIC}")

    assert response.text == "ok"
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    _assert_canary_absent(rendered)
    assert "response_length=" in rendered


def test_webhook_handler_does_not_log_payload_or_message_content(caplog) -> None:
    payload = {
        "token": CANARY,
        "content": SENSITIVE_DIAGNOSTIC,
    }
    body = json.dumps(payload).encode("utf-8")
    message = _message(SENSITIVE_DIAGNOSTIC, user_name=f"user-{CANARY}")
    platform = MagicMock()
    platform.handle_webhook.return_value = (message, None)
    platform.format_response.return_value = WebhookResponse.success({"ok": True})
    dispatcher = MagicMock()
    dispatcher.dispatch.return_value = BotResponse.text_response("safe")
    dispatcher.dispatch_async = AsyncMock(return_value=BotResponse.text_response("safe"))
    caplog.set_level(logging.DEBUG, logger="bot.handler")

    with patch("src.config.get_config", return_value=SimpleNamespace(bot_enabled=True)), patch(
        "bot.handler.get_platform",
        return_value=platform,
    ), patch("bot.handler.get_dispatcher", return_value=dispatcher):
        response = handle_webhook("discord", {}, body)
        async_response = asyncio.run(handle_webhook_async("discord", {}, body))

    assert response.status_code == 200
    assert async_response.status_code == 200
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    _assert_canary_absent(rendered)
    assert f"body_bytes={len(body)}" in rendered
    assert f"content_length={len(SENSITIVE_DIAGNOSTIC)}" in rendered


def test_command_failures_return_only_stable_public_messages(caplog) -> None:
    caplog.set_level(logging.ERROR)
    message = _message("/fixture")

    analysis_service = MagicMock()
    analysis_service.submit_analysis.return_value = {
        "success": False,
        "error": SENSITIVE_DIAGNOSTIC,
    }
    with patch(
        "src.services.task_service.get_task_service",
        return_value=analysis_service,
    ):
        analysis_response = AnalyzeCommand().execute(message, ["600519"])
    analysis_service.submit_analysis.side_effect = RuntimeError(SENSITIVE_DIAGNOSTIC)
    with patch(
        "src.services.task_service.get_task_service",
        return_value=analysis_service,
    ):
        analysis_exception_response = AnalyzeCommand().execute(message, ["600519"])

    history_db = MagicMock()
    history_db.delete_conversation_session.side_effect = RuntimeError(SENSITIVE_DIAGNOSTIC)
    with patch("src.storage.get_db", return_value=history_db):
        history_response = HistoryCommand().execute(message, ["clear"])
    history_detail_db = MagicMock()
    history_detail_db.get_conversation_messages.side_effect = RuntimeError(
        SENSITIVE_DIAGNOSTIC
    )
    with patch("src.storage.get_db", return_value=history_detail_db):
        history_detail_response = HistoryCommand().execute(
            message,
            ["feishu_user-1:chat"],
        )
    history_list_db = MagicMock()
    history_list_db.get_chat_sessions.side_effect = RuntimeError(SENSITIVE_DIAGNOSTIC)
    with patch("src.storage.get_db", return_value=history_list_db):
        history_list_response = HistoryCommand().execute(message, [])

    research_agent = MagicMock()
    research_agent.research.side_effect = RuntimeError(SENSITIVE_DIAGNOSTIC)
    research_config = SimpleNamespace(
        agent_mode=True,
        agent_deep_research_budget=30000,
        agent_deep_research_timeout=180,
    )
    with patch("bot.commands.research.get_config", return_value=research_config), patch(
        "src.agent.factory.get_tool_registry",
        return_value=MagicMock(),
    ), patch("src.agent.llm_adapter.LLMToolAdapter", return_value=MagicMock()), patch(
        "src.agent.research.ResearchAgent",
        return_value=research_agent,
    ):
        research_response = ResearchCommand().execute(message, [SENSITIVE_DIAGNOSTIC])

    with patch("src.config.get_config", return_value=SimpleNamespace()), patch(
        "src.agent.factory.get_skill_manager",
        side_effect=RuntimeError(SENSITIVE_DIAGNOSTIC),
    ):
        strategies_response = StrategiesCommand().execute(message, [])

    assert analysis_response.text == "❌ 错误：提交分析任务失败，请稍后重试"
    assert analysis_exception_response.text == "❌ 错误：分析失败，请稍后重试"
    assert history_response.text == "⚠️ 清除失败，请稍后重试。"
    assert history_detail_response.text == "⚠️ 获取会话详情失败，请稍后重试。"
    assert history_list_response.text == "⚠️ 获取会话列表失败，请稍后重试。"
    assert research_response.text == "❌ Research failed. Please try again later."
    assert strategies_response.text == "⚠️ 获取策略列表失败，请稍后重试。"
    for response in (
        analysis_response,
        analysis_exception_response,
        history_response,
        history_detail_response,
        history_list_response,
        research_response,
        strategies_response,
    ):
        _assert_canary_absent(response.text)
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    _assert_canary_absent(rendered)
    assert all(record.exc_info is None for record in caplog.records)


def test_stream_logs_and_dingtalk_failure_ack_hide_message_and_exception(caplog) -> None:
    message = _message(SENSITIVE_DIAGNOSTIC, user_name=f"user-{CANARY}")
    caplog.set_level(logging.INFO)

    dingtalk_handler = DingtalkStreamHandler(lambda _message: BotResponse.text_response("ok"))
    dingtalk_handler._log_incoming_message(message)
    feishu_handler = FeishuStreamHandler(
        lambda _message: BotResponse.text_response("ok"),
        MagicMock(),
    )
    try:
        feishu_handler._log_incoming_message(message)
    finally:
        feishu_handler.shutdown(wait=True)

    with patch(
        "bot.platforms.dingtalk_stream.dingtalk_stream.ChatbotMessage.from_dict",
        side_effect=RuntimeError(SENSITIVE_DIAGNOSTIC),
    ):
        status, public_error = asyncio.run(
            dingtalk_handler.create_handler().process(SimpleNamespace(data={}))
        )

    assert status == AckMessage.STATUS_SYSTEM_EXCEPTION
    assert public_error == DINGTALK_STREAM_PUBLIC_ERROR == "message_processing_failed"
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    _assert_canary_absent(rendered)
    assert f"content_length={len(SENSITIVE_DIAGNOSTIC)}" in rendered
    assert all(record.exc_info is None for record in caplog.records)


def test_platform_failure_diagnostics_do_not_log_response_bodies(caplog) -> None:
    caplog.set_level(logging.ERROR)
    message = _message("/fixture")
    response = BotResponse.text_response("safe response")

    with patch(
        "src.config.get_config",
        return_value=SimpleNamespace(
            dingtalk_app_key=None,
            dingtalk_app_secret=None,
        ),
    ):
        dingtalk = DingtalkPlatform()
    dingtalk_response = MagicMock(status_code=200)
    dingtalk_response.json.return_value = {
        "errcode": CANARY,
        "errmsg": SENSITIVE_DIAGNOSTIC,
    }
    with patch("requests.post", return_value=dingtalk_response):
        assert not dingtalk.send_by_session_webhook(
            "https://oapi.dingtalk.com/robot/sendBySession",
            response,
            message,
        )

    with patch(
        "src.config.get_config",
        return_value=SimpleNamespace(discord_interactions_public_key="00" * 32),
    ):
        discord = DiscordPlatform()
    message.raw_data = {
        "application_id": "app-1",
        "token": "interaction-token",
    }
    discord_response = MagicMock(status_code=500, text=SENSITIVE_DIAGNOSTIC)
    with patch("bot.platforms.discord.requests.patch", return_value=discord_response):
        assert not discord.send_followup(response, message)

    feishu = FeishuReplyClient.__new__(FeishuReplyClient)
    feishu._client = MagicMock()
    feishu_response = MagicMock()
    feishu_response.success.return_value = False
    feishu_response.code = CANARY
    feishu_response.msg = SENSITIVE_DIAGNOSTIC
    feishu_response.get_log_id.return_value = CANARY
    feishu._client.im.v1.message.reply.return_value = feishu_response
    assert not feishu._send_interactive_card("safe", message_id="message-1")

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    _assert_canary_absent(rendered)
