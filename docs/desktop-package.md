# 桌面端打包说明 (Electron + React UI)

本项目可打包为桌面应用，使用 Electron 作为桌面壳，`apps/dsa-web` 的 React UI 作为界面。

## 架构说明

- React UI（Vite 构建）由本地 FastAPI 服务托管
- Electron 启动时自动拉起后端服务，等待 `/api/health` 就绪后加载 UI
- 桌面端可见产品名、窗口加载页、可执行文件和新发布产物统一使用 `StockPulse`
- Windows 内部 `appId` 继续使用 `com.daily-stock-analysis.desktop` 作为稳定升级标识，避免改名时生成新的 NSIS 安装身份；它不是用户可见品牌
- Python 后端首次初始化 `DatabaseManager` 时同步完成有序数据库 migration，Electron 不复制 Schema 升级逻辑；通用 `/api/health` 不是数据库 readiness probe
- Windows 便携/安装模式下，用户配置文件 `.env`、数据库和持久化日线 provider cache 放在 exe 同级运行时目录；macOS 打包版使用 Electron 用户数据目录保存这些运行时数据
- 桌面端会自动从本机 `8000-8100` 选择可用端口，并把实际选择的端口同步给内置后端；桌面端不依赖 `.env` 里的 `WEBUI_PORT` 来决定窗口连接地址，避免用户改端口后 Electron 仍等待旧端口导致启动超时

## 本地开发

一键启动（开发模式）：

```bash
powershell -ExecutionPolicy Bypass -File scripts\run-desktop.ps1
```

或手动执行：

1) 构建 React UI（输出到 `static/`）

```bash
cd apps/dsa-web
npm install
npm run build
```

2) 启动 Electron 应用（自动拉起后端）

```bash
cd apps/dsa-desktop
npm install
npm run dev
```

首次运行时会自动从 `.env.example` 复制生成 `.env`。

## 桌面深链协议

桌面安装包注册 `stockpulse` 自定义协议。规范形式是
`stockpulse://app/<应用内路径>?<查询参数>`，例如：

```text
stockpulse://app/?stock=AAPL&workspace=watchlist
stockpulse://app/portfolio?account=7
stockpulse://app/stocks/HK00700?period=weekly&days=30
```

协议 authority 固定为 `app`。桌面壳只接受 Web 已声明为稳定产品入口的路径：

- `/`
- `/chat`
- `/portfolio`
- `/decision-signals`
- `/stocks/<stockCode>`，其中股票代码必须是单个 ASCII 路径段
- `/alerts`、`/backtest`、`/screening`、`/settings`、`/usage`

Electron 会保留已接受链接的路径和查询参数，并把它们映射到当前运行时选择的私有本地 Web origin；`desktop_version` 和 `cache_bust` 始终由当前桌面进程覆盖。Web 侧继续负责各页面参数的规范化、敏感键清理和无效资源回退。桌面壳会在加载页面前拒绝非 `stockpulse` 协议、非 `app` authority、用户名或密码、端口、fragment、控制字符或未编码空格、路径归一化或编码走私，以及白名单外路径。拒绝的链接不会改变当前页面，日志也不会记录其原始 URL 或查询参数。

冷启动时，Windows/Linux 从初始 argv 提取链接；macOS 通过 `open-url` 接收链接。若后端尚未通过健康检查，链接会排队到私有 Web origin 就绪后再作为首个产品页面加载。应用已运行时，Windows/Linux 的第二实例 argv 仍走同一验证入口，并先恢复、显示和聚焦主窗口；macOS `open-url` 使用同一排队与路由逻辑。没有协议 URL 的第二实例继续只聚焦现有窗口。

`apps/dsa-desktop/package.json` 的 electron-builder `protocols` 声明负责生成 macOS bundle 的 `CFBundleURLTypes`。electron-builder 24 不会用该字段生成 Windows 协议注册；Windows NSIS 安装器因此通过 `installer.nsh` 在当前用户的 `Software\Classes\stockpulse` 写入带引号的 exe 与 `%1` 命令，并只在该命令仍指向当前安装目录时随卸载清理。运行时同时调用 `app.setAsDefaultProtocolClient('stockpulse')` 作为开发态和注册修复入口。Electron 开发态会把当前入口脚本作为协议启动参数；操作系统级注册和最终安装行为仍应以打包产物为准。

