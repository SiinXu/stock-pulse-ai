# Agent 演化 Episode 日志

**状态**：Issue [#1090](https://github.com/SiinXu/stock-pulse-ai/issues/1090) 与预测闭环 Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107) 基础能力

**English**: [agent-episode-log_EN.md](agent-episode-log_EN.md)

## 目的

在 Agent 运行结束后持久化紧凑、可查询的 **episode**，供离线评测、复盘与权重校准重放轨迹；默认不存储密钥、原始 provider 载荷或完整 Soul 章程正文。

配置、模块与回滚说明见英文版（与实现保持一致）。
