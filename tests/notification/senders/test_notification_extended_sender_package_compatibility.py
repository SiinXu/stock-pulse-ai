"""Compatibility guards for extended notification sender convergence."""

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

import pytest


try:
    from lark_oapi.api.im.v1 import (  # noqa: F401
        CreateMessageRequest as _CreateMessageRequestProbe,
        CreateMessageRequestBody as _CreateMessageRequestBodyProbe,
    )
except ImportError:
    _FEISHU_OPTIONAL_EXPORTS = ()
else:
    _FEISHU_OPTIONAL_EXPORTS = (
        "CreateMessageRequest",
        "CreateMessageRequestBody",
    )


MODULES = {
    "src.notification_sender.custom_webhook_sender": (
        "src.notification_parts.senders.custom_webhook_sender",
        (
            "Any",
            "Callable",
            "Config",
            "CustomWebhookSender",
            "Dict",
            "List",
            "Optional",
            "Template",
            "Tuple",
            "chunk_content_by_max_bytes",
            "is_dingtalk_session_webhook_url",
            "json",
            "log_safe_exception",
            "logger",
            "logging",
            "requests",
            "safe_post",
            "sanitize_exception_chain",
            "slice_at_max_bytes",
            "time",
        ),
        ("Template", "requests", "safe_post", "sanitize_exception_chain", "time"),
        "de05aee564758a8567a4efca6d26dd2dd0646eff80e4b273c05438f1786235bd",
    ),
    "src.notification_sender.discord_sender": (
        "src.notification_parts.senders.discord_sender",
        (
            "Config",
            "DISCORD_CHUNK_SLEEP_SECONDS",
            "DISCORD_MAX_CONTENT_LENGTH",
            "DISCORD_MAX_RETRIES",
            "DiscordSender",
            "MIN_MAX_WORDS",
            "Optional",
            "chunk_content_by_max_words",
            "log_safe_exception",
            "logger",
            "logging",
            "requests",
            "safe_post",
            "time",
        ),
        ("requests", "safe_post", "time"),
        "73a332ebbca982134bb3d890a8e818026c4863341c5c4c19f4468e7179d63075",
    ),
    "src.notification_sender.email_sender": (
        "src.notification_parts.senders.email_sender",
        (
            "Config",
            "EmailSender",
            "Header",
            "List",
            "MIMEImage",
            "MIMEMultipart",
            "MIMEText",
            "Optional",
            "SMTP_CONFIGS",
            "datetime",
            "formataddr",
            "log_safe_exception",
            "logger",
            "logging",
            "markdown_to_html_document",
            "normalize_stock_code",
            "smtplib",
        ),
        ("Header", "MIMEImage", "MIMEMultipart", "MIMEText", "datetime", "smtplib"),
        "a11523887685095742885b6482ee3fda42e9a432ebd0d4b080ffc3e162b8d658",
    ),
    "src.notification_sender.feishu_sender": (
        "src.notification_parts.senders.feishu_sender",
        (
            "Any",
            "Config",
            *_FEISHU_OPTIONAL_EXPORTS,
            "Dict",
            "FEISHU_DOMAIN",
            "FEISHU_FILE_SDK_AVAILABLE",
            "FEISHU_SDK_AVAILABLE",
            "FeishuSender",
            "LARK_DOMAIN",
            "MIN_MAX_BYTES",
            "Optional",
            "PAGE_MARKER_SAFE_BYTES",
            "Path",
            "base64",
            "chunk_content_by_max_bytes",
            "format_feishu_markdown",
            "hashlib",
            "hmac",
            "json",
            "log_safe_exception",
            "logger",
            "logging",
            "os",
            "requests",
            "safe_post",
            "threading",
            "time",
            "uuid_mod",
        ),
        (
            "FEISHU_FILE_SDK_AVAILABLE",
            "FEISHU_SDK_AVAILABLE",
            "Path",
            "_CreateFileRequest",
            "_CreateFileRequestBody",
            "requests",
            "safe_post",
            "time",
            "uuid_mod",
        ),
        "29b2dd9eddae156f8458987d039701de9fb87d63e22c444d28b7621b36382bca",
    ),
    "src.notification_sender.slack_sender": (
        "src.notification_parts.senders.slack_sender",
        (
            "Config",
            "Optional",
            "SlackSender",
            "chunk_content_by_max_bytes",
            "json",
            "log_safe_exception",
            "logger",
            "logging",
            "requests",
            "safe_post",
        ),
        ("requests", "safe_post"),
        "05d6c86fae553c7c3727d25bb7bde2674c7ca39a76a8a0c905096137d5e6fce5",
    ),
    "src.notification_sender.telegram_sender": (
        "src.notification_parts.senders.telegram_sender",
        (
            "Config",
            "Optional",
            "TelegramSender",
            "log_safe_exception",
            "logger",
            "logging",
            "re",
            "requests",
            "safe_post",
            "time",
        ),
        ("re", "requests", "safe_post", "time"),
        "3a18bf1f926709cb1ed23e8d17d3bdabe7822e324b460b80395cf7eaee97443c",
    ),
}

