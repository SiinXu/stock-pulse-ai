# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Sanctioned outbound HTTP helpers for trusted in-process plugins.

Plugins execute as arbitrary in-process Python (ADR-007). There is no OS or
process sandbox. These helpers apply the same fail-closed ``LOCAL_ONLY_MODE``
and outbound policy as first-party ``safe_*`` callers.

They do **not** contain a malicious plugin. Direct ``requests``, ``httpx``,
``urllib.request``, ``urllib3``, or ``aiohttp`` usage in bundled and example
plugins is detectable by ``find_unsanctioned_plugin_http``. A plugin can still
import ``socket`` (or otherwise bypass this wrapper) because it shares the
host process.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Iterable

import requests

from src.security.outbound_policy import (
    OutboundPolicyError,
    safe_get,
    safe_post,
    safe_request,
)


_BANNED_MODULE_PREFIXES = (
    "aiohttp",
    "httpx",
    "requests",
    "urllib.request",
    "urllib3",
)

_BUNDLED_PLUGIN_HTTP_ROOTS = (
    Path("src") / "plugins" / "builtin",
    Path("examples") / "plugins",
    Path("docs") / "examples",
)


def plugin_safe_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Issue one plugin HTTP request through the shared outbound policy."""

    return safe_request(method, url, **kwargs)


def plugin_safe_get(url: str, **kwargs: Any) -> requests.Response:
    """Issue one plugin HTTP GET through the shared outbound policy."""

    return safe_get(url, **kwargs)


def plugin_safe_post(url: str, **kwargs: Any) -> requests.Response:
    """Issue one plugin HTTP POST through the shared outbound policy."""

    return safe_post(url, **kwargs)


def _module_is_banned(name: str) -> bool:
    return any(
        name == prefix or name.startswith(prefix + ".")
        for prefix in _BANNED_MODULE_PREFIXES
    )


def _attribute_chain(node: ast.AST) -> str | None:
    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def find_unsanctioned_plugin_http(
    source: str,
    *,
    filename: str = "<plugin>",
) -> tuple[str, ...]:
    """Return findings for direct HTTP clients in plugin source.

    ``urllib.parse`` / ``urllib.error`` are allowed. Imports of the sanctioned
    ``plugin_safe_*`` helpers and ``src.security.outbound_policy.safe_*`` are
    allowed. Syntax errors fail closed as findings.
    """

    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return (f"{filename}: syntax_error",)

    findings: list[str] = []
    aliases: dict[str, str] = {}

    def record(lineno: int, module: str) -> None:
        findings.append(
            f"{filename}:{lineno}: unsanctioned HTTP client {module}"
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported = alias.name
                bound = alias.asname or imported.split(".", 1)[0]
                aliases[bound] = imported
                if _module_is_banned(imported):
                    record(node.lineno, imported)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                continue
            for alias in node.names:
                imported = f"{module}.{alias.name}" if module else alias.name
                bound = alias.asname or alias.name
                aliases[bound] = imported
                if _module_is_banned(module) or _module_is_banned(imported):
                    record(node.lineno, imported)
        elif isinstance(node, ast.Attribute):
            chain = _attribute_chain(node)
            if chain is None:
                continue
            root, _, remainder = chain.partition(".")
            resolved_root = aliases.get(root, root)
            resolved = (
                f"{resolved_root}.{remainder}" if remainder else resolved_root
            )
            if _module_is_banned(resolved):
                record(node.lineno, resolved)

    return tuple(dict.fromkeys(findings))


def iter_bundled_plugin_python(repo_root: Path) -> tuple[Path, ...]:
    """Return bundled and example plugin Python files under ``repo_root``."""

    files: list[Path] = []
    for relative in _BUNDLED_PLUGIN_HTTP_ROOTS:
        root = repo_root / relative
        if not root.is_dir():
            continue
        files.extend(sorted(path for path in root.rglob("*.py") if path.is_file()))
    return tuple(files)


def scan_bundled_plugin_http(
    repo_root: Path,
    *,
    paths: Iterable[Path] | None = None,
) -> tuple[str, ...]:
    """Scan bundled/example plugin trees for unsanctioned HTTP clients."""

    findings: list[str] = []
    for path in paths if paths is not None else iter_bundled_plugin_python(repo_root):
        relative = path.relative_to(repo_root).as_posix() if path.is_absolute() else path.as_posix()
        source = path.read_text(encoding="utf-8")
        findings.extend(find_unsanctioned_plugin_http(source, filename=relative))
    return tuple(findings)


__all__ = [
    "OutboundPolicyError",
    "find_unsanctioned_plugin_http",
    "iter_bundled_plugin_python",
    "plugin_safe_get",
    "plugin_safe_post",
    "plugin_safe_request",
    "scan_bundled_plugin_http",
]
