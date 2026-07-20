# 多策略投资建议契约：Baseline 语义、Phase 1 收敛、Phase 2/3/4 边界

本页是「多策略投资建议」的专题文档，用于记录 2 个及以上策略/技能（skill）观点在系统内的**语义收敛边界**：有效证据集合、无效观点隔离、阵营分组、共识度、跨消费面一致性。Baseline 负责契约边界和现状盘点；Phase 1 只在 Baseline 契约内完成有效证据集合分拣、`strategy_synthesis` 确定性合成、DecisionAgent prompt 收敛、四条 renderer 一致性以及反例覆盖；Phase 2 只在 Phase 1 契约下新增 2–4 策略并发调度与阶段调度；Phase 3 只在 Phase 2 之上补前端多语言完整展示；Phase 4 只在同一 1.0 语义版本内补权重回测反馈闭环。Baseline 的所有约束对后续 Phase 均永久生效，Phase N 不得静默降级 Baseline 中已经写死的边界。

本仓库的实现说明：分拣与合成经由 `StrategyEngine`（`src/agent/skills/engine.py`）门面完成，Orchestrator 通过 `_run_strategy_engine` / `_apply_partition_fallback`（`src/agent/orchestrator.py`）接线。本仓库**没有** `_partition_skill_opinions` 独立函数——分拣统一收敛在 `StrategyEngine.partition_only` 中。

## 术语与边界

当前仓库里有多种名为 opinion / signal / consensus / synthesis 的数据面，Baseline 必须先消歧，避免把现有运行时结构误写成未来 phase。

| 术语 | 当前含义 | 当前主要消费方 | Baseline 边界 |
| --- | --- | --- | --- |
| `AgentOpinion` | `src/agent/protocols.py` 中所有 Agent（含 SkillAgent、TechnicalAgent、IntelAgent、RiskAgent、DecisionAgent）产出的观点数据类，含 `agent_name` / `signal` / `confidence` / `reasoning` / `key_levels` / `raw_data`。 | Orchestrator、StrategyEngine、Aggregator、DecisionAgent、Disagreement、Renderer | 记录为原始观点承载体；Baseline 不新增字段，也不把 `AgentOpinion` 分裂成两类。 |
| `StrategyOpinion` | `src/agent/protocols.py` 中的内部规范化视图，含 `skill_id` / `signal` / `original_signal` / `invalid_signal`；只在 Aggregator/Synthesizer 内部使用。 | `SkillAggregator`、`ConflictDetector`、`StrategySynthesizer` | 记录为内部计算的规范化视图，不进入 `ctx.opinions`、不进入公共 payload、不进入 DecisionAgent prompt。 |
| Signal / Canonical Signal | 交易信号规范化标签，Canonical 取值仅限 `strong_buy` / `buy` / `hold` / `sell` / `strong_sell` 五个小写字符串。 | 全链路 | 记录为下游所有计算的唯一允许输入形式；大写别名、`"strong buy"`、Signal 枚举原值都必须先经 `normalize_strategy_signal()` 转成 canonical 再参与计算。 |
| Valid Opinion / Invalid Opinion | 通过 `is_valid_strategy_signal(signal) == True` 的观点为 Valid，其余为 Invalid。 | StrategyEngine 分拣、Aggregator、DecisionAgent | 记录为契约层的合法/非法判定；Baseline 只定义判定函数与语义，不预设分拣位置。 |
| Evidence Chain | 进入 DecisionAgent prompt 与 `strategy_synthesis` 数值计算的**有效观点集合**。 | DecisionAgent、Aggregator | 记录为决策输入面；Baseline 规定 Evidence Chain 只由 Valid Opinion 组成，Invalid 不得混入。 |
| Diagnostics | 无效观点的诊断收纳位，仅供日志、调试、用户可见的“另有 N 个策略解析失败”计数使用。 | Renderer 展示、日志 | 记录为诊断面；Baseline 规定 Invalid 必须落到 Diagnostics，不得被静默转成 `hold` 混入 Evidence Chain。 |
| `strategy_synthesis` | `dashboard.strategy_synthesis` 顶层 payload，含 `final_signal` / `consensus_level` / `conflict_severity` / `supporting_skills` / `opposing_skills` / `summary_params`。 | Markdown、WeChat、Notification、History 四条 renderer | 记录为公共低敏 payload；Baseline 规定该 payload 是**唯一权威合成来源**，LLM dashboard 不得反向覆盖。 |
| `disagreement_summary` | `ctx.meta["agent_disagreement_summary"]`，低敏跨 Agent 分歧摘要，来自 `build_agent_disagreement_summary()`。 | DecisionAgent prompt、日志 | 记录为决策路径提示面；Baseline 规定只从 Valid Opinion 建桶，Invalid 不得进入 `bullish_agents` / `bearish_agents` / `neutral_agents`。 |
| Consensus Level | `strategy_synthesis.consensus_level`，取值 `high` / `medium` / `low` / `insufficient`。 | Renderer 展示、Aggregator 内部判定 | 记录为共识度枚举；Baseline 规定 ≤ 1 valid 或 `sum(confidence) == 0` 时强制 `insufficient`，不得输出 `high`。 |

