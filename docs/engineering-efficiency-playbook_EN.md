# Engineering Efficiency Playbook (Operational Guide)

- Status: `Living`
- Issue: [#891](https://github.com/SiinXu/stock-pulse-ai/issues/891)
- Audience: maintainers and agents running parallel fix/merge trains
- Related: [`AGENTS.md`](../AGENTS.md) (contract), [Contributing Guide](CONTRIBUTING_EN.md), [Offline Test Gate](testing-ci-gate.md), [Config inventory](environment-variables_EN.md), [Skills guide](claude-skills-guide.md)
- 中文：[engineering-efficiency-playbook.md](engineering-efficiency-playbook.md)

## 0. Contract vs operations (read first)

| Document | Role | When it wins |
| --- | --- | --- |
| **`AGENTS.md`** | **Contract**: hard rules, ownership boundaries, verification matrix, PR/issue English policy, no silent force-push/merge | Always. If this playbook disagrees with `AGENTS.md`, **follow `AGENTS.md` and fix this playbook**. |
| **This playbook** | **Operations**: how to batch merges, group conflicts, run registry guards, avoid squash false-closes, bound local resources, protect workspaces | Only for execution tactics that do not weaken the contract. |
| **Skills under `.claude/skills/`** | Encode process order; they must stay consistent with `AGENTS.md` | Skills operationalize the contract; they do not replace it. |

Do **not** restate or paste `AGENTS.md` here. Link it. Commands below are operational recipes; required CI names, commit/PR language rules, and confirmation gates (no agent `git push` / merge / force-push without explicit human confirmation) remain those defined in the contract.

---

## 1. Train-batch merges

### When to use

- Many open PRs must land on a moving `main` (feature train, post-audit wiring wave, registry cleanup batches).
- Individual PRs are small enough to rebase, but **all-at-once merge** would thrash CI and force repeated conflict resolution.
- You need a **predictable landing order** so later PRs only rebase once per train slot.

### Operating model

1. **Pick a train window** (hours to one day), not an open-ended "merge everything."
2. **Order by dependency and blast radius**, not PR number:
   - foundations / shared contracts first (schemas, config registry, CI scripts);
   - product mounts and UI wiring second;
   - docs-only and pure tests last when they only document already-landed code.
3. **Batch size**: prefer 3–8 green, rebased PRs per slot. Larger trains need conflict-graph grouping (ch. 2).
4. **One integrator role** (human or single agent): only the integrator merges; workers keep preparing next slots.
5. **After each merge**: wait for required checks on the new `main` head (or the known canary) before starting the next slot's rebases.

### Commands (integrator)

Integrator actions that change remote state (`gh pr merge`, `git push`) require an **explicit human confirmation** for agents — same gate as `AGENTS.md` (agents do not merge or force-push by default). The commands below are the recipe *after* that confirmation.

```bash
git fetch --all --prune
git checkout main
git pull --ff-only origin main

# Inspect open PR readiness (example filters; adjust as needed)
gh pr list --state open --limit 50
gh pr checks <pr_number>
gh pr view <pr_number> --json mergeable,mergeStateStatus,baseRefName,headRefOid,statusCheckRollup

# Before merge: scan for accidental auto-close keywords (ch. 4)
gh pr view <pr_number> --json title,body,commits \
  --jq '{title,body,commits:[.commits[].messageHeadline]}'

# Land one PR only when required checks are green on the **exact** head
# Prefer squash when that is the repo default; keep tracking issues open with Refs (ch. 4)
gh pr merge <pr_number> --squash --delete-branch

# Advance local main and announce the new tip for workers
git pull --ff-only origin main
git rev-parse HEAD
```

Workers refresh against the train tip:

```bash
git fetch origin
git rebase origin/main
# or: merge origin/main into the feature branch when rebase is impractical
# Push only the worker's own topic branch. Never force-push shared branches (main, release/*).
# Agents still need explicit confirmation before any push.
git push --force-with-lease origin HEAD
```

### Counterexamples

| Anti-pattern | Why it hurts |
| --- | --- |
| Merge 20 PRs without reordering or waiting for `main` canary | Cascading red CI; each PR re-fights the same conflicts |
| Parallel integrators merging different PRs simultaneously | Lost races on shared files; "green then red" on `main` |
| Treating "CI was green yesterday" as mergeable today | Stale head; required checks must match **exact head** |
| Closing the whole train issue after one CI slice | Tracking issues stay open until acceptance criteria complete (`Refs` vs `Fixes` — ch. 4) |
| Agents merging or force-pushing without confirmation | Violates the collaboration contract; keep merge/push behind human gates |

---

## 2. Conflict-graph grouping

### When to use

- The open PR set touches overlapping paths (`src/core/config_registry_parts/`, `apps/dsa-web/src/pages/*`, shared i18n JSON, CI workflows).
- You need **parallel prep** without every worker rebasing the same hot files.
- Train order is unclear and "whoever is green first" is too random.

### Method

1. For each candidate PR, list changed paths vs `origin/main`:

```bash
gh pr diff <pr_number> --name-only
# or locally:
git fetch origin pull/<pr_number>/head:pr-<pr_number>
git diff --name-only origin/main...pr-<pr_number>
```

2. Build an undirected **conflict graph**:
   - Node = PR.
   - Edge = non-empty intersection of path sets (or of known hot directories even when filenames differ after rename).
3. **Color / partition** into independent sets (no internal edges). Each set can be prepared in parallel.
4. **Serial chain** inside a connected component: merge high-centrality shared cores first, then leaves.
5. Recompute the graph after every train slot; do not trust yesterday's partition.

### Hot directories (this repo, operational heuristics)

Treat these as high-conflict magnets; co-touching them almost always means serial merge:

- `src/core/config_registry_parts/`, `src/core/config_registry.py`, `.env.example`
- `docs/environment-variables.md`, `docs/environment-variables_EN.md`
- `apps/dsa-web/src/i18n/` (and locale budgets)
- `.github/workflows/ci.yml`, `scripts/ci_gate.sh`, `scripts/ci_select_tests.py`
- Shared shells: `HomePage`, `Settings` routers, navigation registries

### Lightweight path-overlap sketch

```bash
# Write path lists then compute pairwise intersections (example sketch)
for n in 1013 1058 1023; do
  gh pr diff "$n" --name-only | sort -u > "/tmp/pr-${n}.paths"
done
# Intersection size between two PRs:
comm -12 /tmp/pr-1013.paths /tmp/pr-1058.paths | wc -l
```

### Counterexamples

| Anti-pattern | Why it hurts |
| --- | --- |
| Parallel workers all editing the same Settings page "for different issues" | Guaranteed thrash; should be one sequential owner |
| Grouping only by label (`feat`/`fix`) instead of paths | Labels do not predict conflict |
| Freezing a merge order for a multi-day train without refresh | Graph becomes wrong after the first few merges |
| "Resolve by accepting ours/theirs wholesale" on registry or i18n | Silent contract loss; fix content, do not lottery-pick |

---

## 3. Config registration guards

### When to use

- Any PR adds or renames a user-visible / runtime env key.
- A merge train repeatedly breaks Settings (uncategorized keys, wrong controls, missing help).
- CI fails `test_env_example_config_registry_guard` or config inventory checks.

### Contract (do not weaken)

New configuration options must update `.env.example` and relevant docs (`AGENTS.md`). Operationally that means **three sources stay aligned** in the **same** change:

1. `.env.example`
2. `src/core/config_registry_parts/` (registry metadata for Settings UI)
3. `docs/environment-variables.md` + `docs/environment-variables_EN.md`

Canonical deep guide: [Environment variables (EN)](environment-variables_EN.md).

### Commands

```bash
# Three-way consistency (docs / env / registry status)
python scripts/check_config_doc_consistency.py
python scripts/check_config_doc_consistency.py --json

# Optional: treat historical missing-registry debt as hard failure
python scripts/check_config_doc_consistency.py --fail-on all

# Guard tests (no expanding the unregistered baseline to green CI)
python -m pytest tests/core/test_env_example_config_registry_guard.py tests/test_config_registry.py -q
```

### Correct fix path for a new key

1. Add `KEY=` (or commented `# KEY=`) to `.env.example`.
2. Register the field in the appropriate `src/core/config_registry_parts/*` module (type, control, group, help metadata).
3. Update both language inventory tables (or regenerate via the inventory writer if your task already uses it).
4. Run the commands above; fix until green.
5. **Never** expand `TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_BASELINE` / raise the hard ceiling / rewrite the pinned baseline hash to silence CI — register the key instead.

### Counterexamples

| Anti-pattern | Why it hurts |
| --- | --- |
| Ship runtime `os.getenv("NEW_KEY")` only | Settings dump / invisible key / wrong control |
| Document in CN inventory but not EN (or reverse) | `cn_en_mismatch`; bilingual operators diverge |
| Green CI by growing the unregistered debt baseline | Debt ratchets the wrong direction; blocked by design |
| Fix only the failing line after merge without re-checking the three-way script | Same debt reappears on the next train |

---

## 4. Squash false-close issue defense

### When to use

- Default merge style is **squash** (common on this repository).
- Commits or PR bodies contain `Fixes #N` / `Closes #N` / `Resolves #N`.
- Tracking / epic / multi-slice issues (for example #891) must stay open until **full** acceptance criteria land.

### Rules of thumb

| Intent | Use in PR body / commits | Effect on GitHub when squash-merged |
| --- | --- | --- |
| This PR **completes** the issue | `Fixes #N` or `Closes #N` (once, in the PR body preferred) | Issue **closes** |
| This PR is a **slice** of a larger issue | `Refs #N` only | Issue **stays open** |
| Historical linkage without claiming done | `Refs #N` in docs/changelog; avoid close keywords | Issue stays open |

### Pre-merge checklist (integrator)

```bash
# Search the PR for auto-close keywords (title, body, and commits that will squash)
gh pr view <pr_number> --json title,body,commits \
  --jq '{title,body,commits:[.commits[].messageHeadline]}'

# Also scan the full commit messages if needed
gh pr view <pr_number> --json commits --jq '.commits[].messageBody'
```

If a slice PR accidentally contains `Fixes #891` while acceptance criteria remain open:

1. Edit the PR body to `Refs #891` before merge, **or**
2. Reopen the issue immediately after merge and comment why it reopened.

### Changelog discipline

- User-visible slices: flat `[Unreleased]` line with `Refs #N` when the issue is not fully done.
- Do not imply completion in changelog wording if the tracking issue stays open.

### Counterexamples

| Anti-pattern | Why it hurts |
| --- | --- |
| `Fixes #891` on a CI-only or docs-only partial slice | Tracking issue auto-closes; remaining AC looks "done" |
| Putting `Fixes` in an intermediate commit that squash still includes | Squash commit message can still auto-close |
| Relying on "we will reopen later" without a comment | Audit trail lost; bots/reports treat it closed |
| Closing via commit keyword **and** a second manual close | Noise; prefer one intentional close when AC are met |

---

## 5. Self-iteration acceptance loop

### When to use

- Any planned `fix` / `feat` / `refactor` / `test` / `chore` with a written task or issue AC.
- After review feedback (especially when tempted to patch only the named lines).
- Agent/worker delivery that must converge before asking for merge.

### Loop (operational order)

```text
1. Feasibility against real code (files/contracts exist; runnable code wins over plan text)
2. Minimal implementation inside the stated boundary
3. Verification matrix by change scope (see AGENTS.md §6; run-verification skill)
4. Self-review in analyze-pr order: necessity → relevance → title → description → evidence → correctness
5. AC checklist item-by-item; fix full contract surfaces (runtime / API / Web / docs / tests)
6. Update PR body so it matches the final diff
7. Stop only when a review round adds zero new findings on the same semantics
```

Preferred skill entry: `develop-feature` (embeds verification + self-review). External review rounds: `handle-review-feedback` — **no patch stacking**.

### Commands (typical backend-touched change)

```bash
python -m pip install --upgrade --constraint constraints.txt pip
python -m pip install --build-constraint build-constraints.txt -r .github/requirements-ci.txt
python -m pip check
./scripts/ci_gate.sh
python -m py_compile <changed_python_files>
```

Web-touched change (additional):

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run test:i18n
npm run test
npm run build
```

Attribute red tests against `origin/main` (pre-existing vs newly introduced). Do not claim green while new failures remain.

### Counterexamples

| Anti-pattern | Why it hurts |
| --- | --- |
| "CI green" without AC checklist | Unreachable mounts, missing registry, wrong close keywords slip through |
| Point-patch only the reviewer's line | Same bug remains on sibling entry points (explicit low-quality pattern in this repo) |
| Mock away the risk layer so tests prove a local detail | False confidence; fails in production path |
| Leave PR body describing an older diff | Reviewers merge the wrong mental model |

---

## 6. Single-machine resource exhaustion

### When to use

- One host runs many agent workspaces, full `ci_gate`, Web builds, and Docker at once.
- Symptoms: OOM kills, thermal throttling, disk full under `node_modules`/pytest caches, zombie `pytest`/`node` processes, Git lock fights.

### Hard lessons (operational limits)

| Resource | Practical bound on a single laptop/desktop | Rationale |
| --- | --- | --- |
| Concurrent **full** `./scripts/ci_gate.sh` | **1** (never 2+) | Multi-GB RAM + long CPU; dual gates thrash and both fail flaky |
| Concurrent Web `npm run build` / full test matrix | **1–2** | `node_modules` and bundlers dominate disk and RAM |
| Concurrent agent workers editing the **same** git worktree | **1** | Index.lock, half-applied edits, lost work |
| Concurrent workers on **isolated** worktrees | Cap by RAM/disk (often **3–6** light tasks, not 20 full gates) | Each worktree + `node_modules` + venv is multi-GB |
| Background `npm ci` copies | Prefer shared install strategy or sequential bootstrap | Duplicate installs fill disk silently |

### Commands (inspect and shed load)

```bash
# Disk pressure
df -h .
du -sh .git node_modules apps/dsa-web/node_modules .pytest_cache 2>/dev/null

# Heavy processes
ps aux | egrep 'pytest|npm|node|uvicorn|playwright' | egrep -v egrep

# Git locks (do not delete locks held by a live process)
ls -la .git/index.lock .git/worktrees 2>/dev/null

# Drop local caches only when no run is active
# rm -rf .pytest_cache apps/dsa-web/node_modules/.cache
```

### Recommended worker layout

1. **One integrator terminal** on `main` (merge + canary only).
2. **N isolated worktrees** for independent path sets (ch. 2), each with at most one heavy verification at a time.
3. Prefer **path-selective** local tests while iterating; run full `ci_gate` once near handoff.
4. Stagger Docker image builds; do not parallelize `docker build` with two full pytest gates.

### Counterexamples

| Anti-pattern | Why it hurts |
| --- | --- |
| Spawn 15 agents each running full offline suite | Host becomes unusable; false timeouts look like product bugs |
| Share one working tree across agents | Overwrites and lock errors; undebuggable diffs |
| Ignore disk growth until `No space left on device` mid-merge | Corrupt half-merges; painful recovery |
| Kill random `node` PIDs without checking worktree ownership | Can kill the wrong agent's install mid-write |

---

## 7. Accidental workspace deletion defense

### When to use

- Many `git worktree` checkouts under `/tmp`, `~/orca/workspaces/...`, or sibling directories.
- Cleanup scripts, "free disk" sessions, or `rm -rf` after a train.
- Agents instructed to "remove the workspace" after PR open.

### Safe cleanup protocol

```bash
# 1) Inventory — never delete before listing
git worktree list
gh pr list --author @me --state open

# 2) Confirm the path is a worktree, not the primary clone
git -C <path> rev-parse --is-inside-work-tree
git -C <path> branch --show-current
git -C <path> status --short

# 3) Prefer git's own removal (refuses dirty trees by default)
git worktree remove <path>
# only if git cannot see it but directory remains:
git worktree prune

# 4) Directory delete only after worktree remove and clean status
# rm -rf <path>   # last resort; double-check path spelling
```

### Protections

- **Never** run broad deletes (`rm -rf /tmp/stock-pulse-*`, `rm -rf ~/orca/workspaces/stock-pulse-ai/*`) from memory.
- Keep the **primary** clone path on a denylist for automated cleanup.
- Before deletion: open PR pushed? uncommitted research notes? unpushed commits?

```bash
git -C <path> log --oneline origin/main..HEAD | head
git -C <path> status --short
git -C <path> remote -v
```

- If work was only local: create a backup branch or patch first:

```bash
git -C <path> branch backup/<topic>-$(date +%Y%m%d)
git -C <path> format-patch -o /tmp/backup-patches origin/main
```

### Counterexamples

| Anti-pattern | Why it hurts |
| --- | --- |
| `rm -rf` a directory that still has an active agent | Mid-write corruption; cannot reconstruct prompts/state |
| Deleting the only clone that held an unpushed fix | Work lost; "it was green locally" becomes mythology |
| Cleaning `/tmp/hb-*` with a too-broad glob | Unrelated trains share prefixes; collateral damage |
| Removing a worktree path without `git worktree remove` | Stale worktree metadata; later `git worktree add` fails oddly |

---

## 8. Quick command sheet

| Goal | Command |
| --- | --- |
| Full offline backend gate | `./scripts/ci_gate.sh` |
| Config three-way check | `python scripts/check_config_doc_consistency.py` |
| Registry debt guard tests | `python -m pytest tests/core/test_env_example_config_registry_guard.py -q` |
| AI collaboration assets | `python scripts/check_ai_assets.py` |
| Selective PR test map (see CI docs) | `python scripts/ci_select_tests.py` (used by CI; see [testing-ci-gate](testing-ci-gate.md)) |
| PR exact-head checks | `gh pr checks <n>` / `gh pr view <n> --json headRefOid,statusCheckRollup` |
| List worktrees | `git worktree list` |
| Safe worktree drop | `git worktree remove <path>` |

---

## 9. Related issues and slices

| Issue / PR | Role |
| --- | --- |
| [#891](https://github.com/SiinXu/stock-pulse-ai/issues/891) | Parent tracking: efficiency & quality playbook |
| [#808](https://github.com/SiinXu/stock-pulse-ai/pull/808) | Selective PR tests + sharded main gate (CI throughput slice) |
| [#1023](https://github.com/SiinXu/stock-pulse-ai/issues/1023) | Config registry registration debt |
| [#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008) | Post-train production reachability audit |
| [#1054](https://github.com/SiinXu/stock-pulse-ai/issues/1054) | Maintainership / WIP discipline |
| [#1065](https://github.com/SiinXu/stock-pulse-ai/issues/1065) | Further merge-throughput work |

This document records **operational patterns** learned from large parallel fix/merge waves. It does not replace milestone policy, Makefile/just unification, or label/template work still tracked under #891.

---

## 10. Maintenance

- When a pattern proves wrong in production, update this playbook in the same PR that changes process, or open a docs follow-up with evidence.
- Do not duplicate new hard rules here first — put hard rules in `AGENTS.md`, then link from this guide.
- Keep Chinese and English editions semantically aligned (`engineering-efficiency-playbook.md` / `engineering-efficiency-playbook_EN.md`).
