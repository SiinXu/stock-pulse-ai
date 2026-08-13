"""Generic resolver for the ``*_public_surface`` snapshot tests.

Covers, with one implementation:

* ``tests/agent/test_agent_orchestrator_public_surface.py``
* ``tests/agent/test_agent_executor_public_surface.py``
* ``tests/core/test_pipeline_public_surface.py``
* ``tests/notification/test_notification_public_surface.py``

Why neither side is correct
---------------------------
These files pin the *whole* public surface of a module: the set of public
names, and SHA-256 digests over the canonical AST of the extracted method
containers. Every pull request that adds an export or edits a method in the
guarded module rewrites those constants, so two pull requests always collide.

Both snapshots are pure functions of the merged source tree. Taking ``--ours``
keeps a digest of a tree that no longer exists; taking ``--theirs`` keeps a
digest of a *different* tree that also no longer exists. The only correct value
is the one recomputed from the merged tree, so this resolver recomputes it,
using the test file's own ``_container_ast_hash`` helper rather than a
re-implementation that could drift from it.

Refusal conditions (documented contract)
----------------------------------------
* either side of a hunk does not parse as Python;
* the two sides differ anywhere outside a top-level ``EXPECTED_*`` assignment
  (structural change: the helpers, the assertions, or the imports changed);
* a top-level ``EXPECTED_*`` constant exists on only one side;
* a conflicting constant is neither ``EXPECTED_PUBLIC_EXPORTS`` nor a constant
  whose two sides become identical once 64-hex digest literals are blanked —
  i.e. a method-name tuple or any other hand-maintained contract changed on
  both sides;
* ``EXPECTED_PUBLIC_EXPORTS`` is not the expected
  ``frozenset(\"\"\"...\"\"\".split())`` shape;
* the guarded module cannot be determined unambiguously from
  ``importlib.import_module("...")`` calls in the file;
* the guarded module (or anything it imports) fails to import from the merged
  tree, or the file has no ``_container_ast_hash`` helper while digests need
  recomputing — recomputation is the whole point, so a failure to recompute is
  a refusal, never a fallback to one side.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .common import Context, Refusal, Resolution, parse_conflicts, take_side

NAME = "public-surface"
DESCRIPTION = "Recompute module export sets and method AST digests from the merged tree."

SUPPORTED = (
    "tests/agent/test_agent_orchestrator_public_surface.py",
    "tests/agent/test_agent_executor_public_surface.py",
    "tests/core/test_pipeline_public_surface.py",
    "tests/notification/test_notification_public_surface.py",
    "tests/test_analysis_stage_facade.py",
)

# Owned by ``config_registry``, which needs its own recompute recipes.
EXCLUDED = ("tests/core/test_config_registry_public_exports.py",)

_PUBLIC_EXPORTS_NAME = "EXPECTED_PUBLIC_EXPORTS"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_WRAP_WIDTH = 76
_INDENT = "    "


def matches(rel_path: str) -> bool:
    if rel_path in EXCLUDED:
        return False
    if rel_path in SUPPORTED:
        return True
    if not (rel_path.startswith("tests/") and rel_path.endswith(".py")):
        return False
    if rel_path.endswith("_public_surface.py"):
        return True
    # Dispatch on content rather than on file naming: the same snapshot shape
    # is used by facade guards that are not named ``*_public_surface.py``.
    try:
        text = Path(rel_path).read_text(encoding="utf-8")
    except OSError:
        return False
    return "EXPECTED_PUBLIC_EXPORTS" in text


# --------------------------------------------------------------------------
# AST helpers
# --------------------------------------------------------------------------


def _parse(path: str, label: str, text: str) -> ast.Module:
    try:
        return ast.parse(text)
    except SyntaxError as exc:
        raise Refusal(path, f"{label} side does not parse as Python: {exc}") from exc


def _snapshot_assignments(tree: ast.Module) -> dict[str, ast.expr]:
    out: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id.startswith("EXPECTED_"):
                out[target.id] = node.value
    return out


def _skeleton(tree: ast.Module) -> str:
    """``ast.dump`` of the module with every ``EXPECTED_*`` value blanked."""

    clone = ast.parse(ast.unparse(tree))
    for node in clone.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id.startswith("EXPECTED_"):
                node.value = ast.Constant(value=None)
    return ast.dump(clone)


def _blank_digests(node: ast.expr) -> str:
    clone = ast.parse(ast.unparse(node), mode="eval").body
    for child in ast.walk(clone):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if _HEX64.match(child.value):
                child.value = "<digest>"
    return ast.dump(clone)


def _string_constants(node: ast.expr) -> list[ast.Constant]:
    found = [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]
    found.sort(key=lambda item: (item.lineno, item.col_offset))
    return found


def _import_module_literal(node: ast.expr) -> str | None:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "import_module"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value
    return None


def _all_import_targets(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        literal = _import_module_literal(node)
        if literal is not None:
            found.add(literal)
    return found


def _local_module_bindings(function: ast.AST) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            literal = _import_module_literal(node.value)
            if literal is not None:
                bindings[node.targets[0].id] = literal
    return bindings


def _functions(tree: ast.Module) -> list[ast.AST]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _module_for_exports(path: str, tree: ast.Module) -> str:
    """The module whose ``vars()`` the EXPECTED_PUBLIC_EXPORTS test compares."""

    for function in _functions(tree):
        names = {
            node.id for node in ast.walk(function) if isinstance(node, ast.Name)
        }
        if _PUBLIC_EXPORTS_NAME not in names:
            continue
        bindings = _local_module_bindings(function)
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "vars"
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in bindings
            ):
                return bindings[node.args[0].id]
    return _sole_target(path, tree, "the public-export set")


def _module_for_digests(path: str, tree: ast.Module) -> str:
    """The module whose containers ``_container_ast_hash`` digests."""

    for function in _functions(tree):
        uses_hasher = any(
            isinstance(node, ast.Name) and node.id == "_container_ast_hash"
            for node in ast.walk(function)
        )
        if not uses_hasher:
            continue
        bindings = _local_module_bindings(function)
        if len(bindings) == 1:
            return next(iter(bindings.values()))
    return _sole_target(path, tree, "the AST digests")


def _sole_target(path: str, tree: ast.Module, purpose: str) -> str:
    names = _all_import_targets(tree)
    if len(names) != 1:
        raise Refusal(
            path,
            f"cannot determine which module backs {purpose}: found "
            f"{sorted(names) or 'no'} importlib.import_module() targets",
        )
    return names.pop()


# --------------------------------------------------------------------------
# Recompute driver
# --------------------------------------------------------------------------

_DRIVER = r"""
import importlib, json, sys

