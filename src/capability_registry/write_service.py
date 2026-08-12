# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Write-side capability registration service with fail-closed audit.

Mutations never succeed without a durable write and a completed audit pair.
Validation failures surface explicit error codes; the store is not updated.
"""

from __future__ import annotations

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
from src.capability_registry.write_store import (
    CapabilityWriteStore,
    WriteRegistryStoreError,
    default_write_registry_path,
)

Clock = Callable[[], datetime]


class CapabilityWriteError(Exception):
    """Explicit write-side failure with a stable error code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        super().__init__(message or error_code)
        self.error_code = error_code
        self.message = message or error_code


class CapabilityWriteService:
    """Register, update, and retire capability declarations."""

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

    @property
    def auditor(self) -> CapabilityWriteAuditor:
        return self._auditor

    def _now_iso(self) -> str:
        return self._clock().astimezone(timezone.utc).isoformat()

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
        """Create a new active capability entry. Fails if the id already exists."""

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
            snapshot = self._store.load()
            if any(item.capability_id == entry.capability_id for item in snapshot.entries):
                raise CapabilityWriteError(
                    "capability_already_exists",
                    f"capability {entry.capability_id!r} is already registered",
                )
            new_entries = snapshot.entries + (entry,)
            self._store.replace_entries(
                new_entries,
                generation=snapshot.generation + 1,
            )
        except CapabilityWriteError as exc:
            self._auditor.complete(
                capability_id=capability_id or "unknown",
                operation="register",
                success=False,
                correlation_id=correlation_id,
                error_code=exc.error_code,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise
        except WriteRegistryStoreError as exc:
            self._auditor.complete(
                capability_id=capability_id or "unknown",
                operation="register",
                success=False,
                correlation_id=correlation_id,
                error_code=exc.error_code,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise CapabilityWriteError(exc.error_code, str(exc)) from exc
        except ValueError as exc:
            self._auditor.complete(
                capability_id=capability_id or "unknown",
                operation="register",
                success=False,
                correlation_id=correlation_id,
                error_code="capability_validation_failed",
                metadata={"detail": str(exc)[:200]},
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise CapabilityWriteError(
                "capability_validation_failed", str(exc)
            ) from exc
        except Exception:
            self._auditor.complete(
                capability_id=capability_id or "unknown",
                operation="register",
                success=False,
                correlation_id=correlation_id,
                error_code="capability_register_failed",
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise

        self._auditor.complete(
            capability_id=entry.capability_id,
            operation="register",
            success=True,
            correlation_id=correlation_id,
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
        """Update an existing non-retired capability entry."""

        correlation_id = self._auditor.begin(
            capability_id=capability_id,
            operation="update",
            metadata={"fields": sorted(str(key) for key in payload.keys())[:16]},
            actor_type=actor_type,
            actor_id=actor_id,
        )
        try:
            snapshot = self._store.load()
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
            merged = {
                "capability_id": existing.capability_id,
                "domain": existing.domain,
                "capability_type": existing.capability_type,
                "version": existing.version,
                "status": "active",
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
                "version",
                "provider",
                "display_name",
                "dependencies",
                "tags",
                "scopes",
                "markets",
                "model_route",
                "cost_tier",
                "latency_class",
            ):
                if key in payload:
                    merged[key] = payload[key]
            if "domain" in payload and str(payload["domain"]) != existing.domain:
                raise CapabilityWriteError(
                    "capability_identity_immutable",
                    "domain cannot be changed after registration",
                )
            if (
                "capability_type" in payload
                and str(payload["capability_type"]) != existing.capability_type
            ):
                raise CapabilityWriteError(
                    "capability_identity_immutable",
                    "capability_type cannot be changed after registration",
                )
            if (
                "capability_id" in payload
                and str(payload["capability_id"]).strip() != existing.capability_id
            ):
                raise CapabilityWriteError(
                    "capability_identity_immutable",
                    "capability_id cannot be changed after registration",
                )
            entry = self._build_new_entry(merged, existing=existing)
            new_entries = tuple(
                entry if item.capability_id == capability_id else item
                for item in snapshot.entries
            )
            self._store.replace_entries(
                new_entries,
                generation=snapshot.generation + 1,
            )
        except CapabilityWriteError as exc:
            self._auditor.complete(
                capability_id=capability_id,
                operation="update",
                success=False,
                correlation_id=correlation_id,
                error_code=exc.error_code,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise
        except WriteRegistryStoreError as exc:
            self._auditor.complete(
                capability_id=capability_id,
                operation="update",
                success=False,
                correlation_id=correlation_id,
                error_code=exc.error_code,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise CapabilityWriteError(exc.error_code, str(exc)) from exc
        except ValueError as exc:
            self._auditor.complete(
                capability_id=capability_id,
                operation="update",
                success=False,
                correlation_id=correlation_id,
                error_code="capability_validation_failed",
                metadata={"detail": str(exc)[:200]},
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise CapabilityWriteError(
                "capability_validation_failed", str(exc)
            ) from exc
        except Exception:
            self._auditor.complete(
                capability_id=capability_id,
                operation="update",
                success=False,
                correlation_id=correlation_id,
                error_code="capability_update_failed",
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise

        self._auditor.complete(
            capability_id=entry.capability_id,
            operation="update",
            success=True,
            correlation_id=correlation_id,
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
        """Retire an active capability. Idempotent for already-retired ids."""

        correlation_id = self._auditor.begin(
            capability_id=capability_id,
            operation="retire",
            actor_type=actor_type,
            actor_id=actor_id,
        )
        try:
            snapshot = self._store.load()
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
                self._auditor.complete(
                    capability_id=capability_id,
                    operation="retire",
                    success=True,
                    correlation_id=correlation_id,
                    metadata={"already_retired": True},
                    actor_type=actor_type,
                    actor_id=actor_id,
                )
                return existing
            now = self._now_iso()
            entry = replace(
                existing,
                status="retired",
                retired_at=now,
                updated_at=now,
                generation=existing.generation + 1,
            )
            new_entries = tuple(
                entry if item.capability_id == capability_id else item
                for item in snapshot.entries
            )
            self._store.replace_entries(
                new_entries,
                generation=snapshot.generation + 1,
            )
        except CapabilityWriteError as exc:
            self._auditor.complete(
                capability_id=capability_id,
                operation="retire",
                success=False,
                correlation_id=correlation_id,
                error_code=exc.error_code,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise
        except WriteRegistryStoreError as exc:
            self._auditor.complete(
                capability_id=capability_id,
                operation="retire",
                success=False,
                correlation_id=correlation_id,
                error_code=exc.error_code,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise CapabilityWriteError(exc.error_code, str(exc)) from exc
        except Exception:
            self._auditor.complete(
                capability_id=capability_id,
                operation="retire",
                success=False,
                correlation_id=correlation_id,
                error_code="capability_retire_failed",
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise

        self._auditor.complete(
            capability_id=entry.capability_id,
            operation="retire",
            success=True,
            correlation_id=correlation_id,
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
    """Return the process-shared write service (tests may reset)."""

    global _SERVICE
    if reset or _SERVICE is None or path is not None:
        store = CapabilityWriteStore(path or default_write_registry_path())
        _SERVICE = CapabilityWriteService(store=store)
    return _SERVICE
