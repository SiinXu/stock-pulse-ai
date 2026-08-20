# 运行诊断与数据可靠性 1.0（Phase 1）

本文档记录 #1391 Phase 1 的最小运行时落地范围：统一 `trace_id`，并为首批关键数据链路记录结构化 provider 尝试。

## 本轮范围

- API / Web 异步任务创建时，`TaskInfo` 使用 `task_id` 作为默认 `trace_id`。
- 任务列表、任务状态与 SSE 事件追加 `trace_id` 字段；旧客户端可忽略该字段。
- 同步分析使用本次 `query_id` 作为默认 `trace_id`。
- pipeline 运行时建立轻量诊断上下文，贯穿日线准备与单股分析。
- `src/data_provider/base.py` 对以下链路记录 `ProviderRun` 风格事件：
  - `daily_data`
  - `realtime_quote`
- 诊断记录写入内存上下文，随分析 `context_snapshot.diagnostics` 保存；旧历史记录缺少该字段时保持兼容。

## `ProviderRun` 字段

首版字段保持最小：

- `trace_id`
- `data_type`
- `provider`
- `operation`
- `success`
- `latency_ms`
- `error_type`
- `error_message_sanitized`
- `fallback_to`
- `record_count`
- `created_at`

错误摘要会做基础脱敏，避免输出 token、API key、Authorization、Cookie、包含敏感参数的 webhook URL 等内容。

## 模块布局（#1076）

`src.services.run_diagnostics` 仍是唯一对外 facade。实现按只读职责拆到：

- `src/services/diagnostics/schema.py`：稳定 schema、脱敏与序列化
- `src/services/diagnostics/collect.py`：只读采集（写入诊断上下文，不改分析输入/结果/全局业务状态）
- `src/services/diagnostics/export.py`：摘要与 `copy_text` 投影

旧 import、snapshot / summary 字段形状、序列化与 fail-open 异常行为保持不变。消费者继续从 facade 导入，不要直接依赖内部包路径。

## 冻结 schema 契约（#1076 第一切片）

公开 schema 仍由 facade 再导出。权威字段名与状态词在 `src/services/diagnostics/schema.py`：

- `DIAGNOSTIC_SNAPSHOT_KEYS`：`RunDiagnosticContext.snapshot()` 始终包含的键。`prompt_artifact_versions` / `prompt_version` / `skill_versions` 仅在绑定 prompt 产物时附加。
- `ProviderRun.to_dict()`：必有 `trace_id` / `data_type` / `provider` / `operation` / `success` / `created_at`；`None` 的可选字段不序列化。
- `DataQualityEvidenceRecord.to_dict()`：`symbol` / `provider` 即使为 `None` 也会写出；空 `provenance` 省略。
- `RunDiagnosticSummary.to_dict()`：总体状态为 `normal` / `degraded` / `failed` / `unknown`；组件键为 `realtime_quote` / `daily_data` / `news` / `data_quality` / `llm` / `notification` / `history`；组件状态为 `ok` / `degraded` / `failed` / `unknown` / `not_configured` / `skipped`。`copy_text` 始终存在。

### 变异风险

- `sanitize_diagnostic_*` 必须返回新容器，不得改写调用方 mapping / list / 嵌套对象。
- `to_dict()` 必须拷贝嵌套 `dict` / `list`，避免 snapshot 或摘要字典回写诊断对象。
- 采集 / 导出可以写入诊断上下文，但不得改分析输入、分析 outcome 或其嵌套 `window` / `notes` 对象。
- 本切片不拆 collect / export 业务逻辑；后续切片再收敛只读采集 API 与导出投影。

## 稳定性边界

- 诊断记录失败只记录 warning，不影响主分析、数据源 fallback 或历史保存。
- 采集路径不得改变分析 outcome、输入对象或无关的全局运行状态。
- 本轮不新增配置项，不改变数据源优先级，不改变 fallback 策略。
- 本轮不新增 Web 展示组件；`trace_id` 和 provider runs 先进入 API/SSE/历史快照，供后续 Phase 2/3 聚合与展示复用。

## 验证建议

```bash
python -m pytest tests/test_run_diagnostics_p1.py tests/test_analysis_api_contract.py::AnalysisApiContractTestCase::test_get_analysis_status_normalizes_completed_queue_result_contract
python -m py_compile src/services/run_diagnostics.py src/services/diagnostics/schema.py src/services/diagnostics/collect.py src/services/diagnostics/export.py src/services/task_queue/__init__.py src/services/analysis_service.py src/core/pipeline.py src/data_provider/base.py src/api/v1/schemas/analysis.py src/api/v1/endpoints/analysis.py
```
