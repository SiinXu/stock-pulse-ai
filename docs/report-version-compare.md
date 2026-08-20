# 报告版本对比

[中文](report-version-compare.md) | [English](report-version-compare_EN.md)

Issue #188 / T18：用户可从分析历史选择同一标的的两次运行，或从个股详情进入版本对比，并排查看类型化的报告与配置差异。可选的多智能体、结构化风险与催化区块现在有明确的诚实对照：缺失会标成缺失，而不会被当成“两边都为空所以相同”。Issue #188 仍保留比 T17 列表差异更深层的结构化 risk/catalyst 条目展示等后续范围。

## 能力范围

- 版本选择：`GET /api/v1/report-version-compare/runs?stock_code=...`
- 对比：`GET /api/v1/report-version-compare/compare?stock_code=...&base_run_id=...&target_run_id=...`
- Web 页面：`/research/report-compare`
- 复用已合并的 T17 比较引擎（`src/services/history_comparison_service.py` 中的 `compare_analyses`），T18 不复制比较逻辑
- 版本身份统一使用唯一的 `AnalysisHistory.id`；`query_id` 只作为可重复的关联元数据
- 未显式指定报告类型时，在计数与分页前排除 `market_review`

## 状态契约

| status | 含义 |
| --- | --- |
| `ok` | T17 返回 `has_baseline=true` 的 AnalysisDelta |
| `engine_pending` | 合并后的引擎在运行时不可用；仍展示并排字段与配置来源。**不等于无变化** |
| `no_baseline` | T17 返回 `has_baseline=false`。**不等于无变化** |
| `incomparable` | 运行不可比（例如标的不一致） |

## 可选区块诚实对照

`optional_sections` 始终返回完整的三行投影（`catalysts`、`structured_risk`、`multi_agent`）。“已产出”表示持久化运行里存在该区块键（即使列表为空）；“未产出”表示该区块从未生成。`multi_agent` 仅统计可选的 `dashboard.bull_bear_debate` 与 `dashboard.committee_deliberation`；编排器必写的 `dashboard.risk_manager` 风控门禁不计入。

| comparison_status | 含义 |
| --- | --- |
| `both_missing` | 两次运行都未产出该区块。**不等于**两边都是空内容所以相同 |
| `base_missing` | 基线未产出，对比版本产出了 |
| `target_missing` | 对比版本未产出，基线产出了 |
| `present_identical` | 两边都产出，且可比内容相同 |
| `present_different` | 两边都产出，且内容不同 |

该面板补充 T17 AnalysisDelta 的列表差异，不替代自动 delta 报告，也不会给“一侧从未产出的区块”编造条目级 added/removed。

## 变化分级（展示层）

- **major**：结论动作反转（如 buy/add ↔ sell/reduce/avoid）
- **moderate**：非反转的动作变化、较大评分变化、模型差异等
- **minor**：小幅评分微调或摘要文本漂移
- **none**：字段未变化

配置指纹差异单独成区，避免把「配置不同」误读成「市场变化」。只有持久化记录具备模型、报告、provider 路由、model 路由、配置 profile 与配置版本等必需来源时才生成指纹；来源不完整时明确显示 `unknown`，不会误报为相同。

## 身份与类型化差异契约

T17 在 `src/services/history_comparison_service.py` 交付：

```python
def compare_analyses(stock_code: str, base_record_id: int, target_record_id: int) -> AnalysisDelta: ...
```

HTTP API 为兼容保留 `base_run_id` / `target_run_id` 参数名，但参数值是历史主键，并以整数传给 T17。公开投影保留基线状态/原因、主键、trace query ID、标的/报告身份、实质变化标记、类型化标量变化与类型化证据/风险列表变化。持久化评分若不是 0–100 范围内的有限数则投影为 `null`；完整响应满足 strict JSON。

可选：单测可向 `ReportVersionCompareService(compare_fn=...)` 注入 fixture。

## Web 恢复与历史深度

- 版本选择器每页加载 50 条稳定倒序记录，并在未达到服务端总数时显示“加载更多版本”。
- 草稿股票输入与已加载标的身份分离；编辑草稿会使旧选择与结果失效。
- Retry 归失败操作所有：列表失败重放列表请求；对比失败按原参数重放对比，不重新加载版本或清空有效选择。

## 导航与预填

- 分析工作台的 History 区在选中同一股票的两条记录后显示“开始对比”，并携带股票代码、基线历史主键和目标历史主键进入对比页。
- 个股详情页提供“报告版本对比”入口，并携带规范化后的股票代码进入对比页。
- 页面接受 `stock`、`baseRunId`、`targetRunId` 查询参数。`stock` 会触发版本加载；两条运行 ID 都是正安全整数且不相同时，加载成功后自动开始对比。
- 无效或缺失的运行 ID 不会触发自动对比，用户仍可在已加载的版本选择器中手动选择。

## 相关文件

- `src/services/report_version_compare_service.py`
- `src/services/report_version_compare_optional_sections.py`
- `src/services/report_version_compare_adapter.py`
- `src/api/v1/endpoints/report_version_compare.py`
- `apps/dsa-web/src/pages/ReportVersionComparePage.tsx`
- `apps/dsa-web/src/components/report-version-compare/`
