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

启用原始中间产物后，包内仅包含已落盘并完成脱敏的
`context_snapshot.json` 与 `raw_result.json`。两者合计上限为 2,000,000 字节；
超限或缺失时生成显式 `MISSING` 项，不会静默省略。

## API

需要管理员认证。

```http
GET /api/v1/history/{record_id}/evidence-chain
GET /api/v1/history/{record_id}/evidence-pack?format=zip|json
GET /api/v1/analysis/{record_id}/evidence-chain
GET /api/v1/analysis/{record_id}/evidence-pack?format=zip|json
```

ZIP 与 JSON 都携带 manifest、报告、证据链、推理轨迹、决策信号、缺口以及原始中间产物状态。
JSON 使用 `artifacts` 对象承载同一组内容；`evidence_chain.json` 通过 `$ref` 指向顶层
`evidence_chain`，避免重复。单个 ZIP 的未压缩产物内容硬限制为 5,000,000 字节，
可选产物超限时在 manifest 中标为 `missing`，并将 `truncated` 设为 `true`。

## 硬规则

1. 不捏造证据。
2. 缺失必须显式标注，不得省略。
3. 脱敏复用 reasoning-trace 导出。
4. 审计包内嵌推理轨迹复用 `build_reasoning_trace_package`，不另造导出器。
5. 失败、超时或未知状态的数据源/工具执行不得作为结论支持证据；只显示为缺失证据记录。

## 回滚

设置 `AUDIT_EXPORT_ENABLED=false`（可选 `EVIDENCE_CHAIN_ENABLED=false`）并重启。
