# 贡献指南

感谢你对本项目的关注！欢迎任何形式的贡献。

## 🐛 报告 Bug

1. 先搜索 [Issues](https://github.com/ZhuLinsen/daily_stock_analysis/issues) 确认问题未被报告
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
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis

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

### Commit 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
feat: 新功能
fix: Bug 修复
docs: 文档更新
style: 代码格式（不影响功能）
refactor: 重构
perf: 性能优化
test: 测试相关
chore: 构建/工具相关
```

示例：
```
feat: 添加钉钉机器人支持
fix: 修复 429 限流重试逻辑
docs: 更新 README 部署说明
```

### 代码规范

- Python 代码遵循 PEP 8
- 函数和类需要添加 docstring
- 重要逻辑添加注释
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
npm run test:smoke
```

Web 界面文案、语言边界、领域字典和错误码约定见 [Web 国际化开发约定](web-i18n.md)。新增页面或语言时必须按领域扩展 `src/locales/`，不得在 JSX 中硬编码可见文案。

Playwright 默认使用一次性密码，并把 `.env`、SQLite 数据库、密码哈希与 session secret 全部隔离到 `test-results/runtime/`；场景需要的报告、任务、账户和配置必须由 fixture 或场景本身确定性播种，结束后清理 runtime，不读取或改写开发者 `.env`、数据库或认证文件。后端 Python 按祖先目录 `.venv`、`python3`、`python` 的顺序查找并在启动前打印选择；确定性场景固定 `retries: 0`。后端、Vite 与 fake provider 日志保存在 `test-results/service-logs/`，失败时由 CI 连同截图、trace 和 video 上传。如端口冲突，可通过 `DSA_WEB_SMOKE_BACKEND_PORT`、`DSA_WEB_SMOKE_FRONTEND_PORT`、`DSA_WEB_SMOKE_PROVIDER_PORT` 覆盖测试端口。

契约回归不能用 mock 数量、循环条目或注释编号代替语义覆盖。模型路由测试必须覆盖两条 Connection 的同名模型并断言具体 `ModelRef`；Portfolio 交易、资金流水、公司行为和 CSV commit 测试必须复用同一 operation ID 验证 timeout-after-commit 不重复入账，并验证同 ID 异 payload 冲突；Overlay 测试必须覆盖叠层仅顶层响应 Escape、焦点限制与恢复、背景 inert 和滚动锁定。每个 Playwright 验收场景使用独立可读 test 名称与关键断言。

前端本地联调：`npm run dev` 启动的 vite dev server 会把 `/api` 请求代理到 `DSA_WEB_DEV_API_PROXY`（默认 `http://127.0.0.1:8000`）；后端不在本机默认端口时，通过该环境变量指向实际后端地址。

## 📋 优先贡献方向

查看 [Roadmap](README.md#-roadmap) 了解当前需要的功能：

- 🔔 新通知渠道（钉钉、飞书、Telegram）
- 🤖 新 AI 模型支持（GPT-4、Claude）
- 📊 新数据源接入
- 🐛 Bug 修复和性能优化
- 📖 文档完善和翻译

## ❓ 问题解答

如有任何问题，欢迎：
- 创建 Issue 讨论
- 查看已有 Issue 和 Discussion

再次感谢你的贡献！ 🎉
