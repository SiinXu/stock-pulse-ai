"""Verify one-time attestations issued by the trusted Electron main process."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import threading
import time
from typing import Any, Dict

from src.model_pack.errors import ModelPackError


DESKTOP_MODEL_PACK_ATTESTATION_ENV = "STOCKPULSE_DESKTOP_MODEL_PACK_ATTESTATION_KEY"
DESKTOP_MODEL_PACK_ATTESTATION_TTL_MS = 5 * 60 * 1000
MAX_DESKTOP_MODEL_PACK_ATTESTATION_BYTES = 2048
MAX_USED_DESKTOP_MODEL_PACK_ATTESTATIONS = 256
_ATTESTATION_VERSION = 1
_CLOCK_SKEW_MS = 30 * 1000
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+\.[0-9a-f]{64}$")
_NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_SECRET_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PAYLOAD_KEYS = frozenset(
    {
        "version",
        "issuedAt",
        "expiresAt",
        "nonce",
        "modelId",
        "displayName",
        "minimumMemoryGb",
        "licenseId",
        "expectedConfigVersion",
        "expectedRuntimeIdentity",
    }
)
_USED_ATTESTATIONS: Dict[str, int] = {}
_USED_ATTESTATIONS_LOCK = threading.RLock()


def _attestation_error(code: str = "desktop_attestation_invalid") -> ModelPackError:
    return ModelPackError(
        code,
        (
            "Desktop Model Pack validation could not be verified. "
            "Import the Model Pack again from the Local Models panel."
        ),
    )


def _desktop_mode_enabled() -> bool:
    return os.getenv("DSA_DESKTOP_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def consume_desktop_model_pack_attestation(
    attestation: str,
    *,
    model_id: str,
    display_name: str,
    minimum_memory_gb: int,
    license_id: str,
    expected_config_version: str,
    expected_runtime_identity: str,
    now_ms: int | None = None,
) -> None:
    """Authenticate and consume metadata emitted after Desktop validation/create."""
    token = str(attestation or "").strip()
    secret = os.getenv(DESKTOP_MODEL_PACK_ATTESTATION_ENV, "").strip()
    if (
        not _desktop_mode_enabled()
        or _SECRET_PATTERN.fullmatch(secret) is None
        or not token
        or len(token.encode("utf-8")) > MAX_DESKTOP_MODEL_PACK_ATTESTATION_BYTES
        or _TOKEN_PATTERN.fullmatch(token) is None
    ):
        raise _attestation_error()

    encoded_payload, supplied_signature = token.split(".", 1)
    expected_signature = hmac.new(
        secret.encode("ascii"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise _attestation_error()

    try:
        padding = "=" * (-len(encoded_payload) % 4)
        payload_bytes = base64.b64decode(
            encoded_payload + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise _attestation_error() from exc
    if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
        raise _attestation_error()

    issued_at = payload.get("issuedAt")
    expires_at = payload.get("expiresAt")
    if (
        payload.get("version") != _ATTESTATION_VERSION
        or not isinstance(issued_at, int)
        or isinstance(issued_at, bool)
        or not isinstance(expires_at, int)
        or isinstance(expires_at, bool)
        or expires_at - issued_at != DESKTOP_MODEL_PACK_ATTESTATION_TTL_MS
        or _NONCE_PATTERN.fullmatch(str(payload.get("nonce") or "")) is None
    ):
        raise _attestation_error()

    expected_fields: Dict[str, Any] = {
        "modelId": model_id,
        "displayName": display_name,
        "minimumMemoryGb": minimum_memory_gb,
        "licenseId": license_id,
        "expectedConfigVersion": expected_config_version,
        "expectedRuntimeIdentity": expected_runtime_identity,
    }
    if any(payload.get(key) != value for key, value in expected_fields.items()):
        raise _attestation_error()

    current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    if (
        issued_at > current_ms + _CLOCK_SKEW_MS
        or expires_at <= current_ms
        or expires_at > current_ms + DESKTOP_MODEL_PACK_ATTESTATION_TTL_MS + _CLOCK_SKEW_MS
    ):
        raise _attestation_error("desktop_attestation_expired")

    with _USED_ATTESTATIONS_LOCK:
        expired = [
            signature
            for signature, retained_expiry in _USED_ATTESTATIONS.items()
            if retained_expiry <= current_ms
        ]
        for signature in expired:
            del _USED_ATTESTATIONS[signature]
        if supplied_signature in _USED_ATTESTATIONS:
            raise _attestation_error("desktop_attestation_replayed")
        if len(_USED_ATTESTATIONS) >= MAX_USED_DESKTOP_MODEL_PACK_ATTESTATIONS:
            raise _attestation_error("desktop_attestation_capacity")
        _USED_ATTESTATIONS[supplied_signature] = expires_at


__all__ = [
    "DESKTOP_MODEL_PACK_ATTESTATION_ENV",
    "DESKTOP_MODEL_PACK_ATTESTATION_TTL_MS",
    "MAX_DESKTOP_MODEL_PACK_ATTESTATION_BYTES",
    "consume_desktop_model_pack_attestation",
]
