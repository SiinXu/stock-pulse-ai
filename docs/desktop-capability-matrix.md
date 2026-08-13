# Desktop vs Web 能力矩阵

面向操作者与排障：桌面端与纯 Web 共用同一套私有本地 origin 上的 React 路由与 API，但**进程环境、协议唤起与安装升级**不同。本页是 #884 发布的产品矩阵；打包细节仍见 [桌面端打包说明](desktop-package.md)。English: [desktop-capability-matrix_EN.md](desktop-capability-matrix_EN.md)。

## 总览

| 能力 | Web（浏览器） | Desktop（Electron） | 说明 |
| --- | --- | --- | --- |
| 报告 / 分析 / 设置 UI | 是 | 是（同构建产物） | 桌面由本机 FastAPI 托管 `static/` |
| 登录与会话 Cookie | 是 | 是 | 同 Web origin；品牌迁移会复制会话状态 |
| `stockpulse://` 深链 | 否 | 是 | 见 [桌面深链策略](desktop-deep-link-policy.md) |
| 浏览器地址栏 / 分享 URL | 是 | 仅私有 origin | 外链转系统浏览器 |
| 自动更新与版本检查 | 否 | 是 | `window.dsaDesktop` 更新 API |
| 更新时保留 `.env` / DB / cache | N/A | 是 | Windows NSIS 备份/恢复；macOS 用 userData |
| 本地 Ollama 启停 / 内嵌 runtime | 探测远端服务 | 是 | Local Models 面板 |
| 生成后端 CLI（codex/claude/opencode） | 依赖宿主 PATH | 依赖 Desktop 子进程 PATH | macOS GUI 会补 Homebrew 常见路径 |
| CLI/PATH 可见性诊断 | 否 | 是 | `available` / `missing` / `unknown`；不暴露原始路径 |
| CLI 缺失可操作指引 | 否 | 是 | Model Sources 内打开终端 / 安装说明 |
| 调度进程模式文案 | Web 部署语义 | 桌面本机语义 | 以 Settings 调度区块与 #869 为准 |
| 环境变量 / `.env` 位置 | 服务端部署目录 | Windows：exe 旁；macOS：userData | 见打包说明 |
| `WEBUI_PORT` 决定连接地址 | 是 | 否 | 桌面自选 8000–8100 |

## PATH / CLI 诊断与指引

- 诊断对象：`ollama`、`codex`、`claude`、`opencode`
- 三态：`available` / `missing` / `unknown`（超时、权限、PATH 不可用 → `unknown`，**禁止 fail-open 成 available**）
- Renderer / IPC 只收到命令名、状态、原因码与已本地化文案；**永不**包含原始 PATH、PATH 条目或可执行文件绝对路径
- 缺失或未知时，Model Sources「本机 CLI」区提供：**打开系统终端**、**打开安装说明**（HTTPS allowlist）、**重新检测**

## 深链

策略与白名单以 [桌面深链策略](desktop-deep-link-policy.md) 为准。不在白名单内的链接会拒绝导航，并弹出不含原始 URL 的说明。

## 更新与本地数据留存

关键相对路径（Windows 安装目录 / macOS userData）包括：

- `.env`
- `data/stock_analysis.db`（及 `-wal` / `-shm`）
- `data/provider_cache/daily`
- `data/ollama/models`
- `data/alphasift/hotspots.json`、`hotspot.history.jsonl`、`hotspot_details/`、`snapshot.last_good.json`
- `logs/desktop.log`

验证测试覆盖真实目录结构（含中文路径段、嵌套目录、已存在目标）见 `apps/dsa-desktop/tests/main.test.js`。

## 明确非目标

- Desktop 不做完整 OS 自动化宿主
- 不为“与 shell 完全一致”放宽环境变量 denylist
