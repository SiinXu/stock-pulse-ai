# 性能基线与剖析基础设施（Issue #227）

为**关键分析路径**提供可离线复现的性能基线、可关闭的 span 采集，以及本地 cProfile 入口。

## 范围

| 路径 | 离线 workload | 生产钩子 |
| --- | --- | --- |
| 数据获取 / 指标计算 | `data_fetch_indicators`（750 根合成日 K） | 采集开启时镜像 `fetch` |
| 分析运行 | `analysis_trend`（`StockTrendAnalyzer`） | 镜像 `analyze` |
| 报告生成 | `report_generate`（12 条合成结果） | 镜像 `render` |

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PERF_COLLECTION_ENABLED` | `false` | 按需记录 span；关闭时为 no-op |
| `PERF_PROFILE_ENABLED` | `false` | 仅表达离线剖析意图 |

## 本地入口

```bash
python scripts/run_perf_baseline.py
python scripts/run_perf_baseline.py --write-baseline
python scripts/run_perf_baseline.py --compare --strict
python scripts/run_perf_baseline.py --profile
```

基线文件：`tests/perf/baselines/offline_key_paths.json`

English: [performance-baseline_EN.md](performance-baseline_EN.md)
