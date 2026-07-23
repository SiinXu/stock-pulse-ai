"""Compatibility guards for compact notification sender convergence."""

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


@pytest.mark.parametrize("legacy_name", MODULES)
def test_facades_preserve_complete_module_surface(legacy_name: str) -> None:
    implementation_name, expected_exports, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    legacy = importlib.import_module(legacy_name)

    assert tuple(sorted(name for name in vars(legacy) if not name.startswith("_"))) == expected_exports
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
            get_type_hints(
                function,
                globalns=vars(legacy),
                localns={**vars(legacy), **vars(legacy_value)},
            )


@pytest.mark.parametrize("legacy_name", MODULES)
def test_legacy_class_methods_use_legacy_patch_globals(legacy_name: str) -> None:
    implementation_name, _, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    legacy = importlib.import_module(legacy_name)

    for name, node in _source_definitions(implementation).items():
        if not isinstance(node, ast.ClassDef):
            continue
        sender_class = getattr(legacy, name)
        for descriptor_name, descriptor in vars(sender_class).items():
            function = _descriptor_function(descriptor)
            if function is None:
                continue
            assert function.__globals__ is vars(legacy), descriptor_name
            assert function.__globals__["requests"] is legacy.requests
            assert function.__globals__["safe_post"] is legacy.safe_post


def test_legacy_package_root_exports_compact_facade_objects() -> None:
    package = importlib.import_module("src.notification_sender")
    for legacy_name, (implementation_name, _, _) in MODULES.items():
        legacy = importlib.import_module(legacy_name)
        implementation = importlib.import_module(implementation_name)
        for name, node in _source_definitions(implementation).items():
            assert getattr(package, name) is getattr(legacy, name)


def test_legacy_reload_rebinds_fresh_sender_objects_in_subprocess() -> None:
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
def test_new_path_first_import_preserves_existing_sender_objects(legacy_name: str) -> None:
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
        for name in names:
            value = getattr(implementation, name)
            assert value.__module__ == {implementation_name!r}
            if isinstance(value, FunctionType):
                assert value.__globals__ is vars(implementation)
            else:
                for descriptor in vars(value).values():
                    function = descriptor.__func__ if isinstance(descriptor, (staticmethod, classmethod)) else descriptor
                    if isinstance(function, FunctionType):
                        assert function.__globals__ is vars(implementation)

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
def test_legacy_sender_modules_are_thin_facades(legacy_name: str) -> None:
    module = importlib.import_module(legacy_name)
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for node in tree.body
    )


@pytest.mark.parametrize("legacy_name", MODULES)
def test_relocated_sender_sources_are_ast_identical(legacy_name: str) -> None:
    implementation_name, _, expected_digest = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    tree = ast.parse(Path(implementation.__file__).read_text(encoding="utf-8"))
    _normalize_docstring_trailing_whitespace(tree)
    payload = repr(_stable_ast(tree))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert digest == expected_digest
