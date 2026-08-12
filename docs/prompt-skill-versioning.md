# Prompt / Skill 版本化（#249）

**Issue:** #249  
**相关：** 晋升流水线 #1093（本议题不实现）、评估架 #215

英文版：`docs/prompt-skill-versioning_EN.md`

## 目标

为 Skill 与关键 prompt 提供 **版本标识 + 变更历史 + 回滚钉（active pin）** 基座，
使运行可复现，错误内容可回退，且 **不改写现行 prompt / Skill 指令正文**。

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
- 不重写 `strategies/*.yaml` 或 Python prompt 常量

存储：`PROMPT_ARTIFACT_STORE_DIR`；未设置时默认
`<database parent>/prompt_artifacts`。

## 运行 trace

`resolve_skill_prompt_state` → `SkillManager.get_version_trace()` →
`SkillPromptState.version_trace`，并在有诊断上下文时写入
`RunDiagnosticContext.prompt_artifact_versions`（同时兼容 `prompt_version` /
`skill_versions` 字段）。

`SkillAgent.post_process` 向 `raw_data` 写入 `skill_version` /
`skill_content_hash`，供 skill opinion 样本落库。

## 与 #1093 边界

| 能力 | #249 | #1093 |
| --- | --- | --- |
| 版本 id + content hash | 是 | 消费 |
| 历史 + 回滚 pin | 是 | 检查项 |
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