macOS 安装包可用以下命令验证冷启动和已运行实例：

```bash
open "stockpulse://app/portfolio?account=7"
open "stockpulse://app/stocks/AAPL?period=weekly"
```

Windows 安装包使用 PowerShell 验证：

```powershell
Start-Process 'stockpulse://app/portfolio?account=7'
Start-Process 'stockpulse://app/stocks/AAPL?period=weekly'
```

验证时应确认链接落在预期页面、重复打开会唤起现有窗口，并用 `stockpulse://evil.example/settings` 或 `stockpulse://app/login` 确认拒绝路径不会改变当前页面。在非 Windows 环境只能验证 electron-builder 配置和确定性 argv 测试，不能替代 NSIS 安装后的注册表与二实例验收。

## 打包 (Windows)

### 前置条件

- Node.js 18+
- Python 3.10+
- 开启 Windows 开发者模式（electron-builder 需要创建符号链接）
  - 设置 -> 隐私和安全性 -> 开发者选项 -> 开发者模式

### 一键打包

```bash
powershell -ExecutionPolicy Bypass -File scripts\build-all.ps1
```

该脚本会依次执行：
1. 构建 React UI
2. 安装 Python 依赖
3. PyInstaller 打包后端
4. electron-builder 打包桌面应用

当前 Windows 安装包使用 NSIS 向导式安装流程，仅支持当前用户安装且已禁用管理员提权，安装时可手动选择目标目录（例如非 C 盘）。安装器通过 NSIS `.onVerifyInstDir` 回调在安装器层面阻止选择 `Program Files`、`Windows` 等系统保护目录——选择这些路径时"下一步"按钮会被自动禁用。安装完成后，桌面端仍会按现有逻辑在安装目录旁生成/读取 `.env`、`data/stock_analysis.db`（含 `data/stock_analysis.db-wal` / `data/stock_analysis.db-shm`）、`data/provider_cache/daily/` 和 `logs/desktop.log`。推荐使用默认的 per-user 安装目录。如果不想安装，仍可继续分发 `win-unpacked` 免安装包。

## GitHub CI 自动打包并发布 Release

仓库已支持通过 GitHub Actions 自动构建桌面端并上传到 GitHub Releases：

- 工作流：`.github/workflows/desktop-release.yml`
- 触发方式：
  - 推送语义化 tag（如 `v3.2.12`）后自动触发
  - 在 Actions 页面手动触发并指定 `release_tag`
- 产物：
  - Windows 安装包：Release 附件和本地 `apps/dsa-desktop/dist/` 中统一为 `stockpulse-windows-installer-<tag>.exe`
  - Windows 自动更新元数据：Release 附件会额外保留 `latest.yml` 和 `*.blockmap`，供安装版桌面端后台下载与校验更新；普通用户无需手动下载这些元数据。下载完成后用户确认“重启安装”时，桌面端会先停止内置后端、备份运行时文件，并以静默模式执行安装器。
  - Windows 免安装包：`stockpulse-windows-noinstall-<tag>.zip`
  - macOS Intel：`stockpulse-macos-x64-<tag>.dmg`
  - macOS Apple Silicon：`stockpulse-macos-arm64-<tag>.dmg`

### macOS 提示“应用已损坏，无法打开”

当前 macOS DMG 尚未使用 Apple Developer 证书签名和公证。通过浏览器下载后，macOS Gatekeeper 可能因此提示“StockPulse 已损坏，无法打开”或“无法验证开发者”；这通常是系统对未签名、未公证应用的拦截，不代表 DMG 文件必然损坏。

请按以下顺序排查：

