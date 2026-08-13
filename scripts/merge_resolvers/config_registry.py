"""Resolver for ``tests/core/test_config_registry_public_exports.py``.

Why neither side is correct
---------------------------
This file is the configuration registry's whole-repository snapshot: the public
and private export sets of ``src.core.config_registry``, its module
annotations, and two SHA-256 digests over ``get_registered_field_keys()`` and
``build_schema_response()``. Every pull request that registers a configuration
key rewrites the digests, so any two such pull requests conflict on the same
two lines.

A digest of main's tree and a digest of the branch's tree are both digests of
trees that no longer exist after the merge. The correct value is recomputed by
running the registry from the merged tree — which is exactly what the test
itself does at assertion time.

Refusal conditions (documented contract)
----------------------------------------
* either side of a hunk does not parse as Python;
* the sides differ anywhere outside the top-level ``EXPECTED_*`` constants;
* an ``EXPECTED_*`` constant exists on only one side;
* a conflicting constant is not one of the four with a known recompute recipe
  (``EXPECTED_PUBLIC_EXPORTS``, ``EXPECTED_PRIVATE_EXPORTS``,
  ``EXPECTED_MODULE_ANNOTATIONS``, ``EXPECTED_REGISTERED_KEYS_SHA256``,
  ``EXPECTED_SCHEMA_SHA256``);
* importing ``src.core.config_registry`` from the merged tree fails, or the
  recompute subprocess returns anything unexpected. A failed recompute is a
  refusal, never a silent fallback to one side.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys

from .common import Context, Refusal, Resolution, parse_conflicts, take_side
from .public_surface import _offsets, _parse, _skeleton, _snapshot_assignments, _span

NAME = "config-registry-snapshot"
DESCRIPTION = "Recompute config-registry export sets and contract digests."

RELATIVE_PATH = "tests/core/test_config_registry_public_exports.py"
TARGET_MODULE = "src.core.config_registry"
INDENT = "    "

_SET_CONSTANTS = ("EXPECTED_PUBLIC_EXPORTS", "EXPECTED_PRIVATE_EXPORTS")
_DICT_CONSTANTS = ("EXPECTED_MODULE_ANNOTATIONS",)
_DIGEST_CONSTANTS = ("EXPECTED_REGISTERED_KEYS_SHA256", "EXPECTED_SCHEMA_SHA256")
KNOWN = _SET_CONSTANTS + _DICT_CONSTANTS + _DIGEST_CONSTANTS


def matches(rel_path: str) -> bool:
    return rel_path == RELATIVE_PATH


_DRIVER = r"""
import hashlib, json, sys

sys.path.insert(0, {repo_root!r})
import src.core.config_registry as registry


def digest(value, sort_keys=False):
    payload = json.dumps(value, sort_keys=sort_keys, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


public = sorted(name for name in dir(registry) if not name.startswith("_"))
compat = sorted(name for name in dir(registry) if not name.startswith("__"))
private = sorted(set(compat) - set(public))

sys.stdout.write(
    json.dumps(
        {{
            "EXPECTED_PUBLIC_EXPORTS": public,
            "EXPECTED_PRIVATE_EXPORTS": private,
            "EXPECTED_MODULE_ANNOTATIONS": dict(registry.__annotations__),
            "EXPECTED_REGISTERED_KEYS_SHA256": digest(
                registry.get_registered_field_keys()
            ),
            "EXPECTED_SCHEMA_SHA256": digest(
                registry.build_schema_response(), sort_keys=True
            ),
        }}
    )
)
"""


def _recompute(ctx: Context, rel_path: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _DRIVER.format(repo_root=str(ctx.repo_root))],
        cwd=ctx.repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise Refusal(
            rel_path,
            "could not recompute the registry snapshot from the merged tree: "
            + proc.stderr.strip()[-600:],
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise Refusal(rel_path, f"registry recompute produced bad output: {exc}") from exc


def _render_set(names: list[str]) -> str:
    body = "".join(f"{INDENT}{json.dumps(name)},\n" for name in names)
    return "{\n" + body + "}"


def _render_dict(mapping: dict[str, str]) -> str:
    body = "".join(
        f"{INDENT}{json.dumps(key)}: {json.dumps(value)},\n"
        for key, value in sorted(mapping.items())
    )
    return "{\n" + body + "}"


def _render_digest(value: str) -> str:
    # The value node is the bare string literal; the wrapping parentheses and
    # line breaks are part of the surrounding statement and must be preserved.
    return json.dumps(value)


def resolve(ctx: Context, rel_path: str) -> Resolution:
    conflicted = ctx.read_working(rel_path)
    segments = parse_conflicts(rel_path, conflicted)
    if all(isinstance(segment, str) for segment in segments):
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

    conflicting = sorted(
        name
        for name in assigns_ours
        if ast.dump(assigns_ours[name]) != ast.dump(assigns_theirs[name])
    )
    if not conflicting:
        return Resolution(
            path=rel_path,
            text=candidate_ours,
            detail="conflict hunks carried no snapshot difference",
            notes=[],
        )
    unknown = [name for name in conflicting if name not in KNOWN]
    if unknown:
        raise Refusal(
            rel_path,
            "no recompute recipe for conflicting constant(s): " + ", ".join(unknown),
        )

    values = _recompute(ctx, rel_path)
    text = candidate_ours
    offsets = _offsets(text)
    edits: list[tuple[int, int, str]] = []
    for name in conflicting:
        node = assigns_ours[name]
        start, end = _span(offsets, node)
        if name in _SET_CONSTANTS:
            replacement = _render_set(values[name])
        elif name in _DICT_CONSTANTS:
            replacement = _render_dict(values[name])
        else:
            replacement = _render_digest(values[name])
        edits.append((start, end, replacement))

    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]

    return Resolution(
        path=rel_path,
        text=text,
        detail="recomputed " + ", ".join(conflicting),
        notes=[],
    )
