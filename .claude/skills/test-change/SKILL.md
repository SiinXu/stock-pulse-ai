---
name: test-change
description: Map a code change to the repository verification layers, run the matching gates, and produce minimum evidence before claiming done or opening a PR. Use when verifying a task, before PR creation, or when asked to test changes. Project-specific commands only; delegates the executable matrix to run-verification.
---

# Test Change

P0 testing skill for this repository (issue #890). Selects test layers from the change surface, runs the documented commands, and records what passed, skipped, and why. Does **not** replace CI.

**Source of truth**: repository root `AGENTS.md` §6. Executable matrix and red-test attribution live in `/run-verification`. Shared recipes: `.claude/skills/references/test-command-recipes.md`. Hard rules: `.claude/skills/references/hard-rules.md`.

## Usage

```text
/test-change [--scope backend|web|desktop|docs|workflow|ai-assets|auto]
```

## Instructions

### Step 1: Map change → layers

From `git diff --name-only origin/main...HEAD` (or the task boundary):

| Path hit | Layers to run |
|----------|----------------|
| `main.py`, `src/**`, `data_provider/**`, `api/**`, `bot/**`, `tests/**` | backend offline gate / path pytest; `py_compile` minimum |
| Config / `.env.example` / `config_registry*` | **config registry guard** + doc consistency (hard-rules §2) |
| `apps/dsa-web/**` | web lint, unit, build; i18n tests if copy/locales touched; smoke e2e only when UI journeys change |
| `apps/dsa-desktop/**`, desktop scripts | web build then desktop build |
| `AGENTS.md`, `.claude/skills/**`, copilot mirrors | `python scripts/check_ai_assets.py` |
| Docs only | no code tests required; verify every command/filename mentioned |

### Step 2: Execute via run-verification

Run `/run-verification` with the derived scope(s). Prefer full gates when risk is high; never invent alternate install or test entry points when a recipe already exists.

Config-touching changes **must** include:

```bash
python scripts/check_config_doc_consistency.py
python -m pytest tests/core/test_env_example_config_registry_guard.py -q
```

### Step 3: Evidence bar

Minimum evidence before "done" or PR:

- Commands actually run + results
- Pre-existing failures on `origin/main` (non-blocking) vs new failures (blocking)
- Not executed items with reason
- UI/report changes: screenshot policy is PR attachment only (never commit binary evidence)
- Reachability claims (user-visible mounts): support with hard-rules §3 grep evidence, not file existence alone

### Step 4: Forbidden

- Weakening tests to greenwash
- Expanding config-registry debt baselines to green CI
- Claiming verification while new failures remain
- Auto `git push` / merge

## Division of labor

- `run-verification`: owns how to run the matrix and attribute red tests; this skill is the issue #890 **entry name** and the pre-PR evidence checklist that **calls** it.
- `develop-feature` Step 4 / `fix-issue` Step 4: invoke this skill or `run-verification` equivalently.
- `regression-scout`: lists likely surfaces; this skill runs the checks.

## Allowed Auto-Actions

- All non-destructive verification commands in the matrix and recipes

## Never

- Auto push, merge, or secret logging
- Claiming CI replacement by agent self-attestation