1. 只从项目的 [GitHub Releases](https://github.com/SiinXu/stock-pulse-ai/releases) 下载附件，并确认安装包架构与 Mac 一致：Apple 芯片（M1/M2/M3/M4 等）使用 `stockpulse-macos-arm64-<tag>.dmg`，Intel 芯片使用 `stockpulse-macos-x64-<tag>.dmg`。不要对第三方转载或来源不明的安装包绕过 Gatekeeper。
2. 打开 DMG，将 `StockPulse` 拖入“应用程序”后尝试启动一次。若被拦截，进入“系统设置 -> 隐私与安全性”，在安全性提示处确认应用名称，然后点击“仍要打开”，按系统提示再次确认。较旧 macOS 的对应入口为“系统偏好设置 -> 安全性与隐私 -> 通用”。
3. 仅当安装包确认来自上述官方 Release、且“仍要打开”仍无法放行时，打开“终端”清除该应用的下载隔离属性，然后重新启动：

```bash
xattr -dr com.apple.quarantine "/Applications/StockPulse.app"
```

如果应用不在 `/Applications`，请将命令中的路径替换为实际 `.app` 路径。不要对整个“应用程序”目录执行 `xattr`，也不要对来源不明的应用执行此命令。长期彻底消除该提示需要在发布流程中接入 Apple Developer 签名与 notarization（公证），不属于上述临时放行步骤。

建议发布流程：

1. 合并代码到 `main`
2. 由自动打 tag 工作流生成版本（或手动创建 tag）
3. `desktop-release` 工作流自动构建并把两个平台安装包附加到对应 GitHub Release

## 发版前可复现验证（桌面更新链路）

桌面端自动更新链路依赖 Windows NSIS 安装产物、`latest.yml` 与 `*.blockmap` 元数据。当前桌面 CI 不覆盖 `desktop-release` 打包产物可发布链路，提交前建议补充如下本地验证：

说明：该清单专注于 Windows NSIS 安装版与 `electron-updater` 发布元数据。当前 Linux 环境无法直接产出 Windows 安装包和 updater 元数据（`latest.yml` / `*.blockmap`），此类链路需在 Windows 发布执行器或 Windows 本机环境复核。

若在非 Windows 环境无法完成上述验证，请在 PR 验收说明中明确补齐 Windows 发布链路复核人、复核时间窗及 `desktop-release` 产物检查结果（release/tag 与 `stockpulse-windows-installer-<tag>.exe`、`latest.yml`、`*.blockmap` 版本一致性与可下载性）。

1. 先构建 Web 静态产物（桌面端主窗口与设置页入口依赖）

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build
```

2. 回到桌面端，补齐依赖、运行 preload 单测、再执行 Electron 打包

```bash
cd ../dsa-desktop
npm ci
npm test
npm run build
```

在 Windows 发布复核环境，还可额外执行：

```powershell
./scripts/verify-desktop-updater-artifacts.ps1 -ReleaseTag v$(node -p "require('./apps/dsa-desktop/package.json').version")
```

> 预期当前执行环境不支持生成 Windows NSIS 安装器时，请在交付说明中明确注明平台限制，并要求指定的 Windows 发布链路复核人补齐该项验证。

3. 检查更新元数据是否产出

```bash
ls -1 dist | sort
ls -1 dist/*.yml dist/*.blockmap 2>/dev/null || true
```

4. 强制对齐版本与发布附件（可在 Windows 环境或能产出 NSIS 产物的执行器上复核）

```bash
RELEASE_TAG="v$(node -p \"require('./package.json').version\")"
REPO="SiinXu/stock-pulse-ai"

for f in dist/*latest.yml dist/*.blockmap dist/stockpulse-windows-installer-*.exe; do
  [ -f \"$f\" ] && echo \"[FOUND] $f\"
done

if [ -f dist/latest.yml ]; then
  echo \"---- latest.yml 版本片段 ----\"
  grep -E \"^version:|^files:|^sha512:\" dist/latest.yml
fi

echo \"---- Release 清单（人工核对）----\"
echo \"Release Tag: $RELEASE_TAG\"
echo \"Release 地址: https://github.com/$REPO/releases/tag/$RELEASE_TAG\"
echo \"应核对附件是否包含:\"
echo \"- stockpulse-windows-installer-*.exe\"
echo \"- latest.yml\"
echo \"- *.blockmap\"
echo \"并确保 latest.yml 中 version 与 tag 的语义化版本一致，path/url 与安装包附件名一致\"
```

5a. 建议在 PR 描述里记录的“可复核输出”（Windows）：

```bash
echo "release-tag=${RELEASE_TAG}"
echo "latest.yml version:"
grep -E "^version:" dist/latest.yml
echo "latest.yml files:"
sed -n '1,80p' dist/latest.yml
echo "packaging artifacts:"
ls -1 dist/*.yml dist/*.blockmap dist/*installer*.exe 2>/dev/null | sort
```

Windows 发布链路复核清单（在 PR 后由发布团队/维护者执行）：

- release/tag 与 `stockpulse-windows-installer-<tag>.exe` 的版本号一致；
- `latest.yml`、`stockpulse-windows-installer-<tag>.exe`、`*.blockmap` 同 tag 同步出现且可下载；
- `latest.yml` 中 `version` 与 Release tag 语义一致（去掉 `v` 前缀后比对），且 `path` / `files.url` 与安装包附件名一致；
- 如缺少上述文件或 `release-tag` 不匹配，需标注阻断并补齐 `desktop-release` 打包流程。

5. Windows/NSIS 产物与发布附件一致性请在 Windows 环境手动验证（可人工触发发布流程），并在升级后核对运行时文件留存：

   1. 安装前后分别记录安装目录中的 `.env`、`data/stock_analysis.db`、`data/stock_analysis.db-wal`、`data/stock_analysis.db-shm`、`logs/desktop.log` 的 SHA256；
   2. 确认桌面端下一次启动后，上述文件仍存在且与安装前记录一致，并确认 `data/provider_cache/daily/` 目录中的已有 cache 文件未丢失；
   3. 如不一致，可在应用退出后检查用户数据目录中的 `.dsa-desktop-update-backup` 是否清理完整，并结合最新日志串联排查。

Windows 平台建议使用 PowerShell 执行：

```bash
Get-FileHash .env,data\\stock_analysis.db,data\\stock_analysis.db-wal,data\\stock_analysis.db-shm,logs\\desktop.log -Algorithm SHA256
```

说明：应用已在 Windows NSIS 安装版的“重启安装”前停止内置后端、备份安装目录旁上述运行时文件，并以静默模式运行更新安装器，目的是避免安装向导抢先覆盖仍在运行的桌面端进程，同时降低更新过程中文件丢失风险；若恢复失败，桌面端会显示更新安装错误并保留手动下载路径供回退处理。此次修复仅改动 Windows 更新安装链路与内置后端进程生命周期处理，不涉及设置保存语义、模型运行时清理策略或配置迁移行为。

### 分步打包

1) 构建 React UI

```bash
cd apps/dsa-web
npm install
npm run build
```

2) 按现有脚本打包 Python 后端（脚本已内置 AlphaSift 与 AkShare 数据文件收集）

- Windows：

```bash
powershell -ExecutionPolicy Bypass -File scripts\build-backend.ps1
```

- macOS：

```bash
bash scripts/build-backend-macos.sh
```

该脚本会在安装依赖后执行 `--collect-all alphasift` 和 `--collect-data akshare`，并显式收集 `src.migrations`、registry、versions package 及 source-bound checksum 所需的 version `.py` 源码。构建完成后会校验 `alphasift.dsa_adapter` 和 `src.migrations.registry` 可导入，并确认 migration 源码与 AkShare 的 `file_fold/calendar.json` 已进入冻结产物，避免发行包在启动 migration、热点题材或日线增强路径中因缺少模块/package data 失败。

3) 打包 Electron 桌面应用

```bash
cd apps/dsa-desktop
npm install
npm run build
```

打包产物位于 `apps/dsa-desktop/dist/`。Windows 安装器会生成 `stockpulse-windows-installer-<tag>.exe`，安装向导中可选择安装目录。

## 目录结构

Windows 安装包模式下，安装器仅支持当前用户安装且已禁用管理员提权，用户可在安装向导中选择安装目录；安装器会在安装器层面阻止选择 `Program Files`、`Windows` 等系统保护目录（选择时"下一步"按钮自动禁用），安装完成后，应用会在安装目录旁生成/读取 `.env`、`data/stock_analysis.db`（含 `data/stock_analysis.db-wal` / `data/stock_analysis.db-shm`）、`data/provider_cache/daily/` 和 `logs/desktop.log`。请保留默认的 per-user 安装位置或选择其他用户可写目录。

`win-unpacked` 免安装模式下，目录结构如下：

```
win-unpacked/
  StockPulse.exe              <- 双击启动
  .env                        <- 用户配置文件（首次启动自动生成）
  data/
    stock_analysis.db         <- 数据库主文件
    stock_analysis.db-wal     <- WAL 日志文件（更新备份/恢复）
    stock_analysis.db-shm     <- WAL 共享元文件（更新备份/恢复）
    provider_cache/
      daily/                  <- 日线 provider 持久 cache（更新备份/恢复）
  logs/
    desktop.log               <- 运行日志
  resources/
    .env.example              <- 配置模板
    backend/
      stock_analysis.exe      <- 后端服务
```

## 配置文件说明

- Windows 桌面端的 `.env` 放在 exe 同目录下
- macOS 打包版的 `.env`、`data/` 和 `logs/` 放在 Electron 用户数据目录；新安装使用 `StockPulse` 目录，避免替换 `.app` 时丢失
- Desktop 默认把既有的 `PROVIDER_DAILY_CACHE_DIR` 解析为数据库旁的 `data/provider_cache/daily/`，避免相对路径落入冻结后端资源目录；进程环境或 `.env` 中的显式值仍按该顺序优先。显式外部目录不会被复制到安装目录的更新备份中，应由该目录自身的持久化/备份策略负责
- 该 cache 只覆盖已经成功获取并命中的日线请求；fresh/stale 时限继续由既有 `PROVIDER_DAILY_CACHE_*` 配置控制。它不阻断 market data、新闻、模型、通知或桌面更新外呼，也不等同于完整 Offline / Local Only / Privacy Mode
- 首次启动时自动从 `.env.example` 复制生成
- 从旧版本升级时，如果当前 `.app` 或与 `StockPulse.app` 同目录的 `Daily Stock Analysis.app` 内部仍有 `.env`、`data/stock_analysis.db` 或日志文件，新版本会在目标文件不存在时自动迁移到用户数据目录；已有目标文件不会被覆盖，旧应用包也不会被删除
- 从可见品牌仍为 `Daily Stock Analysis` 的版本首次升级时，StockPulse 会在 Electron ready 之前查找同级旧用户数据目录，并复制 `.env`、`data/`、`logs/`、Web 会话状态和待恢复的更新备份；任何已存在的 StockPulse 目标文件都不会被覆盖。每个缺失文件先完整复制到同目录临时文件，再以不覆盖目标的原子操作发布；进程中断留下的临时文件会在重试时清理
- 打包版会在品牌迁移前取得 Electron 单实例锁；同一用户同时启动的第二个 StockPulse 进程会退出并唤起已有窗口，不会并发写入迁移文件或迁移记录
- 品牌迁移完成后，新目录会保存 `.stockpulse-brand-migration.json`，记录旧目录、目标目录和逐项结果；旧目录不会被移动或删除，可用于审计和回滚。关键运行时数据复制失败时，本次启动会完整回退使用旧用户数据目录，不混用两个目录中的配置或数据库；新目录已有内容保持不变，后续启动可在故障解除后重试迁移
- 迁移不是双向同步：升级后在 StockPulse 中产生的新配置或数据不会写回旧目录。需要回滚旧版本时，应先完全退出应用并导出最新配置或备份 `data/`；删除或改名新目录后可在下一次升级时重新执行迁移
- 用户需要编辑 `.env` 配置以下内容：
  - `GEMINI_API_KEY` 或 `OPENAI_API_KEY`：AI 分析必需
  - `STOCK_LIST`：自选股列表（逗号分隔）
  - 其他可选配置参考 `.env.example`

### 配置备份 / 恢复 `.env`

- WebUI 与桌面端都可以从 `设置 -> 高级 -> 配置备份` 看到 `导出 .env` 和 `导入 .env` 按钮
- WebUI 非桌面运行时需要先开启管理员认证并完成登录；未开启认证时按钮会禁用，API 返回 `403`
- `导出 .env` 会导出当前**已保存**的 `.env` 备份文件；页面上尚未点击“保存配置”的本地草稿不会被导出
- `导入 .env` 会读取备份文件中的键值并合并到当前配置中，导入后会立即触发配置重载
- 导入是“键级覆盖”而不是整文件替换：备份文件中出现的键会覆盖当前值，未出现的键保持不变
- 如果当前页面还有未保存草稿，导入前会先提示确认，避免把本地草稿和已保存配置混在一起
- Web 端默认 `ADMIN_AUTH_ENABLED=false` 时，设置页会展示按钮为禁用态并提示先启用管理员鉴权；桌面端不受该配置影响，仍可直接使用配置备份/恢复能力。

> 建议：从旧版本升级的 macOS 用户仍可在升级前执行一次 `导出 .env` 作为保险；如果旧 `.app` 已经被整体替换，包内旧文件无法凭空恢复，只能通过备份导入。

### 数据库迁移与恢复

- Fresh DB 和从旧版 Desktop 保留的 DB 都在 Python 后端首次初始化 `DatabaseManager` 时执行同一 migration registry；数据库依赖路径会等待其完整成功或失败。
- 升级前完全退出 Desktop，再备份整个 `data/` 目录；不要在应用运行时只复制 `.db` 主文件。
- 迁移失败不会记录 applied row，且当前数据库依赖路径失败。停止竞争进程、修复磁盘/权限/数据前置条件后使用匹配版本向前重试，不删除 registry row，也不做 downgrade。
- `python -m src.migrations.cli status` 和 `verify` 使用 SQLite `mode=ro` 与 `PRAGMA query_only=ON` 只读检查 Desktop 数据库，不会创建数据库、补列、写 registry 或应用 pending migration；`status` 对 pending 返回 exit 0，`verify` 返回 `pending_migrations` 和非零 exit。应用后端首次进入 `DatabaseManager` 时仍会同步应用 pending migration。备份前必须完全退出 Desktop；开发 smoke 必须使用已显式初始化的临时 `DATABASE_PATH`，不得指向 Desktop 用户数据库。

完整的 ID、checksum、锁、Fresh/历史数据库和备份边界见 [数据库迁移](database-migrations.md)。

### 设置页版本信息

- `系统设置 -> 版本信息` 中的“桌面端版本”由 Electron 主进程的 `app.getVersion()` 提供，并通过 preload bridge 暴露给前端
- 开发态 `npm run dev` 与打包态 `npm run build` / 安装包都会复用同一条版本注入链路，不再在 `preload.js` 里维护独立硬编码版本号
- `README.md` 继续保留安装和运行入口说明；这类桌面端运行时细节统一落在本专题文档维护，避免入门文档膨胀

### 局域网访问 Windows 桌面端 WebUI

- 桌面端默认仍按 `WEBUI_HOST=127.0.0.1` 只允许本机访问，避免安装后无意暴露后端服务
- 如需让同一局域网内其他设备访问，在桌面端 `.env` 或 `系统设置 -> WebUI 监听地址` 中设置 `WEBUI_HOST=0.0.0.0`，保存后重启桌面端
- 桌面端会自动选择 `8000-8100` 中可用端口并传给后端；常见情况下仍是 `8000`，若端口被占用，可在 `logs/desktop.log` 查看 `Using port ...` 和 `Backend launch command=...`
- Windows 防火墙或服务器安全组仍需放行实际监听端口；对外暴露前建议同时启用 `ADMIN_AUTH_ENABLED`
- 即使后端绑定 `0.0.0.0`，桌面窗口自身仍会使用本机可访问地址完成健康检查和页面加载

### 桌面端更新提醒

- 应用在主界面加载完成后会后台检查 GitHub Releases 的最新正式版，并与当前 `app.getVersion()` 做语义化版本比较
- Windows NSIS 安装版会通过内置 GitHub 更新源自动下载新版本；下载完成后弹出一次性提醒，用户确认后静默重启并安装
- 自动更新静默安装会复用当前安装目录；如果用户安装时选择了非默认目录或带空格目录，后续自动更新仍会覆盖同一目录
- `系统设置 -> 版本信息` 中的“桌面端更新”区域可手动检查更新；若更新已下载，会展示“重启安装”操作
- Windows 免安装包、开发态和 macOS DMG 仍保持“提醒 + 跳转下载页”的兼容路径，不会因为网络失败而阻断桌面端启动
- 版本检查失败、GitHub API 超时、更新元数据缺失或下载安装异常时，会记录到 `logs/desktop.log`，设置页手动检查时会展示错误状态

## 常见问题

### 启动后一直显示 "Preparing backend..."

1. 检查 `logs/desktop.log` 查看错误信息
2. 确认 `.env` 文件存在且配置正确
3. 确认端口 8000-8100 未被占用；桌面端会自动选择其中一个可用端口，无需通过 `.env` 手动改 `WEBUI_PORT`
4. 如果日志里显示 Electron 等待的端口和后端实际监听端口不一致，优先升级到包含桌面端端口同步修复的版本

### 后端启动报 ModuleNotFoundError

PyInstaller 打包时缺少模块，需要在 Windows 与 macOS 后端构建脚本中同步增加 `--hidden-import`，并对冻结产物执行运行时导入校验。当前脚本会显式安装、冻结并探测 LiteLLM 运行路径需要的 `orjson` 以及启动必需的 `src.migrations.registry`；若日志包含 `No module named 'orjson'` 或 `No module named 'src.migrations'`，请升级到修复版本并重新构建，不能只在已发布目录中手工安装依赖。

如果日志提示缺少 `akshare/file_fold/calendar.json`，说明后端冻结产物没有完整收集 AkShare package data。请使用仓库当前的 `scripts/build-backend.ps1` 或 `scripts/build-backend-macos.sh` 重新构建；脚本会在生成桌面包前检查该文件，缺失时直接终止构建。

### UI 加载空白

确认 `static/index.html` 存在，如不存在需重新构建 React UI。

### macOS 升级后配置迁移

旧版本曾把运行时 `.env`、数据库和日志写在 `.app` 包内部。新版本改为使用 Electron 用户数据目录，并在旧 `.app` 包内文件仍可访问时做一次性迁移。迁移规则是“目标不存在才复制”，避免覆盖用户已经在新版本中保存的配置。

如果旧 `.app` 已经被整体替换，旧包内 `.env` 无法由新版本自动恢复。此时可使用升级前导出的 `.env` 在 `设置 -> 高级 -> 配置备份` 中手动导入；完成一次迁移或重新配置后，后续版本会继续复用用户数据目录，不再随 `.app` 替换丢失。

## 分发给用户

Windows 分发现在有两种方式：

1. 安装包：分发 `apps/dsa-desktop/dist/` 下的 `stockpulse-windows-installer-<tag>.exe`，用户安装时可自行选择目标目录
2. 免安装包：将 `apps/dsa-desktop/dist/win-unpacked/` 整个文件夹打包发给用户

使用 `win-unpacked` 免安装包时，用户只需：

1. 解压文件夹
2. 编辑 `.env` 配置 API Key 和股票列表
3. 双击 `StockPulse.exe` 启动
