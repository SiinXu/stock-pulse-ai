# 报告敏感性情景库

版本化情景包，用于报告敏感性分析（Issue [#1136](https://github.com/SiinXu/stock-pulse-ai/issues/1136)，史诗 [#1127](https://github.com/SiinXu/stock-pulse-ai/issues/1127)）。

## 目标

把零散 what-if 沉淀为可复用情景（利率、汇率、行业冲击），并**复用既有 Chat what-if 执行通道**，不另造 Agent 路径。

## 能力

- 预置 + 自定义情景（可保存复用）
- 情景结果明确标注为假设推演（`[HYPOTHETICAL SCENARIO]`），不与基线结论混淆
- 情景目录版本可见（`catalog_version` / `catalog_hash`）
- 切换情景会改变确定性风险表述（供测试断言）
- **不得削弱 Soul** 证据 / 拒绝 / 风险规则

## 实现入口

| 层 | 路径 |
| --- | --- |
| 预置 SSOT JSON | `src/agent/scenario_library_builtins.json`（Web 镜像 `scenarioLibraryBuiltins.json`） |
| 目录与风险投影 | `src/agent/scenario_library.py` |
| what-if 通道扩展 | `src/agent/what_if_scenario.py`（`sector_shock`、`scenario_id`、库附录） |
| 报告挂载 | `report_renderer` + `report_*.j2` 的 `scenario_sensitivity_markdown` |
| Web 情景库与保存 | `apps/dsa-web/src/components/chat/scenarioLibrary.ts` |
| 面板 | `WhatIfScenarioPanel` / `ReportScenarioSensitivityPanel` |

完整英文契约与预设表见：[report-scenario-library_EN.md](report-scenario-library_EN.md)。
