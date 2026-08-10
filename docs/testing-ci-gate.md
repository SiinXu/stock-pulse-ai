# Offline Test Gate, Timeouts, Markers, and Coverage Floor

- Status: `Living`
- Last verified: 2026-08-06
- Related: [Contributing Guide (EN)](CONTRIBUTING_EN.md), `setup.cfg`, `scripts/ci_gate.sh`, `scripts/check_coverage_floor.py`, `.github/workflows/benchmarks.yml`

## Purpose

The backend CI gate (`./scripts/ci_gate.sh`) must:

1. Fail hangs with an attributed test name (per-test timeout).
2. Dump thread stacks when a single test is silent for too long (`faulthandler_timeout`).
3. Measure and enforce a **measured** line-coverage floor for production packages.
4. Fail collection on unknown pytest markers (`--strict-markers`).
5. Keep wall-clock / throughput assertions out of the default offline gate so noisy runners do not redden CI.
6. Refuse a working-tree coverage floor lower than `origin/main` (anti-lowering).
7. Require the offline suite's `--cov=` scopes to match `baseline.packages` exactly, and require measured files under every package prefix.

## Default offline selection

```bash
python -m pytest -m "not network and not benchmark"
```

| Marker | Meaning | In default gate? |
| --- | --- | --- |
| `network` | Needs external network or third-party services | No |
| `benchmark` | Wall-clock or throughput assertions that may flaky-fail on busy CI | No |
| `quality_benchmark` | Offline fixed-panel analysis quality fixtures (no live LLM) | Yes (unless also `network`) |
| `unit` / `integration` | Descriptive markers only | Yes when offline |

`setup.cfg` registers every marker and sets `addopts = -v --tb=short --strict-markers`. An unregistered marker fails collection.

## Per-test timeout

The gate invokes:

```text
--timeout=120 --timeout-method=thread -o faulthandler_timeout=300
```

| Flag | Behavior |
| --- | --- |
| `--timeout=120` | Any single test that runs longer than 120s fails with a pytest-timeout traceback |
| `--timeout-method=thread` | Uses a watcher thread (reliable when the test swallows signals) |
| `faulthandler_timeout=300` | When a single test (including teardown) is silent for 300s, dump all Python thread stacks to stderr |

Override a legitimately slow offline test with an explicit decorator, for example:

```python
@pytest.mark.timeout(300)
def test_large_fixture_parse():
    ...
```

Do **not** raise the global 120s limit for one slow case. Local debugging without timeouts remains available: run `python -m pytest ...` without the gate flags (timeout is not in global `addopts`).

## Coverage measurement and floor

The offline phase measures line coverage for:

- `src`
- `api`
- `data_provider`
- `bot`

and writes a coverage.py JSON report, then runs:

```bash
python scripts/check_coverage_floor.py --report <coverage.json>
```

The checked-in floor lives in [`scripts/coverage_floor_baseline.json`](../scripts/coverage_floor_baseline.json). Semantics:

- Floor is **measured total percent minus a small epsilon** (default 0.5 points), not an aspirational target.
- Falling below the floor fails the gate.
- Raising the floor after a clean measurement is allowed.
- Lowering the floor requires an explicit review: `python scripts/check_coverage_floor.py --write-baseline --allow-lower ...`.
- **Anti-lowering vs `origin/main`**: the deterministic gate runs
  `python scripts/check_coverage_floor.py --assert-floor-not-lowered`, which
  compares the working-tree `floor_percent` to
  `git show origin/main:scripts/coverage_floor_baseline.json`. A lower value
  fails. Raising is free. Missing refs / first-run clones skip with a logged
  notice.
- **Package scope is enforceable**: `run_check` fails if the coverage report
  has no measured files under any `baseline.packages` prefix, and `ci_gate.sh`
  asserts that the offline suite's `--cov=` flags match `baseline.packages`
  exactly (order-sensitive). Narrowing coverage to one well-covered package
  cannot game the floor.

### Legitimate floor lowering (maintainers only; keep it honest and loud)

1. Re-measure the offline suite and run
   `python scripts/check_coverage_floor.py --write-baseline --allow-lower`.
