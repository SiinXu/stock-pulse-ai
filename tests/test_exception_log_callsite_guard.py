"""Static guard for sanitized exception logging across production Python."""

from __future__ import annotations

import ast
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
        trusted_names.update(_trusted_import_names(lexical_scope))
        trusted_names.difference_update(
            _scope_untrusted_bindings(lexical_scope, trusted_methods)
        )
    return trusted_names, trusted_methods


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


def _exception_derived_names(
    scope: ast.AST,
    exception_names: set[str],
    trusted_sanitizer_names: set[str],
    trusted_sanitizer_methods: set[str],
) -> set[str]:
    """Track local aliases whose assigned value derives from an exception."""

    derived_names = set(exception_names)
    assignments: list[tuple[set[str], ast.AST]] = []
    for node in _walk_lexical_scope(scope):
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

    changed = True
    while changed:
        changed = False
        for targets, value in assignments:
            if targets - derived_names and _contains_raw_exception_object(
                value,
                derived_names,
                trusted_sanitizer_names,
                trusted_sanitizer_methods,
            ):
                derived_names.update(targets)
                changed = True
    return derived_names


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


def _closure_exception_names(
    scope: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> set[str]:
    """Return exception names captured from enclosing handlers or functions."""

    names: set[str] = set()
    current = parents.get(scope)
    while current is not None:
        if isinstance(current, ast.ExceptHandler) and current.name:
            names.add(current.name)
        elif isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            names.update(_exception_object_names(current))
        current = parents.get(current)
    names.difference_update(_scope_local_bindings(scope))
    return names


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
    exception_names: set[str],
    trusted_sanitizer_names: set[str],
    trusted_sanitizer_methods: set[str],
) -> bool:
    """Detect exception rendering that executes before a trusted sanitizer."""

    if isinstance(node, ast.Name):
        return False
    if isinstance(node, ast.FormattedValue):
        return _contains_raw_exception_object(
            node.value,
            exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
        )
    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Mod)
        and _contains_raw_exception_object(
            node,
            exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
        )
    ):
        return True
    if isinstance(node, ast.Attribute):
        if (
            node.attr == "__name__"
            and isinstance(node.value, ast.Call)
            and _call_name(node.value) == "type"
        ):
            return False
        if _contains_raw_exception_object(
            node,
            exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
        ):
            return True
    if (
        isinstance(node, ast.Call)
        and _call_name(node) in {"ascii", "format", "repr", "str"}
        and _contains_raw_exception_object(
            node,
            exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
        )
    ):
        return True
    return any(
        _contains_eager_exception_render(
            child,
            exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
        )
        for child in ast.iter_child_nodes(node)
    )


def _contains_raw_exception_object(
    node: ast.AST,
    exception_names: set[str],
    trusted_sanitizer_names: set[str],
    trusted_sanitizer_methods: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in exception_names
    if isinstance(node, ast.Call):
        if _is_trusted_sanitizer_call(
            node,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
        ):
            return _contains_eager_exception_render(
                node,
                exception_names,
                trusted_sanitizer_names,
                trusted_sanitizer_methods,
            )
        call_name = _call_name(node)
        if call_name == "type":
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
            exception_names,
            trusted_sanitizer_names,
            trusted_sanitizer_methods,
        )
        for child in ast.iter_child_nodes(node)
    )


def _contains_raw_traceback(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Call) and _call_name(child) in RAW_TRACEBACK_FORMATTERS
        for child in ast.walk(node)
    )


def find_exception_log_violations(path: str, source: str) -> list[ExceptionLogViolation]:
    tree = ast.parse(source, filename=path)
    logger_names = _logger_alias_names(tree)
    violations: set[ExceptionLogViolation] = set()
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    handler_names: dict[ast.ExceptHandler, set[str]] = {}

    scopes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, _LEXICAL_SCOPE_NODES)
    ]
    for scope in scopes:
        trusted_names, trusted_methods = _trusted_sanitizers_for_scope(
            path,
            scope,
            tree,
            parents,
        )
        annotated_exception_names = _exception_derived_names(
            scope,
            _exception_object_names(scope) | _closure_exception_names(scope, parents),
            trusted_names,
            trusted_methods,
        )
        for node in _walk_lexical_scope(scope):
            if (
                not isinstance(node, ast.Call)
                or not _is_logger_call(node, logger_names)
            ):
                continue
            exception_names = set(annotated_exception_names)
            handler = _enclosing_exception_handler(node, parents)
            if handler is not None:
                if handler not in handler_names:
                    bound_names = {handler.name} if handler.name else set()
                    handler_names[handler] = _exception_derived_names(
                        handler,
                        bound_names,
                        trusted_names,
                        trusted_methods,
                    )
                exception_names.update(handler_names[handler])
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
                    trusted_names,
                    trusted_methods,
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
