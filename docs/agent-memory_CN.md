# Agent 记忆契约（情景 + 语义）

本文对应 Issue #250 引入的分层 Agent 记忆。完整英文契约见 [`agent-memory.md`](./agent-memory.md)。

## 本轮交付范围

| 层级 | 状态 | 说明 |
| --- | --- | --- |
| 短期工作记忆 | 沿用现有 | `AgentContext` / 预取数据 / 消息列表 |
| 情景（episodic） | **已交付** | 指向具体历史分析（`AnalysisHistory`） |
| 语义（semantic） | **已交付** | 跨分析提炼的信号偏好/模式；样本不足保持中性表述 |
| 长期用户偏好 | **延后** | 风险偏好、沟通风格等用户画像本轮不做 |

## 开关

- `AGENT_MEMORY_ENABLED=false`（默认）：全部 API 返回空/中性，与改动前一致
- `AGENT_MEMORY_VECTOR_ENABLED=false`（默认）：纯结构化检索；开启后使用进程内 hashing 向量重排（无 faiss/chroma 依赖）

## 注入与安全

- 注入摘要经脱敏（密钥模式、路径、邮箱）并限长
- 样本不足时不强化结论（与 skill 权重服务的中性原则一致）
- 无新建持久记忆表；回滚 = revert，无需 drop 表

## 模块

- `src/agent/memory.py` — 门面与兼容 API
- `src/agent/memory_layers.py` — 分层数据结构
- `src/agent/memory_retrieval.py` — 结构化检索 + 注入格式化
- `src/agent/memory_vector.py` — 可选轻量向量重排
