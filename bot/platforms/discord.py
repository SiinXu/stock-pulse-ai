# -*- coding: utf-8 -*-
"""
===================================
Discord platform adapter
===================================

Responsible for:
1. Validate Discord Webhook requests
2. Parse Discord messages into a unified format
3. Convert responses to Discord format
"""

import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

import requests
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from bot.platforms.base import BotPlatform
from bot.models import BotMessage, BotResponse, WebhookResponse, ChatType
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)


class DiscordPlatform(BotPlatform):
    """Discord platform adapter"""

    def __init__(self):
        from src.config import get_config

        config = get_config()
        self._interactions_public_key = (
            getattr(config, "discord_interactions_public_key", None) or ""
        ).strip()
    
    @property
    def platform_name(self) -> str:
        """Platform identifier name"""
        return "discord"
    
    def verify_request(self, headers: Dict[str, str], body: bytes) -> bool:
        """Validate Discord Webhook request signature
        
        Discord Webhook Signature verification:
        1. Get X-Signature-Ed25519 and X-Signature-Timestamp from request headers.
        2. Use public key verification for signatures
        
        Args:
            headers: HTTP request headers
            body: Raw bytes of the request body
            
        Returns:
            Signature validity check
        """
        if not self._interactions_public_key:
            logger.warning(
                "[Discord] Interactions public key is not configured; rejecting request"
            )
            return False

        normalized_headers = {str(k).lower(): v for k, v in headers.items()}
        signature = normalized_headers.get("x-signature-ed25519", "")
        timestamp = normalized_headers.get("x-signature-timestamp", "")

        if not signature or not timestamp:
            logger.warning("[Discord] Signature headers are missing; rejecting request")
            return False

        # Validate timestamp format and timeliness to prevent replay attacks
        try:
            ts_int = int(timestamp)
        except (TypeError, ValueError):
            logger.warning(
                "[Discord] Timestamp must be an integer Unix timestamp; rejecting request"
            )
            return False

        try:
            now_ts = int(time.time())
        except Exception as exc:
            log_safe_exception(
                logger,
                "[Discord] Current time lookup failed; rejecting request",
                exc,
                error_code="bot_discord_time_lookup_failed",
                level=logging.WARNING,
            )
            return False

        # Time window: ±5 minutes
        if abs(now_ts - ts_int) > 300:
            logger.warning(
                "[Discord] Request timestamp is outside the allowed window: timestamp=%s now=%s",
                ts_int,
                now_ts,
            )
            return False

        try:
            verify_key = VerifyKey(bytes.fromhex(self._interactions_public_key))
            signature_bytes = bytes.fromhex(signature)
        except ValueError:
            logger.warning(
                "[Discord] Public key or signature is not valid hexadecimal; rejecting request"
            )
            return False
        except Exception as exc:
            log_safe_exception(
                logger,
                "[Discord] Signature public key loading failed",
                exc,
                error_code="bot_discord_public_key_load_failed",
                level=logging.WARNING,
            )
            return False

        try:
            verify_key.verify(timestamp.encode("utf-8") + body, signature_bytes)
        except BadSignatureError:
            logger.warning("[Discord] Signature verification failed")
            return False
        except Exception as exc:
            log_safe_exception(
                logger,
                "[Discord] Signature verification failed unexpectedly",
                exc,
                error_code="bot_discord_signature_verification_failed",
                level=logging.WARNING,
            )
            return False

        return True

    def handle_webhook(
        self,
        headers: Dict[str, str],
        body: bytes,
        data: Dict[str, Any],
    ) -> Tuple[Optional[BotMessage], Optional[WebhookResponse]]:
        """Discord Need pre-signed certificate, reprocess ping/challenge."""
        if not self.verify_request(headers, body):
            return None, WebhookResponse.error("Invalid Discord signature", 401)

        challenge_response = self.handle_challenge(data)
        if challenge_response:
            return None, challenge_response

        message = self.parse_message(data)
        if message is not None and data.get("type") == 2:
            # Discord requires an initial response within 3 s.  Return a
            # deferred acknowledgement (type 5 = DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE)
            # so the handler can dispatch the command in the background and
            # deliver the result via follow-up webhook.
            return message, WebhookResponse.success({"type": 5})

        return message, None
    
    def parse_message(self, data: Dict[str, Any]) -> Optional[BotMessage]:
        """Parse Discord messages into a unified format
        
        Args:
            data: Parsed JSON data
            
        Returns:
            BotMessage object, or None (no need to handle)
        """
        interaction_type = data.get("type")
        if interaction_type != 2:
            return None

        interaction_data = data.get("data", {})
        content = self._build_command_content(interaction_data)
        if not content:
            return None

        author = (
            data.get("user")
            or (data.get("member") or {}).get("user")
            or data.get("author", {})
        )
        user_id = str(author.get("id") or "")
        user_name = author.get("username", "unknown")
        channel_id = str(data.get("channel_id") or "")
        guild_id = str(data.get("guild_id") or "")

        if guild_id:
            chat_type = ChatType.GROUP
        elif channel_id:
            chat_type = ChatType.PRIVATE
        else:
            chat_type = ChatType.UNKNOWN

        return BotMessage(
            platform=self.platform_name,
            message_id=str(data.get("id") or ""),
            user_id=user_id,
            user_name=user_name,
            chat_id=channel_id or guild_id or user_id,
            chat_type=chat_type,
            content=content,
            raw_content=content,
            mentioned=False,
            mentions=[],
            timestamp=self._parse_timestamp(data.get("timestamp")),
            raw_data={
                **data,
                "_interaction_name": interaction_data.get("name", ""),
            },
        )
    
    def format_response(self, response: Any, message: BotMessage) -> WebhookResponse:
        """Convert unified responses to Discord format
        
        for Interaction(type=2)request, Return Discord Interaction Response
        Callback format: type=4 CHANNEL_MESSAGE_WITH_SOURCE with nested data.
        
        Args:
            response: unified response object
            message: Original message object
            
        Returns:
            WebhookResponse object
        """
        content = response.text if hasattr(response, "text") else str(response)

        message_data = {
            "content": content,
            "tts": False,
            "embeds": [],
            "allowed_mentions": {
                "parse": ["users", "roles", "everyone"]
            },
        }

        # Interaction(slash-command)Need Interaction Response Callback Format
        if message.raw_data.get("type") == 2:
            discord_response = {
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": message_data,
            }
        else:
            discord_response = message_data

        return WebhookResponse.success(discord_response)
    
    # Discord message content hard limit
    DISCORD_MAX_CONTENT_LENGTH = 2000

    def send_followup(self, response: BotResponse, message: BotMessage) -> bool:
        """Edit the deferred interaction placeholder with the real result.

        Uses ``PATCH /webhooks/{application_id}/{token}/messages/@original``
        to update the original deferred message, then sends additional
        follow-up messages via ``POST`` if the content exceeds Discord's
        2 000-character limit.
        """
        raw = message.raw_data
        application_id = raw.get("application_id", "")
        interaction_token = raw.get("token", "")
        if not application_id or not interaction_token:
            logger.warning(
                "[Discord] application_id or interaction token is missing; cannot send follow-up"
            )
            return False

        content = response.text if hasattr(response, "text") else str(response)

        from src.formatters import chunk_content_by_max_words

        try:
            chunks = chunk_content_by_max_words(
                content, self.DISCORD_MAX_CONTENT_LENGTH
            )
        except (ValueError, Exception) as exc:
            log_safe_exception(
                logger,
                "[Discord] Message chunking failed; attempting a single message",
                exc,
                error_code="bot_discord_message_chunking_failed",
                level=logging.WARNING,
            )
            chunks = [content]

        base_url = (
            f"https://discord.com/api/v10/webhooks/"
            f"{application_id}/{interaction_token}"
        )

        success = True
        for idx, chunk in enumerate(chunks):
            try:
                if idx == 0:
                    # PATCH the original deferred message
                    resp = requests.patch(
                        f"{base_url}/messages/@original",
                        json={"content": chunk},
                        timeout=10,
                    )
                else:
                    # POST additional follow-up messages
                    resp = requests.post(
                        base_url,
                        json={"content": chunk},
                        timeout=10,
                    )
                if resp.status_code >= 300:
                    logger.error(
                        "[Discord] Follow-up chunk delivery failed: chunk=%d total=%d status=%s",
                        idx + 1,
                        len(chunks),
                        resp.status_code,
                    )
                    success = False
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "[Discord] Follow-up chunk request failed",
                    exc,
                    error_code="bot_discord_followup_request_failed",
                    context={"chunk": idx + 1, "total": len(chunks)},
                )
                success = False

        if success:
            logger.info(
                "[Discord] Follow-up message delivery succeeded: chunk_count=%d",
                len(chunks),
            )
        return success

    def handle_challenge(self, data: Dict[str, Any]) -> Optional[WebhookResponse]:
        """Handle Discord verification requests
        
        Discord sends verification requests when configuring Webhooks
        
        Args:
            data: Request data
            
        Returns:
            Validate response, or None (not a validation request)
        """
        # Discord Webhook The request type is valid. 1
        if data.get("type") == 1:
            return WebhookResponse.success({
                "type": 1
            })
        
        # Discord command interaction validation
        if "challenge" in data:
            return WebhookResponse.success({
                "challenge": data["challenge"]
            })
        
        return None

    def _build_command_content(self, interaction_data: Dict[str, Any]) -> str:
        command_name = str(interaction_data.get("name", "")).strip()
        if not command_name:
            return ""

        parts = [f"/{command_name}"]
        self._append_option_parts(parts, interaction_data.get("options", []))
        return " ".join(parts).strip()

    def _append_option_parts(self, parts: List[str], options: Any) -> None:
        if not isinstance(options, list):
            return

        for option in options:
            if not isinstance(option, dict):
                continue

            nested_options = option.get("options")
            if nested_options:
                nested_name = str(option.get("name", "")).strip()
                if nested_name:
                    parts.append(nested_name)
                self._append_option_parts(parts, nested_options)
                continue

            value = option.get("value")
            if value is None:
                continue
            if isinstance(value, bool):
                # Emit the option name for truthy flags so downstream
                # commands receive a semantic token (e.g. "full") instead
                # of a literal "true"/"false" string.  False flags are
                # simply omitted.
                if value:
                    opt_name = str(option.get("name", "")).strip()
                    if opt_name:
                        parts.append(opt_name)
            else:
                parts.append(str(value))

    def _parse_timestamp(self, value: Any) -> datetime:
        if not value:
            return datetime.now()

        if isinstance(value, datetime):
            return value

        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return datetime.now()
