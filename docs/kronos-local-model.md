# Kronos 本地金融模型（安装 · 配置 · 诊断）

本文是 **产品化安装路径**：如何安装可选依赖、下载权重、在 Web 设置中配置，并用状态面板验证。  
工具契约、注册门槛与输出 schema 详见 [Kronos Agent Tool 契约（英文）](kronos-agent-tool.md)。

## Kronos 在分析中做什么

- Kronos **不是** 聊天 LLM，也不会进入模型目录。
- 就绪后注册 Agent Tool：`forecast_kline_with_kronos`。
- 多 Agent 架构下由 **Technical Agent** 消费；单 Agent 架构则进入该 Agent 的工具注册表。
- 输入为近期日 K OHLCV，输出方向概率、收益区间与波动区间等（研究辅助，**非投资建议**）。
- 默认安装 **不** 导入 PyTorch、**不** 下载权重、**不** 注册该工具；主分析流程在 Kronos 未就绪时继续运行。

## 硬件与平台预期

| 项目 | 说明 |
| --- | --- |
| 依赖 | `requirements-kronos.txt`（含 `torch==2.13.0` 等，**默认不安装**） |
| 平台 | Linux x86_64/arm64、Windows x64、macOS Apple Silicon（macOS 14+）；**macOS Intel 不支持** 该 PyTorch 轮子 |
| 内存 | mini 适合首装；small/base 显著增加 RAM 与 CPU/GPU 占用 |
| 桌面端 | **预构建桌面包不支持 Kronos**（PyInstaller 后端不捆绑 torch/权重）。请在支持的源码环境使用 |
| Docker 默认镜像 | 默认不捆绑可选依赖与权重；需自定义镜像并挂载权重目录 |

## 安装可选依赖

先完成 StockPulse 常规环境，再安装隔离的 Kronos 集合：

```bash
python -m pip install --upgrade --constraint constraints.txt pip
python -m pip install --constraint constraints.txt --build-constraint build-constraints.txt -r requirements-kronos.txt
python -m pip check
```

## 下载权重（显式、可复述大小）

**Web 设置页不会触发下载。** 权重必须由操作者显式下载。

| `KRONOS_MODEL_SIZE` | 模型仓库 | Tokenizer | 大约下载量（模型+tokenizer） |
| --- | --- | --- | --- |
| `mini`（推荐首装） | `NeoQuasar/Kronos-mini` | `NeoQuasar/Kronos-Tokenizer-2k` | ~40 MB |
| `small` | `NeoQuasar/Kronos-small` | `NeoQuasar/Kronos-Tokenizer-base` | ~150 MB |
| `base` | `NeoQuasar/Kronos-base` | `NeoQuasar/Kronos-Tokenizer-base` | ~500 MB |

推荐使用仓库脚本（下载前打印大小；需 `--yes` 或交互确认；在 `huggingface_hub` 支持时尽量断点续传）：

```bash
python scripts/download_kronos_weights.py --list-sizes
python scripts/download_kronos_weights.py \
  --size mini \
  --weights-dir "$HOME/.local/share/stockpulse/kronos" \
  --yes
```

也可手动使用 `hf download`（见 [kronos-agent-tool.md](kronos-agent-tool.md)）。目录结构示例：

```text
<KRONOS_WEIGHTS_DIR>/
  Kronos-mini/
    config.json
    model.safetensors
  Kronos-Tokenizer-2k/
    config.json
    model.safetensors
```

## 配置项

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `KRONOS_ENABLED` | `false` | 启用本地工具；**改后需重启进程** 才能注册插件 |
| `KRONOS_MODEL_SIZE` | `mini` | `mini` / `small` / `base` |
| `KRONOS_WEIGHTS_DIR` | 空 | 本地绝对路径根目录 |

Web 设置：**AI 与模型 → 本地模型**，包含 Kronos 状态面板与上述三项。帮助文案说明「需重启」与「网页不下载」。

示例：

```dotenv
KRONOS_ENABLED=true
KRONOS_MODEL_SIZE=mini
KRONOS_WEIGHTS_DIR=/absolute/path/to/kronos-weights
```

## 用状态面板验证

1. 打开 **设置 → AI 与模型 → 本地模型**。
2. 查看 **Kronos 状态** 面板（`GET /api/v1/system/config/kronos/status`）：
   - 可选依赖 import 探测（按包名，模块级不 import torch）
   - 权重目录是否存在及大小/mtime
   - 启用开关
   - 每个状态下的 **下一步** 操作提示
3. 就绪后重启（若刚启用），在 Agent / Technical Agent 路径确认工具可用。

## 状态矩阵（简表）

| 状态 reason | 含义 | 下一步 |
| --- | --- | --- |
| `disabled` | 未启用 | 装依赖 → 下载权重 → 配置目录 → 启用 → 重启 |
| `dependencies_missing` | 可选包缺失 | `pip install -r requirements-kronos.txt`（见上文） |
| `weights_dir_*` / `weights_incomplete` / `weights_invalid` | 权重路径或文件问题 | `scripts/download_kronos_weights.py` 或修复目录 |
| `ready` | 本地门禁通过 | 若工具未注册则重启；再走 Agent 路径 |
| `packaged_desktop_unsupported` | 预构建桌面 | 改用源码环境 |

## 失败不拖垮主流程

- 未启用或门禁失败：**不注册** 工具，启动日志给出可操作原因。
- 工具调用失败：返回 `schema_version=kronos-forecast-v1` 的 typed error（含 `code` / 提示），**不** 中断整次分析。
- 永远不在分析路径中自动联网下载权重。

## 故障排查

| 现象 | 处理 |
| --- | --- |
| 设置里找不到 Kronos | 升级到包含本功能的版本；查看本地模型页 |
| 依赖探测失败 | 确认安装了 `requirements-kronos.txt` 且 `pip check` 通过 |
| 权重 incomplete/invalid | 重新运行下载脚本或核对 `config.json` + `model.safetensors` |
| 启用后仍无工具 | **重启** API/CLI 进程；确认 `KRONOS_ENABLED=true` |
| 桌面端提示不支持 | 预期行为；使用源码后端 |
| macOS Intel 装不上 torch | 当前可选依赖矩阵不支持；与默认应用无关 |

## 相关文档

- [Kronos Agent Tool 契约](kronos-agent-tool.md)
- [FAQ](FAQ.md) / [FAQ (EN)](FAQ_EN.md)
- [本地模型目录（Ollama 等）](local-model-catalog.md)
