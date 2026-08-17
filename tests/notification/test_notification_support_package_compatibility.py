"""Compatibility guards for notification support package convergence."""

import ast
import hashlib
import importlib
from pathlib import Path
from typing import Any, get_type_hints
from unittest.mock import patch

import pytest


MODULES = {
    "src.notification_parts.capabilities": (
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
        "c560a6081fd037f584a7d5e419d9927d9496551d3ce3262f85b2c9cd4e3ff743",
    ),
    "src.notification_parts.contracts": (
        "src.notification_parts.contracts",
        (
            "Any",
            "ChannelAttemptResult",
            "Dict",
            "FEISHU_APP_BOT_ENV_GROUP",
            "FEISHU_STATIC_ENV_GROUPS",
            "FEISHU_WEBHOOK_ENV_GROUP",
            "List",
            "Mapping",
            "NotificationDispatchResult",
            "Optional",
            "Tuple",
            "annotations",
            "dataclass",
            "field",
            "is_dingtalk_session_webhook_url",
            "is_feishu_app_bot_configured",
            "is_feishu_app_bot_env_configured",
            "is_feishu_static_configured",
            "is_feishu_static_env_configured",
            "parse_qsl",
            "urlsplit",
        ),
        "2eff4e3fcc229f3e20c900a00deea2a9905479add021998c48a680340fab3477",
    ),
    "src.notification_parts.noise": (
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
        "69b5dab6ac1905457c05e5b5aeba397c8028b42cd7dd812f83c3f754347a99df",
    ),
    "src.notification_parts.route_config": (
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
        "370865f0a9df3b98e8a562c0bf53548cba4bef0419f98f61b70fe1816348d62a",
    ),
}

def _source_definitions(module) -> dict[str, ast.AST]:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def _stable_ast(node: Any):
    """Serialize AST nodes without interpreter-version-only empty fields."""
    if isinstance(node, ast.AST):
        return (
            type(node).__name__,
            tuple(
                (field, _stable_ast(getattr(node, field)))
                for field in node._fields
                if field != "type_params"
            ),
        )
    if isinstance(node, list):
        return tuple(_stable_ast(item) for item in node)
    return node


RETIRED_NOTIFICATION_SHIMS = (
    "src.notification_capabilities",
    "src.notification_contracts",
    "src.notification_noise",
    "src.notification_routing",
)


def test_retired_notification_support_shims_are_not_importable() -> None:
    """Deleted root-level notification facades must not remain importable."""

    for legacy_name in RETIRED_NOTIFICATION_SHIMS:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(legacy_name)


@pytest.mark.parametrize("legacy_name", MODULES)
def test_canonical_support_modules_preserve_complete_module_surface(legacy_name: str) -> None:
    implementation_name, expected_exports, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)

    assert tuple(sorted(name for name in vars(implementation) if not name.startswith("_"))) == (
        expected_exports
    )

    if implementation_name == "src.notification_parts.noise":
        assert implementation.logger.name == implementation_name


@pytest.mark.parametrize("legacy_name", MODULES)
def test_canonical_support_modules_preserve_callable_contracts(legacy_name: str) -> None:
    implementation_name, _, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)

    for name, node in _source_definitions(implementation).items():
        implementation_value = getattr(implementation, name)
        assert implementation_value.__module__ == implementation_name
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert implementation_value.__globals__ is vars(implementation)
            get_type_hints(
                implementation_value,
                globalns=vars(implementation),
                localns=vars(implementation),
            )


def test_capabilities_patch_seam_uses_canonical_module() -> None:
    module = importlib.import_module("src.notification_parts.capabilities")
    with patch.object(module, "normalize_channel_name", return_value="wechat"):
        assert module.get_channel_profile(object()) is module.CHANNEL_PROFILES["wechat"]


def test_contract_patch_seam_uses_canonical_module() -> None:
    module = importlib.import_module("src.notification_parts.contracts")
    with patch.object(module, "_has_env_group", return_value=True) as has_group:
        assert module.is_feishu_app_bot_env_configured({}) is True
    has_group.assert_called_once_with({}, module.FEISHU_APP_BOT_ENV_GROUP)


def test_noise_patch_seam_uses_canonical_module() -> None:
    module = importlib.import_module("src.notification_parts.noise")
    expected = module.NotificationNoiseDecision(should_send=False, reason_code="patched")
    with patch.object(module, "_evaluate_notification_noise", return_value=expected):
        actual = module.evaluate_notification_noise(
            object(),
            content="fixture",
            route_type="report",
        )
    assert actual is expected


def test_route_config_patch_seam_uses_canonical_module() -> None:
    module = importlib.import_module("src.notification_parts.route_config")
    with patch.object(module, "parse_notification_route_channels", return_value=["wechat"]):
        assert module.split_notification_route_channels(["ignored"]) == (["wechat"], [])


@pytest.mark.parametrize("legacy_name", MODULES)
def test_relocated_sources_are_ast_identical(legacy_name: str) -> None:
    implementation_name, _, expected_digest = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    tree = ast.parse(Path(implementation.__file__).read_text(encoding="utf-8"))
    payload = repr(_stable_ast(tree))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert digest == expected_digest