## Baseline 范围与非目标

Baseline 的目标是让 Phase 1/2/3/4 都基于同一份语义契约设计运行时改动，而不是每一轮 PR 重新定义“有效观点”、“共识”、“支持方”。

- Baseline 覆盖 SkillAgent → StrategyEngine/Orchestrator → Aggregator → Synthesizer → DecisionAgent → Disagreement → Renderer 七条消费面的语义收敛边界。
- Baseline 固定 Canonical Signal 枚举、Valid/Invalid 判定函数、Evidence Chain / Diagnostics 分离原则、动态二分阵营语义、共识门槛梯度、`strategy_synthesis` payload schema、不变量清单和反例矩阵；Phase 1 是这些边界的第一版代码化实现。
- Baseline 不引入并发调度、不引入前端多语言完整展示、不引入权重回测反馈；这些留给 Phase 2/3/4。
- Baseline 不改变现有 `AgentOpinion` 字段、不新增数据库字段、不改变 API 返回结构、不新增配置项。
- Baseline 不把契约扩展成通用 opinion registry；`AgentOpinion` 结构由现有代码维护，本契约只规范其**语义处置流程**。

## Baseline 内部契约

### Canonical Signal 与 Valid 判定

Canonical Signal 是 Baseline 允许的**唯一评分/加权/分组输入形式**。规范化入口是 `src/agent/protocols.py` 中的两个函数：

- `normalize_strategy_signal(signal)` 返回 `(canonical, invalid, original)` 三元组。它接受 `Signal` 枚举、大小写字符串、`"strong buy"` / `"strong-buy"` 别名，统一映射到 canonical 集合。无法映射时 `invalid=True`，`canonical` 退化为 `default`（默认 `"hold"`）但**必须**配合 `invalid=True` 一并传递到下游，不得被单独使用。
- `is_valid_strategy_signal(signal)` 是 Baseline 全链路合法性判定的**单一真源**：任何模块判断“这条 opinion 是否有资格进入 Evidence Chain”都必须调用此函数（内部委托 `normalize_strategy_signal`）。

SkillAgent（`src/agent/skills/skill_agent.py`）产出 opinion 时对缺失 signal 使用 `parsed.get("signal")`（返回 `None`，不再静默兜底为 `"hold"`），使缺失 signal 能被下游分拣正确识别为 Invalid。

Baseline 禁止在 `_STRATEGY_SIGNAL_ALIASES` 之外再维护第二份 canonical 映射表；ConflictDetector 与 Synthesizer 内部的 `strategy_signal_score(canonical)` 只接受 canonical 值，禁止用 `op.original_signal` 或大小写变体查表。

### Evidence Chain 与 Diagnostics 分离

Baseline 规定：

- **Evidence Chain 是且仅是 Valid Opinion 集合**。DecisionAgent prompt、`strategy_synthesis` 数值计算、`disagreement_summary` 建桶都必须从同一个 Evidence Chain（`ctx.opinions`）读取。
- **Invalid Opinion 必须落到 Diagnostics**（`ctx.meta["invalid_opinions"]`），仅用于日志、诊断、用户可见的“另有 N 个策略解析失败”计数。
- 两个集合**互斥且并集穷尽**：一条 skill opinion 要么在 Evidence Chain，要么在 Diagnostics，不得同时出现或都不出现。
- Invalid Opinion **不得**被静默转换成 `hold` / `confidence` 保留原值 / 匿名混入 `bullish_agents` / `bearish_agents` / `neutral_agents` 桶。

Diagnostics 结构（本仓库 `StrategyEngine.partition_only` 实际产出）：

```python
ctx.meta["invalid_opinions"] = [
    {
        "agent_name": str,          # 原始 agent_name
        "raw_signal": str | None,   # 原始 signal 字面量（未归一化），缺失时为 None
        "confidence": float,        # 原始 confidence，仅诊断，不参与任何计算
        "reason": str,              # "missing_signal" | "unrecognized_signal"
    },
    ...
]
```

分拣落在 `StrategyEngine.partition_only`，由 Orchestrator 的 `_run_strategy_engine` / `_apply_partition_fallback` 写回 `ctx.meta["invalid_opinions"]`。

### 动态二分阵营（Supporting / Opposing）

