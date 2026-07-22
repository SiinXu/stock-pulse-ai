# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Static guard for sanitized exception logging across production Python."""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCOPED_DIRECTORIES = (
    REPO_ROOT / "src",
    REPO_ROOT / "data_provider",
    REPO_ROOT / "api",
    REPO_ROOT / "bot",
)
SCOPED_FILES = (
    REPO_ROOT / "main.py",
    REPO_ROOT / "server.py",
)
LOGGER_METHODS = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "exception",
    "critical",
    "log",
}
TRUSTED_SANITIZER_IMPORTS = {
    "src.agent.public_contract": {"sanitize_agent_diagnostic"},
    "src.llm.errors": {"classify_litellm_generation_param_error"},
    "src.llm.hermes": {"sanitize_hermes_error_text"},
    "src.llm.local_cli_backend": {"redact_diagnostic_text"},
    "src.utils.sanitize": {
        "sanitize_diagnostic_text",
        "sanitize_exception_chain",
    },
}
TRUSTED_LOCAL_SANITIZERS = {
    "src/agent/public_contract.py": {"sanitize_agent_diagnostic"},
    "src/analyzer.py": {
        "_sanitize_litellm_exception_text",
        "sanitize_generation_diagnostic",
    },
    "src/analyzer_parts/analysis.py": {"sanitize_generation_diagnostic"},
    "src/analyzer_parts/generation.py": {
        "_sanitize_litellm_exception_text",
        "sanitize_generation_diagnostic",
    },
    "src/llm/errors.py": {"classify_litellm_generation_param_error"},
    "src/llm/hermes.py": {"sanitize_hermes_error_text"},
    "src/llm/local_cli_backend.py": {"redact_diagnostic_text"},
    "src/market_analyzer.py": {"_sanitize_generation_diagnostic"},
    "src/services/intelligence_service.py": {"_sanitize_error"},
    "src/utils/sanitize.py": {
        "sanitize_diagnostic_text",
        "sanitize_exception_chain",
    },
}
RAW_TRACEBACK_FORMATTERS = {
    "format_exc",
    "format_exception",
    "print_exc",
}


@dataclass(frozen=True, order=True)
class ExceptionLogViolation:
    path: str
    line: int
    rule: str


def _is_logger_call(node: ast.Call, logger_names: set[str]) -> bool:
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in LOGGER_METHODS:
        return False
    owner = node.func.value
    if isinstance(owner, ast.Name):
        return (
            owner.id == "logging"
            or "logger" in owner.id.lower()
            or owner.id in logger_names
        )
    if isinstance(owner, ast.Attribute):
        return "logger" in owner.attr.lower()
    if isinstance(owner, ast.Call):
        return _call_name(owner) == "getLogger"
    return False


def _is_statically_false(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value in (None, False, 0)


def _annotation_names_exception(annotation: ast.AST | None) -> bool:
    if annotation is None:
        return False
    return "exception" in ast.unparse(annotation).lower()


_LEXICAL_SCOPE_NODES = (
    ast.Module,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
)


def _walk_lexical_scope(scope: ast.AST):
    """Yield nodes owned by one lexical scope, excluding nested scopes."""

    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        if isinstance(node, _LEXICAL_SCOPE_NODES):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _walk_scope_binding_nodes(scope: ast.AST):
    """Yield binding nodes while treating nested lexical scopes as values."""

    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, _LEXICAL_SCOPE_NODES):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _exception_object_names(scope: ast.AST) -> set[str]:
    """Return exception-annotated argument names for one lexical scope."""

    names: set[str] = set()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        function = scope
        arguments = (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
        names.update(
            argument.arg
            for argument in arguments
            if _annotation_names_exception(argument.annotation)
        )
        if function.args.vararg and _annotation_names_exception(function.args.vararg.annotation):
            names.add(function.args.vararg.arg)
        if function.args.kwarg and _annotation_names_exception(function.args.kwarg.annotation):
            names.add(function.args.kwarg.arg)
    return names


def _exception_annotation_names(tree: ast.Module) -> set[str]:
    names = {
        name
        for name, value in vars(builtins).items()
        if isinstance(value, type) and issubclass(value, BaseException)
    }
    known_lower = {name.lower() for name in names}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            imported_name = alias.name.rsplit(".", 1)[-1]
            lowered = imported_name.lower()
            if (
                lowered in known_lower
                or "exception" in lowered
                or lowered.endswith("error")
                or lowered.endswith("warning")
            ):
                names.add(alias.asname or imported_name)
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            candidate: str | None = None
            sources: set[str] = set()
            if isinstance(node, ast.ClassDef):
                candidate = node.name
                sources = {
                    base.id if isinstance(base, ast.Name) else base.attr
                    for base in node.bases
                    if isinstance(base, (ast.Name, ast.Attribute))
                }
            elif (
                isinstance(node, (ast.Assign, ast.AnnAssign))
                and isinstance(node.value, ast.Name)
            ):
                targets = (
                    {
                        name
                        for target in node.targets
                        for name in _assigned_names(target)
                    }
                    if isinstance(node, ast.Assign)
                    else _assigned_names(node.target)
                )
                if len(targets) == 1:
                    candidate = next(iter(targets))
                    sources = {node.value.id}
            if candidate and sources & names and candidate not in names:
                names.add(candidate)
                changed = True
    return names


def _annotation_requires_log_sanitization(
    annotation: ast.AST | None,
    exception_annotation_names: set[str],
) -> bool:
    if annotation is None:
        return True
    while isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            annotation = ast.parse(annotation.value, mode="eval").body
        except SyntaxError:
            return True
    names = {
        node.id.lower()
        for node in ast.walk(annotation)
        if isinstance(node, ast.Name)
    } | {
        node.attr.lower()
        for node in ast.walk(annotation)
        if isinstance(node, ast.Attribute)
    }
    direct_name = (
        annotation.id.lower()
        if isinstance(annotation, ast.Name)
        else annotation.attr.lower()
        if isinstance(annotation, ast.Attribute)
        else ""
    )
    known_exception_names = {
        item.lower()
        for item in exception_annotation_names
    }
    return direct_name in {"any", "object"} or any(
        name in known_exception_names
        or "exception" in name
        or name.endswith("error")
        for name in names
    )


def _non_import_binding_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.arg):
        return {node.arg}
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, ast.Assign):
        return {
            name
            for target in node.targets
            for name in _assigned_names(target)
        }
    if isinstance(node, (ast.AnnAssign, ast.NamedExpr, ast.For, ast.AsyncFor)):
        return _assigned_names(node.target)
    if isinstance(node, ast.comprehension):
        return _assigned_names(node.target)
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return {
            name
            for item in node.items
            if item.optional_vars is not None
            for name in _assigned_names(item.optional_vars)
        }
    if isinstance(node, ast.ExceptHandler) and node.name:
        return {node.name}
    if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
        return {node.name}
    if isinstance(node, ast.MatchMapping) and node.rest:
        return {node.rest}
    return set()


_BUILTIN_RECEIVER_DECORATORS = {"classmethod", "property"}
_IMPORTED_RECEIVER_DECORATORS = {
    "abstractmethod": {"abc"},
    "cached_property": {"functools"},
    "classmethod": {"builtins"},
    "contextmanager": {"contextlib"},
    "override": {"typing", "typing_extensions"},
    "property": {"builtins"},
    "retry": {"tenacity"},
}
_CALLED_RECEIVER_DECORATORS = {"retry"}


