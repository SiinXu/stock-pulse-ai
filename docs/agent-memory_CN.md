# Principal-scoped Agent 记忆投影基础

**状态**：Issue [#250](https://github.com/SiinXu/stock-pulse-ai/issues/250) 与 [#198](https://github.com/SiinXu/stock-pulse-ai/issues/198) 的纯函数基础切片

**English**: [agent-memory.md](agent-memory.md)

三个 `src/agent/memory_*` 模块只投影调用方已授权的记录；不读存储、不推断 owner、不持久化/缓存派生结果、不注入生产 prompt。既有 `AgentMemory` 与 `BaseAgent` 行为不变。

## 契约

- 每条记录必须有 `principal_id`；跨 principal 行、重复 id 和 legacy 无 owner 行均被拒绝。
- 输入最多 200 条；输出 limit 必须为正且最多 3；过期记录排除。
- signal 规范化；数值有限且有范围；outcome id、5/20 日 horizon、evaluation time 和 correctness 必须成组出现。
- 错误/未评估预测只是 observation；semantic evidence 仅使用带 provenance 的正确 outcome。
- 投影仅含 typed fact 与 source id，不含历史模型 prose，并序列化为 `NON_AUTHORITATIVE_MEMORY_DATA` 中的有界 strict JSON。
- vector 粗排只能显式开启，不新增配置；CJK unigram/bigram 支持粗排；`vector_used` 覆盖任一层。

## 剩余范围

生产使用仍需权威 principal 与 legacy migration、按用户/层 consent、view/export/correct/delete/clear、retention、派生删除/cache invalidation、run audit 及带 owner 的存储查询。两个 issue 均保持 open。

## 回滚

回退新增模块、测试、文档和 changelog 行即可；没有 runtime hook、config、migration 或持久派生物。
