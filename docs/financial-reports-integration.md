# 财务报表接入基本面分析（Issue #235）

## 范围

- **首版优先 A 股**：经既有 `DataFetcherManager.get_fundamental_context` → `AkshareFundamentalAdapter` 路径扩展，**不**另起并行基本面管道。
- HK/US 仍走 `YfinanceFundamentalAdapter`；仅叠加 `sufficiency` / `data_recency` 等诚实元数据，不改变原有摘要字段。
- 单源失败 fail-open：不影响技术面 / 新闻 / 主分析链路。

## 数据流

1. `get_fundamental_context(code)`（manager 缓存 / 超时 / 重试沿用既有配置）
2. A 股 bundle：`stock_financial_abstract`（及 indicator 候选）→ 多期解析
3. 若摘要缺多期、经营现金流或资产负债表字段，再 best-effort 拉：
   - 利润表 `stock_profit_sheet_by_report_em`（`SH600519` 形态）
   - 资产负债表 `stock_balance_sheet_by_report_em`
   - 现金流量表 `stock_cash_flow_sheet_by_report_em`
   - THS 候选作降级
4. `src/services/financial_reports_service.py` 归一化 periods、派生指标、充分性
5. 写入 `earnings.data.financial_report`（旧键保留）
6. 分析 Prompt（`analyzer_parts/analysis.py`）与报告渲染（`notification_parts/rendering.py`）消费

## `financial_report` 契约（附加字段）

| 字段 | 含义 |
|------|------|
| `report_date` / `revenue` / `net_profit_parent` / `operating_cash_flow` / `roe` / `currency` | 既有摘要（兼容） |
| `periods[]` | 多期事实行（新→旧） |
| `statements` | income / balance / cash_flow / abstract 覆盖 |
| `metrics.*` | `{value, formula, basis}`；`value` 可为 `null` |
| `sufficiency` | `rich` \| `partial` \| `insufficient` + `message` / `missing_fields` |
| `data_recency` | 报告期非实时说明 |

## 派生指标公式（唯一文档源）

见 `src/services/financial_reports_service.py` 模块 docstring：

- **YoY**：`(latest - prior_year_same) / abs(prior_year_same) * 100`（同月日优先；**禁止**用环比冒充同比）
- **毛利率**：`gross_profit / revenue * 100`（或数据源原样）
- **净利率**：`net_profit_parent / revenue * 100`
- **经营现金流/净利润**：`operating_cash_flow / net_profit_parent`
- **资产负债率**：`total_liabilities / total_assets * 100`

## 诚实性

- 缺数 / 部分字段 → `sufficiency.level` 为 `partial` 或 `insufficient`，文案含 **insufficient fundamentals**。
- 禁止静默填 0；N/A 必须表述为缺失。
- Prompt 区分事实表与 `fundamental_analysis` 推理。

## 配置

沿用既有：

- `ENABLE_FUNDAMENTAL_PIPELINE`
- `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS` / `FUNDAMENTAL_FETCH_TIMEOUT_SECONDS`
- `FUNDAMENTAL_RETRY_MAX` / `FUNDAMENTAL_CACHE_TTL_SECONDS` / `FUNDAMENTAL_CACHE_MAX_ENTRIES`

无需新环境变量。

## 测试

- `tests/services/test_financial_reports_service.py`
- `tests/data_provider/test_financial_statements_adapter.py`
- `tests/notification/test_financial_report_rendering.py`
- Fixtures：`tests/fixtures/financial_reports/`