def _decorator_bindings(scope: ast.AST, name: str) -> list[str | None]:
    """Return exact import sources or ``None`` for unsafe name bindings."""

    bindings: list[str | None] = []
    for node in _walk_scope_binding_nodes(scope):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    bindings.append(None)
                elif (alias.asname or alias.name) == name:
                    bindings.append(
                        node.module
                        if node.level == 0
                        and alias.name == name
                        and alias.asname is None
                        else None
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if (alias.asname or alias.name.split(".")[0]) == name:
                    bindings.append(
                        alias.name
                        if alias.name == name and alias.asname is None
                        else None
                    )
        elif name in _non_import_binding_names(node):
            bindings.append(None)
    return bindings


def _is_supported_receiver_decorator(
    decorator: ast.AST,
    scope: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    called = isinstance(decorator, ast.Call)
    expression = decorator.func if called else decorator
    if isinstance(expression, ast.Name):
        name = expression.id
        binding_name = name
        qualified = False
    elif (
        isinstance(expression, ast.Attribute)
        and isinstance(expression.value, ast.Name)
    ):
        name = expression.attr
        binding_name = expression.value.id
        qualified = True
    else:
        return False
    if name not in _BUILTIN_RECEIVER_DECORATORS | _IMPORTED_RECEIVER_DECORATORS.keys():
        return False
    if called != (name in _CALLED_RECEIVER_DECORATORS):
        return False

    approved_sources = _IMPORTED_RECEIVER_DECORATORS.get(name, set())
    if qualified and binding_name not in approved_sources:
        return False
    trusted = name in _BUILTIN_RECEIVER_DECORATORS and not qualified
    for lexical_scope in _lexical_scope_chain(scope, parents)[:-1]:
        bindings = _decorator_bindings(lexical_scope, binding_name)
        if bindings:
            trusted = len(bindings) == 1 and bindings[0] in (
                {binding_name}
                if qualified
                else approved_sources
            )
    return trusted


def _untrusted_log_parameter_names(
    scope: ast.AST,
    parents: dict[ast.AST, ast.AST],
    exception_annotation_names: set[str],
) -> set[str]:
    """Return formals that require explicit log sanitization."""

    if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return set()
    arguments = (
        *scope.args.posonlyargs,
        *scope.args.args,
        *scope.args.kwonlyargs,
        *((scope.args.vararg,) if scope.args.vararg else ()),
        *((scope.args.kwarg,) if scope.args.kwarg else ()),
    )
    positional = (*scope.args.posonlyargs, *scope.args.args)
    decorators = tuple(getattr(scope, "decorator_list", ()))
    decorators_preserve_receiver = all(
        _is_supported_receiver_decorator(
            decorator,
            scope,
            parents,
        )
        for decorator in decorators
    )
    receiver = (
        positional[0]
        if positional
        and isinstance(parents.get(scope), ast.ClassDef)
        and decorators_preserve_receiver
        else None
    )
    return {
        argument.arg
        for argument in arguments
        if argument is not receiver
        and _annotation_requires_log_sanitization(
            argument.annotation,
            exception_annotation_names,
        )
    }


def _assigned_names(target: ast.AST) -> set[str]:
    """Return simple names bound by one assignment target."""

    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return {
            name
            for item in target.elts
            for name in _assigned_names(item)
        }
    return set()


def _scope_local_bindings(scope: ast.AST) -> set[str]:
    """Return names that can shadow module-level trusted imports in one scope."""

    bindings: set[str] = set()
    for node in _walk_scope_binding_nodes(scope):
        if isinstance(node, ast.arg):
            bindings.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bindings.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                bindings.update(_assigned_names(target))
        elif isinstance(node, ast.AnnAssign):
            bindings.update(_assigned_names(node.target))
        elif isinstance(node, ast.NamedExpr):
            bindings.update(_assigned_names(node.target))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            bindings.update(_assigned_names(node.target))
        elif isinstance(node, ast.comprehension):
            bindings.update(_assigned_names(node.target))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    bindings.update(_assigned_names(item.optional_vars))
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bindings.add(node.name)
        elif isinstance(node, ast.Import):
            bindings.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            bindings.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name != "*"
            )
    return bindings


def _trusted_import_names(scope: ast.AST) -> set[str]:
    trusted: set[str] = set()
    for node in _walk_lexical_scope(scope):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        approved = TRUSTED_SANITIZER_IMPORTS.get(node.module, set())
        trusted.update(
            alias.asname or alias.name
            for alias in node.names
            if alias.name in approved
        )
    return trusted


def _scope_untrusted_bindings(
    scope: ast.AST,
    trusted_local_definitions: set[str],
) -> set[str]:
    """Return bindings that invalidate a trusted sanitizer name in one scope."""

    bindings: set[str] = set()
    for node in _walk_scope_binding_nodes(scope):
        if isinstance(node, ast.ImportFrom):
            approved = TRUSTED_SANITIZER_IMPORTS.get(node.module or "", set())
            bindings.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name != "*" and alias.name not in approved
            )
        elif isinstance(node, ast.Import):
            bindings.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.arg):
            bindings.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_approved_definition = (
                isinstance(scope, (ast.Module, ast.ClassDef))
                and node.name in trusted_local_definitions
            )
            if not is_approved_definition:
                bindings.add(node.name)
        elif isinstance(node, ast.ClassDef):
            bindings.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                bindings.update(_assigned_names(target))
        elif isinstance(node, ast.AnnAssign):
            bindings.update(_assigned_names(node.target))
        elif isinstance(node, ast.NamedExpr):
            bindings.update(_assigned_names(node.target))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            bindings.update(_assigned_names(node.target))
        elif isinstance(node, ast.comprehension):
            bindings.update(_assigned_names(node.target))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    bindings.update(_assigned_names(item.optional_vars))
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bindings.add(node.name)
    return bindings


def _trusted_local_sanitizers(path: str) -> set[str]:
    normalized_path = Path(path).as_posix()
    for suffix, names in TRUSTED_LOCAL_SANITIZERS.items():
        if normalized_path.endswith(suffix):
            return set(names)
    return set()


def _trusted_sanitizer_aliases(
    scope: ast.AST,
    trusted_names: set[str],
) -> set[str]:
    records: list[tuple[str, ast.AST]] = []
    counts: dict[str, int] = {}
    for node in _walk_lexical_scope(scope):
        targets: set[str] = set()
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = {
                name
                for target in node.targets
                for name in _assigned_names(target)
            }
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = _assigned_names(node.target)
            value = node.value
        for target in targets:
            counts[target] = counts.get(target, 0) + 1
            if value is not None:
                records.append((target, value))

    aliases: set[str] = set()
    changed = True
    while changed:
        changed = False
        approved = trusted_names | aliases
        for target, value in records:
            if (
                counts[target] == 1
                and isinstance(value, ast.Name)
                and value.id in approved
                and target not in aliases
            ):
                aliases.add(target)
                changed = True
    return aliases


def _lexical_scope_chain(
    scope: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> list[ast.AST]:
    chain: list[ast.AST] = []
    current: ast.AST | None = scope
    while current is not None:
        if isinstance(current, _LEXICAL_SCOPE_NODES):
            chain.append(current)
        current = parents.get(current)
    return list(reversed(chain))


def _trusted_sanitizers_for_scope(
    path: str,
    scope: ast.AST,
    tree: ast.Module,
    parents: dict[ast.AST, ast.AST],
) -> tuple[set[str], set[str]]:
    trusted_methods = _trusted_local_sanitizers(path)
    trusted_names = set(trusted_methods)
    for lexical_scope in _lexical_scope_chain(scope, parents):
        if (
            isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            and isinstance(lexical_scope, ast.ClassDef)
        ):
            continue
        trusted_names.update(_trusted_import_names(lexical_scope))
        trusted_names.difference_update(
            _scope_untrusted_bindings(lexical_scope, trusted_methods)
        )
        trusted_names.update(
            _trusted_sanitizer_aliases(lexical_scope, trusted_names)
        )
    return trusted_names, trusted_methods


_BUILTIN_EXCEPTION_RENDERERS = {"ascii", "format", "repr", "str"}


def _exception_renderers_for_scope(
    scope: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> set[str]:
    """Resolve single-assignment renderer aliases visible as bare names."""

    renderer_names = set(_BUILTIN_EXCEPTION_RENDERERS)
    for lexical_scope in _lexical_scope_chain(scope, parents):
        if (
            isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            and isinstance(lexical_scope, ast.ClassDef)
        ):
            continue
        aliases = _trusted_sanitizer_aliases(lexical_scope, renderer_names)
        renderer_names.difference_update(
            _scope_untrusted_bindings(lexical_scope, set())
        )
        renderer_names.update(aliases)
    return renderer_names


def _logging_get_logger_import_names(tree: ast.AST) -> set[str]:
    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "logging"
        for alias in node.names
        if alias.name == "getLogger"
    }


def _is_logging_get_logger_call(
    node: ast.AST,
    imported_get_logger_names: set[str],
) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id in imported_get_logger_names
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "getLogger"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logging"
    )


