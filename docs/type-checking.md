# Python Type Checking (mypy ratchet)

- Status: `Living`
- Last verified: 2026-08-05
- Related: [Contributing Guide (EN)](CONTRIBUTING_EN.md), `mypy.ini`, `scripts/ci_gate.sh`

## Scope (current)

Type checking is **not** repo-wide.

| Item | Value |
| --- | --- |
| Tool | `mypy` (version pinned via `constraints.txt` / `.github/requirements-ci.txt`) |
| Config | [`mypy.ini`](../mypy.ini) |
| Checked paths | `src/schemas/` (18 modules) and `api/v1/schemas/` (23 modules, ~250 pydantic models) |
| Import policy | `follow_imports = skip` so the rest of the tree is not pulled into the check |
| CI entry | `./scripts/ci_gate.sh` → `deterministic_checks` runs `python -m mypy --config-file mypy.ini` |

The rest of the Python tree remains untyped at the gate. flake8 still only
enforces syntax-level selectors (`E9,F63,F7,F82`).

### Why `follow_imports = skip` stays

Both schema packages already pass cleanly with `follow_imports=skip`. Enabling
`follow_imports=normal` for the combined checked set was measured on 2026-08-05:

| Setting | Result |
| --- | --- |
| `follow_imports=skip` | Success (41 source files) |
| `follow_imports=normal` | **2745 errors in 261 files** (transitive surface through `src/config_parts`, `data_provider`, `src/core`, repositories, endpoints, etc.) |

Keep skip until a later decision deliberately widens import following after those
downstream packages join the ratchet.

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

If a change under a checked package introduces a new mypy error, fix the
annotation or typing issue in that package. Do not widen the checked surface to
silence the error, and do not disable the gate.

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

## Next-package order

Suggested order after the current clean set. Costs are approximate offline
measurements with `--follow-imports=skip` (error counts change as code moves):

| Priority | Package | Approx. size / skip-cost | Notes |
| --- | --- | --- | --- |
| Done | `src/schemas/` | 18 modules, clean | First ratchet package |
| Done | `api/v1/schemas/` | 23 modules, ~250 models, clean | This expansion; pure API data shapes |
| Next | `api/v1/errors.py` | 1 file, 0 errors | Leaf error helpers adjacent to schemas |
| Next | `api/middlewares/` | 4 modules, ~1 error | Small auth/error middleware surface |
| Next | `src/repositories/` | 18 modules, ~1 error | Data access; mostly typed shapes already |
| Later | `api/deps.py` | 1 file, ~13 errors | FastAPI dependencies; more runtime coupling |
| Later | `bot/` | 24 modules, ~25 errors | Notification bots; medium fix cost |
| Later | `api/v1/endpoints/` | 23 modules, low skip-errors but high coupling | Prefer after schemas/deps stabilize; analysis endpoints may be owned by a separate workstream |
| Later | `src/services/` | large (~89 modules) | High coupling; split by subdomain when ratcheting |
| Deferred | Drop `follow_imports=skip` | 2745+ transitive errors today | Only after large portions of `src/` and `data_provider/` are clean |

When claiming the next package, re-measure with the commands above before editing
`mypy.ini`. Prefer pure data / leaf modules over orchestration and provider code.

## Exclusions

No modules under the current checked packages are excluded. If an exclusion is
required later, list it here and in `mypy.ini` with a named comment.

## Pin authority

mypy is installed from `.github/requirements-ci.txt` and locked by
`constraints.txt` through `scripts/check_dependency_locks.py`.
`pyproject.toml` optional group `dev` only mirrors the range; it is not a second
pin authority.
