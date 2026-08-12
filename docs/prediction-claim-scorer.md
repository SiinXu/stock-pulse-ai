# 确定性预测声明打分器（ClaimScorer）

**状态**：预测验证与演进链路 A5，对应 issue [#1111](https://github.com/SiinXu/stock-pulse-ai/issues/1111) / [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)

**English**: [prediction-claim-scorer_EN.md](prediction-claim-scorer_EN.md)

**依赖**：A1 预测契约（[prediction-contract.md](prediction-contract.md)）

## 目的

在**固定**结构化声明与行情实际值给定时，确定性输出逐条命中结果与聚合指标，服务 Agent 质量运营（研究 / 校准）。**不是**收益保证产品面。

```text
ClaimScorer.score(claims, actuals, config) → claim_results + aggregate
```

* 打分器内部无 I/O、无墙钟时间、无随机源。
* 相同输入始终得到相同 `to_dict()` 结果。
* 实际值缺失 / 非有限 → `data_unavailable` 且 `score=None`，**永不伪造命中**。

## 模块位置

| 路径 | 职责 |
| --- | --- |
| `src/schemas/prediction_record.py` | A1 声明类型（`PredictionClaim` 与 payload） |
| `src/schemas/prediction_claim_scoring.py` | 实际值 / 配置 / 结果 / 聚合记录 |
| `src/services/claim_scorer.py` | 纯 `ClaimScorer` |
| `tests/services/test_claim_scorer.py` | 表驱动与确定性测试 |

## 支持的声明类型（A1）

| `type` | 载荷 | 所需实际值 |
| --- | --- | --- |
| `direction` | `up` \| `down` \| `sideways` | `start_price`, `end_price` |
| `return_bucket` | `low_pct` &lt; `high_pct` 与 inclusive 标志 | `start_price`, `end_price` |
| `level_break` | `side`, `level`, `reference` | 优先高低点；否则 `end_price` |
| `vol_regime` | 体制标签 | `vol_regime` |
| `custom` | `metric` + `operator` + 机器 `expected` | `metrics[metric]` |

早期方案中的 `price_range` 用 `custom` + `operator=in_range`（度量通常为 `end_price`）表达。

## 结果与分数

| 结果 | 数值分 | 含义 |
| --- | --- | --- |
| `hit` | `1.0` | 按类型规则命中 |
| `partial` | `0.5` | 近边界 / sideways 带 / 邻近幅度或波动体制 |
| `miss` | `0.0` | 明确未中或声明非法 |
| `data_unavailable` | `None`（不计入比率） | 实际值不足或显式 `unavailable_reason` |

### 边界约定

* **方向 sideways 带**：`|收益小数| <= sideways_epsilon`（含边界；默认 0.1%）。`flat_epsilon` 为别名。
* **收益桶**：遵循 A1 的 inclusive 标志（默认半开 `[low, high)`）。`0.0` 是合法有限边界。
  * **开区间上界 + 默认 margin**：恰落在 exclusive 边界时距离为 0；默认 `bucket_partial_margin_pct=1.0` 记为 **partial**，仅当 margin 为 `0` 时为 **miss**。
* **关键位突破**：绝对价或相对 as_of 收盘百分比；近触碰为 partial。
* **波动体制**：规范标签精确匹配为 hit；`low`↔`normal`↔`high`↔`elevated` 相邻为 partial。缺失 → `missing_vol_regime`；非规范脏标签 → `invalid_vol_regime` / `data_unavailable`（**不是** miss）。
* **custom**：`eq|ne|gt|gte|lt|lte|in_range`；`in_range` 为半开区间。

非法 claim（A1 校验失败）为 `miss` + `reason=invalid_claim`，并在 `details.validation_error` 中保留截断诊断信息，仍永不 hit。

聚合校准中的 `brier_score` 为 soft-label（partial 目标 `0.5`），不是经典二元 Brier。

## 明确非目标

* 不修改 Agent Soul charter 或 ToolSurface 拒绝项。
* 不从非结构化散文发明可验证声明。
* 不直接调用行情 provider。
* 不与离线 agent 输出评测或 skill-opinion 信号评估混用语义。

## 验证

```bash
python -m pytest tests/services/test_claim_scorer.py -q
```
