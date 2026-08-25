# Agent 晋升清单（dry-run CLI）

**议题：** [#1093](https://github.com/SiinXu/stock-pulse-ai/issues/1093) 第一切片
**英文：** [agent-promotion.md](agent-promotion.md)

本文是 **opt-in dry-run 晋升 CLI** 的操作清单。
它**不会**激活实验 Skill、路由规则或生产开关。受治理的 Skill-pin 生产激活仍是
#1093 后续遗留。

调用即闸门。没有配置注册表键、调度器、管理 HTTP，也没有
`EVOLUTION_AUTO_PROMOTE_SKILLS` 环境变量。

## 安全契约

| 规则 | 执行方式 |
| --- | --- |
| 实验候选只存在于 sidecar JSON | `AgentPromotionService` 拒绝把 `strategies/`、`src/agent/skills/`、插件目录和 eval fixtures 当作 `--store-dir` |
| 生产默认保持关闭 | 未调用 CLI 时，SkillRouter 默认 ID 不变 |
| 回执永不自动晋升 | 嵌入的 `PromotionReceipt.auto_promote=false`；沙箱 `auto_promote_to_production=false` |
| 批准不等于激活 | `approve` / `reject` 只翻转 sidecar `review_state` |
| 本路径不改 Soul / 目录字节 | CLI 从不改写 Agent Soul 或 `strategies/*.yaml` |
| 评估离线 | `score` 复用 `prediction_eval_service`（fixture 含轨迹时同时走 trajectory eval）。不会启动 live agent run |

本切片回滚：保持实验 id 未激活，并回退 Skill-id pin。没有需要撤销的数据库 Soul
改写。若要去掉该功能，回退 CLI、库、测试与本文档即可。

## 评审清单

在把 sidecar 的 `approved` 当作**后续**受治理激活 PR 的输入之前（本切片不执行激活）：

1. **安全** — 候选只在 sidecar 中；`strategies/` 或 `skills/experimental/` 下没有新文件。
2. **评估差** — 已对冻结 fixture / episode lessons 完成 `score`；失败检查已被理解。
3. **样本量** — 本 dry-run 只评分源 case。不要把单条 fixture 当作生产证据。
4. **回执** — `review_required=true`，`auto_promote=false`，`first_live_run_guard=human_approval_required`。
5. **回滚** — 实验 id 保持未激活；回退 Skill pin；不改写 Soul。

sidecar 上的 `approved` 只是评审记录，不是运行时开关。

## CLI

```bash
python scripts/agent_evolve.py propose --fixture tests/fixtures/prediction_eval/cases/pred-seeded-miss-lesson.json
python scripts/agent_evolve.py score --proposal-id promo-<hex>
python scripts/agent_evolve.py status
python scripts/agent_evolve.py approve --proposal-id promo-<hex>
python scripts/agent_evolve.py reject --proposal-id promo-<hex>
```

可选 `--store-dir`（默认 `artifacts/agent_evolve`）。propose 还可使用
`--case-id <prediction-eval-id>` 或 `--episodes <json>`。`--kind` 为
`experimental_skill_id`（默认）或 `router_rule`，只写入 sidecar。

## 持久化、错误与幂等

- **持久化：** 每个提案一个 JSON 文件，临时文件 + `fsync` + 替换，进程锁。
- **提案 id：** candidate kind + case id + 规范化 lessons 的内容哈希。重复 propose 同一源返回已有 sidecar。
- **缺失提案：** `score` / `status --proposal-id` / `approve` / `reject` 失败关闭，不创建文件。
- **批准：** 要求 `review_state=scored`。重复 approve 幂等。已 reject 的提案不能再批准。
- **损坏 / 激活回执：** `auto_promote=true`（或 `review_required=false`）在变更命令上失败关闭。
- **写入失败：** 丢弃临时文件，保留原 sidecar 字节。

## 相关文档

- [Prompt / Skill 版本化](prompt-skill-versioning.md) — 身份与 pin；本 CLI 消费它们但不激活 Skill
- [Agent 沙箱](agent-sandbox.md) — `PromotionReceipt.auto_promote=false`
- [预测核验安全上线](prediction-verification-rollout.md) — 自动晋升保持硬关闭
