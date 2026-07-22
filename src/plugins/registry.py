# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Ownership-aware registration for the official plugin extension points."""

from __future__ import annotations

import logging
import math
import re
import threading
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Literal, Mapping, Protocol, TypeAlias

from src.utils.sanitize import log_safe_exception

from .errors import PluginContextClosedError, PluginRegistryError
from .manifest import API_MAJOR_PATTERN, PLUGIN_ID_PATTERN


logger = logging.getLogger(__name__)

ExtensionPoint = Literal[
    "data_provider",
    "analysis_strategy",
    "agent_tool",
    "notification_channel",
    "report_template",
    "event_hook",
]
EXTENSION_POINTS: tuple[ExtensionPoint, ...] = (
    "data_provider",
    "analysis_strategy",
    "agent_tool",
    "notification_channel",
    "report_template",
    "event_hook",
)
JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | tuple["JSONValue", ...] | Mapping[str, "JSONValue"]
IdentityResolver: TypeAlias = Callable[[object], str]
ImplementationValidator: TypeAlias = Callable[[object], bool]

_REGISTRATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MAX_METADATA_DEPTH = 20


class NativeRegistrationBackend(Protocol):
    """Adapter contract for one existing point-specific registry.

    ``unregister`` must be idempotent and remove only ``implementation``. The
    unified registry invokes it after a failed ``register`` because a backend
    may have written before raising.
    """

    def contains(self, registration_id: str) -> bool:
        """Return whether the canonical native key is already occupied."""

    def register(self, registration_id: str, implementation: object) -> None:
        """Register one implementation under its canonical native key."""

    def unregister(self, registration_id: str, implementation: object) -> None:
        """Remove exactly the supplied implementation when it is still owned."""


def _accept_implementation(implementation: object) -> bool:
    del implementation
    return True


def _attribute_identity(attribute: str) -> IdentityResolver:
    def resolve(implementation: object) -> str:
        return getattr(implementation, attribute)

    return resolve


@dataclass(frozen=True, slots=True)
class ExtensionContract:
    """Validation and optional native delegation for one extension point."""

    identity_resolver: IdentityResolver
    validator: ImplementationValidator = _accept_implementation
    supported_versions: frozenset[str] = field(default_factory=lambda: frozenset({"1"}))
    backend: NativeRegistrationBackend | None = None

    def __post_init__(self) -> None:
        versions = frozenset(self.supported_versions)
        if not callable(self.identity_resolver) or not callable(self.validator):
            raise TypeError("extension contract callbacks must be callable")
        if not versions or any(
            type(version) is not str or API_MAJOR_PATTERN.fullmatch(version) is None
            for version in versions
        ):
            raise ValueError("supported extension versions must be positive majors")
        object.__setattr__(self, "supported_versions", versions)


def default_extension_contracts() -> Mapping[ExtensionPoint, ExtensionContract]:
    """Return attribute-level contracts for all extension points in ADR-007."""

    contracts: dict[ExtensionPoint, ExtensionContract] = {
        "data_provider": ExtensionContract(_attribute_identity("provider_id")),
        "analysis_strategy": ExtensionContract(_attribute_identity("name")),
        "agent_tool": ExtensionContract(_attribute_identity("name")),
        "notification_channel": ExtensionContract(_attribute_identity("channel_id")),
        "report_template": ExtensionContract(_attribute_identity("template_id")),
        "event_hook": ExtensionContract(_attribute_identity("hook_id")),
    }
    return MappingProxyType(contracts)


