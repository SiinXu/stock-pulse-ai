# Contributing Guide

Thank you for your interest in contributing! All kinds of contributions are welcome.

## 🐛 Reporting Bugs

1. Search [Issues](https://github.com/SiinXu/stock-pulse-ai/issues) first to check if it has already been reported.
2. Create a new Issue using the **Bug Report** template.
3. Provide detailed reproduction steps and environment information.

## 💡 Suggesting Features

1. Search Issues to make sure the suggestion hasn't already been raised.
2. Create a new Issue using the **Feature Request** template.
3. Describe your use case and expected behavior in detail.

## 🔧 Submitting Code

### Setting Up the Development Environment

```bash
# Clone the repository
git clone https://github.com/SiinXu/stock-pulse-ai.git
cd stock-pulse-ai

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and fill in the required API keys
```

### Contribution Workflow

1. Fork this repository.
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'feat: add some feature'`
4. Push the branch: `git push origin feature/your-feature`
5. Open a Pull Request against `main`.

### Architecture Decisions

If a PR changes component boundaries, a cross-module source of truth, the runtime/persistence/deployment model, security or failure policy, or a reusable large-migration method, its description must record ADR consideration: link a new or existing ADR, or explain why the change stays within accepted decisions and needs no new record. See the [ADR registry](adr/README.md) for numbering, statuses, process, and the template.

Accepted ADRs remain as history. Record a material reversal in a new ADR with reciprocal links instead of rewriting the earlier decision.

### Change Placement

Shared data-source, analysis-pipeline, domain, persistence, and domain-report semantics belong in the foundation pipeline first. API DTOs and projections, Web, Desktop, Bot, interactive Agent experiences, and repository governance belong in the product layer and consume foundation contracts. A cross-track change must identify one authority and preserve compatibility across domain schemas, API projections, task state, and report views; product entrypoints must not duplicate provider fallback, pipeline orchestration, or task lifecycle. See [Foundation Pipeline And Product Layer](foundation-product-architecture.md) for routing, upstream porting, and license-provenance rules. Architectural track does not determine license.

### Commit Message Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

Commit messages, Issue and PR titles/bodies, comments, reviews, GitHub Actions output, and bot comments must be written in English.

```
feat:     New feature
fix:      Bug fix
docs:     Documentation update
style:    Code formatting (no logic change)
refactor: Code refactoring
perf:     Performance improvement
test:     Test-related changes
chore:    Build / tooling changes
```

Examples:

```
feat: add DingTalk bot support
fix: handle 429 rate-limit with retry backoff
docs: update README deployment section
```

### Code Style

- Python code follows PEP 8 (line length: 120).
- Add English docstrings to functions and classes.
- Add English comments for non-obvious logic.
- Update relevant documentation when adding new features.

### CI Checks

After opening a PR, CI will automatically run the following PR checks:

| Check | Description | Required |
|-------|-------------|:--------:|
| `ai-governance` | Validates `AGENTS.md`, compatibility instructions, and repository collaboration assets | ✅ |
| `backend-gate` | `scripts/ci_gate.sh` syntax, flake8, deterministic, and offline-tests stages | ✅ |
| `docker-build` | Docker image build and key module import smoke test | ✅ |
| `web-gate` | `npm run lint` + `npm run test:i18n` + `npm run test` + `npm run build` for Web or related API/config/service contract changes | ✅ (when triggered) |
| `web-e2e` | Uses the same related-path trigger, starts the real backend, Vite, and a local fake model endpoint in isolation, then runs `npm run test:smoke` | ✅ (when triggered) |

`web-e2e` uses dedicated canary credentials only and scopes each CI run to `test-results/ci-secret-bearing/`. That credential-bearing run disables screenshots, videos, and traces. The repository `test:smoke` entry point rejects UI mode and alternate Playwright configs, while global setup checks every project after Playwright merges CLI and project configuration and requires the final trace value to remain `off`. Whether E2E passes or fails, CI first scans the raw run directory for text, logs, JSON, HAR, raw binary canary bytes, and unexpected trace/ZIP entries. It still rejects uninspectable PNG/JPEG/WebM by extension or signature, does not use OCR, and never echoes matched values. After the raw scan succeeds, a dedicated staging script strictly parses `playwright-results.json`, recursively preserves UTF-8 `.log`/`.txt` files and their directory structure under `service-logs/`, rejects symlinks, non-allowlisted files, disguised archives, and media signatures, and emits a size/SHA-256 `manifest.json`. CI scans that staging directory again and uploads only when both scans and staging succeed. Raw output, traces, media, and archives never enter the artifact.

Separately, the repository also has a non-blocking `network-smoke` workflow in `.github/workflows/network-smoke.yml`, but it is only triggered by `schedule` and `workflow_dispatch`, not by pull requests.

**Running checks locally:**

```bash
# Backend gate (recommended)
pip install -r requirements.txt
pip install flake8 pytest
./scripts/ci_gate.sh

# Frontend gate (only if you changed apps/dsa-web/)
cd apps/dsa-web
npm ci
npm run lint
npm run test:i18n
npm run test
npm run build

# Frontend E2E (starts the isolated backend, Vite, and fake provider)
DSA_WEB_E2E_RUN_ID=local-secret-bearing \
DSA_WEB_E2E_CREDENTIAL_BEARING=true \
DSA_WEB_E2E_TRACE=off \
DSA_PLAYWRIGHT_ARTIFACT_CANARY=stockpulse-local-canary-change-me \
DSA_WEB_E2E_ALPHA_API_KEY=stockpulse-local-canary-change-me \
  npm run test:smoke

# Scan local Playwright artifacts (use a dedicated test canary, never a real credential)
cd ../..
DSA_PLAYWRIGHT_ARTIFACT_CANARY=stockpulse-local-canary-change-me \
  python scripts/scan_playwright_artifacts.py apps/dsa-web/test-results/local-secret-bearing

# Real authenticated intentional-failure diagnostics acceptance; temporary files are cleaned
python scripts/check_playwright_failure_diagnostics.py
```

See [Web Internationalization Conventions](web-i18n_EN.md) for UI/report-language boundaries, domain registries, and error-code handling. New pages and languages must extend the relevant `src/locales/` domain instead of hardcoding visible JSX copy.

Playwright uses a throwaway password and isolates its `.env`, SQLite database, password hash, and session secret under `test-results/<run-id>/runtime/`. Reports, tasks, accounts, and configuration required by a scenario must be seeded deterministically by the fixture or the scenario itself; runtime state is removed when the suite ends without reading or modifying the developer's `.env`, database, or auth files. Backend Python resolution checks ancestor `.venv` directories first, then `python3`, then `python`, and prints the selected interpreter before startup; deterministic scenarios use `retries: 0`. Backend, Vite, and fake-provider logs are retained under `test-results/<run-id>/service-logs/`, and the machine-readable result is written to `playwright-results.json` in that run directory. The repository config sets trace to `off` for credential-bearing CI; after scanning the raw directory it uploads only text logs, JSON, and the manifest from a content-validated and rescanned staging directory, never screenshots, videos, or archives. A credential-free local debugging run may opt in to a media-free trace with `DSA_WEB_E2E_TRACE=retain-on-failure`; known test credential environment values automatically imply credential-bearing mode and cannot coexist with a false marker or trace opt-in. Credential-bearing entry points also reject forced `--trace` modes, `--ui`/`--ui-host`/`--ui-port`, and alternate `--config` files. The Web preflight follows the relative import graph and uses a TypeScript AST guard for local `test.use`/`test.extend` option objects, aliases, post-creation assignments, static `Object.fromEntries`, and direct/destructured/`Reflect.get` tracing access on recognizable BrowserContext values. It also pins the Playwright config to the single trace property owned by the runtime policy. Arbitrary dynamic property names, test options produced at runtime by arbitrary functions or external packages, and generated code remain outside the static model; global setup checks the final project configuration, and the raw scanner plus strict staging form the upload boundary. PR screenshots must come from a separate credential-free manual acceptance session and be attached directly to the PR description or comment. Override port conflicts with `DSA_WEB_SMOKE_BACKEND_PORT`, `DSA_WEB_SMOKE_FRONTEND_PORT`, or `DSA_WEB_SMOKE_PROVIDER_PORT`.

Contract regressions cannot be represented by mock counts, loop entries, or numbered comments. Model-routing tests must cover the same model name on two Connections and assert the exact `ModelRef`. Portfolio trade, cash-flow, corporate-action, and CSV-commit tests must reuse one operation ID to prove timeout-after-commit does not duplicate the ledger, and must reject a different payload under the same ID. Overlay tests must cover top-layer-only Escape handling, focus trapping/restoration, background inertness, and scroll locking. Every Playwright acceptance scenario needs its own readable test name and key assertion.

For local frontend/backend integration, `npm run dev` proxies `/api` to `DSA_WEB_DEV_API_PROXY` (default `http://127.0.0.1:8000`). Set it when the backend is running elsewhere; this variable only affects the Vite development server.

### Documentation Sync Rule

When modifying either language of a bilingual core document (for example, `docs/full-guide.md` / `docs/full-guide_EN.md`), evaluate and normally update its counterpart. If the counterpart is not updated, the PR description must explain why.

## 📋 Priority Areas for Contribution

- 🔔 New notification channels (e.g., Slack, Matrix)
- 🤖 New AI model integrations
- 📊 New data source adapters
- 🐛 Bug fixes and performance improvements
- 📖 Documentation improvements and translations

## ❓ Questions

Feel free to:
- Open an Issue for discussion.
- Browse existing Issues.

Thank you for contributing! 🎉
