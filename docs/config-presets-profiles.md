# 推荐配置预设与 stockpulse-profile YAML

本文说明官方**推荐配置预设**以及版本化的 **stockpulse-profile** YAML 格式（issue #795）。

## 目标

- 一键（先确认）应用经过测试的、**不含密钥**的配置组合。
- 可移植的配置包导入/导出，便于审阅与分享。
- 本地优先：在 Ollama / Model Pack / CLI 健康时优先推荐。
- 结构可被未来的引导式 onboarding（#589）复用。

## 官方预设

| ID | 显示名 | 推荐条件 |
| --- | --- | --- |
| `local-first` | Local-first (Ollama / Model Pack) | Ollama 健康或存在 Model Pack |
| `cli-backends` | CLI backends | 检测到 `codex` / `claude` / `opencode` CLI |
| `cloud-balanced` | Cloud balanced | 已有云端凭证；无本地运行时的默认推荐 |
| `power-user` | Custom / advanced | 显式高级路径；几乎不强制键 |

预设数据在 `src/services/config_presets.py`，**只通过** `SystemConfigService` 写入。

## stockpulse-profile YAML v1

```yaml
apiVersion: stockpulse/v1
kind: Profile
metadata:
  name: local-first-ollama
  displayName: Local-first (Ollama)
  description: 优先本地模型；从不包含密钥
  version: "1.0.0"
  tags: [local, privacy]
spec:
  llm:
    preferenceOrder: [ollama, model_pack, cli, cloud]
    config:
      GENERATION_BACKEND: litellm
      LLM_CONFIG_MODE: channels
      # 仅连接 / 模型 id — 从不写密钥
  strategies:
    enabled: [bull_trend]
  features:
    beginnerMode: true
  requirements:
    minRamGb: 16
    needsOllama: true
```

示例见 `docs/examples/profiles/`。

### 安全规则（强制）

**配置档案永远不会导出密钥值。**

- 导出排除含 `KEY` / `TOKEN` / `SECRET` / `PASSWORD`、`*_EXTRA_HEADERS` 以及 `LITELLM_CONFIG` 的键。
- 导入若含密钥形态键，返回 `config_profile_secret_rejected` 并拒绝。
- 应用路径不会伪造 API key。
- 规则同时写在代码、测试与本文档中。

## API

基路径：`/api/v1/config-profiles`

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/presets` | 列出预设 + 本地优先排序 |
| `POST` | `/presets/{id}/preview` | 应用前 diff |
| `POST` | `/presets/{id}/apply` | 经 SystemConfigService 写入非敏感键 |
| `GET` | `/export` | 导出已剥离密钥的 YAML |
| `POST` | `/import/preview` | 校验 + 预览 |
| `POST` | `/import/apply` | 应用导入 |

apply/import 需要当前 `config_version`（与系统配置乐观并发一致）。

## Web UI

设置 → **高级** → **配置备份** 中的 **推荐配置预设与配置档案** 面板：

1. 根据运行时检测给推荐预设打标。
2. 应用前必须确认变更摘要。
3. 导出下载 YAML；导入先预览 diff 再写入。

## 相关文档

- [LLM 配置指南](./LLM_CONFIG_GUIDE.md)
- [新手客户端设置](./beginner-client-setup.md)
- [Model Packs](./model-packs.md)
