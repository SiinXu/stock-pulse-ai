## PR Type

- [ ] fix
- [ ] feat
- [ ] refactor
- [ ] docs
- [ ] chore
- [ ] test
- [ ] ci

## Background And Problem

Describe the problem, its impact, and what triggers it.

## Scope Of Change

List every module and file included in the actual diff. Include the total file count so the description stays aligned with the implementation.

If this PR changes collaboration or governance files such as `.github/PULL_REQUEST_TEMPLATE.md`, `.github/copilot-instructions.md`, `AGENTS.md`, `.github/instructions/**`, or `.claude/skills/**`, explain the reason, impact, and rollback path in the relevant sections below.

Useful baseline commands:

```bash
BASE_REF=$(git merge-base HEAD origin/main)
git diff --stat "$BASE_REF"..HEAD
git diff --name-only "$BASE_REF"..HEAD
```

- Total files and line changes:
- Complete file list:
- Documentation files updated (`docs/**`):

## Issue Link

Provide one of the following:

- `Fixes #<issue_number>`
- `Refs #<issue_number>`
- If there is no issue, explain the motivation and acceptance criteria

## Verification Commands And Results

Paste the commands you actually ran and their key results. Do not write only "tested."

```bash
# Example
./scripts/ci_gate.sh
python -m pytest -m "not network"
```

The full-suite note must match the current PR head. If a local environment produces different results, label them as local environment differences and include the corresponding GitHub CI result and link. Remove historical failure notes that do not apply to the current head.

Record each applicable check with its actual result and link:

- `ai-governance`: pass / fail / not applicable, link:
- `backend-gate`: pass / fail / not applicable, link:
- `docker-build`: pass / fail / not applicable, link:
- `web-gate`: pass / fail / not applicable, link:
- Full-suite note:
- Key output and conclusion:

If this PR changes a PR template or another contribution workflow file, state why the change is necessary, define its impact boundary, and provide a rollback path. Prefer a separate `chore` PR when the governance change is unrelated to the implementation.

## Visual Evidence (If Applicable)

If this PR changes report formatting, report rendering, or the Web UI, attach screenshots of every affected report or page. Include before-and-after evidence when it helps reviewers understand the change.

Keep issue/PR process screenshots, review screenshots, one-off acceptance screenshots, and temporary evidence in the PR body, PR comments, GitHub attachments, Actions artifacts, or an externally accessible link. Do not commit them as repository files.

When screenshots are unavailable, provide reproducible alternative evidence with the exact command and artifact path. For Web settings or report-rendering changes, the evidence must visibly identify the changed fields, labels, help text, or rendered output.

- Screenshot links:
- Before and after:
- Reproduction command:
- Artifact path:
- Reason screenshots are not applicable or available:

Example settings-page evidence:

```bash
cd apps/dsa-web
npx playwright test e2e/smoke.spec.ts --grep "settings page"
```

Expected artifact pattern: `apps/dsa-web/test-results/**/smoke-settings-page-*.png`

## Compatibility And Risk

Describe compatibility impact and potential risks. Write `None` when there are none.

- For changes to third-party model/API compatibility, request parameters, routing prefixes, or provider fallback behavior, include an official source link or announcement. State whether the constraint is permanent, runtime-specific, or a temporary workaround, and identify the regression and rollback paths.
- If provider/model/base URL behavior and runtime configuration save, cleanup, migration, and backfill semantics are unchanged, state: `This PR does not change provider/model/base URL behavior or runtime configuration cleanup/migration semantics. Existing configuration remains unchanged. Rollback: revert this PR.`
- If this PR changes `.github/PULL_REQUEST_TEMPLATE.md` or another PR workflow file, state that it affects contribution governance only, does not change runtime behavior, can be rolled back by reverting the PR, and note any impact on automated submissions.
- If the change depends on a specific runtime or dependency window, such as a LiteLLM version range, OpenAI-compatible routing, or YAML alias behavior, state the verified compatibility range and covered paths.
- If the change touches runtime configuration save, cleanup, migration, or backfill logic, explain whether existing configuration is rewritten, cleared, migrated, or preserved, and how users can restore the previous behavior.

## Rollback Plan

Provide at least one actionable rollback step. For compatibility fixes, include the minimal rollback path, such as `revert this PR`, and say whether configuration or data also needs to be restored.

## EXTRACT_PROMPT Change (If Applicable)

If this PR changes `EXTRACT_PROMPT` in `src/services/image_stock_extractor.py`, paste the complete updated prompt here.

<details>
<summary>Expand the complete EXTRACT_PROMPT</summary>

```
(paste the complete prompt here)
```

</details>

## Checklist

- [ ] This PR has a clear motivation and business value
- [ ] The scope matches the complete diff
- [ ] Reproducible verification commands and results are included
- [ ] Compatibility and risk have been assessed
- [ ] An actionable rollback plan is included
- [ ] User-visible changes are documented in the relevant docs and `docs/CHANGELOG.md`; `README.md` is updated only for homepage-level changes
- [ ] Report or Web UI changes include affected page/report screenshots or reproducible alternative visual evidence
- [ ] Web settings changes include evidence that visibly identifies the changed fields, labels, and help text
