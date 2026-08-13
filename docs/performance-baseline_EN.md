# Performance Baselines and Profiling (Issue #227)

Offline, reproducible performance baselines for **key analysis paths**, plus an opt-in span collector and a local cProfile entry point.

## Scope

| Path | Offline workload | Production hook |
| --- | --- | --- |
| Data fetch / normalize indicators | `data_fetch_indicators` — `BaseFetcher._calculate_indicators` on **750** synthetic daily bars | Pipeline stage `fetch` mirrored when collection is active |
| Analysis run | `analysis_trend` — `StockTrendAnalyzer.analyze` on **750** bars × multiple iterations | Pipeline stage `analyze` mirrored when collection is active |
| Report generation | `report_generate` — single-stock + multi-stock daily report for **12** synthetic results | Pipeline stage `render` mirrored when collection is active |

Workloads intentionally use multi-year bar counts and multi-stock report batches so baselines are not “pretty microbenchmarks.”

**Not this work:** live LLM/network latency baselines, a full metrics platform, or a dedicated slow-run Web UI.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `PERF_COLLECTION_ENABLED` | `false` | Opt-in span recording. When off, helpers are no-ops. |
| `PERF_PROFILE_ENABLED` | `false` | Documents intent for offline tooling; does **not** auto-wrap production requests. |

## Local entry points

```bash
python scripts/run_perf_baseline.py --list
python scripts/run_perf_baseline.py
python scripts/run_perf_baseline.py --write-baseline
python scripts/run_perf_baseline.py --compare
python scripts/run_perf_baseline.py --compare --strict
python scripts/run_perf_baseline.py --profile --profile-out /tmp/perf.pstats
```

Committed baseline: `tests/perf/baselines/offline_key_paths.json`

## CI impact

| Suite | Behavior |
| --- | --- |
| Default offline / `backend-gate` | Fast **unit** tests only. **No** wall-clock fail. |
| `pytest -m benchmark` / `.github/workflows/benchmarks.yml` | Optional wall-clock compare vs baseline (non-blocking). |

## Related

- [Agent observability L0](agent-observability_EN.md)
- [Offline agent evaluation benchmark](agent-eval-benchmark_EN.md)
- Chinese: [performance-baseline.md](performance-baseline.md)
