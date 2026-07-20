"""Static guards for persistence transaction ownership."""

from __future__ import annotations

import ast
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ENDPOINT_ROOT = REPOSITORY_ROOT / "api" / "v1" / "endpoints"
TRANSACTION_PRIMITIVES = {
    "_run_write_transaction",
    "begin",
    "begin_nested",
    "commit",
    "get_session",
    "rollback",
    "session_scope",
}
TransactionExceptionKey = tuple[str, str, str, int]

# Health or operational adapters may be allowlisted only with a non-empty
# reason describing why their transaction cannot live behind a repository
# interface. Each key identifies one exact call site; keeping this empty
# documents that no current exception exists.
ENDPOINT_TRANSACTION_EXCEPTIONS: dict[TransactionExceptionKey, str] = {}


def _enclosing_function(parents: dict[ast.AST, ast.AST], node: ast.AST) -> str:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return "<module>"


def _scan_endpoint_transactions(
    endpoint_root: Path,
    repository_root: Path,
    exceptions: dict[TransactionExceptionKey, str],
) -> tuple[set[TransactionExceptionKey], list[str]]:
    observed_exceptions: set[TransactionExceptionKey] = set()
    violations: list[str] = []

    for path in sorted(endpoint_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        relative_path = path.relative_to(repository_root).as_posix()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            primitive = node.func.attr
            if primitive not in TRANSACTION_PRIMITIVES:
                continue

            key = (relative_path, _enclosing_function(parents, node), primitive, node.lineno)
            if key in exceptions:
                observed_exceptions.add(key)
                continue
            violations.append(f"{relative_path}:{node.lineno} calls {primitive}()")

    return observed_exceptions, violations


def test_endpoints_do_not_control_persistence_transactions() -> None:
    """HTTP adapters must not begin, commit, or roll back persistence work."""
    observed_exceptions, violations = _scan_endpoint_transactions(
        ENDPOINT_ROOT,
        REPOSITORY_ROOT,
        ENDPOINT_TRANSACTION_EXCEPTIONS,
    )

    assert not violations, "Endpoint transaction ownership detected:\n" + "\n".join(violations)
    assert observed_exceptions == set(ENDPOINT_TRANSACTION_EXCEPTIONS), (
        "Stale endpoint transaction exception; remove it or update the guarded call"
    )
    assert all(reason.strip() for reason in ENDPOINT_TRANSACTION_EXCEPTIONS.values())


def test_transaction_guard_scans_nested_endpoint_modules(tmp_path: Path) -> None:
    endpoint_root = tmp_path / "api" / "v1" / "endpoints"
    nested_endpoint = endpoint_root / "operations" / "health.py"
    nested_endpoint.parent.mkdir(parents=True)
    nested_endpoint.write_text(
        "def probe(session):\n"
        "    session.commit()\n",
        encoding="utf-8",
    )

    observed_exceptions, violations = _scan_endpoint_transactions(
        endpoint_root,
        tmp_path,
        {},
    )

    assert observed_exceptions == set()
    assert violations == ["api/v1/endpoints/operations/health.py:2 calls commit()"]


def test_history_delete_endpoint_only_delegates_persistence() -> None:
    """The history deletion adapter must not rebuild repository batching."""
    path = ENDPOINT_ROOT / "history.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "delete_history_by_code"
    )

    forbidden_calls = {
        node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {
            "delete_analysis_history_records",
            "get_analysis_history_paginated",
        }
    }

    assert forbidden_calls == set()
