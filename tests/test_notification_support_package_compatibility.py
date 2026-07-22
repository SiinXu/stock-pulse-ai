"""Compatibility guards for notification support package convergence."""

import ast
import hashlib
import importlib
import inspect
from pathlib import Path
import subprocess
import sys
import textwrap
from types import FunctionType
from typing import Any, get_type_hints
from unittest.mock import patch

import pytest


MODULES = {
    "src.notification_capabilities": (
        "src.notification_parts.capabilities",
        (
            "Any",
            "CHANNEL_PROFILES",
            "CHANNEL_RENDERER_PRESETS",
            "ChannelProfile",
            "Dict",
            "Mapping",
            "Optional",
            "PreparedMessage",
            "RendererPreset",
            "Tuple",
            "all_channel_profiles",
            "all_renderer_presets",
            "annotations",
            "dataclass",
            "get_channel_profile",
            "get_renderer_preset",
            "normalize_channel_name",
        ),
        "b68a8a85759b10266e0e1c62dda9f0901bfde20b03f1d683412e6ddaa6a739e0",
    ),
    "src.notification_contracts": (
        "src.notification_parts.contracts",
        (
            "Any",
            "FEISHU_APP_BOT_ENV_GROUP",
            "FEISHU_STATIC_ENV_GROUPS",
            "FEISHU_WEBHOOK_ENV_GROUP",
            "Mapping",
            "Tuple",
            "annotations",
            "is_dingtalk_session_webhook_url",
            "is_feishu_app_bot_configured",
            "is_feishu_app_bot_env_configured",
            "is_feishu_static_configured",
            "is_feishu_static_env_configured",
            "parse_qsl",
            "urlsplit",
        ),
        "e1710b474c9ef0b83a0b047a5a0ea24033a5a55721d754ad1db765ced2e2c906",
    ),
    "src.notification_noise": (
        "src.notification_parts.noise",
        (
            "DEFAULT_NOTIFICATION_SEVERITY_BY_ROUTE",
            "Dict",
            "NOTIFICATION_SEVERITIES",
            "NOTIFICATION_SEVERITY_RANK",
            "NotificationNoiseDecision",
            "Optional",
            "P4_NOISE_ENV_KEYS",
            "Tuple",
            "ZoneInfo",
            "ZoneInfoNotFoundError",
            "annotations",
            "dataclass",
            "datetime",
            "evaluate_notification_noise",
            "hashlib",
            "is_supported_notification_severity",
            "is_time_in_quiet_hours",
            "log_safe_exception",
            "logger",
            "logging",
            "normalize_notification_severity",
            "parse_notification_quiet_hours",
            "re",
            "record_notification_noise",
            "release_notification_noise",
            "reset_notification_noise_state",
            "threading",
            "uuid",
            "validate_notification_timezone",
        ),
        "161104785d8435e353bbabb70fb8936038f1ac5bb02f93a1fc6a969b7eb5a91c",
    ),
    "src.notification_routing": (
        "src.notification_parts.route_config",
        (
            "Dict",
            "Iterable",
            "List",
            "NOTIFICATION_ROUTE_CONFIGS",
            "Optional",
            "ROUTABLE_NOTIFICATION_CHANNELS",
            "ROUTABLE_NOTIFICATION_CHANNEL_SET",
            "Tuple",
            "annotations",
            "get_notification_route_config",
            "parse_notification_route_channels",
            "split_notification_route_channels",
        ),
        "16cdd3c0160ce82f1458d5e1db74344a2680cb9423952d75dc77d4c96b0a8ae1",
    ),
}

_MODULE_METADATA = {
    "__all__",
    "__builtins__",
    "__cached__",
    "__file__",
    "__loader__",
    "__name__",
    "__package__",
    "__spec__",
}


def _source_definitions(module) -> dict[str, ast.AST]:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def _descriptor_function(descriptor: Any):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    if isinstance(descriptor, FunctionType):
        return descriptor
    return None


