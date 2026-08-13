---
name: sync-ai-assets
description: After editing AGENTS.md, Claude skills, Copilot instruction mirrors, or related AI governance assets, run and fix python scripts/check_ai_assets.py until green. Use when changing collaboration governance files.
---

# Sync AI Assets

Run the repository AI-governance consistency check after any change under the AI collaboration asset set. Skills compose with `AGENTS.md`; this skill does not invent a second rule source.

**Source of truth**: repository root `AGENTS.md` §2. Checker: `scripts/check_ai_assets.py`.

## Usage

```text
/sync-ai-assets
```

## When required

Run after editing any of: `AGENTS.md` / `CLAUDE.md`, `.claude/skills/**`, `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`, related `.gitignore` rules.

## Instructions

### Step 1: Run the checker

```bash
python scripts/check_ai_assets.py
```

Success prints `[ai-assets] OK`.

### Step 2: Fix path when it fails

| Failure theme | Fix |
|---------------|-----|
| `CLAUDE.md` missing or not symlink to `AGENTS.md` | `ln -sf AGENTS.md CLAUDE.md` |
| Missing instruction file | Restore required backend/client/governance instruction files |
| Missing skill asset | Restore required `SKILL.md` / README under `.claude/skills/` |
| Skill body lacks `AGENTS.md` reference | Cite `AGENTS.md` as the rule source |
| Changelog type tokens diverge | Align Copilot with AGENTS Unreleased types |
| Tracked `.claude` path outside `skills/` | Untrack review artifacts |
| `.gitignore` missing skill allow rules | Restore `!.claude/skills/` allowlist snippets |

Re-run until OK. Do not weaken the checker to greenwash.

## Division of labor

- This skill: governance asset check only.
- `test-change` / `run-verification`: include ai-assets as one matrix cell.

## Allowed Auto-Actions

- Running `python scripts/check_ai_assets.py`
- Local fixes to governance files required to pass

## Never

- Auto commit / push
- Logging secrets
- Replacing `CLAUDE.md` symlink with a divergent file copy