PACKAGE_EXPORTS = (
    "AstrbotSender",
    "CustomWebhookSender",
    "DingtalkSender",
    "DiscordSender",
    "EmailSender",
    "FeishuSender",
    "GotifySender",
    "NtfySender",
    "PushoverSender",
    "PushplusSender",
    "Serverchan3Sender",
    "SlackSender",
    "TelegramSender",
    "WECHAT_IMAGE_MAX_BYTES",
    "WechatSender",
    "astrbot_sender",
    "custom_webhook_sender",
    "dingtalk_sender",
    "discord_sender",
    "email_sender",
    "feishu_sender",
    "gotify_sender",
    "ntfy_sender",
    "pushover_sender",
    "pushplus_sender",
    "resolve_gotify_message_endpoint",
    "resolve_ntfy_endpoint",
    "serverchan3_sender",
    "slack_sender",
    "telegram_sender",
    "wechat_sender",
)

PACKAGE_BINDINGS = {
    "AstrbotSender": "astrbot_sender",
    "CustomWebhookSender": "custom_webhook_sender",
    "DingtalkSender": "dingtalk_sender",
    "DiscordSender": "discord_sender",
    "EmailSender": "email_sender",
    "FeishuSender": "feishu_sender",
    "GotifySender": "gotify_sender",
    "NtfySender": "ntfy_sender",
    "PushoverSender": "pushover_sender",
    "PushplusSender": "pushplus_sender",
    "Serverchan3Sender": "serverchan3_sender",
    "SlackSender": "slack_sender",
    "TelegramSender": "telegram_sender",
    "WECHAT_IMAGE_MAX_BYTES": "wechat_sender",
    "WechatSender": "wechat_sender",
    "resolve_gotify_message_endpoint": "gotify_sender",
    "resolve_ntfy_endpoint": "ntfy_sender",
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


def _normalize_docstring_trailing_whitespace(tree: ast.AST) -> ast.AST:
    """Normalize formatting-only whitespace within scope docstrings."""
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
            continue
        if not isinstance(first.value.value, str):
            continue
        first.value.value = "\n".join(
            line.rstrip() for line in first.value.value.split("\n")
        )
    return tree


RETIRED_LEGACY_PREFIXES = tuple(MODULES)


def test_retired_extended_sender_shims_are_not_importable() -> None:
    """The deleted compatibility package must not remain importable."""

    for legacy_name in RETIRED_LEGACY_PREFIXES:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(legacy_name)
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.notification_sender")


@pytest.mark.parametrize("legacy_name", MODULES)
def test_canonical_senders_preserve_complete_module_surface(legacy_name: str) -> None:
    implementation_name, expected_exports, _, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)

    public = tuple(sorted(name for name in vars(implementation) if not name.startswith("_")))
    assert public == expected_exports
    assert implementation.logger.name == implementation_name

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
            continue
        get_type_hints(
            implementation_value,
            globalns=vars(implementation),
            localns=vars(implementation),
        )
        for descriptor_name, descriptor in vars(implementation_value).items():
            function = _descriptor_function(descriptor)
            if function is None:
                continue
            assert function.__module__ == implementation_name, descriptor_name
            unwrapped = inspect.unwrap(function)
            if unwrapped.__globals__.get("__name__") != "dataclasses":
                assert unwrapped.__globals__ is vars(implementation), descriptor_name