@pytest.mark.parametrize("legacy_name", MODULES)
def test_facades_preserve_complete_module_surface(legacy_name: str) -> None:
    implementation_name, expected_exports, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    legacy = importlib.import_module(legacy_name)

    assert tuple(sorted(name for name in vars(legacy) if not name.startswith("_"))) == (
        expected_exports
    )
    assert legacy.__all__ == expected_exports
    assert implementation.__all__ == expected_exports

    definitions = _source_definitions(implementation)
    for name, implementation_value in vars(implementation).items():
        if name in _MODULE_METADATA:
            continue
        assert name in vars(legacy), name
        legacy_value = getattr(legacy, name)
        if name in definitions and isinstance(implementation_value, FunctionType):
            assert legacy_value is not implementation_value, name
        else:
            assert legacy_value is implementation_value, name

    if legacy_name == "src.notification_noise":
        assert legacy.logger.name == legacy_name


@pytest.mark.parametrize("legacy_name", MODULES)
def test_facades_preserve_callable_contracts(legacy_name: str) -> None:
    implementation_name, _, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    legacy = importlib.import_module(legacy_name)

    for name, node in _source_definitions(implementation).items():
        legacy_value = getattr(legacy, name)
        implementation_value = getattr(implementation, name)
        assert legacy_value.__module__ == legacy_name
        assert inspect.signature(legacy_value) == inspect.signature(implementation_value)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert legacy_value is not implementation_value
            assert implementation_value.__module__ == implementation_name
            assert legacy_value.__globals__ is vars(legacy)
            assert inspect.unwrap(legacy_value).__globals__ is vars(legacy)
            assert legacy_value.__annotations__ == implementation_value.__annotations__
            assert get_type_hints(
                legacy_value,
                globalns=vars(legacy),
                localns=vars(legacy),
            ) == get_type_hints(
                implementation_value,
                globalns=vars(implementation),
                localns=vars(implementation),
            )
            continue

        assert legacy_value is implementation_value
        get_type_hints(legacy_value, globalns=vars(legacy), localns=vars(legacy))
        for descriptor_name, descriptor in vars(legacy_value).items():
            function = _descriptor_function(descriptor)
            if function is None:
                continue
            assert function.__module__ == legacy_name, descriptor_name
            unwrapped = inspect.unwrap(function)
            assert unwrapped.__module__ == legacy_name, descriptor_name
            if unwrapped.__globals__.get("__name__") != "dataclasses":
                assert unwrapped.__globals__ is vars(legacy), descriptor_name


@pytest.mark.parametrize(
    "module_name",
    ("src.notification_capabilities", "src.notification_parts.capabilities"),
)
def test_capabilities_patch_seam_works_through_both_paths(module_name: str) -> None:
    module = importlib.import_module(module_name)
    with patch.object(module, "normalize_channel_name", return_value="wechat"):
        assert module.get_channel_profile(object()) is module.CHANNEL_PROFILES["wechat"]


@pytest.mark.parametrize(
    "module_name",
    ("src.notification_contracts", "src.notification_parts.contracts"),
)
def test_contract_patch_seam_works_through_both_paths(module_name: str) -> None:
    module = importlib.import_module(module_name)
    with patch.object(module, "_has_env_group", return_value=True) as has_group:
        assert module.is_feishu_app_bot_env_configured({}) is True
    has_group.assert_called_once_with({}, module.FEISHU_APP_BOT_ENV_GROUP)


@pytest.mark.parametrize(
    "module_name",
    ("src.notification_noise", "src.notification_parts.noise"),
)
def test_noise_patch_seam_works_through_both_paths(module_name: str) -> None:
    module = importlib.import_module(module_name)
    expected = module.NotificationNoiseDecision(should_send=False, reason_code="patched")
    with patch.object(module, "_evaluate_notification_noise", return_value=expected):
        actual = module.evaluate_notification_noise(
            object(),
            content="fixture",
            route_type="report",
        )
    assert actual is expected


