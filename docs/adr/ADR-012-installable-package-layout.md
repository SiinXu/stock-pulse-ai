# ADR-012: Installable Package Layout Without Import Rewrites

- Status: `Accepted`
- Decision date: 2026-08-17
- Decision owners: maintainers of the packaged-layout migration (issue #167)
- References: [Issue #167](https://github.com/SiinXu/stock-pulse-ai/issues/167),
  [ADR-006](ADR-006-behavior-preserving-module-decomposition.md),
  [ADR-010](ADR-010-import-cycle-ratchet.md),
  `pyproject.toml` `[tool.setuptools.packages.find]`,
  `scripts/ci_gate.sh`, `docker/Dockerfile`,
  `scripts/build-backend-macos.sh`, `scripts/build-backend.ps1`

## Context

Everything in this repository imports through four top-level names that live on
repo-root `sys.path`: `src`, `api`, `bot`, and `data_provider`. Callers, tests,
PyInstaller hidden-import lists, Docker `COPY` fan-out, and CI `py_compile`
lists all encode that layout. `pyproject.toml` previously recorded a deliberate
non-installable decision:

```toml
# Application repository: metadata and optional dependency groups only.
# Runtime code is imported from the source tree, not as an installed library.
[tool.setuptools]
packages = []
```

That comment was accurate for an application repo that never expected
`pip install`. It is now the blocker for proving installability *before* any
file moves. An editable install that exposes those four exact package names is
purely additive: **zero import statements change**. That is the point of this
stage.

Verified at `origin/main` `faa33106a` (2026-08-17):

| Coupling (module-level `from`/`import` lines) | Count |
| --- | ---: |
| `api` → `src` | 288 |
| `src` → `data_provider` | 104 |
| `data_provider` → `src` | 69 |

Of the `data_provider` → `src` edges, the layer-direction ratchet records
**three** file-level exceptions, all `data_provider` → `src.services`:

- `data_provider/futu_position_fetcher.py`
- `data_provider/symbol_normalization.py`
- `data_provider/yfinance_fetcher.py`

Repo-wide `hard_ceiling` is 12 (`scripts/layer_direction_baseline.json`).
Those three files are inventory, not permission to grow.

Other artifacts that still encode the four-root layout and must keep working
without a rewrite in this stage:

- PyInstaller `--hidden-import` lists in `scripts/build-backend-macos.sh` and
  `scripts/build-backend.ps1` (`api`, `src.services`, `src.migrations`, …)
- Docker `COPY api/`, `COPY data_provider/`, `COPY bot/`, `COPY src/`
- `scripts/ci_gate.sh` `py_compile` lists (`src/…`, `data_provider/*.py`)

This ADR **reverses** the `packages = []` decision. It does not rename `src`,
does not introduce a `stockpulse` import root, and does not authorize a
single-epoch rewrite of imports or checker classifiers.

## Decision

1. `src` is the long-term single installed package. During the transition the
   distribution installs **four** packages whose names match the existing
   import roots: `src`, `api`, `bot`, `data_provider`. Discovery is:

   ```toml
   [tool.setuptools.packages.find]
   include = ["src*", "api*", "bot*", "data_provider*"]
   ```

2. **All** environments that need the application importable as installed
   packages run `python -m pip install -e . --no-deps` **after** the existing
   constrained requirements path. `--no-deps` is mandatory. Pin authority
   **remains** `constraints.txt` (plus `build-constraints.txt` for builds).
   `check_dependency_locks` and `check_install_guidance` must never see an
   unconstrained resolve.

3. Distribution name `stock-pulse-ai` versus import name `src` is an accepted
   trade-off. Renaming the import root is **out of scope**.

4. Day-to-day dependency flow stays `requirements.txt` + `constraints.txt`.
   `pyproject.toml` extras continue to **mirror names only**; they are not a
   second pin authority.

### PYTHONPATH single-track policy

- Repo-root cwd execution stays supported. `main.py`, `server.py`, and
  `pytest` keep working without a new `PYTHONPATH` injection.
- The editable install points at the same source tree (`-e .`). There is no
  double-copy of application code into `site-packages`.
- CI adds **no** new `PYTHONPATH` injection. The installable flip is the
  additional track; cwd/`sys.path` remains the existing one.
- Local `scripts/ci_gate.sh` and hosted CI stay aligned by running the same
  `--no-deps` editable install inside the gate.

## Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| `src/stockpulse` src-layout (`import stockpulse`) | Forces a single-epoch rewrite of every import, every import-layer / layer-direction / facade / hot-path / config-access baseline, every checker classifier, and every PyInstaller hidden-import. Contradicts ADR-006's staged, behavior-preserving method. |
| Flat `stockpulse/` at repo root | Same rewrite cost, plus a colliding top-level name and a Docker/`COPY` reshuffle in the same epoch. |

Both alternatives can be revisited only as a later, separately accepted ADR
after the four-package installable layout is proven in CI, Docker, and desktop
packaging.

## Consequences

- `pip install -e . --no-deps` makes `import src`, `import api`, `import bot`,
  and `import data_provider` work from a different cwd. That is the
  installability proof this stage exists to land.
- No production import statement changes in this stage. Guard baselines are
  expected to be unchanged.
- Docker must copy `pyproject.toml` (and the PEP 621 `readme` / `license`
  files it references) and run the `--no-deps` editable install after the
  existing source `COPY` block.
- Desktop backend builds run the same editable install before PyInstaller so
  hidden-imports resolve through the installed package names rather than
  cwd-only `sys.path`.
- Rollback is a single revert of the PR: `packages = []` returns and the
  install commands disappear. No data or configuration migration.

## Migration reference

Issue #167 staged packaged-layout work. This record is the keystone
**installable flip**. Later stages may collapse the four packages to `src`
alone; they must not rewrite imports in the same slice that changes package
discovery. ADR-006 still governs any later physical file moves: inventory
callers first, keep facades if needed, and do not combine a move with a
behavior change.
