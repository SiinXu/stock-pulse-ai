# Principal 作用域分层 Agent 记忆

**状态**：分层记忆基础 + 生命周期 + 默认关闭的观测持久化存储（无生产分层记忆 prompt 注入，无用户 CRUD）。#1118 剩余 UX/prompt/语义事实/程序层 persist：[#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118)。来源标注与防投毒基线：[#1124](https://github.com/SiinXu/stock-pulse-ai/issues/1124)。写入准入库：[#1119](https://github.com/SiinXu/stock-pulse-ai/issues/1119) Slice 1（遗忘 / 压缩仍开放）。

**English**: [agent-memory.md](agent-memory.md)

## 已有模块

| 模块 | 职责 |
| --- | --- |
| `src/agent/memory_layers.py` | 严格类型记录与投影类型 |
| `src/agent/memory_retrieval.py` | 结构化 episodic + **outcome-pattern** 检索；可选向量粗排 |
| `src/agent/memory_vector.py` | 无额外依赖的粗排 |
| `src/agent/memory_governance.py` | 知情同意、保留期、按 principal 删除/清空、访问审计；可选耐久存储 |
| `src/agent/memory_isolation.py` | 面向 prompt 的不可信数据隔离 |
| `src/schemas/memory_write_policy.py` | 仅库层、覆盖既有存储的写入准入（#1119 Slice 1） |
| `src/schemas/layered_memory_persist.py` | 观测映射准入：服务端 provenance、secret/PII 拒绝、事实/意见锁 |
| `src/repositories/layered_memory_repo.py` | SQLite 观测行 + 同意 + 仅追加访问审计 |
| `src/services/layered_memory_collection_service.py` | 分析历史保存后的默认关闭、失败软化收集 |

