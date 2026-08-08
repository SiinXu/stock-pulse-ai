# 零配置首次成功

Issue: [#796](https://github.com/SiinXu/stock-pulse-ai/issues/796)

English: [zero-config-first-run_EN.md](zero-config-first-run_EN.md)

## 验收含义

1. 全新环境，**没有** `.env` 密钥、**没有**主要模型 API Key。
2. 启动后能看到首次运行引导。
3. **不必填写任何云端必填项**即可看到一次分析结果形态：
   - 本机 Ollama 探测成功时优先走**本地模型**（官方 `local-first` 预设非密钥字段）。
   - 否则打开**离线示例分析**（始终标注为示例数据）。
4. 已有主要模型或既有配置的用户**不会被强制切换**新手默认，且就绪检查**绝不**改写其配置。

## API

| 方法 | 路径 | 是否写配置 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/onboarding/first-run` | 否 | 全新环境信号、新手推荐、本地探测快照、主 CTA |
| `GET` | `/api/v1/onboarding/demo-analysis?report_language=zh\|en` | 否 | 离线 fixture；始终 `is_sample=true` |
| `POST` | `/api/v1/onboarding/apply` | 是（需 confirm） | 复用：`infrastructure=local_models` → `local-first` 预设 |

本地探测复用 `src/services/local_runtime_detect.py`。预设只读 `src/services/config_presets.py`。

## UI

- 自包含组件：`apps/dsa-web/src/components/onboarding/ZeroConfigFirstRunPanel.tsx`
- Playground：`zero-config-first-run-panel`
- Home / Settings 接线见 PR 的 **Integration Point**。

## 相关

- 官方预设：issue #795 / `config_presets.py`
- 后端探测波次：PR #817
- 小白安装指南：[beginner-client-setup.md](beginner-client-setup.md)
