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
| **即时**（步骤批评） | 工具失败或矛盾观察 | 生产路径使用确定性映射 | 类型化教训 + `replan_reason_kinds` |
| **运行级**（轨迹反思） | 配置开启的运行结束反思 | `AGENT_REFLECTION_LLM_BUDGET`（**0–64**，默认 **1**） | 完整 `ReflectionResult` |
| **跨运行**（离线 meta） | 离线任务且样本量 ≥ 阈值 | 确定性聚合 | Markdown/JSON 演进报告与建议动作 |

教训使用既有 episode 投影形状（`kind` / `severity` / `claim_ref` / `remedy` / `source_step`），见 `episode_lessons.py`。生产路径在 `AGENT_REFLECTION_ENABLED` 时于 plan 结束挂轨迹反思。episode 持久化由 #1210 的单一运行结束 finalizer 负责；本变更不创建第二条 soft-append 写入路径。在该集成落地前，产出保留在 `planning_metadata`。

运行级反思通过 executor 的真实 provider 消费经过边界限制和脱敏的运行成功状态、工具轨迹与规划结果。provider 失败会显式记录 `status=error` / `validation_status=error`，不得伪造成功反思或新教训；已有的确定性即时教训会作为证据保留。

跨运行默认样本阈值 `AGENT_META_REVIEW_MIN_EPISODES=30`（范围 1–50000）；不足时返回 `threshold_not_met`，不编造建议。CLI 输入文件上限为 16 MiB，episode 必须唯一且结构有效；坏样本不会被静默过滤。聚合排序确定性，报告 basename 拒绝路径穿越，单个 Markdown/JSON 文件采用原子替换。

生产规划路径会把 Config 写入 `context["config"]`，因此 `AGENT_STEP_CRITIQUE_ENABLED` 在真实 AgentExecutor 跑通时生效。离线 meta CLI 仅在传入 `--force` 或配置开启时才绕过/启用门闩（默认不强制）。

离线命令：

```bash
python scripts/run_meta_review.py --episodes path/to/episodes.json --output-dir artifacts/meta_review --force
```

英文完整说明见 [agent-multi-level-reflection_EN.md](agent-multi-level-reflection_EN.md)。

运行时配置包含百科运行内反思键（`AGENT_REFLECTION_ENABLED`、`AGENT_REFLECTION_LLM_BUDGET` 0–64、`AGENT_REFLECTION_MAX_REVISE`）以及多层键 `AGENT_STEP_CRITIQUE_ENABLED`、`AGENT_META_REVIEW_ENABLED` 和 `AGENT_META_REVIEW_MIN_EPISODES`。即时层和 meta 层的实验性 LLM callback 只能由库调用方显式注入（默认预算为代码常量 0），不作为生产环境变量。

## 回滚

关闭相关 enable 开关即可；本变更无数据库迁移。
