#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Ratcheting guard for broad exception handlers in production Python."""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import sys
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "scripts" / "broad_exception_baseline.json"
SCOPED_DIRECTORIES = ("src", "data_provider", "api", "bot")
SCOPED_FILES = ("main.py", "server.py")
BASELINE_VERSION = 1
CLASSIFICATIONS = frozenset(
    {"cleanup", "optional_metadata", "fallback_recorded"}
)
MARKER_PREFIX = "broad-exception:"
MARKER_PATTERN = re.compile(
    r"\bbroad-exception:\s*([a-z_]+)\s+-\s+(.+?)\s*$"
)
LOGGER_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
)
SAFE_LOG_FUNCTIONS = frozenset({"log_safe_exception", "safe_before_sleep_log"})
TYPED_EXCEPTION_FACTORIES = frozenset({"api_error"})
DIAGNOSTIC_TERMS = frozenset(
    {
        "diagnostic",
        "diagnostics",
        "error",
        "errors",
        "exception",
        "exceptions",
        "failure",
        "failures",
    }
)
FAILURE_RECORD_TERMS = DIAGNOSTIC_TERMS | {
    "degraded",
    "fail",
    "failed",
    "fallback",
}
NEGATIVE_OUTCOME_TERMS = frozenset({"ok", "success", "successful"})
IPC_OWNER_TERMS = frozenset({"channel", "conn", "connection", "ipc", "pipe"})
IGNORED_AST_FIELDS = frozenset({"type_params"})
_LEXICAL_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_LOCAL_HANDLER_BOUNDARIES = (*_LEXICAL_SCOPES, ast.ExceptHandler)
_TOP_LEVEL_TERMINALS = (ast.Raise, ast.Return, ast.Break, ast.Continue)


class BaselineError(ValueError):
    """Raised when the checked-in baseline is malformed."""


@dataclass(frozen=True, order=True)
class BaselineEntry:
    path: str
    scope: str
    caught: tuple[str, ...]
    digest: str

    def as_json(self) -> dict[str, object]:
        return {
            "path": self.path,
            "scope": self.scope,
            "caught": list(self.caught),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class Marker:
    category: str
    reason: str


@dataclass(frozen=True)
class BroadHandler:
    path: str
    line: int
    header_end: int
    scope: str
    caught: tuple[str, ...]
    digest: str
    marker: Marker | None
    marker_error: str | None
    catches_base_exception: bool
    has_local_pass: bool
    has_safe_log: bool
    has_recording_evidence: bool
    propagates: bool
    maps_typed_error: bool

    @property
    def baseline_entry(self) -> BaselineEntry:
        return BaselineEntry(
            path=self.path,
            scope=self.scope,
            caught=self.caught,
            digest=self.digest,
        )


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        location = self.path if self.line <= 0 else f"{self.path}:{self.line}"
        return f"{location}: {self.rule}: {self.message}"


@dataclass(frozen=True)
class Baseline:
    deferred_files: Mapping[str, str]
    legacy_handlers: tuple[BaselineEntry, ...]


def _iter_python_paths(root: Path) -> Iterator[Path]:
    for relative_path in SCOPED_FILES:
        path = root / relative_path
        if path.is_file():
            yield path
    for relative_directory in SCOPED_DIRECTORIES:
        directory = root / relative_directory
        if not directory.is_dir():
            continue
        yield from sorted(directory.rglob("*.py"))


def _broad_exception_names(node: ast.AST | None) -> tuple[str, ...]:
    if node is None:
        return ("bare",)
    if isinstance(node, ast.Name) and node.id in {"Exception", "BaseException"}:
        return (node.id,)
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "builtins"
        and node.attr in {"Exception", "BaseException"}
    ):
        return (node.attr,)
    if isinstance(node, ast.Tuple):
        return tuple(
            sorted(
                {
                    name
                    for item in node.elts
                    for name in _broad_exception_names(item)
                }
            )
        )
    return ()