给定最终信号 `final_signal` 与 canonical score `final_score = strategy_signal_score(final_signal)`，对每个 Valid Opinion `op` 计算 `op_score = strategy_signal_score(op.signal)`：

- **当 `final_signal == "hold"`（即 `final_score == 3.0`）时**：
  - `op_score == 3.0` → `supporting_skills`
  - `op_score != 3.0` → `opposing_skills`（作为异议与分歧收纳，保证观望与分歧观点不被静默丢弃，避免展示时丢失异议背景）

- **当 `final_signal` 为方向性信号（`strong_buy` / `buy` / `sell` / `strong_sell`）时**：
  - 同向（都看涨 或 都看跌）且 `abs(op_score - final_score) ≤ 1.0` → `supporting_skills`
  - 反向 且 `abs(op_score - final_score) ≥ 2.0` → `opposing_skills`
  - 其余（`abs(diff) < 2.0` 且非同向）→ `opposing_skills`（并入异议，杜绝第三阵营 `neutral_skills`）

Baseline 明确 **`neutral_skills` 不作为 payload 的正式字段**。每个 Valid Opinion 必须**恰好**落入 `supporting_skills` 或 `opposing_skills` 其一，分组结果总数必须等于 `summary_params.opinion_count`。

### 共识度门槛

Baseline 固定共识度按 valid 样本数梯度判定：

| valid 数量 | consensus_level | 说明 |
| --- | --- | --- |
| 0 | `insufficient` | 无证据可综合，final_signal 强制 `hold`，`confidence=0.0` |
| 1 | `insufficient` | 单样本不构成“共识”，即使与 final 完全一致也不得输出 `high` |
| ≥ 2，`sum(confidence) == 0` | `insufficient` | 有效证据的置信度为零，无从建立共识 |
| ≥ 2，`sum(confidence) > 0` | 进入 aligned_ratio 判定 | 见下表 |

Aligned Ratio 判定（valid ≥ 2 且 `sum(confidence) > 0`）：

| 条件 | consensus_level |
| --- | --- |
| `conflict_severity == "high"` | `low` |
| `aligned_ratio ≥ 2/3` 且 `conflict_count == 0`（等价 `conflict_severity == "none"`） | `high` |
| `conflict_severity == "medium"` 且 `aligned_ratio < 0.5` | `low` |
| 其余 | `medium` |

其中 `aligned = 与 final_signal 同向且 score 距离 ≤ 1.0 的 valid 数量`，`aligned_ratio = aligned / len(valid)`。

Baseline 禁止使用 `sum(...) or 1.0` 之类的兜底把零权重掩盖成分母 1；零权重必须显式走 `insufficient` 分支，并让 `final_signal` 退回 `hold`。

### `strategy_synthesis` Payload Schema

```json
{
  "final_signal": "hold",                 // canonical signal
  "weighted_score": 3.0,                  // 保留 4 位小数
  "confidence": 0.72,                     // 折减后的置信度
  "original_confidence": 0.80,            // 折减前的加权置信度
  "conflict_count": 0,
  "conflict_severity": "none",            // none | low | medium | high
  "conflicts": [ /* ConflictDetector 输出的 dict 列表 */ ],
  "supporting_skills": [ /* opinion item */ ],
  "opposing_skills":   [ /* opinion item */ ],
  "consensus_level": "high",              // high | medium | low | insufficient
  "summary_key": "strategy_synthesis.no_conflicts",   // 动态 i18n 摘要键名，随共识和冲突状态确定
  "summary_params": {
    "opinion_count": 2,                   // valid 样本数（Evidence Chain 大小）
    "total_opinion_count": 4,             // valid + invalid（分拣前原始输入总数）
    "invalid_opinion_count": 2,           // Diagnostics 长度
    "final_signal": "hold",
    "consensus_level": "high",
    "conflict_severity": "none",
    "conflict_count": 0
  }
}
```

Opinion Item 结构（`supporting_skills` / `opposing_skills` 每个元素）：

```json
{
  "skill_id": "trend_v1",
  "agent_name": "skill_trend_v1",
  "signal": "hold",              // canonical
  "confidence": 0.80,            // 保留 4 位小数
  "reasoning": "...",
  "score_adjustment": 0,
  "conditions_met": [],
  "invalid_signal": false        // 兼容诊断标记；公开条目中必须恒为 false
}
```

Baseline 明确 `strategy_synthesis` 是**由 SkillAggregator 确定性算法产出、经 StrategyEngine 装配的唯一权威合成结果**。Orchestrator 的 `_collect_strategy_synthesis()` 从 `ctx.get_data("skill_consensus")` 读取 synthesis。**LLM 返回的 dashboard 不得覆盖或修改 `dashboard.strategy_synthesis`**；`normalize_dashboard_payload` 收到 LLM 输出时应剥离 LLM 侧的 `strategy_synthesis` 字段，避免 LLM 幻觉污染权威合成结果——`StrategyEngine` 是该字段的唯一写入方。

