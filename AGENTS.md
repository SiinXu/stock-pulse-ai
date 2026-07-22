# AGENTS.md

This document defines the default development process for this repository. Its purpose is to reduce repeated communication and rework while keeping changes consistent with the current project structure.

If this document conflicts with the repository's scripts, workflows, or current implementation, treat the runnable code as authoritative and update the documentation as part of the relevant change to prevent further drift.

## 1. Hard Rules

- Follow existing directory boundaries:
  - Prefer `src/`, `data_provider/`, `api/`, and `bot/` for backend logic.
  - Make Web frontend changes in `apps/dsa-web/`.
  - Make desktop client changes in `apps/dsa-desktop/`.
  - Make deployment and pipeline changes in `scripts/`, `.github/workflows/`, and `docker/`.
- Do not execute `git commit`, `git tag`, or `git push` without explicit confirmation.
- Commit messages must be written in English and must not include `Co-Authored-By`.
- All GitHub collaboration content must be in English, including Issue / PR titles and bodies, comments, reviews, check / job / step names, step summaries, bot comments, and automated review outputs.
- Do not hardcode secrets, accounts, paths, model names, ports, or environment-specific branching.
- Prioritize reuse of existing modules, configuration entries, scripts, and tests; do not add parallel implementations.
- Stability takes priority over incidental optimization by default. Avoid refactors, abstractions, and infrastructure migrations that are not directly required by the current task.
- When adding configuration options, also update `.env.example` and the relevant documentation.
- Changes to user-visible capabilities, CLI/API behavior, deployment, notifications, or report structure must also update the relevant documentation and `docs/CHANGELOG.md`.
- When modifying report formats, report rendering, or the Web UI, the PR description must include screenshots of the affected reports or pages. Prefer before-and-after comparisons when applicable. If screenshots are unavailable, explain why and provide alternative visual evidence.
- Issue/PR process screenshots, review screenshots, one-time acceptance screenshots, and temporary visual evidence must not be committed to the repository. Put them in PR descriptions, PR comments, GitHub attachments, Actions artifacts, or externally accessible evidence links. Diagrams intentionally maintained as long-term product documentation are exempt, but their filenames and document context must be independent of a specific issue or PR number.
- The `[Unreleased]` section of `docs/CHANGELOG.md` uses a **flat format**: each entry is a separate line formatted as `- [Type] Description`. Allowed `Type` values are `Added`/`Changed`/`Fixed`/`Docs`/`Tests`/`Chore`, and descriptions must be in English. **Do not add `### category headings` within `[Unreleased]`**, to reduce merge conflicts between concurrent PRs. Maintainers will consolidate entries into the categorized release format when publishing a release.
- Keep `README.md` focused on homepage-level information: project positioning, core capabilities, quick start, primary entry points, sponsorship, and collaboration. Avoid unnecessary README updates and continued expansion.
- For detailed module behavior, page interactions, feature-specific configuration, troubleshooting guidance, field contracts, implementation semantics, and boundary conditions, update the corresponding `docs/*.md` or topic document instead of the README.
- When changing either version of bilingual English/Chinese documentation, evaluate whether the other version also needs an update. If it is not updated, explain why in the delivery notes.
- New or modified source code comments, docstrings, and developer logs must use English; gradually migrate untouched historical texts. Localized product text, user notification content, and corresponding language documents can be used in target languages.

## 1.1 PR Title Guidance (Non-Blocking)

- Prefer English PR titles in the form `<type>: <change summary>`, for example `fix: preserve market analysis history`. Preferred types are `fix`/`feat`/`refactor`/`docs`/`chore`/`test`/`ci`.
- Titles should describe the actual change and should not include `[codex]`, `codex`, `autocode`, `copilot`, or another tool/agent attribution prefix.
- This guidance improves consistency and readability but must not be used as the sole review blocker.

## 1.2 Contribution Quality Baseline

- This repository does not accept PRs that replace genuine design convergence with stacking code volume, expanding diff size, or patch-style responses to reviews.
- Judge contribution quality by whether it solves a clear problem, minimizes impact, preserves existing contracts, and covers real risk paths, not by lines added, files changed, feature promotion, or whether it merely "looks complete."
- Do not treat this repository as a low-cost experimentation ground, resume showcase, or contribution farming place. Any PR must demonstrate that the author understands the current system contract and completes basic self-review, integration, and verification.
- Using AI-assisted development is not itself a problem. The problem is submitting AI-generated code without human semantic review, validation, and convergence. Such PRs will be treated as low-quality submissions.
- After receiving review feedback, do not address only the exact locations mentioned. The author must re-check every entry point, configuration, test, document, workflow, and user-visible path governed by the same business semantics.
- If a PR continues to appear with similar contract drift, repeated fallback, bypassing real risk layers, inconsistency between PR body and actual diff after multiple review rounds, maintainers can require it to be closed and reworked instead of continuing point-by-point review.

