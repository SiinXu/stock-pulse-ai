---
name: review-pr
description: Review a GitHub pull request for this repository with a blocking-vs-nit checklist covering correctness, security, foundation/product boundaries, i18n, tokens, config dual-sources, reachability, squash-body hygiene, and AGENTS compliance. Use when reviewing a PR or producing a merge verdict.
---

# Review PR

P0 review skill for this repository (issue #890). Produces a structured verdict: summary, blockers, nits, test gaps. **Does not merge.**

**Source of truth**: repository root `AGENTS.md`. Detailed fetch/sync/output procedure is implemented by `/analyze-pr`; this skill is the issue-named entry point and the expanded approve checklist. Hard rules: `.claude/skills/references/hard-rules.md`.

## Usage

```text
/review-pr <pr_number>
```

## Instructions

### Step 1: Run the analyze-pr procedure

Execute `/analyze-pr <pr_number>` Steps 1–5. Save the analysis document under `.claude/reviews/prs/pr-<number>.md`.

All GitHub-facing review text must be **English**. Local analysis docs may be Chinese.

### Step 2: Blocking vs nit checklist

Mark each item **Blocker**, **Nit**, or **N/A** with evidence.

| Area | Blocker examples | Nit examples |
|------|------------------|--------------|
| Correctness | Wrong behavior, broken fallback, silent exception swallow on critical path | Naming, comment typos |
| Security | Secrets in diff, auth bypass, unsafe defaults | Extra logging noise |
| Foundation vs product | Product inventing parallel IA that conflicts with foundation designs (#864–#889) | Doc cross-link polish |
| Config | New dual config sources; **new `.env.example` key without registry** (hard-rules §2) | Help text wording |
| i18n high-risk | User-visible string only in one locale | Unused key cleanup |
| Tokens / raw color | New page-private color tokens bypassing theme contract | Minor spacing |
| Reachability | Claims "user-reachable" without production mount (hard-rules §3) | Playground-only when Web OOS is explicit |
| AGENTS compliance | Auto-push instructions, Chinese GitHub body, screenshots committed to repo | Title type preference only |
| Squash / body hygiene | Body/diff mismatch; missing rollback; missing verification on this head (hard-rules §1) | Extra detail in scope list |
| Tests | No evidence on risk path; weakened assertions | Missing optional e2e when unit covers contract |
| Train PRs | Product edits on train branch; Cancelled treated as pass (hard-rules §5) | Extra deferred-member commentary |

### Step 3: UI / report evidence

If the PR changes report format, report rendering, or Web UI: require screenshots or stated alternative visual evidence in the PR (not in the repo). Missing evidence is a **blocker**.

### Step 4: Output format

```markdown
# PR #<number> Review

## Summary
## Blockers
## Nits
## Test gaps
## Squash body check
## Merge recommendation
- request changes / approve with nits / approve
- Never merge from this skill
```

## Division of labor

- `analyze-pr`: full read-only analysis procedure and document template.
- `review-pr`: issue #890 entry name + blocking/nit checklist + squash-body and train gates.
- `handle-review-feedback`: for authors responding to feedback on **their** PR.

## Allowed Auto-Actions

Same as `analyze-pr`.

## Actions Requiring Confirmation

1. Publish review comment
2. Approve / request changes
3. Merge (normally **refuse**)
