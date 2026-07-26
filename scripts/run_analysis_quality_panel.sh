#!/usr/bin/env bash
# Deterministic local runner for the offline analysis quality panel (#617).
# No network. No live LLM calls. Exits non-zero if any panel assertion fails.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PY="${PYTHON:-}"
if [[ -z "${PY}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  elif command -v python >/dev/null 2>&1; then
    PY=python
  else
    echo "[analysis-quality-panel] ERROR: python3/python not found" >&2
    exit 127
  fi
fi

export PYTHONDONTWRITEBYTECODE=1

echo "[analysis-quality-panel] repo=${REPO_ROOT}"
echo "[analysis-quality-panel] interpreter=${PY}"
echo "[analysis-quality-panel] running offline panel (pytest -m 'not network and quality_benchmark')"

# Force an isolated temp DB path so local runs never touch developer state.
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/stockpulse-aqp.XXXXXX")"
cleanup() {
  rm -rf "${tmp_dir}"
}
trap cleanup EXIT

DATABASE_PATH="${tmp_dir}/stockpulse-aqp.sqlite" \
  "${PY}" -m pytest \
    -m "not network and quality_benchmark" \
    tests/analysis_quality \
    -q \
    --tb=short \
    "$@"

echo "[analysis-quality-panel] OK"