`AGENT_ONLINE_ADAPTERS_ENABLED` 关闭或缺失时，既有 `AgentMemory` 数值校准行为不变。分层 `PrincipalMemoryLifecycle` **尚未**接入生产 prompt。耐久存储仅在 `LAYERED_MEMORY_COLLECTION_ENABLED` 为真 **且** operator principal（`local_admin`）已同意时写入现有 `MemoryObservation`。存储失败 fail-soft，不得中断分析。Historical Decision Reflection 是独立的生产注入路径（见下）。可选 `AGENT_MEMORY_ENABLED` 历史注入默认关闭；开启时 `BaseAgent._build_memory_context` 用 `isolate_untrusted_memory_body` 包裹历史行，并将 `signal` 规范为 `buy|hold|sell`（见[威胁注释](#threat-notes)）。

## 在线进化适配器（默认关闭）

`BaseAgent._apply_memory_calibration` 经 `src/agent/evolution/adapters.py` 做门控置信度应用。开关关闭或配置缺失时保持今天的 `AgentMemory` 相乘。已持有 `Config` 的生产构造路径会注入该配置；否则 `BaseAgent` 读取 `get_application_services().config`。若该实时查找失败，`BaseAgent` 会安全记录 `agent_online_adapter_config_unavailable`，并继续走同一条非门控相乘（不写 `adapter_influence`）。开启时对已存 `calibration_factor` **只应用一次**（不得二次相乘）。工具排序与路由偏好仍是恒等桩。

| 控制项 | 默认值 | 行为 |
| --- | --- | --- |
| `AGENT_ONLINE_ADAPTERS_ENABLED` | `false` | 总开关。关闭或缺失时 `BaseAgent` 走今天的 `AgentMemory` 相乘，适配器辅助函数为恒等（原始置信度、输入工具顺序、原路由），且不在 `AgentContext.meta` 写入 `adapter_influence`。 |
| `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES` | `30` | 门控置信度校准生效所需的最少 `AgentMemory` 样本。低于阈值时因子为 `1.0`，`applied=false`，门控路径上展示置信度保持原始值。 |

Issue #1115 示例名 `EVOLUTION_MIN_SAMPLES` **不是** `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES` 的别名。只应作为 [预测核验安全放量](prediction-verification-rollout.md) 的 **第 5 步** 打开本适配器闸门：先抽取、再单 worker / 显式 CLI 解析器、再 miss/partial 后验。自动晋升保持硬关闭；没有 `EVOLUTION_AUTO_PROMOTE_SKILLS` 环境变量。

开启且样本达到适配器阈值后，`BaseAgent` 把展示/决策置信度交给 `calibrate_confidence`，后者使用 `AgentMemory.get_calibration` 已存的 `CalibrationResult.calibration_factor`（且仅在 `calibrated` 为真时生效）。门控调用使用既有适配器签名（`agent_name`、`stock_code`），不传 `skill_id`；非门控路径仍传入 `extract_skill_id(self.agent_name)`。AgentMemory 已将 `historical_accuracy / avg_confidence` 钳制到 `0.5..1.5`，其中 `historical_accuracy=0.0` 是真实的 0% 准确率；适配器不得再用 `accuracy or 0.5` 这类真值回退重算该比值。随后将置信度限制在 `[0,1]`。样本来源仍是既有 `AGENT_MEMORY_ENABLED` / `AgentMemory`，本切片不新增存储。工具有效性与路由偏好是显式恒等桩：不会解锁已拒绝的 ToolSurface 工具，也不会写入 `AGENT_ORCHESTRATOR_MODE`。影响只记录在运行期 `AgentContext.meta["adapter_influence"]`（不写入 episode）。本切片 **不** 实现真正的 `rank_tools` 打分（#1123）、`prefer_route` / AgentRouter（#1120）、预测结果叠加挂钩（#1106）、EvolutionEvent 生产者（#1113）、episode schema 持久化或晋升。

### 预测结果叠加（默认关闭）

适配器开启时，`src/agent/evolution/outcome_ingest.py` 中的 `apply_forecast_outcome_calibration` 可通过既有 `list_by_symbol_market`（`limit <= 500`）拉取当前标的/市场已结算的 `agent_predictions`，并将带有 `[0, 1]` 内有限置信度的 `hit` / `partial` / `miss` 行送入既有门控适配器。数值准确率使用 `OUTCOME_NUMERIC_SCORE`（`hit=1.0`、`partial=0.5`、`miss=0.0`）。

- 开关关闭或缺少 `stock_code`：恒等，且不查询存储。适配器关闭时不写入 `adapter_influence`。
- `N < AGENT_ONLINE_ADAPTERS_MIN_SAMPLES`：恒等（`applied=false`，`reason=insufficient_samples`）。
- `N >=` 阈值：只用预测结果统计。本切片 **不会** 把 `AgentMemory` / 回测统计与实盘预测结果混合。
- `data_unavailable`、未标注行、无效置信度、远期收益 sidecar 分桶（`1d_up` 等）以及存储失败都不是样本，也绝不会伪造 hit。
- 影响仍只写在 `AgentContext.meta["adapter_influence"]`。叠加层仍是仅库层：`BaseAgent` **不会**调用 `apply_forecast_outcome_calibration`。Soul、ToolSurface、episode、预测 HTTP 以及工具/路由桩均不变。

## 诚实命名

第二层是 **outcome-pattern（结果模式）记忆**，不是自由文本「语义知识库」。Payload 使用 `outcome_patterns`；`semantic` 为弃用别名。

## 数据治理（默认最小化收集）

| 控制 | 默认 |
| --- | --- |
| `LAYERED_MEMORY_COLLECTION_ENABLED` | `false`（关闭时收集助手不打开 repository） |
| 按 principal 同意 | 无（collect/list/project/export 前必须；生产收集使用单一 operator `local_admin`） |
| `LAYERED_MEMORY_RETENTION_DAYS` | `90` |
| `LAYERED_MEMORY_AUDIT_ENABLED` | `true`（审计表禁止 UPDATE/DELETE） |
| `LAYERED_MEMORY_VECTOR_ENABLED` | `false` |
| `LAYERED_MEMORY_MAX_RECORDS_PER_PRINCIPAL` | `200` |

耐久表：`layered_memory_observations`、`layered_memory_consent`、`layered_memory_access_audit`。这不是 `agent_episodes`，也不持久化 semantic-fact 或 procedural 权重。本切片无 HTTP/Web CRUD。

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
| **投毒（Poisoning）** | 生产 decision-memory 只准入带 `signal_id`、有大小上限的结构化已结算 outcome，并将 prompt 块标为不可信数据。分层投影字段拒绝自由文本。可选、默认关闭的 `AGENT_MEMORY_ENABLED` BaseAgent 历史注入用 `isolate_untrusted_memory_body` 包裹数据行，并将 `signal` 规范为 `buy` / `hold` / `sell`（`normalize_decision_signal`）；不会把 `operation_advice` 散文写入 `signal`。预期的存储查询失败（`RuntimeError`、`SQLAlchemyError`）会跳过注入，而不是输出未证实的行。映射路径上的意外错误不会被吞掉。数值校准不变。 | 用户笔记与自由文本反馈是意见，不是行情事实。Prompt 隔离在注入时仍会截断（分析构建保持失败即跳过）。 |
| **事实 vs 意见** | 系统行情 actuals 在 `decision_signal_outcomes` 与 `agent_predictions.outcome_json`（`resolved` 行不可变）。用户反馈是 sidecar 意见表。DAG-1 在 `src/schemas/memory_fact_opinion.py` 锁定事实/意见写入键：prediction resolve、decision-signal outcome/feedback upsert 以及 `PUT /api/v1/decision-signals/{signal_id}/feedback` 对混合载荷 **拒绝**。反馈不能改写 PredictionOutcome actuals。传输通道 `source`（`web` / `api`）**不是** provenance。DAG-3 在 `src/schemas/memory_provenance.py` 由服务端盖章 `provenance_source` ∈ `system_resolve` / `user_feedback` / `operator` 以及可选会话 `actor_id`（反馈写入为 `local_admin`）。客户端提交的 provenance 键会被 **拒绝**。历史 prediction/episode 行保持 NULL；已有反馈行可回填 `user_feedback`。 | 可选 `actor_id` 是 `AUTH-05` 下的管理员/会话标识，不是多租户授权。持久化存储 / principal 赋值仍属 [#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118) / [#230](https://github.com/SiinXu/stock-pulse-ai/issues/230)。 |
| **Soul 边界伪造** | Soul/Persona 组装会拒绝 Soul 边界标记。用户可写记忆文本（`PUT .../feedback` 的 `note`/`reason_code`、仓库 upsert、episode 的 `user_feedback` / `extra` / `remedy`）对 Soul 边界标记、超限和非法 C0 控制字符 **拒绝**，不会截断或剥离后存储。既有上限不变：反馈 note 1000、reason_code 64、episode 字符串 256 / remedy 300。密钥脱敏仍存在，但不能代替写路径拒绝。 | Prompt 隔离在注入时仍会截断（分析构建保持失败即跳过）。那不是写路径契约。 |
| **租户 / actor** | 产品是单管理员模型（`AUTH-05`）。分层 `principal_id` 拒绝仅存在于进程内基础层。 | 基础层 principal 测试不是生产隔离。可选 `actor_id` 是管理员/会话标识，不是多租户授权。跨用户隔离仍属 [#230](https://github.com/SiinXu/stock-pulse-ai/issues/230) / [#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118)。 |

写路径上的非法、超限或标记注入载荷必须 **拒绝**，不得截断后当事实存储。Decision-memory **准入** 保持失败即关闭（不准入则不注入）；分析 **构建** 失败保持失败即跳过（跳过注入、分析继续）。见[安全基线 Current Gaps](security-baseline.md#current-gaps)。

<a id="write-admission-policy"></a>
## 写入准入策略（#1119 Slice 1）

仅库层的持久化写入准入位于 `src/schemas/memory_write_policy.py`，与 #1124 写入契约同层。它分类写入并失败即关闭。它 **复用** `memory_fact_opinion`、`memory_write_guard`、`memory_provenance`，不分叉、不削弱。没有新表、新环境变量、公开 API、Web 或 Desktop 面。

| 写入类别 | 准入 | 是否持久化 |
| --- | --- | --- |
| **Episodic（情景）** | 紧凑的 run/outcome 摘要仅在既有结构化大小 / Soul / 控制字符校验之后准入 | 是 — 仅追加的 `agent_episodes` |
| **Market actuals（行情事实）** | `system_resolve` 载荷准入并由 **服务端盖章**。意见字段不得混入 | 是 — prediction resolve / decision-signal outcomes |
| **Opinion（意见）** | `user_feedback` / `operator` 载荷不得包含或覆盖 actual / outcome 字段；委托既有事实/意见锁 | 是 — decision-signal 反馈 sidecar 以及 run/prediction 反馈 sidecar |
| **Semantic fact（语义事实）** | 单条未验证用户笔记拒绝。达到 `MIN_OUTCOME_PATTERN_EVIDENCE`（3）的重复独立验证证据 **或** 显式 operator-promote 意图仅作为 **候选** 准入 | **否** — 尚无语义存储（[#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118)） |
| **Procedural auto-flag（程序性自动标记）** | 必须 **同时** 提供显式的正整数 `min_samples`（需要适配器下限时由调用方传入 `DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES`；缺省或非法 `min_samples` 失败即关闭）**以及** 显式通过的 eval 闸门。闸门缺席 / 为假一律拒绝 | **否** — 无程序性存储；自动晋升保持硬关闭 |

受治理的持久化入口：prediction resolve / `data_unavailable` actuals（SQLite 与解析器内存存储）、decision-signal outcome 与 feedback upsert、run/prediction 反馈 upsert（`AgentFeedbackRepository` / `AgentFeedbackService`）、episode 追加。成功载荷、状态迁移、不可变性、provenance source、分析失败即跳过、episode 仅追加行为，以及 run/prediction 反馈的 `_OPINION_KEYS` 身份键边界均不变。

已扫描但不并入本切片：curator-grade 入库与 forward-return 分桶（#1096）会在 sidecar 标签上盖 provenance，但不是覆盖行情 actuals 的用户笔记意见写入。请求体 schema 仍用 #1124 锁做传输校验，不是持久化准入。

Decision Memory 的 `admit_decision_memory` 是 **独立的 READ / 注入** 过滤器。渲染准入不是本写入策略；注入载荷按设计包含 `outcome` 键。

本切片 **不** 增加压缩、遗忘、按标的 TTL / 行数上限、检索分数衰减、#1118 存储、#1113 EvolutionEvent 持久化、自动晋升或新的产品反馈 API。[#1119](https://github.com/SiinXu/stock-pulse-ai/issues/1119) 保持开放。

## 剩余范围

- 权威 principal 赋值（API/bot/CLI/定时任务）与遗留迁移。
- 用户侧查看/编辑/删除/导出 UI 与 HTTP CRUD：仍属 [#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118)（吸收已关闭的 [#250](https://github.com/SiinXu/stock-pulse-ai/issues/250) 与 [#198](https://github.com/SiinXu/stock-pulse-ai/issues/198)）。观测/同意/审计耐久存储已落地；issue 保持开放。
- 经安全审查的生产 prompt 消费。
- 语义事实表 persist 与程序层权重 persist（#1119 下仍为 fail-closed `persist=False`）。
- 偏好层：[#1117](https://github.com/SiinXu/stock-pulse-ai/issues/1117)（吸收已关闭的 [#150](https://github.com/SiinXu/stock-pulse-ai/issues/150)）。
- 记忆 provenance、事实/意见隔离与防投毒基线：[#1124](https://github.com/SiinXu/stock-pulse-ai/issues/1124)。DAG-0 威胁注释、DAG-1 事实/意见锁定、DAG-2 Soul/超限写路径拒绝（`src/schemas/memory_write_guard.py`）和 DAG-3 服务端盖章 provenance（`src/schemas/memory_provenance.py`）已落地。DAG-4 将默认关闭的 AgentMemory 注入隔离为不可信数据（`src/agent/agents/base_agent.py` / `src/agent/memory.py`），`signal` 规范为 `buy` / `hold` / `sell`。不要并入 #1118 存储/UI 或 #1105 产品反馈 API。
- 写入准入 / 压缩 / 遗忘：[#1119](https://github.com/SiinXu/stock-pulse-ai/issues/1119)。Slice 1（覆盖既有存储的库层写入准入）见上文。仍缺：旧 episodic 行压缩、不改 Soul 的语义/程序性候选晋升、按标的 TTL / 行数上限、检索分数衰减，以及 [#1113](https://github.com/SiinXu/stock-pulse-ai/issues/1113) 落地后丢弃已回滚的程序性标记。保持 #1119 开放。

不要重开 #250、#198 或 #150。

## 回滚

将 `LAYERED_MEMORY_COLLECTION_ENABLED=false`（默认值）关闭收集。然后执行本切片 migration `downgrade`，仅 DROP `layered_memory_observations`、`layered_memory_consent`、`layered_memory_access_audit` 及其索引/trigger。不得触碰 episode / evolution-event / prediction / decision-memory 表。回退 PR 以移除收集助手。未接线生产 prompt，关闭开关后分析输出不变。

## 相关：错误模式百科

从后验/反思教训聚类的人类可编辑错误模式卡片见 [agent-error-pattern-encyclopedia.md](agent-error-pattern-encyclopedia.md) （Issue #1138）。教训是输入，百科是聚合层；与本页 outcome-pattern 记忆不同。
