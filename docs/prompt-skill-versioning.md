# Prompt / Skill 版本化（#249）

**Issue:** #249
**相关：** 晋升流水线 #1093（本议题不实现）、评估架 #215

英文版：`docs/prompt-skill-versioning_EN.md`

## 目标

为 Skill 与关键 prompt 提供 **版本标识 + 变更历史 + 回滚钉（active pin）** 基座，
使运行可追溯，关键 prompt 的错误内容可回退，且 **不改写现行 prompt / Skill
源文件或运行时 ToolSurface**。

本议题明确不做：

- 改写任何已发布 prompt / Skill `instructions` 正文
- experimental → production 晋升（#1093）
- 审批 UI、A/B 分配、跨版本评估编排

## 身份模型

| 字段 | 含义 |
| --- | --- |
| `version` | 作者标签（如 `1.0.0`）或 content-addressed `ca-<12 hex>` |
| `content_hash` | 定义载荷的 `sha256:<hex>` |
| `lifecycle` | `draft` \| `active` \| `deprecated` \| `archived` |

### Skill

- YAML 可选：`version`、`lifecycle`（仅元数据，不改 `instructions`）
- 未提供 `version` 时，运行时派生 `ca-<hash12>`
- 加载路径：`load_skill_from_yaml` / `load_skill_from_markdown`，以及插件
  `AnalysisStrategyDefinition.to_skill()`

哈希载荷排除 `enabled` 等运行时开关。

### 关键 prompt

注册于 `src/agent/prompt_versioning/registry.py`，基线版本标签 `1.0.0`
（对应当前已发布正文；后续改文应另 PR 升版本）。

## 历史与回滚

`PromptArtifactService`：

- `ensure_*`：内容哈希变化时追加修订
- `list_history`：最新优先
- `rollback(..., to_version=N)`：只移动 **active pin**，历史行不可变
- Skill rollback 只移动历史 active pin，运行时 Skill 仍以源文件 / plugin 定义为准；
  受治理的 Skill 激活留给 #1093
- 不重写 `strategies/*.yaml` 或 Python prompt 常量

存储固定派生自既有 `DATABASE_PATH`：`<database parent>/prompt_artifacts`。

**运行时闭环（Skill）：** `resolve_skill_prompt_state` 对实际激活的 Skill 写入历史和
trace，但不会从历史反向改写 `instructions`、`required_tools`、`allowed_tools`、默认
激活或路由字段。这样版本记录不能在进程运行时绕过 ToolSurface 或 plugin catalog；
受治理的 rollback 激活留给 #1093。

**运行时闭环（关键 prompt）：** `resolve_key_prompt_text(prompt_id)` 在
Agent run/chat、chat summary 压缩、analyzer system/text、image extract 路径使用。同样仅在
`active_version < latest_version` 时返回 pin 正文。`agent.soul` **禁止** pin
叠加（Soul 身份证明要求 live charter）。每次实际解析先原子写入当前正文，再记录所选
修订的 `source_version`；索引损坏或版本标签复用不同正文时失败关闭，不静默使用未钉选正文。

JSON 存储通过进程级文件锁保护完整 read-modify-write，并以临时文件、`fsync` 和原子
替换落盘。损坏、未知 schema 或不满足修订不变量的索引会报错且不会被空历史覆盖。

## 运行 trace

`resolve_skill_prompt_state` → `SkillManager.get_version_trace()` →
`SkillPromptState.version_trace` 写入实际 Skill 身份；Agent run/chat、analyzer system/text、
image extract 在解析实际 prompt 时把对应修订合并到
`RunDiagnosticContext.prompt_artifact_versions`（同时兼容 `prompt_version` /
`skill_versions` 字段）。Soul 沿用已有独立、不可覆盖的 runtime facts 身份证明。

`SkillAgent.post_process` 向 `raw_data` 写入 `skill_version` /
`skill_content_hash`，供 skill opinion 样本落库。

## 与 #1093 边界

| 能力 | #249 | #1093 |
| --- | --- | --- |
| 版本 id + content hash | 是 | 消费 |
| 历史 + key prompt 回滚 pin；Skill 管理 pin | 是 | 消费 Skill pin 并治理激活 |
| lifecycle 字段 | 存储 | 策略迁移 |
| experimental 激活 | 否 | 是 |
| 晋升 CLI / eval | 否 | 是 |

## 用法

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
