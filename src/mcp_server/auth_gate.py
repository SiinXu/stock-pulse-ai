# -*- coding: utf-8 -*-
"""Official-SDK bearer verification for the Streamable HTTP transport."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time

from mcp.server.auth.provider import AccessToken

from src.auth import verify_session
from src.mcp_server.config import McpServerConfig
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    SecurityAuditUnavailable,
    get_security_audit_service,
    require_security_audit_recorder,
)

logger = logging.getLogger(__name__)


class AdminSessionTokenVerifier:
    """Validate one explicitly audience-pinned existing admin session."""

    def __init__(
        self,
        config: McpServerConfig,
        *,
        security_audit: SecurityAuditRecorder | None = None,
    ) -> None:
        if not config.http_session_token_sha256:
            raise ValueError("HTTP session token digest is required")
        self.config = config
        self._audit = require_security_audit_recorder(
            security_audit or get_security_audit_service()
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        actor_id = f"session:{digest[:16]}"
        correlation_id = SecurityAuditService.new_correlation_id()
        fields = {
            "event_type": "mcp.auth",
            "actor_type": "admin_session",
            "actor_id": actor_id,
            "execution_id": correlation_id,
            "action": "mcp.authenticate",
            "target_type": "mcp_resource",
            "target_id": "stockpulse-mcp",
            "correlation_id": correlation_id,
            "metadata": {"transport": "streamable-http"},
        }
        try:
            self._audit.record_attempt(**fields)
        except SecurityAuditUnavailable:
            logger.error("MCP authentication denied because the security audit attempt was unavailable")
            return None

        pinned = hmac.compare_digest(digest, self.config.http_session_token_sha256 or "")
        valid = pinned and verify_session(token)
        try:
            self._audit.record_completion(
                **fields,
                outcome="success" if valid else "denied",
                reason_code="authenticated" if valid else "invalid_token",
            )
        except SecurityAuditUnavailable:
            logger.error("MCP authentication denied because the security audit completion was unavailable")
            return None
        if not valid:
            logger.warning(
                "MCP authentication denied (audience_pin=%s, admin_session_valid=%s)",
                pinned,
                valid if pinned else False,
            )
            return None

        timestamp = _session_timestamp(token)
        if timestamp is None:
            logger.warning("MCP authentication denied because the admin session timestamp was malformed")
            return None
        expires_at = timestamp + self.config.admin_session_max_age_hours * 3600
        if expires_at <= int(time.time()):
            logger.warning("MCP authentication denied because the pinned admin session expired")
            return None
        return AccessToken(
            token=token,
            client_id="stockpulse-mcp",
            subject=actor_id,
            scopes=sorted(self.config.http_scopes),
            expires_at=expires_at,
            resource=self.config.http_resource,
            claims={"iss": "stockpulse-admin-session", "aud": self.config.http_resource},
        )


def _session_timestamp(token: str) -> int | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None