def _logger_alias_names(tree: ast.AST) -> set[str]:
    """Return simple names assigned from logging.getLogger or another alias."""

    imported_get_logger_names = _logging_get_logger_import_names(tree)
    assignments: list[tuple[set[str], ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = {
                name
                for target in node.targets
                for name in _assigned_names(target)
            }
            assignments.append((targets, node.value))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            assignments.append((_assigned_names(node.target), node.value))
        elif isinstance(node, ast.NamedExpr):
            assignments.append((_assigned_names(node.target), node.value))

    logger_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for targets, value in assignments:
            is_logger = _is_logging_get_logger_call(
                value,
                imported_get_logger_names,
            ) or (
                isinstance(value, ast.Name) and value.id in logger_names
            )
            if is_logger and targets - logger_names:
                logger_names.update(targets)
                changed = True
    return logger_names


_TAINT_PRESERVING_VALUE_NODES = (
    ast.Attribute,
    ast.BinOp,
    ast.BoolOp,
    ast.Compare,
    ast.Dict,
    ast.FormattedValue,
    ast.IfExp,
    ast.JoinedStr,
    ast.List,
    ast.Set,
    ast.Starred,
    ast.Subscript,
    ast.Tuple,
    ast.UnaryOp,
)


def _is_simple_exception_derived_value(
    node: ast.AST,
    raw_exception_names: set[str],
    trusted_sanitizer_names: set[str],
    trusted_sanitizer_methods: set[str],
    renderer_names: set[str],
) -> bool:
    """Return whether a value still carries a raw exception object."""

    if isinstance(node, ast.Name):
        return node.id in raw_exception_names
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "__name__"
        and (
            (
                isinstance(node.value, ast.Attribute)
                and node.value.attr == "__class__"
            )
            or (
                isinstance(node.value, ast.Call)
                and _call_name(node.value) == "type"
                and "type" not in renderer_names
            )
        )
    ):
        return False
    if isinstance(node, ast.Call):
        if (
            _call_name(node) in renderer_names
            or _is_trusted_sanitizer_call(
                node,
                trusted_sanitizer_names,
                trusted_sanitizer_methods,
            )
        ):
            return False
    elif not isinstance(node, _TAINT_PRESERVING_VALUE_NODES):
        return False
    return any(
        _is_simple_exception_derived_value(
            child,
            raw_exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
            renderer_names,
        )
        for child in ast.iter_child_nodes(node)
    )


def _preceding_statements(
    scope: ast.AST,
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> list[ast.stmt]:
    groups: list[list[ast.stmt]] = []
    current: ast.AST | None = node
    while current is not None and current is not scope:
        parent = parents.get(current)
        if parent is None:
            break
        if isinstance(current, ast.stmt) and not (
            isinstance(parent, ast.ClassDef) and parent is not scope
        ):
            for _field, value in ast.iter_fields(parent):
                if isinstance(value, list) and current in value:
                    groups.append([
                        item
                        for item in value[:value.index(current)]
                        if isinstance(item, ast.stmt)
                    ])
                    break
        current = parent
    return [statement for group in reversed(groups) for statement in group]


def _enclosing_binding_events(
    scope: ast.AST,
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> list[tuple[set[str], ast.AST, bool]]:
    """Return structural bindings established before entering ``node``."""

    events: list[tuple[set[str], ast.AST, bool]] = []
    current: ast.AST | None = node
    while current is not None and current is not scope:
        parent = parents.get(current)
        if isinstance(parent, (ast.For, ast.AsyncFor)):
            if current in parent.body:
                events.append((_assigned_names(parent.target), parent.iter, True))
            elif current in parent.orelse:
                events.append((_assigned_names(parent.target), parent.iter, False))
        elif isinstance(parent, (ast.With, ast.AsyncWith)) and current in parent.body:
            events.extend(
                (_assigned_names(item.optional_vars), item.context_expr, True)
                for item in reversed(parent.items)
                if item.optional_vars is not None
            )
        current = parent
    return list(reversed(events))


def _is_eager_exception_derived_value(
    node: ast.AST,
    raw_exception_names: set[str],
    rendered_exception_names: set[str],
    trusted_sanitizer_names: set[str],
    trusted_sanitizer_methods: set[str],
    renderer_names: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in rendered_exception_names
    if isinstance(node, ast.Call):
        if (
            _call_name(node) not in renderer_names
            and not _is_trusted_sanitizer_call(
                node,
                trusted_sanitizer_names,
                trusted_sanitizer_methods,
            )
        ):
            return any(
                _is_eager_exception_derived_value(
                    child,
                    raw_exception_names,
                    rendered_exception_names,
                    trusted_sanitizer_names,
                    trusted_sanitizer_methods,
                    renderer_names,
                )
                for child in ast.iter_child_nodes(node)
            )
    elif isinstance(
        node,
        (ast.BoolOp, ast.Dict, ast.IfExp, ast.List, ast.Set, ast.Tuple),
    ):
        return any(
            _is_eager_exception_derived_value(
                child,
                raw_exception_names,
                rendered_exception_names,
                trusted_sanitizer_names,
                trusted_sanitizer_methods,
                renderer_names,
            )
            for child in ast.iter_child_nodes(node)
        )
    elif not isinstance(node, (ast.BinOp, ast.FormattedValue, ast.JoinedStr)):
        return False
    return _contains_eager_exception_render(
        node,
        raw_exception_names,
        rendered_exception_names,
        trusted_sanitizer_names,
        trusted_sanitizer_methods,
        renderer_names,
    )


def _terminal_assignment_values(
    statements: list[ast.stmt],
) -> dict[str, tuple[ast.AST, ...]]:
    """Return final values assigned on every path through a simple branch."""

    for statement in reversed(statements):
        if isinstance(statement, ast.Pass):
            continue
        if isinstance(statement, ast.Assign):
            return {
                name: (statement.value,)
                for target in statement.targets
                for name in _assigned_names(target)
            }
        if isinstance(statement, ast.AnnAssign) and statement.value is not None:
            return {
                name: (statement.value,)
                for name in _assigned_names(statement.target)
            }
        if isinstance(statement, ast.If) and statement.orelse:
            body_values = _terminal_assignment_values(statement.body)
            else_values = _terminal_assignment_values(statement.orelse)
            return {
                name: body_values[name] + else_values[name]
                for name in body_values.keys() & else_values.keys()
            }
        return {}
    return {}


def _assignment_events(
    statement: ast.stmt,
) -> list[tuple[set[str], ast.AST, bool]]:
    """Return definite and possible assignment effects from one statement."""

    events = [
        (_assigned_names(node.target), node.value, False)
        for node in _walk_lexical_scope(statement)
        if isinstance(node, ast.NamedExpr)
    ]
    events.extend(
        (
            {
                name
                for target in node.targets
                for name in _assigned_names(target)
            },
            node.value,
            False,
        )
        for node in _walk_lexical_scope(statement)
        if isinstance(node, ast.Assign)
    )
    events.extend(
        (_assigned_names(node.target), node.value, False)
        for node in _walk_lexical_scope(statement)
        if isinstance(node, ast.AnnAssign) and node.value is not None
    )
    events.sort(key=lambda item: (item[1].lineno, item[1].col_offset))
    if isinstance(statement, ast.Assign):
        events.append(
            (
                {
                    name
                    for target in statement.targets
                    for name in _assigned_names(target)
                },
                statement.value,
                True,
            )
        )
    elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
        events.append((_assigned_names(statement.target), statement.value, True))
    elif isinstance(statement, ast.If) and statement.orelse:
        body_values = _terminal_assignment_values(statement.body)
        else_values = _terminal_assignment_values(statement.orelse)
        for name in body_values.keys() & else_values.keys():
            combined = ast.Tuple(
                elts=[*body_values[name], *else_values[name]],
                ctx=ast.Load(),
            )
            ast.copy_location(combined, statement)
            events.append(({name}, combined, True))
    return events


def _exception_name_state_at_node(
    scope: ast.AST,
    node: ast.AST,
    raw_exception_names: set[str],
    rendered_exception_names: set[str],
    trusted_sanitizer_names: set[str],
    trusted_sanitizer_methods: set[str],
    renderer_names: set[str],
    parents: dict[ast.AST, ast.AST],
) -> tuple[set[str], set[str]]:
    """Track raw and eagerly rendered values along one definite statement path."""

    raw_names = set(raw_exception_names)
    rendered_names = set(rendered_exception_names)
    for targets, value, definite in _enclosing_binding_events(
        scope,
        node,
        parents,
    ):
        rendered = _is_eager_exception_derived_value(
            value,
            raw_names,
            rendered_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
            renderer_names,
        )
        raw = _is_simple_exception_derived_value(
            value,
            raw_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
            renderer_names,
        )
        if definite:
            raw_names.difference_update(targets)
            rendered_names.difference_update(targets)
        if rendered:
            rendered_names.update(targets)
        elif raw:
            raw_names.update(targets)
    for statement in _preceding_statements(scope, node, parents):
        for targets, value, definite in _assignment_events(statement):
            if not targets:
                continue
            rendered = _is_eager_exception_derived_value(
                value,
                raw_names,
                rendered_names,
                trusted_sanitizer_names,
                trusted_sanitizer_methods,
                renderer_names,
            )
            raw = _is_simple_exception_derived_value(
                value,
                raw_names,
                trusted_sanitizer_names,
                trusted_sanitizer_methods,
                renderer_names,
            )
            if definite:
                raw_names.difference_update(targets)
                rendered_names.difference_update(targets)
            if rendered:
                rendered_names.update(targets)
            elif raw:
                raw_names.update(targets)
    return raw_names, rendered_names


def _enclosing_exception_handler(
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> ast.ExceptHandler | None:
    """Return the handler that owns a logger call, if any."""

    current = parents.get(node)
    while current is not None:
        if isinstance(current, ast.ExceptHandler):
            return current
        if isinstance(current, _LEXICAL_SCOPE_NODES):
            return None
        current = parents.get(current)
    return None


def _nearest_enclosing_callable(
    scope: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | None:
    current = parents.get(scope)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return current
        current = parents.get(current)
    return None


def _enclosing_handler_names(
    node: ast.AST,
    boundary: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> set[str]:
    names: set[str] = set()
    current = parents.get(node)
    while current is not None and current is not boundary:
        if isinstance(current, ast.ExceptHandler) and current.name:
            names.add(current.name)
        current = parents.get(current)
    return names


def _closure_exception_state(
    path: str,
    scope: ast.AST,
    tree: ast.Module,
    parents: dict[ast.AST, ast.AST],
    exception_annotation_names: set[str],
    inferred_parameter_names: dict[ast.AST, set[str]] | None = None,
) -> tuple[set[str], set[str]]:
    """Return raw and rendered exception values captured by one callable."""

    enclosing = _nearest_enclosing_callable(scope, parents)
    if enclosing is None:
        return set(), set()

    captured_raw, captured_rendered = _closure_exception_state(
        path,
        enclosing,
        tree,
        parents,
        exception_annotation_names,
        inferred_parameter_names,
    )
    trusted_names, trusted_methods = _trusted_sanitizers_for_scope(
        path,
        enclosing,
        tree,
        parents,
    )
    renderer_names = _exception_renderers_for_scope(enclosing, parents)
    raw_names, rendered_names = _exception_name_state_at_node(
        enclosing,
        scope,
        captured_raw
        | _exception_object_names(enclosing)
        | (inferred_parameter_names or {}).get(enclosing, set())
        | _untrusted_log_parameter_names(
            enclosing,
            parents,
            exception_annotation_names,
        )
        | _enclosing_handler_names(scope, enclosing, parents),
        captured_rendered,
        trusted_names,
        trusted_methods,
        renderer_names,
        parents,
    )
    local_bindings = _scope_local_bindings(scope)
    raw_names.difference_update(local_bindings)
    rendered_names.difference_update(local_bindings)
    return raw_names, rendered_names


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _is_trusted_sanitizer_call(
    node: ast.Call,
    trusted_sanitizer_names: set[str],
    trusted_sanitizer_methods: set[str],
) -> bool:
    if isinstance(node.func, ast.Name):
        return node.func.id in trusted_sanitizer_names
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr in trusted_sanitizer_methods
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"cls", "self"}
    )


def _contains_eager_exception_render(
    node: ast.AST,
    raw_exception_names: set[str],
    rendered_exception_names: set[str],
    trusted_sanitizer_names: set[str],
    trusted_sanitizer_methods: set[str],
    renderer_names: set[str],
) -> bool:
    """Detect exception rendering that executes before a trusted sanitizer."""

    if isinstance(node, ast.Name):
        return node.id in rendered_exception_names
    if isinstance(node, ast.FormattedValue):
        return _contains_raw_exception_object(
            node.value,
            raw_exception_names,
            rendered_exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
            renderer_names,
        )
    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Mod)
        and _contains_raw_exception_object(
            node,
            raw_exception_names,
            rendered_exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
            renderer_names,
        )
    ):
        return True
    if isinstance(node, ast.Attribute):
        if (
            node.attr == "__name__"
            and isinstance(node.value, ast.Call)
            and _call_name(node.value) == "type"
            and "type" not in renderer_names
        ):
            return False
        if _contains_raw_exception_object(
            node,
            raw_exception_names,
            rendered_exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
            renderer_names,
        ):
            return True
    if (
        isinstance(node, ast.Call)
        and _call_name(node) in renderer_names
        and _contains_raw_exception_object(
            node,
            raw_exception_names,
            rendered_exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
            renderer_names,
        )
    ):
        return True
    return any(
        _contains_eager_exception_render(
            child,
            raw_exception_names,
            rendered_exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
            renderer_names,
        )
        for child in ast.iter_child_nodes(node)
    )


def _contains_raw_exception_object(
    node: ast.AST,
    raw_exception_names: set[str],
    rendered_exception_names: set[str],
    trusted_sanitizer_names: set[str],
    trusted_sanitizer_methods: set[str],
    renderer_names: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return (
            node.id in raw_exception_names
            or node.id in rendered_exception_names
        )
    if isinstance(node, ast.Call):
        if _is_trusted_sanitizer_call(
            node,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
        ):
            return _contains_eager_exception_render(
                node,
                raw_exception_names,
                rendered_exception_names,
                trusted_sanitizer_names,
                trusted_sanitizer_methods,
                renderer_names,
            )
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "__name__"
        and isinstance(node.value, ast.Call)
        and _call_name(node.value) == "type"
        and "type" not in renderer_names
    ):
        return False
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "__name__"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "__class__"
    ):
        return False
    return any(
        _contains_raw_exception_object(
            child,
            raw_exception_names,
            rendered_exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
            renderer_names,
        )
        for child in ast.iter_child_nodes(node)
    )


def _contains_raw_traceback(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Call) and _call_name(child) in RAW_TRACEBACK_FORMATTERS
        for child in ast.walk(node)
    )


def _module_local_call_targets(
    tree: ast.Module,
) -> dict[str, tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]]:
    """Return every provable module function candidate for each local name."""

    bindings: dict[str, list[ast.AST | str | None]] = {}
    for node in _walk_scope_binding_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bindings.setdefault(node.name, []).append(node)
            continue
        if isinstance(node, ast.Assign):
            names = {
                name
                for target in node.targets
                for name in _assigned_names(target)
            }
            candidate = node.value.id if isinstance(node.value, ast.Name) else None
            for name in names:
                bindings.setdefault(name, []).append(candidate)
            continue
        if isinstance(node, ast.AnnAssign):
            names = _assigned_names(node.target)
            candidate = (
                node.value.id
                if isinstance(node.value, ast.Name)
                else None
            )
            for name in names:
                bindings.setdefault(name, []).append(candidate)
            continue
        if isinstance(node, ast.Import):
            names = {alias.asname or alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names = {
                alias.asname or alias.name
                for alias in node.names
                if alias.name != "*"
            }
        else:
            names = _non_import_binding_names(node)
        for name in names:
            bindings.setdefault(name, []).append(None)

    # Decorator semantics may be opaque, so retaining the local sink is the
    # fail-closed choice when an exception-derived argument reaches it.
    resolved: dict[str, set[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for name, candidates in bindings.items():
        for candidate in candidates:
            if not isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            resolved.setdefault(name, set()).add(candidate)
    changed = True
    while changed:
        changed = False
        for name, candidates in bindings.items():
            target_candidates = {
                target
                for candidate in candidates
                if isinstance(candidate, str)
                for target in resolved.get(candidate, set())
            }
            current = resolved.setdefault(name, set())
            if target_candidates - current:
                current.update(target_candidates)
                changed = True
    return {
        name: tuple(sorted(candidates, key=lambda item: (item.lineno, item.col_offset)))
        for name, candidates in resolved.items()
        if candidates
    }


@dataclass(frozen=True)
class _ResolvedLocalCall:
    target: ast.FunctionDef | ast.AsyncFunctionDef
    skip_receiver: bool | None = False


def _scope_function_bindings(
    scope: ast.AST,
    name: str,
) -> tuple[
    bool,
    tuple[ast.FunctionDef | ast.AsyncFunctionDef | ast.Attribute | str, ...],
]:
    """Return every provable callable binding plus whether the name is local."""

    candidates: list[ast.AST | str | None] = []
    for node in _walk_scope_binding_nodes(scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                candidates.append(node)
            continue
        if isinstance(node, ast.Assign):
            names = {
                assigned
                for target in node.targets
                for assigned in _assigned_names(target)
            }
            if name in names:
                candidates.append(
                    node.value.id
                    if isinstance(node.value, ast.Name)
                    else node.value
                    if isinstance(node.value, ast.Attribute)
                    and isinstance(node.value.value, ast.Name)
                    and node.value.value.id in {"cls", "self"}
                    else None
                )
            continue
        if isinstance(node, ast.AnnAssign):
            if name in _assigned_names(node.target):
                candidates.append(
                    node.value.id
                    if isinstance(node.value, ast.Name)
                    else node.value
                    if isinstance(node.value, ast.Attribute)
                    and isinstance(node.value.value, ast.Name)
                    and node.value.value.id in {"cls", "self"}
                    else None
                )
            continue
        if isinstance(node, ast.NamedExpr):
            if name in _assigned_names(node.target):
                candidates.append(
                    node.value.id if isinstance(node.value, ast.Name) else None
                )
            continue
        if isinstance(node, ast.Import):
            names = {alias.asname or alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names = {
                alias.asname or alias.name
                for alias in node.names
                if alias.name != "*"
            }
        else:
            names = _non_import_binding_names(node)
        if name in names:
            candidates.append(None)
    if not candidates:
        return False, ()
    return True, tuple(
        dict.fromkeys(
            candidate
            for candidate in candidates
            if isinstance(
                candidate,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.Attribute, str),
            )
        )
    )


def _resolved_bare_call_targets(
    name: str,
    scope: ast.AST,
    targets: dict[str, tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]],
    parents: dict[ast.AST, ast.AST],
    seen: frozenset[tuple[ast.AST, str]] = frozenset(),
) -> tuple[_ResolvedLocalCall, ...]:
    key = (scope, name)
    if key in seen:
        return ()
    next_seen = seen | {key}
    for lexical_scope in reversed(_lexical_scope_chain(scope, parents)):
        if isinstance(lexical_scope, ast.ClassDef) and lexical_scope is not scope:
            continue
        if isinstance(lexical_scope, ast.Module):
            return tuple(
                _ResolvedLocalCall(target)
                for target in targets.get(name, ())
            )
        is_bound, binding_targets = _scope_function_bindings(lexical_scope, name)
        if not is_bound:
            continue
        resolved_calls: list[_ResolvedLocalCall] = []
        for target in binding_targets:
            if isinstance(target, str):
                resolved_calls.extend(
                    _resolved_bare_call_targets(
                        target,
                        lexical_scope,
                        targets,
                        parents,
                        next_seen,
                    )
                )
                continue
            if isinstance(target, ast.Attribute):
                class_scope = _enclosing_class(lexical_scope, parents)
                if class_scope is None:
                    continue
                method = _unique_class_method(class_scope, target.attr)
                if method is None:
                    continue
                resolved_calls.append(
                    _ResolvedLocalCall(
                        method,
                        _method_receiver_mode(method, parents),
                    )
                )
                continue
            resolved_calls.append(_ResolvedLocalCall(target))
        return tuple(dict.fromkeys(resolved_calls))
    return ()


def _enclosing_class(
    scope: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> ast.ClassDef | None:
    current: ast.AST | None = scope
    while current is not None:
        if isinstance(current, ast.ClassDef):
            return current
        current = parents.get(current)
    return None


def _scope_class_binding(
    scope: ast.AST,
    name: str,
) -> tuple[bool, ast.ClassDef | str | None]:
    """Resolve one class definition or alias, preserving shadowing ambiguity."""

    candidates: list[ast.ClassDef | str | None] = []
    for node in _walk_scope_binding_nodes(scope):
        if isinstance(node, ast.ClassDef):
            if node.name == name:
                candidates.append(node)
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                {
                    assigned
                    for target in node.targets
                    for assigned in _assigned_names(target)
                }
                if isinstance(node, ast.Assign)
                else _assigned_names(node.target)
            )
            if name in targets:
                candidates.append(
                    node.value.id if isinstance(node.value, ast.Name) else None
                )
            continue
        if isinstance(node, ast.Import):
            names = {alias.asname or alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names = {
                alias.asname or alias.name
                for alias in node.names
                if alias.name != "*"
            }
        else:
            names = _non_import_binding_names(node)
        if name in names:
            candidates.append(None)
    if not candidates:
        return False, None
    if len(candidates) == 1 and isinstance(candidates[0], (ast.ClassDef, str)):
        return True, candidates[0]
    return True, None


def _resolved_local_class(
    name: str,
    scope: ast.AST,
    parents: dict[ast.AST, ast.AST],
    seen: frozenset[tuple[ast.AST, str]] = frozenset(),
) -> ast.ClassDef | None:
    key = (scope, name)
    if key in seen:
        return None
    next_seen = seen | {key}
    for lexical_scope in reversed(_lexical_scope_chain(scope, parents)):
        is_bound, target = _scope_class_binding(lexical_scope, name)
        if not is_bound:
            continue
        if isinstance(target, str):
            return _resolved_local_class(
                target,
                lexical_scope,
                parents,
                next_seen,
            )
        return target
    return None


def _scope_instance_binding(
    scope: ast.AST,
    name: str,
) -> tuple[bool, str | None]:
    """Return the unique bare local constructor used to bind an instance."""

    candidates: list[str | None] = []
    for node in _walk_scope_binding_nodes(scope):
        targets: set[str] = set()
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = {
                assigned
                for target in node.targets
                for assigned in _assigned_names(target)
            }
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = _assigned_names(node.target)
            value = node.value
        elif isinstance(node, ast.Import):
            targets = {alias.asname or alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            targets = {
                alias.asname or alias.name
                for alias in node.names
                if alias.name != "*"
            }
        else:
            targets = _non_import_binding_names(node)
        if name not in targets:
            continue
        candidates.append(
            value.func.id
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            else None
        )
    if not candidates:
        return False, None
    if len(candidates) == 1 and isinstance(candidates[0], str):
        return True, candidates[0]
    return True, None


def _resolved_local_instance_class(
    name: str,
    scope: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> ast.ClassDef | None:
    for lexical_scope in reversed(_lexical_scope_chain(scope, parents)):
        is_bound, class_name = _scope_instance_binding(lexical_scope, name)
        if not is_bound:
            continue
        if class_name is None:
            return None
        return _resolved_local_class(class_name, lexical_scope, parents)
    return None


def _unique_class_method(
    class_scope: ast.ClassDef,
    name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    candidates: list[ast.AST | None] = []
    for node in _walk_scope_binding_nodes(class_scope):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            candidates.append(node)
        elif name in _non_import_binding_names(node):
            candidates.append(None)
    if len(candidates) != 1 or not isinstance(
        candidates[0],
        (ast.FunctionDef, ast.AsyncFunctionDef),
    ):
        return None
    return candidates[0]


def _method_receiver_mode(
    target: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
) -> bool | None:
    if not target.decorator_list:
        return True

    if len(target.decorator_list) == 1:
        decorator = target.decorator_list[0]
        for name, mode in (("staticmethod", False), ("classmethod", True)):
            if not isinstance(decorator, ast.Name) or decorator.id != name:
                continue
            trusted = True
            for lexical_scope in _lexical_scope_chain(target, parents)[:-1]:
                bindings = _decorator_bindings(lexical_scope, name)
                if bindings:
                    trusted = len(bindings) == 1 and bindings[0] == "builtins"
            if trusted:
                return mode

    if all(
        _is_supported_receiver_decorator(decorator, target, parents)
        for decorator in target.decorator_list
    ):
        return True
    return None


def _resolved_local_call_targets(
    node: ast.Call,
    scope: ast.AST,
    targets: dict[str, tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]],
    parents: dict[ast.AST, ast.AST],
) -> tuple[_ResolvedLocalCall, ...]:
    """Resolve a direct call when no enclosing callable shadows its name."""

    if isinstance(node.func, ast.Name):
        return _resolved_bare_call_targets(
            node.func.id,
            scope,
            targets,
            parents,
        )

    if not isinstance(node.func, ast.Attribute) or not isinstance(
        node.func.value,
        ast.Name,
    ):
        return ()
    receiver_name = node.func.value.id
    class_qualified = False
    if receiver_name in {"cls", "self"}:
        class_scope = _enclosing_class(scope, parents)
    else:
        class_scope = _resolved_local_class(receiver_name, scope, parents)
        class_qualified = class_scope is not None
        if class_scope is None:
            class_scope = _resolved_local_instance_class(
                receiver_name,
                scope,
                parents,
            )
    if class_scope is None:
        return ()
    target = _unique_class_method(class_scope, node.func.attr)
    if target is None:
        return ()
    receiver_mode = _method_receiver_mode(target, parents)
    if class_qualified and not target.decorator_list:
        receiver_mode = False
    return (_ResolvedLocalCall(target, receiver_mode),)


def _bound_call_arguments(
    resolved: _ResolvedLocalCall,
    node: ast.Call,
) -> list[tuple[str, ast.AST]]:
    """Bind statically explicit call arguments to local function parameters."""

    positional_values: list[ast.AST] = []
    for argument in node.args:
        if not isinstance(argument, ast.Starred):
            positional_values.append(argument)
            continue
        if not isinstance(argument.value, (ast.List, ast.Tuple)):
            return []
        positional_values.extend(argument.value.elts)

    keyword_values: list[tuple[str, ast.AST]] = []
    for keyword in node.keywords:
        if keyword.arg is not None:
            keyword_values.append((keyword.arg, keyword.value))
            continue
        if not isinstance(keyword.value, ast.Dict) or any(
            not isinstance(key, ast.Constant) or not isinstance(key.value, str)
            for key in keyword.value.keys
        ):
            return []
        keyword_values.extend(
            (key.value, value)
            for key, value in zip(keyword.value.keys, keyword.value.values)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        )

    target = resolved.target
    receiver_modes = (
        (False, True)
        if resolved.skip_receiver is None
        else (resolved.skip_receiver,)
    )
    all_bound: list[tuple[str, ast.AST]] = []
    for skip_receiver in receiver_modes:
        positional = (*target.args.posonlyargs, *target.args.args)
        if skip_receiver and positional:
            positional = positional[1:]
        named = {
            argument.arg: argument
            for argument in (*positional, *target.args.kwonlyargs)
        }
        bound: list[tuple[str, ast.AST]] = []
        for index, value in enumerate(positional_values):
            if index < len(positional):
                bound.append((positional[index].arg, value))
            elif target.args.vararg is not None:
                bound.append((target.args.vararg.arg, value))
            else:
                bound = []
                break
        else:
            for keyword_name, keyword_value in keyword_values:
                parameter = named.get(keyword_name)
                if parameter is not None:
                    bound.append((parameter.arg, keyword_value))
                elif target.args.kwarg is not None:
                    bound.append((target.args.kwarg.arg, keyword_value))
                else:
                    bound = []
                    break
        all_bound.extend(bound)
    return list(dict.fromkeys(all_bound))


def _infer_local_call_parameter_taint(
    path: str,
    tree: ast.Module,
    scopes: list[ast.AST],
    parents: dict[ast.AST, ast.AST],
    exception_annotation_names: set[str],
) -> dict[ast.AST, set[str]]:
    """Propagate actual exception-derived arguments into local callees."""

    targets = _module_local_call_targets(tree)
    inferred: dict[ast.AST, set[str]] = {}
    changed = True
    while changed:
        changed = False
        for scope in scopes:
            trusted_names, trusted_methods = _trusted_sanitizers_for_scope(
                path,
                scope,
                tree,
                parents,
            )
            renderer_names = _exception_renderers_for_scope(scope, parents)
            closure_raw_names, closure_rendered_names = _closure_exception_state(
                path,
                scope,
                tree,
                parents,
                exception_annotation_names,
                inferred,
            )
            initial_exception_names = (
                _exception_object_names(scope)
                | _untrusted_log_parameter_names(
                    scope,
                    parents,
                    exception_annotation_names,
                )
                | closure_raw_names
                | inferred.get(scope, set())
            )
            for node in _walk_lexical_scope(scope):
                if not isinstance(node, ast.Call):
                    continue
                call_targets = _resolved_local_call_targets(
                    node,
                    scope,
                    targets,
                    parents,
                )
                if not call_targets:
                    continue
                exception_names, rendered_names = _exception_name_state_at_node(
                    scope,
                    node,
                    initial_exception_names,
                    closure_rendered_names,
                    trusted_names,
                    trusted_methods,
                    renderer_names,
                    parents,
                )
                handler = _enclosing_exception_handler(node, parents)
                if handler is not None:
                    handler_names, handler_rendered_names = _exception_name_state_at_node(
                        handler,
                        node,
                        {handler.name} if handler.name else set(),
                        set(),
                        trusted_names,
                        trusted_methods,
                        renderer_names,
                        parents,
                    )
                    exception_names.update(handler_names)
                    rendered_names.update(handler_rendered_names)
                for target in call_targets:
                    for parameter, value in _bound_call_arguments(target, node):
                        if not _contains_raw_exception_object(
                            value,
                            exception_names,
                            rendered_names,
                            trusted_names,
                            trusted_methods,
                            renderer_names,
                        ):
                            continue
                        target_names = inferred.setdefault(target.target, set())
                        if parameter not in target_names:
                            target_names.add(parameter)
                            changed = True
    return inferred


def find_exception_log_violations(path: str, source: str) -> list[ExceptionLogViolation]:
    tree = ast.parse(source, filename=path)
    exception_annotation_names = _exception_annotation_names(tree)
    logger_names = _logger_alias_names(tree)
    violations: set[ExceptionLogViolation] = set()
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    scopes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, _LEXICAL_SCOPE_NODES)
    ]
    inferred_parameter_names = _infer_local_call_parameter_taint(
        path,
        tree,
        scopes,
        parents,
        exception_annotation_names,
    )
    for scope in scopes:
        trusted_names, trusted_methods = _trusted_sanitizers_for_scope(
            path,
            scope,
            tree,
            parents,
        )
        renderer_names = _exception_renderers_for_scope(scope, parents)
        closure_raw_names, closure_rendered_names = _closure_exception_state(
            path,
            scope,
            tree,
            parents,
            exception_annotation_names,
            inferred_parameter_names,
        )
        initial_exception_names = (
            _exception_object_names(scope)
            | _untrusted_log_parameter_names(
                scope,
                parents,
                exception_annotation_names,
            )
            | closure_raw_names
            | inferred_parameter_names.get(scope, set())
        )
        for node in _walk_lexical_scope(scope):
            if (
                not isinstance(node, ast.Call)
                or not _is_logger_call(node, logger_names)
            ):
                continue
            exception_names, rendered_names = _exception_name_state_at_node(
                scope,
                node,
                initial_exception_names,
                closure_rendered_names,
                trusted_names,
                trusted_methods,
                renderer_names,
                parents,
            )
            handler = _enclosing_exception_handler(node, parents)
            if handler is not None:
                handler_names, handler_rendered_names = _exception_name_state_at_node(
                    handler,
                    node,
                    {handler.name} if handler.name else set(),
                    set(),
                    trusted_names,
                    trusted_methods,
                    renderer_names,
                    parents,
                )
                exception_names.update(handler_names)
                rendered_names.update(handler_rendered_names)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "exception":
                violations.add(ExceptionLogViolation(path, node.lineno, "logger.exception"))

            for keyword in node.keywords:
                if keyword.arg == "exc_info" and not _is_statically_false(keyword.value):
                    violations.add(ExceptionLogViolation(path, node.lineno, "truthy-exc-info"))

            logged_values = (
                *node.args,
                *(keyword.value for keyword in node.keywords if keyword.arg != "exc_info"),
            )
            if any(
                _contains_raw_exception_object(
                    value,
                    exception_names,
                    rendered_names,
                    trusted_names,
                    trusted_methods,
                    renderer_names,
                )
                for value in logged_values
            ):
                violations.add(
                    ExceptionLogViolation(path, node.lineno, "raw-exception-object")
                )
            if any(_contains_raw_traceback(value) for value in logged_values):
                violations.add(ExceptionLogViolation(path, node.lineno, "raw-traceback"))

    return sorted(violations)


def _scoped_python_files() -> list[Path]:
    files = {
        path
        for directory in SCOPED_DIRECTORIES
        for path in directory.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    files.update(SCOPED_FILES)
    return sorted(files)


def test_callsite_guard_detects_all_unsafe_forms_and_accepts_shared_helper() -> None:
    source = '''
import logging
import traceback
from src.utils.sanitize import sanitize_diagnostic_text
logger = logging.getLogger(__name__)

def helper(exc: Exception):
    logger.exception("legacy")
    logger.error("legacy", exc_info=True)
    logger.warning("legacy: %s", exc)
    logger.error("legacy traceback: %s", traceback.format_exc())
    logging.getLogger(__name__).warning("legacy chained logger: %s", exc)
    logger.log(logging.ERROR, "legacy generic: %s", exc)
    raw_alias = str(exc)
    logger.error("legacy alias: %s", raw_alias)
    raw_repr_alias = repr(exc)
    logger.error("legacy repr alias: %s", raw_repr_alias)
    logger.info(
        "sanitized: exception_type=%s diagnostic=%s",
        type(exc).__name__,
        sanitize_diagnostic_text(exc),
    )
    log_safe_exception(logger, "Safe event", exc, error_code="safe_error")
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 8, "logger.exception"),
        ExceptionLogViolation("fixture.py", 9, "truthy-exc-info"),
        ExceptionLogViolation("fixture.py", 10, "raw-exception-object"),
        ExceptionLogViolation("fixture.py", 11, "raw-traceback"),
        ExceptionLogViolation("fixture.py", 12, "raw-exception-object"),
        ExceptionLogViolation("fixture.py", 13, "raw-exception-object"),
        ExceptionLogViolation("fixture.py", 15, "raw-exception-object"),
        ExceptionLogViolation("fixture.py", 17, "raw-exception-object"),
    ]


def test_callsite_guard_detects_eager_rendering_inside_sanitizer_and_logger_alias() -> None:
    source = '''
import logging
from src.utils.sanitize import sanitize_diagnostic_text
logger = logging.getLogger(__name__)
log = logging.getLogger(__name__)

def helper(exc: Exception):
    logger.error("unsafe inline str: %s", sanitize_diagnostic_text(str(exc)))
    logger.error("unsafe inline repr: %s", sanitize_diagnostic_text(repr(exc)))
    log.error("unsafe logger alias: %s", exc)
    logger.error("safe direct sanitizer: %s", sanitize_diagnostic_text(exc))
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 8, "raw-exception-object"),
        ExceptionLogViolation("fixture.py", 9, "raw-exception-object"),
        ExceptionLogViolation("fixture.py", 10, "raw-exception-object"),
    ]


def test_callsite_guard_only_trusts_sanitizers_from_approved_sources() -> None:
    local_shadow = '''
import logging
from src.utils.sanitize import sanitize_diagnostic_text
logger = logging.getLogger(__name__)

def helper(exc: Exception):
    def sanitize_diagnostic_text(value):
        return str(value)
    logger.error("unsafe local sanitizer: %s", sanitize_diagnostic_text(exc))
'''
    untrusted_import = '''
import logging
from attacker import sanitize_diagnostic_text
logger = logging.getLogger(__name__)

def helper(exc: Exception):
    logger.error("unsafe imported sanitizer: %s", sanitize_diagnostic_text(exc))
'''
    module_shadow = '''
import logging
from src.utils.sanitize import sanitize_diagnostic_text
logger = logging.getLogger(__name__)

def sanitize_diagnostic_text(value):
    return str(value)

def helper(exc: Exception):
    logger.error("unsafe module sanitizer: %s", sanitize_diagnostic_text(exc))
'''
    trusted_import = '''
import logging
from src.utils.sanitize import sanitize_diagnostic_text
logger = logging.getLogger(__name__)

def helper(exc: Exception):
    logger.error("safe sanitizer: %s", sanitize_diagnostic_text(exc))
'''

    assert find_exception_log_violations("local_shadow.py", local_shadow) == [
        ExceptionLogViolation("local_shadow.py", 9, "raw-exception-object")
    ]
    assert find_exception_log_violations("untrusted.py", untrusted_import) == [
        ExceptionLogViolation("untrusted.py", 7, "raw-exception-object")
    ]
    assert find_exception_log_violations("module_shadow.py", module_shadow) == [
        ExceptionLogViolation("module_shadow.py", 10, "raw-exception-object")
    ]
    assert find_exception_log_violations("trusted.py", trusted_import) == []


def test_callsite_guard_tracks_closure_exceptions_and_imported_get_logger_alias() -> None:
    closure_source = '''
import logging
logger = logging.getLogger(__name__)

def outer():
    try:
        raise RuntimeError("probe")
    except Exception as exc:
        def inner():
            logger.error("unsafe closure: %s", exc)
        inner()
'''
    imported_logger_source = '''
from logging import getLogger
log = getLogger(__name__)

def helper(exc: Exception):
    log.error("unsafe imported logger alias: %s", exc)
'''

    assert find_exception_log_violations("closure.py", closure_source) == [
        ExceptionLogViolation("closure.py", 10, "raw-exception-object")
    ]
    assert find_exception_log_violations(
        "imported_logger.py",
        imported_logger_source,
    ) == [
        ExceptionLogViolation("imported_logger.py", 6, "raw-exception-object")
    ]


def test_callsite_guard_rejects_unannotated_parameters_at_raw_log_sinks() -> None:
    source = '''
import logging
from typing import Any
from src.utils.sanitize import sanitize_diagnostic_text
logger = logging.getLogger(__name__)
clean = sanitize_diagnostic_text

class DomainError(Exception):
    pass

def emit(error):
    logger.error("failure: %s", error)  # sync-sink

async def emit_async(error):
    logger.error("failure: %s", error)  # async-sink

def relay(error):
    forwarded = error
    logger.error("failure: %s", forwarded)  # alias-sink

def identity(value):
    return value

def relay_through_call(error):
    forwarded = identity(error)
    logger.error("failure: %s", forwarded)  # call-alias-sink

def branch_retaint(error, replacement):
    error = sanitize_diagnostic_text(error)
    if replacement:
        error = replacement
    logger.error("failure: %s", error)  # branch-retaint-sink

class Reporter:
    def emit(self, error):
        logger.error("failure: %s", error)  # method-sink

class ReceiverCases:
    def ordinary(this):
        logger.info("receiver: %s", this.name)

    @staticmethod
    def static(self):
        logger.error("failure: %s", self)  # static-self-sink

def outer(error):
    def nested():
        logger.error("failure: %s", error)  # closure-sink
    nested()

def outer_alias(error):
    alias = error
    def nested():
        logger.error("failure: %s", alias)  # closure-alias-sink
    nested()

def outer_safe(error):
    error = sanitize_diagnostic_text(error)
    def nested():
        logger.info("safe: %s", error)
    nested()

def handler_closure():
    try:
        operation()
    except Exception as exc:
        alias = exc
        def nested():
            logger.error("failure: %s", alias)  # handler-closure-sink
        nested()

def safe(error):
    logger.error("safe: %s", sanitize_diagnostic_text(error))

def safe_overwrite(error):
    error = sanitize_diagnostic_text(error)
    logger.error("safe: %s", error)

def ordinary_overwrite(error):
    error = "ordinary"
    logger.info("safe: %s", error)

def eager_alias(error):
    rendered = str(error)
    logger.error("failure: %s", sanitize_diagnostic_text(rendered))  # eager-alias-sink

def type_alias(error):
    type = str
    logger.error("failure: %s", type(error))  # type-alias-sink

def safe_type_name(error):
    label = error.__class__.__name__
    logger.info("type: %s", label)

def safe_sanitizer_alias(error):
    logger.info("safe: %s", clean(error))

def typed_errors(value_error: ValueError, domain_error: DomainError, unknown: Any):
    logger.error("failure: %s", value_error)  # value-error-sink
    logger.error("failure: %s", domain_error)  # domain-error-sink
    logger.error("failure: %s", unknown)  # any-sink

def ordinary(message: str, count: int):
    logger.info("%s: %d", message, count)

def run():
    try:
        operation()
    except Exception as exc:
        emit(exc)
'''

    def line_number(marker: str) -> int:
        return next(
            line
            for line, content in enumerate(source.splitlines(), start=1)
            if marker in content
        )

    markers = {
        "sync-sink",
        "async-sink",
        "alias-sink",
        "call-alias-sink",
        "branch-retaint-sink",
        "method-sink",
        "closure-sink",
        "static-self-sink",
        "closure-alias-sink",
        "handler-closure-sink",
        "eager-alias-sink",
        "type-alias-sink",
        "value-error-sink",
        "domain-error-sink",
        "any-sink",
    }
    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation(
            "fixture.py",
            line_number(marker),
            "raw-exception-object",
        )
        for marker in sorted(markers, key=line_number)
    ]


def test_callsite_guard_propagates_actual_exception_arguments_across_local_calls() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

def emit(error: str):
    logger.error("failure: %s", error)

def run():
    try:
        operation()
    except Exception as exc:
        emit(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 6, "raw-exception-object")
    ]


def test_callsite_guard_propagates_to_trusted_retry_decorated_helpers() -> None:
    forms = (
        ("bare", "from tenacity import retry", "retry()"),
        ("qualified", "import tenacity", "tenacity.retry()"),
    )
    for case_name, import_line, decorator in forms:
        source = f'''
import logging
{import_line}
logger = logging.getLogger(__name__)

@{decorator}
def emit(error: str):
    logger.error("failure: %s", error)  # decorated-sink

def run():
    try:
        operation()
    except Exception as exc:
        emit(exc)
'''

        sink_line = next(
            line
            for line, content in enumerate(source.splitlines(), start=1)
            if "decorated-sink" in content
        )
        path = f"{case_name}_retry.py"
        assert find_exception_log_violations(path, source) == [
            ExceptionLogViolation(path, sink_line, "raw-exception-object")
        ]


def test_callsite_guard_fails_closed_for_opaque_decorated_local_helpers() -> None:
    forms = (
        (
            "aliased-retry",
            "from tenacity import retry as retry_alias",
            "retry_alias()",
        ),
        (
            "unknown-passthrough",
            "def passthrough(function):\n    return function",
            "passthrough",
        ),
    )
    for case_name, setup, decorator in forms:
        source = f'''
import logging
{setup}
logger = logging.getLogger(__name__)

@{decorator}
def emit(error: str):
    logger.error("failure: %s", error)  # opaque-decorated-sink

def run():
    try:
        operation()
    except Exception as exc:
        emit(exc)
'''

        sink_line = next(
            line
            for line, content in enumerate(source.splitlines(), start=1)
            if "opaque-decorated-sink" in content
        )
        path = f"{case_name}.py"
        assert find_exception_log_violations(path, source) == [
            ExceptionLogViolation(path, sink_line, "raw-exception-object")
        ]


def test_callsite_guard_binds_explicit_starred_exception_arguments() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

def emit_positional(error: str):
    logger.error("positional: %s", error)  # positional-sink

def emit_keyword(*, error: str):
    logger.error("keyword: %s", error)  # keyword-sink

def run():
    try:
        operation()
    except Exception as exc:
        emit_positional(*(exc,))
        emit_keyword(**{"error": exc})
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", line, "raw-exception-object")
        for line in (6, 9)
    ]


