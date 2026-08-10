# 投资委员会分析模式

[中文](investment-committee-mode.md) | [English](investment-committee-mode_EN.md)

Issue [#545](https://github.com/SiinXu/stock-pulse-ai/issues/545)。在**不新增第二套策略引擎**的前提下，用配置开关激活一组人格（persona）Skills，走现有 Multi-Agent **specialist** 路径 + `StrategyEngine` 合成，并在报告中输出结构化「委员会审议」小节。

## 默认关闭

- 配置项：`AGENT_INVESTMENT_COMMITTEE_MODE`（默认 `false`）
- 关闭时：Single / Multi / Chat 与今日行为一致（无 `skills_requested` 注入、无 `committee_deliberation` 字段）
- 开启时：解析默认人格包（或请求中的 `personas`），写入 `ctx.meta.skills_requested`，由现有 `SkillRouter` + `SkillAgent` 执行

## 如何启用

1. `AGENT_MODE=true`（或等价 Agent 分析入口）
2. `AGENT_ARCH=multi`
3. `AGENT_ORCHESTRATOR_MODE=specialist`（人格 specialist 在 Decision 前插入）
4. `AGENT_INVESTMENT_COMMITTEE_MODE=true`

可选请求覆盖（分析 context）：

| 字段 | 含义 |
| --- | --- |
| `committee_mode: true/false` | 单次请求开关（`false` 强制关闭） |
| `personas: ["persona_value_moat", ...]` | 覆盖默认人格列表；单独传 `personas` 也会激活委员会模式 |

## 默认人格包

顺序与 `strategies/personas/` 中 `default_priority` 一致：

1. `persona_value_moat` — 价值与护城河  
2. `persona_mental_models` — 心智模型与反演  
3. `persona_contrarian_deep_value` — 逆向深度价值  
4. `persona_disruptive_growth` — 颠覆式成长  
5. `persona_tail_risk` — 尾部风险与脆弱性  

## 上限与失败隔离

- **上限**：与现有 specialist 并发上限一致，**最多 3** 个 persona 实际执行；超出部分写入 `personas_truncated`（明确截断策略，非静默丢弃）。
- **无效 id**：在可枚举 skill 目录时，未知 id 进入 `personas_invalid` / diagnostics，**不**当作成功执行。
- **单 persona 失败**：遵循多策略契约——无效 signal 进 Diagnostics；其余有效意见仍可合成 `strategy_synthesis`。
- **合成**：仅使用现有 `StrategyEngine`；不新增并行 Risk Manager 产品面。

## 报告

开启且完成分析后，dashboard 可含：

```text
dashboard.committee_deliberation  # schema_version: committee-deliberation-v1
```

结构遵循证据分层呈现习惯（缺失/冲突、模型推断、风险与反证、非投资建议声明），Markdown / WeChat 模板在 `strategy_synthesis` 之后渲染。历史报告无该字段时保持安静。

## 成本与免责

- 委员会模式会对每个选中 persona 多跑一轮 SkillAgent，**预期 token / 时延更高**。
- 输出为模拟研究视角，**不构成投资建议**；非任何具名个人或机构背书。

## Web UI

本 issue v1 **不包含** Web 设置页 / 分析页 UI（延后）。配置与 API context 字段优先；Web 启用入口见后续 issue。

## 回滚

将 `AGENT_INVESTMENT_COMMITTEE_MODE` 设为 `false` 或删除即可；无需数据迁移。