### 渲染层防腐（Renderer Hardening）

历史记录和外部调用方可能保留契约落地前的宽松 shape。四条 renderer 必须通过 `src/report_language.py` 中的共享 helper 消费 payload：

- `normalize_strategy_synthesis_payload(value)`：把非 dict 顶层值视为缺失（返回 `{}`），把 `supporting_skills` / `opposing_skills` / `conflicts` 中的非 dict 元素过滤掉，并把每个 conflict 的 `participants` 收敛为非空字符串列表，避免渲染器迭代坏数据。
- `format_strategy_skill_items(items, language, include_details=...)`：统一格式化策略列表，并只从 `get_report_labels(language)["none_label"]` 取得空列表占位符；Markdown / Notification / History 展示信号与置信度，WeChat 模板只展示紧凑策略名。
- `strategy_invalid_opinion_count(payload)`：统一读取 `summary_params.invalid_opinion_count`，防御 `summary_params` 缺失或非 dict、`bool`、负值、非十进制字符串等坏值，均降级为 0。
- `localize_strategy_signal` / `localize_consensus_level` / `localize_conflict_severity` / `localize_strategy_skill`：`_translate_from_map` 薄封装，识别命中则按 `report_language` 翻译，未识别则原样透传。
- `localize_strategy_conflict_description`：把 conflict_type 翻成展示句（zh/en/ko）。
- `localize_strategy_synthesis_summary`：从结构化 payload 生成语言相关摘要（区分有/无冲突）。

空列表占位符必须通过 `labels.none_label`（按 `report_language` 查表，zh/en/ko 三语完备）输出。禁止在 History、Notification 或模板中保留平行的手写读取逻辑或硬编码 `"无"` / `"None"` / `"없음"` 字面量。

### 关键不变量

Baseline 的语义边界收敛为八条不变量。所有 Phase N 的实现必须同时满足这八条，任一违反视为契约破坏。

| ID | 不变量 | 场景 | 期望 |
| --- | --- | --- | --- |
| I-1 | Evidence Chain 排他性 | 任何模块读取 Evidence Chain | 集合内每一条都必须 `is_valid_strategy_signal == True`；Invalid 不允许出现 |
| I-2 | 禁止静默转换 | 缺失或无法识别的 signal | 归入 Diagnostics，不得转换成 `hold` 后混入 Evidence Chain 或建桶 |
| I-3 | 零证据 → insufficient | 任意有效信号但 `sum(confidences) == 0`，或 valid 数量 = 0 | `final_signal="hold"`, `weighted_confidence=0.0`, `consensus_level="insufficient"`；禁止输出方向性信号 |
| I-4 | 单样本 → insufficient | 恰好 1 个 valid opinion | `consensus_level="insufficient"`，即使与 final 完全一致 |
| I-5 | Hold-final 一致性 | `final_signal == "hold"` 且存在 ≥ 2 个 hold valid opinion | 全部 hold opinion 必须归入 `supporting_skills`；consensus_level 与 supporting_skills 数量关系必须自洽（`high` 时 supporting 覆盖 ≥ 2/3） |
| I-6 | Payload 与 renderer 语义一致 | `dashboard.strategy_synthesis` 值 | 四条 renderer（Markdown / WeChat / Notification / History）实际文本必须与 payload 完全一致，不得出现“共识度：高 + 支持策略：无”等自相矛盾组合 |
| I-7 | Canonical-First 评分 | Aggregator / ConflictDetector / Synthesizer 内部的评分、加权、冲突判定、分组 | 必须使用 `normalize_strategy_signal()` 返回的 canonical 小写值；禁止用大写 `"BUY"`、别名等原始字符串直接查 `strategy_signal_score` |
| I-8 | 多语言空占位符 | `supporting_skills` / `opposing_skills` 为空时的展示 | 必须通过 `labels.none_label` 按 `report_language` 查表；禁止在代码或模板中硬编码中文 `"无"` / 英文 `"None"` / 韩文 `"없음"` 字面量 |

## Phase 1 语义收敛

Phase 1 是 Baseline 契约的第一版代码化实现。Phase 1 **不新增契约条款**，只把 Baseline 已经写死的边界落到具体代码：StrategyEngine 分拣、Aggregator/Synthesizer 计算收敛、DecisionAgent prompt 收敛、Disagreement 收敛、四条 renderer 一致性、反例覆盖。

Phase 1 涉及的入口：

