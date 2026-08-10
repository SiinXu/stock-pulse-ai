# Principal-scoped Agent 记忆投影基础

**状态**：Issue [#250](https://github.com/SiinXu/stock-pulse-ai/issues/250) 与 [#198](https://github.com/SiinXu/stock-pulse-ai/issues/198) 的纯函数基础切片

**English**: [agent-memory.md](agent-memory.md)

三个 `src/agent/memory_*` 模块只投影调用方已授权的记录；不读存储、不推断 owner、不持久化/缓存派生结果、不注入生产 prompt。既有 `AgentMemory` 与 `BaseAgent` 行为不变。

## 契约

- 每条记录必须有 `principal_id`；跨 principal 行、重复 id 和 legacy 无 owner 行均被拒绝。
- 输入最多 200 条；输出 limit 必须为正且最多 3。
- signal 规范化；数值有限且有范围；outcome id、5/20 日 horizon、evaluation time 和 correctness 必须成组出现。`outcome_id` 与 `analysis_history_id` 必须是有界正整数，`was_correct` 必须是真正的 bool，因此非法 provenance 在构造期即失败，而不会在检索期 `int()` 崩溃。
- 所有时间戳（`observed_at`、`expires_at`、`evaluated_at`、`as_of`）必须是 `[2000, 2100)` 区间内的规范 UTC `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` 瞬时值，并按解析后的瞬时值比较。像 `2026-8-01T00:00:00Z` 这样的畸形值会被拒绝，而不是在字典序比较中胜出。
- 投影相对 `as_of` 为 point-in-time：晚于 `as_of` 观测的记录被排除，在 `as_of` 已过期的记录被排除，晚于 `as_of` 的评估会从 episodic 条目中扣留（`outcome_pending_as_of=true`）且不能成为 evidence。2099 年的面板在 2026 年的 `as_of` 下为空。
- 错误/未评估预测只是 observation；semantic evidence 仅使用带 provenance 的正确 outcome，且每个 pattern 只拥有一个 `horizon_days`。一条正确的 5 日结果加两条正确的 20 日结果是两个不充分 pattern，绝不会合并成一个 `sufficient_evidence`。
- 投影仅含 typed fact 与 source id，不含历史模型 prose。所有可能进入 payload 的字符串——`principal_id`、`stock_code`、时间戳、signal、派生的 `pattern_id`/`source`——都被限制在固定字符集内，因此存储的自由文本根本无法进入该边界。序列化为 `NON_AUTHORITATIVE_MEMORY_DATA` 中的有界 strict JSON。
- vector 粗排只能显式开启，不新增配置；CJK unigram/bigram 支持粗排；`vector_used` 覆盖任一层。

## 剩余范围

生产使用仍需权威 principal 与 legacy migration、按用户/层 consent、view/export/correct/delete/clear、retention、派生删除/cache invalidation、run audit 及带 owner 的存储查询。两个 issue 均保持 open。

## 回滚

回退新增模块、测试、文档和 changelog 行即可；没有 runtime hook、config、migration 或持久派生物。
