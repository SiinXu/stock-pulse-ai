# Repository Claude Skills

本目录存放仓库级协作 skills，属于版本库资产。

- 规则真源：仓库根目录 `AGENTS.md`
- 兼容入口：根目录 `CLAUDE.md`（应为指向 `AGENTS.md` 的软链接）
- 本目录中的 skill 需要与 `AGENTS.md` 保持一致
- 共享硬规则与命令菜谱：`references/hard-rules.md`、`references/test-command-recipes.md`
- `.claude/reviews/` 属于本地分析产物，不作为规则真源
- 使用指南与选型速查：`docs/claude-skills-guide.md`

当前 skill 清单：

| Skill | 用途 |
|-------|------|
| `analyze-issue` | 评估既有 issue |
| `draft-issue` | 起草新 issue（查重 + 证据核实；GitHub 正文英文） |
| `fix-issue` | 单 issue 修复流程（含 Delivered/Remaining 评论格式） |
| `develop-feature` | 任务完整闭环（可行性门禁 → 实现 → 验证 → PR → 自审 → 收敛修复） |
| `test-change` | 按改动面选测试层并产出证据（#890 P0 入口名） |
| `run-verification` | 可执行验证矩阵 + 相对 main 的红测归因 |
| `analyze-pr` | 评审他人 PR 的分析流程与文档模板 |
| `review-pr` | #890 P0 评审入口：Blocker/Nit 清单 + squash 正文体检 |
| `handle-review-feedback` | 处理自己 PR 上的外部评审反馈（AGENTS.md §8.1，禁止点状补丁） |
| `sync-ai-assets` | 改治理资产后跑通 `python scripts/check_ai_assets.py` |
| `pr-template-fill` | 从 diff + issue 生成英文 PR 正文 |
| `regression-scout` | 从 diff 列出可能回归面并指向已有测试 |

## Which skill for develop / issue / test / review

| Intent | Skill |
|--------|--------|
| Implement a planned task | `develop-feature` |
| Fix one existing issue | `fix-issue` |
| Draft / analyze an issue | `draft-issue` / `analyze-issue` |
| Verify before “done” or PR | `test-change` → `run-verification` |
| Review a PR | `review-pr` (uses `analyze-pr` procedure) |
| Author PR body | `pr-template-fill` |
| After editing AGENTS/skills | `sync-ai-assets` |

如果未来需要兼容其他 agent 目录，应先明确单一真源，再通过脚本或镜像同步。