2. Open a dedicated PR that lowers `floor_percent` and explains the regression.
3. For that PR only, set `COVERAGE_FLOOR_ALLOW_LOWER_VS_MAIN=1` in the gate
   environment (or temporarily edit the anti-lowering comparison in
   `scripts/check_coverage_floor.py` so review sees an explicit maintainer
   decision). Do **not** silently lower only the JSON.
4. After merge, clear the override so the ratchet re-arms against the new floor
   on `origin/main`.

### Measure and update the floor

```bash
# Same packages and marker selection as the gate (timeout optional locally)
DATABASE_PATH=/tmp/stockpulse-cov.sqlite \
  python -m pytest -m "not network and not benchmark" \
    --cov=src --cov=api --cov=data_provider --cov=bot \
    --cov-report=term \
    --cov-report=json:coverage.json

python scripts/check_coverage_floor.py --assert-cov-flags \
  --cov src --cov api --cov data_provider --cov bot
python scripts/check_coverage_floor.py --write-baseline --report coverage.json
# After review only, if the measured value legitimately dropped:
# python scripts/check_coverage_floor.py --write-baseline --allow-lower --report coverage.json

python scripts/check_coverage_floor.py --self-test
python scripts/check_coverage_floor.py --assert-floor-not-lowered
```

## Running benchmarks (scheduled + manual)

Wall-clock assertions are marked `@pytest.mark.benchmark` and are **excluded**
from `ci_gate.sh`. They run in the non-blocking workflow
[`.github/workflows/benchmarks.yml`](../.github/workflows/benchmarks.yml)
(`schedule` weekly + `workflow_dispatch`), which uploads pytest output as an
artifact. That workflow is **not** a required branch-ruleset check.

```bash
# All benchmarks only (same selection as the scheduled workflow)
python -m pytest -m benchmark

# Search-performance suite
python -m pytest tests/services/test_search_performance.py -m benchmark

# Single cases
python -m pytest tests/test_task_execution.py -k real_thread_pool_shutdown -m benchmark
python -m pytest tests/security/test_sensitive_redaction.py -k field_scanner_checks_one_public -m benchmark
python -m pytest tests/data_provider/test_hk_stock_name_fallback.py -k parallel_cold_lookups -m benchmark
```

Current benchmark-marked wall-clock cases:

- `tests/services/test_search_performance.py` (throughput / typo / fuzzy budgets)
- `tests/test_task_execution.py::test_real_thread_pool_shutdown_returns_before_blocked_runner_exits` (`elapsed < 1`)
- `tests/security/test_sensitive_redaction.py::test_field_scanner_checks_one_public_boundary_per_whitespace_run` (`elapsed < 0.5`)
- `tests/data_provider/test_hk_stock_name_fallback.py::test_parallel_cold_lookups_share_one_em_request` (4-thread barrier / sleep; relocated from the blocking gate)

## Time determinism (fake clock, phase 1)

Wall-clock-sensitive offline tests should prefer the repo-local seam in
[`tests/time_determinism.py`](../tests/time_determinism.py) over real
`time.sleep` or live `datetime.now()` anchors.

| Piece | Role |
| --- | --- |
| `FakeClock` | Explicit `time()` / `monotonic()` / `tick()` / optional non-blocking `sleep()` |
| `install_fake_clock(monkeypatch, ...)` | Pytest install (reverts automatically) |
| `frozen_time(...)` | Context manager for `unittest.TestCase` |
| `fake_clock` fixture | Default freeze at `DEFAULT_FAKE_NOW` (2026-06-15 12:00 UTC) |

**Why not freezegun (phase 1):** freezegun is not in the dependency lock.
Adding it requires the reviewed lock-refresh path
(`scripts/check_dependency_locks.py --update` + supply-chain review). A
monkeypatch fixture covers the first converted suites without expanding the
lock surface. Revisit freezegun only through that process if a later phase
needs broader auto-patching.

**Scope notes:**

* Rebind module-level `datetime` names when code uses
  `from datetime import datetime` (pass `datetime_modules=[...]`).
* Leave `patch_sleep=False` when a test still needs real short sleeps (for
  example worker-drain loops). Prefer explicit `clock.tick(...)` for TTL /
  cooldown advances.
