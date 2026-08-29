# Offline Test Gate, Timeouts, Markers, and Coverage Floor

- Status: `Living`
- Last verified: 2026-08-29
- Related: [Contributing Guide (EN)](CONTRIBUTING_EN.md), `setup.cfg`, `scripts/ci_gate.sh`, `scripts/check_coverage_floor.py`, `.github/workflows/benchmarks.yml`

## Purpose

The backend CI gate (`./scripts/ci_gate.sh`) must:

1. Fail hangs with an attributed test name (per-test timeout).
2. Dump thread stacks when a single test is silent for too long (`faulthandler_timeout`).
3. Measure and enforce a **measured** line-coverage floor for production packages (**push-to-main / full tier only**).
4. Fail collection on unknown pytest markers (`--strict-markers`).
5. Keep wall-clock / throughput assertions out of the default offline gate so noisy runners do not redden CI.
6. Refuse a working-tree coverage floor lower than `origin/main` (anti-lowering).
7. Require the offline suite's `--cov=` scopes to match `baseline.packages` exactly, and require measured files under every package prefix.

## Two-tier hosted CI (throughput)

| Event | Backend tier | What runs |
| --- | --- | --- |
| `pull_request` | **Fast** | `syntax` + `flake8` + `deterministic` + **selective** offline pytest via `scripts/ci_select_tests.py`. When mapping is `FULL`, the four 30-minute `backend-tests` shards run (same partition as push-to-main). The 45-minute selective `backend-gate` job must not invoke the unsharded `offline_test_suite`. |
| `push` to `main` | **Full** | 4 sharded offline suites (`scripts/ci_test_shard.py`) + **one** combined coverage floor check |
| `merge_group` (`checks_requested`) | **Full** | Same authoritative Python 3.11 shards + coverage combine as push-to-main, plus the same four Python 3.10 shards, even when path filters would skip backend on a PR or push (for example frontend-only `apps/dsa-web/src/api/auth.ts`). `changes.backend` is fail-closed true for this event. The PR selective planner does not run. Observation jobs stay push-only. Path-gated jobs such as `docker-build` keep their existing path filters and may skip. Workflow readiness only; this repository does not enable a merge queue. |

`python-minimum` (3.10) runs `python-min-smoke` (imports + a small offline subset) on pull requests. Pushes to `main` and `merge_group` runs use the same four `offline-tests-shard` partitions on Python 3.10 (`python-minimum-tests`, 45-minute job bound) and fail the required `python-minimum` check unless every shard succeeds. Coverage floor remains a Python 3.11 `backend-gate` combine; the 3.10 shards prove floor-runtime execution only.

Path-triggered blocking jobs in `.github/workflows/ci.yml` always conclude so they can be required checks, and they run the existing green commands only when their path filters match:

| Check | When the full matrix runs | Command |
| --- | --- | --- |
| `ocr-stock-extractor` | OCR / image stock-extractor sources, tests, `requirements/ocr.txt`, or `ci.yml` | Install `requirements/ocr.txt` + Tesseract, then the existing extractor pytest files; skips are failures |
| `desktop-gate` | `apps/dsa-desktop/**`, desktop packaging scripts, or `ci.yml` | `cd apps/dsa-desktop && npm ci && npm test` (no `electron-builder` / Ollama download) |

Default backend pytest still excludes `@pytest.mark.network`. These jobs do not promote network tests to blocking.

Local full gate remains:

```bash
./scripts/ci_gate.sh
# or
./scripts/ci_gate.sh offline-tests
```

### Enabling the merge queue (maintainer-only, later step)

`ci.yml` already answers `merge_group` `checks_requested`, but no merge queue is enabled on this
repository and no hosted `merge_group` run has ever been produced.

**Eligibility precondition: the repository must be owned by a GitHub organization.** GitHub exposes
the **Require merge queue** ruleset rule only for organization-owned repositories, so on a
personal-account repository the rule does not exist to enable. This repository is owned by a
personal account, which is why the queue cannot be turned on today and the `merge_group` path stays
dormant and unproven on hosted runners. Moving the repository under an organization is therefore a
prerequisite for every step below. The steps are repository-admin actions, not code changes, and
they are the only thing left to activate the path.

