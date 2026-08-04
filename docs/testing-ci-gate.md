# Offline Test Gate, Timeouts, Markers, and Coverage Floor

- Status: `Living`
- Last verified: 2026-08-04
- Related: [Contributing Guide (EN)](CONTRIBUTING_EN.md), `setup.cfg`, `scripts/ci_gate.sh`, `scripts/check_coverage_floor.py`

## Purpose

The backend CI gate (`./scripts/ci_gate.sh`) must:

1. Fail hangs with an attributed test name (per-test timeout).
2. Dump thread stacks when a single test is silent for too long (`faulthandler_timeout`).
3. Measure and enforce a **measured** line-coverage floor for production packages.
4. Fail collection on unknown pytest markers (`--strict-markers`).
5. Keep wall-clock / throughput assertions out of the default offline gate so noisy runners do not redden CI.

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

### Measure and update the floor

```bash
# Same packages and marker selection as the gate (timeout optional locally)
DATABASE_PATH=/tmp/stockpulse-cov.sqlite \
  python -m pytest -m "not network and not benchmark" \
    --cov=src --cov=api --cov=data_provider --cov=bot \
    --cov-report=term \
    --cov-report=json:coverage.json

python scripts/check_coverage_floor.py --write-baseline --report coverage.json
# After review only, if the measured value legitimately dropped:
# python scripts/check_coverage_floor.py --write-baseline --allow-lower --report coverage.json

python scripts/check_coverage_floor.py --self-test
```

## Running benchmarks manually

Wall-clock assertions are marked `@pytest.mark.benchmark` and are **excluded** from `ci_gate.sh`. Run them on demand:

```bash
# All benchmarks only
python -m pytest -m benchmark

# Search-performance suite
python -m pytest tests/services/test_search_performance.py -m benchmark

# Single cases
python -m pytest tests/test_task_execution.py -k real_thread_pool_shutdown -m benchmark
python -m pytest tests/security/test_sensitive_redaction.py -k field_scanner_checks_one_public -m benchmark
```

Current benchmark-marked wall-clock cases:

- `tests/services/test_search_performance.py` (throughput / typo / fuzzy budgets)
- `tests/test_task_execution.py::test_real_thread_pool_shutdown_returns_before_blocked_runner_exits` (`elapsed < 1`)
- `tests/security/test_sensitive_redaction.py::test_field_scanner_checks_one_public_boundary_per_whitespace_run` (`elapsed < 0.5`)

## Parallelism (`pytest-xdist`)

`pytest-xdist` is **not** enabled in the gate by default. Global monkeypatches in `tests/conftest.py` (asyncio/anyio/TestClient rebinding) are process-global and may not be safe under multi-process collection. Re-evaluate with two clean `pytest -n auto -m "not network and not benchmark"` runs before enabling in `ci_gate.sh`.

## Local full gate

```bash
python -m pip install --upgrade --constraint constraints.txt pip
python -m pip install --build-constraint build-constraints.txt -r .github/requirements-ci.txt
python -m pip check
./scripts/ci_gate.sh
```

Phases: `syntax` → `flake8` → `deterministic` (includes `check_coverage_floor.py --self-test`) → `offline-tests` (timeout + coverage + floor).

## Related CI packaging

`pytest-timeout` and `pytest-cov` are listed in `.github/requirements-ci.txt` and locked through `constraints.txt` via `scripts/check_dependency_locks.py`. Do not hand-edit `constraints.txt`.
