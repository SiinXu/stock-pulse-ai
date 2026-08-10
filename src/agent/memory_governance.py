# -*- coding: utf-8 -*-
"""Principal-scoped memory lifecycle: consent, retention, delete, audit.

Defaults minimize collection:

- Global collection switch is **off**.
- Per-principal consent is required before any collect/project/export.
- Retention is finite; expired rows are dropped on write and on expire passes.
- Delete/clear are principal-scoped and audited.
- Access (project/export/delete/clear/consent) is append-only audited.

This store is an in-process foundation for the lifecycle contract. It does not
replace shared ``analysis_history`` storage or assign principals for production
API/bot/CLI paths; those remain separate remaining work.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from src.agent.memory_isolation import isolate_layered_memory_for_prompt
from src.agent.memory_layers import (
    MAX_AUTHORIZED_RECORDS,
    LayeredMemoryBundle,
    MemoryObservation,
    parse_instant,
    validate_principal_id,
)
from src.agent.memory_retrieval import AuthorizedMemoryProjector

_AUDIT_ACTIONS = frozenset({
    "consent_grant",
    "consent_revoke",
    "collect",
    "project",
    "export",
    "delete",
    "clear",
    "expire",
})
_DETAIL_RE_SAFE = re.compile(r"^[A-Za-z0-9._:@\-/ ]{0,200}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _add_days_iso(instant: str, days: int) -> str:
    base = parse_instant("observed_at", instant)
    return (base + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class LayeredMemoryPolicy:
    collection_enabled: bool = False
    retention_days: int = 90
    vector_enabled: bool = False
    max_records_per_principal: int = MAX_AUTHORIZED_RECORDS
    audit_enabled: bool = True

    def __post_init__(self) -> None:
        if type(self.collection_enabled) is not bool:
            raise ValueError("collection_enabled must be a boolean")
        if type(self.vector_enabled) is not bool:
            raise ValueError("vector_enabled must be a boolean")
        if type(self.audit_enabled) is not bool:
            raise ValueError("audit_enabled must be a boolean")
        if type(self.retention_days) is not int or not 1 <= self.retention_days <= 3650:
            raise ValueError("retention_days must be within [1, 3650]")
        if (
            type(self.max_records_per_principal) is not int
            or not 1 <= self.max_records_per_principal <= MAX_AUTHORIZED_RECORDS
        ):
            raise ValueError(
                f"max_records_per_principal must be within [1, {MAX_AUTHORIZED_RECORDS}]"
            )

    @classmethod
    def from_config(cls, config: Any) -> "LayeredMemoryPolicy":
        return cls(
            collection_enabled=bool(
                getattr(config, "layered_memory_collection_enabled", False)
            ),
            retention_days=int(getattr(config, "layered_memory_retention_days", 90)),
            vector_enabled=bool(getattr(config, "layered_memory_vector_enabled", False)),
            max_records_per_principal=int(
                getattr(
                    config,
                    "layered_memory_max_records_per_principal",
                    MAX_AUTHORIZED_RECORDS,
                )
            ),
            audit_enabled=bool(getattr(config, "layered_memory_audit_enabled", True)),
        )


@dataclass(frozen=True)
class MemoryAuditEvent:
    event_id: str
    principal_id: str
    action: str
    at: str
    detail: str = ""
    resource_count: int = 0

    def __post_init__(self) -> None:
        validate_principal_id(self.principal_id)
        parse_instant("at", self.at)
        if self.action not in _AUDIT_ACTIONS:
            raise ValueError("unknown memory audit action")
        if type(self.event_id) is not str or not 1 <= len(self.event_id) <= 64:
            raise ValueError("event_id must be a bounded string")
        if type(self.detail) is not str or not _DETAIL_RE_SAFE.match(self.detail):
            raise ValueError("audit detail must use the safe alphabet")
        if type(self.resource_count) is not int or self.resource_count < 0:
            raise ValueError("resource_count must be a non-negative int")


@dataclass
class MemoryAccessAuditor:
    _events: List[MemoryAuditEvent] = field(default_factory=list)

    def record(
        self,
        *,
        principal_id: str,
        action: str,
        at: Optional[str] = None,
        detail: str = "",
        resource_count: int = 0,
    ) -> MemoryAuditEvent:
        event = MemoryAuditEvent(
            event_id=uuid.uuid4().hex,
            principal_id=principal_id,
            action=action,
            at=at or _utc_now_iso(),
            detail=detail,
            resource_count=resource_count,
        )
        self._events.append(event)
        return event

    def list_for_principal(self, principal_id: str) -> List[MemoryAuditEvent]:
        validate_principal_id(principal_id)
        return [event for event in self._events if event.principal_id == principal_id]

    def all_events(self) -> List[MemoryAuditEvent]:
        return list(self._events)


@dataclass
class PrincipalMemoryLifecycle:
    policy: LayeredMemoryPolicy = field(default_factory=LayeredMemoryPolicy)
    auditor: MemoryAccessAuditor = field(default_factory=MemoryAccessAuditor)
    _consent_at: Dict[str, str] = field(default_factory=dict)
    _records: Dict[str, Dict[int, MemoryObservation]] = field(default_factory=dict)

    def has_consent(self, principal_id: str) -> bool:
        validate_principal_id(principal_id)
        return principal_id in self._consent_at

    def grant_consent(self, principal_id: str, *, at: Optional[str] = None) -> None:
        validate_principal_id(principal_id)
        granted_at = at or _utc_now_iso()
        parse_instant("at", granted_at)
        self._consent_at[principal_id] = granted_at
        self._audit(principal_id, "consent_grant", at=granted_at, detail="granted")

    def revoke_consent(
        self,
        principal_id: str,
        *,
        at: Optional[str] = None,
        clear_data: bool = True,
    ) -> int:
        validate_principal_id(principal_id)
        revoked_at = at or _utc_now_iso()
        parse_instant("at", revoked_at)
        deleted = 0
        if clear_data:
            deleted = self.clear(principal_id, at=revoked_at, _from_revoke=True)
        self._consent_at.pop(principal_id, None)
        self._audit(
            principal_id,
            "consent_revoke",
            at=revoked_at,
            detail="revoked",
            resource_count=deleted,
        )
        return deleted

    def put(self, observation: MemoryObservation, *, now: Optional[str] = None) -> MemoryObservation:
        if not self.policy.collection_enabled:
            raise PermissionError("layered memory collection is disabled")
        principal_id = observation.principal_id
        if not self.has_consent(principal_id):
            raise PermissionError("principal has not consented to memory collection")
        now_iso = now or _utc_now_iso()
        parse_instant("now", now_iso)
        stored = self._apply_retention_stamp(observation)
        bucket = self._records.setdefault(principal_id, {})
        self._drop_expired_in_bucket(principal_id, now_iso)
        if (
            stored.analysis_history_id not in bucket
            and len(bucket) >= self.policy.max_records_per_principal
        ):
            raise ValueError("principal memory panel exceeds hard cap")
        if parse_instant("observed_at", stored.observed_at) > parse_instant("now", now_iso):
            raise ValueError("cannot collect a future observation")
        bucket[stored.analysis_history_id] = stored
        self._audit(
            principal_id,
            "collect",
            at=now_iso,
            detail=f"history:{stored.analysis_history_id}",
            resource_count=1,
        )
        return stored

    def expire_due(self, *, now: Optional[str] = None) -> int:
        now_iso = now or _utc_now_iso()
        parse_instant("now", now_iso)
        total = 0
        for principal_id in list(self._records):
            total += self._drop_expired_in_bucket(principal_id, now_iso)
        return total

    def list_records(
        self,
        principal_id: str,
        *,
        as_of: Optional[str] = None,
    ) -> List[MemoryObservation]:
        validate_principal_id(principal_id)
        if not self.has_consent(principal_id):
            raise PermissionError("principal has not consented to memory access")
        as_of_iso = as_of or _utc_now_iso()
        parse_instant("as_of", as_of_iso)
        self._drop_expired_in_bucket(principal_id, as_of_iso)
        rows = list(self._records.get(principal_id, {}).values())
        rows.sort(
            key=lambda row: (
                parse_instant("observed_at", row.observed_at),
                row.analysis_history_id,
            ),
            reverse=True,
        )
        return rows

    def delete(
        self,
        principal_id: str,
        analysis_history_id: int,
        *,
        at: Optional[str] = None,
    ) -> bool:
        validate_principal_id(principal_id)
        if type(analysis_history_id) is not int or analysis_history_id <= 0:
            raise ValueError("analysis_history_id must be a positive int")
        bucket = self._records.get(principal_id, {})
        removed = bucket.pop(analysis_history_id, None) is not None
        if removed:
            self._audit(
                principal_id,
                "delete",
                at=at or _utc_now_iso(),
                detail=f"history:{analysis_history_id}",
                resource_count=1,
            )
        return removed

    def clear(
        self,
        principal_id: str,
        *,
        at: Optional[str] = None,
        _from_revoke: bool = False,
    ) -> int:
        validate_principal_id(principal_id)
        bucket = self._records.pop(principal_id, {})
        count = len(bucket)
        if count and not _from_revoke:
            self._audit(
                principal_id,
                "clear",
                at=at or _utc_now_iso(),
                detail="complete-clear",
                resource_count=count,
            )
        return count

    def project(
        self,
        principal_id: str,
        *,
        stock_code: str,
        as_of: Optional[str] = None,
        query: str = "",
    ) -> LayeredMemoryBundle:
        if not self.has_consent(principal_id):
            raise PermissionError("principal has not consented to memory access")
        as_of_iso = as_of or _utc_now_iso()
        records = self.list_records(principal_id, as_of=as_of_iso)
        projector = AuthorizedMemoryProjector(
            records,
            principal_id=principal_id,
            as_of=as_of_iso,
            vector_enabled=self.policy.vector_enabled,
        )
        bundle = projector.retrieve_layered(stock_code=stock_code, query=query)
        self._audit(
            principal_id,
            "project",
            at=as_of_iso,
            detail=f"stock:{stock_code}",
            resource_count=len(bundle.source_history_ids),
        )
        return bundle

    def export_isolated_prompt_block(
        self,
        principal_id: str,
        *,
        stock_code: str,
        as_of: Optional[str] = None,
        query: str = "",
    ) -> str:
        bundle = self.project(
            principal_id,
            stock_code=stock_code,
            as_of=as_of,
            query=query,
        )
        rendered = isolate_layered_memory_for_prompt(bundle)
        self._audit(
            principal_id,
            "export",
            at=as_of or _utc_now_iso(),
            detail="isolated-prompt-block",
            resource_count=len(bundle.source_history_ids),
        )
        return rendered

    def _apply_retention_stamp(self, observation: MemoryObservation) -> MemoryObservation:
        if observation.expires_at is not None:
            return observation
        expires_at = _add_days_iso(observation.observed_at, self.policy.retention_days)
        return replace(observation, expires_at=expires_at)

    def _drop_expired_in_bucket(self, principal_id: str, now_iso: str) -> int:
        bucket = self._records.get(principal_id)
        if not bucket:
            return 0
        now = parse_instant("now", now_iso)
        expired_ids = [
            history_id
            for history_id, row in bucket.items()
            if row.expires_at is not None
            and parse_instant("expires_at", row.expires_at) <= now
        ]
        for history_id in expired_ids:
            del bucket[history_id]
        if expired_ids:
            self._audit(
                principal_id,
                "expire",
                at=now_iso,
                detail="retention-expiry",
                resource_count=len(expired_ids),
            )
        if not bucket:
            self._records.pop(principal_id, None)
        return len(expired_ids)

    def _audit(
        self,
        principal_id: str,
        action: str,
        *,
        at: str,
        detail: str = "",
        resource_count: int = 0,
    ) -> None:
        if not self.policy.audit_enabled:
            return
        self.auditor.record(
            principal_id=principal_id,
            action=action,
            at=at,
            detail=detail,
            resource_count=resource_count,
        )


def authorize_records_for_principal(
    records: Sequence[MemoryObservation],
    *,
    principal_id: str,
) -> List[MemoryObservation]:
    validate_principal_id(principal_id)
    authorized: List[MemoryObservation] = []
    for record in records:
        if record.principal_id != principal_id:
            raise PermissionError("cross-principal record rejected")
        authorized.append(record)
    if len(authorized) > MAX_AUTHORIZED_RECORDS:
        raise ValueError("authorized record panel exceeds hard cap")
    return authorized
