# GitBook 部署说明

本手册目录已按 **GitBook 兼容结构** 组织，可同步到组织站点：

**后台站点（需登录）**  
https://app.gitbook.com/o/JMiVv6cqssblgINpUvgv/sites/site_gPScy

仓库根配置文件：`.gitbook.yaml`（`root: ./docs/ui-manual/`）。

---

## A. 同步到 GitBook.com（你的 `site_gPScy`）

GitBook 云端**不能**用仓库里的脚本代替你的登录态。请在浏览器里完成一次绑定：

### 1. 打开站点后台

打开上面的站点链接，确认 Space / Site 名称是否为操作手册用途。

### 2. 连接 GitHub 仓库

1. 在 GitBook 左侧进入 **Integrations** / **Git Sync**（文案可能是 *GitHub* / *Git Sync*）。  
2. 授权组织/账号 **SiinXu**（或你托管本仓库的账号）。  
3. 选择仓库：`SiinXu/stock-pulse-ai`（以实际 remote 为准）。  
4. **分支**建议：  
   - 先连 `docs/ui-manual-module-deep-dive` 预览 PR 内容，或  
   - 合入 `main` 后改跟 `main`。  
5. **内容根目录 / monorepo path** 填：

   ```text
   docs/ui-manual
   ```

   若控制台支持读取仓库根 `.gitbook.yaml`，应与其中 `root: ./docs/ui-manual/` 一致。

6. 确认识别到：  
   - `SUMMARY.md`（侧栏目录）  
   - `README.md`（首页）  
7. 保存并触发 **Sync / Import**。

### 3. 发布

同步成功后，在 GitBook 点 **Publish**（若站点还是草稿）。  
公开阅读地址在站点 **Settings → Domain / Public URL**（形如 `https://xxx.gitbook.io/yyy` 或自定义域名），与后台 `app.gitbook.com/.../sites/site_gPScy` 不是同一个链接。

### 4. 之后怎么更新

- 只改 `docs/ui-manual/**` 的 PR 合并到已绑定分支 → GitBook 自动同步（视你的 Sync 设置为 push 或 PR merge）。  
- 中英分册都在 `SUMMARY.md` 里；改目录请同时改 `SUMMARY.md`。

### 5. 同步时注意

| 点 | 说明 |
| --- | --- |
| 出站链接 `../beginner-client-setup.md` 等 | GitBook 子路径可能解析失败；可在 GitBook 里改成绝对 GitHub URL，或把安装指南也纳入同一 Space |
| Mermaid | 云端 GitBook 对 mermaid 支持因计划而异；失败时图会显示为代码块，正文仍可读 |
| 密钥 | 不要把 GitBook Token 写进仓库 |

---

## B. 本地 Honkit 预览（不登录 GitBook 也能看）

```bash
cd docs/ui-manual
npm install
npm run serve
# 浏览器打开 http://localhost:4000
```

只构建静态站：

```bash
cd docs/ui-manual
npm run build
# 产物在仓库根 .gitbook-ui-manual-site/
```

详见目录内 `package.json` 脚本。

---

## C. 本目录关键文件

| 文件 | 作用 |
| --- | --- |
| `SUMMARY.md` | 侧栏目录（中 + 英） |
| `book.json` | Honkit 本地书配置 |
| `README.md` | 书首页（中文） |
| `01-*.md` … `14-*.md` | 分册正文 |
| `package.json` | 本地 `honkit` 依赖 |

---

## D. 若同步失败常见原因

1. 根目录指到了仓库根而不是 `docs/ui-manual` → 找不到 `SUMMARY.md`。  
2. 绑定了错误分支 → 看不到最新手册。  
3. GitHub App 权限不足 → 重新授权仓库。  
4. `SUMMARY.md` 里某文件路径写错 → 同步日志会报 missing page。

本地可先跑：`cd docs/ui-manual && npm run build`，能完整生成再查 Git Sync 日志。
