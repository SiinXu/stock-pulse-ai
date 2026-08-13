---
name: fix-issue
description: Implement a fix for a single GitHub issue under this repository's rules, including verification, risks, rollback notes, and Delivered/Remaining issue comments.
---

# Fix Issue

基于 issue 分析结果实现修复，并按仓库规则补齐验证、风险与回滚说明。

**Repository**: https://github.com/SiinXu/stock-pulse-ai

**Source of truth**: repository root `AGENTS.md`. Hard rules: `.claude/skills/references/hard-rules.md`.

## Usage

```text
/fix-issue <issue_number>
```

## Prerequisites

优先先完成 `/analyze-issue <issue_number>`，确保问题成立且边界清晰。

## Instructions

### Step 1: 确认分析基线

检查 `.claude/reviews/issues/issue-<number>.md` 是否存在；如果不存在，先补做 issue 分析或在本次修复中补齐最小分析结论。

### Step 2: 同步最新代码基线并选择安全的工作方式

开始修复或准备创建 / 更新 PR 前，先按 `AGENTS.md` 拉新：

```bash
git status --short
git fetch --all --prune
# 仅当工作区干净且当前分支可 fast-forward 时执行：
git pull --ff-only
```

- 默认基于当前工作树做最小相关改动
- 只有在工作区干净、当前分支有可 fast-forward 的上游时，才执行并接受 `git pull --ff-only` 的结果
- 如存在本地改动、冲突状态、未跟踪风险文件、无上游分支或无法 fast-forward，不要执行 `stash`、`reset`、强制切分支或覆盖本地状态；先记录本地 HEAD、使用的远端基线与无法更新本地工作树的原因
- 若后续要创建 / 更新 PR，先说明当前分支与目标基线差异；必要时请求用户确认 rebase、merge 或继续基于当前分支推进
- 不要默认切换分支或改写用户当前工作状态
- 如果用户明确要求建分支，再执行最小必要的分支操作

### Step 3: 实施修复

- 根据 issue 结论定位相关文件
- 优先复用现有模块、配置入口、脚本和测试
- 保持默认行为向后兼容，避免破坏 fallback / fail-open
- 如果修复涉及用户可见行为、配置语义、CLI/API、部署、通知、报告结构，要同步更新相关文档、`docs/CHANGELOG.md`、`.env.example`
- 新增或重命名配置键时，必须同步 `src/core/config_registry_parts/` 与双语环境变量清单，并执行 hard-rules §2 的 registry guard（禁止靠扩大 unregistered baseline 来绿 CI）
- 若声称用户可到达某能力，须按 hard-rules §3 做可达性 grep；仅有文件存在不算 Delivered
- 向 `docs/CHANGELOG.md` 写入条目时，在 `[Unreleased]` 段追加一行，格式为 `- [Type] Description`，其中 `Type` 为 `Added`/`Changed`/`Fixed`/`Docs`/`Tests`/`Chore`（与 `AGENTS.md` 一致，英文）；只有修复 bug 时才使用 `Fixed`；**不要**在 `[Unreleased]` 内新增 `###` 类目标题
- `README.md` 只承载项目定位、核心能力、快速开始、主要入口、赞助/合作等首页级信息；非必要不更新 README，避免持续膨胀
- 更细的模块行为、页面交互、专题配置、排障说明、字段契约、实现语义和边界条件，优先更新对应 `docs/*.md`

### Step 4: 按改动面验证

按 `AGENTS.md` 的验证矩阵执行最接近的检查（优先 `/test-change` 或 `/run-verification`）：

- 后端优先：`./scripts/ci_gate.sh`
- 最低后端要求：`python -m py_compile <changed_python_files>`
- 配置改动：`python scripts/check_config_doc_consistency.py` 与 registry guard 测试
- 前端：`cd apps/dsa-web && npm ci && npm run lint && npm run build`
- 桌面端：先构建 Web，再构建桌面端
- AI 协作资产：`python scripts/check_ai_assets.py`

如无法完成完整验证，必须记录缺口、原因与潜在风险。

### Step 5: 更新 issue 分析文档

在 `.claude/reviews/issues/issue-<number>.md` 中补充：

```markdown
## Fix Implementation

**Date**: YYYY-MM-DD

### Changes Made

- 文件与改动点：

### Validation

- 已执行：
- 未执行：

### Risks

- 风险点：

### Rollback

- 回滚方式：
```

### Step 6: Issue 评论与 PR（需确认）

若在 issue 下汇报进度或完成情况，GitHub 评论必须使用英文 **Delivered / Remaining / Verification** 格式（hard-rules §4）。在-scope Remaining 非空时不要使用 `Fixes`/`Closes`。

如用户要求创建 PR、生成 PR 标题或整理 PR 描述：优先 `/pr-template-fill`，并在提交前做 squash 正文体检（hard-rules §1）。PR title 建议遵循 `AGENTS.md`：

- 使用英文 `<type>: <change summary>` 格式，例如 `fix: preserve market analysis history`
- 类型优先使用 `fix`/`feat`/`refactor`/`docs`/`chore`/`test`/`ci`
- 标题只描述实际改动，建议不添加 `[codex]`、`codex`、`autocode`、`copilot` 或其他工具/agent 来源前缀
- 该约定仅用于协作一致性，不应被单独当作 process blocker
- 所有发布到 GitHub 的 Issue / PR 正文、评论、review 和建议回复必须使用英文。

只有在用户明确确认后，才执行：

- 建分支
- `git commit`
- `git push`
- 创建 PR
- 在 issue 下回复或关闭 issue
- 合并 / 开启 auto-merge（默认拒绝；火车合并纪律见 hard-rules §5）

## Allowed Auto-Actions (No Confirmation Needed)

- 阅读和分析代码
- 执行 `git fetch --all --prune`，并在工作区干净且可 fast-forward 时执行 `git pull --ff-only`
- 应用与当前任务直接相关的最小修复
- 运行非破坏性的本地验证
- 更新本地 issue 分析文档

## Actions Requiring Confirmation

1. 切换或创建分支
2. `git commit`
3. `git push`
4. 创建 PR
5. 回复或关闭 issue
