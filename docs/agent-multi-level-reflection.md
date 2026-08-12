# 多层反思（即时步骤批评 / 运行级 / 跨运行）

对应 Issue **#1094**，从属 Epic **#1107**。复用预测后验与反思轨道（**#1196**）中的类型化教训 taxonomy（`src/agent/evolution/lessons.py`）。

## 产品规则（以 Epic #1107 为准）

- 仅研究 / 质量运维视角，不构成收益承诺。
- **不得**在运行时改写 Agent Soul（charter / version / hash）。
- **不得**在运行时改写 ToolSurface 拒绝/放行边界。
- 不可解析散文 **不会**变成可核验假声明或新的 lesson kind。
- 可选 LLM 均有预算；耗尽时显式 `budget_skipped`，禁止静默当成功。

## 三层结构

| 层级 | 触发条件 | 预算（默认） | 产出 |
| --- | --- | --- | --- |
| **即时**（步骤批评） | 工具失败或矛盾观察 | `AGENT_STEP_CRITIQUE_LLM_BUDGET`（默认 **0**，仅确定性映射） | 类型化教训 + `replan_reason_kinds` |
| **运行级**（轨迹反思） | 配置开启的运行结束反思 | `AGENT_REFLECTION_LLM_BUDGET`（默认 **1**） | 完整 `ReflectionResult` |
| **跨运行**（离线 meta） | 离线任务且样本量 ≥ 阈值 | `AGENT_META_REVIEW_LLM_BUDGET`（默认 **0**） | Markdown/JSON 演进报告与建议动作 |

教训写入既有 episode 投影形状（`kind` / `severity` / `claim_ref` / `remedy` / `source_step`），见 `episode_lessons.py`。

跨运行默认样本阈值 `AGENT_META_REVIEW_MIN_EPISODES=30`；不足时返回 `threshold_not_met`，不编造建议。

生产规划路径会把 Config 写入 `context["config"]`，因此 `AGENT_STEP_CRITIQUE_ENABLED` 在真实 AgentExecutor 跑通时生效。离线 meta CLI 仅在传入 `--force` 或配置开启时才绕过/启用门闩（默认不强制）。

离线命令：

```bash
python scripts/run_meta_review.py --episodes path/to/episodes.json --output-dir artifacts/meta_review --force
```

英文完整说明见 [agent-multi-level-reflection_EN.md](agent-multi-level-reflection_EN.md)。

## 回滚

关闭相关 enable 开关即可；本变更无数据库迁移。
