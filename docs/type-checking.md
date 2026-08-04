# Python Type Checking (mypy ratchet)

- Status: `Living`
- Last verified: 2026-08-04
- Related: [Contributing Guide (EN)](CONTRIBUTING_EN.md), `mypy.ini`, `scripts/ci_gate.sh`

## Scope (current)

Type checking is **not** repo-wide.

| Item | Value |
| --- | --- |
| Tool | `mypy` (version pinned via `constraints.txt` / `.github/requirements-ci.txt`) |
| Config | [`mypy.ini`](../mypy.ini) |
| Checked paths | `src/schemas/` only (17 modules) |
| Import policy | `follow_imports = skip` so the rest of the tree is not pulled into the check |
| CI entry | `./scripts/ci_gate.sh` → `deterministic_checks` runs `python -m mypy --config-file mypy.ini` |

The rest of the Python tree remains untyped at the gate. flake8 still only
enforces syntax-level selectors (`E9,F63,F7,F82`).

## Local commands

```bash
# Install CI tooling (includes pinned mypy)
python -m pip install --upgrade --constraint constraints.txt pip
python -m pip install --build-constraint build-constraints.txt -r .github/requirements-ci.txt
python -m pip check

# Type-check the current ratchet scope
python -m mypy --config-file mypy.ini

# Same path as CI deterministic stage
./scripts/ci_gate.sh deterministic
```

If a change under `src/schemas/` introduces a new mypy error, fix the annotation
or typing issue in that package. Do not widen the checked surface to silence the
error, and do not disable the gate.

## How to expand coverage

Expand only when a package is already small and self-contained enough to pass
cleanly on its own:

1. Run `mypy` against the candidate package with `--follow-imports=skip`.
2. Fix annotations inside that package, or document temporary per-module
   exclusions in `mypy.ini` with a comment naming each excluded module and why.
3. Add the package path to `files =` in `mypy.ini`.
4. Keep `follow_imports = skip` until a later decision deliberately widens import
   following.
5. Update this document and add a one-line `[Unreleased]` changelog entry.

Do **not** enable repo-wide mypy in one step. The ratchet direction is
package-by-package growth of the clean set.

## Exclusions

No `src/schemas/` modules are currently excluded. If an exclusion is required
later, list it here and in `mypy.ini` with a named comment.

## Pin authority

mypy is installed from `.github/requirements-ci.txt` and locked by
`constraints.txt` through `scripts/check_dependency_locks.py`.
`pyproject.toml` optional group `dev` only mirrors the range; it is not a second
pin authority.
