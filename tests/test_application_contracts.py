# -*- coding: utf-8 -*-
"""Regression guards for neutral application boundary contracts."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from api.v1.schemas.run_flow import RunFlowEdge as ApiRunFlowEdge
from api.v1.schemas.run_flow import RunFlowSnapshot as ApiRunFlowSnapshot
from bot.application_context import to_analysis_request_context
from bot.models import BotMessage, ChatType, Platform
from src.core.pipeline import StockAnalysisPipeline
from src.schemas.run_flow import RunFlowEdge, RunFlowSnapshot


ROOT = Path(__file__).resolve().parents[1]
SECRET_WEBHOOK = "https://oapi.dingtalk.com/robot/sendBySession?session=secret"


def _message(**overrides) -> BotMessage:
    values = {
        "platform": "feishu",
        "message_id": "message-1",
        "user_id": "user-1",
        "user_name": "Ada",
        "chat_id": "chat-1",
        "chat_type": ChatType.PRIVATE,
        "content": "/analyze 600519",
        "raw_data": {},
    }
    values.update(overrides)
    return BotMessage(**values)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_src_does_not_import_delivery_boundary_dtos() -> None:
    violations = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        for module in _imported_modules(path):
            if module == "api.v1" or module.startswith("api.v1.") or module == "bot.models":
                violations.append(f"{path.relative_to(ROOT)} -> {module}")

    assert violations == []


def test_run_flow_api_path_reexports_the_neutral_contract() -> None:
    assert ApiRunFlowSnapshot is RunFlowSnapshot
    assert ApiRunFlowEdge is RunFlowEdge

    edge = RunFlowEdge(
        id="request_to_queue",
        **{"from": "request", "to": "queue"},
        kind="control",
        status="running",
    )
    payload = edge.model_dump(mode="json", by_alias=True)

    assert payload["from"] == "request"
    assert "from_node" not in payload


def test_bot_mapping_snapshots_provenance_and_hides_reply_credentials() -> None:
    message = _message(
        platform=Platform.FEISHU,
        raw_data={"sessionWebhook": SECRET_WEBHOOK},
    )

    context = to_analysis_request_context(message)

    assert context.requester_platform == "feishu"
    assert context.requester_user_id == "user-1"
    assert context.requester_user_name == "Ada"
    assert context.requester_chat_id == "chat-1"
    assert context.requester_message_id == "message-1"
    assert context.requester_query == "/analyze 600519"
    assert [target.kind for target in context.reply_targets] == ["dingtalk", "feishu"]
    assert context.reply_address("dingtalk") == SECRET_WEBHOOK
    assert context.reply_address("feishu") == "chat-1"
    assert SECRET_WEBHOOK not in repr(context)
    assert not hasattr(context, "raw_data")

    message.user_name = "mutated"
    message.raw_data.clear()
    assert context.requester_user_name == "Ada"
    assert context.reply_address("dingtalk") == SECRET_WEBHOOK
    with pytest.raises(FrozenInstanceError):
        context.requester_user_name = "mutated"


@pytest.mark.parametrize(
    "raw_data",
    [
        {"_session_webhook": SECRET_WEBHOOK},
        {"sessionWebhook": SECRET_WEBHOOK},
        {"session_webhook": SECRET_WEBHOOK},
        {"session_webhook_url": SECRET_WEBHOOK},
        {"headers": {"sessionWebhook": SECRET_WEBHOOK}},
    ],
)
def test_bot_mapping_preserves_dingtalk_session_webhook_shapes(raw_data) -> None:
    context = to_analysis_request_context(_message(platform="dingtalk", raw_data=raw_data))

    assert context.reply_address("dingtalk") == SECRET_WEBHOOK


def test_bot_mapping_preserves_telegram_nested_numeric_chat_id() -> None:
    context = to_analysis_request_context(
        _message(
            platform="telegram",
            chat_id="",
            raw_data={"message": {"chat": {"id": -100200300}}},
        )
    )

    assert context.reply_address("telegram") == "-100200300"


def test_bot_mapping_ignores_non_mapping_raw_payload() -> None:
    message = _message(platform="dingtalk")
    message.raw_data = []

    context = to_analysis_request_context(message)

    assert context.reply_targets == ()


def test_pipeline_persists_only_neutral_requester_provenance() -> None:
    request_context = to_analysis_request_context(
        _message(raw_data={"sessionWebhook": SECRET_WEBHOOK})
    )
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.request_context = request_context
    pipeline.query_id = "query-1"
    pipeline.query_source = pipeline._resolve_query_source()

    context = pipeline._build_query_context()

    assert context == {
        "query_id": "query-1",
        "query_source": "bot",
        "requester_platform": "feishu",
        "requester_user_id": "user-1",
        "requester_user_name": "Ada",
        "requester_chat_id": "chat-1",
        "requester_message_id": "message-1",
        "requester_query": "/analyze 600519",
    }
    assert SECRET_WEBHOOK not in repr(context)
