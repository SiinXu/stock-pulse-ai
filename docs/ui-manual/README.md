# StockPulse 界面操作手册

> **范围**：Web 工作台与桌面客户端的界面操作。  
> **不包含**：部署、Docker、GitHub Actions、环境变量清单、服务器运维。  
> 安装与首次填 Key 见 [客户端安装与配置](../beginner-client-setup.md)（[English](../beginner-client-setup_EN.md)）；部署见 [完整配置与部署指南](../full-guide.md)。

第一次打开 StockPulse 时，你可能还不熟股票代码写法，也不清楚「分析」「信号」「持仓」分别做什么。下面按使用顺序拆开讲：点哪里、会看到什么、接下来怎么走。

界面文案若和手册不一致，以你屏幕上的为准。

> 产品输出仅供学习与研究，**不构成投资建议**。真实买卖请自行判断风险与合规要求。

## 建议阅读顺序（按阶段）

```mermaid
flowchart LR
  A[安装与填 Key] --> B[认识壳层与首页]
  B --> C[跑通第一份分析]
  C --> D[学会读报告]
  D --> E[日常 5 分钟工作流]
  E --> F[信号 / 持仓 / 回测进阶]
```

| 你现在的阶段 | 先读 | 然后 |
| --- | --- | --- |
| 还没装好 / 还没有模型 Key | [客户端安装](../beginner-client-setup.md)（[EN](../beginner-client-setup_EN.md)） | 本手册 01 → 02 |
| 已经能打开界面 | [01 壳层](01-shell.md)、[02 首页](02-home.md) | [03 分析工作台](03-analysis-workbench.md) |
| 已经跑出报告 | [08 阅读报告](08-reading-reports.md) | [11 日常工作流](11-daily-workflows.md) |
| 想盯盘或记账 | [06 信号中心](06-signals.md)、[07 持仓](07-portfolio.md) | [09 回测](09-backtest.md) |

不必一次读完。多数人第一周只需要 **01 + 02 + 03 + 08 + 11**。

## 模块一览

| 模块 | 说明 |
| --- | --- |
| [01 壳层与全局操作](01-shell.md) | 导航、命令面板、通知铃、语言与主题 |
| [02 首页](02-home.md) | 今日焦点、待办、配置缺口提示 |
| [03 分析工作台](03-analysis-workbench.md) | 发起分析、任务进度、历史与对比 |
| [04 大盘复盘](04-market-review.md) | 触发复盘、阅读复盘历史 |
| [05 问股对话](05-agent-chat.md) | Agent 多轮追问与策略选择 |
| [06 信号中心](06-signals.md) | AI 建议池、告警规则、推送历史与再评估（**不在一级侧栏**；铃铛 / 命令面板 / `/signals`） |
| [07 持仓](07-portfolio.md) | 侧栏「组合」；账户、记账、导入、风险与一键分析 |
| [08 阅读报告](08-reading-reports.md) | 个股报告阅读顺序与字段含义 |
| [09 回测](09-backtest.md) | 历史建议事后验证 |
| [10 设置](10-settings.md) | 模型、自选、通知、数据源等界面操作 |
| [11 日常工作流](11-daily-workflows.md) | 推荐用法与界面常见问题 |

## 入门术语速查

| 术语 | 一句话解释 |
| --- | --- |
| **自选股（Watchlist）** | 你关心的股票代码列表，系统会按它做批量分析或首页摘要 |
| **个股分析** | 针对**一只**股票生成研究报告（技术面、资讯、风险、建议等） |
| **大盘复盘** | 对整个市场（如 A 股）的盘面摘要，不是单只股票买卖建议 |
| **信号（Decision Signal）** | 系统从分析报告里提炼出的、可查询的「建议资产」，方便事后核对 |
| **策略 / Skill** | 可选的分析风格包（例如更偏趋势或更偏质量），不选则用默认 |
| **支撑 / 压力** | 价格下方可能被买盘托住的区域叫支撑；上方可能遇卖压的区域叫压力 |
| **止损** | 预先想好的「错了就认错离场」的价格或条件，用于控制亏损 |
| **界面语言 vs 报告语言** | 前者改按钮和菜单；后者改报告正文语言，二者**互不影响** |
| **组合 vs 持仓** | 侧栏导航名多为「组合」；页面标题多为「持仓」——同一模块 |
| **Agent vs 问股** | 侧栏多为「Agent」；页面标题多为「问股」——同一模块 |

更完整的金融用词治理见 [多语言金融术语指导](../financial-terminology-guide.md)。

## 语言版本

| 手册语言 | 文件 |
| --- | --- |
| 简体中文（源） | `NN-topic.md`、`README.md` |
| English | `NN-topic_EN.md`、`README_EN.md` |

- 产品界面另支持 zh-TW / ja / ko / de / es / fr / id / ms 等；**操作手册**当前以简中 + English 维护，与产品 `locales` 分开。
- 界面语言在壳层切换；读手册时请对照你当前 UI 语言下的标签。约定见 [TRANSLATION.md](TRANSLATION.md)。
- 安装上手（桌面客户端）：[客户端安装](../beginner-client-setup.md) · [English](../beginner-client-setup_EN.md)

## 文档维护说明（给贡献者）

- 本手册只写「怎么点界面」，不写部署与密钥运维。
- 发现界面标签与手册不一致时，以**线上界面**为准，并开文档 PR 修正。
- 模块文档写清入口路径、术语、步骤、案例与相邻模块。
- **有 UI / 路由 / 文案变更的 PR**：同一变更列车内检查并更新对应 `docs/ui-manual/*` 分册与本 README 导航表；中英成对修改。
- 对照源码时优先核对：`apps/dsa-web/src/routing/routes.ts`、`components/layout/navigation.ts`、`i18n/uiText.ts`、设置 IA `settingsInformationArchitecture.ts`、选股文案 `locales/screening.ts`。