- `src/agent/protocols.py`：`is_valid_strategy_signal()` 单一真源，`normalize_strategy_signal()` 保留 invalid 状态位。
- `src/agent/skills/skill_agent.py`：缺失 signal 时使用 `parsed.get("signal")`（返回 `None`，无静默默认）。
- `src/agent/skills/engine.py`：`StrategyEngine.process()` 通过 `partition_only()` 完成唯一权威分拣，再由 `process_partition()` 驱动聚合与合成；Valid 保留在 Evidence Chain，Invalid 写入 `EvidencePartition.invalid_records`。
- `src/agent/orchestrator.py`：在 DecisionAgent 运行前调用 `_run_strategy_engine(ctx)`；timeout / budget-skip 早退路径调用 `_apply_partition_fallback(ctx)`，只分拣、不合成，避免 Invalid 回流证据链。二者均把 invalid 记录写入 `ctx.meta["invalid_opinions"]`。
- `src/agent/skills/aggregator.py`：`StrategyEngine` 把 `valid_skill_opinions` 交给 `SkillAggregator.calculate()`；数学计算只使用 valid opinion，对 `valid_weight_sum == 0` 显式走 `insufficient` 分支。
- `src/agent/skills/synthesis.py`：`ConflictDetector` / `StrategySynthesizer` 使用 canonical signal 计算；`_group_opinions()` 按 §“动态二分阵营” 实现；`_consensus_level()` 按 §“共识度门槛” 实现；`summary_params` 补齐 `invalid_opinion_count` / `total_opinion_count`。
- `src/agent/agents/decision_agent.py`：`build_user_message()` 直接消费 `ctx.opinions`，不再二次过滤；在 prompt 中如实展示 `ctx.meta["invalid_opinions"]` 数量（英文诊断段落，仅供 `data_limitations` 标注，不作为决策依据）。
- `src/agent/disagreement.py`：`build_agent_disagreement_summary()` 直接消费 `ctx.opinions`（因 StrategyEngine 已完成分拣并由 Orchestrator 写回），Invalid 完全不出现在 `bullish_agents` / `bearish_agents` / `neutral_agents` 三桶中。
- `src/services/report_renderer.py`、`templates/report_markdown.j2`、`templates/report_wechat.j2`、`src/notification.py`、`src/services/history_service.py`：读取 `strategy_synthesis` 的确定性字段；支持/反方列表只经共享 `format_strategy_skill_items` 输出，空列表使用 `labels.none_label`，且不消费 `neutral_skills`。Notification fallback WeChat 是明确的紧凑例外，不展示列表与 conflict 明细。所有渲染前先经 `normalize_strategy_synthesis_payload` 防腐。
- `src/report_language.py`：`labels.none_label` 在 zh/en/ko 三语中完备；共识度、诊断计数文案完备；新增策略信号/共识/冲突/技能四类 canonical/translation 表与对应 `localize_*` helper。
- `tests/test_multi_agent.py`、`tests/test_report_language.py`、`tests/test_notification.py`、`tests/test_analysis_history.py`、`tests/test_report_renderer.py`：反例矩阵，从 SkillAgent 输入 → StrategyEngine 分拣/聚合 → DecisionAgent prompt → dashboard payload → renderer 实际文本全链路断言。

Phase 1 不改变 `AgentOpinion` 字段、不改变 API 返回结构、不改变数据库 schema、不新增配置项、不改变现有 skill 的执行方式。

## Phase 2 并发调度（未实现）

Phase 2 只在 Phase 1 契约下新增 2–4 策略并发调度与阶段调度：

- 策略执行从串行改为并发（`asyncio.gather` 或 thread pool），阶段调度中按 `SKILL_CONCURRENCY` / `SKILL_TIMEOUT_PER_SKILL` 控制。
- 单个 skill 超时或异常，走 Baseline Invalid 处理路径，进入 Diagnostics，不阻塞其他 skill 与主流程。
- Phase 2 不改变 Baseline Evidence Chain / Diagnostics 分离原则、不改变阵营语义、不改变共识门槛、不改变 payload schema。
- Phase 2 不改变 renderer 展示逻辑；`invalid_opinion_count` 计数天然覆盖超时/异常 skill。

## Phase 3 前端多语言完整展示（未实现）

Phase 3 只在 Phase 2 之上补前端（`apps/dsa-web/`、`apps/dsa-desktop/`）对 `strategy_synthesis` 的完整多语言展示：

- Web 报告详情页展示 `final_signal` / `consensus_level` / `supporting_skills` / `opposing_skills` / `conflicts` / `invalid_opinion_count`。
- 桌面端复用 Web 展示逻辑。
- 多语言 label 表复用 `src/report_language.py` 已有的 zh/en/ko 三语；前端只做投影，不重新定义。
- Phase 3 不改变 Baseline 契约、不新增 payload 字段、不新增 API 端点。

## Phase 4 权重回测反馈闭环（未实现）

