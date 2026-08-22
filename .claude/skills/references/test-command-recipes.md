# Standard Test Command Recipes

Deterministic command menu so agents do not invent ad-hoc gates. Authoritative process is `AGENTS.md` §6; offline gate details live in `docs/testing-ci-gate.md`. When this file drifts from CI workflows, the workflows win.

## One-liners by scope

| Scope | Preferred command |
|-------|-------------------|
| AI governance assets | `python scripts/check_ai_assets.py` |
| Config three-way consistency | `python scripts/check_config_doc_consistency.py` |
| Config registry debt guard | `python -m pytest tests/core/test_env_example_config_registry_guard.py -q` |
| Backend full local gate | `./scripts/ci_gate.sh` |
| Backend syntax only | `python -m py_compile <changed_python_files>` |
| Backend offline tests | `python -m pytest -m "not network"` |
| Backend path-focused | `python -m pytest -m "not network" <paths> -q` |
| Web install | `cd apps/dsa-web && npm ci` |
| Web lint | `cd apps/dsa-web && npm run lint` |
| Web unit | `cd apps/dsa-web && npm run test` |
| Web unit coverage gate | `cd apps/dsa-web && npm run test:coverage` |
| Web i18n | `cd apps/dsa-web && npm run test:i18n` |
| Web build | `cd apps/dsa-web && npm run build` |
| Web smoke e2e | `cd apps/dsa-web && npm run test:e2e-security-preflight && npx playwright install --with-deps chromium && npm run test:smoke` |
| Desktop | PR gate: `cd apps/dsa-desktop && npm ci && npm test`. Packaging: Web build first, then `cd apps/dsa-desktop && npm install && npm run build` |
| CI deps (Python) | `python -m pip install --upgrade --constraint constraints.txt pip && python -m pip install --build-constraint build-constraints.txt -r .github/requirements-ci.txt` |

## Evidence minimum

For every claim of "verified", record:

1. Exact command (copy-pasteable)
2. Exit status / key summary line
3. Whether failures were attributed as pre-existing on `origin/main` vs new (see `run-verification` Step 3)
4. What was **not** run and why

## Do not

- Weaken or delete assertions to get green
- Expand config-registry debt baselines to green CI (see `hard-rules.md` §2)
- Treat `Cancelled` CI as pass
- Commit screenshots into the repo (attach on the PR instead)