def _comment_lines(source: str) -> dict[int, list[str]]:
    comments: dict[int, list[str]] = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT:
                comments.setdefault(token.start[0], []).append(token.string.lstrip("# "))
    except (IndentationError, tokenize.TokenError):
        return comments
    return comments


def _marker_for_handler(
    handler: ast.ExceptHandler,
    comments: Mapping[int, Sequence[str]],
) -> tuple[Marker | None, str | None]:
    first_body_line = handler.body[0].lineno if handler.body else handler.lineno
    header_end = max(handler.lineno, first_body_line - 1)
    candidates = [
        comment
        for line in range(handler.lineno, header_end + 1)
        for comment in comments.get(line, ())
        if MARKER_PREFIX in comment
    ]
    if not candidates:
        return None, None
    if len(candidates) != 1 or candidates[0].count(MARKER_PREFIX) != 1:
        return None, "broad exception handlers must have exactly one classification marker"
    match = MARKER_PATTERN.search(candidates[0])
    if match is None:
        return None, (
            "classification marker must use "
            "'# broad-exception: <category> - <reason>'"
        )
    category, reason = match.groups()
    if category not in CLASSIFICATIONS:
        return None, (
            f"unsupported category {category!r}; expected one of "
            f"{', '.join(sorted(CLASSIFICATIONS))}"
        )
    reason = reason.strip()
    if not reason:
        return None, "classification marker requires a non-empty reason"
    return Marker(category=category, reason=reason), None


def _walk_local_nodes(statements: Iterable[ast.stmt]) -> Iterator[ast.AST]:
    yield from _walk_nodes(statements, boundaries=_LOCAL_HANDLER_BOUNDARIES)


def _walk_control_flow_nodes(statements: Iterable[ast.stmt]) -> Iterator[ast.AST]:
    yield from _walk_nodes(statements, boundaries=_LEXICAL_SCOPES)


def _walk_nodes(
    statements: Iterable[ast.stmt],
    *,
    boundaries: tuple[type[ast.AST], ...],
) -> Iterator[ast.AST]:
    stack: list[ast.AST] = list(reversed(tuple(statements)))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, boundaries):
            continue
        stack.extend(reversed(tuple(ast.iter_child_nodes(node))))


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _attribute_owner_text(node: ast.AST) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts)).lower()


def _name_terms(value: str) -> set[str]:
    snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return {
        item
        for item in re.split(r"[^a-z0-9]+", snake_case.lower())
        if item
    }


def _is_logger_owner(node: ast.AST) -> bool:
    owner = _attribute_owner_text(node)
    if not owner:
        return False
    terminal = owner.rsplit(".", maxsplit=1)[-1]
    return (
        terminal in {"logger", "logging", "_logger"}
        or terminal.startswith("logger_")
        or terminal.endswith("_logger")
    )


def _is_safe_log_call(call: ast.Call) -> bool:
    name = _call_name(call)
    if name in SAFE_LOG_FUNCTIONS:
        return True
    if name not in LOGGER_METHODS or not isinstance(call.func, ast.Attribute):
        return False
    return _is_logger_owner(call.func.value)


def _direct_call(statement: ast.stmt) -> ast.Call | None:
    if not isinstance(statement, ast.Expr):
        return None
    value = statement.value
    if isinstance(value, ast.Await):
        value = value.value
    return value if isinstance(value, ast.Call) else None


def _is_safe_log_statement(statement: ast.stmt) -> bool:
    call = _direct_call(statement)
    return call is not None and _is_safe_log_call(call)