Phase 4 在同一 1.0 语义版本内补权重回测反馈：

- `SkillAggregator._compute_weight()` 已有 `perf_weight` / `_backtest_factor()` 接线，Phase 4 只补自动权重更新的闭环。
- Phase 4 不改变 Baseline canonical signal / valid 判定 / 共识门槛 / 阵营语义；权重变化只影响 `weighted_score` 与 `confidence`，不影响 `consensus_level` 判定路径。

## 消费面盘点

Baseline 的七条消费面必须严格按下表分工，不得越界互相消费对方的内部数据。

### SkillAgent

各 skill 通过 `src/agent/skills/skill_agent.py` 产出 `AgentOpinion`。Baseline 允许 skill 输出任意 signal 字面量（含大写、别名、`Signal` 枚举），也允许 skill 因数据不足产出 `signal=None` / 缺失字段——这些情况由下游分拣处理，skill 本身不做自我过滤。

### StrategyEngine / Orchestrator（分拣与接线）

Phase 1 在 DecisionAgent 运行前由 Orchestrator 调用 `_run_strategy_engine(ctx)`：

- `StrategyEngine.partition_only()` 遍历所有 `agent_name` 命中 `is_skill_agent_name()` 的观点，使用 `normalize_strategy_signal()` 保留 canonical signal；命中的 skill_consensus/legacy consensus 观点在分拣时跳过（由 engine 重新生成）。
- Invalid 从 Evidence Chain 移除，写入 `EvidencePartition.invalid_records`；Orchestrator 再把它赋给 `ctx.meta["invalid_opinions"]`。
- `StrategyEngine.process_partition()` 只把 `valid_skill_opinions` 交给 Aggregator/Synthesizer；产出的 consensus opinion 和 `skill_consensus_data` 由 `_run_strategy_engine()` 一次写回 context（`ctx.opinions` 重建为 non-skill + valid skill + consensus；`ctx.set_data("skill_consensus", ...)`）。
- timeout / budget-skip 发生在完整 engine 运行前时，`_apply_partition_fallback()` 复用 `partition_only()`，只完成分拣和 Diagnostics 写回，不生成 consensus；对已完整运行过的情形幂等跳过（`skill_consensus` 已存在时直接返回）。

Baseline 规定 `StrategyEngine.partition_only()` 是**唯一权威分拣实现**。Aggregator / DecisionAgent / Disagreement 不再各自定义 Valid/Invalid 规则，直接消费 engine 收敛后的 Evidence Chain。本仓库不存在独立的 `_partition_skill_opinions` 函数。

### SkillAggregator

正常运行时由 `StrategyEngine` 调用 `SkillAggregator.calculate(valid_skill_opinions)`。Aggregator 把输入转换为内部 `StrategyOpinion`，数学计算只使用 valid opinion，并严格使用 canonical signal 查 `strategy_signal_score`。对以下三种状态显式走 `insufficient` 分支：

- `len(valid) == 0`：`final_signal="hold"`, `confidence=0.0`。
- `len(valid) == 1`：按该 opinion 的 canonical signal 输出 `final_signal`，但 `consensus_level="insufficient"`。
- `len(valid) ≥ 2` 且 `sum(confidence) == 0`：`final_signal="hold"`, `confidence=0.0`。

产出的 `strategy_synthesis` 由 `StrategyEngine` 装入 `StrategyResult.skill_consensus_data`，再由 Orchestrator 挂到 `ctx.set_data("skill_consensus", {...})`；`_collect_strategy_synthesis()` 从这里读取，作为 dashboard 的权威合成源。

### DecisionAgent

`build_user_message()` 从 `ctx.opinions` 读取观点写入 `## Agent Opinions (Evidence Chain)` 段落。因为分拣已保证 `ctx.opinions` 只含 Valid，DecisionAgent **不再**做二次过滤，并在拼接单条观点的顶层 extra data 时排除 `invalid_signal` 键。当 `ctx.meta["invalid_opinions"]` 非空时，追加 `## Invalid Skill Opinions (Diagnostics only; not in evidence chain)` 段落，用一句英文说明有 N 条 skill 观点因 signal 缺失或无法识别被移出证据链，仅供 `data_limitations` 标注、绝不作为决策依据。

DecisionAgent 输出的 dashboard JSON 不得覆盖 `dashboard.strategy_synthesis`；如果 LLM 返回中含有该字段，`normalize_dashboard_payload()` 必须剥离，保留 Aggregator 侧的权威合成。

### Disagreement

`build_agent_disagreement_summary()` 只从 `ctx.opinions` 建 `bullish_agents` / `bearish_agents` / `neutral_agents` 三桶。因为 `ctx.opinions` 已只含 Valid，Invalid 完全不出现在三桶中，也不会被静默兜底为 `hold`。

