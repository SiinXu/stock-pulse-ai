# 工程效率操作手册（Operational Playbook）

- 状态：`Living`
- 关联 Issue：[\#891](https://github.com/SiinXu/stock-pulse-ai/issues/891)
- 读者：维护者与需要跑并行修复/合并火车的 Agent
- 相关文档：[`AGENTS.md`](../AGENTS.md)（合同）、[贡献指南](CONTRIBUTING.md)、[离线测试门禁](testing-ci-gate.md)、[环境变量清单](environment-variables.md)、[Skills 指南](claude-skills-guide.md)
- English：[engineering-efficiency-playbook_EN.md](engineering-efficiency-playbook_EN.md)

## 0. 与 AGENTS.md 的分工（必读）

| 文档 | 角色 | 冲突时谁优先 |
| --- | --- | --- |
| **`AGENTS.md`** | **合同**：硬规则、目录边界、验证矩阵、GitHub 英文策略、禁止静默 force-push/merge 等 | **永远优先**。若本手册与 `AGENTS.md` 冲突，**以 `AGENTS.md` 为准**，并回修本手册。 |
| **本手册** | **操作指南**：如何火车合并、冲突图分组、跑注册守卫、防 squash 误关 Issue、约束本机资源、保护工作区 | 仅覆盖不削弱合同的执行战术。 |
| **`.claude/skills/`** | 把合同流程编码成可调用步骤 | Skills 操作化合同，不替代合同。 |

**不要**在本手册中整段粘贴 `AGENTS.md`。下列命令是操作配方；CI 名称、提交/PR 语言、需人工确认的动作等硬约束仍以合同为准。

---

## 1. 火车批次合并（Train-batch merges）

### 何时用

- 大量开放 PR 需要落上持续前进的 `main`（功能火车、合并后接线潮、注册表清理批次）。
- 单 PR 体量可 rebase，但「一口气全合」会打爆 CI、反复制造同类冲突。
- 需要**可预期的落盘顺序**，让后续 PR 每个车次只 rebase 一次。

### 操作模型

1. **划定车次窗口**（数小时到一天），不要无限期「有绿就合」。
2. **按依赖与爆炸半径排序**，不要按 PR 号排序：
   - 先合基础/共享契约（schema、配置注册表、CI 脚本）；
   - 再合产品挂载与 UI 接线；
   - 仅文档/纯测试且只描述已合入代码的放最后。
3. **批次规模**：每车次优先 3–8 个已绿且已 rebase 的 PR。更大火车先做冲突图分组（第 2 章）。
4. **单一整合者角色**（人或单一 Agent）：只有整合者执行 merge；worker 只准备下一车次。
5. **每合入一个后**：等新 `main` head（或已知 canary）的必过检查通过，再启动下一车次的 rebase。

### 命令（整合者）

```bash
git fetch --all --prune
git checkout main
git pull --ff-only origin main

# 查看开放 PR 就绪度（过滤器可按需调整）
gh pr list --state open --limit 50
gh pr checks <pr_number>
gh pr view <pr_number> --json mergeable,mergeStateStatus,baseRefName,headRefOid,statusCheckRollup

# 仅在「精确 head」上必过检查全绿时合入
gh pr merge <pr_number> --squash --delete-branch

# 推进本地 main，向 worker 公布新 tip
git pull --ff-only origin main
git rev-parse HEAD
```

Worker 跟进车次 tip：

```bash
git fetch origin
git rebase origin/main
# 或在不便 rebase 时：merge origin/main 进特性分支
git push --force-with-lease   # 仅限自己的特性分支；禁止 force 共享 main
```

### 反例

| 反模式 | 伤害 |
| --- | --- |
| 不排序、不等 `main` canary 连合 20 个 PR | CI 连锁变红；每个 PR 反复解决同类冲突 |
| 多个整合者同时合不同 PR | 共享文件竞态；`main`「先绿后红」 |
| 把「昨天 CI 绿」当成今天可合 | head 已过期；必过检查必须对齐**精确 head** |
| 一个 CI 切片合入后就关整个追踪 Issue | 追踪 Issue 应保持开放直到验收项完成（`Refs` vs `Fixes`——见第 4 章） |

---

## 2. 冲突图分组（Conflict-graph grouping）

### 何时用

- 开放 PR 集合改到重叠路径（`src/core/config_registry_parts/`、`apps/dsa-web/src/pages/*`、共享 i18n、CI workflow）。
- 需要**并行准备**，又不希望所有 worker 都在同一热点文件上 rebase。
- 火车顺序不清，「谁先绿谁先合」过于随机。

### 方法

1. 对每个候选 PR 列出相对 `origin/main` 的变更路径：

```bash
gh pr diff <pr_number> --name-only
# 或本地：
git fetch origin pull/<pr_number>/head:pr-<pr_number>
git diff --name-only origin/main...pr-<pr_number>
```

2. 建无向**冲突图**：
   - 节点 = PR；
   - 边 = 路径集合非空交集（重命名后路径不同但同属已知热点目录时也算）。
3. **着色/划分**独立集（集内无边）。每个独立集可并行准备。
4. 连通分量内部**串行链**：先合中心度高的共享核心，再合叶子。
5. 每个车次结束后**重算图**；不要信任昨天的划分。

### 热点目录（本仓库操作启发式）

下列目录几乎总是冲突磁铁；同时触达则倾向串行合并：

- `src/core/config_registry_parts/`、`src/core/config_registry.py`、`.env.example`
- `docs/environment-variables.md`、`docs/environment-variables_EN.md`
- `apps/dsa-web/src/i18n/`（及 locale 体积预算）
- `.github/workflows/ci.yml`、`scripts/ci_gate.sh`、`scripts/ci_select_tests.py`
- 共享壳层：`HomePage`、Settings 路由、导航注册表

### 路径重叠速算草图

```bash
for n in 1013 1058 1023; do
  gh pr diff "$n" --name-only | sort -u > "/tmp/pr-${n}.paths"
done
# 两 PR 交集规模：
comm -12 /tmp/pr-1013.paths /tmp/pr-1058.paths | wc -l
```

### 反例

| 反模式 | 伤害 |
| --- | --- |
| 多名 worker 为「不同 Issue」并行改同一 Settings 页 | 必冲突；应指定单一顺序所有者 |
| 只按 label（`feat`/`fix`）分组 | label 不预测冲突 |
| 多日火车冻结合并顺序且不刷新 | 前几个合入后图已失效 |
| 注册表/i18n 冲突时整文件「全盘 ours/theirs」 | 静默丢契约；应修内容，不要抽签 |

---

## 3. 配置注册守卫（Config registration guards）

### 何时用

- PR 新增或重命名用户可见 / 运行时环境变量键。
- 合并火车反复弄坏 Settings（未分类键、控件类型错误、缺 help）。
- CI 失败于 `test_env_example_config_registry_guard` 或配置清单检查。

### 合同约束（不可削弱）

新增配置项必须同步更新 `.env.example` 与相关文档（见 `AGENTS.md`）。操作上意味着**同一变更**内对齐三方：

1. `.env.example`
2. `src/core/config_registry_parts/`（Settings UI 元数据）
3. `docs/environment-variables.md` + `docs/environment-variables_EN.md`

深读：[环境变量清单与配置事实源](environment-variables.md)。

### 命令

```bash
# 三方一致性（文档 / env / 注册状态）
python scripts/check_config_doc_consistency.py
python scripts/check_config_doc_consistency.py --json

# 可选：把历史「未注册」债务也变成硬失败
python scripts/check_config_doc_consistency.py --fail-on all

# 守卫测试（禁止靠扩大未注册 baseline 刷绿）
python -m pytest tests/core/test_env_example_config_registry_guard.py tests/test_config_registry.py -q
```

### 新键正确修复路径

1. 在 `.env.example` 增加 `KEY=`（或注释行 `# KEY=`）。
2. 在合适的 `src/core/config_registry_parts/*` 注册字段（类型、控件、分组、help）。
3. 更新中英清单表（若任务已使用 inventory writer，可按既有流程生成）。
4. 跑上列命令直至绿色。
5. **禁止**为刷绿而扩大 `TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_BASELINE`、抬高 hard ceiling、或改写 pinned baseline hash——应去注册该键。

### 反例

| 反模式 | 伤害 |
| --- | --- |
| 只写运行时 `os.getenv("NEW_KEY")` | Settings 垃圾堆 / 键不可见 / 控件错误 |
| 只改中文清单不改英文（或相反） | `cn_en_mismatch`；双语运维分叉 |
| 靠扩大未注册债务 baseline 刷绿 CI | 债务棘轮反方向；设计上会被拦 |
| 合入后只改失败行、不重跑三方脚本 | 下一班火车重复同一债务 |

---

## 4. Squash 误关 Issue 防线

### 何时用

- 仓库默认合并方式为 **squash**。
- 提交信息或 PR 正文含 `Fixes #N` / `Closes #N` / `Resolves #N`。
- 追踪型 / Epic / 多切片 Issue（例如 #891）必须在**完整**验收项落地前保持开放。

### 用词对照

| 意图 | 在 PR 正文/提交中使用 | squash 合入后 GitHub 行为 |
| --- | --- | --- |
| 本 PR **完整完成**该 Issue | 优先在 PR 正文写一次 `Fixes #N` 或 `Closes #N` | Issue **关闭** |
| 本 PR 只是大 Issue 的**切片** | 只用 `Refs #N` | Issue **保持开放** |
| 历史关联、不宣称完成 | 文档/changelog 用 `Refs #N`；避免 close 关键字 | Issue 保持开放 |

### 合入前检查（整合者）

```bash
# 扫描 PR 标题、正文、将进入 squash 的提交标题
gh pr view <pr_number> --json title,body,commits \
  --jq '{title,body,commits:[.commits[].messageHeadline]}'

# 需要时再看完整提交正文
gh pr view <pr_number> --json commits --jq '.commits[].messageBody'
```

若切片 PR 误写 `Fixes #891` 而验收项未完成：

1. 合入前把 PR 正文改为 `Refs #891`，或
2. 合入后立即 reopen，并评论说明原因。

### Changelog 纪律

- 用户可见切片：在扁平 `[Unreleased]` 行使用 `Refs #N`（Issue 未完成时）。
- changelog 措辞不要暗示「整项完成」，若追踪 Issue 仍开放。

### 反例

| 反模式 | 伤害 |
| --- | --- |
| 仅 CI/文档局部切片写 `Fixes #891` | 追踪 Issue 被自动关掉，剩余 AC 看似已完成 |
| 中间提交含 `Fixes`，squash 仍带上该关键字 | squash 提交信息仍可触发自动关闭 |
| 依赖「稍后 reopen」且不留评论 | 审计链断裂；机器人/报表当已关闭 |
| 关键字关闭 + 再手动关一次 | 噪音；AC 真正完成时一次有意关闭即可 |

---

## 5. 自迭代验收闭环（Self-iteration acceptance loop）

### 何时用

- 任何带书面任务或 Issue AC 的 `fix` / `feat` / `refactor` / `test` / `chore`。
- 收到评审反馈后（尤其想「只改被点名那几行」时）。
- Agent/worker 交付在请求合入前必须收敛。

### 闭环顺序（操作）

```text
1. 相对真实代码做可行性（文件/契约是否存在；可运行代码优先于计划文本）
2. 在给定边界内做最小实现
3. 按变更范围跑验证矩阵（见 AGENTS.md §6；run-verification skill）
4. 按 analyze-pr 顺序自审：必要性 → 相关性 → 标题 → 描述 → 证据 → 正确性
5. 逐条勾 AC；修齐同一语义下的全部表面（runtime / API / Web / docs / tests）
6. 更新 PR 正文使其与最终 diff 一致
7. 仅当一轮评审对同一语义零新增发现时停止
```

首选 skill 入口：`develop-feature`（内嵌验证 + 自审）。外部评审轮次：`handle-review-feedback`——**禁止补丁堆叠**。

### 命令（典型后端改动）

```bash
python -m pip install --upgrade --constraint constraints.txt pip
python -m pip install --build-constraint build-constraints.txt -r .github/requirements-ci.txt
python -m pip check
./scripts/ci_gate.sh
python -m py_compile <changed_python_files>
```

若触及 Web，额外：

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run test:i18n
npm run test
npm run build
```

红测须相对 `origin/main` 归因（既有 vs 新引入）。存在新失败时不得宣称绿色。

### 反例

| 反模式 | 伤害 |
| --- | --- |
| 只看「CI 绿」不勾 AC | 不可达挂载、缺注册、错误关闭关键字漏网 |
| 只点修评审指出的行 | 兄弟入口残留同类问题（本仓库明确的低质量模式） |
| 用 mock 绕开风险层，测试只证明局部细节 | 虚假信心；生产路径仍挂 |
| PR 正文描述旧 diff | 评审者带着错误心智模型合入 |

---

## 6. 单机资源打爆教训

### 何时用

- 同一主机上同时跑多个 agent 工作区、完整 `ci_gate`、Web 构建与 Docker。
- 症状：OOM、过热降频、`node_modules`/pytest 缓存把磁盘撑满、僵尸 `pytest`/`node`、Git 锁争用。

### 硬教训（操作上限）

| 资源 | 单机实用上限 | 原因 |
| --- | --- | --- |
| 并发**完整** `./scripts/ci_gate.sh` | **1**（绝不 2+） | 多 GB 内存 + 长 CPU；双 gate 会互相拖死并假超时 |
| 并发 Web `npm run build` / 完整测试矩阵 | **1–2** | `node_modules` 与打包器主导磁盘与内存 |
| 并发 agent 改**同一** git worktree | **1** | index.lock、半写入、丢改动 |
| 隔离 worktree 上的并发 worker | 按内存/磁盘封顶（常见 **3–6** 个轻任务，而非 20 个全量 gate） | 每个 worktree + `node_modules` + venv 都是数 GB |
| 后台并行多份 `npm ci` | 优先共享安装策略或串行 bootstrap | 重复安装静默吃盘 |

### 命令（巡检与减载）

```bash
# 磁盘压力
df -h .
du -sh .git node_modules apps/dsa-web/node_modules .pytest_cache 2>/dev/null

# 重进程
ps aux | egrep 'pytest|npm|node|uvicorn|playwright' | egrep -v egrep

# Git 锁（有活进程持有时不要删锁文件）
ls -la .git/index.lock .git/worktrees 2>/dev/null

# 仅在无运行任务时清理本地缓存
# rm -rf .pytest_cache apps/dsa-web/node_modules/.cache
```

### 推荐 worker 布局

1. **一个整合者终端**只操作 `main`（merge + canary）。
2. 按冲突图划分的** N 个隔离 worktree**（第 2 章），每个 worktree 同时最多一个重验证。
3. 迭代时优先**路径选择**本地测试；交接前再跑一次完整 `ci_gate`。
4. Docker 镜像构建与双全量 pytest 不要并行。

### 反例

| 反模式 | 伤害 |
| --- | --- |
| 拉起 15 个 agent 各自跑完整离线套件 | 主机不可用；超时被误判为产品 bug |
| 多 agent 共享一个 working tree | 互相覆盖与锁错误；diff 不可调试 |
| 磁盘涨到 `No space left on device` 才处理 | 半成品 merge 损坏；恢复成本高 |
| 不看 worktree 归属乱杀 `node` PID | 可能杀掉别人的安装写入过程 |

---

## 7. 误删工作区防线

### 何时用

- 大量 `git worktree` 落在 `/tmp`、`~/orca/workspaces/...` 或兄弟目录。
- 火车结束后「清磁盘」、跑清理脚本、或指示 agent「PR 开完就删工作区」。

### 安全清理协议

```bash
# 1) 先清单——未列出前禁止删除
git worktree list
gh pr list --author @me --state open

# 2) 确认路径是 worktree，不是主 clone
git -C <path> rev-parse --is-inside-work-tree
git -C <path> branch --show-current
git -C <path> status --short

# 3) 优先用 git 自带移除（默认拒绝脏树）
git worktree remove <path>
# 仅当 git 已看不到但目录仍在时：
git worktree prune

# 4) 仅在 worktree remove 且状态干净后才考虑目录删除
# rm -rf <path>   # 最后手段；再核对路径拼写
```

### 防护

- **禁止**凭记忆执行宽泛删除（`rm -rf /tmp/stock-pulse-*`、`rm -rf ~/orca/workspaces/stock-pulse-ai/*`）。
- 把**主 clone** 路径加入自动清理黑名单。
- 删除前确认：PR 已推送？有无未提交调研笔记？有无未推送提交？

```bash
git -C <path> log --oneline origin/main..HEAD | head
git -C <path> status --short
git -C <path> remote -v
```

- 若工作仅在本地：先打备份分支或 patch：

```bash
git -C <path> branch backup/<topic>-$(date +%Y%m%d)
git -C <path> format-patch -o /tmp/backup-patches origin/main
```

### 反例

| 反模式 | 伤害 |
| --- | --- |
| `rm -rf` 仍有活跃 agent 的目录 | 半写入损坏；提示词/状态不可复原 |
| 删掉唯一持有未推送修复的 clone | 工作丢失；「本地曾绿」变成传说 |
| 用过宽 glob 清理 `/tmp/hb-*` | 无关火车共享前缀；误伤 |
| 不经 `git worktree remove` 直接删路径 | 残留 worktree 元数据；之后 `git worktree add` 行为怪异 |

---

## 8. 命令速查

| 目标 | 命令 |
| --- | --- |
| 完整离线后端门禁 | `./scripts/ci_gate.sh` |
| 配置三方检查 | `python scripts/check_config_doc_consistency.py` |
| 注册债务守卫测试 | `python -m pytest tests/core/test_env_example_config_registry_guard.py -q` |
| AI 协作资产检查 | `python scripts/check_ai_assets.py` |
| PR 路径选择测试映射 | `python scripts/ci_select_tests.py`（CI 使用；见 [testing-ci-gate](testing-ci-gate.md)） |
| PR 精确 head 检查 | `gh pr checks <n>` / `gh pr view <n> --json headRefOid,statusCheckRollup` |
| 列出 worktree | `git worktree list` |
| 安全移除 worktree | `git worktree remove <path>` |

---

## 9. 相关 Issue / 切片

| Issue / PR | 角色 |
| --- | --- |
| [\#891](https://github.com/SiinXu/stock-pulse-ai/issues/891) | 父追踪：效率与质量 playbook |
| [\#808](https://github.com/SiinXu/stock-pulse-ai/pull/808) | 选择性 PR 测试 + main 分片门禁（CI 吞吐切片） |
| [\#1023](https://github.com/SiinXu/stock-pulse-ai/issues/1023) | 配置注册表登记债务 |
| [\#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008) | 火车后生产可达性审计 |
| [\#1054](https://github.com/SiinXu/stock-pulse-ai/issues/1054) | 维护可持续性 / WIP 纪律 |
| [\#1065](https://github.com/SiinXu/stock-pulse-ai/issues/1065) | 进一步合并吞吐工作 |

本文记录大规模并行修复/合并中沉淀的**操作模式**。它不替代 #891 中仍待完成的里程碑策略、Makefile/just 统一入口或 label/模板等工作。

---

## 10. 维护

- 当某模式在实战中被证伪时，在改变流程的同一 PR 中更新本手册，或开带证据的文档 follow-up。
- 新硬规则不要先写进本手册——先写入 `AGENTS.md`，再从本指南链接。
- 保持中英两版语义对齐（`engineering-efficiency-playbook.md` / `engineering-efficiency-playbook_EN.md`）。
