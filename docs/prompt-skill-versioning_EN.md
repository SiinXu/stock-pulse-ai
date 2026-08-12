# Prompt and Skill versioning

**Issue:** #249  
**Related:** promotion pipeline #1093 (out of scope here), evaluation harness #215

Chinese version: `docs/prompt-skill-versioning.md`

## Purpose

Provide a **version identity + change history + rollback pin** base for Skills
and key prompts so runs are reproducible and bad content can be pinned back
without rewriting source modules.

This issue intentionally does **not**:

- Change any shipped prompt / Skill instruction text
- Implement experimental → production promotion (#1093)
- Build approval UI, A/B assignment, or cross-version eval orchestration

## Identity model

| Field | Meaning |
| --- | --- |
| `version` | Author label (e.g. `1.0.0`) or content-addressed `ca-<12 hex>` |
| `content_hash` | `sha256:<hex>` of the definition-bearing payload |
| `lifecycle` | `draft` \| `active` \| `deprecated` \| `archived` |

### Skills

- Optional YAML keys: `version`, `lifecycle` (metadata only)
- When `version` is omitted, runtime derives `ca-<hash12>`
- Identity is attached on YAML/Markdown load and plugin `to_skill()` rebuild

### Key prompts

Registered in `src/agent/prompt_versioning/registry.py` with baseline label
`1.0.0` for currently shipped bodies. Future text edits should bump labels in a
dedicated PR.

## History and rollback

`PromptArtifactService`:

- `ensure_*` appends a revision when the content hash changes
- `list_history` returns newest-first revisions
- `rollback(..., to_version=N)` moves only the **active pin**
- `apply_active_skill_pin` overlays the active pin onto a live Skill when the
  pin body differs from the disk/plugin load (in memory only)
- Does **not** rewrite `strategies/*.yaml` or Python prompt constants

Storage root: `PROMPT_ARTIFACT_STORE_DIR` (default
`<database parent>/prompt_artifacts`).

**Runtime loop (Skills):** `load_skill_from_yaml` / `load_skill_from_markdown`,
`SkillManager.register`, and plugin `AnalysisStrategyDefinition.to_skill()` all
call `apply_active_skill_pin`. The pin body is applied only when
`active_version < latest_version` (rolled back); while the tip is active, disk /
plugin content remains the working set. On-disk YAML is never rewritten.

**Runtime loop (key prompts):** `resolve_key_prompt_text(prompt_id)` is used by
Agent run/chat, analyzer system/text, and image extract. Same
`active_version < latest_version` rule. `agent.soul` **never** accepts a pin
overlay (Soul identity proofs require the live charter).

## Runtime trace

`resolve_skill_prompt_state` builds `SkillPromptState.version_trace` and, when a
diagnostic context is active, attaches it via
`attach_prompt_artifact_versions`. Snapshots expose
`prompt_artifact_versions`, plus compatibility fields `prompt_version` and
`skill_versions`.

`SkillAgent.post_process` sets `raw_data.skill_version` /
`skill_content_hash` for skill-opinion samples.

## Boundary vs #1093

| Concern | #249 | #1093 |
| --- | --- | --- |
| Version id + content hash | Yes | Consumes |
| History + rollback pin | Yes | Checklist item |
| Lifecycle label field | Store only | Transitions / policy |
| Experimental activation | No | Yes |
| Eval + promotion CLI | No | Yes |

## Programmatic usage

```python
from src.agent.prompt_versioning import (
    get_prompt_artifact_service,
    get_key_prompt_identity,
    ArtifactKind,
)

service = get_prompt_artifact_service()
service.ensure_skill(skill, record_history=True)
service.list_history(kind=ArtifactKind.SKILL, artifact_id="bull_trend")
service.rollback(kind=ArtifactKind.SKILL, artifact_id="bull_trend", to_version=1)
get_key_prompt_identity("agent.system")
```