1. Open **Settings -> Rules -> Rulesets -> `Protect main with required CI`**.
2. Add the **Require merge queue** rule and keep merge method, build concurrency, and grouping at
   GitHub's defaults.
3. Leave the required status checks exactly as they are. The queue reuses the same eight contexts,
   which are the `ci.yml` job display names:

   - `🔎 Change Detection`
   - `ai-governance`
   - `backend-gate`
   - `python-minimum`
   - `pydanticai-installed`
   - `docker-build`
   - `openapi-types-gate`
   - `web-gate`

4. Queue one low-risk pull request and confirm the resulting `merge_group` run scheduled four
   `backend-tests` shards, the `backend-gate` coverage combine, and four `python-minimum-tests`
   shards.

Rollback order matters: **disable the Require merge queue rule first**, then revert the workflow
change. Reverting files in this repository does not undo a remote ruleset, and a required context
that stops reporting on `merge_group` leaves queued pull requests stuck instead of failing fast.

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

The offline phase measures line coverage for the single canonical `src`
package, including its API, Bot, and provider subpackages, and writes a
coverage.py JSON report, then runs:

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
    --cov=src \
    --cov-report=term \
    --cov-report=json:coverage.json

python scripts/check_coverage_floor.py --assert-cov-flags --cov src
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

## Agent HITL / Critic path contracts (high-risk)

Backend regressions in Human-in-the-Loop approvals and the bounded Critic must
be caught by **deterministic offline tests** that exercise real risk layers:

| Path | Real entry preferred | Deterministic seams | Anchor tests |
| --- | --- | --- | --- |
| HITL approve → consume | `ApprovalService.await_risk_control_bypass` and dashboard `_apply_risk_override` | Injectable `clock` / `sleeper`; in-memory SQLite | `tests/services/test_approval_regression_anchors.py`, `tests/agent/test_hitl_path_contracts.py` |
| HITL reject | Same | Decision injected via `sleeper` (no wall-clock sleep) | Same |
| HITL proposal lifetime timeout | Same | Advance injectable clock past `expires_at` | Same |
| HITL pipeline deadline timeout | Same | `stop_waiting_check` or `_approval_deadline_epoch` | Same; semantics in [human-approvals_EN.md](human-approvals_EN.md) |
| Critic pass / fail_soft / budget skip | Orchestrator `_execute_pipeline` | Fixture Critic + fake `time.time` budget | `tests/agent/test_bounded_critic.py` |

