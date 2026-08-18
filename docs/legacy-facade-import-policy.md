# Legacy Facade Import Policy

- Status: `Living`
- Last verified: 2026-08-17
- Related: [ADR-006](adr/ADR-006-behavior-preserving-module-decomposition.md), [ADR-012](adr/ADR-012-installable-package-layout.md), Issue #623, Issue #167

## Purpose

ADR-006 intentionally kept top-level compatibility facades so oversized modules
could be split without breaking imports, patches, or reflection. New production
code must not deepen that dual path.

The guard now catalogues only ADR-006 module facades (for example
`src/market_sector_analysis.py`) left behind by behavior-preserving module
decomposition. The ADR-012 root import packages (`api`, `bot`, and
`data_provider`) have been retired after all production, test, script,
packaging, and workflow references moved to `src.*`.

This document records:

1. The current inventory of production importers of known legacy facades.
2. The canonical import path for each facade.
3. The contributor rule and CI enforcement for **new** production imports.
4. A phased retirement plan (no big-bang delete).

## Contributor Rule

| Context | Rule |
| --- | --- |
| New production code under `src/` or entrypoints `main.py` / `server.py` | Import the **canonical package** only (`src.api`, `src.bot`, `src.data_provider`, `src.market.sector_analysis`). |
| Retired root import packages | Do not recreate `api`, `bot`, or `data_provider`; use the canonical `src.*` packages. |
| Samples, examples, and repository scripts | Use canonical `src.*` imports. Published plugin and authoring samples are what out-of-tree authors copy, so they must not teach the shim paths. |
| Existing allowlisted production importers | May keep the facade path until a dedicated migration PR shrinks the baseline. |
| Tests | May import a still-catalogued facade when patch targets or reload contracts require it. Use canonical `src.*` paths otherwise. |
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
| `src.market_sector_analysis` | `src.market.sector_analysis` | 1 | `src/market_sector_analysis.py` |

**Total allowlisted production importer rows: 1.** The removed root packages
are unknown facade keys; adding them to the baseline fails validation.

The root-level analysis-context-pack shims
(`src/analysis_context_pack_overview.py`, `src/analysis_context_pack_prompt.py`)
have been removed. Production and test imports use
`src.analysis_context_pack.overview` and `src.analysis_context_pack.prompt`.
Leftover baseline keys for those facades fail as unknown facades.

The root-level market shims (`src/market_analyzer.py`, `src/market_context.py`,
`src/market_phase_prompt.py`, `src/market_phase_summary.py`,
`src/market_regime_prompt.py`, `src/market_structure_prompt.py`) have been
removed. Production and test imports use `src.market.*` only. The legacy
facade guard no longer catalogues those paths; leftover baseline keys fail as
unknown facades.

The `src/notification_sender/` re-export shims have been removed. Production
and test imports use `src.notification_parts.senders` only. The legacy facade
guard no longer catalogues those paths; leftover baseline keys fail as
unknown facades.

The root `api/`, `bot/`, and `data_provider/` compatibility packages have also
been removed. Production, tests, scripts, workflows, Docker, and package
discovery use `src.api`, `src.bot`, and `src.data_provider` only.

## Phased Retirement

| Phase | Goal | Success criteria |
| --- | --- | --- |
| **0 — Ban growth (this document)** | Stop new production facade imports | Guard green in CI; inventory published; baseline does not expand without review |
| **1 — Import migration** | Migrate every importer to its canonical package | Baseline shrinks and focused offline tests pass |
| **2 — Facade thinning** | Reduce a shim to documented patch targets only | Separate PR; state intentional contract change; patch/reload tests stay green |
| **3 — Removal** | Delete an unused facade when no importer or required patch target remains | Explicit compatibility evidence completed |

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
- [ADR-012](adr/ADR-012-installable-package-layout.md) — packaged layout; `src` is the long-term single installed package
- Issue #623 (import ban), Issue #622 (`data_provider.base` decomposition)
