# Hard Rules From Recent Practice

Shared process constraints for repository skills. Source of truth remains repository-root `AGENTS.md`; this file only operationalizes recurring failure modes from multi-agent delivery and merge trains.

Skills that claim completion, recommend merge, or wire user-visible capabilities must apply the rules that match their step.

## 1. Squash body check (squash commit / PR body hygiene)

Before recommending merge, updating a PR body after force-push/amend, or drafting a squash commit message:

1. Diff the final head against the merge base:

```bash
BASE_REF=$(git merge-base HEAD origin/main)
git diff --stat "$BASE_REF"..HEAD
git diff --name-only "$BASE_REF"..HEAD
```

2. Re-read the PR title and body (or intended squash subject/body). They must describe **this head**, not an earlier WIP snapshot.
3. Fail the check (block "ready to merge" / rewrite the body) when any of the following hold:
   - Body file list or "What Changed" claims files that are not in the final diff
   - Acceptance or verification claims are not supported by commands actually run on this head
   - Title has a tool/agent prefix (`[codex]`, `codex`, `autocode`, `copilot`, …)
   - Commit/squash message is not English, or includes `Co-Authored-By`
   - Visual evidence is missing while the diff touches report rendering or Web UI
4. After any amend, rebase, or review-fix round that changes the tree, re-run this check and update the PR body so it matches the head (body/diff mismatch is an explicit low-quality-PR trait in `AGENTS.md` §8.1).

## 2. Config registry guard

Any change that adds or renames a documented environment key, Settings field, or config default must keep the three-way contract:

| Surface | Location |
|---------|----------|
| Documented env | `.env.example` |
| Registry metadata | `src/core/config_registry_parts/` (via `src.core.config_registry`) |
| Bilingual inventory | `docs/environment-variables.md` / `docs/environment-variables_EN.md` |

Required checks (run and record results):

```bash
python scripts/check_config_doc_consistency.py
python -m pytest tests/core/test_env_example_config_registry_guard.py -q
```

Hard prohibitions (do not use these to green CI):

- Expanding `TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_BASELINE` for a **new** key
- Raising `TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_MAX_COUNT` / `HARD_CEILING`
- Rewriting `BASELINE_SHA256` instead of registering the key

Also update Settings help / i18n titles when the field is user-visible, and add a flat `[Unreleased]` line to `docs/CHANGELOG.md` when the change is user-visible (`- [Type] Description` with English `Added`/`Changed`/`Fixed`/`Docs`/`Tests`/`Chore` — no `###` subheadings).

See also: `docs/CONTRIBUTING_EN.md`, issue #1023, `tests/core/test_env_example_config_registry_guard.py`.

## 3. Reachability grep criteria

**File existence is not delivery.** Claiming a capability is "done", "wired", "user-reachable", or "production-ready" requires a production entry chain:

1. Implementation exists (service/API/component), **and**
2. A normal user can discover it (route **or** navigation **or** in-page mount from a shipped host), **and**
3. A live non-test production caller imports/mounts it.

Audit method (adjust symbols/paths to the change):

```bash
# Production references only — exclude tests, playground, and generated noise
rg -n "ComponentName|api/moduleName|service_function" apps/dsa-web/src src \
  --glob '!**/*test*' \
  --glob '!**/*.test.*' \
  --glob '!**/*.spec.*' \
  --glob '!**/playground/**' \
  --glob '!**/__tests__/**' \
  --glob '!**/generated/**'
```

Classification:

| Result | Conclusion |
|--------|------------|
| Only playground / unit tests / barrels | **Unreachable** — do not claim delivered |
| Route registered but no nav/overview entry | **URL-only** — say so; usually Remaining unless product accepts URL-only |
| Host page imports panel + API client used | **Reachable** — evidence is the import path + optional integration test |
| Backend-only with explicit "Web OOS" in the issue/PR | Not an accidental bug; list under Remaining or Non-goals |

Cross-check against issue #1008 audit rules when mounting deferred UI foundations.

## 4. Delivered / Remaining comment format

When posting an English completion or progress comment on an issue or PR (requires confirmation unless pre-authorized):

```markdown
## Delivered
- <acceptance item or slice>: <evidence — PR link, `path` / symbol, command + result>

## Remaining
- <item>: <why deferred, owner, or follow-up issue>
- (none) — only when the scoped acceptance criteria are fully closed

## Verification
- `<command>` → <result>
- Not run: <item> — <reason>
```

Rules:

- Every Delivered bullet needs evidence, not restated intent.
- Do not claim `Fixes`/`Closes` while Remaining still holds in-scope acceptance criteria.
- Soft cross-references (`Refs`) are allowed for partial slices; say partial explicitly.
- Local analysis docs may be Chinese; **GitHub comments stay English**.

## 5. Merge train discipline

Applies when assembling or reviewing a **merge train** / train validation PR (for example `train/YYYYMMDD-NN` and `chore: validate merge train …`).

1. **No product edits on the train branch.** Only merge commits of qualified members (plus unavoidable conflict resolutions documented in the train PR body). Prefer deferring members over editing product code on the train.
2. **Exact baseline and member SHAs** must appear in the train PR body: `main` tip, each member PR number + head SHA, merge order.
3. **Overlap check** before assembly: members should have no pairwise product-file overlap; flat `docs/CHANGELOG.md` `[Unreleased]` lines are the usual allowed shared file.
4. **Defer with reasons** when current-main conflicts are non-trivial or the change is already patch-equivalent on main.
5. **Qualification**: every applicable **required** CI job must succeed. `Cancelled` is not a pass. Do not treat a green subset as train qualification.
6. **Do not merge the validation PR into main as the product delivery.** Member merges (or the documented train landing process) are the product path; the validation PR is evidence.
7. **Authorization**: skills never merge, never enable auto-merge, and never force-push shared train branches without explicit human confirmation.

Workers delivering a single feature PR are not train conductors: keep the feature PR self-contained, avoid claiming train slots, and leave train assembly to the authorized process.
