# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Atomicity and ownership regressions for the unified extension registry."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.plugins import ExtensionContract, ExtensionRegistry, PluginRegistryError


@dataclass
class _Template:
    template_id: str


class _Backend:
    def __init__(self) -> None:
        self.items: dict[str, object] = {}
        self.unregister_order: list[str] = []
        self.fail_register_after_write = False
        self.fail_unregister = False

    def contains(self, registration_id: str) -> bool:
        return registration_id in self.items

    def register(self, registration_id: str, implementation: object) -> None:
        self.items[registration_id] = implementation
        if self.fail_register_after_write:
            raise RuntimeError("registration failed after write")

    def unregister(self, registration_id: str, implementation: object) -> None:
        self.unregister_order.append(registration_id)
        if self.fail_unregister:
            raise RuntimeError("cleanup failed")
        if self.items.get(registration_id) is implementation:
            del self.items[registration_id]


def _registry(backend: _Backend | None = None) -> ExtensionRegistry:
    return ExtensionRegistry(
        {
            "report_template": ExtensionContract(
                identity_resolver=lambda implementation: implementation.template_id,
                validator=lambda implementation: isinstance(implementation, _Template),
                backend=backend,
            )
        }
    )


def _assert_error(error_code: str, callback: object) -> None:
    with pytest.raises(PluginRegistryError) as raised:
        callback()  # type: ignore[operator]
    assert raised.value.error_code == error_code


def test_registry_rejects_unified_and_native_collisions() -> None:
    backend = _Backend()
    registry = _registry(backend)
    first = _Template("daily")
    registry.register(
        plugin_id="first-plugin",
        extension_point="report_template",
        registration_id="daily",
        implementation=first,
    )

    _assert_error(
        "extension_registration_conflict",
        lambda: registry.register(
            plugin_id="second-plugin",
            extension_point="report_template",
            registration_id="daily",
            implementation=_Template("daily"),
        ),
    )

    backend.items["native-only"] = _Template("native-only")
    _assert_error(
        "native_registration_conflict",
        lambda: registry.register(
            plugin_id="second-plugin",
            extension_point="report_template",
            registration_id="native-only",
            implementation=_Template("native-only"),
        ),
    )


def test_backend_write_is_rolled_back_when_registration_raises() -> None:
    backend = _Backend()
    backend.fail_register_after_write = True
    registry = _registry(backend)

    _assert_error(
        "native_registry_registration_failed",
        lambda: registry.register(
            plugin_id="failing-plugin",
            extension_point="report_template",
            registration_id="daily",
            implementation=_Template("daily"),
        ),
    )

    assert backend.items == {}
    assert registry.registrations() == ()


def test_failed_rollback_retains_quarantined_owner_until_cleanup_retry() -> None:
    backend = _Backend()
    backend.fail_register_after_write = True
    backend.fail_unregister = True
    registry = _registry(backend)
    implementation = _Template("daily")

    with pytest.raises(PluginRegistryError) as raised:
        registry.register(
            plugin_id="failing-plugin",
            extension_point="report_template",
            registration_id="daily",
            implementation=implementation,
        )

    assert raised.value.error_code == "native_registry_rollback_failed"
    recovery_handle = raised.value.recovery_handle
    assert recovery_handle is not None
    assert recovery_handle.active is True
    assert backend.items["daily"] is implementation
    assert registry.registrations() == ()
    assert registry.get("report_template", "daily") is None
    _assert_error(
        "extension_registration_conflict",
        lambda: registry.register(
            plugin_id="replacement-plugin",
            extension_point="report_template",
            registration_id="daily",
            implementation=_Template("daily"),
        ),
    )

    backend.fail_unregister = False
    recovery_handle.unregister()

    assert recovery_handle.active is False
    assert backend.items == {}
    backend.fail_register_after_write = False
    replacement_handle = registry.register(
        plugin_id="replacement-plugin",
        extension_point="report_template",
        registration_id="daily",
        implementation=_Template("daily"),
    )
    assert replacement_handle.active is True


