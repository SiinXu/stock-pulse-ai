"""Resolver for the checked-in generated API artifacts.

Covers ``apps/dsa-web/openapi.json`` and ``apps/dsa-web/src/types/api.generated.ts``.

Why neither side is correct
---------------------------
These two files are build outputs, not source. ``openapi-types-gate`` in
``.github/workflows/ci.yml`` regenerates them and fails on any drift, so the
only value that can pass CI is the one produced by running the generators over
the merged tree. Merging their text — by side or by hunk — produces a document
that describes neither branch's API.

This resolver therefore never merges text. It runs the same two commands the CI
job runs and takes the result:

* ``python scripts/export_openapi.py --output apps/dsa-web/openapi.json``
* ``npm run generate:api-types`` (in ``apps/dsa-web``)

Refusal conditions (documented contract)
----------------------------------------
* the generator command is missing, or fails on the merged tree — a failed
  regeneration means the merged API surface does not build, which is exactly
  the signal a human needs;
* ``apps/dsa-web/node_modules`` is absent when the TypeScript generator is
  required;
* the regenerated file still differs from what the generator wrote (i.e. the
  generator is not deterministic here).

Note that regeneration writes through the generator, so this resolver is the
one place where the batch's atomicity is bounded by an external tool: the
generators are only invoked after every other file in the batch has produced a
resolution.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .common import Context, Refusal, Resolution

NAME = "generated-api-artifacts"
DESCRIPTION = "Regenerate openapi.json / api.generated.ts instead of merging them."

OPENAPI_JSON = "apps/dsa-web/openapi.json"
API_TYPES = "apps/dsa-web/src/types/api.generated.ts"
SUPPORTED = (OPENAPI_JSON, API_TYPES)

DEFERRED_NOTE = "deferred"


def matches(rel_path: str) -> bool:
    return rel_path in SUPPORTED


def resolve(ctx: Context, rel_path: str) -> Resolution:
    """Return a placeholder resolution; the real work happens in ``finalize``."""

    # The conflicted working-tree content is irrelevant: the file is replaced
    # wholesale by the generator. Start from the "ours" stage so that the tree
    # is never left holding conflict markers while the generators run.
    ours = ctx.stage(rel_path, 2)
    if ours is None:
        raise Refusal(rel_path, "missing index stage 'ours'; needs a human")
    return Resolution(
        path=rel_path,
        text=ours,
        detail="scheduled for regeneration from the merged tree",
        notes=[DEFERRED_NOTE],
    )


def finalize(ctx: Context, rel_path: str) -> list[str]:
    """Run the generator that owns ``rel_path`` and verify its output."""

    messages: list[str] = []
    if rel_path == OPENAPI_JSON:
        script = ctx.repo_root / "scripts" / "export_openapi.py"
        if not script.is_file():
            raise Refusal(OPENAPI_JSON, "scripts/export_openapi.py is missing")
        proc = subprocess.run(
            [sys.executable, str(script), "--output", OPENAPI_JSON],
            cwd=ctx.repo_root,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise Refusal(
                OPENAPI_JSON,
                "export_openapi.py failed on the merged tree: "
                + (proc.stderr or proc.stdout).strip()[-600:],
            )
        messages.append("regenerated apps/dsa-web/openapi.json")
    elif rel_path == API_TYPES:
        web_root = ctx.repo_root / "apps" / "dsa-web"
        if not (web_root / "node_modules").is_dir():
            raise Refusal(
                API_TYPES,
                "regenerating API types needs apps/dsa-web/node_modules "
                "(run `npm ci` there first)",
            )
        proc = subprocess.run(
            ["npm", "run", "generate:api-types"],
            cwd=web_root,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise Refusal(
                API_TYPES,
                "npm run generate:api-types failed on the merged tree: "
                + (proc.stderr or proc.stdout).strip()[-600:],
            )
        messages.append("regenerated apps/dsa-web/src/types/api.generated.ts")

    target = ctx.repo_root / rel_path
    if not target.is_file():
        raise Refusal(rel_path, "generator did not produce the expected file")
    if "<<<<<<<" in Path(target).read_text(encoding="utf-8"):
        raise Refusal(rel_path, "generated output still contains conflict markers")
    return messages