def _is_empty_record_value(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return not bool(node.value)
    if isinstance(node, (ast.Dict, ast.List, ast.Set, ast.Tuple)):
        return not any(ast.iter_child_nodes(node))
    return False


def _value_has_failure_semantics(node: ast.AST) -> bool:
    if _is_empty_record_value(node):
        return False
    if isinstance(node, ast.Name):
        return bool(_name_terms(node.id) & FAILURE_RECORD_TERMS)
    if isinstance(node, ast.Attribute):
        return bool(_name_terms(node.attr) & FAILURE_RECORD_TERMS)
    if isinstance(node, ast.Call):
        return bool(_name_terms(_call_name(node)) & FAILURE_RECORD_TERMS)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return bool(_name_terms(node.value) & FAILURE_RECORD_TERMS)
    if isinstance(node, ast.Dict):
        return any(
            key is not None
            and (
                (
                    _value_has_failure_semantics(key)
                    and not _is_empty_record_value(value)
                )
                or _is_negative_outcome(key, value)
            )
            for key, value in zip(node.keys, node.values)
        ) or any(_value_has_failure_semantics(value) for value in node.values)
    if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
        return any(_value_has_failure_semantics(item) for item in node.elts)
    return False


def _is_negative_outcome(key: ast.AST, value: ast.AST) -> bool:
    return (
        isinstance(key, ast.Constant)
        and isinstance(key.value, str)
        and bool(_name_terms(key.value) & NEGATIVE_OUTCOME_TERMS)
        and isinstance(value, ast.Constant)
        and value.value is False
    )


def _keyword_records_failure(keyword: ast.keyword) -> bool:
    return (
        keyword.arg is not None
        and (
            (
                bool(_name_terms(keyword.arg) & FAILURE_RECORD_TERMS)
                and not _is_empty_record_value(keyword.value)
            )
            or (
                bool(_name_terms(keyword.arg) & NEGATIVE_OUTCOME_TERMS)
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is False
            )
        )
    ) or _value_has_failure_semantics(keyword.value)


def _call_records_failure(call: ast.Call) -> bool:
    return (
        bool(_name_terms(_call_name(call)) & FAILURE_RECORD_TERMS)
        or any(_value_has_failure_semantics(argument) for argument in call.args)
        or any(_keyword_records_failure(keyword) for keyword in call.keywords)
    )


def _is_ipc_send(call: ast.Call) -> bool:
    if (
        _call_name(call) != "send"
        or not isinstance(call.func, ast.Attribute)
    ):
        return False
    has_ipc_owner = bool(
        _name_terms(_attribute_owner_text(call.func.value)) & IPC_OWNER_TERMS
    )
    return has_ipc_owner and _call_records_failure(call)


def _is_structured_record_call(call: ast.Call) -> bool:
    name = _call_name(call)
    if name.startswith("record_"):
        return _call_records_failure(call)
    if name == "set_exception":
        values = [*call.args, *(keyword.value for keyword in call.keywords)]
        return bool(values) and any(not _is_empty_record_value(value) for value in values)
    return _is_ipc_send(call)


def _target_has_diagnostic_term(target: ast.AST) -> bool:
    if isinstance(target, ast.Attribute):
        return bool(_name_terms(target.attr) & DIAGNOSTIC_TERMS)
    if isinstance(target, ast.Subscript):
        owner_has_term = bool(
            _name_terms(_attribute_owner_text(target.value)) & DIAGNOSTIC_TERMS
        )
        slice_value = target.slice
        if isinstance(slice_value, ast.Constant) and isinstance(slice_value.value, str):
            return owner_has_term or bool(
                _name_terms(slice_value.value) & DIAGNOSTIC_TERMS
            )
        return owner_has_term
    if isinstance(target, (ast.Tuple, ast.List)):
        return any(_target_has_diagnostic_term(item) for item in target.elts)
    return False


def _is_diagnostic_assignment(statement: ast.stmt) -> bool:
    if isinstance(statement, ast.Assign):
        return (
            any(_target_has_diagnostic_term(target) for target in statement.targets)
            and not _is_empty_record_value(statement.value)
        )
    if isinstance(statement, ast.AnnAssign):
        return (
            statement.value is not None
            and _target_has_diagnostic_term(statement.target)
            and not _is_empty_record_value(statement.value)
        )
    if isinstance(statement, ast.AugAssign):
        return _target_has_diagnostic_term(
            statement.target
        ) and not _is_empty_record_value(statement.value)
    return False


def _is_recording_statement(statement: ast.stmt) -> bool:
    call = _direct_call(statement)
    if call is not None:
        return _is_safe_log_call(call) or _is_structured_record_call(call)
    return _is_diagnostic_assignment(statement)


def _has_reachable_recording_statement(statements: Sequence[ast.stmt]) -> bool:
    has_prior_fallback_escape = False
    for statement in statements:
        if _is_recording_statement(statement) and not has_prior_fallback_escape:
            return True
        if isinstance(statement, _TOP_LEVEL_TERMINALS):
            return False
        statement_nodes = tuple(_walk_control_flow_nodes((statement,)))
        has_prior_fallback_escape = (
            has_prior_fallback_escape or _has_control_flow_escape(statement_nodes)
        )
    return False


def _has_reachable_safe_log(statements: Sequence[ast.stmt]) -> bool:
    for statement in statements:
        if _is_safe_log_statement(statement):
            return True
        if isinstance(statement, _TOP_LEVEL_TERMINALS):
            return False
    return False


def _has_control_flow_escape(nodes: Sequence[ast.AST]) -> bool:
    return any(
        isinstance(node, (ast.Return, ast.Break, ast.Continue, ast.Yield, ast.YieldFrom))
        for node in nodes
    )


def _looks_like_typed_exception(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    constructor = node.func
    if isinstance(constructor, ast.Name):
        name = constructor.id
        if name in TYPED_EXCEPTION_FACTORIES:
            return True
    elif isinstance(constructor, ast.Attribute):
        name = constructor.attr
    else:
        return False
    return name.endswith("Error") or name.endswith("Exception")


def _raise_kind(
    owner: ast.Try | ast.TryStar,
    handler: ast.ExceptHandler,
    control_flow_nodes: Sequence[ast.AST],
) -> tuple[bool, bool]:
    if not handler.body or not isinstance(handler.body[-1], ast.Raise):
        return False, False
    if _has_control_flow_escape(control_flow_nodes):
        return False, False
    finalbody_nodes = tuple(_walk_control_flow_nodes(owner.finalbody))
    if _has_control_flow_escape(finalbody_nodes):
        return False, False
    final_raise = handler.body[-1]
    if final_raise.exc is None:
        return True, False
    if (
        handler.name
        and isinstance(final_raise.exc, ast.Name)
        and final_raise.exc.id == handler.name
    ):
        return True, False
    has_direct_safe_log = _has_reachable_safe_log(handler.body[:-1])
    return False, has_direct_safe_log and _looks_like_typed_exception(final_raise.exc)


def _stable_ast_dump(value: object) -> str:
    if isinstance(value, ast.AST):
        fields = (
            f"{field}={_stable_ast_dump(field_value)}"
            for field, field_value in ast.iter_fields(value)
            if field not in IGNORED_AST_FIELDS
        )
        return f"{type(value).__name__}({','.join(fields)})"
    if isinstance(value, list):
        return f"[{','.join(_stable_ast_dump(item) for item in value)}]"
    return repr(value)


def _handler_digest(
    owner: ast.Try | ast.TryStar,
    try_site_index: int,
    handler_index: int,
    handler: ast.ExceptHandler,
) -> str:
    payload = {
        "finalbody": _stable_ast_dump(owner.finalbody),
        "handler": _stable_ast_dump(handler),
        "handler_index": handler_index,
        "handlers": _stable_ast_dump(owner.handlers),
        "protected_body": _stable_ast_dump(owner.body),
        "try_kind": type(owner).__name__,
        "try_site_index": try_site_index,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class _HandlerVisitor(ast.NodeVisitor):
    def __init__(self, path: str, source: str) -> None:
        self.path = path
        self.comments = _comment_lines(source)
        self.handlers: list[BroadHandler] = []
        self._scope: list[str] = ["<module>"]
        self._try_site_counts: dict[tuple[str, ...], int] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        self._scope.append(f"<lambda@{node.lineno}>")
        self.generic_visit(node)
        self._scope.pop()

    def _record_handler(
        self,
        owner: ast.Try | ast.TryStar,
        try_site_index: int,
        handler_index: int,
        node: ast.ExceptHandler,
    ) -> None:
        caught = _broad_exception_names(node.type)
        if caught:
            local_nodes = tuple(_walk_local_nodes(node.body))
            control_flow_nodes = tuple(_walk_control_flow_nodes(node.body))
            has_safe_log = any(
                _is_safe_log_statement(statement) for statement in node.body
            )
            has_recording_evidence = _has_reachable_recording_statement(node.body)
            propagates, maps_typed_error = _raise_kind(
                owner,
                node,
                control_flow_nodes,
            )
            marker, marker_error = _marker_for_handler(node, self.comments)
            self.handlers.append(
                BroadHandler(
                    path=self.path,
                    line=node.lineno,
                    header_end=max(
                        node.lineno,
                        (node.body[0].lineno if node.body else node.lineno) - 1,
                    ),
                    scope=".".join(self._scope),
                    caught=caught,
                    digest=_handler_digest(
                        owner,
                        try_site_index,
                        handler_index,
                        node,
                    ),
                    marker=marker,
                    marker_error=marker_error,
                    catches_base_exception=("BaseException" in caught or "bare" in caught),
                    has_local_pass=any(isinstance(item, ast.Pass) for item in local_nodes),
                    has_safe_log=has_safe_log,
                    has_recording_evidence=has_recording_evidence,
                    propagates=propagates,
                    maps_typed_error=maps_typed_error,
                )
            )

    def _visit_try(self, node: ast.Try | ast.TryStar) -> None:
        scope = tuple(self._scope)
        try_site_index = self._try_site_counts.get(scope, 0)
        self._try_site_counts[scope] = try_site_index + 1
        for handler_index, handler in enumerate(node.handlers):
            self._record_handler(node, try_site_index, handler_index, handler)
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:  # noqa: N802
        self._visit_try(node)

    def visit_TryStar(self, node: ast.TryStar) -> None:  # noqa: N802
        self._visit_try(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        self.generic_visit(node)


def scan_file(path: Path, root: Path) -> tuple[BroadHandler, ...]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    relative_path = path.relative_to(root).as_posix()
    visitor = _HandlerVisitor(relative_path, source)
    visitor.visit(tree)
    return tuple(visitor.handlers)


def scan_repository(root: Path) -> tuple[BroadHandler, ...]:
    handlers: list[BroadHandler] = []
    for path in _iter_python_paths(root):
        handlers.extend(scan_file(path, root))
    return tuple(handlers)


def _parse_entry(raw: object, index: int) -> BaselineEntry:
    if not isinstance(raw, dict):
        raise BaselineError(f"legacy_handlers[{index}] must be an object")
    if set(raw) != {"path", "scope", "caught", "digest"}:
        raise BaselineError(
            f"legacy_handlers[{index}] must contain path/scope/caught/digest only"
        )
    path = raw["path"]
    scope = raw["scope"]
    caught = raw["caught"]
    digest = raw["digest"]
    if not isinstance(path, str) or not path:
        raise BaselineError(f"legacy_handlers[{index}].path must be a non-empty string")
    if not isinstance(scope, str) or not scope:
        raise BaselineError(f"legacy_handlers[{index}].scope must be a non-empty string")
    if (
        not isinstance(caught, list)
        or not caught
        or any(not isinstance(item, str) or not item for item in caught)
    ):
        raise BaselineError(f"legacy_handlers[{index}].caught must be a string list")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise BaselineError(f"legacy_handlers[{index}].digest must be SHA-256 hex")
    return BaselineEntry(path=path, scope=scope, caught=tuple(caught), digest=digest)


def load_baseline(path: Path) -> Baseline:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BaselineError(f"baseline is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BaselineError(f"baseline is invalid JSON: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {
        "version",
        "deferred_files",
        "legacy_handlers",
    }:
        raise BaselineError(
            "baseline must contain version/deferred_files/legacy_handlers only"
        )
    if raw["version"] != BASELINE_VERSION:
        raise BaselineError(
            f"unsupported baseline version {raw['version']!r}; expected {BASELINE_VERSION}"
        )
    deferred = raw["deferred_files"]
    if not isinstance(deferred, dict) or any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        or not value.strip()
        for key, value in deferred.items()
    ):
        raise BaselineError("deferred_files must map paths to non-empty reasons")
    legacy = raw["legacy_handlers"]
    if not isinstance(legacy, list):
        raise BaselineError("legacy_handlers must be a list")
    entries = tuple(_parse_entry(item, index) for index, item in enumerate(legacy))
    if list(entries) != sorted(entries):
        raise BaselineError("legacy_handlers must be deterministically sorted")
    return Baseline(
        deferred_files={key: value.strip() for key, value in deferred.items()},
        legacy_handlers=entries,
    )


def _policy_violations(handler: BroadHandler) -> list[Violation]:
    violations: list[Violation] = []
    if handler.marker_error:
        violations.append(
            Violation(handler.path, handler.line, "invalid-marker", handler.marker_error)
        )
        return violations
    marker = handler.marker
    if handler.catches_base_exception and handler.has_local_pass and (
        marker is None or marker.category != "cleanup"
    ):
        violations.append(
            Violation(
                handler.path,
                handler.line,
                "base-exception-pass",
                "BaseException/bare pass requires an explicit cleanup classification and reason",
            )
        )
    if (
        marker
        and marker.category == "fallback_recorded"
        and not handler.has_recording_evidence
    ):
        violations.append(
            Violation(
                handler.path,
                handler.line,
                "unrecorded-fallback",
                "fallback_recorded requires a direct safe log or structured record statement",
            )
        )
    return violations


def _is_reviewed(handler: BroadHandler) -> bool:
    return bool(handler.marker or handler.propagates or handler.maps_typed_error)


def _validate_deferred_files(
    root: Path,
    baseline: Baseline,
    handlers: Sequence[BroadHandler],
) -> list[Violation]:
    violations: list[Violation] = []
    handler_paths = {handler.path for handler in handlers}
    scoped_paths = {
        path.relative_to(root).as_posix()
        for path in _iter_python_paths(root)
    }
    for path, reason in sorted(baseline.deferred_files.items()):
        if path not in scoped_paths:
            violations.append(
                Violation(
                    path,
                    0,
                    "invalid-deferred-file",
                    f"deferred path is missing or outside production scope ({reason})",
                )
            )
        elif path not in handler_paths:
            violations.append(
                Violation(
                    path,
                    0,
                    "stale-deferred-file",
                    f"deferred file no longer contains a broad handler ({reason})",
                )
            )
    return violations


def _orphan_marker_violations(
    root: Path,
    handlers: Sequence[BroadHandler],
    deferred: set[str],
) -> list[Violation]:
    header_ranges: dict[str, list[tuple[int, int]]] = {}
    for handler in handlers:
        header_ranges.setdefault(handler.path, []).append(
            (handler.line, handler.header_end)
        )
    violations: list[Violation] = []
    for path in _iter_python_paths(root):
        relative_path = path.relative_to(root).as_posix()
        if relative_path in deferred:
            continue
        comments = _comment_lines(path.read_text(encoding="utf-8"))
        for line, values in comments.items():
            for comment in values:
                if MARKER_PREFIX not in comment:
                    continue
                if not any(
                    start <= line <= end
                    for start, end in header_ranges.get(relative_path, ())
                ):
                    violations.append(
                        Violation(
                            relative_path,
                            line,
                            "orphan-marker",
                            "classification marker is not attached to a broad except header",
                        )
                    )
    return violations


def collect_violations(root: Path, baseline_path: Path) -> tuple[Violation, ...]:
    try:
        baseline = load_baseline(baseline_path)
    except BaselineError as exc:
        return (Violation(baseline_path.as_posix(), 0, "invalid-baseline", str(exc)),)

    handlers = scan_repository(root)
    violations = _validate_deferred_files(root, baseline, handlers)
    deferred = set(baseline.deferred_files)
    violations.extend(_orphan_marker_violations(root, handlers, deferred))
    checked = [handler for handler in handlers if handler.path not in deferred]
    for handler in checked:
        violations.extend(_policy_violations(handler))

    current_legacy = Counter(
        handler.baseline_entry
        for handler in checked
        if not _is_reviewed(handler) and not _policy_violations(handler)
    )
    expected_legacy = Counter(baseline.legacy_handlers)
    for entry, count in sorted((current_legacy - expected_legacy).items()):
        line = next(
            (
                handler.line
                for handler in checked
                if handler.baseline_entry == entry
            ),
            0,
        )
        violations.append(
            Violation(
                entry.path,
                line,
                "new-broad-handler",
                f"{count} unclassified handler(s) are not in the legacy baseline",
            )
        )
    for entry, count in sorted((expected_legacy - current_legacy).items()):
        violations.append(
            Violation(
                entry.path,
                0,
                "stale-baseline-entry",
                f"remove {count} obsolete legacy fingerprint(s) after reviewing the change",
            )
        )
    return tuple(sorted(set(violations)))


def _serialize_baseline(
    deferred_files: Mapping[str, str],
    legacy_handlers: Sequence[BaselineEntry],
) -> str:
    lines = ["{", f'  "version": {BASELINE_VERSION},', '  "deferred_files": {']
    deferred_items = sorted(deferred_files.items())
    for index, (path, reason) in enumerate(deferred_items):
        suffix = "," if index + 1 < len(deferred_items) else ""
        lines.append(
            f"    {json.dumps(path, ensure_ascii=True)}: "
            f"{json.dumps(reason, ensure_ascii=True)}{suffix}"
        )
    lines.extend(["  },", '  "legacy_handlers": ['])
    for index, entry in enumerate(legacy_handlers):
        suffix = "," if index + 1 < len(legacy_handlers) else ""
        rendered = json.dumps(
            entry.as_json(),
            ensure_ascii=True,
            separators=(",", ":"),
        )
        lines.append(f"    {rendered}{suffix}")
    lines.extend(["  ]", "}"])
    return "\n".join(lines) + "\n"


def write_baseline(root: Path, baseline_path: Path) -> int:
    baseline = load_baseline(baseline_path)
    handlers = scan_repository(root)
    violations = _validate_deferred_files(root, baseline, handlers)
    deferred = set(baseline.deferred_files)
    violations.extend(_orphan_marker_violations(root, handlers, deferred))
    checked = [handler for handler in handlers if handler.path not in deferred]
    for handler in checked:
        violations.extend(_policy_violations(handler))
    if violations:
        for violation in sorted(set(violations)):
            print(f"[broad-exception] ERROR: {violation.render()}", file=sys.stderr)
        return 1
    current_legacy = Counter(
        handler.baseline_entry
        for handler in checked
        if not _is_reviewed(handler)
    )
    expected_legacy = Counter(baseline.legacy_handlers)
    added = current_legacy - expected_legacy
    if added:
        for entry, count in sorted(added.items()):
            print(
                "[broad-exception] ERROR: "
                f"{entry.path}: baseline-expansion: refusing {count} new or "
                "modified unclassified handler(s); classify or narrow them instead",
                file=sys.stderr,
            )
        return 1
    legacy_handlers = sorted((current_legacy & expected_legacy).elements())
    baseline_path.write_text(
        _serialize_baseline(baseline.deferred_files, legacy_handlers),
        encoding="utf-8",
    )
    print(
        f"[broad-exception] wrote {len(legacy_handlers)} legacy fingerprints "
        f"to {baseline_path}"
    )
    return 0


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Rewrite legacy fingerprints after manually reviewing each change.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root.resolve()
    baseline_path = args.baseline.resolve()
    if args.write_baseline:
        try:
            return write_baseline(root, baseline_path)
        except BaselineError as exc:
            print(f"[broad-exception] ERROR: invalid-baseline: {exc}", file=sys.stderr)
            return 1
    violations = collect_violations(root, baseline_path)
    if violations:
        for violation in violations:
            print(f"[broad-exception] ERROR: {violation.render()}", file=sys.stderr)
        return 1
    baseline = load_baseline(baseline_path)
    print(
        f"[broad-exception] OK: {len(baseline.legacy_handlers)} legacy "
        f"fingerprints, {len(baseline.deferred_files)} deferred files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