## 2. AI Collaboration Asset Governance

- `AGENTS.md` is the single source of truth for AI collaboration rules in the repository.
- `CLAUDE.md` must be a symbolic link to `AGENTS.md` for compatibility with the Claude ecosystem.
- `.github/copilot-instructions.md` and `.github/instructions/*.instructions.md` are mirrored or layered supplements for GitHub Copilot / Coding Agent; in case of conflict, refer to `AGENTS.md`.
- Repository collaboration skills are stored in `.claude/skills/`, and analysis artifacts are stored in `.claude/reviews/`. Skills may be committed; review artifacts are local-only by default.
- The root `SKILL.md` and `docs/openclaw-skill-integration.md` are product or external integration documentation, not sources of repository collaboration rules.
- Before adding `.agents/skills/` or another agent-specific directory, define a single source of truth and synchronize mirrors through scripts. Do not maintain multiple equivalent copies by hand over time.
- When modifying AI collaboration governance assets, execute:

```bash
python scripts/check_ai_assets.py
```

## 3. Project Overview

- Project positioning: an intelligent stock analysis system covering A-shares, Hong Kong stocks, and U.S. stocks.
- Main workflow: data fetching -> technical analysis/news retrieval -> LLM analysis -> report generation -> notification push.
- Key entry points:
  - `main.py`: The main entry point for analysis tasks
  - `server.py`: FastAPI service entry point
  - `webui.py`: Retained compatibility launcher for direct FastAPI startup
  - `apps/dsa-web/`: Web frontend
  - `apps/dsa-desktop/`: Electron desktop app
  - `.github/workflows/`: CI, release, and daily tasks
- Core responsibilities:
  - `src/core/`: Main workflow orchestration
  - `src/market/`: Market analysis, context, phase, and structure implementations
  - `src/analysis_context_pack/`: Analysis-context projection and prompt implementations
  - `src/services/`: Business service layer
  - `src/repositories/`: Data access layer
  - `src/schemas/`: Schemas and data structures
  - `data_provider/`: Multi-provider adapters and fallback logic
  - `api/`: FastAPI API
  - `bot/`: Bot integrations
  - `strategies/`: Built-in natural-language trading Skill definitions in YAML
  - `templates/`: Jinja report presentation templates
  - `scripts/`: Local scripts
  - `.github/scripts/`: GitHub automation scripts
  - `tests/`: pytest tests
  - `docs/`: Documentation and guides

## 4. Common commands

### Run the application

```bash
python main.py
python main.py --debug
python main.py --dry-run
python main.py --stocks 600519,hk00700,AAPL
python main.py --market-review
python main.py --schedule
python main.py --serve
python main.py --serve-only
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### Backend validation

```bash
python -m pip install --upgrade --constraint constraints.txt pip
python -m pip install --build-constraint build-constraints.txt -r .github/requirements-ci.txt
python -m pip check
./scripts/ci_gate.sh
python -m pytest -m "not network"
python -m py_compile <changed_python_files>
```

### Web / Desktop

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build

cd ../dsa-desktop
npm install
npm run build
```

### PR / CI evidence

```bash
gh pr view <pr_number>
gh pr checks <pr_number>
gh run view <run_id> --log-failed
```

## 5. Default workflow

1. Determine the task type: `fix / feat / refactor / docs / chore / test / review`.
2. Read the existing implementation, configuration, tests, scripts, workflows, and documentation before making changes.
3. Identify change boundaries: Backend / API / Web / Desktop / Workflow / Docs / AI collaboration assets.
4. Determine whether the task affects a high-risk area: configuration semantics, API / Schema, data source fallback, report structure, authentication, scheduling, release processes, or the desktop startup path.
5. Perform the smallest changes directly related to the current task, avoiding unnecessary refactoring.
6. If documentation, scripts, and workflows disagree, treat the actual code and workflows as authoritative, then decide whether to correct the documentation as part of the task.
7. Execute checks using the verification matrix below after making changes.
8. The final delivery should explicitly state:
   - What was changed
   - Why this change was made
   - Verification status
   - Unverified items
   - Risk points
   - Rollback method

## 6. Verification Matrix

### CI coverage principle

The current repository CI mainly contains:

