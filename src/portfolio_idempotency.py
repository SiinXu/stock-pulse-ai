"""Stable identity helpers for persisted Portfolio idempotency records."""

from __future__ import annotations

import hashlib
import json
from typing import Optional


def build_portfolio_idempotency_scope_key(
    *,
    account_id: int,
    owner_id: Optional[str],
) -> str:
    """Return the stable account/owner scope digest used by current records."""

    payload = {
        "account_id": int(account_id),
        "owner_id": (owner_id or "").strip(),
    }
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_portfolio_idempotency_storage_id(
    *,
    operation_type: str,
    scope_key: str,
    client_operation_id: str,
) -> str:
    """Return a bounded physical key compatible with the legacy unique column."""

    payload = {
        "client_operation_id": client_operation_id,
        "operation_type": operation_type,
        "scope_key": scope_key,
        "version": 2,
    }
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"v2:{digest}"