sys.path.insert(0, {repo_root!r})

request = json.loads(sys.argv[1])
source = open(request["candidate"], encoding="utf-8").read()
namespace = {{"__name__": "_merge_resolver_public_surface", "__file__": request["origin"]}}
exec(compile(source, request["origin"], "exec"), namespace)

result = {{}}

if request["exports_target"]:
    module = importlib.import_module(request["exports_target"])
    result["exports"] = sorted(
        name for name in vars(module) if not name.startswith("_")
    )

digests = []
if request["digest_groups"]:
    module = importlib.import_module(request["digest_target"])
    hasher = namespace.get("_container_ast_hash")
    if hasher is None:
        print("the test file has no _container_ast_hash helper", file=sys.stderr)
        raise SystemExit(3)
    for group in request["digest_groups"]:
        container_name = None
        for candidate in reversed(group["candidates"]):
            value = getattr(module, candidate, None)
            if isinstance(value, type):
                container_name = candidate
                break
        if container_name is None:
            print("cannot resolve container for " + json.dumps(group), file=sys.stderr)
            raise SystemExit(4)
        digests.append(
            {{"key": group["key"], "value": hasher(getattr(module, container_name))}}
        )
result["digests"] = digests

sys.stdout.write(json.dumps(result))
"""


def _run_driver(ctx: Context, rel_path: str, candidate: str, request: dict) -> dict:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(candidate)
        candidate_path = handle.name
    driver_source = _DRIVER.format(repo_root=str(ctx.repo_root))
    payload = dict(request)
    payload["candidate"] = candidate_path
    payload["origin"] = str(ctx.repo_root / rel_path)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", driver_source, json.dumps(payload)],
            cwd=ctx.repo_root,
            capture_output=True,
            text=True,
        )
    finally:
        Path(candidate_path).unlink(missing_ok=True)
    if proc.returncode != 0:
        raise Refusal(
            rel_path,
            "could not recompute the snapshot from the merged tree "
            f"(exit {proc.returncode}): {proc.stderr.strip()[-600:]}",
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise Refusal(
            rel_path, f"snapshot recompute produced unreadable output: {exc}"
        ) from exc


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _render_exports(names: list[str]) -> str:
    lines: list[str] = []
    current: list[str] = []
    for name in names:
        trial = current + [name]
        if current and len(_INDENT) + len(" ".join(trial)) > _WRAP_WIDTH:
            lines.append(_INDENT + " ".join(current))
            current = [name]
        else:
            current = trial
    if current:
        lines.append(_INDENT + " ".join(current))
    body = "\n".join(lines)
    return (
        f"{_PUBLIC_EXPORTS_NAME} = frozenset(\n"
        f'{_INDENT}"""\n'
        f"{body}\n"
        f'{_INDENT}""".split()\n'
        ")"
    )


def _offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.split("\n"):
        offsets.append(offsets[-1] + len(line) + 1)
    return offsets


