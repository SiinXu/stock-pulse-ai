# Changelog fragments

Each pull request that changes user-visible product behaviour adds **one new
file** under this directory instead of editing `docs/CHANGELOG.md` directly.

## Why

Nearly every historical PR touched the single shared `docs/CHANGELOG.md`. Local
merges resolve that file with the `merge=union` driver, but GitHub's server-side
`DIRTY` status does not. Authors then re-synced `main`, re-ran the full
`backend-gate` (~35 minutes), and went dirty again as soon as the next PR
landed. Fragments are **new files**, so they never conflict and never mark
sibling PRs dirty. See issue #1284.

## File name

```
docs/changelog.d/<pr-or-slug>-<short-topic>.md
```

Examples: `1284-changelog-fragments.md`, `fix-fx-stale-flag.md`.

`README.md` in this directory is ignored by the collector.

## File content

One or more Keep-a-Changelog style lines, English only:

```markdown
- [Added] Short description of the change (Refs #123).
- [Fixed] Another line if needed (Refs #123).
```

Allowed types: `Added`, `Changed`, `Fixed`, `Docs`, `Tests`, `Chore`.

Blank lines and `#` comment lines are ignored. No `###` category headings.

## Commands

```bash
# CI / local validation (no writes)
python scripts/collect_changelog.py --check

# Release maintainers: fold fragments into docs/CHANGELOG.md [Unreleased]
python scripts/collect_changelog.py --consume
```

## Transition

Open PRs that already edit `docs/CHANGELOG.md` remain valid. The CI guard
accepts either a fragment **or** a direct `docs/CHANGELOG.md` edit until those
PRs land. New PRs should prefer fragments.
