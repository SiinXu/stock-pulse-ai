# Contributing Guide

Thank you for your interest in contributing! All kinds of contributions are welcome.

## 🐛 Reporting Bugs

1. Search [Issues](https://github.com/ZhuLinsen/daily_stock_analysis/issues) first to check if it has already been reported.
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
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis

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

### Commit Message Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

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
- Add docstrings to functions and classes.
- Add comments for non-obvious logic.
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
npm run test:smoke
```

See [Web Internationalization Conventions](web-i18n_EN.md) for UI/report-language boundaries, domain registries, and error-code handling. New pages and languages must extend the relevant `src/locales/` domain instead of hardcoding visible JSX copy.

Playwright uses a throwaway password and isolates its `.env`, SQLite database, password hash, and session secret under `test-results/runtime/`. Reports, tasks, accounts, and configuration required by a scenario must be seeded deterministically by the fixture or the scenario itself; runtime state is removed when the suite ends without reading or modifying the developer's `.env`, database, or auth files. Backend Python resolution checks ancestor `.venv` directories first, then `python3`, then `python`, and prints the selected interpreter before startup; deterministic scenarios use `retries: 0`. Backend, Vite, and fake-provider logs are retained under `test-results/service-logs/`; CI uploads them with screenshots, traces, and videos on failure. Override port conflicts with `DSA_WEB_SMOKE_BACKEND_PORT`, `DSA_WEB_SMOKE_FRONTEND_PORT`, or `DSA_WEB_SMOKE_PROVIDER_PORT`.

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
- Browse existing Issues and Discussions.

Thank you for contributing! 🎉
