# -*- coding: utf-8 -*-
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

from nacl.signing import SigningKey

from bot.models import ChatType
from bot.platforms.discord import DiscordPlatform


def _make_platform(public_key: str) -> DiscordPlatform:
    with patch(
        "src.config.get_config",
        return_value=SimpleNamespace(
            discord_interactions_public_key=public_key,
        ),
    ):
        return DiscordPlatform()


def _current_timestamp() -> str:
    """Returns the current Unix timestamp string, used to generate a valid signature."""
    return str(int(time.time()))


def _sign_headers(signing_key: SigningKey, body: bytes, timestamp: str | None = None):
    if timestamp is None:
        timestamp = _current_timestamp()
    signature = signing_key.sign(timestamp.encode("utf-8") + body).signature.hex()
    return {
        "X-Signature-Ed25519": signature,
        "X-Signature-Timestamp": timestamp,
    }


def test_signed_ping_request_is_accepted():
    signing_key = SigningKey.generate()
    platform = _make_platform(signing_key.verify_key.encode().hex())
    payload = {"type": 1}
    body = json.dumps(payload).encode("utf-8")

    message, response = platform.handle_webhook(
        _sign_headers(signing_key, body),
        body,
        payload,
    )

    assert message is None
    assert response is not None
    assert response.status_code == 200
    assert response.body == {"type": 1}


def test_signed_interaction_request_returns_deferred_ack():
    """type=2 Interaction should return type 5 Delay ACK, Still parsed out simultaneously BotMessage."""
    signing_key = SigningKey.generate()
    platform = _make_platform(signing_key.verify_key.encode().hex())
    payload = {
        "id": "interaction-1",
        "type": 2,
        "channel_id": "channel-1",
        "guild_id": "guild-1",
        "application_id": "app-123",
        "token": "interaction-token",
        "member": {
            "user": {
                "id": "user-1",
                "username": "tester",
            }
        },
        "data": {
            "name": "analyze",
            "options": [
                {"name": "stock_code", "value": "600519"},
            ],
        },
    }
    body = json.dumps(payload).encode("utf-8")

    message, response = platform.handle_webhook(
        _sign_headers(signing_key, body),
        body,
        payload,
    )

    # Should return type 5 delay ACK
    assert response is not None
    assert response.status_code == 200
    assert response.body == {"type": 5}

    # Still parse out the message
    assert message is not None
    assert message.platform == "discord"
    assert message.chat_id == "channel-1"
    assert message.chat_type == ChatType.GROUP
    assert message.user_id == "user-1"
    assert message.user_name == "tester"
    assert message.content == "/analyze 600519"
    # follow-up: Required fields are in raw_data
    assert message.raw_data.get("application_id") == "app-123"
    assert message.raw_data.get("token") == "interaction-token"


def test_invalid_signature_ping_request_is_rejected_before_challenge():
    signing_key = SigningKey.generate()
    platform = _make_platform(signing_key.verify_key.encode().hex())
    payload = {"type": 1}
    body = json.dumps(payload).encode("utf-8")
    headers = _sign_headers(signing_key, body)
    headers["X-Signature-Ed25519"] = "00" * 64

    message, response = platform.handle_webhook(headers, body, payload)

    assert message is None
    assert response is not None
    assert response.status_code == 401
    assert response.body == {"error": "Invalid Discord signature"}


def test_missing_signature_header_is_rejected():
    signing_key = SigningKey.generate()
    platform = _make_platform(signing_key.verify_key.encode().hex())
    payload = {
        "id": "interaction-2",
        "type": 2,
        "data": {"name": "help"},
    }
    body = json.dumps(payload).encode("utf-8")

    message, response = platform.handle_webhook(
        {"X-Signature-Timestamp": _current_timestamp()},
        body,
        payload,
    )

    assert message is None
    assert response is not None
    assert response.status_code == 401
    assert response.body == {"error": "Invalid Discord signature"}


def test_invalid_public_key_configuration_is_rejected():
    platform = _make_platform("not-a-hex-public-key")
    payload = {"type": 1}
    body = json.dumps(payload).encode("utf-8")

    message, response = platform.handle_webhook(
        {
            "X-Signature-Ed25519": "00" * 64,
            "X-Signature-Timestamp": _current_timestamp(),
        },
        body,
        payload,
    )

    assert message is None
    assert response is not None
    assert response.status_code == 401
    assert response.body == {"error": "Invalid Discord signature"}


def test_expired_timestamp_is_rejected():
    """Expired timestamp (outside ±5 minute window) should be rejected, preventing rate limiting attacks."""
    signing_key = SigningKey.generate()
    platform = _make_platform(signing_key.verify_key.encode().hex())
    payload = {"type": 1}
    body = json.dumps(payload).encode("utf-8")
    # Timestamp 10 minutes ago
    stale_ts = str(int(time.time()) - 600)

    message, response = platform.handle_webhook(
        _sign_headers(signing_key, body, timestamp=stale_ts),
        body,
        payload,
    )

    assert message is None
    assert response is not None
    assert response.status_code == 401