def _freeze_json_value(
    value: object,
    *,
    depth: int,
    active_containers: frozenset[int],
) -> JSONValue:
    if depth > _MAX_METADATA_DEPTH:
        raise ValueError("metadata nesting is too deep")
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("metadata numbers must be finite")
        return value
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active_containers:
            raise ValueError("metadata must not contain cycles")
        nested_active = active_containers | {identity}
        frozen: dict[str, JSONValue] = {}
        for key, nested_value in value.items():
            if type(key) is not str:
                raise TypeError("metadata object keys must be strings")
            frozen[key] = _freeze_json_value(
                nested_value,
                depth=depth + 1,
                active_containers=nested_active,
            )
        return MappingProxyType(frozen)
    if type(value) in {list, tuple}:
        identity = id(value)
        if identity in active_containers:
            raise ValueError("metadata must not contain cycles")
        nested_active = active_containers | {identity}
        return tuple(
            _freeze_json_value(
                item,
                depth=depth + 1,
                active_containers=nested_active,
            )
            for item in value
        )
    raise TypeError("metadata values must be JSON-compatible")


def freeze_json_metadata(metadata: Mapping[str, object] | None) -> Mapping[str, JSONValue]:
    """Validate, detach, and deeply freeze registration metadata."""

    if metadata is None:
        return MappingProxyType({})
    frozen = _freeze_json_value(metadata, depth=0, active_containers=frozenset())
    if not isinstance(frozen, Mapping):
        raise TypeError("registration metadata must be an object")
    return frozen


@dataclass(frozen=True, slots=True)
class ExtensionRegistration:
    """Immutable view of one active extension registration."""

    extension_point: ExtensionPoint
    registration_id: str
    plugin_id: str
    implementation: object
    contract_version: str
    priority: int
    registration_order: int
    metadata: Mapping[str, JSONValue]


@dataclass(frozen=True, slots=True)
class _RegistryEntry:
    registration: ExtensionRegistration
    token: object


class RegistrationHandle:
    """Opaque, idempotent owner token for one exact registration."""

    __slots__ = ("_extension_point", "_registration_id", "_registry", "_token")

    def __init__(
        self,
        registry: "ExtensionRegistry",
        extension_point: ExtensionPoint,
        registration_id: str,
        token: object,
    ) -> None:
        self._registry = registry
        self._extension_point = extension_point
        self._registration_id = registration_id
        self._token = token

    @property
    def extension_point(self) -> ExtensionPoint:
        """Return the extension point owned by this handle."""

        return self._extension_point

    @property
    def registration_id(self) -> str:
        """Return the canonical ID owned by this handle."""

        return self._registration_id

    @property
    def active(self) -> bool:
        """Return whether this exact opaque token still owns the registration."""

        return self._registry._owns(
            self._extension_point,
            self._registration_id,
            self._token,
        )

    def unregister(self) -> None:
        """Remove only the exact registration originally returned to this handle."""

        self._registry._unregister(
            self._extension_point,
            self._registration_id,
            self._token,
        )