| Check | Source | Description | Blocking? |
| --- | --- | --- | --- |
| `ai-governance` | `.github/workflows/ci.yml` | Validates `AGENTS.md` / `CLAUDE.md` / `.github` instructions / `.claude/skills` relationships | Yes |
| `backend-gate` | `.github/workflows/ci.yml` | Executes `./scripts/ci_gate.sh` | Yes |
| `docker-build` | `.github/workflows/ci.yml` | Builds the Docker image and smoke-tests imports of key modules | Yes |
| `web-gate` | `.github/workflows/ci.yml` | Executes `npm run lint`, `npm run test`, and `npm run build` during frontend changes | Yes (triggered) |
| `web-e2e` | `.github/workflows/ci.yml` | For frontend changes, starts a real backend, Vite, and local fake model endpoint with an isolated temporary `ENV_FILE`, then runs `npm run test:smoke` (Playwright) | Yes (when triggered) |
| `network-smoke` | `.github/workflows/network-smoke.yml` | `pytest -m network` + `scripts/test.sh quick` | No, observation item |
| `pr-review` | `.github/workflows/pr-review.yml` | PR static check + AI review + automatic tagging | No, auxiliary item |

If there is a corresponding CI result on the existing PR, you can directly quote the CI conclusion; if the CI does not cover the changes or the local environment differs significantly from the CI environment, supplement local verification and gaps.

### Validation By Change Scope

- Python backend changes:
  - Applicable scope: `main.py`, `src/`, `data_provider/`, `api/`, `bot/`, `tests/`
  - Preferred command: `./scripts/ci_gate.sh`
  - Minimum requirement: `python -m py_compile <changed_python_files>`
  - If it affects API, task scheduling, report generation, notification sending, data source fallback, authentication, or scheduling, the delivery instructions should specify whether the corresponding paths are covered.

- Web frontend changes:
  - Applicable scope: `apps/dsa-web/`
  - Default execution: `cd apps/dsa-web && npm ci && npm run lint && npm run build`
  - If the change affects API integration, routing, state management, Markdown/chart rendering, or authentication state, describe the integration surface and any unverified risk in the delivery notes.

- Desktop client changes:
  - Applicable scope: `apps/dsa-desktop/`, `scripts/run-desktop.ps1`, `scripts/build-desktop*.ps1`, `scripts/build-*.sh`, `docs/desktop-package.md`
  - Default execution: First build the Web, then build the desktop client
  - If platform constraints prevent complete verification, explicitly state whether the Web build output, Electron build, and release workflow were verified.

- API / Schema / authentication changes:
  - Applicable scope: `api/**`, `src/schemas/**`, `src/services/**`, `apps/dsa-web/**`, `apps/dsa-desktop/**`
  - Must cover corresponding backend validation + affected client build validation.
  - For changes to login, cookies, sessions, polling state, fields, or enum values, explicitly state the compatibility impact.

- Documentation and governance file changes:
  - Applicable scope: `README.md`, `docs/**`, `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/**`, `.claude/skills/**`
  - Code testing is not enforced.
  - Confirm command, configuration items, filenames, workflow names with the actual repository.
  - When modifying AI collaboration governance assets, execute `python scripts/check_ai_assets.py`.

- Workflow / script / Docker changes:
  - Applicable scope: `.github/**`, `scripts/**`, `docker/**`
  - Run local validation closest to the change scope.
  - State which pipeline, release path, or deployment path is affected in the delivery notes.
  - If Docker / GitHub Actions validation was not executed, clearly state the reason and potential risks.

- Network or third-party dependency changes:
  - First run offline or deterministic checks.
  - Prioritize confirming that timeout, retry, fallback, error messages, and degradation paths still work.
  - If online validation was not executed, clearly state the reason.

## 7. Stability Safeguards

- Configuration and runtime entry points:
  - When modifying `.env` semantics, default values, CLI parameters, service startup methods, or scheduling semantics, evaluate the impact on local runs, Docker, GitHub Actions, API, Web, and Desktop.
  - New configuration should favor "runs without configuration, gains capabilities when configured" to avoid overlapping switches and mutually exclusive modes.

- Data sources and fallback:
  - When modifying `data_provider/`, consider provider priority, failure fallback, field normalization, caching, and timeout strategies.
  - Single data source failure should not halt the entire analysis process unless explicitly required to fail-fast.

- API / Web / Desktop compatibility:
  - When modifying API / Schema / Authentication / report payload, check backend, Web, and Desktop compatibility simultaneously.
  - Default priority is adding fields, preserving old fields, or providing a compatibility layer to avoid silently breaking existing clients.

- Reports, prompts, and notifications:
  - When modifying report structure, prompts, extractors, notification templates, or bot delivery chains, check upstream inputs and downstream consumers for compatibility.
  - A single notification channel failure should not halt the entire analysis workflow unless the requirement explicitly calls for fail-fast behavior.
  - When modifying `EXTRACT_PROMPT` in `src/services/image_stock_extractor.py`, include the complete current prompt in the PR description.

