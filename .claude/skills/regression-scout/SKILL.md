---
name: regression-scout
description: From a PR or working-tree diff, list likely regression surfaces (routes, config keys, providers, i18n keys, report templates) and point to existing tests or commands to run. Lightweight pre-review scout — not full QA.
---

# Regression Scout

Lightweight surface scout for a change set. Outputs likely regressions and **existing** tests or recipe commands — it does not replace `/test-change` or CI.

**Source of truth**: `AGENTS.md` §6–7. Recipes: `.claude/skills/references/test-command-recipes.md`. Reachability: `.claude/skills/references/hard-rules.md` §3.

## Usage

```text
/regression-scout [--base origin/main] [--pr <n>]
```

## Instructions

### Step 1: Obtain the diff

```bash
BASE_REF=$(git merge-base HEAD origin/main)
git diff --name-only "$BASE_REF"..HEAD
# or: gh pr diff <n> --repo SiinXu/stock-pulse-ai --name-only
```

### Step 2: Classify surfaces

| Diff hits | Scout for |
|-----------|-----------|
| `api/**`, `src/schemas/**` | API compatibility; OpenAPI drift; Web client types |
| `src/core/config*`, `.env.example`, `config_registry_parts/**` | Settings controls; registry guard; inventory |
| `data_provider/**` | Priority, timeout, fallback, cache contracts |
| `templates/**`, report services | Report/notification structure |
| `apps/dsa-web` pages/routes/nav | Deep links; production reachability |
| i18n / locales | Missing keys; high-risk process |
| workflows / scripts | Gate semantics; path filters |

### Step 3: Point to existing tests

```bash
rg -n "symbol_or_module" tests apps/dsa-web --glob '*test*' -l
```

Map each surface to a recipe from `test-command-recipes.md`.

### Step 4: Reachability pass

If the diff adds a user-facing panel/API client/service, run hard-rules §3 production-reference grep.

### Step 5: Output

Surfaces → commands; reachability verdict; hand off execution to `/test-change` and merge verdict to `/review-pr`.

## Never

- Claiming the PR is fully verified after scouting only
- Weakening tests
- Auto push / merge
