# 有界 AI 候选发现

- 状态：`Living`
- 最近核对：2026-08-12
- 关联：Issues #177、#325；[英文版](candidate-discovery.md)；[AlphaSift 集成](alphasift-integration.md)

## 目的

在**现有** Research Discover 选股页（`/research/discover`）增加 AI 候选发现能力，不新建路由。用户可在**显式、可分页**的宇宙上用自然语言或结构化条件生成短名单，再转入深度分析或自选。

## 非目标

- 无界全市场行情扫描
- 替换 AlphaSift 策略选股（策略模式仍保留）
- 交易指令或组合优化

## 宇宙

| 宇宙 | 来源 | 分页 |
| --- | --- | --- |
| `watchlist` | 配置中的自选列表 | page / page_size |
| `portfolio` | 缓存持仓 | page / page_size |
| `index` | 本地股票索引（`stocks.index.json`） | page / page_size |
| `codes` | 请求显式代码（最多 100） | 单页 |

单次运行硬上限：

- 返回数量：最多 30（默认 10）
- 每页大小：最多 100
- 评估标的：最多 200
- data_provider 行情调用：最多 50（默认 20）
- 可选 LLM 解释：批量 1 次（预算上限 2）

## API

- `POST /api/v1/discover/screen` — 同步发现
- `POST /api/v1/discover/screen/tasks` — 后台任务（202）
- `GET /api/v1/discover/screen/tasks/{task_id}`
- `POST /api/v1/discover/screen/tasks/{task_id}/cancel`

响应包含：

- `candidates[]`：`reason` / `reason_codes`（及可选 `llm_thesis`）
- `universe_contract`：解析 / 过滤 / 评估数量与截断
- `cost_contract`：provider/LLM 调用、耗时、bounded 标记
- `research_disclaimer`：研究免责声明

## 数据路径

1. 解析宇宙分页（本地索引 / 自选 / 持仓，不做全市场扫描）。
2. 规则解析自然语言 → 条件（市场、关键词、涨跌幅/成交额阈值、排除 ST）。
3. 仅在 `max_provider_calls` 内通过 `DataFetcherManager`（data_provider）取行情。
4. 评分排序，返回可解释短名单；可选 LLM 批量润色。
5. 任务模式下在标的间检查取消。

## Web

Research Discover 模式切换：

- **AI 发现**（默认）：NL/条件面板、取消、成本摘要、分析 / 加入自选
- **策略选股**：既有 AlphaSift 策略流（需 `ALPHASIFT_ENABLED`）

页头在 AI 发现模式下展示“AI 发现可用（有界）”，**不依赖** AlphaSift 开关。

## 回滚

回退对应 PR，或停止调用 `/api/v1/discover/*` 并隐藏 AI 发现模式。无迁移、无新增必填环境变量。
