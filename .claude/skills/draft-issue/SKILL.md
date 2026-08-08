# Draft Issue

Draft a high-quality issue in this repository's style: dedupe first, then structure as "background evidence → proposal → boundaries → acceptance", producing an English body plus label suggestions. Produces a draft only by default; publishing requires confirmation.

**Repository**: https://github.com/SiinXu/stock-pulse-ai/issues

## Usage

```text
/draft-issue <one-line problem/idea description> [--type bug|feature|design|docs|chore]
```

## Instructions

**Issue titles and bodies published to GitHub must be in English.**

### Step 1: Dedupe and relate

```bash
gh issue list --repo SiinXu/stock-pulse-ai --state open --search "<keywords>" --limit 20
gh issue list --repo SiinXu/stock-pulse-ai --state closed --search "<keywords>" --limit 10
```

- An open issue already covers the topic → recommend commenting there instead of opening a new issue; output the comment draft and stop.
- Related but distinct → continue drafting, reference it as `#<number>` in the body, and state the difference explicitly.

### Step 2: Verify the evidence

Every factual claim in the body needs a source:

- Bug: reproduction steps and the actual code location (`file:line` or function name). No "seems broken / probably broken". If it cannot be reproduced, say so and state what the claim is based on.
- Feature/design: describe the current state (where the existing implementation lives, what is missing), citing relevant docs (`docs/*.md`) or existing issues.
- Never invent config names, filenames, or API fields — verify every name exists in the repository.

### Step 3: Compose (English body skeleton)

```markdown
## Summary
<one paragraph: what the problem/request is, who is affected>

## Background / Evidence
<current state and evidence: repro steps, code locations, audit references; for bugs, actual vs expected behavior>

## Proposal
<direction, in steps; state explicitly which existing modules are reused — no parallel implementations>

### Non-goals
<what is explicitly out of scope, to prevent scope creep>

## Scope / Boundaries
<directories/file domains involved; whether high-risk areas are touched (config semantics, API/Schema, data-source fallback, report structure, auth, scheduling, release, desktop startup)>

## Acceptance Criteria
<decidable items (commands, numbers, allow/deny lists), each individually checkable>

## Related
<#issue references and how they relate>
```

- Title: English, describes the actual change (`fix:` / `feat:` / `design:` prefix style consistent with the repo), no tool/agent attribution.
- Splitting: if the proposal contains more than two independent deliverables, recommend splitting into multiple issues with a split proposal instead of one mega-issue.

### Step 4: Label suggestions

Check existing labels (`gh label list --repo SiinXu/stock-pulse-ai --limit 100`) and suggest a set: type (`bug`/`enhancement`/`documentation`) + domain (`web`/`desktop`/`data-source`/`agent`/`i18n`/`security` — only ones that actually exist) + priority (`P0`–`P3`, only with explicit justification). Do not suggest creating new labels.

### Step 5: Deliver

Output: English issue title + body + label suggestions + dedupe conclusion.

## Division of labor vs existing skills

- `analyze-issue`: evaluates an **existing** issue (validity, priority, fix entry point); this skill covers drafting and dedupe **before creation**. Both share the same quality bar: verifiable evidence, decidable acceptance criteria.

## Allowed Auto-Actions (No Confirmation Needed)

- Read-only queries such as `gh issue list` / `gh label list`
- Reading code to verify evidence; writing local drafts

## Actions Requiring Confirmation

1. `gh issue create` (publishing the issue)
2. Commenting on an existing issue
