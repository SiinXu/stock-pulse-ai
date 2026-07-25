# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Native runtime adapter for plugin-owned notification channels."""

from __future__ import annotations

import inspect
import logging
import threading
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Literal, Mapping, Protocol, TypeAlias

from src.notification_routing import ROUTABLE_NOTIFICATION_CHANNEL_SET
from src.utils.sanitize import log_safe_exception

from .manifest import PLUGIN_ID_PATTERN
from .registry import (
    ExtensionContract,
    JSONValue,
    freeze_json_metadata,
)

if TYPE_CHECKING:
    from src.config import Config


logger = logging.getLogger(__name__)

_RESERVED_NOTIFICATION_CHANNEL_IDS = frozenset(
    (*ROUTABLE_NOTIFICATION_CHANNEL_SET, "unknown", "__context__")
)


@dataclass(frozen=True, slots=True)
class NotificationRequest:
    """Immutable, core-prepared request passed to one plugin adapter."""

    content: str
    route_type: str | None
    severity: str | None
    image_bytes: bytes | None
    stock_codes: tuple[str, ...]
    metadata: Mapping[str, JSONValue] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        if type(self.content) is not str:
            raise TypeError("notification content must be a string")
        if self.route_type is not None and type(self.route_type) is not str:
            raise TypeError("notification route_type must be a string or None")
        if self.severity is not None and type(self.severity) is not str:
            raise TypeError("notification severity must be a string or None")
        if self.image_bytes is not None and type(self.image_bytes) is not bytes:
            raise TypeError("notification image_bytes must be bytes or None")
        if type(self.stock_codes) is not tuple or any(
            type(stock_code) is not str for stock_code in self.stock_codes
        ):
            raise TypeError("notification stock_codes must be a tuple of strings")
        object.__setattr__(self, "metadata", freeze_json_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class NotificationAdapterResult:
    """Adapter-owned delivery result mapped by the core dispatch authority."""

    success: bool
    error_code: str | None = None
    retryable: bool = False
    diagnostics: str | None = None

    def __post_init__(self) -> None:
        if type(self.success) is not bool:
            raise TypeError("notification adapter success must be a boolean")
        if self.error_code is not None and type(self.error_code) is not str:
            raise TypeError("notification adapter error_code must be a string or None")
        if type(self.retryable) is not bool:
            raise TypeError("notification adapter retryable must be a boolean")
        if self.diagnostics is not None and type(self.diagnostics) is not str:
            raise TypeError("notification adapter diagnostics must be a string or None")


class NotificationChannelAdapter(Protocol):
    """Executable notification adapter created from the application config."""

    channel_id: str
    display_name: str

    def is_available(self) -> bool:
        """Return whether the adapter can receive a dispatch now."""

        ...

    def send(self, request: NotificationRequest) -> NotificationAdapterResult:
        """Attempt one delivery after the core has completed shared policy checks."""

        ...


NotificationChannelFactory: TypeAlias = Callable[
    ["Config"],
    NotificationChannelAdapter,
]


@dataclass(frozen=True, slots=True)
class NotificationChannelSnapshot:
    """One exact adapter retained by a stable dispatch snapshot."""

    channel_id: str
    display_name: str
    adapter: NotificationChannelAdapter


@dataclass(frozen=True, slots=True)
class NotificationChannelLifecycleSnapshot:
    """One canonical ID retained for read-only lifecycle diagnostics."""

    channel_id: str
    display_name: str
    state: Literal["enabled", "disabled", "failed", "unloaded"]


@dataclass(frozen=True, slots=True)
class _OwnedNotificationChannel:
    """Retain one registration-owned adapter with deterministic ordering metadata."""

    factory: object
    owner_token: object
    snapshot: NotificationChannelSnapshot
    registration_order: int


def _valid_channel_identity(value: object) -> bool:
    """Return whether a value is a canonical notification channel ID."""

    return (
        type(value) is str
        and len(value) <= 128
        and PLUGIN_ID_PATTERN.fullmatch(value) is not None
    )


def _valid_display_name(value: object) -> bool:
    """Return whether a value is a bounded non-empty display name."""

    return type(value) is str and 0 < len(value.strip()) <= 200


def _accepts_positional_call(
    implementation: object,
    argument_count: int,
) -> bool:
    """Return whether a callable accepts the core positional call shape."""

    signature = inspect.signature(implementation)
    arguments = (object(),) * argument_count
    signature.bind(*arguments)
    return True


def validate_notification_channel_factory(implementation: object) -> bool:
    """Return whether an implementation has the documented factory shape."""

    if not callable(implementation):
        return False
    try:
        if not _accepts_positional_call(implementation, 1):
            return False
    except Exception as exc:  # broad-exception: fallback_recorded - hostile factory descriptors and signatures are safely recorded before plugin code executes
        log_safe_exception(
            logger,
            "Notification channel factory validation failed",
            exc,
            error_code="notification_channel_factory_invalid",
            exception_redaction_values=(),
        )
        return False
    return True


def _build_adapter_snapshot(
    adapter: object,
    channel_id: str,
) -> NotificationChannelSnapshot | None:
    try:
        adapter_channel_id = getattr(adapter, "channel_id")
        adapter_display_name = getattr(adapter, "display_name")
        availability_probe = getattr(adapter, "is_available")
        sender = getattr(adapter, "send")
        if not (
            adapter_channel_id == channel_id
            and _valid_channel_identity(adapter_channel_id)
            and _valid_display_name(adapter_display_name)
            and callable(availability_probe)
            and callable(sender)
        ):
            return None
        if not (
            _accepts_positional_call(availability_probe, 0)
            and _accepts_positional_call(sender, 1)
        ):
            return None
        return NotificationChannelSnapshot(
            channel_id=channel_id,
            display_name=adapter_display_name,
            adapter=adapter,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - hostile adapter attributes are safely recorded and fail closed before publication
        log_safe_exception(
            logger,
            "Notification channel adapter validation failed",
            exc,
            error_code="notification_channel_adapter_invalid",
            context={"channel": channel_id},
            exception_redaction_values=(),
        )
        return None


def _safe_display_name(implementation: object, fallback: str) -> str:
    """Read an optional display name without making it part of v1 factory shape."""

    try:
        display_name = getattr(implementation, "display_name", fallback)
    except Exception as exc:  # broad-exception: fallback_recorded - optional diagnostic identity cannot affect publication validation
        log_safe_exception(
            logger,
            "Notification channel display name could not be read",
            exc,
            error_code="notification_channel_display_name_invalid",
            context={"channel": fallback},
            exception_redaction_values=(),
        )
        return fallback
    return display_name if _valid_display_name(display_name) else fallback


class NotificationChannelRegistry:
    """Exact-owner native registry consumed by ``NotificationService``."""

    def __init__(
        self,
        config_provider: Callable[[], object],
        *,
        reserved_channel_ids: frozenset[str] = _RESERVED_NOTIFICATION_CHANNEL_IDS,
    ) -> None:
        if not callable(config_provider):
            raise TypeError("notification config provider must be callable")
        if type(reserved_channel_ids) is not frozenset or any(
            not _valid_channel_identity(channel_id)
            and channel_id != "__context__"
            for channel_id in reserved_channel_ids
        ):
            raise TypeError("reserved notification channel IDs are invalid")
        self._config_provider = config_provider
        self._reserved_channel_ids = reserved_channel_ids
        self._entries: dict[str, _OwnedNotificationChannel] = {}
        self._lifecycle: dict[str, NotificationChannelLifecycleSnapshot] = {}
        self._next_order = 0
        self._lock = threading.RLock()

    def contains(self, registration_id: str) -> bool:
        """Return whether a built-in or plugin channel owns the canonical ID."""

        with self._lock:
            return (
                registration_id in self._reserved_channel_ids
                or registration_id in self._entries
            )

    def config_snapshot(self) -> object:
        """Return the Config authority used for the next adapter publication."""

        return self._config_provider()

    def validate_factory(self, implementation: object) -> bool:
        """Validate the accepted v1 ``Callable[[Config], Adapter]`` shape."""

        return validate_notification_channel_factory(implementation)

    def register(
        self,
        registration_id: str,
        implementation: object,
    ) -> object:
        """Construct an adapter and return its opaque publication owner token."""

        if not self.validate_factory(implementation):
            raise TypeError("notification channel factory is invalid")
        owner_token = object()
        factory_display_name = _safe_display_name(
            implementation,
            registration_id,
        )
        with self._lock:
            if (
                registration_id in self._reserved_channel_ids
                or registration_id in self._entries
            ):
                raise ValueError("notification channel ID is already registered")
        try:
            config = self._config_provider()
            adapter = implementation(config)  # type: ignore[operator]
        except Exception as exc:  # broad-exception: fallback_recorded - factory failures are isolated and redacted before the registry rejects them
            with self._lock:
                self._lifecycle[registration_id] = (
                    NotificationChannelLifecycleSnapshot(
                        channel_id=registration_id,
                        display_name=factory_display_name,
                        state="failed",
                    )
                )
            log_safe_exception(
                logger,
                "Notification channel factory failed",
                exc,
                error_code="notification_channel_factory_failed",
                context={"channel": registration_id},
                exception_redaction_values=(),
            )
            raise RuntimeError("notification channel factory failed") from None
        snapshot = _build_adapter_snapshot(
            adapter,
            registration_id,
        )
        if snapshot is None:
            failed_display_name = _safe_display_name(
                adapter,
                factory_display_name,
            )
            with self._lock:
                self._lifecycle[registration_id] = (
                    NotificationChannelLifecycleSnapshot(
                        channel_id=registration_id,
                        display_name=failed_display_name,
                        state="failed",
                    )
                )
            raise TypeError("notification channel adapter is invalid")

        with self._lock:
            if (
                registration_id in self._reserved_channel_ids
                or registration_id in self._entries
            ):
                raise ValueError("notification channel ID is already registered")
            self._entries[registration_id] = _OwnedNotificationChannel(
                factory=implementation,
                owner_token=owner_token,
                snapshot=snapshot,
                registration_order=self._next_order,
            )
            self._lifecycle[registration_id] = (
                NotificationChannelLifecycleSnapshot(
                    channel_id=registration_id,
                    display_name=snapshot.display_name,
                    state="enabled",
                )
            )
            self._next_order += 1
        return owner_token

    def unregister(self, registration_id: str, implementation: object) -> None:
        """Remove only the adapter created by the exact registered factory."""

        with self._lock:
            entry = self._entries.get(registration_id)
            if entry is not None and entry.factory is implementation:
                del self._entries[registration_id]
                self._lifecycle[registration_id] = (
                    NotificationChannelLifecycleSnapshot(
                        channel_id=registration_id,
                        display_name=entry.snapshot.display_name,
                        state="disabled",
                    )
                )

    def snapshot(self) -> tuple[NotificationChannelSnapshot, ...]:
        """Return active plugin adapters in deterministic registration order."""

        with self._lock:
            entries = tuple(self._entries.values())
        return tuple(
            entry.snapshot
            for entry in sorted(entries, key=lambda item: item.registration_order)
        )

    def snapshot_for_exact_owners(
        self,
        owners: Mapping[str, object],
    ) -> tuple[NotificationChannelSnapshot, ...]:
        """Return adapters paired to exact opaque native registration owners."""

        owner_snapshot = dict(owners)
        with self._lock:
            entries = tuple(
                entry
                for channel_id, entry in self._entries.items()
                if owner_snapshot.get(channel_id) is entry.owner_token
            )
        return tuple(
            entry.snapshot
            for entry in sorted(entries, key=lambda item: item.registration_order)
        )

    def lifecycle_snapshot(
        self,
    ) -> tuple[NotificationChannelLifecycleSnapshot, ...]:
        """Return known canonical IDs in first-publication insertion order."""

        with self._lock:
            return tuple(self._lifecycle.values())

    def mark_unloaded(self) -> None:
        """Mark root-owned disabled adapters as terminally unloaded."""

        with self._lock:
            for channel_id, entry in tuple(self._lifecycle.items()):
                if entry.state != "disabled":
                    continue
                self._lifecycle[channel_id] = (
                    NotificationChannelLifecycleSnapshot(
                        channel_id=entry.channel_id,
                        display_name=entry.display_name,
                        state="unloaded",
                    )
                )


def available_notification_channel_snapshot(
    snapshot: tuple[NotificationChannelSnapshot, ...],
) -> tuple[NotificationChannelSnapshot, ...]:
    """Probe one stable enabled snapshot with per-adapter isolation."""

    available: list[NotificationChannelSnapshot] = []
    for entry in snapshot:
        try:
            result = entry.adapter.is_available()
        except Exception as exc:  # broad-exception: fallback_recorded - one availability failure cannot suppress later plugin channels
            log_safe_exception(
                logger,
                "Notification channel availability probe failed",
                exc,
                error_code="notification_channel_availability_failed",
                context={"channel": entry.channel_id},
                exception_redaction_values=(),
            )
            continue
        if result is True:
            available.append(entry)
        elif result is not False:
            logger.warning(
                "Notification channel availability probe returned an invalid value "
                "error_code=notification_channel_availability_invalid channel=%s",
                entry.channel_id,
            )
    return tuple(available)


def build_notification_channel_extension_contract(
    registry: NotificationChannelRegistry,
) -> ExtensionContract:
    """Build the notification point contract bound to its native registry."""

    if not isinstance(registry, NotificationChannelRegistry):
        raise TypeError("notification channel registry is invalid")
    return ExtensionContract(
        identity_resolver=None,
        validator=registry.validate_factory,
        backend=registry,
    )
