# Web Unit-Test Coverage Gate

- Status: `Living`
- Last verified: 2026-08-19
- Related: [Contributing Guide (EN)](CONTRIBUTING_EN.md), [Offline Test Gate](testing-ci-gate.md), `apps/dsa-web/vitest.config.ts`, `apps/dsa-web/scripts/web-coverage-baseline.json`

Chinese companion: [web-unit-coverage_zh.md](web-unit-coverage_zh.md).

## Purpose

The Web unit suite in `apps/dsa-web` now has a **measured** Vitest v8 coverage floor. Before this gate, `npm run test` proved tests passed but did not stop coverage from shrinking. The floor is ratcheted from a real measurement of `src/` with explicit exclusions only for generated, vendor/dev-only, and non-unit-testable data assets.

This is independent of the backend coverage floor in `scripts/coverage_floor_baseline.json`.

## Local reproduction

```bash
cd apps/dsa-web
npm ci
# Fast unit run without coverage (default local loop)
npm run test
# Same suite plus the coverage floor (what web-gate runs)
npm run test:coverage
```

`npm run test:coverage` is `vitest run --coverage`. It is the single unit-suite entry used by CI. Do not add a second `npm run test` step beside it.

HTML output is optional and local-only:

```bash
cd apps/dsa-web
npx vitest run --coverage --coverage.reporter=html
```

Reports write to `apps/dsa-web/coverage/`, which is gitignored.

## What is measured

| Setting | Value | Why |
| --- | --- | --- |
| Provider | `@vitest/coverage-v8` `4.1.0` (matches locked `vitest@4.1.0`) | Vitest-supported default; no Istanbul extra toolchain |
| `all` | `true` | Untested included files count as 0%, so the floor is honest |
| Include | `src/**/*.{ts,tsx}` | Product TypeScript only |
| Thresholds | integers in `scripts/web-coverage-baseline.json` | `floor(measured_percent - epsilon_percent)` per metric |

Initial measurement on `origin/main` `e441a0e8b` (653 product files, `all: true`):

| Metric | Measured | Floor (`epsilon=1`) |
| --- | --- | --- |
| Lines | 86.46% | 85 |
| Statements | 85.09% | 84 |
| Functions | 83.32% | 82 |
| Branches | 71.45% | 70 |

### Allowed exclusions

Vitest 4's `configDefaults.coverage.exclude` is empty, so the baseline lists every extra ignore explicitly:

| Pattern | Reason |
| --- | --- |
| `src/types/api.generated.ts` | Generated OpenAPI snapshot |
| `src/dev/**` | Local/dev mocks and annotator stubs |
| `src/playground/**` | Developer playground, not shipped product routes |
| `src/locales/**` | Translation dictionaries (structure gated by `npm run test:i18n`) |
| `src/i18n/translations/**` | Generated locale resource bundles |
| `src/assets/**` | Static SVG/image assets |
| `src/**/__tests__/**` | Unit-test files and helpers |
| `src/**/*.test.*` / `src/**/*.spec.*` | Colocated unit tests |
| `src/test-utils/**` | Test harness helpers |
| `src/setupTests.ts` | Vitest setup file |

Do **not** exclude pages, components, hooks, API clients, or stores to make the number look better.

## Ratchet policy

1. Measure with `npm run test:coverage` on an `origin/main`-equivalent unit suite.
2. Record `measured` totals from `coverage/coverage-summary.json` `total.{lines,functions,statements,branches}.pct`.
3. Set each threshold to `Math.floor(measured - epsilonPercent)` with `epsilonPercent = 1`.
4. Raise thresholds after a clean remasurement when coverage grows.
5. Do not lower thresholds to hide a regression. If a legitimate product change drops coverage, remasure, document the reason in the PR, and treat the lower floor as a review item.

The 1-point epsilon is deterministic headroom for v8 rounding and coverage-instrumentation noise. It is not a license to delete tests.

## CI wiring

`web-gate` replaces `npm run test` with `npm run test:coverage` when frontend paths change. Coverage instrumentation makes production-source glob/AST scans slower, so `vitest.config.ts` raises `testTimeout` to 30s only when `--coverage` is present. The default `npm run test` timeout stays 5s.

Testing Library `findBy` / `waitFor` does **not** inherit Vitest `testTimeout`. `src/setupTests.ts` therefore sets `asyncUtilTimeout` to 10s when `--coverage` is present and keeps the 1s default for the fast local loop. React.lazy report panels (for example `ReportDiagnostics` in `ReportSummary`) stay absent until the chunk resolves; tests must wait for those nodes as part of ready, not after a news-only settle. Timeouts live in `src/test-utils/coverageTimeouts.ts`.

## Related

- Backend coverage floor: [testing-ci-gate.md](testing-ci-gate.md)
- Bundle size budget: `apps/dsa-web/scripts/bundle-size-budget.json`
- Runtime performance soft gate: [web-runtime-performance.md](web-runtime-performance.md)
