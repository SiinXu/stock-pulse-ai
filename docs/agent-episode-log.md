# Agent 演化 Episode 日志

**状态**：Issue [#1090](https://github.com/SiinXu/stock-pulse-ai/issues/1090) 与预测闭环 Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107) 基础能力

**English**: [agent-episode-log_EN.md](agent-episode-log_EN.md)

## 目的

在 Agent 运行结束后持久化紧凑、可查询的 **episode**，供离线评测、复盘与权重校准重放轨迹；默认不存储密钥、原始 provider 载荷或完整 Soul 章程正文。

关闭功能时不会导入写入器或初始化仓库；开启后，模块加载、数据库初始化、写入与清理失败均不得覆盖 Agent 的成功结果或原始异常。查询与重放输入上限为 200 条，持久化 JSON 损坏会显式报错，绝不伪装成空轨迹。

配置、模块与回滚说明见英文版（与实现保持一致）。
