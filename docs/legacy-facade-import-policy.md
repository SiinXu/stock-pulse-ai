# Legacy Facade Import Policy

- Status: `Living`
- Last verified: 2026-07-26
- Related: [ADR-006](adr/ADR-006-behavior-preserving-module-decomposition.md), Issue #623

## Purpose

ADR-006 intentionally kept top-level compatibility facades so oversized modules
could be split without breaking imports, patches, or reflection. New production
code must not deepen that dual path.

This document records:

1. The current inventory of production importers of known legacy facades.
2. The canonical import path for each facade.
3. The contributor rule and CI enforcement for **new** production imports.
4. A phased retirement plan (no big-bang delete).

## Contributor Rule

| Context | Rule |
| --- | --- |
| New production code under `src/`, `data_provider/`, `api/`, `bot/`, or entrypoints `main.py` / `server.py` / `webui.py` | Import the **canonical package** only. |
| Existing allowlisted production importers | May keep the facade path until a dedicated migration PR shrinks the baseline. |
| Tests | May import facades when patch targets, reload, or historical contracts require them. Prefer canonical paths for new tests when possible. |
| Facade shim modules themselves | Remain the re-export surface; do not expand their public contract without a separate decision. |

Enforcement:

```bash
python scripts/check_legacy_facade_imports.py --self-test
python scripts/check_legacy_facade_imports.py
```

The guard is wired into `./scripts/ci_gate.sh` deterministic checks. Expanding
the allowlist requires an explicit baseline update with a retirement note in the
PR; shrinking is the expected direction of travel.

To regenerate the allowlist after deliberate migrations:

```bash
python scripts/check_legacy_facade_imports.py --write-baseline
```

## Inventory (production importers)

Counts and paths are frozen in
[`scripts/legacy_facade_import_baseline.json`](../scripts/legacy_facade_import_baseline.json).
Summary at the time this policy was introduced:

| Legacy facade | Canonical module | Production importers | Facade definition |
| --- | --- | --- | --- |
| `src.market_context` | `src.market.context` | 6 | `src/market_context.py` |
| `src.market_phase_prompt` | `src.market.phase_prompt` | 4 | `src/market_phase_prompt.py` |
| `src.market_phase_summary` | `src.market.phase_summary` | 18 | `src/market_phase_summary.py` |
| `src.market_structure_prompt` | `src.market.structure_prompt` | 5 | `src/market_structure_prompt.py` |
| `src.market_sector_analysis` | `src.market.sector_analysis` | 1 | `src/market_sector_analysis.py` |
| `src.market_analyzer` | `src.market.analyzer` | 2 | `src/market_analyzer.py` |
| `src.analysis_context_pack_overview` | `src.analysis_context_pack.overview` | 7 | `src/analysis_context_pack_overview.py` |
| `src.analysis_context_pack_prompt` | `src.analysis_context_pack.prompt` | 3 | `src/analysis_context_pack_prompt.py` |

**Total allowlisted production importer rows: 46** (one file may appear under
multiple facades).

`data_provider.base` is **not** listed as a banned legacy facade in this guard.
It is the active compatibility surface for the data-provider decomposition
tracked by Issue #622 / ADR-006; its extraction uses re-exports, not a second
parallel public import tree. New call sites should continue to use the public
`data_provider` / `data_provider.base` contracts until a later retirement PR says
otherwise.

## Phased Retirement

| Phase | Goal | Success criteria |
| --- | --- | --- |
| **0 — Ban growth (this document)** | Stop new production facade imports | Guard green in CI; inventory published; baseline does not expand without review |
| **1 — Leaf services** | Migrate low-risk service and bot importers to canonical packages | Baseline rows for those files removed via `--write-baseline`; offline tests for the migrated modules green |
| **2 — Pipeline / analyzer / agent** | Migrate high-churn orchestration importers | Same as Phase 1 for `src/core/**`, `src/analyzer.py`, `src/agent/**` |
| **3 — API surfaces** | Migrate HTTP endpoints that still bind facades | Same as Phase 1 for `api/**` |
| **4 — Facade thinning** | Reduce shim surface to documented patch targets only | Separate PR; state intentional contract change; patch/reload tests still green |
| **5 — Optional removal** | Delete unused facades only when no baseline importers and no required patch targets remain | Explicit PR; ADR-006 compatibility evidence completed |

Each phase is one or more review-sized PRs. Deleting facades is never combined
with behavior changes.

## Out Of Scope

- Deleting all facades in one PR
- Changing market-analysis runtime behavior
- Provider priority / circuit / fallback policy (ADR-005)
- Pipeline mixin rebind cleanup (linked follow-up if needed)

## Related

- [Architecture overview](architecture-overview.md) — directory ownership and facade notes
- [ADR-006](adr/ADR-006-behavior-preserving-module-decomposition.md)
- Issue #623 (import ban), Issue #622 (`data_provider.base` decomposition)
