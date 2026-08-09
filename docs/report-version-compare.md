# 报告版本对比

[中文](report-version-compare.md) | [English](report-version-compare_EN.md)

Issue #188 / T18 基础能力：用户可分页浏览分析历史，选择同一标的的两次运行，并排查看类型化的报告与配置差异。Issue #188 仍保留现有报告/历史页面入口与可选多智能体区块等后续范围。

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

## 导航接线（可选）

本任务未改 `SidebarNav` / `ResearchOverviewPage`（批次冻结或争用）。合并后可在研究总览追加入口：

```tsx
// ResearchOverviewPage RESEARCH_DESTINATIONS
{
  key: 'report-compare',
  titleKey: /* new i18n key */,
  descriptionKey: /* new i18n key */,
  to: APP_ROUTE_PATHS.researchReportCompare,
  icon: GitCompareArrows,
}
```

## 相关文件

- `src/services/report_version_compare_service.py`
- `src/services/report_version_compare_adapter.py`
- `api/v1/endpoints/report_version_compare.py`
- `apps/dsa-web/src/pages/ReportVersionComparePage.tsx`
- `apps/dsa-web/src/components/report-version-compare/`
