---
name: pr-template-fill
description: Generate an English GitHub PR body from the current diff and linked issue using .github/PULL_REQUEST_TEMPLATE.md sections — motivation, scope, verification, docs, screenshots policy, risks, rollback. Use when opening or refreshing a PR description.
---

# PR Template Fill

Fill the repository pull request template from the actual diff and issue evidence. Output is English only for anything posted to GitHub.

**Source of truth**: `.github/PULL_REQUEST_TEMPLATE.md` and `AGENTS.md`. Hard rules: `.claude/skills/references/hard-rules.md` §1 and §4.

## Usage

```text
/pr-template-fill [--issue <n>] [--base origin/main]
```

## Instructions

### Step 1: Collect facts

```bash
BASE_REF=$(git merge-base HEAD origin/main)
git diff --stat "$BASE_REF"..HEAD
git diff --name-only "$BASE_REF"..HEAD
gh issue view <n> --repo SiinXu/stock-pulse-ai
```

Verify every filename, config key, and command against the repository.

### Step 2: Fill every template section (English)

1. PR Type
2. Background And Problem
3. Scope Of Change (complete file list from final diff)
4. Issue Link (`Fixes` only when acceptance fully met; else `Refs`)
5. Feasibility (when using develop-feature)
6. Verification Commands And Results (real commands for this head)
7. Visual Evidence (report/UI; never commit screenshots)
8. Compatibility And Risk
9. Rollback Plan

Title: English `<type>: <change summary>` without tool/agent prefixes.

### Step 3: Squash body check

Apply hard-rules §1 before delivery.

### Step 4: Config / registry extras

If env keys or Settings fields are added, state registry + `.env.example` + inventory updates and list hard-rules §2 commands.

### Step 5: Deliver

Default: print English PR body. Creating/editing the PR requires confirmation. Never auto-push.

## Division of labor

- `develop-feature` Step 5 uses this shape.
- `analyze-pr` / `review-pr` judge completeness against the same template.

## Never

- Chinese PR titles or bodies
- `Co-Authored-By` in commits
- Secret values in the body
- Auto merge