class ExtensionRegistry:
    """Serialize extension registration, native delegation, and owner cleanup."""

    def __init__(
        self,
        contracts: Mapping[ExtensionPoint, ExtensionContract] | None = None,
    ) -> None:
        configured = dict(default_extension_contracts())
        if contracts is not None:
            for extension_point, contract in contracts.items():
                if extension_point not in EXTENSION_POINTS:
                    raise ValueError("unsupported extension point")
                if not isinstance(contract, ExtensionContract):
                    raise TypeError("contracts must contain ExtensionContract values")
                configured[extension_point] = contract
        self._contracts = MappingProxyType(configured)
        self._entries: dict[tuple[ExtensionPoint, str], _RegistryEntry] = {}
        self._next_order = 0
        self._lock = threading.RLock()

    def register(
        self,
        *,
        plugin_id: str,
        extension_point: ExtensionPoint,
        registration_id: str,
        implementation: object,
        contract_version: str = "1",
        priority: int = 100,
        metadata: Mapping[str, object] | None = None,
    ) -> RegistrationHandle:
        """Validate and atomically register one plugin-owned implementation."""

        contract = self._contracts.get(extension_point)
        if contract is None:
            raise PluginRegistryError("extension_point_unsupported")
        if type(plugin_id) is not str or PLUGIN_ID_PATTERN.fullmatch(plugin_id) is None:
            raise PluginRegistryError("plugin_id_invalid")
        if (
            type(registration_id) is not str
            or len(registration_id) > 128
            or _REGISTRATION_ID_PATTERN.fullmatch(registration_id) is None
        ):
            raise PluginRegistryError("registration_id_invalid")
        if type(contract_version) is not str or contract_version not in contract.supported_versions:
            raise PluginRegistryError("extension_contract_version_unsupported")
        if type(priority) is not int:
            raise PluginRegistryError("registration_priority_invalid")

        try:
            canonical_id = contract.identity_resolver(implementation)
        except Exception as exc:  # broad-exception: fallback_recorded - Plugin identity failures are safely logged and mapped to a stable registry error.
            log_safe_exception(
                logger,
                "Plugin extension identity resolution failed",
                exc,
                error_code="extension_identity_invalid",
                context={"extension_point": extension_point, "plugin_id": plugin_id},
            )
            raise PluginRegistryError("extension_identity_invalid") from None
        if type(canonical_id) is not str or canonical_id != registration_id:
            raise PluginRegistryError("extension_identity_mismatch")

        try:
            implementation_valid = contract.validator(implementation)
        except Exception as exc:  # broad-exception: fallback_recorded - Plugin validation failures are safely logged and mapped to a stable registry error.
            log_safe_exception(
                logger,
                "Plugin extension validation failed",
                exc,
                error_code="extension_implementation_invalid",
                context={"extension_point": extension_point, "plugin_id": plugin_id},
            )
            raise PluginRegistryError("extension_implementation_invalid") from None
        if implementation_valid is not True:
            raise PluginRegistryError("extension_implementation_invalid")

        try:
            frozen_metadata = freeze_json_metadata(metadata)
        except (TypeError, ValueError):
            raise PluginRegistryError("registration_metadata_invalid") from None
        except Exception as exc:  # broad-exception: fallback_recorded - Custom mapping failures are safely logged and mapped to invalid metadata.
            log_safe_exception(
                logger,
                "Plugin registration metadata could not be read",
                exc,
                error_code="registration_metadata_invalid",
                context={"extension_point": extension_point, "plugin_id": plugin_id},
            )
            raise PluginRegistryError("registration_metadata_invalid") from None

        key = (extension_point, registration_id)
        with self._lock:
            if key in self._entries:
                raise PluginRegistryError("extension_registration_conflict")
            if contract.backend is not None:
                try:
                    native_collision = contract.backend.contains(registration_id)
                except Exception as exc:  # broad-exception: fallback_recorded - Native preflight failures are safely logged before registration is rejected.
                    log_safe_exception(
                        logger,
                        "Native extension collision preflight failed",
                        exc,
                        error_code="native_registry_preflight_failed",
                        context={"extension_point": extension_point, "plugin_id": plugin_id},
                    )
                    raise PluginRegistryError("native_registry_preflight_failed") from None
                if native_collision:
                    raise PluginRegistryError("native_registration_conflict")

            token = object()
            registration = ExtensionRegistration(
                extension_point=extension_point,
                registration_id=registration_id,
                plugin_id=plugin_id,
                implementation=implementation,
                contract_version=contract_version,
                priority=priority,
                registration_order=self._next_order,
                metadata=frozen_metadata,
            )
            try:
                if contract.backend is not None:
                    contract.backend.register(registration_id, implementation)
                self._entries[key] = _RegistryEntry(registration=registration, token=token)
            except Exception as exc:  # broad-exception: fallback_recorded - Partial native registration is rolled back and recorded before a typed failure is returned.
                rollback_failed = False
                if contract.backend is not None:
                    try:
                        contract.backend.unregister(registration_id, implementation)
                    except Exception as rollback_exc:  # broad-exception: fallback_recorded - A failed exact-owner rollback is safely recorded for operators.
                        rollback_failed = True
                        log_safe_exception(
                            logger,
                            "Native extension registration rollback failed",
                            rollback_exc,
                            error_code="native_registry_rollback_failed",
                            context={"extension_point": extension_point, "plugin_id": plugin_id},
                        )
                if rollback_failed:
                    error_code = "native_registry_rollback_failed"
                elif contract.backend is not None:
                    error_code = "native_registry_registration_failed"
                else:
                    error_code = "extension_registry_registration_failed"
                log_safe_exception(
                    logger,
                    "Plugin extension registration failed",
                    exc,
                    error_code=error_code,
                    context={"extension_point": extension_point, "plugin_id": plugin_id},
                )
                raise PluginRegistryError(error_code) from None
            self._next_order += 1
            return RegistrationHandle(self, extension_point, registration_id, token)

    def registrations(
        self,
        extension_point: ExtensionPoint | None = None,
    ) -> tuple[ExtensionRegistration, ...]:
        """Return an immutable snapshot ordered by priority then registration order."""

        with self._lock:
            values = tuple(
                entry.registration
                for entry in self._entries.values()
                if extension_point is None or entry.registration.extension_point == extension_point
            )
        return tuple(sorted(values, key=lambda item: (item.priority, item.registration_order)))

    def get(
        self,
        extension_point: ExtensionPoint,
        registration_id: str,
    ) -> ExtensionRegistration | None:
        """Return one active registration without exposing its owner token."""

        with self._lock:
            entry = self._entries.get((extension_point, registration_id))
            return None if entry is None else entry.registration

    def _owns(
        self,
        extension_point: ExtensionPoint,
        registration_id: str,
        token: object,
    ) -> bool:
        with self._lock:
            entry = self._entries.get((extension_point, registration_id))
            return entry is not None and entry.token is token

    def _unregister(
        self,
        extension_point: ExtensionPoint,
        registration_id: str,
        token: object,
    ) -> None:
        key = (extension_point, registration_id)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.token is not token:
                return
            contract = self._contracts[extension_point]
            if contract.backend is not None:
                try:
                    contract.backend.unregister(
                        registration_id,
                        entry.registration.implementation,
                    )
                except Exception as exc:  # broad-exception: fallback_recorded - Native cleanup failure is recorded while ownership remains retryable.
                    log_safe_exception(
                        logger,
                        "Native plugin extension cleanup failed",
                        exc,
                        error_code="native_registry_unregistration_failed",
                        context={
                            "extension_point": extension_point,
                            "plugin_id": entry.registration.plugin_id,
                        },
                    )
                    raise PluginRegistryError("native_registry_unregistration_failed") from None
            current = self._entries.get(key)
            if current is not None and current.token is token:
                del self._entries[key]


