# Develop Feature

Execute a development task end-to-end under this repository's rules: feasibility analysis → minimal implementation → verification → PR → self-review → convergent fixes. Applies to fix / feat / refactor / test / chore tasks.

**Source of truth**: repository root `AGENTS.md`. This skill only encodes the process order and repo-specific constraints; if it conflicts with `AGENTS.md`, `AGENTS.md` wins.

## Usage

```text
/develop-feature <task description or plan-document path> [--boundary <allowed file scope>] [--base <baseline branch, default origin/main>]
```

The caller (user or an orchestrating harness prompt) may pre-authorize branch creation / commit / push / PR creation in the invoking instruction; without pre-authorization, each of those actions requires confirmation (see the boundaries at the end). **Merging is never part of this skill under any circumstances.**

## Instructions

All GitHub-facing content (commit messages, PR titles and bodies, comments) must be in English. Commit messages must not include `Co-Authored-By`. Titles must not carry tool/agent attribution prefixes.

### Step 1: Read and sync the baseline

1. Read the task description / plan document; read repository root `AGENTS.md`.
2. Sync the baseline (same safety rules as the analyze-pr skill):

```bash
git status --short
git fetch --all --prune
# Only when the worktree is clean and the current branch can fast-forward:
git pull --ff-only
```

3. Determine the task type (fix/feat/refactor/docs/chore/test) and change boundary (Backend / API / Web / Desktop / Workflow / Docs / AI assets). Check whether the task touches a high-risk area (config semantics, API/Schema, data-source fallback, report structure, authentication, scheduling, release process, desktop startup path) — if so, call out the impact surface separately in the delivery notes.

### Step 2: Feasibility analysis (hard gate, before any change)

Verify every factual claim in the plan against the real code (file existence, current behavior, contracts). When the plan conflicts with the code, the runnable code is authoritative. Produce one of three conclusions and record it (it goes into the PR body's Feasibility section):

- **Feasible**: execute as planned.
- **Needs adjustment**: list each adjustment with code evidence; adjustments must stay inside the given file boundary.
- **Infeasible**: state the evidence, stop implementing, deliver the analysis report only.

For defect tasks whose plan requires reproduction first: reproduce before touching code. Failure to reproduce is handled as "needs adjustment" or "infeasible" — never skip reproduction and patch anyway.

### Step 3: Minimal implementation

1. Make only the smallest change directly required by the task; no drive-by refactors, copy edits, or dependency bumps.
2. If a file boundary was given (`--boundary`), stop at the boundary: when the root cause lies outside it, produce a diagnostic report (symptom / evidence / suggested owner) instead of crossing.
3. Repo-specific constraints:
   - Reuse existing modules, config entries, scripts, and tests; do not add parallel implementations.
   - New config options must update `.env.example` and relevant docs.
   - User-visible changes must update the relevant docs and `docs/CHANGELOG.md` (`[Unreleased]`, one flat line `- [Type] Description`, in English, no subheadings).
   - Web copy i18n: prefer reusing existing keys; a new key requires en/zh source entries plus all locale bundles, then `npm run i18n:resources -- --write`.
   - Never hardcode secrets, accounts, paths, model names, or ports.

### Step 4: Verification

Run the `/run-verification` matrix (commands selected by change scope; red tests must be attributed against the origin/main baseline as pre-existing vs newly introduced). Do not proceed while verification fails; anything unverifiable goes into the delivery notes under "Not executed" with the reason.

### Step 5: Commit and PR (requires authorization)

1. Commit messages: English `<type>: <summary>`; no `Co-Authored-By`; do not trigger auto-tagging (no `#patch/#minor/#major`).
2. PR: `gh pr create --base main`, body per `.github/PULL_REQUEST_TEMPLATE.md`, and it must include:
   - What changed / Why
   - Feasibility analysis (Step 2 conclusion and adjustments)
   - Verification status (each command + result) and Unverified items (including the list of pre-existing red tests on main, if applicable)
   - Risk points / Rollback method
   - Before/after screenshots for UI or report changes (hard repo rule; screenshots go in the PR, never into the repo).

### Step 6: Self-review and convergent fixes

1. Review your own PR using the `/analyze-pr` order: necessity → relevance → title → description completeness → verification evidence → implementation correctness.
2. Check the task plan's acceptance criteria item by item; check for out-of-boundary files (`git diff --stat` against the boundary).
3. Fixes follow `AGENTS.md` §8.1: no point patches — converge every path governed by the same business semantics (runtime / API / Web / CLI / docs / tests); re-run Step 4 after each fix round; iterate until a review round yields zero new findings.
4. After fixing, update the PR body so it matches the final diff (a body inconsistent with the diff is an explicitly listed low-quality-PR trait in this repo).

### Step 7: Delivery notes

Output per `AGENTS.md` §9: What was changed / Why / Verification status / Unverified items / Risk points / Rollback method.

### Step 8: External review feedback (later rounds)

When maintainer/review feedback arrives on the PR after this loop completes, do not point-patch the named lines — run `/handle-review-feedback <pr_number>`, which encodes the `AGENTS.md` §8.1 convergence process.

## Division of labor vs existing skills

- `analyze-issue`: evaluates an existing issue; this skill consumes its conclusions as task input.
- `fix-issue`: single-issue fix workflow; this skill is its superset (adds the feasibility gate, boundary circuit-breaker, and the review-fix loop). Prefer this skill for tasks that come with a plan document.
- `analyze-pr`: PR review; Step 6 reuses its review order rather than redefining review standards.

## Allowed Auto-Actions (No Confirmation Needed)

- Reading code, feasibility analysis, reproducing defects
- `git fetch --all --prune`; `git pull --ff-only` when the worktree is clean and fast-forwardable
- Minimal local changes directly tied to the task, and non-destructive verification

## Actions Requiring Confirmation (unless pre-authorized by the invoking instruction)

1. Creating/switching branches
2. `git commit`
3. `git push`
4. Creating a PR

## Never (even if asked)

- Merging PRs / enabling auto-merge
- `git push --force` to shared branches, or modifying someone else's branch
- Claiming completion while bypassing failed verification
