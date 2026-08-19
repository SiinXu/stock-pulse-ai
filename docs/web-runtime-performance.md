# Web Runtime Performance Budgets

Issue [#883](https://github.com/SiinXu/stock-pulse-ai/issues/883) extends the existing bundle-size budget (PR #905 / #920 / T20) with **runtime** budgets for ten audited `apps/dsa-web` surfaces, plus the T16 shared `DataTable` virtualization contract now on `main`.

Chinese companion: [web-runtime-performance_CN.md](web-runtime-performance_CN.md).

## Design principles

- **Do not shrink measurement scope** to pass a budget (full declared input sizes stay in CI contracts).
- **Do not remove product features** to hit a number.
- **Do not encode one machine's absolute speed** as a blocking wall-clock budget.
- **Do not hide regressions with broad margins.** Raise a number only with product evidence.
- **Network and Desktop timing are never blocking.**
- Structural metrics are CI-reproducible. Wall-clock targets are manual guidance on reference hardware.

## Audited surfaces

Issue #883 named ten surfaces. T16 added the shared `DataTable` window as an eleventh measured contract; keep it.

| Surface | Scenario | Kind | Gate | Why this gate |
| --- | --- | --- | --- | --- |
| Shared DataTable | `data-table-virtualization` | structural | **blocking** | T16 windows compatible tables ≥ 24 rows; 150-row input, ≤40 mounted body rows. |
| History list | `history-list-virtualization` | structural | **blocking** | Virtual window is deterministic; 150-row input, ≤40 mounted rows. |
| Signals list | `signals-list-pagination` | structural | **blocking** | Feed page model slices to 20; mounting the remainder is a regression. |
| Screening results | `screening-results-mounted-rows` | structural | **observe** | 150-row table still mounts every candidate (row details block windowing). Honest WARN until pagination or a compatible window lands. |
| Settings forms | `settings-field-isolation` | structural | **blocking** | One field edit must not re-render siblings (0). |
| SSE chat progress | `sse-progress-batching` | structural | **blocking** | 60 events must not commit `progressSteps` once per event (≤4). |
| Chat markdown | `chat-markdown-isolation` | structural | **blocking** | Prior bubbles keep DOM identity while live progress updates. |
| Home widgets | `home-widget-slots` | structural | **blocking** | Default board keeps four independent widget slots. |
| Per-route bundle split | `bundle-route-split` | external | **skip** | Already blocked by `check-bundle-size.mjs` aggregate families (T20). Not a runtime timer. |
| Desktop idle CPU/GPU | `desktop-idle-power` | external | **skip** | Unavailable in Web jsdom CI. Manual only. |
| First contentful chrome | `first-chrome-shell` | structural | **blocking** | Shell sidebar, main, and mobile header mount before the route outlet. The ~300 ms route-switch target stays manual wall-clock. |

Skip is a first-class **unavailable** result, not a pass. A skip without `skipReason` fails closed.

## Budgets (source of truth)

Machine-readable: `apps/dsa-web/scripts/runtime-performance-budget.json`.

Shared constants: `apps/dsa-web/src/performance/runtimeBudgets.ts`.

| Scenario | Input | Metric | Budget | Direction |
| --- | --- | --- | --- | --- |
| `data-table-virtualization` | 150 DataTable rows | Mounted body-row DOM nodes | 40 | at most |
| `history-list-virtualization` | 150 history rows | Mounted row DOM nodes | 40 | at most |
| `signals-list-pagination` | 150 signals | Mounted feed cards after `PAGE_SIZE` slice | 20 | at most |
| `screening-results-mounted-rows` | 150 candidates | Mounted table body rows | 40 | at most (observe) |
| `settings-field-isolation` | 40 fields | Sibling field commits after one edit | 0 | at most |
| `sse-progress-batching` | 60 SSE progress events | `progressSteps` store commits | 4 | at most |
| `chat-markdown-isolation` | 8 completed bubbles | Prior-bubble identity losses on progress update | 0 | at most |
| `home-widget-slots` | 4 default widgets | Independent widget slots | 4 | at least |
| `first-chrome-shell` | pending outlet | Shell chrome landmarks | 3 | at least |

Wall-clock guidance (manual, never a CI hard gate):

| Area | Target |
| --- | --- |
| Primary route switch | Interactive under ~300 ms on a reference laptop (prod build) |
| Settings field edit | Does not lock the shell/nav |
| Chat Stop | Perceived response under ~100 ms; UI not frozen multi-second |

## Measurement entry points

```bash
cd apps/dsa-web
npm ci
# Contract measurements (full declared input sizes)
npx vitest run src/performance/__tests__/runtimePerformance*.test.tsx
# Checker unit tests (threshold, skip, timing/network forbidden)
npx vitest run scripts/check-runtime-performance.test.mjs
# CI-shaped run: warmup 1 + median of 3 measured runs, per-scenario gates
node scripts/check-runtime-performance.mjs --print --warmup 1 --repeat 3
# Local promotion rehearsal (observe treated as blocking; skip stays skip)
node scripts/check-runtime-performance.mjs --strict --print
```

The checker writes a temporary report via `DSA_RUNTIME_PERF_REPORT`, aggregates with **median after warmup**, and compares each scenario to its gate. `--report` loads a fixture report (used by counterexample tests) and does not spawn Vitest.

### Manual profiling notes (top heavy pages)

| Surface | How to profile | What to watch |
| --- | --- | --- |
| Shared DataTable | React Profiler on a ≥24-row compatible table | Mounted body rows stay windowed; opt-out/detail tables stay fully mounted |
| Home history rail | React Profiler + Performance panel; load 100+ history rows via infinite scroll | Mounted row count stays windowed; scroll FPS stays interactive |
| Signal Center feed | Load more than one page of signals | Only the current page of cards mounts |
| Screening results | Run a wide screen with 100+ candidates | Observe WARN until the table paginates or windows |
| Settings AI / large category | Type into one field in a dense category | Sibling fields and shell remain responsive; no full-page remount |
| Chat SSE stream | Long Agent run with many stage/tool events; click Stop mid-stream | Progress UI updates in batches; prior markdown does not rebuild; Stop aborts without multi-second freeze |
| Home dashboard | Load Home with all four widgets | Slots stay independent; one slow widget does not replace chrome |
| First chrome / route switch | Production build, Performance panel on nav | Shell + nav paint before heavy widgets; ~300 ms is manual |

## Product mitigations already in tree

- **DataTable**: fixed-estimate virtual window (`useVirtualWindow`) when row count ≥ 24, unless controlled detail rows are present or the caller passes `virtualization={false}`; default/compact row heights are 48px/36px with overscan 6. Windowed sticky headers use opaque `bg-card`. Auto-window does not measure rendered height. Variable-height hosts (Event Calendar, Screening Discovery, stock-history trend, RiskHeatmap, portfolio correlation, Portfolio positions, Token Usage, import failed rows, Personal Performance, Event Alerts, and other wrapping or stacked tables) stay on the full table path.
- **HistoryList**: fixed-estimate virtual window (`useVirtualWindow`) when item count ≥ 24; `HistoryListItem` memoized.
- **Signals feed**: `mergeWatchlistSignalResponses` / `PAGE_SIZE` 20 hard-paginates the list model.
- **SettingsField**: `React.memo` with prop equality so unchanged sibling fields skip re-render.
- **SSE**: `agentChatStore` batches `progressSteps` commits with `requestAnimationFrame`; `ChatMessageBubble` memoized so stream progress does not re-parse every prior bubble.
- **Home**: `HomeDashboardLayout` keeps four independent widget slots.
- **Shell**: sidebar, main, and mobile header mount independently of the route outlet.

## Flake policy

- **Blocking structural**: zero flakes. Median of `measuredRuns` after `warmupRuns` must stay within budget. Do not raise the budget to swallow variance.
- **Observe**: WARN only. Promote to blocking only after repeated CI medians are stable at the declared input size.
- **Skip / unavailable**: printed as `[SKIP]` with `skipReason`. Missing `skipReason` fails closed. Missing measurements for blocking or observe fail closed so coverage cannot be dropped to go green.
- **Timing / network**: `kind=timing` and `kind=network` cannot use `gate=blocking`. The checker rejects that schema.
- **Retries**: CI does not retry this step. Re-run locally with the same `--warmup` / `--repeat` flags.

## Diagnostics

`node scripts/check-runtime-performance.mjs --print` prints per scenario: status, measured vs budget, gate, metric, and the measured sample list after warmup. Hosted `web-gate` keeps this log on the **Runtime performance budgets** step.

## Baseline-update procedure

1. Keep the declared input size (150 / 40 / 60 / 8 / 4). Do not shrink the fixture.
2. Prefer fixing the product or the fixture over raising the number.
3. To change a structural budget: record `--print` output, explain the product reason, update `runtimeBudgets.ts` and the JSON together, add a changelog fragment.
4. To promote observe → blocking: three local measured medians plus one hosted `web-gate` log, all within budget, without needing a wider cap.
5. Do not convert skip (Desktop, gzip) into a runtime blocking timer.

## Rollback

Revert the PR (or restore the previous three-scenario JSON and the soft-only CI step). Bundle-size aggregate families are independent.

## Soft override vs CI

`--soft` demotes blocking exceedances to WARN for local emergency comparison. CI must not pass `--soft`. `--strict` promotes observe to blocking for promotion rehearsal; skip stays skip.

The Web gate runs `node scripts/check-runtime-performance.mjs --print --warmup 1 --repeat 3` after unit tests when frontend paths change. Blocking exceedances fail the required Web gate. Observe exceedances warn. Skip prints unavailable.

## Bundle size (per-asset and aggregate)

Machine-readable: `apps/dsa-web/scripts/bundle-size-budget.json`.

Checker: `apps/dsa-web/scripts/check-bundle-size.mjs` (`npm run build:check` after a production build).

| Layer | What it caps | Bypass it prevents |
| --- | --- | --- |
| `rules` | Each matching `.js` / `.css` asset | A single named chunk growing past its gzip cap |
| `aggregateRules` | Unique gzip total of every asset matching a family of globs | Splitting one route or component into many smaller chunks that each stay under the per-asset cap |

Aggregate rules are keyed by stable family IDs (`<named-rule>-family` or a route prefix such as `home-watchlist-route`). `match` is one glob or a list of globs. Each asset is counted once inside a family even when several globs hit the same hashed filename. A family that matches nothing fails, so a renamed prefix cannot silently drop out of the gate.

`vendor-misc` stays a first-match residual per-asset rule only. Its glob `assets/vendor-*.js` would otherwise sum every vendor chunk.

Same-pattern families inherit the existing named per-asset cap when the current production build still emits one artifact. Locale packs on current `main` already emit several `ja-*.js` (and sibling locale) files; those families use the measured zlib-9 sum plus 400 B. Extra route families (`settings-route`, `portfolio-route`, `screening-route`, `home-watchlist-route`, `backtest-route`) cover prefix children that would not match the original named glob. Do not raise a per-asset cap to hide family growth.

```bash
cd apps/dsa-web
npm run build
node scripts/check-bundle-size.mjs --print
```

The checker prints matched assets, per-file gzip, family gzip totals, and the budget that failed.

## Related

- Bundle size budget: `apps/dsa-web/scripts/bundle-size-budget.json`, `check-bundle-size.mjs`
- Issue #883 acceptance criteria and phases
