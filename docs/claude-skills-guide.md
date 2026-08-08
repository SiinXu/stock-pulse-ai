# Repository Skills Guide

This repository ships versioned collaboration skills under `.claude/skills/`. Any Claude Code session opened in a checkout of this repository (including git worktrees and parallel agent workspaces) discovers them automatically — no per-machine or per-project setup. That is the reuse mechanism: **merge once, every new session on every branch containing them has the skills.**

Source of truth for all rules remains `AGENTS.md`; skills only operationalize it. If a skill drifts from `AGENTS.md`, `AGENTS.md` wins and the skill must be updated.

## Skill inventory

| Skill | Purpose | Typical trigger |
|-------|---------|-----------------|
| `analyze-issue` | Evaluate an existing issue: validity, priority, fix entry points | "Is #123 real? Where would the fix go?" |
| `draft-issue` | Draft a new issue: dedupe, evidence-verified body, labels | "File an issue for X" |
| `fix-issue` | Single-issue fix workflow | "Fix #123" |
| `develop-feature` | Full task loop: feasibility gate → minimal change → verification → PR → self-review → convergent fixes | Any planned fix/feat/refactor/test/chore task |
| `run-verification` | Scope-derived verification matrix with red-test baseline attribution | "Verify my changes" / called by other skills |
| `analyze-pr` | Review someone's PR (necessity → relevance → title → description → evidence → correctness) | "Review PR #456" |
| `handle-review-feedback` | Respond to external review feedback on your own PR per `AGENTS.md` §8.1 (no patch stacking) | Reviewer left comments on your open PR |

## Which skill when

- **Starting work from a plan or task description** → `develop-feature`. It embeds `run-verification` (Step 4) and the `analyze-pr` review order for self-review (Step 6), so you rarely invoke those separately.
- **Only need to (re)run checks** → `run-verification`. Its key discipline: every red test is attributed against `origin/main` — pre-existing failures are reported but non-blocking; new failures block; unclear cases count as new.
- **An issue exists and you were asked to fix exactly it** → `fix-issue` (lighter than `develop-feature`; no plan document involved).
- **After your PR is open and a human reviews it** → `handle-review-feedback`. Never point-patch the commented lines; the skill forces semantic convergence across every governed path.
- **Reviewing others' work** → `analyze-pr`. **Creating work items** → `draft-issue` / `analyze-issue`.

## Invocation

Skills are invoked as slash commands in a session, or referenced by an orchestrating prompt:

```text
/develop-feature docs/plans/my-task.md --boundary "apps/dsa-web/src/pages/AlertsPage.tsx" --base origin/main
/run-verification --scope web
/handle-review-feedback 842
/draft-issue "signal deep links fail for ids outside the loaded page" --type bug
```

## Authorization model

All skills share one model, consistent with `AGENTS.md`:

- **Auto-allowed**: reading, analysis, reproduction, local minimal changes, non-destructive verification, `git fetch` (+ `git pull --ff-only` only when clean and fast-forwardable).
- **Requires confirmation** (unless the invoking instruction pre-authorizes it explicitly): branch creation, `git commit`, `git push`, PR creation, posting GitHub comments.
- **Never, regardless of instructions**: merging PRs, force-pushing shared branches, bypassing failed verification, weakening assertions to get green.

Orchestrating prompts (e.g. a parallel-batch harness) may pre-authorize the middle tier by stating so in the instruction text; the "Never" tier is not pre-authorizable.

## Multi-agent batch pattern

For parallel work across many workspaces, the proven pattern is:

1. A per-task plan file (goal / owned file scope / approach / acceptance / risks) — file ownership must be disjoint across concurrent tasks.
2. A short harness prompt per workspace that names the plan file and delegates the loop to `/develop-feature <plan> --boundary <owned files>`, pre-authorizing branch/commit/push/PR but never merge.
3. `handle-review-feedback` for the round after human review.

Keep batch-specific rules (ownership matrix, shared-file conventions like the flat `docs/CHANGELOG.md` entry) in the harness prompt; keep everything reusable in the skills. That split is what makes the skills reusable across batches.

## Maintenance

- Adding or modifying a skill is an AI-governance change: run `python scripts/check_ai_assets.py` and keep `AGENTS.md` §8's skill list in sync.
- Each skill documents its division of labor against neighbors; when adding one, state that division explicitly to avoid competing workflows.
- Skills are English-only, like all new collaboration assets in this repository.
