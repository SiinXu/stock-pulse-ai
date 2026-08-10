# Principal 作用域分层 Agent 记忆

**状态**：Issue [#250](https://github.com/SiinXu/stock-pulse-ai/issues/250) 与 [#198](https://github.com/SiinXu/stock-pulse-ai/issues/198) 的基础投影 + 生命周期切片

**English**: [agent-memory.md](agent-memory.md)

## 已有模块

| 模块 | 职责 |
| --- | --- |
| `src/agent/memory_layers.py` | 严格类型记录与投影类型 |
| `src/agent/memory_retrieval.py` | 结构化 episodic + **outcome-pattern** 检索；可选向量粗排 |
| `src/agent/memory_vector.py` | 无额外依赖的粗排 |
| `src/agent/memory_governance.py` | 知情同意、保留期、按 principal 删除/清空、访问审计 |
| `src/agent/memory_isolation.py` | 面向 prompt 的不可信数据隔离 |

既有 `AgentMemory` / `BaseAgent` 行为不变。**尚未**接入生产 prompt 注入。

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

任何面向 prompt 的渲染必须使用 `isolate_layered_memory_for_prompt()`。

## 剩余范围

权威 principal 赋值、持久化存储、用户 UI、经安全审查的生产 prompt 消费、#150 偏好层。#250 与 #198 保持 open。

## 回滚

回退新增模块/测试/文档/配置字段与 changelog 行。
