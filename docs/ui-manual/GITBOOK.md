# 用 GitBook / Honkit 预览本手册

本目录已按 **GitBook 兼容结构** 组织（`SUMMARY.md` + `book.json`），可用开源 **Honkit**（GitBook 维护分支）本地构建与预览。

> 云端 [gitbook.com](https://www.gitbook.com/) 若要同步仓库，需你在 GitBook 控制台绑定 GitHub 并选择本目录或 monorepo 子路径；本仓库不提交任何 GitBook 私密 Token。

## 本地一键预览（推荐）

在仓库根目录执行：

```bash
cd docs/ui-manual
npm install
npm run serve
```

浏览器打开终端提示的地址（默认 **http://localhost:4000**）。

只构建静态站点：

```bash
cd docs/ui-manual
npm install
npm run build
```

产物目录：仓库根下 `.gitbook-ui-manual-site/`（已在 `.gitignore` 忽略时不会进 Git；若未忽略请勿提交构建缓存）。

## 目录约定

| 文件 | 作用 |
| --- | --- |
| `SUMMARY.md` | 左侧目录（中英分册） |
| `book.json` | Honkit / GitBook 书配置 |
| `README.md` | 书首页 |
| `01-…`～`14-…` | 分册正文 |
| `package.json` | 本地 `honkit` 依赖与脚本 |

## 同步到 GitBook.com（可选）

1. 在 GitBook 创建 Space / 文档。  
2. 选择 **GitHub sync**，授权本仓库。  
3. 内容根目录选 `docs/ui-manual`（或按 GitBook 要求放置 `SUMMARY.md` 的路径）。  
4. 推送 `main` 或文档分支后，在 GitBook 控制台查看在线版。  
5. 发布权限、自定义域名在 GitBook 后台配置（与本仓库 CI 无关）。

## 注意

- 手册内相对链接（如 `../beginner-client-setup.md`）在 GitBook 子目录同步时，可能需要把安装指南一并纳入 Space，或改成仓库绝对 URL。本地 Honkit 预览时，出站 `../` 链接以构建器解析为准。  
- Mermaid 图：部分 GitBook/Honkit 主题默认不渲染 Mermaid；预览以正文与表格为主，图为辅助。  
- 本构建 **不替代** 产品 Web UI，只预览操作手册。
