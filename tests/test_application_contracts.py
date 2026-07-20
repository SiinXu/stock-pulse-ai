# -*- coding: utf-8 -*-
"""Regression guards for neutral application boundary contracts."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from api.app import create_app
from api.v1.schemas.run_flow import RunFlowEvent as ApiRunFlowEvent
from api.v1.schemas.run_flow import RunFlowLane as ApiRunFlowLane
from api.v1.schemas.run_flow import RunFlowNode as ApiRunFlowNode
from api.v1.schemas.run_flow import RunFlowEdge as ApiRunFlowEdge
from api.v1.schemas.run_flow import RunFlowSnapshot as ApiRunFlowSnapshot
from api.v1.schemas.run_flow import RunFlowSummary as ApiRunFlowSummary
from bot.application_context import to_analysis_request_context
from bot.models import BotMessage, ChatType, Platform
from src.core.pipeline import StockAnalysisPipeline
from src.schemas.request_context import AnalysisRequestContext, NotificationReplyTarget
from src.schemas.run_flow import (
    RunFlowEdge,
    RunFlowEvent,
    RunFlowLane,
    RunFlowNode,
    RunFlowSnapshot,
    RunFlowSummary,
)


ROOT = Path(__file__).resolve().parents[1]
SECRET_WEBHOOK = "https://oapi.dingtalk.com/robot/sendBySession?session=secret"
RUN_FLOW_MODEL_PAIRS = (
    (ApiRunFlowLane, RunFlowLane),
    (ApiRunFlowNode, RunFlowNode),
    (ApiRunFlowEdge, RunFlowEdge),
    (ApiRunFlowEvent, RunFlowEvent),
    (ApiRunFlowSummary, RunFlowSummary),
    (ApiRunFlowSnapshot, RunFlowSnapshot),
)
RUN_FLOW_PATHS = (
    "/api/v1/analysis/tasks/{task_id}/flow",
    "/api/v1/history/{record_id}/flow",
)
RUN_FLOW_OPENAPI_SHA256 = (
    "14d4816b582eec9af86fede9edda8deb07e204641b4cdbccf2bf44799184faae"
)


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
            if (
                module == "api.v1"
                or module.startswith("api.v1.")
                or module == "bot"
                or module == "bot.models"
            ):
                violations.append(f"{path.relative_to(ROOT)} -> {module}")

    assert violations == []


def test_run_flow_api_path_reexports_the_neutral_contract() -> None:
    for api_model, application_model in RUN_FLOW_MODEL_PAIRS:
        assert api_model is application_model

    edge = RunFlowEdge(
        id="request_to_queue",
        **{"from": "request", "to": "queue"},
        kind="control",
        status="running",
    )
    payload = edge.model_dump(mode="json", by_alias=True)

    assert payload["from"] == "request"
    assert "from_node" not in payload


def test_run_flow_openapi_surface_is_unchanged() -> None:
    spec = create_app().openapi()
    schemas = spec["components"]["schemas"]
    surface = {
        "paths": {path: spec["paths"][path] for path in RUN_FLOW_PATHS},
        "schemas": {
            application_model.__name__: schemas[application_model.__name__]
            for _, application_model in RUN_FLOW_MODEL_PAIRS
        },
    }
    canonical = json.dumps(
        surface,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert hashlib.sha256(canonical).hexdigest() == RUN_FLOW_OPENAPI_SHA256


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
    assert [target.kind for target in context.reply_targets] == ["feishu"]
    assert context.reply_address("dingtalk") is None
    assert context.reply_address("feishu") == "chat-1"
    assert SECRET_WEBHOOK not in repr(context)
    assert not hasattr(context, "raw_data")

    message.user_name = "mutated"
    message.raw_data.clear()
    assert context.requester_user_name == "Ada"
    assert context.reply_address("dingtalk") is None
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
    assert SECRET_WEBHOOK not in repr(context)


@pytest.mark.parametrize(
    "platform,url",
    [
        ("feishu", SECRET_WEBHOOK),
        ("telegram", SECRET_WEBHOOK),
        ("dingtalk", "http://oapi.dingtalk.com/robot/sendBySession?session=secret"),
        ("dingtalk", "https://attacker.example/robot/sendBySession?session=secret"),
        ("dingtalk", "https://oapi.dingtalk.com/robot/sendBySession?session="),
        ("dingtalk", "https://oapi.dingtalk.com/robot/sendBySession/extra?session=secret"),
    ],
)
def test_bot_mapping_rejects_cross_platform_or_untrusted_dingtalk_targets(
    platform,
    url,
) -> None:
    context = to_analysis_request_context(
        _message(platform=platform, raw_data={"sessionWebhook": url})
    )

    assert context.reply_address("dingtalk") is None
    assert context.contextual_reply_only is True


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
    assert context.contextual_reply_only is False


def test_bot_mapping_rejects_blank_feishu_target_without_losing_reply_only_intent() -> None:
    context = to_analysis_request_context(
        _message(platform="feishu", chat_id="   ", raw_data={})
    )

    assert context.reply_targets == ()
    assert context.contextual_reply_only is True


def test_bot_mapping_keeps_missing_telegram_target_as_non_contextual() -> None:
    context = to_analysis_request_context(
        _message(platform="telegram", chat_id="   ", raw_data={})
    )

    assert context.reply_targets == ()
    assert context.contextual_reply_only is False


def test_request_context_rejects_blank_targets_and_freezes_mutable_input() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        NotificationReplyTarget("dingtalk", "   ")
    with pytest.raises(ValueError, match="official session endpoint"):
        NotificationReplyTarget(
            "dingtalk",
            "https://attacker.example/robot/sendBySession?session=secret",
        )

    target = NotificationReplyTarget("feishu", "chat-1")
    mutable_targets = [target]
    context = AnalysisRequestContext(reply_targets=mutable_targets)
    mutable_targets.clear()

    assert context.reply_targets == (target,)
    assert isinstance(context.reply_targets, tuple)
    assert context.contextual_reply_only is True

    with pytest.raises(TypeError, match="provenance fields must be strings"):
        AnalysisRequestContext(requester_query=[])
    with pytest.raises(TypeError, match="contextual_reply_only must be a bool"):
        AnalysisRequestContext(contextual_reply_only="yes")


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
