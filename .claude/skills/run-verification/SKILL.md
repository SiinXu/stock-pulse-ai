# Run Verification

Select and execute this repository's verification matrix based on change scope, and output a structured verification report (executed / not executed / pre-existing failures / new failures). This is the executable form of `AGENTS.md` §6.

**Source of truth**: repository root `AGENTS.md`. If the matrix here drifts, `AGENTS.md` and the actual CI workflows win.

## Usage

```text
/run-verification [--scope backend|web|desktop|docs|workflow|ai-assets|auto]
```

`--scope auto` (default): derive the change scope from `git diff --name-only <baseline>...`; multiple scopes can apply at once.

## Instructions

### Step 1: Derive change scope

```bash
git diff --name-only origin/main...HEAD
```

| Path hit | Scope |
|----------|-------|
| `main.py`, `src/**`, `data_provider/**`, `api/**`, `bot/**`, `tests/**` | backend |
| `apps/dsa-web/**` | web |
| `apps/dsa-desktop/**`, `scripts/*desktop*` | desktop |
| `README.md`, `docs/**` | docs |
| `.github/**`, `scripts/**`, `docker/**` | workflow |
| `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, `.github/instructions/**`, `.claude/skills/**` | ai-assets |

### Step 2: Execute per scope

**backend** (prefer the full gate; fall back to itemized commands):

```bash
./scripts/ci_gate.sh
# Minimum requirement:
python -m py_compile <changed_python_files>
python -m pytest -m "not network" <relevant test paths>
```

**web**:

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run test
npm run build
```

If i18n is touched (`src/i18n/**`, `src/locales/**`, or any user-visible copy), additionally:

```bash
npm run test:i18n
```

**web e2e** (only when the change targets e2e specs or components covered by them — e.g. overlays, auth flows; not part of the default web gate):

```bash
cd apps/dsa-web
npm run test:e2e-security-preflight
npx playwright install --with-deps chromium
npm run test:smoke                 # playwright.config.ts self-hosts backend + web via webServer
# Single spec: node e2e/run-playwright-tests.mjs <spec-file>
```

The backend webServer requires Python deps installed (`python -m pip install --build-constraint build-constraints.txt -r .github/requirements-ci.txt`). e2e failures follow the same Step 3 baseline attribution as unit tests — many e2e specs are already red on main.

**desktop** (web first, then desktop):

```bash
cd apps/dsa-web && npm run build
cd ../dsa-desktop && npm install && npm run build
```

When platform limits prevent full verification, list verified vs unverified platforms explicitly in the report.

**docs**: tests are not enforced, but every command, config entry, filename, and workflow name mentioned in the docs must be checked against the actual repository, and the report must state the check results.

**workflow**: run the local validation closest to the change (e.g. `bash -n`, a `docker build` smoke, `python scripts/<changed>.py --help`). Anything not locally verifiable (e.g. Actions trigger conditions) is listed as unverified with the risk stated.

**ai-assets**:

```bash
python scripts/check_ai_assets.py
```

### Step 3: Red-test attribution (the key discipline)

On any failure, compare against the main baseline before drawing conclusions:

```bash
git stash            # or use a clean worktree: git worktree add /tmp/wt-main origin/main
# Run the same command on the baseline and record its failure set
git stash pop
```

Worktree tip: symlink `node_modules` into the worktree (`ln -s <repo>/apps/dsa-web/node_modules /tmp/wt-main/apps/dsa-web/node_modules`) instead of reinstalling; remove the worktree afterwards (`git worktree remove --force /tmp/wt-main`).

- **Red on baseline and untouched by the change** → "pre-existing failure": listed in the report, does not block this task.
- **Green on baseline, red after the change** → "new failure": must be fixed; never bypassed.
- When attribution is unclear, treat it as a new failure.

### Step 4: Output the report

```markdown
### Verification Report

- Scope: <derived scopes>
- Executed: <command> → <result> (one line each)
- Not executed: <item> — <reason>
- Pre-existing failures (also red on origin/main): <list or none>
- New failures: <must be empty to pass>
```

## Division of labor vs existing skills

- This skill owns only "how to run verification and attribute results". The development flow lives in `develop-feature`; PR review lives in `analyze-pr` (both reference this skill for their verification step instead of keeping matrix copies).

## Allowed Auto-Actions (No Confirmation Needed)

- All verification commands above (all non-destructive local operations)
- Creating/cleaning temporary worktrees for baseline comparison

## Actions Requiring Confirmation

- None (this skill contains no actions that change remote or commit state)
