# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Write-side capability registration service with fail-closed audit."""

from __future__ import annotations

import logging

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from src.capability_registry.write_audit import CapabilityWriteAuditor
from src.capability_registry.write_models import (
    WriteCapabilityEntry,
    WriteCapabilityStatus,
    WriteRegistrySnapshot,
)
from src.utils.sanitize import log_safe_exception
from src.capability_registry.write_store import (
    CapabilityWriteStore,
    WriteRegistryStoreError,
    default_write_registry_path,
)

Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)


class CapabilityWriteError(Exception):
    def __init__(self, error_code: str, message: str = "") -> None:
        super().__init__(message or error_code)
        self.error_code = error_code
        self.message = message or error_code


class CapabilityWriteAuditCompletionUnavailable(RuntimeError):
    """Raised when the durable mutation succeeded but audit completion failed."""

    def __init__(self, entry: WriteCapabilityEntry) -> None:
        super().__init__("security_audit_unavailable")
        self.entry = entry


class CapabilityWriteService:
    def __init__(
        self,
        store: CapabilityWriteStore | None = None,
        *,
        auditor: CapabilityWriteAuditor | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._store = store or CapabilityWriteStore()
        self._auditor = auditor or CapabilityWriteAuditor()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def store(self) -> CapabilityWriteStore:
        return self._store

    def _now_iso(self) -> str:
        return self._clock().astimezone(timezone.utc).isoformat()

    def _complete_success(
        self,
        *,
        capability_id: str,
        operation: str,
        correlation_id: str,
        entry: WriteCapabilityEntry,
        metadata: Mapping[str, Any] | None = None,
        actor_type: str,
        actor_id: str,
    ) -> None:
        """Persist success audit; surface write-done/audit-failed distinctly."""

        try:
            self._auditor.complete(
                capability_id=capability_id,
                operation=operation,
                success=True,
                correlation_id=correlation_id,
                metadata=metadata,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - map to completion-unavailable
            from src.services.security_audit_service import SecurityAuditUnavailable

            log_safe_exception(
                logger,
                "Capability write audit completion unavailable after mutation",
                exc,
                error_code="capability_write_audit_completion_unavailable",
                context={
                    "capability_id": capability_id,
                    "operation": operation,
                },
            )
            if isinstance(exc, SecurityAuditUnavailable):
                raise CapabilityWriteAuditCompletionUnavailable(entry) from None
            raise CapabilityWriteAuditCompletionUnavailable(entry) from exc

    def _complete_failure(
        self,
        *,
        capability_id: str,
        operation: str,
        correlation_id: str,
        error_code: str,
        metadata: Mapping[str, Any] | None = None,
        actor_type: str,
        actor_id: str,
    ) -> None:
        """Best-effort failure audit; never mask the original domain error."""

        try:
            self._auditor.complete(
                capability_id=capability_id,
                operation=operation,
                success=False,
                correlation_id=correlation_id,
                error_code=error_code,
                metadata=metadata,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - preserve domain error
            log_safe_exception(
                logger,
                "Capability write failure audit completion unavailable",
                exc,
                error_code="capability_write_failure_audit_unavailable",
                context={
                    "capability_id": capability_id,
                    "operation": operation,
                },
            )

    def list_entries(
        self,
        *,
        domain: str | None = None,
        status: WriteCapabilityStatus | None = None,
        include_retired: bool = True,
    ) -> WriteRegistrySnapshot:
        snapshot = self._store.load()
        entries = snapshot.entries
        if domain is not None:
            entries = tuple(item for item in entries if item.domain == domain)
        if status is not None:
            entries = tuple(item for item in entries if item.status == status)
        elif not include_retired:
            entries = tuple(item for item in entries if item.status == "active")
        return WriteRegistrySnapshot(
            generation=snapshot.generation,
            as_of=snapshot.as_of,
            entries=entries,
        )

    def get(self, capability_id: str) -> WriteCapabilityEntry | None:
        return self._store.get(capability_id)

    def register(
        self,
        payload: Mapping[str, Any],
        *,
        actor_type: str = "administrator",
        actor_id: str = "local_operator",
    ) -> WriteCapabilityEntry:
        capability_id = str(payload.get("capability_id") or "").strip()
        correlation_id = self._auditor.begin(
            capability_id=capability_id or "unknown",
            operation="register",
            metadata={"domain": str(payload.get("domain") or "")},
            actor_type=actor_type,
            actor_id=actor_id,
        )
        try:
            entry = self._build_new_entry(payload, existing=None)

            def _apply(snapshot: WriteRegistrySnapshot) -> tuple[WriteCapabilityEntry, ...]:
                if any(item.capability_id == entry.capability_id for item in snapshot.entries):
                    raise CapabilityWriteError(
                        "capability_already_exists",
                        f"capability {entry.capability_id!r} is already registered",
                    )
                return snapshot.entries + (entry,)

            self._store.mutate(_apply)
        except CapabilityWriteError as exc:
            self._complete_failure(
                capability_id=capability_id or "unknown",
                operation="register",
                correlation_id=correlation_id,
                error_code=exc.error_code,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise
        except WriteRegistryStoreError as exc:
            self._complete_failure(
                capability_id=capability_id or "unknown",
                operation="register",
                correlation_id=correlation_id,
                error_code=exc.error_code,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise CapabilityWriteError(exc.error_code, str(exc)) from exc
        except ValueError as exc:
            self._complete_failure(
                capability_id=capability_id or "unknown",
                operation="register",
                correlation_id=correlation_id,
                error_code="capability_validation_failed",
                metadata={"detail": str(exc)[:200]},
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise CapabilityWriteError("capability_validation_failed", str(exc)) from exc
        except Exception:
            self._complete_failure(
                capability_id=capability_id or "unknown",
                operation="register",
                correlation_id=correlation_id,
                error_code="capability_register_failed",
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise
        self._complete_success(
            capability_id=entry.capability_id,
            operation="register",
            correlation_id=correlation_id,
            entry=entry,
            metadata={"version": entry.version, "domain": entry.domain},
            actor_type=actor_type,
            actor_id=actor_id,
        )
        return entry

    def update(
        self,
        capability_id: str,
        payload: Mapping[str, Any],
        *,
        actor_type: str = "administrator",
        actor_id: str = "local_operator",
    ) -> WriteCapabilityEntry:
        correlation_id = self._auditor.begin(
            capability_id=capability_id,
            operation="update",
            metadata={"fields": sorted(str(key) for key in payload.keys())[:16]},
            actor_type=actor_type,
            actor_id=actor_id,
        )
        produced: list[WriteCapabilityEntry] = []
        try:
            def _apply(snapshot: WriteRegistrySnapshot) -> tuple[WriteCapabilityEntry, ...]:
                existing = next(
                    (item for item in snapshot.entries if item.capability_id == capability_id),
                    None,
                )
                if existing is None:
                    raise CapabilityWriteError(
                        "capability_not_found",
                        f"capability {capability_id!r} is not registered",
                    )
                if existing.status == "retired":
                    raise CapabilityWriteError(
                        "capability_retired",
                        f"capability {capability_id!r} is retired and cannot be updated",
                    )
                for field_name, message in (
                    ("domain", "domain cannot be changed after registration"),
                    ("capability_type", "capability_type cannot be changed after registration"),
                    ("capability_id", "capability_id cannot be changed after registration"),
                ):
                    if field_name in payload and str(payload[field_name]).strip() != str(
                        getattr(existing, field_name)
                    ):
                        raise CapabilityWriteError("capability_identity_immutable", message)
                merged = {
                    "capability_id": existing.capability_id,
                    "domain": existing.domain,
                    "capability_type": existing.capability_type,
                    "version": existing.version,
                    "provider": existing.provider,
                    "display_name": existing.display_name,
                    "dependencies": list(existing.dependencies),
                    "tags": list(existing.tags),
                    "scopes": list(existing.scopes),
                    "markets": list(existing.markets),
                    "model_route": existing.model_route,
                    "cost_tier": existing.cost_tier,
                    "latency_class": existing.latency_class,
                }
                for key in (
                    "version", "provider", "display_name", "dependencies", "tags",
                    "scopes", "markets", "model_route", "cost_tier", "latency_class",
                ):
                    if key in payload:
                        merged[key] = payload[key]
                entry = self._build_new_entry(merged, existing=existing)
                produced.append(entry)
                return tuple(
                    entry if item.capability_id == capability_id else item
                    for item in snapshot.entries
                )

            self._store.mutate(_apply)
        except CapabilityWriteError as exc:
            self._complete_failure(
                capability_id=capability_id, operation="update",
                correlation_id=correlation_id, error_code=exc.error_code,
                actor_type=actor_type, actor_id=actor_id,
            )
            raise
        except WriteRegistryStoreError as exc:
            self._complete_failure(
                capability_id=capability_id, operation="update",
                correlation_id=correlation_id, error_code=exc.error_code,
                actor_type=actor_type, actor_id=actor_id,
            )
            raise CapabilityWriteError(exc.error_code, str(exc)) from exc
        except ValueError as exc:
            self._complete_failure(
                capability_id=capability_id, operation="update",
                correlation_id=correlation_id, error_code="capability_validation_failed",
                metadata={"detail": str(exc)[:200]}, actor_type=actor_type, actor_id=actor_id,
            )
            raise CapabilityWriteError("capability_validation_failed", str(exc)) from exc
        except Exception:
            self._complete_failure(
                capability_id=capability_id, operation="update",
                correlation_id=correlation_id, error_code="capability_update_failed",
                actor_type=actor_type, actor_id=actor_id,
            )
            raise
        entry = produced[0]
        self._complete_success(
            capability_id=entry.capability_id,
            operation="update",
            correlation_id=correlation_id,
            entry=entry,
            metadata={"version": entry.version, "generation": entry.generation},
            actor_type=actor_type,
            actor_id=actor_id,
        )
        return entry

    def retire(
        self,
        capability_id: str,
        *,
        actor_type: str = "administrator",
        actor_id: str = "local_operator",
    ) -> WriteCapabilityEntry:
        correlation_id = self._auditor.begin(
            capability_id=capability_id, operation="retire",
            actor_type=actor_type, actor_id=actor_id,
        )
        produced: list[WriteCapabilityEntry] = []
        already_retired = False
        try:
            def _apply(
                snapshot: WriteRegistrySnapshot,
            ) -> tuple[WriteCapabilityEntry, ...] | None:
                nonlocal already_retired
                existing = next(
                    (item for item in snapshot.entries if item.capability_id == capability_id),
                    None,
                )
                if existing is None:
                    raise CapabilityWriteError(
                        "capability_not_found",
                        f"capability {capability_id!r} is not registered",
                    )
                if existing.status == "retired":
                    already_retired = True
                    produced.append(existing)
                    return None
                now = self._now_iso()
                entry = replace(
                    existing, status="retired", retired_at=now, updated_at=now,
                    generation=existing.generation + 1,
                )
                produced.append(entry)
                return tuple(
                    entry if item.capability_id == capability_id else item
                    for item in snapshot.entries
                )

            self._store.mutate(_apply)
        except CapabilityWriteError as exc:
            self._complete_failure(
                capability_id=capability_id, operation="retire",
                correlation_id=correlation_id, error_code=exc.error_code,
                actor_type=actor_type, actor_id=actor_id,
            )
            raise
        except WriteRegistryStoreError as exc:
            self._complete_failure(
                capability_id=capability_id, operation="retire",
                correlation_id=correlation_id, error_code=exc.error_code,
                actor_type=actor_type, actor_id=actor_id,
            )
            raise CapabilityWriteError(exc.error_code, str(exc)) from exc
        except Exception:
            self._complete_failure(
                capability_id=capability_id, operation="retire",
                correlation_id=correlation_id, error_code="capability_retire_failed",
                actor_type=actor_type, actor_id=actor_id,
            )
            raise
        entry = produced[0]
        if already_retired:
            self._complete_success(
                capability_id=entry.capability_id,
                operation="retire",
                correlation_id=correlation_id,
                entry=entry,
                metadata={"already_retired": True},
                actor_type=actor_type,
                actor_id=actor_id,
            )
            return entry
        self._complete_success(
            capability_id=entry.capability_id,
            operation="retire",
            correlation_id=correlation_id,
            entry=entry,
            actor_type=actor_type,
            actor_id=actor_id,
        )
        return entry

    def _build_new_entry(
        self,
        payload: Mapping[str, Any],
        *,
        existing: WriteCapabilityEntry | None,
    ) -> WriteCapabilityEntry:
        now = self._now_iso()
        generation = 1 if existing is None else existing.generation + 1
        registered_at = existing.registered_at if existing is not None else now
        return WriteCapabilityEntry(
            capability_id=str(payload.get("capability_id") or ""),
            domain=payload.get("domain"),  # type: ignore[arg-type]
            capability_type=payload.get("capability_type"),  # type: ignore[arg-type]
            version=str(payload.get("version") or "1"),
            status="active",
            provider=str(payload.get("provider") or payload.get("capability_id") or ""),
            display_name=str(payload.get("display_name") or ""),
            dependencies=tuple(payload.get("dependencies") or ()),
            tags=tuple(payload.get("tags") or ()),
            scopes=tuple(payload.get("scopes") or ()),
            markets=tuple(payload.get("markets") or ()),
            model_route=str(payload.get("model_route") or ""),
            cost_tier=str(payload.get("cost_tier") or ""),
            latency_class=str(payload.get("latency_class") or ""),
            registered_at=registered_at,
            updated_at=now,
            retired_at=None,
            generation=generation,
        )


_SERVICE: CapabilityWriteService | None = None


def get_capability_write_service(
    *,
    path: Path | None = None,
    reset: bool = False,
) -> CapabilityWriteService:
    global _SERVICE
    if reset or _SERVICE is None or path is not None:
        store = CapabilityWriteStore(path or default_write_registry_path())
        _SERVICE = CapabilityWriteService(store=store)
    return _SERVICE
