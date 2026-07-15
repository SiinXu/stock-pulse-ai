# -*- coding: utf-8 -*-
"""Atomic idempotency coordination for portfolio ledger writes."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Callable, Dict, Optional

from src.repositories.portfolio_repo import (
    PortfolioIdempotencyClaimConflict,
    PortfolioRepository,
)


class PortfolioIdempotencyKeyReusedError(Exception):
    """Raised when one operation ID is reused for a different payload."""


def normalize_portfolio_operation_id(value: Optional[str]) -> Optional[str]:
    operation_id = (value or "").strip()
    if not operation_id:
        return None
    if len(operation_id) > 128:
        raise ValueError("operation_id must be at most 128 characters")
    return operation_id


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported idempotency payload value: {type(value).__name__}")


def portfolio_payload_hash(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PortfolioIdempotencyCoordinator:
    """Run a portfolio mutation and persist its response in one transaction."""

    def __init__(self, repo: PortfolioRepository):
        self.repo = repo

    def execute(
        self,
        *,
        operation_kind: str,
        account_id: int,
        operation_id: Optional[str],
        payload: Dict[str, Any],
        write: Callable[[Any], Dict[str, Any]],
    ) -> Dict[str, Any]:
        normalized_id = normalize_portfolio_operation_id(operation_id)
        if normalized_id is None:
            with self.repo.portfolio_write_session() as session:
                return write(session)

        payload_hash = portfolio_payload_hash(payload)
        try:
            with self.repo.portfolio_write_session() as session:
                existing = self.repo.get_idempotency_record_in_session(
                    session=session,
                    operation_kind=operation_kind,
                    account_id=account_id,
                    operation_id=normalized_id,
                )
                if existing is not None:
                    return self._replay(existing.payload_hash, existing.response_json, payload_hash)

                claim = self.repo.claim_idempotency_in_session(
                    session=session,
                    operation_kind=operation_kind,
                    account_id=account_id,
                    operation_id=normalized_id,
                    payload_hash=payload_hash,
                )
                response = write(session)
                self.repo.complete_idempotency_in_session(
                    session=session,
                    row=claim,
                    response_json=json.dumps(
                        response,
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                        default=_json_default,
                    ),
                )
                return response
        except PortfolioIdempotencyClaimConflict:
            # On databases without SQLite's BEGIN IMMEDIATE serialization, a
            # concurrent claim can win after our initial lookup. Its unique-key
            # failure rolls back this entire transaction, including any writes.
            existing = self.repo.get_idempotency_record(
                operation_kind=operation_kind,
                account_id=account_id,
                operation_id=normalized_id,
            )
            if existing is None:
                raise RuntimeError("Idempotency claim completed without a durable record")
            return self._replay(existing.payload_hash, existing.response_json, payload_hash)

    @staticmethod
    def _replay(stored_hash: str, response_json: str, requested_hash: str) -> Dict[str, Any]:
        if stored_hash != requested_hash:
            raise PortfolioIdempotencyKeyReusedError(
                "The idempotency key was already used with a different request payload."
            )
        response = json.loads(response_json)
        if not isinstance(response, dict):
            raise RuntimeError("Stored portfolio idempotency response is invalid")
        return response
