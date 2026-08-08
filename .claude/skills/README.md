# Repository Claude Skills

本目录存放仓库级协作 skills，属于版本库资产。

- 规则真源：仓库根目录 `AGENTS.md`
- 兼容入口：根目录 `CLAUDE.md`（应为指向 `AGENTS.md` 的软链接）
- 本目录中的 skill 需要与 `AGENTS.md` 保持一致
- `.claude/reviews/` 属于本地分析产物，不作为规则真源
- 使用指南与选型速查：`docs/claude-skills-guide.md`

当前 skill 清单：

| Skill | 用途 |
|-------|------|
| `analyze-issue` | 评估既有 issue |
| `draft-issue` | 起草新 issue（查重 + 证据核实） |
| `fix-issue` | 单 issue 修复流程 |
| `develop-feature` | 任务完整闭环（可行性门禁 → 实现 → 验证 → PR → 自审 → 收敛修复） |
| `run-verification` | 按改动域执行验证矩阵（红测试基线归因） |
| `analyze-pr` | 评审他人 PR |
| `handle-review-feedback` | 处理自己 PR 上的外部评审反馈（AGENTS.md §8.1，禁止点状补丁） |

如果未来需要兼容其他 agent 目录（如 `.agents/skills/` 或 `.github/skills/`），应先明确单一真源，再通过脚本或镜像同步，而不是手工长期维护多份同义内容。