### Renderer（四条）

所有 renderer 读取 `dashboard.strategy_synthesis` 展示综合信号、共识、冲突与 invalid 计数。Markdown、Jinja WeChat、Notification 全量报告和 History 还展示支持/反方策略；Notification 的 fallback WeChat 简版为保持现有消息密度，明确省略支持/反方列表与 conflict 明细：

- `final_signal` / `consensus_level` / `conflict_severity` / `conflict_count`。
- `supporting_skills` / `opposing_skills`（上述紧凑例外除外，且所有路径都不消费 `neutral_skills`）。
- `summary_params.invalid_opinion_count` → 按语言展示“另有 N 个策略无效/解析失败”。

空列表占位符必须通过 `labels.none_label`（按 `report_language` 查表）输出。四条 renderer 展示的最终文本必须与 payload 完全一致，不得出现“共识度：高 + 支持策略：无”这类内部矛盾。渲染前必须先经 `normalize_strategy_synthesis_payload()` 防腐，`strategy_invalid_opinion_count()` 统一读取诊断计数。

- Markdown / WeChat 模板经 `report_renderer.render` 注入的 jinja context 调用上述 helper（务必确保模板用到的每个 helper 都在 context 中注册）。
- Notification 经 `_append_strategy_synthesis_block` 与共享 `format_strategy_skill_items` 在 Markdown 全量报告、WeChat 简版、单股详情三处渲染；WeChat 简版只输出 headline、invalid 计数与完整摘要。
- History 经共享 `format_strategy_skill_items` 与历史详情策略综合块渲染。

### Diagnostics

`ctx.meta["invalid_opinions"]` 只允许被以下三类消费：

- 日志：记录 `agent_name` / `raw_signal` / `reason`，供排障。
- DecisionAgent prompt：作为“Invalid Skill Opinions”计数来源。
- Renderer：作为 `summary_params.invalid_opinion_count` 的来源。

禁止把 Diagnostics 里的 `confidence` 参与任何加权计算；禁止把 `raw_signal` 塞回 `ctx.opinions`。

## 反例矩阵

Phase 1 提供如下反例覆盖，从 SkillAgent 输入进，穿过 StrategyEngine 分拣 → SkillAggregator → DecisionAgent prompt → 最终 dashboard payload → 四条 renderer 实际文本输出。

| 编号 | 输入 | 断言点 | 覆盖的不变量 |
| --- | --- | --- | --- |
| E2E-A | 1 valid `buy/0.8` + 2 invalid `moon/0.9` | ① DecisionAgent prompt 不含 `moon` 字面量、不含 invalid `agent_name`；② `ctx.meta["invalid_opinions"]` 长度 = 2；③ `strategy_synthesis.summary_params.opinion_count == 1`、`invalid_opinion_count == 2`；④ `consensus_level == "insufficient"`；⑤ 四条 renderer 输出文本包含“另有 2 个策略无效/解析失败”（按语言）；⑥ `disagreement_summary` 三桶中都不出现 moon 转成的 hold/0.9 | I-1, I-2, I-4 |
| E2E-B | 2 valid `hold/0.0` | `final_signal="hold"`、`weighted_confidence=0.0`、`consensus_level="insufficient"`、**绝不**出现方向性信号；所有 renderer 展示“证据不足” | I-3 |
| E2E-C | 1 valid `buy/0.0` + 1 valid `hold/0.0` | 混合零权重场景：`final="hold"`、`confidence=0.0`、`consensus="insufficient"` | I-3 |
| E2E-D | 2 valid `hold/0.8` | ① `final_signal="hold"`、`consensus_level="high"`；② `supporting_skills` 长度 = 2、`opposing_skills` 长度 = 0；③ 除 Notification fallback WeChat 紧凑例外外，各明细输出同时包含“高共识”和两个 skill 名，不得出现“支持策略：无”配“共识度：高”；紧凑例外仍必须展示高共识且不得伪造空列表 | I-5, I-6 |
| E2E-E | 1 valid `buy/0.8` + 9 invalid | `consensus_level="insufficient"`（**不得** high）；四条 renderer 展示“基于 1 个有效策略判断（另有 9 个策略无效/解析失败）” | I-4, I-6 |
| E2E-F | 2 valid opinion，其中一个 `signal="BUY"`（大写） | Aggregator 内部计算 `weighted_score` 时使用 canonical `buy` 查分，**不得**因大写查表失败得到 0；`strategy_synthesis.final_signal` 输出 canonical 小写 | I-7 |
| E2E-G | 空 `supporting_skills` + `report_language="en"` | 所有实际展示空列表的 renderer 输出中不出现中文 `"无"`，而是 `"None"`（或对应语言 `labels.none_label`）；Notification fallback WeChat 紧凑例外不输出该列表 | I-8 |

