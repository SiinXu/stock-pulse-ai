# Actions 普通用户能力拆分（v1）

> 订阅层（路径 A）体验差异化计划。已建 Issue：https://github.com/SiinXu/stock-pulse-ai/issues/847

关联：#797 #796 #795 #624 #241

## 总表

| 优先级 | 主题 | 状态 |
|--------|------|------|
| P0 | Config Check | #847 |
| P0 | 失败/跳过人话 Summary + 短错误通知 | 待建 |
| P0 | Actions 三行预设文档 | 待建 |
| P1 | 无 IM：GitHub Issue 日报收件箱 | 待建 |
| P1 | simple 报告诚实分层 + 决策结构 | 待建 |
| P1 | alert-only 异动才推 | 待建 |
| P2 | 周复盘 workflow | 待建 |

## Issue 2 — 失败人话 Summary

标题：`[Feature] Actions：Daily Analysis 失败/跳过人话 Summary + 短错误通知`

方案：00-daily-analysis.yml 末尾 always/failure；run_status.json；GITHUB_STEP_SUMMARY；系统错误短通知。
枚举：missing_llm / missing_watchlist / non_trading_day / data_source / timeout / unknown
用户路径：跑分析 → Summary 看原因 → 可选 IM → 改配置或 #847
配置：NOTIFICATION_SYSTEM_ERROR_CHANNELS；可选 FAILURE_NOTIFY_ENABLED；无新 Web 页

## Issue 3 — 三行预设文档

标题：`[Docs] Actions 普通用户三行预设`

最小：LLM_ZHIPU_API_KEY 或 LLM_SILICONFLOW_API_KEY 或 GEMINI_API_KEY；STOCK_LIST；可选 Webhook
路径：Fork → 填 2-3 项 → Config Check → Daily Analysis → IM/Artifact

## Issue 4 — Issue 收件箱

标题：`[Feature] Actions：GitHub Issue 日报收件箱`

REPORT_ISSUE_INBOX_ENABLED（默认 false）；upsert 单条 Daily analysis inbox；参考 upstream-parity；公开仓隐私说明

## Issue 5 — 报告诚实分层

标题：`[Feature] 报告 simple：事实/缺口/推断 + 决策结构`

默认 simple 固定：事实、数据缺口、推断、观察框架；脚注模型与数据源；REPORT_HONESTY_LAYERS 默认 true

## Issue 6 — alert-only

标题：`[Feature] alert-only 模式`

mode=alert-only；复用 #241 规则；无触发不刷屏；Web 扩展现有 Alerts UI

## Issue 7 — 周复盘

标题：`[Feature] Actions 周复盘 Weekly Digest`

01-weekly-digest.yml；汇总近 5 日非全量重跑；样本不足诚实说明

## 顺序

847 → 失败 Summary → 三行文档 → 收件箱 → 分层 → alert-only → 周复盘