@pytest.mark.parametrize("legacy_name", MODULES)
def test_canonical_class_methods_use_canonical_patch_globals(legacy_name: str) -> None:
    implementation_name, _, patch_globals, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)

    for name, node in _source_definitions(implementation).items():
        if not isinstance(node, ast.ClassDef):
            continue
        sender_class = getattr(implementation, name)
        for descriptor_name, descriptor in vars(sender_class).items():
            function = _descriptor_function(descriptor)
            if function is None:
                continue
            assert function.__globals__ is vars(implementation), descriptor_name
            for global_name in patch_globals:
                assert function.__globals__[global_name] is getattr(
                    implementation, global_name
                )


def test_canonical_package_root_preserves_complete_exports() -> None:
    canonical_package = importlib.import_module("src.notification_parts.senders")

    public = tuple(
        sorted(name for name in vars(canonical_package) if not name.startswith("_"))
    )
    assert public == PACKAGE_EXPORTS
    assert canonical_package.__all__ == PACKAGE_EXPORTS

    for name, short_module in PACKAGE_BINDINGS.items():
        canonical_module = importlib.import_module(
            f"src.notification_parts.senders.{short_module}"
        )
        assert getattr(canonical_package, name) is getattr(canonical_module, name)

    for name in PACKAGE_EXPORTS:
        if not name.endswith("_sender"):
            continue
        assert getattr(canonical_package, name) is importlib.import_module(
            f"src.notification_parts.senders.{name}"
        )


def test_feishu_sender_preserves_sdk_optional_imports_in_subprocess() -> None:
    code = textwrap.dedent(
        """
        import builtins
        import importlib

        original_import = builtins.__import__

        def without_lark(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "lark_oapi" or name.startswith("lark_oapi."):
                raise ImportError("blocked lark-oapi for compatibility test")
            return original_import(name, globals, locals, fromlist, level)

        builtins.__import__ = without_lark
        implementation = importlib.import_module(
            "src.notification_parts.senders.feishu_sender"
        )
        assert implementation.FEISHU_SDK_AVAILABLE is False
        assert implementation.FEISHU_FILE_SDK_AVAILABLE is False
        assert "CreateMessageRequest" not in vars(implementation)
        assert "CreateMessageRequestBody" not in vars(implementation)
        assert not hasattr(implementation, "CreateMessageRequest")
        """
    )
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.parametrize("legacy_name", MODULES)
def test_relocated_sender_sources_are_ast_identical(legacy_name: str) -> None:
    implementation_name, _, _, expected_digest = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    tree = ast.parse(Path(implementation.__file__).read_text(encoding="utf-8"))
    _normalize_docstring_trailing_whitespace(tree)
    payload = repr(_stable_ast(tree))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert digest == expected_digest


def test_feishu_sender_imports_without_the_optional_sdk() -> None:
    code = textwrap.dedent(
        """
        import importlib
        import sys

        sys.modules["lark_oapi"] = None
        implementation = importlib.import_module(
            "src.notification_parts.senders.feishu_sender"
        )
        package = importlib.import_module("src.notification_parts.senders")

        assert implementation.FEISHU_SDK_AVAILABLE is False
        assert "CreateMessageRequest" not in vars(implementation)
        assert not hasattr(implementation, "CreateMessageRequest")
        assert package.FeishuSender is implementation.FeishuSender
        """
    )
    subprocess.run([sys.executable, "-c", code], check=True)
