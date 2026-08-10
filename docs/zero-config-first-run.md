# 零配置首次成功

Issue: [#796](https://github.com/SiinXu/stock-pulse-ai/issues/796)

English: [zero-config-first-run_EN.md](zero-config-first-run_EN.md)

## 验收含义

1. 全新环境，**没有** `.env` 密钥、**没有**主要模型 API Key。
2. 启动后能看到首次运行引导。
3. **不必填写任何云端必填项**即可看到一次分析结果形态：
   - 本机 Ollama 可达且至少有一个模型时，优先引导到**本地模型设置**。
   - Ollama 可达但模型列表为空时，明确提示先安装模型，并降级到演示路径。
   - 否则打开**离线示例分析**（始终标注为示例数据）。
4. 已有主要模型或既有配置的用户**不会被强制切换**新手默认，且就绪检查**绝不**改写其配置。

## API

| 方法 | 路径 | 是否写配置 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/onboarding/first-run` | 否 | 全新环境信号、新手推荐、本地探测快照、主 CTA |
| `GET` | `/api/v1/onboarding/demo-analysis?report_language=zh\|en\|ko` | 否 | 离线 fixture；始终 `is_sample=true` |

本地探测复用 `src/services/local_runtime_detect.py`；主要模型是否可运行复用系统设置的 authoritative setup check。`first-run` 只返回稳定的 reason code、参数和版本化 `snapshot_id`，不下发英文展示文案，也不提供检测后直接应用配置的语义。

## UI

- 自包含组件：`apps/dsa-web/src/components/onboarding/ZeroConfigFirstRunPanel.tsx`
- Playground：`zero-config-first-run-panel`
- 当前 PR 是自包含基础组件；Home / Settings 的产品入口仍是后续 **Integration Point**。
- 对 `configured` / `local_ollama` 路径，宿主必须提供设置跳转处理器。缺失时主按钮禁用并说明原因，不会静默无响应或替换成演示操作。

## 相关

- 官方预设：issue #795 / `config_presets.py`
- 后端探测波次：PR #817
- 小白安装指南：[beginner-client-setup.md](beginner-client-setup.md)
