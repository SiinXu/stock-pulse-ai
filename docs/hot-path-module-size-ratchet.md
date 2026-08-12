# Hot-Path Module Size Ratchet

- Status: `Living`
- Last verified: 2026-08-12
- Related: [architecture overview](architecture-overview.md),
  [layer-direction ratchet](layer-direction-ratchet.md),
  `scripts/check_hot_path_module_size.py`,
  `scripts/hot_path_module_size_baseline.json`,
  issue [#1087](https://github.com/SiinXu/stock-pulse-ai/issues/1087)

## Purpose

Splitting gravity modules fails long-term if new features immediately re-inflate
the same hot-path files. This ratchet freezes the current oversized inventory
and fails CI when debt grows.

## Scopes

| Path | Role on the hot path |
| --- | --- |
| `data_provider/` | Market adapters, fallback, cache |
| `src/services/` | Application use cases and task lifecycle |
| `src/agent/` | Agent orchestration and tools |
| `src/market/` | Market analysis / phase / structure |

Only production `*.py` files under these roots are measured. Tests and docs are
out of scope.

## Thresholds (with rationale)

| Threshold | Value | Role |
| --- | --- | --- |
| Soft budget | **1500** physical lines | New hot-path files must stay at or under this limit. Existing files above it require a baseline entry. |
| Extraction preference | **2000** lines | Documented cleanup priority (issue #1087); prefer split/extract first for files above this band. Not a second independent fail threshold. |
| `hard_ceiling_count` | Introduction inventory size | Never raise — pins how many oversized hot-path files may exist. |
| `hard_ceiling_max_lines` | Largest file at introduction | Never raise — pins the worst single-file size. |

**Why 1500:** issue #1087 encourages review when a hot-path file exceeds
~1200–1500 lines. Using the upper end of that band avoids allowlisting every
mid-size service while still catching re-growth after splits.

**Why 2000:** issue #1087 strongly prefers extraction above ~2000 lines on the
primary analyze path. The cleanup plan prioritizes those modules first.

Line counts are physical lines (`wc -l` style), including blanks and comments,
for a deterministic, encoding-stable measurement.

## Existing debt (introduction inventory)

Historical oversized modules live in
`scripts/hot_path_module_size_baseline.json` as `path → max_lines`. At
introduction the inventory included gravity modules such as:

- `data_provider/base.py`
- `data_provider/akshare_fetcher.py`
- `src/services/task_queue.py`
- `src/services/run_diagnostics.py`
- `src/services/portfolio_service.py`
- `src/services/scheduled_task_service.py`
- `src/market/analyzer.py`

plus other services modules between 1500 and 2000 lines.

### Cleanup plan

1. Prefer extracting cohesive helpers or packages when a baselined file exceeds
   the extraction preference (2000), starting with the largest providers and
   services modules.
2. After a successful split that reduces a path under the soft budget, run
   `--write-baseline` to drop the path or lower its line cap.
3. **Never raise** `soft_budget_lines`, `hard_ceiling_count`, or
   `hard_ceiling_max_lines` to green CI.

## How to read a failure

```text
[hot-path-size] ERROR: new-oversized-module: src/services/foo.py: 1600 lines exceeds soft budget 1500; ...
[hot-path-size] ERROR: module-grew: data_provider/base.py: 4800 lines exceeds baselined max 4733; ...
```

Typical fixes:

1. Extract a helper package or module and re-export stable import surfaces if
   needed (mechanical move only).
2. Stop adding large new blocks to already-oversized files; place new code in a
   focused module under the same package.

## Commands

```bash
python scripts/check_hot_path_module_size.py --self-test
python scripts/check_hot_path_module_size.py
python scripts/check_hot_path_module_size.py --write-baseline
```

Wired into `./scripts/ci_gate.sh` deterministic checks (self-test then live
check).

## Legitimate change path

| Change | Action |
| --- | --- |
| **Shrink** (split under budget or reduce lines) | Merge the split, then run `--write-baseline`. Always allowed. |
| **Growth** (new oversized file or regrowth) | **Not** allowed via `--write-baseline`. Split the module. Do not raise path budgets or hard ceilings. |
| Accidental growth | Fix the code; do not edit the baseline. |