* OS-level waits (`concurrent.futures` timeouts, subprocess, thread joins)
  are **not** controlled by the fake clock.

* Pytest assertion rewriting may keep a separate globals dict for test methods.
  Rebinding ``datetime`` only on ``sys.modules[name]`` will not affect bare
  ``datetime.now()`` inside rewritten tests; also rebind the test method
  globals (see the news-freshness suite) or call ``clock.now()`` explicitly.


Phase-1 converted modules: `tests/search/test_search_news_freshness.py`,
`tests/data_provider/test_realtime_types.py`,
`tests/services/test_market_structure_service.py` (TTL / retry-delay cases).

There is no separate Chinese twin of this guide; keep time-determinism notes
here only until a bilingual testing guide pair is introduced.

## Parallelism (`pytest-xdist`)

`pytest-xdist` is **not** enabled in the gate by default. Global monkeypatches in `tests/conftest.py` (asyncio/anyio/TestClient rebinding) are process-global and may not be safe under multi-process collection. Re-evaluate with two clean `pytest -n auto -m "not network and not benchmark"` runs before enabling in `ci_gate.sh`.

## Threadless TestClient vs real Starlette client

The offline gate (and the default local suite) rebind FastAPI/Starlette `TestClient` to a process-local **threadless** client, plus related asyncio/anyio wake-up patches, so sandboxed CI runners do not hang on AnyIO cross-thread portals.

| Env var | Default | Behavior |
| --- | --- | --- |
| `STOCKPULSE_TEST_THREADLESS` | `1` (unset = on) | Use the threadless client and asyncio/anyio sandbox patches |
| `STOCKPULSE_TEST_THREADLESS=0` | — | Leave the real `starlette.testclient.TestClient` untouched |

Falsy values: `0`, `false`, `no`, `off`, empty string.

Local real-client run (same selection as the non-required `api-real-client` CI job):

```bash
STOCKPULSE_TEST_THREADLESS=0 \
  DATABASE_PATH=/tmp/stockpulse-real-client.sqlite \
  python -m pytest tests/api -m "not network and not benchmark"
```

The `api-real-client` job in `.github/workflows/ci.yml` is **not** a required branch-ruleset check. It runs **only on push-to-main** (after `ai-governance`), not on pull requests, so real-client regressions still surface post-merge without consuming PR runners.


## Playwright flake quarantine

Web e2e uses Playwright with **`retries: 0`**. Flakes must not be masked by re-runs or `waitForTimeout` sleeps. When a spec is intermittently red and the root cause cannot ship in the same PR, move it into the **quarantine lane** instead of weakening the blocking suite.

### Rules

1. **Tag** the test with `@quarantine` (Playwright `tag: ['@quarantine']` and/or the literal token in the title).
2. **Tracking issue required**: every quarantined case must pass `quarantineDetails(issueUrl, reason)` from `apps/dsa-web/e2e/quarantine.ts`. The helper rejects non-GitHub issue URLs and empty reasons at load time.
3. **Empty is healthy**: when the flake is fixed, remove the tag and details. Shipping zero quarantined specs is the default; the mechanism is the deliverable.
4. **No product bypass**: quarantine is for test harness isolation only. A genuine UI race still needs an English issue with trace evidence; the deterministic wait belongs in e2e helpers such as `expectAnalyzeButtonReady` in `apps/dsa-web/e2e/workbench-fixture.ts`.

### Example

```ts
import { test } from '@playwright/test';
import { quarantineDetails } from './quarantine';

test(
  'flaky surface @quarantine',
  quarantineDetails(
    'https://github.com/SiinXu/stock-pulse-ai/issues/1234',
    'Analyze button enable races setup-status; awaiting product fix on issue 1234.',
  ),
  async ({ page }) => {
    // ...
  },
);
```

### Lanes

| Lane | How | Role |
| --- | --- | --- |
| Blocking smoke | `npm run test:smoke` (default `chromium` project, `grepInvert: /@quarantine/`) | CI `web-e2e` and local default; must stay deterministic |
| Quarantine | `npm run test:smoke:quarantine` (`DSA_WEB_E2E_QUARANTINE_LANE=1`, project `chromium-quarantine`) | Non-blocking observation; may be red without failing the main gate |

