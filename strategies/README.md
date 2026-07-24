# 交易策略目录 / Trading Strategies

本目录存放 **自然语言交易策略文件**（YAML 格式）。系统启动时自动加载此目录下所有 `.yaml` 文件。

对用户和文档，我们继续把这些能力称为“策略”；在代码、配置和 API 字段里，它们统一命名为 `skill`，你可以把它理解为“可复用的策略能力包”。

## 如何编写自定义策略（Strategy Skill）

只需创建一个 `.yaml` 文件，用中文（或任意语言）描述你的交易策略即可，**无需编写任何代码**。

### 最简模板

```yaml
name: my_strategy          # 唯一标识（英文，下划线连接）
display_name: 我的策略      # 显示名称（中文）
description: 简短描述策略用途

instructions: |
  你的策略描述...
  用自然语言写出判断标准、入场条件、出场条件等。
  可以引用工具名称（如 get_daily_history、analyze_trend）来指导 AI 使用哪些数据。
```

### 完整模板

```yaml
name: my_strategy
display_name: 我的策略
description: 简短描述策略适用的市场场景

# 策略分类：trend（趋势）、pattern（形态）、reversal（反转）、framework（框架）
category: trend

# 关联的核心交易理念编号（1-7），可选
core_rules: [1, 2]

# 策略需要使用的工具列表，可选
# 可用工具：get_daily_history, analyze_trend, get_realtime_quote,
#           get_sector_rankings, search_stock_news, get_stock_info
required_tools:
  - get_daily_history
  - analyze_trend

# 可选别名（用于 /ask 等自然语言技能选择）
aliases: [我的战法, 我的模型]

# 以下元数据用于驱动默认行为（可选）
# default_active: 是否属于默认激活技能集
# default_router: 是否属于路由 fallback 技能集
# default_priority: 默认展示/排序优先级，数值越小越靠前
# market_regimes: 该技能优先适配的市场状态标签
default_active: true
default_router: false
default_priority: 100
market_regimes: [trending_up]

# 策略详细说明（自然语言，支持 Markdown 格式）
instructions: |
  **我的策略名称**

  判断标准：

  1. **条件一**：
     - 使用 `analyze_trend` 检查均线排列。
     - 描述你期望看到的趋势特征...

  2. **条件二**：
     - 描述量能要求...

  评分调整：
  - 满足条件时建议的 sentiment_score 调整
  - 在 `buy_reason` 中注明策略名称
```

### 核心交易理念参考

| 编号 | 理念 |
|------|------|
| 1 | 严进策略：乖离率 < 5% 才考虑入场 |
| 2 | 趋势交易：MA5 > MA10 > MA20 多头排列 |
| 3 | 效率优先：量能确认趋势有效性 |
| 4 | 买点偏好：优先回踩均线支撑 |
| 5 | 风险排查：利空新闻一票否决 |
| 6 | 量价配合：成交量验证价格运动 |
| 7 | 强势趋势股放宽：龙头股可适当放宽标准 |

## 自定义策略目录

除了本目录（内置策略），你还可以通过环境变量指定额外的自定义策略目录：

```env
AGENT_SKILL_DIR=./my_skills
```

系统会同时加载内置策略和自定义策略。如果名称冲突，自定义策略覆盖内置策略。

环境变量名仍然是 `AGENT_SKILL_DIR`，这是内部统一命名后的配置入口；在产品语义上，它依然表示“自定义策略目录”。

## 何时使用策略 Skill，何时使用系统插件

- 如果需求只包含自然语言分析规则、提示词、激活元数据，或对现有 Agent 工具的 allowlist，请使用本目录的 YAML，或 `AGENT_SKILL_DIR` 下的 YAML / `SKILL.md`。这类 Skill 不执行 Python，也不能注册新工具或数据源。
- 如果需求必须执行受信任的 Python，并且属于数据源、分析策略、Agent 工具、通知渠道、报告模板或事件 Hook 之一，请先检查[插件扩展机制选择矩阵](../docs/plugin-extension-contract.md#choosing-an-extension-mechanism)及其实现状态。只有已经接入运行时的扩展点可用。
- UI 组件、Settings 面板、自定义命令、远程 marketplace、自动安装依赖、hot reload、connector / MCP 或新的扩展点需要先完成独立设计与 ADR；不要通过策略目录或相近的插件注册项绕过该边界。