class PluginContext:
    """Short-lived owner context valid only during one plugin ``onload`` call."""

    def __init__(self, plugin_id: str, registry: ExtensionRegistry) -> None:
        self._plugin_id = plugin_id
        self._registry = registry
        self._handles: list[RegistrationHandle] = []
        self._active = True
        self._lock = threading.RLock()

    @property
    def active(self) -> bool:
        """Return whether registration is still allowed."""

        with self._lock:
            return self._active

    @property
    def handles(self) -> tuple[RegistrationHandle, ...]:
        """Return every handle created during this transition in creation order."""

        with self._lock:
            return tuple(self._handles)

    def register(
        self,
        extension_point: ExtensionPoint,
        registration_id: str,
        implementation: object,
        *,
        contract_version: str = "1",
        priority: int = 100,
        metadata: Mapping[str, object] | None = None,
    ) -> RegistrationHandle:
        """Register one extension and retain its handle for manager cleanup."""

        with self._lock:
            if not self._active:
                raise PluginContextClosedError("plugin_context_closed")
            handle = self._registry.register(
                plugin_id=self._plugin_id,
                extension_point=extension_point,
                registration_id=registration_id,
                implementation=implementation,
                contract_version=contract_version,
                priority=priority,
                metadata=metadata,
            )
            self._handles.append(handle)
            return handle

    def close(self) -> None:
        """Reject all future registration attempts."""

        with self._lock:
            self._active = False