- Workflows, releases, and packaging:
  - When modifying automatic tagging, releases, Docker publishing, daily analysis, or desktop packaging, evaluate trigger conditions, artifact paths, permission boundaries, and rollback methods.
  - Automatic tag defaults to opt-in: Only commit titles containing `#patch`, `#minor`, or `#major` will trigger version number updates unless explicitly required to change the release strategy.

## 8. Issue / PR / Skill workflow

- The repository provides the following skills for preferred reuse:
  - `.claude/skills/analyze-issue/SKILL.md`
  - `.claude/skills/analyze-pr/SKILL.md`
  - `.claude/skills/fix-issue/SKILL.md`
- If the task explicitly involves issue analysis, PR review, or issue resolution, follow the corresponding skill first and save its artifacts to `.claude/reviews/`.
- Commands, templates, validation order, and delivery structure in these skills must remain consistent with `AGENTS.md`.
- Before creating or updating a PR, reviewing a PR, or analyzing an issue, synchronize the latest codebase: first check the workspace status and execute `git fetch --all --prune`; if the workspace is clean and the current branch can be fast-forwarded, execute `git pull --ff-only`. If there are local modifications, conflict states, untracked risk files, or inability to fast-forward, do not forcibly switch branches, stash, reset, or overwrite local status; PR review/issue analysis can use the fetched remote refs/PR head for analysis and clearly record the reason for not updating the local working tree and the current local HEAD with the remote baseline in the analysis document; PR creation/update should first explain the difference between the current branch and the target baseline, and request user confirmation to rebase, merge, or continue based on the current branch.
- Skills should inspect CI and workflow evidence before deciding whether additional local validation is needed.
- Except for the safe fast-forward synchronization described above for PR creation/update, PR review, and issue analysis, skills must not run `git pull`, `git push`, `git tag`, `gh pr create`, or other operations that change remote or current branch state by default. These operations require user confirmation.
- PR review default order:
  1. Necessity
  2. Relevance
  3. Title recommendation (`<type>: <change summary>`, without a tool/agent prefix; not a hard blocker)
  4. Description completeness against `.github/PULL_REQUEST_TEMPLATE.md`
  5. Verification evidence
  6. Implementation correctness
  7. Merge decision
- `fix` PRs must describe the original problem, root cause, fix, and regression risk.
- Merge blocking conditions:
  - Correctness or security issues
  - Blocking CI checks have not passed
  - PR description is substantially inconsistent with the actual code changes
  - Missing rollback plan
  - Repeated unresolved contract drift, patch stacking, or misleading verification evidence

## 8.1 Handling Review Feedback And Prohibiting Patch Stacking

When handling review feedback, do not add local patches only at the lines identified by the reviewer and then claim that everything is fixed. First re-evaluate the business contract behind the feedback, then inspect every entry point, configuration, test, document, workflow, and user-visible path governed by the same semantics.

After receiving review feedback, you must handle it in the following order:

1. List each issue identified by the reviewer.
2. Explain the root cause, not merely which lines changed.
3. Identify every related path governed by the same semantics, such as runtime, API/Web, CLI, diagnostics, workflows, docs, and tests.
4. Fix the complete contract, not only the currently failing test or commented line.
5. Add regression coverage for the reviewer's counterexample through tests or final-entry validation, or clearly explain why it cannot be verified.
6. Update the PR body so its scope, verification results, compatibility, risks, and rollback plan match the current head.

If you cannot complete the above consolidation, do not continue to stack patches, and do not claim ready for merge. You should proactively explain that the current PR needs to be split, closed as a redo, or request maintainers to confirm the new minimum scope.

The following behaviors will be considered low-quality PRs:

- Masking unclear contracts with broad fallback, silent degradation, or `return False/None/[]`.
- Mocking away the actual risk layer so tests prove only a local implementation detail.
- Claim the issue is closed after CI passes but without covering counterexamples pointed out by reviewers.
- The PR body is inconsistent with the actual diff, verification results, or compatibility risks.
- Adding scattered patches after review instead of converging the complete semantics.
- Inconsistent business semantics across runtime, Web/API, docs, workflow, and tests.

CI passing only indicates automated checks passed; it cannot replace manual semantic convergence or independently prove that reviewer-identified counterexamples have been closed.

## 9. Delivery & Release

- Default delivery structure:
  - `What was changed`
  - `Why this change`
  - `Verification status`
  - `Unverified items`
  - `Risk points`
  - `Rollback method`
- If it's a `docs` task, you can write: `Docs only, tests not run`; but still need to explain whether the commands and filenames were verified.
- Automatic tagging does not trigger version updates unless the commit title contains `#patch`, `#minor`, or `#major`.
- Manual tag creation must use annotated tags.
- User-visible changes are prioritized through PR merges and require complete label and validation documentation.
