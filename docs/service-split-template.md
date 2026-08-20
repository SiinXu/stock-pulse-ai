# Service-Split Template

- Status: `Living`
- Last verified: 2026-08-20
- Related: [ADR-006](adr/ADR-006-behavior-preserving-module-decomposition.md),
  [hot-path module size ratchet](hot-path-module-size-ratchet.md),
  [import-cycle ratchet](import-cycle-ratchet.md),
  [layer-direction ratchet](layer-direction-ratchet.md),
  [legacy facade import policy](legacy-facade-import-policy.md),
  [data provider ownership map](data-provider-ownership.md),
  issue [#1088](https://github.com/SiinXu/stock-pulse-ai/issues/1088)
- Runnable code and CI guards remain authoritative when this document drifts.

## Purpose

This is the repo-local checklist for **behavior-preserving** splits of gravity
modules under `src/services/`, `src/data_provider/`, `src/market/`,
`src/plugins/`, and similar hot-path packages.

[ADR-006](adr/ADR-006-behavior-preserving-module-decomposition.md) is the
architectural decision (staged extraction behind a compatibility facade). This
template is the operational contract for a split PR. It is not a new ADR.

A split PR that cannot tick every blocking item below is not an end-to-end
compliant split. Partial historical splits stay useful evidence; they do not
close this template.

## When To Use

Use this template when the PR:

- extracts a cohesive subdomain out of an oversized module, **and**
- intends no user-visible behavior, API, serialization, fallback, or analysis
  outcome change in the same PR.

Do **not** mix a mechanical split with a feature, bugfix, schema redesign, or
policy change. Those belong in a later, separately reviewed PR.

Intended consumers (open as of 2026-08-20; this template does not close them):

| Issue | Target |
| --- | --- |
| [#1067](https://github.com/SiinXu/stock-pulse-ai/issues/1067) | `src/data_provider/base.py` manager / health / routing / cache |
| [#1068](https://github.com/SiinXu/stock-pulse-ai/issues/1068) | oversized fetchers (client / parse / orchestrate) |
| [#1073](https://github.com/SiinXu/stock-pulse-ai/issues/1073) | `src/services/task_queue` api / store / worker / recovery |
| [#1074](https://github.com/SiinXu/stock-pulse-ai/issues/1074) | `src/services/portfolio_service` positions / transactions / risk |
| [#1075](https://github.com/SiinXu/stock-pulse-ai/issues/1075) | scheduler → queue/pipeline facade only |
| [#1076](https://github.com/SiinXu/stock-pulse-ai/issues/1076) | run diagnostics collect / schema / export |
| [#1080](https://github.com/SiinXu/stock-pulse-ai/issues/1080) | `src/plugins/manager.py` loader / permissions / lifecycle |
| [#1085](https://github.com/SiinXu/stock-pulse-ai/issues/1085) | `src/market/analyzer.py` metrics / prompts / degradation |
| [#1086](https://github.com/SiinXu/stock-pulse-ai/issues/1086) | remaining oversized services (`run_flow`, scheduler leftovers) |

Several of those issues already have layout-only splits on `main`. Remaining
issue acceptance is independent of this template slice.

## Blocking Checklist

Copy this table into the split PR. Every row is blocking unless the PR records
an explicit, evidenced exception.

| # | Rule | Pass when |
| --- | --- | --- |
| 1 | **Stable facade and public names** | The pre-split import path remains the only production import. `__all__` (or an equivalent frozen name list in tests) matches the previous public names. No production caller is migrated onto internal modules in the same PR. |
| 2 | **Internal module ownership** | Each extracted file has one named responsibility. The internal package `__init__.py` does not become a second public API. New production code is added under the owner module, not the facade body. |
| 3 | **Compatibility re-exports** | Public callables keep observed `__module__`, patch targets, and object identity required by existing tests. Re-exports are explicit; star-imports of internals are not a public contract. |
| 4 | **Import direction and cycles** | `python scripts/check_import_layers.py` and `python scripts/check_layer_direction.py` pass. The split does not add a new bidirectional package pair or a reverse layer edge. Same-package internals import one-way (types/leaf → collect → export); lazy imports are a last resort and must be named in the PR. |
| 5 | **Test migration and characterization** | Existing tests still import the **facade**. New characterization covers public names, `__module__` / patch seams, and the split invariant. Focused tests for extracted pure helpers live next to the new modules (`tests/<area>/...`). Tests are not rewritten to depend only on internal paths. |
| 6 | **Serialization and API compatibility** | Snapshot keys, `to_dict()` / JSON omit-`None` rules, HTTP DTO fields, and analysis outcome dicts remain equal to the pre-split contract. Add a mutation counterexample when the split touches collect/export. |
| 7 | **Module-size ratchet** | After the split, run `python scripts/check_hot_path_module_size.py`. If a path dropped under the 1500-line soft budget, run `--write-baseline` in the **same** PR so the old allowance cannot grow back. Never raise `soft_budget_lines`, `hard_ceiling_count`, or `hard_ceiling_max_lines`. New extracted files must stay ≤ 1500 lines. |
| 8 | **No behavior change in the split PR** | Diff is mechanical move + re-export + tests/docs/ratchet. Fail-open wrappers, fallback, redaction, and analysis outcomes keep the same branches and observed contracts (same exception fingerprints unless regenerated by the repository tooling). |
| 9 | **Docs and changelog** | Topic doc records the new layout and “import the facade, not internals.” Add a unique `docs/changelog.d/<slug>.md` line. Do not expand `README.md`. Use `Refs #<issue>`; `Fixes`/`Closes` only when that issue’s acceptance is fully met. |
| 10 | **Verification matrix** | Run the commands in [Verification](#verification). Paste actual results on the current head. |
| 11 | **Rollback** | Revert the PR. No config, database, or API migration. |
| 12 | **Shim removal criteria** | The PR states what is a **stable public facade** versus a **temporary re-export**. Temporary names may be deleted only under [Removing compatibility shims](#removing-compatibility-shims). |

## Layout Pattern

Keep the original module (or package `__init__.py`) as the caller-facing facade:

```text
src/<package>/<facade>.py          # stable public names; thin re-exports over time
src/<package>/<subdomain>/
  __init__.py                      # empty or package marker; not a second public API
  <owner_a>.py                     # one responsibility
  <owner_b>.py
```

Examples already on `main` (layout only; not template-compliance claims):

- `src.services.run_diagnostics` → `src/services/diagnostics/{schema,collect,export}.py`
- `src.services.task_queue` → `models` / `store` / `worker` / `recovery` / `api`
- `src.plugins.manager` → `loader` / `permissions` / `lifecycle` / `manager_types`

Inventory before moving code: production imports, test patch targets, reload
seams, reflection (`__module__`, method order), serialization keys, and
broad-exception fingerprints.

## Removing Compatibility Shims

Distinguish two surfaces:

| Surface | Example | Default |
| --- | --- | --- |
| **Stable public facade** | `src.services.run_diagnostics`, `src.services.task_queue`, `src.plugins.manager` | Keep. This **is** the public API. |
| **Temporary re-export** | A name re-exported only so an old patch target or unused alias keeps working | Removable after the criteria below. |
| **ADR-006 legacy top-level shim** | Catalogued in [legacy facade import policy](legacy-facade-import-policy.md) | Shrink-only via `scripts/check_legacy_facade_imports.py`; never grow. |

Delete a temporary re-export only in a **follow-up** PR, and only when all of
these hold:

1. Production, tests, scripts, samples, and packaging no longer import that name
   from the shim path (`rg` over those trees; file existence is not enough).
2. Characterization tests for that name are updated or removed in the same PR.
3. If the path is a catalogued ADR-006 facade, the legacy-facade baseline
   shrinks with `--write-baseline` after the code change.
4. Hot-path size, import-layer, and layer-direction checks still pass.
5. No HTTP/serialization/behavior change is mixed in.

Do not delete a stable public facade merely because internals exist. Migrating
callers onto `src.services.<internal>` is a separate contract change.

## Verification

Minimum on every split PR (replace paths with the modules you touched):

```bash
python -m py_compile src/<package>/<facade>.py src/<package>/<subdomain>/*.py

python -m pytest -m "not network" tests/<facade-or-area-tests> -q

python scripts/check_hot_path_module_size.py
python scripts/check_import_layers.py
python scripts/check_layer_direction.py
python scripts/check_broad_exceptions.py
python scripts/collect_changelog.py --check
```

When the split touches catalogued ADR-006 shims:

```bash
python scripts/check_legacy_facade_imports.py
```

When CI mapping or the change surface is broader than the focused tests, run
`./scripts/ci_gate.sh` or record the exact subset and the hosted `backend-gate`
result. Do not claim full-suite green from an unrun command.

## Worked Audit: Merged PR #1352

Source of truth: merged PR
[#1352](https://github.com/SiinXu/stock-pulse-ai/pull/1352)
(`2469e7bc8`, head `6d767cbb3`, first-parent diff vs `45bb655ee`, 10 files,
`+2488 / -2026`), issue [#1076](https://github.com/SiinXu/stock-pulse-ai/issues/1076).

This template did **not** exist when #1352 merged. The table is a historical
audit against the checklist above. It is **not** proof that #1352 followed this
template end-to-end, and it does **not** close #1088.

| Checklist item | Result | Evidence / deviation |
| --- | --- | --- |
| 1. Stable facade | **Pass** | Production still imports `src.services.run_diagnostics` only. Facade `__all__` lists the public names. |
| 2. Internal ownership | **Deviation** | `schema.py` / `collect.py` / `export.py` exist, but the facade is still 647 lines and owns `RunDiagnosticContext` methods. `diagnostics/__init__.py` is a package marker (good), yet ownership is not a thin facade. |
| 3. Compatibility re-exports | **Pass** | Characterization asserts facade-bound callables keep `__module__ == "src.services.run_diagnostics"`. |
| 4. Import direction / cycles | **Deviation** | Package-level import/layer checks were reported green on the PR. Same-package `schema.py` still lazy-imports `export.format_copyable_diagnostics` for `copy_text` (internal back-edge, named here rather than treated as a passed cycle rule). |
| 5. Test migration | **Deviation** | Tests stayed at `tests/test_run_diagnostics_p1.py` and `tests/test_run_diagnostics_p2.py`. Characterization was **added in place**; tests were not moved next to `src/services/diagnostics/`. `PUBLIC_NAMES` is a subset of facade `__all__` (record dataclasses and summary types are omitted). |
| 6. Serialization / API | **Pass** | Snapshot keys, `ProviderRun.to_dict()` None-omission, and collect/export non-mutation of inputs/outcomes are tested. |
| 7. Module-size ratchet | **Pass** | `run_diagnostics.py` dropped off `scripts/hot_path_module_size_baseline.json`; extracted files are under 1500 lines (`collect.py` 1048, `export.py` 573, `schema.py` 472). |
| 8. No mixed behavior change | **Pass** (as declared) | PR scoped to mechanical split + characterization + ratchet shrink; used `Refs #1076`. |
| 9. Docs / changelog | **Pass** | `docs/run-diagnostics-p1.md` layout note and `docs/changelog.d/1076-run-diagnostics-split.md`. |
| 10. Verification | **Pass** (as recorded on the PR) | Focused diagnostics tests plus `./scripts/ci_gate.sh` were reported on that head. |
| 11. Rollback | **Pass** | Revert the PR; no migration. |
| 12. Shim removal criteria | **Deviation** | The PR told consumers not to import internals, but did not state when temporary re-exports may die or that the facade remains the public API until a separate contract PR. |

**Audit verdict:** #1352 is a useful historical split with documented deviations.
It does **not** satisfy #1088 “at least one split PR follows this template
end-to-end.” Issue #1076 remains open.

### Not accepted evidence

Open draft
[PR #1402](https://github.com/SiinXu/stock-pulse-ai/pull/1402)
(`refactor: freeze run diagnostics schema boundary`) is an **unverified
candidate** on the #1352 layout. Do not cite it as accepted evidence that #1076
or #1088 is closed.

## Issue Closing Rule

| Acceptance item from #1088 | This docs slice |
| --- | --- |
| Template documented in-repo | Met by this file plus index links |
| At least one split PR follows it end-to-end | **Not met** — #1352 has deviations; no later split is accepted evidence here |
| Checklist covers facade, re-exports, tests, no drive-by behavior changes | Met by the blocking table |

Keep [#1088](https://github.com/SiinXu/stock-pulse-ai/issues/1088) **open**. PRs
that only add or refine this template use `Refs #1088`, never `Fixes`/`Closes`.