def test_unregister_removes_only_exact_owner_and_stale_handle_is_safe() -> None:
    backend = _Backend()
    registry = _registry(backend)
    original = _Template("daily")
    original_handle = registry.register(
        plugin_id="first-plugin",
        extension_point="report_template",
        registration_id="daily",
        implementation=original,
    )

    native_replacement = _Template("daily")
    backend.items["daily"] = native_replacement
    original_handle.unregister()

    assert backend.items["daily"] is native_replacement
    assert registry.get("report_template", "daily") is None

    del backend.items["daily"]
    replacement = _Template("daily")
    replacement_handle = registry.register(
        plugin_id="second-plugin",
        extension_point="report_template",
        registration_id="daily",
        implementation=replacement,
    )
    original_handle.unregister()

    assert replacement_handle.active is True
    assert registry.get("report_template", "daily").implementation is replacement  # type: ignore[union-attr]


def test_unregister_failure_retains_retryable_ownership() -> None:
    backend = _Backend()
    registry = _registry(backend)
    implementation = _Template("daily")
    handle = registry.register(
        plugin_id="example-plugin",
        extension_point="report_template",
        registration_id="daily",
        implementation=implementation,
    )
    backend.fail_unregister = True

    _assert_error("native_registry_unregistration_failed", handle.unregister)

    assert handle.active is True
    assert registry.get("report_template", "daily") is not None

    backend.fail_unregister = False
    handle.unregister()
    assert handle.active is False


def test_priority_order_and_metadata_are_detached_and_deeply_immutable() -> None:
    registry = _registry()
    metadata: dict[str, object] = {"nested": {"values": [1, "two"]}}
    registry.register(
        plugin_id="last-plugin",
        extension_point="report_template",
        registration_id="last",
        implementation=_Template("last"),
        priority=100,
    )
    registry.register(
        plugin_id="first-plugin",
        extension_point="report_template",
        registration_id="first",
        implementation=_Template("first"),
        priority=10,
        metadata=metadata,
    )
    registry.register(
        plugin_id="equal-plugin",
        extension_point="report_template",
        registration_id="equal",
        implementation=_Template("equal"),
        priority=10,
    )
    metadata["nested"] = {"changed": True}

    registrations = registry.registrations("report_template")

    assert [registration.registration_id for registration in registrations] == [
        "first",
        "equal",
        "last",
    ]
    first_metadata = registrations[0].metadata
    assert first_metadata["nested"]["values"] == (1, "two")  # type: ignore[index]
    with pytest.raises(TypeError):
        first_metadata["new"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        first_metadata["nested"]["new"] = True  # type: ignore[index]


def test_registry_rejects_identity_version_metadata_and_validator_drift() -> None:
    registry = _registry()
    _assert_error(
        "extension_identity_mismatch",
        lambda: registry.register(
            plugin_id="example-plugin",
            extension_point="report_template",
            registration_id="requested",
            implementation=_Template("canonical"),
        ),
    )
    _assert_error(
        "extension_contract_version_unsupported",
        lambda: registry.register(
            plugin_id="example-plugin",
            extension_point="report_template",
            registration_id="daily",
            implementation=_Template("daily"),
            contract_version="2",
        ),
    )
    _assert_error(
        "registration_metadata_invalid",
        lambda: registry.register(
            plugin_id="example-plugin",
            extension_point="report_template",
            registration_id="daily",
            implementation=_Template("daily"),
            metadata={"invalid": {1, 2}},
        ),
    )
    _assert_error(
        "extension_implementation_invalid",
        lambda: registry.register(
            plugin_id="example-plugin",
            extension_point="report_template",
            registration_id="daily",
            implementation=type("WrongTemplate", (), {"template_id": "daily"})(),
        ),
    )

    with pytest.raises(ValueError):
        ExtensionContract(
            identity_resolver=lambda implementation: implementation.template_id,
            supported_versions=frozenset({1}),  # type: ignore[arg-type]
        )


def test_default_contracts_fail_closed_until_native_validator_is_configured() -> None:
    registry = ExtensionRegistry()

    _assert_error(
        "extension_implementation_invalid",
        lambda: registry.register(
            plugin_id="example-plugin",
            extension_point="report_template",
            registration_id="daily",
            implementation=_Template("daily"),
        ),
    )