def _span(offsets: list[int], node: ast.AST) -> tuple[int, int]:
    start = offsets[node.lineno - 1] + node.col_offset
    end = offsets[node.end_lineno - 1] + node.end_col_offset
    return start, end


def _validate_exports_shape(path: str, node: ast.expr) -> None:
    ok = (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "frozenset"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Call)
        and isinstance(node.args[0].func, ast.Attribute)
        and node.args[0].func.attr == "split"
        and isinstance(node.args[0].func.value, ast.Constant)
        and isinstance(node.args[0].func.value.value, str)
    )
    if not ok:
        raise Refusal(
            path,
            f"{_PUBLIC_EXPORTS_NAME} is not the expected "
            'frozenset("""...""".split()) shape',
        )


def resolve(ctx: Context, rel_path: str) -> Resolution:
    conflicted = ctx.read_working(rel_path)
    segments = parse_conflicts(rel_path, conflicted)
    if not any(not isinstance(segment, str) for segment in segments):
        return Resolution(
            path=rel_path, text=conflicted, detail="no conflict markers", notes=[]
        )

    candidate_ours = take_side(segments, "ours")
    candidate_theirs = take_side(segments, "theirs")
    tree_ours = _parse(rel_path, "ours", candidate_ours)
    tree_theirs = _parse(rel_path, "theirs", candidate_theirs)

    if _skeleton(tree_ours) != _skeleton(tree_theirs):
        raise Refusal(
            rel_path,
            "the two sides differ outside the EXPECTED_* snapshot constants; "
            "this is a real code conflict, not a derived-value conflict",
        )

    assigns_ours = _snapshot_assignments(tree_ours)
    assigns_theirs = _snapshot_assignments(tree_theirs)
    only_one_side = set(assigns_ours) ^ set(assigns_theirs)
    if only_one_side:
        raise Refusal(
            rel_path,
            "snapshot constant(s) present on only one side: "
            + ", ".join(sorted(only_one_side)),
        )

    conflicting = [
        name
        for name in assigns_ours
        if ast.dump(assigns_ours[name]) != ast.dump(assigns_theirs[name])
    ]
    if not conflicting:
        return Resolution(
            path=rel_path,
            text=candidate_ours,
            detail="conflict hunks carried no snapshot difference",
            notes=[],
        )

    need_exports = False
    digest_nodes: list[tuple[str, ast.Constant, list[str]]] = []
    for name in sorted(conflicting):
        if name == _PUBLIC_EXPORTS_NAME:
            _validate_exports_shape(rel_path, assigns_ours[name])
            need_exports = True
            continue
        if _blank_digests(assigns_ours[name]) != _blank_digests(assigns_theirs[name]):
            raise Refusal(
                rel_path,
                f"{name} differs on both sides in more than its digest literals; "
                "a hand-maintained contract changed and needs a human",
            )
        strings = _string_constants(assigns_ours[name])
        preceding: list[str] = []
        added = 0
        for constant in strings:
            if _HEX64.match(constant.value):
                digest_nodes.append((name, constant, list(preceding)))
                added += 1
            else:
                preceding.append(constant.value)
        if not added:
            raise Refusal(
                rel_path,
                f"{name} conflicts but contains no recomputable digest literal",
            )

    request = {
        "exports_target": (
            _module_for_exports(rel_path, tree_ours) if need_exports else None
        ),
        "digest_target": (
            _module_for_digests(rel_path, tree_ours) if digest_nodes else None
        ),
        "digest_groups": [
            {"key": f"{index}", "candidates": candidates}
            for index, (_, _, candidates) in enumerate(digest_nodes)
        ],
    }
    result = _run_driver(ctx, rel_path, candidate_ours, request)

    text = candidate_ours
    offsets = _offsets(text)
    edits: list[tuple[int, int, str]] = []

    for index, (_, constant, _) in enumerate(digest_nodes):
        value = result["digests"][index]["value"]
        start, end = _span(offsets, constant)
        edits.append((start, end, json.dumps(value)))

    if need_exports:
        node = next(
            item
            for item in tree_ours.body
            if isinstance(item, ast.Assign)
            and isinstance(item.targets[0], ast.Name)
            and item.targets[0].id == _PUBLIC_EXPORTS_NAME
        )
        start, end = _span(offsets, node)
        edits.append((start, end, _render_exports(result["exports"])))

    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]

    detail = "recomputed " + ", ".join(
        part
        for part in (
            f"{_PUBLIC_EXPORTS_NAME} ({len(result.get('exports', []))} names)"
            if need_exports
            else "",
            f"{len(digest_nodes)} AST digest(s)" if digest_nodes else "",
        )
        if part
    )
    return Resolution(path=rel_path, text=text, detail=detail, notes=[])
