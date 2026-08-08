# Handle Review Feedback

Process external review feedback on your own open PR following `AGENTS.md` §8.1: converge the full business contract behind each finding instead of stacking point patches at the named lines. This repository explicitly treats patch stacking as a low-quality-PR trait and grounds for close-and-redo.

**Source of truth**: repository root `AGENTS.md` §8.1. If this skill drifts from it, `AGENTS.md` wins.

## Usage

```text
/handle-review-feedback <pr_number>
```

## Instructions

All GitHub-facing replies must be in English.

### Step 1: Collect the feedback

```bash
gh pr view <pr_number> --repo SiinXu/stock-pulse-ai --comments
gh api repos/SiinXu/stock-pulse-ai/pulls/<pr_number>/comments   # inline review threads
gh pr checks <pr_number> --repo SiinXu/stock-pulse-ai
```

List every distinct issue the reviewer raised — including ones phrased as questions. Do not silently drop any item.

### Step 2: Root-cause each item

For each issue, explain the root cause at the semantic level, not merely which lines will change. If the reviewer gave a counterexample, reproduce it first.

### Step 3: Map the full semantic surface

For each root cause, identify **every** path governed by the same business semantics: runtime, API/Web, CLI, diagnostics, workflows, docs, tests. The reviewer pointing at one location never means only that location is affected.

### Step 4: Fix the complete contract

Implement the convergent fix across the mapped surface. Forbidden moves (each is an explicitly listed low-quality pattern in this repo):

- Fixing only the commented line while sibling paths keep the old semantics
- Masking unclear contracts with broad fallback, silent degradation, or `return False/None/[]`
- Mocking away the actual risk layer so tests prove only a local detail
- Weakening or deleting a failing assertion to get green

### Step 5: Regression coverage

Add a test (or final-entry validation) for the reviewer's counterexample. If it genuinely cannot be verified, state why explicitly in the PR — do not stay silent.

### Step 6: Re-verify and sync the PR body

1. Re-run the full `/run-verification` matrix for the change scope.
2. Update the PR body so scope, verification results, compatibility notes, risks, and rollback plan match the current head. CI passing does not by itself close a reviewer's counterexample — say explicitly how each one was closed.

### Step 7: Respond

Draft an English reply per review thread stating root cause → full surface converged → regression coverage added. Post replies only with confirmation (or when the invoking instruction pre-authorized PR interactions).

### Step 8: When convergence is not achievable

If the feedback reveals the PR's scope is wrong (needs splitting, or close-and-redo), say so explicitly and propose it — do not keep stacking patches and do not claim ready-for-merge. This is the outcome `AGENTS.md` §8.1 mandates over point-by-point patching.

## Division of labor vs existing skills

- `analyze-pr`: reviewing **someone else's** PR (or producing a review verdict).
- `develop-feature` Step 6: **self**-review before external review exists.
- This skill: responding to **external** feedback on **your own** PR after it is open.

## Allowed Auto-Actions (No Confirmation Needed)

- Reading PR comments, threads, and CI results
- Reproducing counterexamples; local fixes and verification on your own branch

## Actions Requiring Confirmation (unless pre-authorized)

1. Pushing fix commits to the PR branch
2. Posting replies to review threads
3. Editing the PR body

## Never (even if asked)

- Marking threads resolved without a semantic fix or an explicit disagreement rationale
- Claiming all feedback is addressed while any item from Step 1 is unhandled
