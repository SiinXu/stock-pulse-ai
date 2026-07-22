# 贡献指南

感谢你对本项目的关注！欢迎任何形式的贡献。

## 🐛 报告 Bug

1. 先搜索 [Issues](https://github.com/SiinXu/stock-pulse-ai/issues) 确认问题未被报告
2. 使用 Bug Report 模板创建新 Issue
3. 提供详细的复现步骤和环境信息

## 💡 功能建议

1. 先搜索 Issues 确认建议未被提出
2. 使用 Feature Request 模板创建新 Issue
3. 详细描述你的使用场景和期望功能

## 🔧 提交代码

### 开发环境

```bash
# 克隆仓库
git clone https://github.com/SiinXu/stock-pulse-ai.git
cd stock-pulse-ai

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
```

### 提交流程

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交改动：`git commit -m 'feat: add some feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 创建 Pull Request

### 认领 Issue

对于开放且尚未分配的 Issue，请发送一条内容仅为 `/claim` 的新评论。自动化只会把 Issue 分配给发出命令的真人评论者，每个账号同时最多持有一个开放 Issue 分配。它不处理 Pull Request 评论、Bot 评论、非精确命令或已关闭 Issue，也不会覆盖已有 assignee；如果 Issue 已分配，它会保留原状态并礼貌回复。

认领后请在 3 天内发布 draft Pull Request 或进展更新。这个活动窗口由维护者手动执行，不会自动过期；当前不支持 `/unclaim`，需要释放认领时请联系维护者。

### 架构决策

如果 PR 会改变组件边界、跨模块单一权威、运行时/持久化/部署模型、安全或故障策略，或建立可复用的大型迁移方法，PR 正文必须完成 ADR 考量：链接一个新的或既有的 ADR，或者说明为什么改动仍受现有决策约束且不需要新 ADR。编号、状态、流程和模板见 [ADR 注册表](adr/README.md)。

已接受的 ADR 保留为历史记录。重大改判应新增 ADR 并互相链接，不要直接重写旧记录来隐藏原决策。

### 变更归属

共享的数据源、分析管线、领域契约、持久化与领域报告语义应优先归入 foundation pipeline；API DTO 与投影、Web、Desktop、Bot、交互式 Agent 体验及仓库治理归入 product layer，并通过共享契约消费 foundation 能力。跨轨改动必须先确定单一权威并保持领域 Schema、API 投影、任务状态与报告视图兼容，不能在产品入口复制 provider fallback、管线编排或任务生命周期。完整路由、上游移植和许可证来源规则见 [Foundation Pipeline 与 Product Layer](foundation-product-architecture.md)。架构轨不决定许可证。

### Commit 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

Commit message、Issue / PR 标题与正文、评论、review、GitHub Actions 输出和 bot 评论必须使用英文。

```
feat: add a feature
fix: fix a bug
docs: update documentation
style: format code without behavior changes
refactor: restructure code
perf: improve performance
test: add or update tests
chore: update build or tooling
```

示例：
```
feat: add DingTalk bot support
fix: handle 429 rate limits with retry backoff
docs: update the README deployment guide
```

### 代码规范

- Python 代码遵循 PEP 8
- 函数和类需要添加英文 docstring
- 非直观逻辑使用英文注释
- 新功能需要更新相关文档

### CI 自动检查

提交 PR 后，CI 会自动运行以下检查：

| 检查项 | 说明 | 必须通过 |
|--------|------|:--------:|
| ai-governance | 校验 `AGENTS.md`、兼容指令和仓库协作资产 | ✅ |
| backend-gate | `scripts/ci_gate.sh` 的 syntax、flake8、deterministic 与 offline-tests | ✅ |
| docker-build | Docker 镜像构建与关键模块导入 smoke | ✅ |
| web-gate | Web 或关联 API/配置/服务契约变更时执行 `npm run lint` + `npm run test:i18n` + `npm run test` + `npm run build` | ✅（触发时） |
| web-e2e | 同一关联路径触发；以隔离运行时启动真实后端、Vite 与本地 fake 模型端点并执行 `npm run test:smoke` | ✅（触发时） |
| network-smoke | 定时/手动执行 `pytest -m network` + `scripts/test.sh quick`（非阻断） | ❌（观测项） |

`web-e2e` 只使用专用 canary credential，并将单次运行限定在 `test-results/ci-secret-bearing/`。该 credential-bearing 运行关闭 screenshot、video 和 trace；仓库 `test:smoke` 入口拒绝 UI 模式和替代 Playwright config，global setup 在 Playwright 合并 CLI/project 配置后逐 project 再确认最终 trace 为 `off`。无论 E2E 成功或失败，CI 都先扫描原始运行目录中的文本、日志、JSON、HAR、原始二进制 canary，以及意外出现的 trace/ZIP 条目；扫描器仍按扩展名或文件签名拒绝无法可靠检查的 PNG/JPEG/WebM，不使用 OCR，也不回显匹配值。原始扫描成功后，专用 staging 脚本严格解析 `playwright-results.json`，递归保留 `service-logs/` 中的 UTF-8 `.log`/`.txt` 及目录结构，拒绝符号链接、非 allowlist 文件、伪装 archive 和媒体签名，并生成带大小与 SHA-256 的 `manifest.json`；CI 再扫描 staging 目录，只有两次扫描与 staging 全部成功才上传。原始目录、trace、媒体和 archive 不进入 artifact。

**本地运行检查：**

```bash
# backend gate（推荐）
pip install -r requirements.txt
pip install flake8 pytest
./scripts/ci_gate.sh

# 前端 gate（如修改了 apps/dsa-web）
cd apps/dsa-web
npm ci
npm run lint
npm run test:i18n
npm run test
npm run build

# 前端 e2e（可选；自动启动真实后端、Vite 与本地 fake 模型端点）
DSA_WEB_E2E_RUN_ID=local-secret-bearing \
DSA_WEB_E2E_CREDENTIAL_BEARING=true \
DSA_WEB_E2E_TRACE=off \
DSA_PLAYWRIGHT_ARTIFACT_CANARY=stockpulse-local-canary-change-me \
DSA_WEB_E2E_ALPHA_API_KEY=stockpulse-local-canary-change-me \
  npm run test:smoke

# 扫描本地 Playwright 产物（必须使用专用测试 canary，不要使用真实凭据）
cd ../..
DSA_PLAYWRIGHT_ARTIFACT_CANARY=stockpulse-local-canary-change-me \
  python scripts/scan_playwright_artifacts.py apps/dsa-web/test-results/local-secret-bearing

# 真实登录后故意失败的安全诊断验收；临时 spec 与默认结果会自动清理
python scripts/check_playwright_failure_diagnostics.py
```

Web 界面文案、语言边界、领域字典和错误码约定见 [Web 国际化开发约定](web-i18n.md)。新增页面或语言时必须按领域扩展 `src/locales/`，不得在 JSX 中硬编码可见文案。

Playwright 默认使用一次性密码，并把 `.env`、SQLite 数据库、密码哈希与 session secret 全部隔离到 `test-results/<run-id>/runtime/`；场景需要的报告、任务、账户和配置必须由 fixture 或场景本身确定性播种，结束后清理 runtime，不读取或改写开发者 `.env`、数据库或认证文件。后端 Python 按祖先目录 `.venv`、`python3`、`python` 的顺序查找并在启动前打印选择；确定性场景固定 `retries: 0`。后端、Vite 与 fake provider 日志保存在 `test-results/<run-id>/service-logs/`，机器可读取结果写入同目录的 `playwright-results.json`；credential-bearing CI 的 repository config 将 trace 设为 `off`，扫描原始目录后仅从经过内容校验和二次扫描的 staging 目录上传文本日志、JSON 与 manifest，也不上传 screenshot、video 或 archive。仅在不含真实或可关联凭据的本地调试会话中，才可设置 `DSA_WEB_E2E_TRACE=retain-on-failure` 显式保留无媒体 trace；已知测试凭据环境变量会自动进入 credential-bearing 模式，不能与 `false` 标记或 trace opt-in 共存。credential-bearing 入口同时拒绝 `--trace` 强制模式、`--ui`/`--ui-host`/`--ui-port` 和替代 `--config`。Web preflight 使用 TypeScript AST 守卫追踪相对 import 图、`test.use`/`test.extend` 的本地 option 对象、别名、后赋值和静态 `Object.fromEntries`，并检查可识别 BrowserContext 上的直接/解构/`Reflect.get` tracing 访问；Playwright config 还锁定唯一由运行时策略控制的 `trace` 属性。任意动态属性名、由任意函数或外部 package 运行时构造的 test option，以及代码生成不属于静态模型；最终 project 配置由 global setup 再校验，原始 scanner 与 strict staging 是上传边界。PR 所需页面截图应来自不含凭据的独立人工验收会话并直接附在 PR 描述或评论中。如端口冲突，可通过 `DSA_WEB_SMOKE_BACKEND_PORT`、`DSA_WEB_SMOKE_FRONTEND_PORT`、`DSA_WEB_SMOKE_PROVIDER_PORT` 覆盖测试端口。

契约回归不能用 mock 数量、循环条目或注释编号代替语义覆盖。模型路由测试必须覆盖两条 Connection 的同名模型并断言具体 `ModelRef`；Portfolio 交易、资金流水、公司行为和 CSV commit 测试必须复用同一 operation ID 验证 timeout-after-commit 不重复入账，并验证同 ID 异 payload 冲突；Overlay 测试必须覆盖叠层仅顶层响应 Escape、焦点限制与恢复、背景 inert 和滚动锁定。每个 Playwright 验收场景使用独立可读 test 名称与关键断言。

前端本地联调：`npm run dev` 启动的 vite dev server 会把 `/api` 请求代理到 `DSA_WEB_DEV_API_PROXY`（默认 `http://127.0.0.1:8000`）；后端不在本机默认端口时，通过该环境变量指向实际后端地址。

## 📋 优先贡献方向

当前优先欢迎以下方向的贡献：

- 🔔 新通知渠道（钉钉、飞书、Telegram）
- 🤖 新 AI 模型支持（GPT-4、Claude）
- 📊 新数据源接入
- 🐛 Bug 修复和性能优化
- 📖 文档完善和翻译

## ❓ 问题解答

如有任何问题，欢迎：
- 创建 Issue 讨论
- 查看已有 Issue

再次感谢你的贡献！ 🎉