def test_noise_facade_shares_process_local_state_with_implementation() -> None:
    legacy = importlib.import_module("src.notification_noise")
    implementation = importlib.import_module("src.notification_parts.noise")

    assert legacy._dedup_expires_at is implementation._dedup_expires_at
    assert legacy._cooldown_expires_at is implementation._cooldown_expires_at
    assert legacy._dedup_inflight_until is implementation._dedup_inflight_until
    assert legacy._cooldown_inflight_until is implementation._cooldown_inflight_until
    assert legacy._state_lock is implementation._state_lock


@pytest.mark.parametrize(
    "module_name",
    ("src.notification_routing", "src.notification_parts.route_config"),
)
def test_route_config_patch_seam_works_through_both_paths(module_name: str) -> None:
    module = importlib.import_module(module_name)
    with patch.object(module, "parse_notification_route_channels", return_value=["wechat"]):
        assert module.split_notification_route_channels(["ignored"]) == (["wechat"], [])


def test_legacy_reload_rebinds_fresh_objects_in_subprocess() -> None:
    pairs = {legacy: values[0] for legacy, values in MODULES.items()}
    code = textwrap.dedent(
        f"""
        import ast
        import importlib
        from pathlib import Path
        from types import FunctionType

        modules = {pairs!r}
        for legacy_name, implementation_name in modules.items():
            legacy = importlib.import_module(legacy_name)
            implementation = importlib.import_module(implementation_name)
            tree = ast.parse(Path(implementation.__file__).read_text(encoding="utf-8"))
            names = [
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            ]
            previous = {{name: getattr(legacy, name) for name in names}}
            for _ in range(2):
                importlib.reload(legacy)
                implementation = importlib.import_module(implementation_name)
                for name in names:
                    value = getattr(legacy, name)
                    implementation_value = getattr(implementation, name)
                    assert value is not previous[name]
                    assert value.__module__ == legacy_name
                    if isinstance(value, FunctionType):
                        assert value is not implementation_value
                        assert implementation_value.__module__ == implementation_name
                        assert value.__globals__ is vars(legacy)
                    else:
                        assert value is implementation_value
                    previous[name] = value
        """
    )
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.parametrize("legacy_name", MODULES)
def test_new_path_first_import_preserves_existing_objects(legacy_name: str) -> None:
    implementation_name, _, _ = MODULES[legacy_name]
    code = textwrap.dedent(
        f"""
        import ast
        import importlib
        from pathlib import Path
        from types import FunctionType

        implementation = importlib.import_module({implementation_name!r})
        tree = ast.parse(Path(implementation.__file__).read_text(encoding="utf-8"))
        names = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        before = {{name: getattr(implementation, name) for name in names}}
        legacy = importlib.import_module({legacy_name!r})
        for name in names:
            implementation_value = getattr(implementation, name)
            legacy_value = getattr(legacy, name)
            assert implementation_value is before[name]
            if isinstance(implementation_value, FunctionType):
                assert legacy_value is not implementation_value
                assert implementation_value.__module__ == {implementation_name!r}
                assert implementation_value.__globals__ is vars(implementation)
            else:
                assert legacy_value is implementation_value
        """
    )
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.parametrize("legacy_name", MODULES)
def test_legacy_modules_are_thin_facades(legacy_name: str) -> None:
    module = importlib.import_module(legacy_name)
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for node in tree.body
    )


@pytest.mark.parametrize("legacy_name", MODULES)
def test_relocated_sources_are_ast_identical(legacy_name: str) -> None:
    implementation_name, _, expected_digest = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    tree = ast.parse(Path(implementation.__file__).read_text(encoding="utf-8"))
    payload = ast.dump(tree, include_attributes=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert digest == expected_digest