def test_callsite_guard_propagates_actual_exception_arguments_to_async_helpers() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

async def emit(error: str):
    logger.error("failure: %s", error)

async def run():
    try:
        await operation()
    except Exception as exc:
        await emit(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 6, "raw-exception-object")
    ]


def test_callsite_guard_propagates_actual_exception_arguments_to_methods() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

class Reporter:
    def emit(self, error: str):
        logger.error("instance: %s", error)  # instance-sink

    @staticmethod
    def emit_static(error: str):
        logger.error("static: %s", error)  # static-sink

    @classmethod
    def emit_class(cls, error: str):
        logger.error("class: %s", error)  # class-sink

    def run(self):
        try:
            operation()
        except Exception as exc:
            self.emit(exc)
            self.emit_static(exc)
            self.emit_class(exc)
'''

    def line_number(marker: str) -> int:
        return next(
            line
            for line, content in enumerate(source.splitlines(), start=1)
            if marker in content
        )

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", line_number(marker), "raw-exception-object")
        for marker in ("instance-sink", "static-sink", "class-sink")
    ]


def test_callsite_guard_propagates_to_provable_local_instances() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

class Reporter:
    def emit(self, error: str):
        logger.error("failure: %s", error)

def run():
    reporter = Reporter()
    try:
        operation()
    except Exception as exc:
        reporter.emit(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 7, "raw-exception-object")
    ]


def test_callsite_guard_propagates_to_class_qualified_methods() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

class Reporter:
    @staticmethod
    def emit_static(error: str):
        logger.error("static: %s", error)  # static-sink

    @classmethod
    def emit_class(cls, error: str):
        logger.error("class: %s", error)  # class-sink

def run():
    try:
        operation()
    except Exception as exc:
        Reporter.emit_static(exc)
        Reporter.emit_class(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", line, "raw-exception-object")
        for line in (8, 12)
    ]


def test_callsite_guard_propagates_through_bound_method_aliases() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

class Reporter:
    def emit(self, error: str):
        logger.error("failure: %s", error)

    def run(self):
        send = self.emit
        try:
            operation()
        except Exception as exc:
            send(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 7, "raw-exception-object")
    ]


def test_callsite_guard_fails_closed_on_ambiguous_method_decorator_provenance() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

def staticmethod(function):
    return function

class Reporter:
    @staticmethod
    def emit(self, error: str):
        logger.error("failure: %s", error)

    def run(self):
        try:
            operation()
        except Exception as exc:
            self.emit(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 11, "raw-exception-object")
    ]


def test_callsite_guard_propagates_actual_exception_arguments_to_closures() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

def run():
    def emit(error: str):
        logger.error("failure: %s", error)

    try:
        operation()
    except Exception as exc:
        emit(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 7, "raw-exception-object")
    ]


def test_callsite_guard_propagates_inferred_parameters_into_captured_closures() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

def relay(error: str):
    def emit():
        logger.error("failure: %s", error)
    emit()

def run():
    try:
        operation()
    except Exception as exc:
        relay(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 7, "raw-exception-object")
    ]


def test_callsite_guard_propagates_actual_exception_arguments_through_local_aliases() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

def emit(error: str):
    logger.error("failure: %s", error)

send = emit

def run():
    try:
        operation()
    except Exception as exc:
        send(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 6, "raw-exception-object")
    ]


def test_callsite_guard_fails_closed_on_rebound_local_call_aliases() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

def emit(error: str):
    logger.error("failure: %s", error)

def ignore(error: str):
    pass

send = emit
if condition:
    send = ignore

def run():
    try:
        operation()
    except Exception as exc:
        send(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 6, "raw-exception-object")
    ]


def test_callsite_guard_resolves_simple_aliases_in_the_nearest_closure() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

def run():
    def emit(error: str):
        logger.error("failure: %s", error)
    send = emit

    try:
        operation()
    except Exception as exc:
        send(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 7, "raw-exception-object")
    ]


def test_callsite_guard_fails_closed_on_rebound_closure_call_aliases() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

def run():
    def emit(error: str):
        logger.error("failure: %s", error)

    def ignore(error: str):
        pass

    send = emit
    if condition:
        send = ignore
    try:
        operation()
    except Exception as exc:
        send(exc)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 7, "raw-exception-object")
    ]


def test_callsite_guard_tracks_exception_values_bound_by_for_loops() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

def run():
    try:
        operation()
    except Exception as exc:
        for alias in [exc]:
            logger.error("failure: %s", alias)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 10, "raw-exception-object")
    ]


def test_callsite_guard_tracks_exception_values_bound_by_with_statements() -> None:
    source = '''
