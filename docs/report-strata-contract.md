# 报告证据分层合同

[中文](report-strata-contract.md) | [English](report-strata-contract_EN.md)

## 目的

Issue #616 要求分析报告以**固定证据分层**呈现内容，避免把模型流畅叙述误读为已核实投资事实。这是呈现与 payload 合同，**不**替代 #127 的可导出审计包。

## 六层（产品顺序）

1. **已核实事实** — 可选 `source_id` / `as_of`
2. **缺失数据或来源冲突** — 不得并入事实层
3. **模型推断**
4. **风险与反证**
5. **与个人框架对齐** — 复用 #465 本地框架槽位；无 active 框架时 `not_configured`（预期空槽，非分析失败）；有 active 框架时个股分析路径会填充只读研究上下文与对齐摘要
6. **非投资建议声明** — 面向用户的格式始终可见（报告级页脚 / Web 面板）

## Schema

- 领域模型：`src/schemas/report_strata.py`（`report-strata-v1`）
- 加性字段：优先 `dashboard.report_strata`，兼容顶层 `report_strata`
- 历史报告可完全省略该字段并仍可渲染
- 外层 `AnalysisReportSchema` 仍为 `report-v1`；分层自带 `schema_version`

## 新分析产物

成功 JSON 解析路径会调用 `attach_report_strata_to_dashboard`：若 LLM 已输出分层则规范化填充；否则写入空六层结构（无 active 框架时 `not_configured` + 免责声明），再由 `enrich_dashboard_framework_alignment` 在有 active 框架时填充对齐槽。这保证**新 run 的持久化/渲染 payload 始终带有六层槽位**，不等同于 LLM 已填满事实条目，也不表示模型已保证遵守全部框架规则。

## 渲染

| 表面 | 行为 |
| --- | --- |
| Markdown / brief / WeChat | 有 strata 时输出 1–5 层；免责声明统一在报告级页脚一次输出 |
| Web 完整报告 | 同样 1–5 顺序 + 免责声明面板；无 strata 时仅免责声明 |
| API `ReportDetails.report_strata` | 从 `raw_result`/dashboard 解析后投影（analysis / history / status） |

## Fixtures

见 `tests/fixtures/report_strata/`（空来源、冲突、缺时间戳、历史无分层、含分层新报告）。

## 范围外

- #127 审计 zip
- 多租户
- 交易 alpha 保证
