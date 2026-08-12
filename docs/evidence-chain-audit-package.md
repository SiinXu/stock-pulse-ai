# 证据链与可审计报告包

结论→证据链路与可导出审计报告包（Issues #986 / #127）。只读投影已落盘历史。
复用 reasoning-trace 脱敏与安全审计 attempt/completion 链路。

English: [evidence-chain-audit-package_EN.md](evidence-chain-audit-package_EN.md)

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `EVIDENCE_CHAIN_ENABLED` | `true` | 构建 `evidence-chain-v1` |
| `AUDIT_EXPORT_ENABLED` | `false` | ZIP/JSON 审计包导出开关 |
| `AUDIT_INCLUDE_RAW_ARTIFACTS` | `false` | 原始中间产物（仍脱敏）；默认显式跳过 |

## API

需要管理员认证。

```http
GET /api/v1/history/{record_id}/evidence-chain
GET /api/v1/history/{record_id}/evidence-pack?format=zip|json
GET /api/v1/analysis/{record_id}/evidence-chain
GET /api/v1/analysis/{record_id}/evidence-pack?format=zip|json
```

## 硬规则

1. 不捏造证据。
2. 缺失必须显式标注，不得省略。
3. 脱敏复用 reasoning-trace 导出。
4. 审计包内嵌推理轨迹复用 `build_reasoning_trace_package`，不另造导出器。

## 回滚

设置 `AUDIT_EXPORT_ENABLED=false`（可选 `EVIDENCE_CHAIN_ENABLED=false`）并重启。
