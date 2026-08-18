# -*- coding: utf-8 -*-
"""Pydantic v2 AuthStatusResponse wire contract (Issue #549 Batch 3)."""

from __future__ import annotations

import json

from src.api.v1.endpoints.auth import AuthStatusResponse


# Golden camelCase payloads for wire stability (byte-identical serialization).
_GOLDEN_STATUS = (
    b'{"authEnabled":true,"loggedIn":false,"passwordChangeable":true,'
    b'"passwordSet":true,"setupState":"enabled"}'
)


def _json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def test_auth_status_response_serialization_byte_identical() -> None:
    model = AuthStatusResponse.model_validate(
        {
            "authEnabled": True,
            "loggedIn": False,
            "passwordSet": True,
            "passwordChangeable": True,
            "setupState": "enabled",
        }
    )
    assert _json_bytes(model.model_dump(mode="json", by_alias=True)) == _GOLDEN_STATUS


def test_auth_status_rejects_unknown_setup_state() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AuthStatusResponse.model_validate(
            {
                "authEnabled": False,
                "loggedIn": False,
                "passwordSet": False,
                "passwordChangeable": False,
                "setupState": "unknown",
            }
        )


def test_auth_status_rejects_extra_fields() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AuthStatusResponse.model_validate(
            {
                "authEnabled": False,
                "loggedIn": False,
                "passwordSet": False,
                "passwordChangeable": False,
                "setupState": "no_password",
                "futureFlag": True,
            }
        )
