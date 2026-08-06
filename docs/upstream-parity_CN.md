# 上游一致性检查（Upstream Parity）

- 状态：`Living`
- 最近核对：2026-08-05
- 范围：`ZhuLinsen/daily_stock_analysis` 漂移报告、白名单语义与分诊流程

StockPulse **手动**移植上游 foundation 修复，不会自动 merge 或同步上游。本文说明每周运行的一致性检查如何报告漂移，以便维护者有计划地分诊移植。

英文版：[upstream-parity.md](upstream-parity.md)。

相关策略：[Foundation Pipeline 与 Product Layer](foundation-product-architecture.md#upstream-porting-policy)。

## 检查器做什么

脚本：`scripts/check_upstream_parity.py`  
白名单：`scripts/upstream_parity_whitelist.json`  
工作流：`.github/workflows/upstream-parity.yml`

每次每周（或手动）运行时，工作流会：

1. 将 `https://github.com/ZhuLinsen/daily_stock_analysis.git` 拉取为 `upstream`。
2. 计算 StockPulse `main` 与 `upstream/main` 的 merge-base（分叉点）。
3. 列出自该分叉点起**仅存在于上游**的提交。
4. 按变更路径对照白名单分类。
5. 交叉引用本地 `Ported-from:` trailer，标记已移植提交。
6. 上传 Markdown 报告产物，并**原地更新唯一**跟踪 Issue。

离线 CI 门禁**不会**拉取上游。请使用 `--self-test` 做夹具回归；需要实时报告时再在有网络与 remote 的环境运行脚本。

## Ported-from Trailer 约定

当 StockPulse 提交移植了上游行为时，请记录来源：

```text
Ported-from: ZhuLinsen/daily_stock_analysis@<sha>
```

- 使用上游提交 SHA（7–40 位十六进制）。
- 一次 StockPulse 变更合并多个上游提交时，可写多条 trailer。
- 检查器将 trailer 中的 SHA 作为前缀与完整上游 SHA 匹配。

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
- **不要**为了消音报告而把 `data_provider/`、`src/core/` 等共享 foundation 路径加入白名单。
- 扩展白名单属于产品决策：同步更新 JSON、本文（中英）与 changelog。

空路径列表（例如部分 merge 提交）按 informational 处理。

## 分诊流程

1. 打开标签为 `upstream-parity` 的跟踪 Issue（标题：`Upstream parity drift report`），或下载工作流产物 `upstream-parity-report-*.md`。
2. 优先处理 **Attention** 提交。对每个候选：
   - 确认是否适合 foundation 兼容移植（见上游移植策略）。
   - 在聚焦的 StockPulse PR 中移植，并适配当前契约与许可证。
   - 在提交中写入 `Ported-from: ZhuLinsen/daily_stock_analysis@<sha>`。
3. **Informational** 提交可保持不移植，除非路径后来进入共享代码。
4. 移植后本地复跑：

```bash
python scripts/check_upstream_parity.py --self-test
python scripts/check_upstream_parity.py --fetch \
  --local-ref origin/main \
  --upstream-ref upstream/main \
  --output /tmp/upstream-parity-report.md
```

5. 不要另开跟踪 Issue。工作流只更新带 `upstream-parity` 标签且含 HTML 标记 `<!-- upstream-parity-tracking-issue -->` 的那一个开放 Issue；重复项会被自动关闭。

## 本地命令

```bash
python scripts/check_upstream_parity.py --self-test
python -m pytest tests/scripts/test_upstream_parity.py -q
python scripts/check_upstream_parity.py --fetch \
  --local-ref origin/main \
  --upstream-ref upstream/main
```

## 工作流说明

- 计划：每周一 04:00 UTC，以及 `workflow_dispatch`。
- Actions 使用 SHA 固定（由 `scripts/check_workflow_supply_chain.py` 强制）。
- 权限：parity 作业仅 `contents: read`、`issues: write`。
- 工作流不会推送代码、打开 PR，也不会 merge 上游。

## 文档维护

白名单语义、trailer 格式或分诊流程变更时，请同步更新本文与 `upstream-parity.md`。移植策略本身变更时，更新 `foundation-product-architecture.md`。
