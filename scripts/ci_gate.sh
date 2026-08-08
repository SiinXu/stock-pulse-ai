#!/usr/bin/env bash
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
#
# Hosted CI entry points:
#   all                 — full offline suite with coverage floor (legacy / merge-group single-node)
#   syntax|flake8|deterministic — shared preflight
#   offline-tests       — full offline suite + coverage floor
#   offline-tests-selective — path-mapped pytest (PR tier); FULL fallback when uncertain
#   offline-tests-shard — one shard of the full suite; writes coverage data for combine
#   offline-tests-combine — combine shard coverage data and enforce the floor once
#   python-min-smoke    — 3.10 import/schema/smoke subset (PR tier)

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
  python scripts/check_import_layers.py --self-test
  python scripts/check_import_layers.py
  python scripts/check_config_access.py --self-test
  python scripts/check_config_access.py
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

_run_pytest_offline() {
  # Shared pytest invocation for offline (non-network, non-benchmark) suites.
  # Extra args are appended (paths, cov flags, etc.).
  local test_data_dir="$1"
  shift
  DATABASE_PATH="${test_data_dir}/stockpulse-ci.sqlite" \
    python -m pytest -m "not network and not benchmark" \
      --timeout=120 --timeout-method=thread \
      -o faulthandler_timeout=300 \
      "$@"
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
  # Coverage is measured for src/api/data_provider/bot and enforced by the
  # checked-in floor in scripts/coverage_floor_baseline.json.
  # Keep --cov= flags in lockstep with baseline.packages (order-sensitive).
  echo "==> backend-gate: assert --cov packages match coverage floor baseline"
  python scripts/check_coverage_floor.py --assert-cov-flags \
    --cov src --cov api --cov data_provider --cov bot
  _run_pytest_offline "${test_data_dir}" \
<<<<<<< HEAD
=======
      --durations=30 --durations-min=0.5 \
>>>>>>> origin/main
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

offline_test_suite_selective() {
  echo "==> backend-gate: selective offline test suite (PR tier)"
  local base_ref="${CI_SELECT_BASE:-origin/main}"
  local selection
  selection="$(python scripts/ci_select_tests.py --base "${base_ref}")"
  echo "==> selective mapping result: ${selection}"
  if [ "${selection}" = "FULL" ]; then
    echo "==> mapping uncertain or infrastructure touched — full offline suite"
    offline_test_suite
    return $?
  fi
  if [ "${selection}" = "NONE" ]; then
<<<<<<< HEAD
    echo "==> no backend pytest targets for changed paths — smoke collection only"
    local test_data_dir
    test_data_dir="$(mktemp -d)"
    # Collection smoke: ensure the suite still imports under markers.
=======
    echo "==> no backend pytest targets for changed paths — collection smoke only"
    local test_data_dir
    test_data_dir="$(mktemp -d)"
>>>>>>> origin/main
    DATABASE_PATH="${test_data_dir}/stockpulse-ci.sqlite" \
      python -m pytest -m "not network and not benchmark" \
        --collect-only -q \
        tests/test_ci_workflow.py \
      || true
    rm -rf "${test_data_dir}"
    return 0
  fi
<<<<<<< HEAD
  # Selective path: run mapped targets without coverage floor (full rigor is
  # merge-group only). Still enforce per-test timeouts.
=======
  # Selective path: run mapped targets without coverage floor (full floor stays
  # on push-to-main / full offline-tests). Still enforce per-test timeouts.
>>>>>>> origin/main
  local test_data_dir
  local test_exit_code=0
  test_data_dir="$(mktemp -d)"
  # shellcheck disable=SC2086
  _run_pytest_offline "${test_data_dir}" ${selection} \
    || test_exit_code=$?
  rm -rf "${test_data_dir}"
  return "${test_exit_code}"
}

<<<<<<< HEAD
offline_test_suite_shard() {
  local splits="${PYTEST_SPLITS:?PYTEST_SPLITS is required for offline-tests-shard}"
  local group="${PYTEST_GROUP:?PYTEST_GROUP is required for offline-tests-shard}"
  local overhead="${PYTEST_FIRST_SHARD_OVERHEAD:-0}"
  local out_dir="${COVERAGE_SHARD_DIR:-.}"
  local cov_data="${out_dir}/.coverage.shard${group}"
  local cov_json="${out_dir}/coverage-shard-${group}.json"
  local test_data_dir
  local test_exit_code=0
  test_data_dir="$(mktemp -d)"
  mkdir -p "${out_dir}"
  echo "==> backend-gate: offline test suite shard ${group}/${splits}"
  python scripts/check_coverage_floor.py --assert-cov-flags \
    --cov src --cov api --cov data_provider --cov bot
  # List shard modules, then run with an isolated coverage data file so a later
  # combine job can enforce the floor once on the merged report.
  shard_list_file="${test_data_dir}/shard-files.txt"
  python scripts/ci_test_shard.py \
    --splits "${splits}" \
    --group "${group}" \
    --first-shard-overhead "${overhead}" \
    --list-only > "${shard_list_file}"
  if [ ! -s "${shard_list_file}" ]; then
    echo "Shard ${group}/${splits} selected zero modules" >&2
    rm -rf "${test_data_dir}"
    return 1
  fi
  shard_count="$(wc -l < "${shard_list_file}" | tr -d " ")"
  echo "==> shard ${group} modules: ${shard_count}"
  # coverage.py data file isolation per shard
  export COVERAGE_FILE="${cov_data}"
  # shellcheck disable=SC2046
  DATABASE_PATH="${test_data_dir}/stockpulse-ci.sqlite" \
    python -m coverage run \
      --source=src,api,data_provider,bot \
      -m pytest \
      -m "not network and not benchmark" \
      --timeout=120 --timeout-method=thread \
      -o faulthandler_timeout=300 \
      $(cat "${shard_list_file}") \
    || test_exit_code=$?
  if [ "${test_exit_code}" -eq 0 ]; then
    python -m coverage json -o "${cov_json}"
    python -m coverage report || true
    echo "==> wrote ${cov_json} and ${cov_data}"
  fi
  rm -rf "${test_data_dir}"
  return "${test_exit_code}"
}

offline_test_suite_combine() {
  local data_dir="${COVERAGE_SHARD_DIR:-.}"
  local combined_json="${data_dir}/coverage-combined.json"
  echo "==> backend-gate: combine shard coverage data from ${data_dir}"
  shopt -s nullglob
  local data_files=( "${data_dir}"/.coverage.shard* )
  shopt -u nullglob
  if [ "${#data_files[@]}" -eq 0 ]; then
    echo "No shard coverage data files found under ${data_dir}" >&2
    return 1
  fi
  # coverage combine merges parallel data files into .coverage
  export COVERAGE_FILE="${data_dir}/.coverage.combined"
  rm -f "${COVERAGE_FILE}"
  python -m coverage combine "${data_files[@]}"
  python -m coverage json -o "${combined_json}"
  python -m coverage report || true
  echo "==> backend-gate: coverage floor on combined report"
  python scripts/check_coverage_floor.py --report "${combined_json}"
}

python_min_smoke() {
  echo "==> python-minimum: 3.10 import/schema/smoke (PR tier)"
  # Real 3.10 execution without a second full offline suite on every PR.
  # Merge-group runs the full offline suite on 3.10 instead.
=======
python_min_smoke() {
  echo "==> python-minimum: 3.10 import/schema/smoke (PR tier)"
  # Real 3.10 execution without a second full offline suite on every PR.
  # Push-to-main still runs the full offline suite on 3.10.
>>>>>>> origin/main
  python -m py_compile main.py server.py src/config.py src/storage.py
  python -c "
from src.config import get_config
from src.storage import DatabaseManager
from data_provider import DataFetcherManager
from api.app import app
print('✅ python-minimum smoke imports OK', app.title)
"
  local test_data_dir
  test_data_dir="$(mktemp -d)"
  DATABASE_PATH="${test_data_dir}/stockpulse-ci.sqlite" \
    python -m pytest -m "not network and not benchmark" \
      --timeout=120 --timeout-method=thread \
      -o faulthandler_timeout=300 \
      tests/test_ci_workflow.py \
      tests/test_api_schema_pydantic.py \
      tests/test_error_envelope_contract.py \
      -q
  rm -rf "${test_data_dir}"
  echo "==> python-minimum: smoke passed"
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
  offline-tests-selective)
    offline_test_suite_selective
    ;;
<<<<<<< HEAD
  offline-tests-shard)
    offline_test_suite_shard
    ;;
  offline-tests-combine)
    offline_test_suite_combine
    ;;
=======
>>>>>>> origin/main
  python-min-smoke)
    python_min_smoke
    ;;
  *)
<<<<<<< HEAD
    echo "Usage: $0 [all|syntax|flake8|deterministic|offline-tests|offline-tests-selective|offline-tests-shard|offline-tests-combine|python-min-smoke]" >&2
=======
    echo "Usage: $0 [all|syntax|flake8|deterministic|offline-tests|offline-tests-selective|python-min-smoke]" >&2
>>>>>>> origin/main
    exit 2
    ;;
esac