`retries` stays `0` in both lanes. Quarantine is not a license to add sleeps.

### Workflow note

Wiring a continuous quarantine job in GitHub Actions (schedule / push-to-main observation, non-required check) is intentionally left to CI throughput PRs (`#808` / `#810` class). This repository ships the Playwright project + npm script so that wiring is a thin workflow step, not a second config design.

### Related readiness helper

The Analysis Workbench primary action stays disabled until `isExperienceModeReady` (setup-status request settled) and the stock query is non-empty. Specs that type a symbol and click **分析 / Analyze** must use `expectAnalyzeButtonReady` (controlled-input set + `expect(...).toBeEnabled()` on `#analysis-workbench-stock-search` and Analyze) rather than filling a still-disabled control or relying on placeholder visibility.

## CI path filters (`web-gate` vs `web-e2e`)

The `changes` job in `.github/workflows/ci.yml` emits two independent filters:

| Output | Consumed by | Paths (summary) |
| --- | --- | --- |
| `frontend` | `web-gate` on PR and push (lint / i18n / unit / build / bundle size) | `apps/dsa-web/**` |
| `web_e2e` | `web-e2e` on **push-to-main only** (real backend + Playwright smoke) | `apps/dsa-web/**`, `api/**`, `src/**`, `data_provider/**`, `bot/**`, `main.py`, `server.py`, dependency lock inputs, `ci.yml` |

PR runs keep the ruleset-required backend/docker/openapi gates. `web-gate` always concludes: it runs the full frontend matrix only when `frontend` is `true`, records a no-frontend summary when it is `false`, and fails closed when change detection is unavailable. `web-e2e` and `api-real-client` are observation jobs after merge. The auxiliary `PR Review` workflow is opt-in via `workflow_dispatch` and does not auto-run on every PR.

### PR-tier backend throughput

To avoid a doubled full offline suite on every PR:

| Job | PR tier | Push-to-main |
| --- | --- | --- |
| `backend-gate` offline phase | `./scripts/ci_gate.sh offline-tests-selective` via `scripts/ci_select_tests.py` (prints `FULL` / `NONE` / path targets) | `./scripts/ci_gate.sh offline-tests` (coverage floor) |
| `python-minimum` | `./scripts/ci_gate.sh python-min-smoke` (3.10 import + small contract suite) | `./scripts/ci_gate.sh offline-tests` |

Selective mapping falls back to the full offline suite when infrastructure paths change (for example `tests/conftest.py`, `ci.yml`, coverage floor scripts, or top-level config).

## Push-to-main CI

`ci.yml` triggers on `pull_request` **and** `push` to `main`. Concurrency group is `ci-${{ github.event.pull_request.number || github.ref }}` with `cancel-in-progress: true`, so a merge burst cancels the superseded `ci-refs/heads/main` run and keeps only the newest main revision.

## Local full gate

```bash
python -m pip install --upgrade --constraint constraints.txt pip
python -m pip install --build-constraint build-constraints.txt -r .github/requirements-ci.txt
python -m pip check
./scripts/ci_gate.sh
```

Phases: `syntax` → `flake8` → `deterministic` (includes `check_coverage_floor.py --self-test`, `check_import_layers.py` self-test + live check, and peer AST ratchets) → `offline-tests` (timeout + coverage + floor).

## Import-cycle ratchet

The deterministic phase also runs:

```bash
python scripts/check_import_layers.py --self-test
python scripts/check_import_layers.py
```

This shrink-only guard fails when a **new** bidirectional package import pair
appears (module-level edges only). See [import-cycle ratchet](import-cycle-ratchet.md)
and [ADR-010](adr/ADR-010-import-cycle-ratchet.md) for package identity, failure
messages, and the legitimate shrink / intentional-growth paths.

## Related CI packaging

`pytest-timeout` and `pytest-cov` are listed in `.github/requirements-ci.txt` and locked through `constraints.txt` via `scripts/check_dependency_locks.py`. Do not hand-edit `constraints.txt`.