**Hard rules for these suites** (see Issues #225, #1079):

1. Do **not** mock away `ApprovalService.await_risk_control_bypass`, the risk
   manager gate, or Critic fail-soft/budget logic merely to raise coverage.
2. Prefer wiring a real service with a test database and injectable clock over
   stubbing return values of the risk layer.
3. Never lower `scripts/coverage_floor_baseline.json` to green these paths.

Operational HITL defaults and the independence of proposal lifetime vs pipeline
deadline are documented in [human-approvals_EN.md](human-approvals_EN.md).

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

The `api-real-client` job in `.github/workflows/ci.yml` is **not** a required branch-ruleset check. It runs **only on push-to-main** (after `ai-governance`), not on pull requests or `merge_group`, so real-client regressions still surface post-merge without consuming PR or queue runners.


## Playwright flake quarantine

Web e2e uses Playwright with **`retries: 0`**. Flakes must not be masked by re-runs or `waitForTimeout` sleeps. When a spec is intermittently red and the root cause cannot ship in the same PR, move it into the **quarantine lane** instead of weakening the blocking suite.

### Rules

1. **Tag** the test with `@quarantine` (Playwright `tag: ['@quarantine']` and/or the literal token in the title).
2. **Tracking issue required**: every quarantined case must pass `quarantineDetails(issueUrl, reason)` from `apps/dsa-web/e2e/quarantine.ts`. The helper rejects non-GitHub issue URLs and empty reasons at load time.
3. **Empty is healthy**: when the flake is fixed, remove the tag and details. Shipping zero quarantined specs is the default; the mechanism is the deliverable.
4. **No product bypass**: quarantine is for test harness isolation only. A genuine UI race still needs an English issue with trace evidence; the deterministic wait belongs in e2e helpers such as `expectAnalyzeButtonReady` in `apps/dsa-web/e2e/workbench-fixture.ts`.

### Route-handler teardown

Specs import `test` from `apps/dsa-web/e2e/playwright-test.ts`, not directly from `@playwright/test`. That shared `test` unroutes page and context handlers with `page.unrouteAll({ behavior: 'ignoreErrors' })` after the test body and before Playwright closes the page. Async handlers that `await route.fetch()` must not outlive that close; do not paper over the race with a per-handler try/catch.

### Example

```ts
import { test } from './playwright-test';
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
| `frontend` | `web-gate` on PR and push (lint / i18n / unit coverage / runtime-perf / build / bundle size) | `apps/dsa-web/**` |
| `web_e2e` | `web-e2e` on **push-to-main only** (real backend + Playwright smoke) | `apps/dsa-web/**`, `src/**`, `main.py`, `server.py`, dependency lock inputs, `ci.yml` |

PR runs keep the ruleset-required backend/docker/openapi gates. `web-gate` always concludes: it runs the full frontend matrix only when `frontend` is `true`, records a no-frontend summary when it is `false`, and fails closed when change detection is unavailable. The frontend unit step is `npm run test:coverage` (one Vitest run with the v8 coverage floor). Local reproduction and the ratchet policy live in [Web Unit-Test Coverage Gate](web-unit-coverage.md). `web-e2e` and `api-real-client` are observation jobs after merge. The auxiliary `PR Review` workflow is opt-in via `workflow_dispatch` with a required `pr_number` and does not auto-run on every PR. Its `security-check` job is checkout-free: it snapshots head/base SHAs through `pulls.get`, inventories files with SHA-pinned `repos.compareCommits` of those exact commit SHAs (same-repo and fork; not `USERNAME:BRANCH` / `owner:SHA`), and fail-closes on a later `pulls.get` mismatch or compare 404. `pulls.listFiles` is not used for that inventory because it cannot pin a SHA.

### PR-tier backend throughput

To avoid a doubled full offline suite on every PR:

| Job | PR tier | Push-to-main / `merge_group` |
| --- | --- | --- |
| `backend-gate` offline phase | `./scripts/ci_gate.sh offline-tests-selective` via `scripts/ci_select_tests.py` (prints `NONE` / path targets). Mapping `FULL` is fail-closed in that script and is scheduled as four `backend-tests` shards plus `offline-tests-combine` under the same required check name. Planner and selective job pin `github.event.pull_request.base.sha` so a later `origin/main` fetch cannot remap `NONE` → `FULL`. | Four `offline-tests-shard` jobs followed by one `offline-tests-combine` coverage-floor check. `merge_group` uses this full path even when `backend_non_web` and `backend_web_contract` are false; it does not run the PR planner. |
| `python-minimum` | `./scripts/ci_gate.sh python-min-smoke` (3.10 import + small contract suite) | Four `python-minimum-tests` shards (`./scripts/ci_gate.sh offline-tests-shard` on Python 3.10, 45-minute job bound); required `python-minimum` check fails unless every shard result is `success` |

Selective mapping fails closed to the **sharded** full offline suite when infrastructure paths change (for example `tests/conftest.py`, `ci.yml`, coverage floor scripts, or top-level config), when the merge-base cannot be proven, when a changed path matches no mapping, when a `tests/` path is not a collectable `test_*.py` module (helpers, nested conftest, fixtures, SQL/JSON, images), when a mapping is an empty tuple outside the `NONE` allowlist, or when every mapped target is missing / every glob matches nothing. `NONE` is allowed only for `docs/`-only and remaining `apps/dsa-web/`-only change sets (`NONE_PREFIXES` in `scripts/ci_select_tests.py`). The `backend_web_contract` paths in `.github/workflows/ci.yml` (`apps/dsa-web/public/**`, settings help locales, `systemConfigI18n.ts`, and `llmProviderTemplates.ts`) are excluded from that allowlist and map to the backend tests that cover the shared contract. Any other empty selection is `FULL`. Collectable `tests/test_*.py` files still map to themselves. The 45-minute selective job must not run `offline_test_suite`. Hosted counterexamples: PR #1375 run 32238883191 and PR #1377 run 32238746609 printed planner `NONE`, remapped to `FULL` after `git fetch --depth=1 origin main`, and cancelled at 45m21s.

## Push-to-main CI

`ci.yml` triggers on `pull_request` and `push` to `main`, plus `merge_group` `checks_requested` (workflow readiness only; no merge queue is enabled here). Concurrency group is `ci-${{ (github.event_name == 'pull_request' && github.event.pull_request.number) || github.ref }}` with `cancel-in-progress: true`, so a merge burst cancels the superseded `ci-refs/heads/main` run and keeps only the newest main revision. The `pull_request` clause short-circuits on `merge_group` and `push`, so those events use `github.ref` and never dereference `github.event.pull_request`. The four `backend-tests` shards are duration-greedy over `.github/ci-test-durations.json` (hosted module wall-clocks from main run 32963128085 attempt 3). Unknown modules missing from that map receive the median of known weights so a PR can add `tests/**/test_*.py` files before a hosted timing refresh; committed coverage is ratcheted (non-empty, at least 95% of discovered modules, hotspot weight preserved) rather than requiring an exact key match. An empty durations map falls back to equal 1.0s weights and is **not** balanced. Hosted main run 32963128085 attempt 3 cancelled backend-tests shard 1 at the 30-minute job bound after colocating `tests/test_exception_log_callsite_guard.py` (~16 minutes) with other modules (job 98171256271). `PYTEST_FIRST_SHARD_OVERHEAD` on `backend-tests` is 165 seconds for shard-1-only supply-chain / syntax / flake8 / deterministic checks; `python-minimum-tests` keeps overhead 0 because those jobs skip that pre-pytest work. The Python 3.10 push suite uses the same 4-way module partition with a 45-minute job bound: hosted 3.10 shard 2 is ~28-30 minutes (main run 32269161288 job 96121339880 cancelled at the 30-minute cap at 99% passed; prior post-#1378 runs finished in 29:24-29:52). An unsharded `offline-tests` job on 3.10 historically ran ~47 minutes (main runs 32223100719 and 32234145338) and was superseded before the required check could stay green.

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
appears. Edges are measured from **import-time** imports: the module body plus
every nested body that executes during import (`try`/`except`/`else`/`finally`,
`if`/`else`, `with`, loops and their `else`, `match` cases, and class bodies).
`def` bodies and `if TYPE_CHECKING:` blocks are excluded. See
[import-cycle ratchet](import-cycle-ratchet.md) and
[ADR-010](adr/ADR-010-import-cycle-ratchet.md) for package identity, failure
messages, and the legitimate shrink / intentional-growth paths.

The peer [layer-direction ratchet](layer-direction-ratchet.md) shares that
traversal and additionally records function-local reverse imports in an advisory
`lazy_exceptions` inventory. Drift in that inventory — a deferred reverse import
added or removed — never fails CI: the guard prints `NOTE:` lines, still exits
`0`, and no test pins the live tree to the checked-in seed. A `lazy_exceptions`
section the guard cannot parse is still rejected as an invalid baseline
(`ERROR: invalid-baseline: …`, exit `1`), like every other baseline section.

The enforced inventories use the same shrink-is-free convention as the guards:
repository pins (`test_repository_inventories_are_not_inflated`,
`test_repository_pair_inventory_is_not_inflated`,
`test_baseline_hard_ceiling_matches_introduction_inventory`) assert `<=` /
subset against the introduction ceilings (12 reverse edges, 11 pairs). They
must not require live equality with the checked-in allowlist, so a later
legitimate shrink stays green before `--write-baseline`. Growth past those
ceilings, or a live scan that is not a subset of the allowlist, still fails.
`scripts/` edits map through `scripts/ci_select_tests.py` to `tests/scripts`,
so those pins run on selective PR CI.

## Related CI packaging

`pytest-timeout` and `pytest-cov` are listed in `.github/requirements-ci.txt` and locked through `constraints.txt` via `scripts/check_dependency_locks.py`. Do not hand-edit `constraints.txt`.
