# API 错误分类学

版本一 API 错误信封以稳定的机器可读 `error` 码为权威身份。本文档定义在**不替换**这些码的前提下，如何将码映射为类别、严重度与默认用户动作。

English: [api-error-taxonomy_EN.md](api-error-taxonomy_EN.md)

## 信封字段

| 字段 | 作用 |
| --- | --- |
| `error` | 稳定业务码（身份权威） |
| `message` | 诊断 / 旧客户端回退文案（非 Web 主文案） |
| `params` | 有界本地化插值参数 |
| `details` / `detail` | 嵌套诊断（`detail` 为 `details` 的弃用别名） |
| `category` | 由 `error` 推导的分类学类别（附加字段） |
| `severity` | `info` \| `warning` \| `error` \| `critical`（附加字段） |
| `trace_id` | 支持侧关联 ID |

## 默认动作（Web 约定）

| 动作 | UI 行为 |
| --- | --- |
| `retry` | **仅当调用方提供真实操作回调时**展示「重试」；只清除错误不算重试 |
| `settings` | 跳转设置深链 |
| `login` | 跳转登录 |
| `docs` | 在新标签打开相关文档 |
| `none` | 仅文案指引，无主按钮 |

实现位置：`src/api/v1/error_taxonomy.py`、`apps/dsa-web/src/api/error/taxonomy.ts`、`resolveErrorRemediation`、`ApiErrorAlert`。

分类严重度控制 Toast 的视觉 tone，但 API 操作失败仍使用 assertive `alert` 通知。普通 warning/info Toast 继续使用 polite `status`；视觉颜色不能静默降低错误的可访问性语义。

## 新增错误码

1. 稳定 snake_case `error` 码  
2. 登记到后端分类学  
3. 同步 Web 镜像  
4. 补充 `STABLE_ERROR_TEXT`（复用既有动作文案键）  
5. 运行 `python scripts/check_error_taxonomy.py` 与相关测试  

详见英文版完整类别表与验收命令。

## CI 守卫

`scripts/check_error_taxonomy.py` 在 `./scripts/ci_gate.sh deterministic` 中执行，断言：

1. Web `STABLE_ERROR_TEXT` 的每个码都在后端分类学中登记；
2. 后端与 Web 的 `ERROR_CODE_TAXONOMY` 码集合及
   `(category, severity, default_action)` 三元组一致。
