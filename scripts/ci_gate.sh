#!/usr/bin/env bash

set -euo pipefail

syntax_check() {
  echo "==> backend-gate: Python syntax check"
  python -m py_compile main.py src/config.py src/auth.py src/analyzer.py src/notification.py
  python -m py_compile src/storage.py src/scheduler.py src/search_service.py
  python -m py_compile src/migrations/*.py src/migrations/versions/*.py
  python -m py_compile src/market_analyzer.py src/stock_analyzer.py
  python -m py_compile data_provider/*.py
}

flake8_checks() {
  echo "==> backend-gate: flake8 critical checks"
  flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
  echo "==> backend-gate: broad exception classification guard"
  python scripts/check_broad_exceptions.py
}

deterministic_checks() {
  echo "==> backend-gate: local deterministic checks"
  python scripts/check_workflow_supply_chain.py --self-test
  python scripts/check_workflow_supply_chain.py
  python scripts/check_dependency_locks.py --self-test
  python scripts/check_dependency_locks.py
  python scripts/check_install_guidance.py --self-test
  python scripts/check_install_guidance.py
  python scripts/check_local_model_catalog.py
  python scripts/check_dependency_vulnerabilities.py --self-test
  python scripts/check_legacy_facade_imports.py --self-test
  python scripts/check_legacy_facade_imports.py
  python scripts/check_coverage_floor.py --self-test
  # Anti-lowering: working-tree floor must not fall below origin/main.
  # Missing ref / first-run skips with a logged notice. Intentional lowers:
  # set COVERAGE_FLOOR_ALLOW_LOWER_VS_MAIN=1 (loud, temporary).
  if git rev-parse --verify origin/main >/dev/null 2>&1; then
    :
  elif git rev-parse --verify main >/dev/null 2>&1; then
    :
  else
    # Best-effort: shallow CI checkouts may lack origin/main until fetched.
    git fetch --no-tags --depth=1 origin main 2>/dev/null || true
  fi
  python scripts/check_coverage_floor.py --assert-floor-not-lowered
  echo "==> backend-gate: mypy type check (src/schemas only)"
  python -m mypy --config-file mypy.ini
  ./scripts/test.sh code
  ./scripts/test.sh yfinance
}

offline_test_suite() {
  echo "==> backend-gate: offline test suite"
  local test_data_dir
  local coverage_report
  local test_exit_code=0
  test_data_dir="$(mktemp -d)"
  coverage_report="${test_data_dir}/coverage.json"
  # Marker selection excludes network and wall-clock benchmarks. Benchmarks
  # still collect under --strict-markers; scheduled/manual runner:
  #   .github/workflows/benchmarks.yml  (pytest -m benchmark)
  #   python -m pytest -m benchmark
  # Per-test timeout + thread method: hard-fail hangs with an attributed
  # traceback instead of burning the full job budget. faulthandler_timeout
  # dumps every thread stack when a single test (including teardown) is silent
  # for 300s, which is complementary post-mortem signal beyond pytest-timeout.
  # Coverage is measured for src/api/data_provider/bot and enforced by the
  # checked-in floor in scripts/coverage_floor_baseline.json.
  # Keep --cov= flags in lockstep with baseline.packages (order-sensitive).
  echo "==> backend-gate: assert --cov packages match coverage floor baseline"
  python scripts/check_coverage_floor.py --assert-cov-flags \
    --cov src --cov api --cov data_provider --cov bot
  DATABASE_PATH="${test_data_dir}/stockpulse-ci.sqlite" \
    python -m pytest -m "not network and not benchmark" \
      --timeout=120 --timeout-method=thread \
      -o faulthandler_timeout=300 \
      --cov=src --cov=api --cov=data_provider --cov=bot \
      --cov-report=term \
      --cov-report="json:${coverage_report}" \
    || test_exit_code=$?
  if [ "${test_exit_code}" -eq 0 ]; then
    echo "==> backend-gate: coverage floor"
    python scripts/check_coverage_floor.py --report "${coverage_report}" \
      || test_exit_code=$?
  fi
  rm -rf "${test_data_dir}"
  return "${test_exit_code}"
}

run_all() {
  syntax_check
  flake8_checks
  deterministic_checks
  offline_test_suite
  echo "==> backend-gate: all checks passed"
}

phase="${1:-all}"

case "$phase" in
  all)
    run_all
    ;;
  syntax)
    syntax_check
    ;;
  flake8)
    flake8_checks
    ;;
  deterministic)
    deterministic_checks
    ;;
  offline-tests)
    offline_test_suite
    ;;
  *)
    echo "Usage: $0 [all|syntax|flake8|deterministic|offline-tests]" >&2
    exit 2
    ;;
esac