def test_format_response_wraps_interaction_callback():
    """type=2 Use for interaction response Interaction Response Callback Format(type=4 + data)."""
    from bot.models import BotMessage, BotResponse, ChatType

    platform = _make_platform("00" * 32)
    message = BotMessage(
        platform="discord",
        message_id="msg-1",
        user_id="user-1",
        user_name="tester",
        chat_id="channel-1",
        chat_type=ChatType.GROUP,
        content="/analyze 600519",
        raw_data={"type": 2, "data": {"name": "analyze"}},
    )
    response = BotResponse.text_response("分析结果")

    webhook_response = platform.format_response(response, message)

    assert webhook_response.status_code == 200
    assert webhook_response.body["type"] == 4
    assert "data" in webhook_response.body
    assert webhook_response.body["data"]["content"] == "分析结果"
    assert webhook_response.body["data"]["tts"] is False


def test_send_followup_patches_original_message():
    """send_followup Respond PATCH Discord follow-up webhook."""
    from bot.models import BotMessage, BotResponse, ChatType

    platform = _make_platform("00" * 32)
    message = BotMessage(
        platform="discord",
        message_id="msg-1",
        user_id="user-1",
        user_name="tester",
        chat_id="channel-1",
        chat_type=ChatType.GROUP,
        content="/analyze 600519",
        raw_data={
            "type": 2,
            "application_id": "app-123",
            "token": "interaction-token",
        },
    )
    response = BotResponse.text_response("分析结果")

    with patch("bot.platforms.discord.requests") as mock_requests:
        mock_resp = type("R", (), {"status_code": 200, "text": "ok"})()
        mock_requests.patch.return_value = mock_resp
        result = platform.send_followup(response, message)

    assert result is True
    mock_requests.patch.assert_called_once()
    call_args = mock_requests.patch.call_args
    assert "/app-123/interaction-token/messages/@original" in call_args[0][0]
    assert call_args[1]["json"]["content"] == "分析结果"


def test_send_followup_chunks_long_content():
    """Follow-up exceeding 2000 characters should be chunked: initial PATCH, subsequent POST."""
    from bot.models import BotMessage, BotResponse, ChatType

    platform = _make_platform("00" * 32)
    message = BotMessage(
        platform="discord",
        message_id="msg-1",
        user_id="user-1",
        user_name="tester",
        chat_id="channel-1",
        chat_type=ChatType.GROUP,
        content="/analyze 600519",
        raw_data={
            "type": 2,
            "application_id": "app-123",
            "token": "interaction-token",
        },
    )
    # Generate content exceeding 2000 characters
    long_content = "A" * 3500
    response = BotResponse.text_response(long_content)

    with patch("bot.platforms.discord.requests") as mock_requests:
        mock_resp = type("R", (), {"status_code": 200, "text": "ok"})()
        mock_requests.patch.return_value = mock_resp
        mock_requests.post.return_value = mock_resp
        result = platform.send_followup(response, message)

    assert result is True
    # Use PATCH first
    mock_requests.patch.assert_called_once()
    patch_url = mock_requests.patch.call_args[0][0]
    assert "/messages/@original" in patch_url
    # Use POST for subsequent blocks.
    assert mock_requests.post.call_count >= 1
    post_url = mock_requests.post.call_args[0][0]
    assert post_url.endswith("/app-123/interaction-token")


def test_send_followup_missing_token_returns_false():
    """If the `interaction token` is missing, `send_followup` should return False."""
    from bot.models import BotMessage, BotResponse, ChatType

    platform = _make_platform("00" * 32)
    message = BotMessage(
        platform="discord",
        message_id="msg-1",
        user_id="user-1",
        user_name="tester",
        chat_id="channel-1",
        chat_type=ChatType.GROUP,
        content="/analyze 600519",
        raw_data={"type": 2},
    )
    response = BotResponse.text_response("分析结果")
    assert platform.send_followup(response, message) is False


def test_non_numeric_timestamp_is_rejected():
    """Non-numeric timestamp should be rejected."""
    signing_key = SigningKey.generate()
    platform = _make_platform(signing_key.verify_key.encode().hex())
    payload = {"type": 1}
    body = json.dumps(payload).encode("utf-8")

    message, response = platform.handle_webhook(
        _sign_headers(signing_key, body, timestamp="not-a-number"),
        body,
        payload,
    )

    assert message is None
    assert response is not None
    assert response.status_code == 401


def test_boolean_option_true_emits_name():
    """The boolean True option should output option name, instead of the literal 'true'."""
    platform = _make_platform("00" * 32)
    interaction_data = {
        "name": "analyze",
        "options": [
            {"name": "stock_code", "value": "600519"},
            {"name": "full", "value": True},
        ],
    }
    content = platform._build_command_content(interaction_data)
    assert content == "/analyze 600519 full"


def test_boolean_option_false_is_omitted():
    """The boolean False option should be ignored and not appear in the command content."""
    platform = _make_platform("00" * 32)
    interaction_data = {
        "name": "analyze",
        "options": [
            {"name": "stock_code", "value": "600519"},
            {"name": "full", "value": False},
        ],
    }
    content = platform._build_command_content(interaction_data)
    assert content == "/analyze 600519"
