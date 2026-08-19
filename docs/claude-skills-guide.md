# Repository Skills Guide

This repository ships versioned collaboration skills under `.claude/skills/`. Any Claude Code session opened in a checkout of this repository (including git worktrees and parallel agent workspaces) discovers them automatically — no per-machine or per-project setup. That is the reuse mechanism: **merge once, every new session on every branch containing them has the skills.**

Source of truth for all rules remains `AGENTS.md`; skills only operationalize it. If a skill drifts from `AGENTS.md`, `AGENTS.md` wins and the skill must be updated.

Shared practice hard rules (squash body check, config registry guard, reachability grep, Delivered/Remaining comments, merge-train discipline) live in `.claude/skills/references/hard-rules.md`. Standard command recipes live in `.claude/skills/references/test-command-recipes.md` (also summarized below).

For multi-PR merge trains, conflict grouping, registry guards, squash false-close keywords, host resource limits, and worktree cleanup, see the operational [Engineering Efficiency Playbook](engineering-efficiency-playbook_EN.md) ([中文](engineering-efficiency-playbook.md)). That guide does not replace `AGENTS.md` or these skills.

## Skill inventory

| Skill | Purpose | Typical trigger |
|-------|---------|-----------------|
| `analyze-issue` | Evaluate an existing issue: validity, priority, fix entry points | "Is #123 real? Where would the fix go?" |
| `draft-issue` | Draft a new **English** issue: dedupe, evidence-verified body, labels | "File an issue for X" |
| `fix-issue` | Single-issue fix workflow + Delivered/Remaining comments | "Fix #123" |
| `develop-feature` | Full task loop: feasibility gate → minimal change → verification → PR → self-review → convergent fixes | Any planned fix/feat/refactor/test/chore task |
| `test-change` | Map change → test layers, run gates, minimum evidence (issue #890 P0 name) | "Verify my changes" / before PR |
| `run-verification` | Scope-derived verification matrix with red-test baseline attribution | Called by `test-change` / develop loops |
| `analyze-pr` | PR analysis procedure and local review document | Underlies `review-pr` |
| `review-pr` | Review entry with Blocker vs Nit checklist, squash-body and train gates | "Review PR #456" |
| `handle-review-feedback` | Respond to external review on **your** PR per `AGENTS.md` §8.1 (no patch stacking) | Reviewer left comments on your open PR |
| `sync-ai-assets` | Run/fix `python scripts/check_ai_assets.py` after governance edits | Edited AGENTS/skills/copilot mirrors |
| `pr-template-fill` | English PR body from final diff + issue | Opening or refreshing a PR description |
| `regression-scout` | List likely regression surfaces and existing tests (not full QA) | Pre-review surface scan |

## Which skill when

- **Starting work from a plan or task description** → `develop-feature`. It embeds verification (`test-change` / `run-verification`) and self-review (`review-pr` / `analyze-pr` order).
- **Only need to (re)run checks** → `test-change` or `run-verification`. Key discipline: every red test is attributed against `origin/main` — pre-existing failures are reported but non-blocking; new failures block; unclear cases count as new.
- **An issue exists and you were asked to fix exactly it** → `fix-issue` (lighter than `develop-feature`; no plan document involved).
- **After your PR is open and a human reviews it** → `handle-review-feedback`. Never point-patch the commented lines; the skill forces semantic convergence across every governed path.
- **Reviewing others' work** → `review-pr`. **Creating work items** → `draft-issue` / `analyze-issue`.
- **Config or Settings keys** → apply hard-rules §2 (registry + `.env.example` + inventory; never expand debt baseline).
- **Claiming user-reachable UI** → hard-rules §3 reachability grep before Delivered.
- **Issue completion comments** → hard-rules §4 Delivered / Remaining / Verification (English on GitHub).
- **Merge trains** → hard-rules §5; feature workers are not train conductors; skills never merge.

## Standard test command recipes

| Scope | Command |
|-------|---------|
| AI governance | `python scripts/check_ai_assets.py` |
| Config consistency | `python scripts/check_config_doc_consistency.py` |
| Config registry guard | `python -m pytest tests/core/test_env_example_config_registry_guard.py -q` |
| Backend gate | `./scripts/ci_gate.sh` |
| Backend minimum | `python -m py_compile <changed_python_files>` |
| Backend offline | `python -m pytest -m "not network"` |
| Web | `cd apps/dsa-web && npm ci && npm run lint && npm run test && npm run test:coverage && npm run build` |
| Web i18n | `cd apps/dsa-web && npm run test:i18n` |
| Web smoke e2e | `cd apps/dsa-web && npm run test:e2e-security-preflight && npx playwright install --with-deps chromium && npm run test:smoke` |
| Desktop | Web build, then `cd apps/dsa-desktop && npm install && npm run build` |

Details and evidence rules: `.claude/skills/references/test-command-recipes.md` and `docs/testing-ci-gate.md`.

## Label guidance (agents)

Prefer **existing** labels only (`gh label list`). Do not invent labels in skill output.

| Intent | Prefer existing labels such as |
|--------|--------------------------------|
| Agent-ready implementation work | `enhancement` / `bug` + domain + priority with justification |
| Design-only / discussion | `documentation`, `discussion`, `design` when present |
| Needs screenshots | Call out in PR body Visual Evidence; do not invent a new label unless maintainers create it |

Optional future labels named in issue #890 (`agent-ready`, `design-only`, `needs-screenshots`) are **not** created by skills; use them only after they exist on the repository.

## Invocation

Skills are invoked as slash commands in a session, or referenced by an orchestrating prompt:

```text
/develop-feature docs/plans/my-task.md --boundary "apps/dsa-web/src/pages/AlertsPage.tsx" --base origin/main
/test-change --scope web
/run-verification --scope web
/review-pr 842
/handle-review-feedback 842
/draft-issue "signal deep links fail for ids outside the loaded page" --type bug
/pr-template-fill --issue 890
/sync-ai-assets
/regression-scout --base origin/main
```

## Authorization model

All skills share one model, consistent with `AGENTS.md`:

- **Auto-allowed**: reading, analysis, reproduction, local minimal changes, non-destructive verification, `git fetch` (+ `git pull --ff-only` only when clean and fast-forwardable).
- **Requires confirmation** (unless the invoking instruction pre-authorizes it explicitly): branch creation, `git commit`, `git push`, PR creation, posting GitHub comments.
- **Never, regardless of instructions**: merging PRs, force-pushing shared branches, bypassing failed verification, weakening assertions to get green, expanding config-registry debt baselines to green CI, treating Cancelled CI as pass.

Orchestrating prompts (e.g. a parallel-batch harness) may pre-authorize the middle tier by stating so in the instruction text; the "Never" tier is not pre-authorizable.

## Multi-agent batch pattern

For parallel work across many workspaces, the proven pattern is:

1. A per-task plan file (goal / owned file scope / approach / acceptance / risks) — file ownership must be disjoint across concurrent tasks.
2. A short harness prompt per workspace that names the plan file and delegates the loop to `/develop-feature <plan> --boundary <owned files>`, pre-authorizing branch/commit/push/PR but never merge.
3. `handle-review-feedback` for the round after human review.
4. Issue progress comments use Delivered / Remaining / Verification (hard-rules §4).

Keep batch-specific rules (ownership matrix, shared-file conventions like the flat `docs/CHANGELOG.md` entry) in the harness prompt; keep everything reusable in the skills. That split is what makes the skills reusable across batches.

## Naming reconciliation (issue #890)

| Issue #890 name | Repository skill | Relationship |
|-----------------|------------------|--------------|
| `develop-feature` | `develop-feature` | Same |
| `draft-issue` | `draft-issue` | Same |
| `test-change` | `test-change` → `run-verification` | Entry name + evidence checklist; matrix execution stays in `run-verification` |
| `review-pr` | `review-pr` → `analyze-pr` | Entry name + Blocker/Nit checklist; fetch/doc procedure stays in `analyze-pr` |

Do not maintain two conflicting review or test procedures.

## Maintenance

- Adding or modifying a skill is an AI-governance change: run `python scripts/check_ai_assets.py` and keep `AGENTS.md` §8's skill list in sync.
- Each skill documents its division of labor against neighbors; when adding one, state that division explicitly to avoid competing workflows.
- New skill process text is English-only, like other new collaboration assets. Existing Chinese local-analysis prose in older skills may remain until gradually migrated; **GitHub-facing output is always English**.