import logging
logger = logging.getLogger(__name__)

def run():
    try:
        operation()
    except Exception as exc:
        with context(exc) as alias:
            logger.error("failure: %s", alias)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 10, "raw-exception-object")
    ]


def test_callsite_guard_recognizes_exception_aliases_and_unsafe_decorators() -> None:
    source = '''
import logging
from contextlib import contextmanager
logger = logging.getLogger(__name__)

class LocalFailure(Exception):
    pass

Failure = ValueError
static_alias = staticmethod

def passthrough(function):
    return function

def annotated(warning: Warning, local: LocalFailure, alias: Failure):
    logger.error("warning: %s", warning)  # warning-sink
    logger.error("local: %s", local)  # local-failure-sink
    logger.error("alias: %s", alias)  # aliased-failure-sink

def quoted_annotations(warning: "Warning", failure: "Failure"):
    logger.error("warning: %s", warning)  # quoted-warning-sink
    logger.error("failure: %s", failure)  # quoted-failure-sink

class Reporter:
    @static_alias
    def aliased_static(first):
        logger.error("static: %s", first)  # aliased-static-sink

    @passthrough
    def decorated(first):
        logger.error("decorated: %s", first)  # unknown-decorator-sink

    def ordinary(self, message: str):
        logger.info("ordinary: %s", message)

    @contextmanager
    def managed(self):
        logger.info("managed: %s", self.name)
        yield
'''

    def line_number(marker: str) -> int:
        return next(
            line
            for line, content in enumerate(source.splitlines(), start=1)
            if marker in content
        )

    markers = {
        "warning-sink",
        "local-failure-sink",
        "aliased-failure-sink",
        "quoted-warning-sink",
        "quoted-failure-sink",
        "aliased-static-sink",
        "unknown-decorator-sink",
    }
    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation(
            "fixture.py",
            line_number(marker),
            "raw-exception-object",
        )
        for marker in sorted(markers, key=line_number)
    ]


