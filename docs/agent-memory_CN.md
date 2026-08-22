# Principal 作用域分层 Agent 记忆

**状态**：分层记忆基础 + 生命周期（分层记忆尚未接入生产 prompt）。持久化存储/UI：[#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118)。来源标注与防投毒基线：[#1124](https://github.com/SiinXu/stock-pulse-ai/issues/1124)。

**English**: [agent-memory.md](agent-memory.md)

## 已有模块

| 模块 | 职责 |
| --- | --- |
| `src/agent/memory_layers.py` | 严格类型记录与投影类型 |
| `src/agent/memory_retrieval.py` | 结构化 episodic + **outcome-pattern** 检索；可选向量粗排 |
| `src/agent/memory_vector.py` | 无额外依赖的粗排 |
| `src/agent/memory_governance.py` | 知情同意、保留期、按 principal 删除/清空、访问审计 |
| `src/agent/memory_isolation.py` | 面向 prompt 的不可信数据隔离 |

既有 `AgentMemory` / `BaseAgent` 行为不变。分层 `PrincipalMemoryLifecycle` **尚未**接入生产 prompt。Historical Decision Reflection 是独立的生产注入路径（见下）。可选 `AGENT_MEMORY_ENABLED` 校准注入默认关闭，且当前不经过 `isolate_untrusted_memory_body`（见[威胁注释](#threat-notes)）。

## 诚实命名

第二层是 **outcome-pattern（结果模式）记忆**，不是自由文本「语义知识库」。Payload 使用 `outcome_patterns`；`semantic` 为弃用别名。

## 数据治理（默认最小化收集）

| 控制 | 默认 |
| --- | --- |
| `LAYERED_MEMORY_COLLECTION_ENABLED` | `false` |
| 按 principal 同意 | 无（collect/list/project/export 前必须） |
| `LAYERED_MEMORY_RETENTION_DAYS` | `90` |
| `LAYERED_MEMORY_AUDIT_ENABLED` | `true` |
| `LAYERED_MEMORY_VECTOR_ENABLED` | `false` |
| `LAYERED_MEMORY_MAX_RECORDS_PER_PRINCIPAL` | `200` |

## 注入防护

任何面向 prompt 的渲染必须使用 `isolate_layered_memory_for_prompt()`，或共享的
`isolate_untrusted_memory_body()`（非 bundle 文本）。

### 历史决策记忆复盘（#118）

同标的 Historical Decision Reflection 走 **独立生产路径**（`DecisionSignal` +
outcome 存储，不是 `PrincipalMemoryLifecycle`），但仍必须：

1. **准入**：仅 size-capped 的结构化已结算 outcome，且带 `signal_id` 来源
   （`admit_decision_memory`）；不注入自由文本 `reason`。本股胜率与列表同源
   （同一 lookback 准入集合）。每个 renderer 都会重新执行准入（dataclass 的
   `admitted` 标记不是授权位），并拒绝非有限数值、越界配置及非标准 action。
2. **隔离**：Prompt 块经 `isolate_untrusted_memory_body` 标注为不可信数据。
3. **可关闭**：`DECISION_MEMORY_ENABLED` / 请求级 `use_memory`。

详见 `docs/decision-signals.md`「历史决策记忆注入」。

<a id="threat-notes"></a>
## 威胁注释（#1124）

共享/长期记忆的短安全基线。这是范围图，不是利用指南，也不是记忆产品说明。

| 威胁 | 当前契约 | 缺口 |
| --- | --- | --- |
| **投毒（Poisoning）** | 生产 decision-memory 只准入带 `signal_id`、有大小上限的结构化已结算 outcome，并将 prompt 块标为不可信数据。分层投影字段拒绝自由文本。 | 用户笔记与自由文本反馈是意见，不是行情事实。可选 `AGENT_MEMORY_ENABLED` 校准注入默认关闭，且当前未做隔离包装。 |
| **事实 vs 意见** | 系统行情 actuals 在 `decision_signal_outcomes` 与 `agent_predictions.outcome_json`（`resolved` 行不可变）。用户反馈是 sidecar 意见表，不得改写这些 actuals。 | 传输通道 `source`（`web` / `api`）**不是** provenance。持久化记忆写入仍需服务端盖章的 `source` ∈ `system_resolve` / `user_feedback` / `operator`，以及可选的会话 `actor_id`。 |
| **Soul 边界伪造** | Soul/Persona 组装会拒绝 Soul 边界标记。反馈 `note` 有长度上限并做密钥脱敏。 | 用户可写记忆文本尚未拒绝 Soul 边界标记或标记注入载荷。 |
| **租户 / actor** | 产品是单管理员模型（`AUTH-05`）。分层 `principal_id` 拒绝仅存在于进程内基础层。 | 基础层 principal 测试不是生产隔离。可选 `actor_id` 是管理员/会话标识，不是多租户授权。跨用户隔离仍属 [#230](https://github.com/SiinXu/stock-pulse-ai/issues/230) / [#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118)。 |

写路径上的非法、超限或标记注入载荷必须 **拒绝**，不得截断后当事实存储。Decision-memory **准入** 保持失败即关闭（不准入则不注入）；分析 **构建** 失败保持失败即跳过（跳过注入、分析继续）。见[安全基线 Current Gaps](security-baseline.md#current-gaps)。

## 剩余范围

- 权威 principal 赋值（API/bot/CLI/定时任务）与遗留迁移。
- 持久化生命周期存储与用户 UI：[#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118)（吸收已关闭的 [#250](https://github.com/SiinXu/stock-pulse-ai/issues/250) 与 [#198](https://github.com/SiinXu/stock-pulse-ai/issues/198)）。
- 经安全审查的生产 prompt 消费。
- 偏好层：[#1117](https://github.com/SiinXu/stock-pulse-ai/issues/1117)（吸收已关闭的 [#150](https://github.com/SiinXu/stock-pulse-ai/issues/150)）。
- 记忆 provenance、事实/意见隔离与防投毒基线：[#1124](https://github.com/SiinXu/stock-pulse-ai/issues/1124)。

不要重开 #250、#198 或 #150。

## 回滚

回退新增模块/测试/文档/配置字段与 changelog 行。

## 相关：错误模式百科

从后验/反思教训聚类的人类可编辑错误模式卡片见 [agent-error-pattern-encyclopedia.md](agent-error-pattern-encyclopedia.md) （Issue #1138）。教训是输入，百科是聚合层；与本页 outcome-pattern 记忆不同。
