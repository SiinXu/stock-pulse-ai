# 上游一致性检查（Upstream Parity）

- 状态：`Living`
- 最近核对：2026-08-20
- 范围：`ZhuLinsen/daily_stock_analysis` 漂移报告、白名单语义、trailer-safe / do-not-trailer SHA 契约、分诊流程与维护节奏

StockPulse **手动**移植上游 foundation 修复，不会自动 merge 或同步上游。本文说明每周运行的一致性检查如何报告漂移，以便维护者有计划地分诊移植。

英文版：[upstream-parity.md](upstream-parity.md)。

相关策略：[Foundation Pipeline 与 Product Layer](foundation-product-architecture.md#upstream-porting-policy)。
节奏责任 Issue：[#1061](https://github.com/SiinXu/stock-pulse-ai/issues/1061)。
机器跟踪 Issue：[#1002](https://github.com/SiinXu/stock-pulse-ai/issues/1002)。

## 检查器做什么

脚本：`scripts/check_upstream_parity.py`  
盘点脚本（路径存在性 + 建议动作）：`scripts/inventory_upstream_drift.py`
白名单：`scripts/upstream_parity_whitelist.json`  
Trailer SHA 契约：`scripts/upstream_trailer_triage.json`  
工作流：`.github/workflows/upstream-parity.yml`

每次每周（或手动）运行时，工作流会：

1. 将 `https://github.com/ZhuLinsen/daily_stock_analysis.git` 拉取为 `upstream`。
2. 计算 StockPulse `main` 与 `upstream/main` 的 merge-base（分叉点）。
3. 列出自该分叉点起**仅存在于上游**的提交。
4. 按变更路径对照白名单分类。
5. 交叉引用本地 `Ported-from:` trailer，标记已移植提交。
6. 上传 Markdown 报告产物，并**原地更新唯一**跟踪 Issue。

机器报告刷新后，维护者应运行**盘点脚本**，把 Attention 提交转为可执行差距清单（本地路径存在性，以及 Port / Design / Record-trailer / Skip-docs 建议）。路径存在性只是启发式，不等于语义等价。

离线 CI 门禁**不会**拉取上游。请使用 `--self-test` 做夹具回归；需要实时报告时再在有网络与 remote 的环境运行脚本。

## Ported-from Trailer 约定

当 StockPulse 提交移植了上游行为时，请记录来源：

```text
Ported-from: ZhuLinsen/daily_stock_analysis@<sha>
```

- 使用上游提交 SHA（7–40 位十六进制）。
- 一次 StockPulse 变更合并多个上游提交时，可写多条 trailer。
- 检查器将 trailer 中的 SHA 作为前缀与完整上游 SHA 匹配。
- 必须写成 `Ported-from: ZhuLinsen/daily_stock_analysis@<sha>`。缺少 `repo@` 的 `Ported-from: <sha>` 为畸形 trailer，**不算** already ported。

## Trailer-safe 与 do-not-trailer SHA

路径存在性 ≥75% 只是启发式（`record_trailer`），不能单独授权补 `Ported-from` trailer。`scripts/upstream_trailer_triage.json` 是 SHA 级契约（#1221）：

- **trailer_safe** — 语义 spot-check 已确认意图被 fork-native 布局吸收。可补格式正确的 trailer（空提交或下一张相关 PR）。不要二次拷贝上游文件。
- **do_not_trailer** — 高路径存在性仍掩盖残留缺口、部分移植或有意的治理/安全分叉。不要靠补 trailer 或改写畸形 trailer 消音 Attention。应开/保留 port 或 design Issue。
- 把 `do_not_trailer` SHA 的畸形 trailer 改成合法格式会掩盖残留差距。
- **不要**靠扩大路径白名单来隐藏这些 SHA。

进行中的产品 port PR 可能随后吸收某条启发式 `record_trailer`；那些 SHA 归产品 PR 所有，不属于 trailer-only 提交。

## 白名单语义

白名单列出 **有意分叉的路径前缀**。分类规则：

| 提交路径 | 是否有 Ported-from 匹配 | 状态 |
| --- | --- | --- |
| 任一路径不在白名单（共享 foundation / 共享产品面） | 否 | **Attention** — 需审阅是否主动移植 |
| 含共享路径 | 是 | **Already ported** |
| 全部路径仅匹配白名单前缀 | 否 | **Informational** — 预期的产品/治理分叉 |
| 全部为白名单路径 | 是 | **Already ported**（仍会记录） |

经验规则：

- 白名单保持**尽量小**。只加入 StockPulse 明确不会镜像的前缀（桌面打包、AI 协作资产、一致性工具自身等）。
- **不要**为了消音报告而把 `src/data_provider/`、`src/core/` 等共享 foundation 路径加入白名单。
- 扩展白名单属于产品决策：同步更新 JSON、本文（中英）与 changelog。

空路径列表（例如部分 merge 提交）按 informational 处理。

## 分诊流程

1. 打开标签为 `upstream-parity` 的跟踪 Issue（标题：`Upstream parity drift report`，当前为 #1002），或下载工作流产物 `upstream-parity-report-*.md`。
2. 生成维护者盘点报告（路径存在性 + 建议动作）：

```bash
python scripts/inventory_upstream_drift.py \
  --local-ref origin/main \
  --upstream-ref upstream/main \
  --output /tmp/upstream-drift-inventory.md
```

3. 优先处理 **Attention** 提交。对每个候选，按 #1061 分类：
   - **Port now** — foundation 修复；小而可测的 PR，提交含 `Ported-from: ZhuLinsen/daily_stock_analysis@<sha>`
   - **DESIGN-NEEDED** — 与本地 Agent/策略/报告契约纠缠；先开设计 Issue 再写代码（示例：#805 multi-strategy 集群）
   - **Record trailer** — 本仓已以 fork-native 布局吸收意图；语义 spot-check 后补 `Ported-from`，使 #1002 不再标为 Attention。无后续产品 port 时，仅 `scripts/upstream_trailer_triage.json` 中的 `trailer_safe` SHA 可补 trailer。
   - **Do not trailer** — SHA 在 `do_not_trailer` 中；高路径存在性不等于已吸收。在真实 port 或有意 skip Issue 落地前保持 Attention。
   - **Skip / whitelist** — 仅产品面、docs/changelog 或治理路径，StockPulse 明确不镜像；扩展白名单须审慎
4. **禁止半移植** 跨 orchestrator/pipeline/报告 schema 的纠缠集群（无设计说明不得拆文件拷贝）。
5. 对真实残留差距**开子 Issue 或更新既有 Issue**；不要只把差距留在周报正文里。
6. **Informational** 提交可保持不移植，除非路径后来进入共享代码。
7. 移植后本地复跑：

```bash
python scripts/check_upstream_parity.py --self-test
python scripts/inventory_upstream_drift.py --self-test
python scripts/check_upstream_parity.py --fetch \
  --local-ref origin/main \
  --upstream-ref upstream/main \
  --output /tmp/upstream-parity-report.md
python scripts/inventory_upstream_drift.py \
  --local-ref origin/main \
  --upstream-ref upstream/main \
  --output /tmp/upstream-drift-inventory.md
```

8. 不要另开**机器跟踪** Issue。工作流只更新带 `upstream-parity` 标签且含 HTML 标记 `<!-- upstream-parity-tracking-issue -->` 的那一个开放 Issue；重复项会被自动关闭。Port/Design 子 Issue 是预期产物，应引用 #1002 / #1061。

## 治理节奏（谁 / 何时）

| 节奏 | 责任人 | 动作 |
| --- | --- | --- |
| 每周一 04:00 UTC（或 `workflow_dispatch`） | GitHub Actions `upstream-parity` | 刷新 #1002 分类与产物 |
| 每次刷新后数日内 | 维护者 / #1061 节奏负责人 | 跑 `inventory_upstream_drift.py`，分诊 Attention，开/更新子 Issue |
| 每个 port PR 合入后 | Port 作者 | 确认 `Ported-from` trailer；复跑盘点使 Attention 收敛 |
| 白名单变更 | 维护者产品决策 | 同步 JSON + 本文（中英）+ changelog |

**盘点报告消费者：** #1002 分诊评论、#1061 checklist 负责人、规划下一波 port 的作者。

## 本地命令

```bash
python scripts/check_upstream_parity.py --self-test
python scripts/inventory_upstream_drift.py --self-test
python -m pytest tests/scripts/test_upstream_parity.py tests/scripts/test_inventory_upstream_drift.py -q
python scripts/check_upstream_parity.py --fetch \
  --local-ref origin/main \
  --upstream-ref upstream/main
python scripts/inventory_upstream_drift.py --fetch \
  --local-ref origin/main \
  --upstream-ref upstream/main \
  --output /tmp/upstream-drift-inventory.md
```

## 工作流说明

- 计划：每周一 04:00 UTC，以及 `workflow_dispatch`。
- Actions 使用 SHA 固定（由 `scripts/check_workflow_supply_chain.py` 强制）。
- 权限：parity 作业仅 `contents: read`、`issues: write`。
- 工作流不会推送代码、打开 PR，也不会 merge 上游。

## 文档维护

白名单语义、trailer 格式、分诊流程或治理节奏变更时，请同步更新本文与 `upstream-parity.md`。移植策略本身变更时，更新 `foundation-product-architecture.md`。
