# 助手引导配置（Agent-guided onboarding）

关联 Issue：[#589](https://github.com/SiinXu/stock-pulse-ai/issues/589)

## 目标

用短流程完成 **画像采集 → 配置计划预览 → 确认写入**，避免第一天就把完整设置页砸给用户。计划只教产品配置与研究流程，**不下单、不伪造 API Key**。

## 入口

| 入口 | 行为 |
| --- | --- |
| 首页配置未完成卡片 | 主按钮 **让助手帮我配置**；次按钮 **手动打开设置** |
| 首次运行向导完成页 | 可选 **继续助手引导配置** |
| 之后 | 配置仍不完整时可从首页再次进入；草稿可恢复 |

全程可跳过。画像草稿保存在 `localStorage`，支持中断后继续。

## 画像 schema（`UserOnboardingProfile`）

版本化 JSON（`schema_version = 1`）：

| 字段 | 取值 |
| --- | --- |
| `experience_stage` | `beginner` / `report_reader` / `has_system` |
| `markets` | 多选：`cn` / `hk` / `us` |
| `goals` | 多选：`daily_push` / `pre_post_market` / `holdings_risk` / `strategy_validation` |
| `holdings` | `none` / `watchlist` / `bookkeeping` |
| `interaction` | `push` / `web` / `chat` |
| `risk_tone` | `conservative` / `balanced` / `assertive`（仅语气，非建议） |
| `infrastructure` | `cloud_key` / `local_models` / `free_only` |
| `report_language` | `zh` / `en` / `ko` / `ja` |

## 计划引擎与诚实降级

- **默认引擎：** 确定性规则（`engine: "rules"`）。
- **LLM 润色：** 仅当已有可用模型且用户勾选时有意义；无模型时仍返回规则计划，并给出诚实的 `llm_note`，**不假装 AI**。
- **预设：** 优先复用 W10-03 的 `config_presets`；不可用时使用对齐的内置映射（`local-first` / `cli-backends` / `cloud-balanced` / `power-user`）。

## 写入契约

- 仅通过 `SystemConfigService.update` 写 **非密钥** 配置。
- 密钥类字段永不写入；计划里用 todo + 设置深链提示用户自行粘贴。
- `STOCK_LIST` 为空时可按市场写入种子代码；已有列表不覆盖。
- 应用后状态落在活动 `.env` 同目录的 `onboarding_state.json`。重置只删档案，不回滚已写配置。

## 功能阶段（L0–L3）

| 阶段 | 强调 | 暂缓 |
| --- | --- | --- |
| L0 冷启动 | 首页、分析工作台、模型/自选 | 完整信号中心、委员会、插件 |
| L1 日报读者 | 历史、大盘复盘、通知 | 复杂告警规则 |
| L2 持仓用户 | 组合、基础价格提醒 | Multi-Agent、自定义 Skill |
| L3 研究用户 | 对话、信号、回测 | 高成本委员会默认关闭 |

阶段影响推荐文案与首页「今日计划」卡片，**不硬删路由**。

## API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/v1/onboarding/plan` | 生成计划 |
| `POST` | `/api/v1/onboarding/apply` | 写入非密钥配置并持久化档案 |
| `GET` | `/api/v1/onboarding/state` | 读取持久化状态 |
| `DELETE` | `/api/v1/onboarding/state` | 重置档案（保留配置） |

## 免责声明

引导配置只服务产品上手与研究流程教学，**不构成投资建议**，也不把买卖指令作为必做步骤。

## 回滚

- 隐藏首页 CTA / 向导按钮即可关闭入口。
- 删除 `onboarding_state.json` 或调用 `DELETE /api/v1/onboarding/state`。
- 已写入的非密钥配置保留在 Settings 中，可手动改回。
