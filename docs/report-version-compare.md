# 报告版本对比

[中文](report-version-compare.md) | [English](report-version-compare_EN.md)

Issue #188 / T18：用户可任选同一标的的两次分析历史，并排查看字段差异与配置指纹差异。

## 能力范围

- 版本选择：`GET /api/v1/report-version-compare/runs?stock_code=...`
- 对比：`GET /api/v1/report-version-compare/compare?stock_code=...&base_run_id=...&target_run_id=...`
- Web 页面：`/research/report-compare`
- **不实现** T17 比较引擎（`src/services/history_comparison_service.py` 中的 `compare_analyses`）

## 状态契约

| status | 含义 |
| --- | --- |
| `ok` | T17 返回 `has_baseline=true` 的 AnalysisDelta |
| `engine_pending` | T17 尚未接线；仍展示并排字段与配置指纹差异。**不等于无变化** |
| `no_baseline` | T17 返回 `has_baseline=false`。**不等于无变化** |
| `incomparable` | 运行不可比（例如标的不一致） |

## 变化分级（展示层）

- **major**：结论动作反转（如 buy/add ↔ sell/reduce/avoid）
- **moderate**：非反转的动作变化、较大评分变化、模型差异等
- **minor**：小幅评分微调或摘要文本漂移
- **none**：字段未变化

配置指纹差异单独成区，避免把「配置不同」误读成「市场变化」。

## Integration Point（T17 合并后）

T17 在 `src/services/history_comparison_service.py` 交付：

```python
def compare_analyses(stock_code: str, base_run_id: str, target_run_id: str) -> AnalysisDelta: ...
```

T18 已通过 `src/services/report_version_compare_adapter.py` 的 `resolve_compare_analyses()` 在运行时自动发现该函数，**无需改 endpoint 签名**。集成者只需确认 T17 已合并且函数可 import。

可选：单测可向 `ReportVersionCompareService(compare_fn=...)` 注入 fixture。

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