def test_callsite_guard_recognizes_imported_exception_aliases() -> None:
    source = '''
import logging
from requests import RequestException as Failure
logger = logging.getLogger(__name__)

def emit(error: Failure):
    logger.error("failure: %s", error)
'''

    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation("fixture.py", 7, "raw-exception-object")
    ]


def test_callsite_guard_only_trusts_supported_receiver_decorators() -> None:
    supported_sources = {
        "abstractmethod": ("abc",),
        "cached_property": ("functools",),
        "classmethod": (None, "builtins"),
        "contextmanager": ("contextlib",),
        "override": ("typing", "typing_extensions"),
        "property": (None, "builtins"),
        "retry": ("tenacity",),
    }

    for decorator_name, modules in supported_sources.items():
        called = "()" if decorator_name == "retry" else ""
        decorator = f"{decorator_name}{called}"
        for module in modules:
            trusted_forms = (
                (
                    (f"from {module} import {decorator_name}", decorator),
                    (f"import {module}", f"{module}.{decorator_name}{called}"),
                )
                if module is not None
                else (("", decorator),)
            )
            for import_line, trusted_decorator in trusted_forms:
                trusted_source = f'''
import logging
{import_line}
logger = logging.getLogger(__name__)

class Reporter:
    @{trusted_decorator}
    def emit(self, message: str):
        logger.info("%s: %s", self.name, message)
'''
                assert find_exception_log_violations(
                    f"trusted_{decorator_name}.py",
                    trusted_source,
                ) == []

        local_binding = (
            "def retry():\n    return staticmethod"
            if decorator_name == "retry"
            else f"{decorator_name} = staticmethod"
        )
        local_source = f'''
import logging
{local_binding}
logger = logging.getLogger(__name__)

class Reporter:
    @{decorator}
    def emit(error):
        logger.error("failure: %s", error)
'''
        hostile_source = f'''
import logging
from attacker import {decorator_name}
logger = logging.getLogger(__name__)

class Reporter:
    @{decorator}
    def emit(error):
        logger.error("failure: %s", error)
'''
        assert find_exception_log_violations(
            f"local_{decorator_name}.py",
            local_source,
        ) == [
            ExceptionLogViolation(
                f"local_{decorator_name}.py",
                10 if decorator_name == "retry" else 9,
                "raw-exception-object",
            )
        ]
        assert find_exception_log_violations(
            f"hostile_{decorator_name}.py",
            hostile_source,
        ) == [
            ExceptionLogViolation(
                f"hostile_{decorator_name}.py",
                9,
                "raw-exception-object",
            )
        ]
        for module in (item for item in modules if item is not None):
            relative_source = f'''
import logging
from .{module} import {decorator_name}
logger = logging.getLogger(__name__)

class Reporter:
    @{decorator}
    def emit(error):
        logger.error("failure: %s", error)
'''
            assert find_exception_log_violations(
                f"relative_{decorator_name}.py",
                relative_source,
            ) == [
                ExceptionLogViolation(
                    f"relative_{decorator_name}.py",
                    9,
                    "raw-exception-object",
                )
            ]

    wildcard_import_source = '''
import logging
from tenacity import retry
from attacker import *
logger = logging.getLogger(__name__)

class Reporter:
    @retry()
    def emit(error):
        logger.error("failure: %s", error)
'''
    aliased_import_source = '''
import logging
from tenacity import retry as retry_alias
logger = logging.getLogger(__name__)

class Reporter:
    @retry_alias()
    def emit(error):
        logger.error("failure: %s", error)
'''
    pattern_shadow_source = '''
import logging
from tenacity import retry
logger = logging.getLogger(__name__)

match replacement:
    case retry:
        pass

class Reporter:
    @retry()
    def emit(error):
        logger.error("failure: %s", error)
'''
    assert find_exception_log_violations("wildcard.py", wildcard_import_source) == [
        ExceptionLogViolation("wildcard.py", 10, "raw-exception-object")
    ]
    assert find_exception_log_violations("aliased.py", aliased_import_source) == [
        ExceptionLogViolation("aliased.py", 9, "raw-exception-object")
    ]
    assert find_exception_log_violations("pattern.py", pattern_shadow_source) == [
        ExceptionLogViolation("pattern.py", 13, "raw-exception-object")
    ]


