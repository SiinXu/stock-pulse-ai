#!/usr/bin/env python3
"""Resolve supported derived-file conflicts as one fail-closed batch."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.merge_resolvers import additive_entries, bundle_size_budget, docs_index
from scripts.merge_resolvers import config_registry_snapshot, generated_openapi
from scripts.merge_resolvers import playground_catalog, public_surface, settings_help
from scripts.merge_resolvers.common import (
    RefusalError,
    atomic_write_and_stage,
    ensure_no_conflict_markers,
    load_conflict_context,
)


SUPPORTED_PATHS = frozenset(
    {
        bundle_size_budget.SUPPORTED_PATH,
        config_registry_snapshot.SUPPORTED_PATH,
        playground_catalog.SUPPORTED_PATH,
        *public_surface.SUPPORTED_PATHS,
        *docs_index.SUPPORTED_PATHS,
        *generated_openapi.SUPPORTED_PATHS,
    }
)

SUPPORTED_DISPLAY = tuple(
    sorted(path.as_posix() for path in SUPPORTED_PATHS)
    + list(additive_entries.SUPPORTED_PATTERNS)
    + list(settings_help.SUPPORTED_PATTERNS)
)


def _is_supported(path: Path) -> bool:
    return (
        path in SUPPORTED_PATHS
        or additive_entries.is_supported(path)
        or settings_help.is_supported(path)
    )


def _repository_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "not inside a Git repository")
    return Path(result.stdout.strip()).resolve()


def _normalize_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    absolute = candidate.resolve() if candidate.is_absolute() else (Path.cwd() / candidate).resolve()
    try:
        return absolute.relative_to(root)
    except ValueError as exc:
        raise RefusalError(candidate, "path is outside the repository") from exc


def plan_resolutions(root: Path, paths: list[Path]) -> dict[Path, bytes]:
    if not paths:
        raise RefusalError("<batch>", "no conflict files were provided")
    if len(set(paths)) != len(paths):
        raise RefusalError("<batch>", "duplicate conflict paths were provided")
    unsupported = [path for path in paths if not _is_supported(path)]
    if unsupported:
        raise RefusalError(unsupported[0], "unsupported conflict file")

    contexts = {path: load_conflict_context(root, path) for path in paths}
    outputs: dict[Path, bytes] = {}

    for path in sorted(path for path in contexts if additive_entries.is_supported(path)):
        outputs[path] = additive_entries.resolve(contexts[path]).encode()

    for path in sorted(path for path in contexts if settings_help.is_supported(path)):
        outputs[path] = settings_help.resolve(contexts[path]).encode()

    if config_registry_snapshot.SUPPORTED_PATH in contexts:
        path = config_registry_snapshot.SUPPORTED_PATH
        outputs[path] = config_registry_snapshot.resolve(contexts[path], root).encode()

    if bundle_size_budget.SUPPORTED_PATH in contexts:
        path = bundle_size_budget.SUPPORTED_PATH
        outputs[path] = bundle_size_budget.resolve(contexts[path]).encode()

    public_paths = set(contexts) & public_surface.SUPPORTED_PATHS
    for path in sorted(public_paths):
        outputs[path] = public_surface.resolve(contexts[path], root).encode()

    index_paths = set(contexts) & docs_index.SUPPORTED_PATHS
    if index_paths:
        for path, text in docs_index.resolve_pair(
            {path: contexts[path] for path in index_paths}
        ).items():
            outputs[path] = text.encode()

    if playground_catalog.SUPPORTED_PATH in contexts:
        path = playground_catalog.SUPPORTED_PATH
        outputs[path] = playground_catalog.resolve(contexts[path], root).encode()

    generated_paths = set(contexts) & generated_openapi.SUPPORTED_PATHS
    if generated_paths:
        outputs.update(
            generated_openapi.resolve(
                {path: contexts[path] for path in generated_paths},
                root,
            )
        )

    if not outputs:
        raise RefusalError("<batch>", "resolver produced no outputs")

    for path, body in outputs.items():
        if not body:
            raise RefusalError(path, "resolver produced empty output")
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RefusalError(path, "resolver produced non-UTF-8 output") from exc
        ensure_no_conflict_markers(path, text)
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Unmerged repository-relative files")
    parser.add_argument("--list", action="store_true", help="List supported files and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        for path in SUPPORTED_DISPLAY:
            print(path)
        return 0
    if not args.paths:
        print("no conflict files; nothing to do")
        return 0
    try:
        root = _repository_root()
        paths = [_normalize_path(root, value) for value in args.paths]
        outputs = plan_resolutions(root, paths)
        atomic_write_and_stage(root, outputs)
    except RefusalError as exc:
        print(f"REFUSE {exc.path}: {exc.reason}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"resolved {len(outputs)} derived file(s) atomically")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
