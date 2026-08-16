"""Compatibility guards for compact notification sender convergence."""

import ast
import hashlib
import importlib
import inspect
from pathlib import Path
from types import FunctionType
from typing import Any, get_type_hints

import pytest


MODULES = {
    "src.notification_sender.astrbot_sender": (
        "src.notification_parts.senders.astrbot_sender",
        (
            "AstrbotSender",
            "Config",
            "Optional",
            "hashlib",
            "hmac",
            "json",
            "log_safe_exception",
            "logger",
            "logging",
            "markdown_to_html_document",
            "requests",
            "safe_post",
        ),
        "0ce02b31c3208b9952a279bfeb4c787704da7867a90954bb6f2d754c856918d2",
    ),
    "src.notification_sender.dingtalk_sender": (
        "src.notification_parts.senders.dingtalk_sender",
        (
            "Config",
            "DingtalkSender",
            "Optional",
            "base64",
            "chunk_content_by_max_bytes",
            "hashlib",
            "hmac",
            "log_safe_exception",
            "logger",
            "logging",
            "requests",
            "safe_post",
            "time",
            "urllib",
        ),
        "56f76e6f0747ea1b815c349c22451f65d52eaa6d4f474ec835404b1538a2b58d",
    ),
    "src.notification_sender.gotify_sender": (
        "src.notification_parts.senders.gotify_sender",
        (
            "Config",
            "GotifySender",
            "Optional",
            "annotations",
            "datetime",
            "logger",
            "logging",
            "requests",
            "resolve_gotify_message_endpoint",
            "safe_post",
            "urlparse",
            "urlunparse",
        ),
        "1ca6036872218ad9258c58c9417e77c9be736d9f80a057648ef8a9d0845f2daa",
    ),
    "src.notification_sender.ntfy_sender": (
        "src.notification_parts.senders.ntfy_sender",
        (
            "Config",
            "NtfySender",
            "Optional",
            "Tuple",
            "annotations",
            "datetime",
            "logger",
            "logging",
            "requests",
            "resolve_ntfy_endpoint",
            "safe_post",
            "unquote",
            "urlparse",
            "urlunparse",
        ),
        "f57c2786e1f5fd467803b92e1467ac99ddeea000a408e90f624a2a2c281dc13b",
    ),
    "src.notification_sender.pushover_sender": (
        "src.notification_parts.senders.pushover_sender",
        (
            "Config",
            "Optional",
            "PushoverSender",
            "datetime",
            "log_safe_exception",
            "logger",
            "logging",
            "markdown_to_plain_text",
            "requests",
            "safe_post",
        ),
        "e172a2553041a7b1a4f63ef255f21a7f45783344c6e2238b6756f8f39a6a2ca7",
    ),
    "src.notification_sender.pushplus_sender": (
        "src.notification_parts.senders.pushplus_sender",
        (
            "Config",
            "Optional",
            "PushplusSender",
            "chunk_content_by_max_bytes",
            "datetime",
            "log_safe_exception",
            "logger",
            "logging",
            "requests",
            "safe_post",
            "time",
        ),
        "2c31665291c25767fe5e30d60fbf0bf2c7b89a4784b685732c89a307397baf6e",
    ),
    "src.notification_sender.serverchan3_sender": (
        "src.notification_parts.senders.serverchan3_sender",
        (
            "Config",
            "Optional",
            "Serverchan3Sender",
            "datetime",
            "log_safe_exception",
            "logger",
            "logging",
            "re",
            "requests",
            "safe_post",
        ),
        "c0af738566b86fcb6690acdf984d00ae8c21964bc01e69c6f5f4048e195e5707",
    ),
    "src.notification_sender.wechat_sender": (
        "src.notification_parts.senders.wechat_sender",
        (
            "Config",
            "Optional",
            "WECHAT_IMAGE_MAX_BYTES",
            "WechatSender",
            "base64",
            "chunk_content_by_max_bytes",
            "hashlib",
            "log_safe_exception",
            "logger",
            "logging",
            "requests",
            "safe_post",
            "time",
        ),
        "293718577b850a5069722c3cfda11581b7db461eeb62fc35dae97da4cfec91bb",
    ),
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
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
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


def test_retired_compact_sender_shims_are_not_importable() -> None:
    """The deleted compatibility package must not remain importable."""

    for legacy_name in RETIRED_LEGACY_PREFIXES:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(legacy_name)
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.notification_sender")


@pytest.mark.parametrize("legacy_name", MODULES)
def test_canonical_senders_preserve_complete_module_surface(legacy_name: str) -> None:
    implementation_name, expected_exports, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)

    assert tuple(sorted(name for name in vars(implementation) if not name.startswith("_"))) == expected_exports
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
        get_type_hints(implementation_value, globalns=vars(implementation), localns=vars(implementation))
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
    implementation_name, _, _ = MODULES[legacy_name]
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
            assert function.__globals__["requests"] is implementation.requests
            assert function.__globals__["safe_post"] is implementation.safe_post


def test_canonical_package_root_exports_compact_sender_objects() -> None:
    package = importlib.import_module("src.notification_parts.senders")
    for _legacy_name, (implementation_name, _, _) in MODULES.items():
        implementation = importlib.import_module(implementation_name)
        for name, node in _source_definitions(implementation).items():
            assert getattr(package, name) is getattr(implementation, name)


@pytest.mark.parametrize("legacy_name", MODULES)
def test_relocated_sender_sources_are_ast_identical(legacy_name: str) -> None:
    implementation_name, _, expected_digest = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    tree = ast.parse(Path(implementation.__file__).read_text(encoding="utf-8"))
    _normalize_docstring_trailing_whitespace(tree)
    payload = repr(_stable_ast(tree))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert digest == expected_digest