## 源码锚点

| 域 | 锚点 |
| --- | --- |
| Signal 规范化与 Valid 判定 | `src/agent/protocols.py::normalize_strategy_signal`, `is_valid_strategy_signal`, `strategy_signal_score` |
| SkillAgent 观点产出 | `src/agent/skills/skill_agent.py::SkillAgent.post_process` |
| StrategyEngine 分拣与合成门面 | `src/agent/skills/engine.py::StrategyEngine.partition_only`, `process`, `process_partition` |
| Orchestrator 接线与早退分拣 | `src/agent/orchestrator.py::_run_strategy_engine`, `_apply_partition_fallback` |
| SkillAggregator | `src/agent/skills/aggregator.py::SkillAggregator.calculate` |
| ConflictDetector / StrategySynthesizer | `src/agent/skills/synthesis.py::ConflictDetector`, `StrategySynthesizer` |
| DecisionAgent prompt | `src/agent/agents/decision_agent.py::build_user_message` |
| Disagreement | `src/agent/disagreement.py::build_agent_disagreement_summary` |
| Dashboard 合成挂载 | `src/agent/orchestrator.py::_collect_strategy_synthesis` |
| Renderer · Markdown | `src/services/report_renderer.py::render`, `templates/report_markdown.j2` |
| Renderer · WeChat | `templates/report_wechat.j2` |
| Renderer · Notification | `src/notification.py::_append_strategy_synthesis_block` |
| Renderer · History | `src/services/history_service.py::_generate_single_stock_markdown`（历史详情策略综合块） |
| 多语言与宽松 payload 防腐 | `src/report_language.py::_REPORT_LABELS`, `normalize_strategy_synthesis_payload`, `format_strategy_skill_items`, `strategy_invalid_opinion_count`, `localize_strategy_synthesis_summary`, `localize_strategy_signal`, `localize_consensus_level`, `localize_conflict_severity`, `localize_strategy_skill`, `localize_strategy_conflict_description`, `labels.none_label` |
| 反例矩阵 | `tests/test_multi_agent.py`, `tests/test_report_language.py`, `tests/test_notification.py`, `tests/test_analysis_history.py`, `tests/test_report_renderer.py` |

## 兼容与回滚

### 已废弃行为（Phase 1 落地后）

| 旧行为 | 契约后 |
| --- | --- |
| `SkillAgent` 缺失 signal 时静默 `parsed.get("signal", "hold")` | 缺失 signal 用 `parsed.get("signal")`（`None`），由分拣归入 Diagnostics |
| `normalize_strategy_signal` 对未知信号静默返回 `default="hold"` 并混入证据链 | 未知信号必须归入 Diagnostics，`ctx.opinions` 中不允许出现 |
| Aggregator 通过 `sum(...) or 1.0` 掩盖零权重 | 显式判 `valid_weight_sum == 0`，走 `insufficient` 分支，`final_signal="hold"` |
| Renderer 硬编码 `"无"` 展示空阵营 | 通过 `labels.none_label` 按语言查表 |
| DecisionAgent 在 prompt 层自己过滤 invalid | 分拣在 StrategyEngine 完成，DecisionAgent 直接消费 `ctx.opinions` |
| `strategy_synthesis` 输出 `neutral_skills` | 契约后该字段不存在，renderer 不再消费 |
| LLM dashboard 覆盖 `strategy_synthesis` | 权威合成来自 StrategyEngine/Aggregator，LLM 侧字段被 `normalize_dashboard_payload` 剥离 |

### 已新增字段

- `ctx.meta["invalid_opinions"]`：Diagnostics 收纳位（结构见“Evidence Chain 与 Diagnostics 分离”）。
- `strategy_synthesis.summary_params.invalid_opinion_count`：Diagnostics 长度。
- `strategy_synthesis.summary_params.total_opinion_count`：valid + invalid 的原始总数。

### 回滚方式

| 手段 | 作用 | 不能做什么 |
| --- | --- | --- |
| 版本回退 Phase 1 相关提交 | 移除 StrategyEngine 分拣接线、Aggregator/Synthesizer 收敛、renderer 一致性改动 | 无法只回退部分不变量；契约是整体收敛 |
| 只保留契约文档、回退代码 | 保留 Baseline 文本、回到旧行为 | 只有文档意义，无运行时收益；不推荐 |
| Phase 2/3/4 独立回退 | 各自 Phase 的运行时改动独立回退 | 不能回退 Baseline，任何 Phase 都必须始终满足 Baseline 八条不变量 |

Baseline 不新增配置项，因此无 env-level 回滚开关；这是刻意选择——契约边界应在代码中恒定生效，不通过环境变量降级。
