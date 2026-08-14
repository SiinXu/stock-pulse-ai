# 研报资产包导出

一键导出可离线阅读的研报资产包（Issues #988 / #1140）。English: [research-pack-export_EN.md](research-pack-export_EN.md)。

## 包结构（`research-pack-v1`）

包含 `meta.json`、`report.md`、`brief-card.md`、`signals.json`、`evidence-refs.json`、`evidence-summary.md`、`claims-outcomes.json`、`reasoning-trace.json`、`README.md`。

完整证据链 `evidence-chain-v1`（#986/#127）暂缓；`meta.evidence_chain_status=deferred`。
历史记录中的 `brief`、`standard` 或 `research` 报告会原样保存在 `report.md`，
并由 `meta.report_mode` 标注；受长度约束的决策卡仍为独立文件。NaN/±Inf
不会进入导出：不可用数值明确显示为“不可计算”，风险结论缺失时显示“未评估”而非“通过”。

## 配置

- `RESEARCH_PACK_EXPORT_ENABLED` 默认 `false`
- `RESEARCH_PACK_MAX_ZIP_BYTES` 默认 24 MiB（夹紧 1–64 MiB）

## API

`GET /api/v1/history/{record_id}/research-pack`，需管理员认证；响应头含进度与截断信息。

## 回滚

保持 `RESEARCH_PACK_EXPORT_ENABLED=false` 并重启。

## 相关导出面

证据链审计包（#986 / #127，开放 PR #1214）是独立的审计 ZIP；本研报资产包面向 #988 / #1140 的分享场景。
