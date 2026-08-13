#!/usr/bin/env python3
"""Unified entry point for the derived-file merge resolvers.

    python scripts/merge_resolvers/resolve.py --list
    python scripts/merge_resolvers/resolve.py <conflicted files>...

Typical use during a merge train::

    git merge --no-commit --no-ff <pull request head>
    python scripts/merge_resolvers/resolve.py $(git diff --name-only --diff-filter=U)
    git diff --name-only --diff-filter=U   # empty when everything was resolved

Exit codes:
    0 — every requested file was resolved and staged
    2 — at least one file was refused; **nothing was written**
    1 — internal error (bad git state, unreadable file, resolver bug)

The batch is atomic on purpose. An earlier ad-hoc resolver validated and wrote
in a single pass, so refusing the last file left a half-resolved working tree
that looked resolved. Here every resolver computes its result in memory first
and the first refusal aborts the whole batch.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import ModuleType

if __package__ in (None, ""):  # direct `python scripts/merge_resolvers/resolve.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "scripts.merge_resolvers"

from scripts.merge_resolvers import (  # noqa: E402
    bundle_budget,
    config_registry,
    docs_index,
    generated_artifacts,
    i18n_locales,
    playground_catalog,
    public_surface,
)
from scripts.merge_resolvers.common import (  # noqa: E402
    Context,
    Refusal,
    Resolution,
    ResolverError,
    repo_root,
)

RESOLVERS: tuple[ModuleType, ...] = (
    bundle_budget,
    public_surface,
    config_registry,
    docs_index,
    playground_catalog,
    i18n_locales,
    generated_artifacts,
)

EXIT_OK = 0
EXIT_INTERNAL_ERROR = 1
EXIT_REFUSED = 2


def _select(rel_path: str) -> ModuleType | None:
    for module in RESOLVERS:
        if module.matches(rel_path):
            return module
    return None


def _print_list() -> None:
    print("Supported derived files (whole-repository state; neither merge side is correct):")
    print()
    for module in RESOLVERS:
        print(f"  {module.NAME}")
        print(f"      {module.DESCRIPTION}")
        patterns = getattr(module, "SUPPORTED", None) or (
            (module.RELATIVE_PATH,) if hasattr(module, "RELATIVE_PATH") else ()
        )
        for pattern in patterns:
            print(f"      - {pattern}")
        if module is i18n_locales:
            print("      - apps/dsa-web/src/i18n/**/*.ts")
        if module is public_surface:
            print("      - tests/**/*_public_surface.py")
        print()


def _normalise(repo: Path, argument: str) -> str:
    path = Path(argument)
    if path.is_absolute():
        try:
            return str(path.relative_to(repo))
        except ValueError as exc:
            raise ResolverError(f"{argument} is outside the repository") from exc
    return str(Path(argument).as_posix())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="resolve.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="*", help="conflicted paths, repository-relative")
    parser.add_argument(
        "--list", action="store_true", help="list the supported derived files and exit"
    )
    parser.add_argument(
        "--remeasure",
        action="store_true",
        help=(
            "allow resolvers to rebuild and measure the merged tree "
            "(bundle-size budgets); slow, but the only correct answer when both "
            "sides changed the same chunk"
        ),
    )
    parser.add_argument(
        "--no-stage",
        action="store_true",
        help="write the resolved files but do not `git add` them",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute every resolution and report, but write nothing",
    )
    args = parser.parse_args(argv)

    if args.list:
        _print_list()
        return EXIT_OK
    if not args.paths:
        parser.print_usage()
        print("no paths given; nothing to do")
        return EXIT_OK

    try:
        repo = repo_root()
    except ResolverError as exc:
        print(f"merge-resolvers: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR

    ctx = Context(repo_root=repo, remeasure=args.remeasure)

    try:
        paths = [_normalise(repo, argument) for argument in args.paths]
    except ResolverError as exc:
        print(f"merge-resolvers: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR

    # ---- phase 1: plan everything, write nothing -------------------------
    resolutions: dict[str, Resolution] = {}
    owners: dict[str, ModuleType] = {}
    refusals: list[str] = []

    for rel_path in paths:
        module = _select(rel_path)
        if module is None:
            refusals.append(
                f"{rel_path}: no resolver for this file. It is not a known "
                "whole-repository derived file, so the conflict is real and needs "
                "a human."
            )
            continue
        try:
            resolution = module.resolve(ctx, rel_path)
        except Refusal as exc:
            refusals.append(f"{exc.path}: {exc.reason}")
            continue
        except ResolverError as exc:
            print(f"merge-resolvers: internal error on {rel_path}: {exc}", file=sys.stderr)
            return EXIT_INTERNAL_ERROR
        except Exception as exc:  # noqa: BLE001 - surfaced as an internal error
            print(
                f"merge-resolvers: internal error on {rel_path}: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return EXIT_INTERNAL_ERROR
        resolutions[rel_path] = resolution
        owners[rel_path] = module

    # ---- phase 2: cross-file batch invariants ----------------------------
    if not refusals:
        for module in RESOLVERS:
            validator = getattr(module, "validate_batch", None)
            if validator is None:
                continue
            try:
                validator(ctx, {p: r for p, r in resolutions.items() if owners[p] is module})
            except Refusal as exc:
                refusals.append(f"{exc.path}: {exc.reason}")

    if refusals:
        print("merge-resolvers: REFUSED, nothing was written.", file=sys.stderr)
        for message in refusals:
            print(f"  REFUSE {message}", file=sys.stderr)
        return EXIT_REFUSED

    if args.dry_run:
        for rel_path, resolution in resolutions.items():
            print(f"  would resolve {rel_path}: {resolution.detail}")
        return EXIT_OK

    # ---- phase 3: write, regenerate, stage --------------------------------
    written: list[str] = []
    try:
        for rel_path, resolution in resolutions.items():
            if "regenerate" in resolution.notes:
                continue
            (repo / rel_path).write_text(resolution.text, encoding="utf-8")
            written.append(rel_path)

        regenerate = [
            rel_path
            for rel_path, resolution in resolutions.items()
            if "regenerate" in resolution.notes
        ]
        if regenerate:
            for rel_path in regenerate:
                (repo / rel_path).write_text(
                    resolutions[rel_path].text, encoding="utf-8"
                )
            for message in generated_artifacts.finalize(ctx, regenerate):
                print(f"  {message}")
            written.extend(regenerate)
    except Refusal as exc:
        print(
            "merge-resolvers: REFUSED during regeneration; "
            "run `git checkout --merge -- <paths>` to restore the conflicted state.",
            file=sys.stderr,
        )
        print(f"  REFUSE {exc.path}: {exc.reason}", file=sys.stderr)
        return EXIT_REFUSED
    except OSError as exc:
        print(f"merge-resolvers: internal error while writing: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR

    if not args.no_stage:
        ctx.git("add", "--", *written)

    for rel_path in written:
        resolution = resolutions[rel_path]
        print(f"  resolved {rel_path}: {resolution.detail}")
        for note in resolution.notes:
            if note in {"regenerate"} or note.startswith("incoming-rows="):
                continue
            print(f"      note: {note}")
    print(f"merge-resolvers: resolved {len(written)} file(s)")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
