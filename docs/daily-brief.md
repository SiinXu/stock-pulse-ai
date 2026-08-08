# 每日简报（历史准确率复盘）

> English: [daily-brief_EN.md](daily-brief_EN.md)

面向 Issue [#466](https://github.com/SiinXu/stock-pulse-ai/issues/466)：在生成新的每日内容前，先复盘既有预测/决策的历史准确率，形成「预测—验证」闭环。

## 能力边界

- **默认关闭**（`DAILY_BRIEF_ENABLED=false`）。开启后由运行时调度器后台任务按本地日历日最多触发一次。
- 内容来源：
  1. **昨日分析**：`AnalysisHistory` 中按配置时区映射到「昨天」的记录（排除 `market_review` / `daily_brief` 自身）
  2. **今日关注列表**：`STOCK_LIST` 覆盖情况（是否昨日已有分析）
  3. **历史准确率**：只**读取**既有结果，不新建评估引擎
     - 决策信号 outcome（`DecisionSignalOutcomeService` / 已落库 stats）
     - 回测 overall summary（`BacktestService.get_summary`）
     - 技能观点表现只读 API（`SkillOpinionPerformanceService.get_stats`）
- **诚实规则**：任一数据源样本不足时，简报**明确写出**样本不足，**绝不编造**命中率/准确率百分比。
- 投递：沿用现有 `NotificationService.send`（`route_type=report`）与 `save_analysis_history`；**任一通知渠道失败不会中断**简报生成与落库。

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DAILY_BRIEF_ENABLED` | `false` | 总开关 |
| `DAILY_BRIEF_SCHEDULE_TIME` | `08:30` | 本地 HH:MM，到达后可触发 |
| `DAILY_BRIEF_TIMEZONE` | `Asia/Shanghai` | 日程与「昨天」映射时区 |
| `DAILY_BRIEF_MIN_SAMPLES` | `10` | 发布百分比前的最小完成样本 |
| `DAILY_BRIEF_NOTIFY` | `true` | 是否走通知分发 |
| `DAILY_BRIEF_PERSIST_HISTORY` | `true` | 是否写入分析历史（`report_type=daily_brief`） |
| `DAILY_BRIEF_SAVE_REPORT_FILE` | `true` | 是否保存 Markdown 文件 |

## 调度

- 与 Event Monitor 类似：注册名为 `daily_brief` 的后台任务，轮询间隔 60 秒（调度器下限 30 秒）。
- 每个本地自然日在 `DAILY_BRIEF_SCHEDULE_TIME` 之后最多成功生成一次；内存与历史表双重去重。
- CLI `--schedule` 路径与 `RuntimeSchedulerService` 长驻路径均会在开关打开时注册。

## 模板与历史

- 模板：`templates/daily_brief.j2`
- 历史代码：`DAILY_BRIEF`，`report_type=daily_brief`

## 与预留「每日摘要」开关的关系

`NOTIFICATION_DAILY_DIGEST_ENABLED` 仍是 P4 **预留**噪声控制开关，**不会**发送摘要。本功能使用独立的 `DAILY_BRIEF_*` 配置。

## 相关

- [通知](notifications.md)
- [决策信号](decision-signals.md)
- [技能观点 outcome](skill-opinion-outcome-evaluation.md)
- [定时任务](scheduled-tasks.md)
