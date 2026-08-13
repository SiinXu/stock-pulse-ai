# Web Runtime Performance Budgets

Issue [#883](https://github.com/SiinXu/stock-pulse-ai/issues/883) extends the existing bundle-size budget (PR #905 / #920) with **runtime** budgets for three product surfaces in `apps/dsa-web`:

1. Long list rendering (`HistoryList`)
2. Settings large forms (`SettingsField` isolation)
3. SSE chat streams (`agentChatStore` progress batching)

Chinese companion: [web-runtime-performance_CN.md](web-runtime-performance_CN.md).

## Design principles

- **Do not shrink measurement scope** to pass a budget (full declared input sizes stay in CI contracts).
- **Do not remove product features** to hit a number.
- **Soft gate first**: exceedances warn in CI without failing the Web gate until thresholds are proven stable.
- Structural metrics are CI-reproducible; wall-clock targets are manual guidance on reference hardware.

## Budgets (source of truth)

Machine-readable: `apps/dsa-web/scripts/runtime-performance-budget.json`.

Shared constants: `apps/dsa-web/src/performance/runtimeBudgets.ts`.

| Scenario | Input | Metric | Budget | Rationale |
| --- | --- | --- | --- | --- |
| `history-list-virtualization` | 150 history rows | Mounted row DOM nodes | ≤ 40 | Lists > 100 rows must virtualize or hard-paginate; History already pages (20/page) but accumulates. |
| `settings-field-isolation` | 40 fields | Sibling field commits after one edit | 0 | Single-field edit must not re-render every sibling control. |
| `sse-progress-batching` | 60 SSE progress events | `progressSteps` store commits | ≤ 4 | rAF-batched commits keep Stop responsive under long streams. |

Wall-clock guidance (manual, not CI hard gates):

| Area | Target |
| --- | --- |
| Primary route switch | Interactive under ~300 ms on a reference laptop (prod build) |
| Settings field edit | Does not lock the shell/nav |
| Chat Stop | Perceived response under ~100 ms; UI not frozen multi-second |

## Measurement entry points

### Local / CI-reproducible contracts

```bash
cd apps/dsa-web
npm ci
# Hard contracts (fail on exceedance of structural budgets)
npx vitest run src/performance/__tests__/runtimePerformanceContracts.test.tsx
# Soft gate (default): prints WARN, always exit 0 when measurements complete
node scripts/check-runtime-performance.mjs
# Future hard gate once thresholds are stable:
node scripts/check-runtime-performance.mjs --strict
```

The soft-gate checker runs the Vitest measurement suite, writes a temporary report via `DSA_RUNTIME_PERF_REPORT`, and compares measured values to the budget JSON.

### Manual profiling notes (top heavy pages)

| Surface | How to profile | What to watch |
| --- | --- | --- |
| Home history rail | React Profiler + Performance panel; load 100+ history rows via infinite scroll | Mounted row count stays windowed; scroll FPS stays interactive |
| Settings AI / large category | Type into one field in a dense category | Sibling fields and shell remain responsive; no full-page remount |
| Chat SSE stream | Long Agent run with many stage/tool events; click Stop mid-stream | Progress UI updates in batches; Stop aborts without multi-second freeze |

## Product mitigations shipped with this budget

- **HistoryList**: fixed-estimate virtual window (`useVirtualWindow`) when item count ≥ 24; `HistoryListItem` memoized.
- **SettingsField**: `React.memo` with prop equality so unchanged sibling fields skip re-render.
- **SSE**: `agentChatStore` batches `progressSteps` commits with `requestAnimationFrame`; `ChatMessageBubble` memoized so stream progress does not re-parse every prior bubble.

## Soft gate in CI

The Web gate runs `node scripts/check-runtime-performance.mjs` after unit tests when frontend paths change. Soft mode prints warnings into the job log and **does not fail** the required Web gate. Switch to `--strict` only after budgets are validated on CI runners.

## Related

- Bundle size budget: `apps/dsa-web/scripts/bundle-size-budget.json`, `check-bundle-size.mjs`
- Issue #883 acceptance criteria and phases
