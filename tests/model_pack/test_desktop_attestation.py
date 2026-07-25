from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from src.model_pack import (
    DESKTOP_MODEL_PACK_ATTESTATION_ENV,
    DESKTOP_MODEL_PACK_ATTESTATION_TTL_MS,
    ModelPackError,
    consume_desktop_model_pack_attestation,
)


SECRET = "a" * 64
NOW_MS = 1_784_966_400_000
RUNTIME_IDENTITY = "b" * 64


def _attestation(*, nonce: str, overrides: dict | None = None) -> str:
    payload = {
        "version": 1,
        "issuedAt": NOW_MS,
        "expiresAt": NOW_MS + DESKTOP_MODEL_PACK_ATTESTATION_TTL_MS,
        "nonce": nonce,
        "modelId": "licensed/finance:q4",
        "displayName": "Licensed Finance Q4",
        "minimumMemoryGb": 16,
        "licenseId": "LicenseRef-Finance",
        "expectedConfigVersion": "config-1",
        "expectedRuntimeIdentity": RUNTIME_IDENTITY,
    }
    payload.update(overrides or {})
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        SECRET.encode("ascii"), encoded.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{encoded}.{signature}"


def _consume(token: str, **overrides) -> None:
    fields = {
        "model_id": "licensed/finance:q4",
        "display_name": "Licensed Finance Q4",
        "minimum_memory_gb": 16,
        "license_id": "LicenseRef-Finance",
        "expected_config_version": "config-1",
        "expected_runtime_identity": RUNTIME_IDENTITY,
        "now_ms": NOW_MS,
    }
    fields.update(overrides)
    consume_desktop_model_pack_attestation(token, **fields)


def test_desktop_attestation_binds_metadata_and_is_consumed_once(monkeypatch) -> None:
    monkeypatch.setenv("DSA_DESKTOP_MODE", "true")
    monkeypatch.setenv(DESKTOP_MODEL_PACK_ATTESTATION_ENV, SECRET)
    token = _attestation(nonce="1" * 32)

    _consume(token)

    with pytest.raises(ModelPackError) as replay:
        _consume(token)
    assert replay.value.code == "desktop_attestation_replayed"


def test_desktop_attestation_rejects_tampered_metadata(monkeypatch) -> None:
    monkeypatch.setenv("DSA_DESKTOP_MODE", "true")
    monkeypatch.setenv(DESKTOP_MODEL_PACK_ATTESTATION_ENV, SECRET)
    token = _attestation(nonce="2" * 32)

    with pytest.raises(ModelPackError) as error:
        _consume(token, display_name="Forged presentation")

    assert error.value.code == "desktop_attestation_invalid"


def test_desktop_attestation_rejects_public_server_and_expired_tokens(monkeypatch) -> None:
    token = _attestation(nonce="3" * 32)
    monkeypatch.setenv(DESKTOP_MODEL_PACK_ATTESTATION_ENV, SECRET)

    with pytest.raises(ModelPackError) as public_error:
        _consume(token)
    assert public_error.value.code == "desktop_attestation_invalid"

    monkeypatch.setenv("DSA_DESKTOP_MODE", "true")
    with pytest.raises(ModelPackError) as expired:
        _consume(token, now_ms=NOW_MS + DESKTOP_MODEL_PACK_ATTESTATION_TTL_MS)
    assert expired.value.code == "desktop_attestation_expired"