def test_callsite_guard_tracks_walrus_renderers_and_closure_value_state() -> None:
    source = '''
import logging
from src.utils.sanitize import sanitize_diagnostic_text
logger = logging.getLogger(__name__)
render = str

def walrus(error):
    (alias := error)
    logger.error("walrus: %s", alias)  # walrus-sink

def renderer_alias(error):
    logger.error(  # renderer-alias-sink
        "rendered: %s",
        sanitize_diagnostic_text(render(error)),
    )

def closure_states(error):
    raw = error
    rendered = str(error)
    def nested():
        logger.info("safe raw: %s", sanitize_diagnostic_text(raw))
        logger.error(  # closure-rendered-sink
            "unsafe rendered: %s",
            sanitize_diagnostic_text(rendered),
        )
    nested()

class Reporter:
    sanitize_diagnostic_text = render

    def safe(self, error):
        logger.info("safe: %s", sanitize_diagnostic_text(error))
'''

    def line_number(marker: str) -> int:
        return next(
            line
            for line, content in enumerate(source.splitlines(), start=1)
            if marker in content
        )

    markers = {
        "walrus-sink",
        "renderer-alias-sink",
        "closure-rendered-sink",
    }
    assert find_exception_log_violations("fixture.py", source) == [
        ExceptionLogViolation(
            "fixture.py",
            line_number(marker),
            "raw-exception-object",
        )
        for marker in sorted(markers, key=line_number)
    ]


def test_callsite_guard_clears_taint_when_every_branch_sanitizes() -> None:
    source = '''
import logging
from src.utils.sanitize import sanitize_diagnostic_text
logger = logging.getLogger(__name__)

def emit(error, use_primary):
    if use_primary:
        error = sanitize_diagnostic_text(error)
    else:
        error = sanitize_diagnostic_text(error)
    logger.error("failure: %s", error)
'''

    assert find_exception_log_violations("fixture.py", source) == []


def test_all_production_python_uses_shared_sanitized_exception_logging() -> None:
    violations = [
        violation
        for path in _scoped_python_files()
        for violation in find_exception_log_violations(
            str(path.relative_to(REPO_ROOT)),
            path.read_text(encoding="utf-8"),
        )
    ]

    assert violations == []
