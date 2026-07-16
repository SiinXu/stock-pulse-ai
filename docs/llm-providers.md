# LLM 服务商配置指南

本文面向首次配置用户，说明如何选择 LLM 配置方式、如何把 Web 设置页「模型接入」的模型服务预设映射到 `.env` / GitHub Actions，以及如何处理常见检测错误。

> 本页未引入新的外部 provider、模型名或 Base URL 兼容行为，仅整理配置参考与官方来源；实际兼容性仍以仓库当前运行时依赖与测试结论为准。

> - 运行时基础：`requirements.txt` 当前锁定 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`，兼容语义以该版本约束下实现为准。
> - 验证闭环：系统配置链路回归见 `tests/test_system_config_service.py` 与 `tests/test_system_config_api.py`，`Web` 侧配置页交互回归见现有组件测试用例。
> - 回退路径：保留旧变量不做自动迁移；可通过 Web/桌面导出备份后 `POST /api/v1/system/config/import` 回滚，或手动恢复历史 `LLM_*` / `LITELLM_*` / `AGENT_*` / `VISION_MODEL` 配置。

实际可用模型、额度、区域限制和价格以各服务商控制台为准；如果模型发现失败，可在“模型接入”的连接模型管理中手动添加模型 ID。Web 设置页展示的服务商元数据（标签、默认 Base URL、协议、凭据与地址要求、发现能力、能力标识）统一来自后端服务商目录 `GET /api/v1/system/config/llm/providers`（单一权威源，前端不再维护并行清单）；能力显示文案、官方来源链接与配置注意事项属前端 curated 展示内容，仅用于配置参考，不代表运行时能力已验证通过。

## 先选配置方式

| 方式 | 适合谁 | 主要变量 | 说明 |
| --- | --- | --- | --- |
| 极简 legacy | 只想快速跑通一个模型的用户 | `LITELLM_MODEL` + 对应 provider key | 最少变量，适合本地快速开始；不适合复杂 fallback。 |
| Channels | 需要多个 provider、同一 provider 多连接、多个 key 或 fallback 的用户 | `LLM_CHANNELS` + `LLM_<CONNECTION>_*` | 推荐默认路径；Web 设置页保存的也是这一层配置。 |
| YAML | 熟悉 LiteLLM 路由、负载均衡和企业网关的用户 | `LITELLM_CONFIG` / `LITELLM_CONFIG_YAML` | 优先级最高；一旦有效生效，Channels 和 legacy 不再参与本次请求。 |

优先级保持不变：`LITELLM_CONFIG` / `LITELLM_CONFIG_YAML` > `LLM_CHANNELS` > legacy provider keys。P4 只补文档，不迁移、不清空、不静默改写旧配置。

Channels 中连接名与 Provider 身份是两个字段。新配置使用 `LLM_<CONNECTION>_PROVIDER=<provider_id>` 保存后端 Provider Catalog ID，因此 `openai_work` 和 `openai_personal` 可以同时属于 OpenAI，重命名连接也不会改变服务商身份。旧配置没有该字段时，仅当连接名精确等于 Catalog ID 才兼容识别；系统不会按 `openai2` 等名称前缀猜测，也不会静默回写旧配置。只有持久化身份确实无法识别的 legacy 连接才按 Custom 迁移处理；Catalog 请求暂时失败不会改变已保存卡片的 Provider 身份。

任务路由不再用 runtime route 单独承担身份。可用模型目录为每个 `connection_id + runtime_route` 生成稳定 `ModelRef`；同一 Provider 的两条 Connection 即使提供同名模型，也会保持为两个可区分选项并解析到各自凭据。旧裸 route 唯一匹配时继续兼容，多连接歧义时以 `ambiguous_model_route` 要求确认。删除或停用 Connection、删除同名模型时，引用检查按 `ModelRef` 精确定位，不会影响另一条 Connection 的同名模型。

Generation backend 配置是更外层的运行时选择契约。Phase 4 支持 `GENERATION_BACKEND=litellm|codex_cli|claude_code_cli|opencode_cli`，但本地 CLI backend 不是 LiteLLM provider；不要配置成 `LITELLM_MODEL=codex_cli/...`、`LITELLM_MODEL=claude_code_cli/...` 或 `LITELLM_MODEL=opencode_cli/...`。`codex_cli` preset 使用 `codex exec --output-last-message <temp-file> -` 读取最终响应；`claude_code_cli` preset 使用 `claude --safe-mode --tools "" --disallowedTools "mcp__*" --strict-mcp-config --no-session-persistence --output-format json -p <static instruction>`，完整 DSA prompt 走 stdin，并只从 JSON envelope 的 `result/success` 字段提取最终文本，参数依据见 [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)；`opencode_cli` preset 使用 `opencode --pure run --format json [--model <OPENCODE_CLI_MODEL>] <static instruction> --file <temp prompt file>`，仅在显式配置 `OPENCODE_CLI_MODEL` 时追加 `--model`，完整 DSA prompt 走权限受控的临时文件，并只从无工具事件的 JSON event text 输出提取最终文本，参数依据见 [OpenCode CLI reference](https://opencode.ai/docs/cli)，配置合并语义见 [OpenCode config reference](https://opencode.ai/docs/config)。诊断 stdout/stderr 与最终响应一起受 `GENERATION_BACKEND_MAX_OUTPUT_BYTES` 总上限约束，超限时返回结构化 `output_too_large`。`GENERATION_FALLBACK_BACKEND=` 空值会在本地 `.env` 禁用 backend-level fallback，未配置时默认回退到 `litellm`；默认 GitHub Actions workflow 未配置该变量时会显式使用 `litellm`，如需禁用 fallback 可设为 primary backend 走 self no-op。Agent 工具调用仍使用 LiteLLM；Web 设置页只暴露 `AGENT_GENERATION_BACKEND=auto|litellm`，手写 `codex_cli|claude_code_cli|opencode_cli` 不会启用 text-only Agent mode，只会返回明确 unsupported tool-calling 诊断。

生成后端状态接口与 Web 面板会把轻量检查和冒烟测试分开展示：快速检查只读取已保存 `.env`、运行时兜底值和当前草稿，不写配置、不重载运行时，也不发起真实模型请求；只有 JSON 冒烟测试会使用固定的 JSON 提示词和 schema 发起真实请求。`health_status` 与 `last_error_code/message` 是本次计算结果，不表示历史最后错误。本地 CLI preset 的 `supports_tools=false` 仅表示不支持 DSA Agent 工具调用链路，不代表普通文本生成不可用。

Phase 6a Tool Surface 只补充 AgentBackend 前置的内部工具面：统一 DSA 工具 schema、public descriptor、MCP-compatible descriptor、scope guard、结构化错误、审计摘要和脱敏诊断。stock-scoped 工具调用必须显式传入 `ToolAccessContext.stock_scope`；有 `stock_code` 参数但未声明 stock scope 的工具会 fail-closed。它不新增 provider、模型、Base URL、README、`.env`、API、Web 配置入口、MCP server 或外部 runtime adapter，也不改变 `GENERATION_BACKEND` / `AGENT_GENERATION_BACKEND` 路由。后续 Codex / Claude / OpenCode / Hermes adapter 必须消费这层 Tool Surface，不能绕过它直接拼 provider-specific tool schema；真实 Agent tools 能力仍必须由 wire-level tool call / tool result roundtrip probe 证明。

本 PR smoke 验证版本为 `claude 2.1.177 (Claude Code)` 与 `opencode 1.17.11`，不声明更宽最低版本。如果用户安装的 CLI 不支持这些固定 preset 参数或非交互输出契约，DSA 会返回结构化 `capability_unsupported`、`cli_contract_unsupported`、`invalid_json`、`schema_validation_failed` 或对应 backend error，并在配置 backend fallback 时回退到 `litellm`。

本地 CLI Backend 不等于离线模型。Docker、云服务器和 CI 不天然拥有本机 CLI 登录态；macOS 从 Finder/Dock 启动桌面端时不继承 shell PATH，打包桌面端会在启动后端时补入常见 Homebrew 路径，如果设置检查仍提示找不到 CLI 可执行文件，需要完全退出并重开 DSA。DSA 不读取 Codex/Claude/OpenCode credential 文件，也不为 OpenCode 生成或搬运 provider API key；子进程可能按 CLI 自身机制使用本机登录态或配置，股票代码、新闻、持仓上下文、分析 prompt 和报告草稿可能被对应 CLI 背后的服务处理。DSA 默认只继承最小运行环境，并拒绝通配继承 `CLAUDE_*`、`ANTHROPIC_*`、`OPENCODE_*`、provider API key/token/base-url/model env 和 webhook tokens，降低父进程配置泄漏风险；`CODEX_HOME` 仅作为既有 Codex CLI 登录目录兼容的 exact-name 例外保留。

`opencode_cli` 是 experimental/limited generation backend，不支持 OpenCode serve / web / ACP / MCP / attach / `--dangerously-skip-permissions`。DSA 默认使用本机 OpenCode 的默认模型；`OPENCODE_CLI_MODEL` 只是可选模型覆盖值，配置时才传给 OpenCode `--model`。DSA 会在临时 cwd 写入最小项目 `opencode.json`，但 OpenCode resolved config 仍可能包含用户本机全局配置；运行时安全边界同时依赖 `--pure`、env denylist、prompt file 权限和 event extractor fail-closed。

## Web 设置页路径

推荐优先使用 Web 设置页完成配置：

1. 打开设置页的「AI 与模型 → 模型接入」（模型服务商 / 模型连接 / 可用模型的唯一入口）。
2. 点击「添加模型服务」，选择模型服务商并创建一条连接（同一服务商可创建多条连接）。
3. 填入 API Key（官方服务商默认端点无需填写 Base URL；自定义兼容服务需填写 Base URL；Ollama/localhost 免 Key）。
4. 新建连接不会预填示例模型（模型名会过期，不作为默认写入配置）。只有 Provider Catalog 标记支持发现时才显示「获取模型」；OpenAI-compatible 使用模型列表接口，Ollama 使用 `/api/tags`。不支持发现或发现失败时逐个手动添加模型；发现结果不会自动全选，没有模型时连接保持“未完成”状态。
5. 点击「测试连接」确认鉴权、模型名、额度和响应格式正常。
6. 在「任务路由」为报告 / Agent / Vision 等任务从已接入模型中选择模型（底层 route 由系统生成，无需手写 `provider/model`）。
7. 如需确认 JSON / tools / stream / vision 能力，手动勾选「运行时能力检测」后再触发；该检测会产生真实 LLM 请求，结果只代表当前账号、模型和 endpoint 的一次 best-effort 检测，不会写回 `.env`，也不会阻止保存。

日常设置修改按字段组在停止编辑 700ms 后自动保存，不显示全局 Save。AI 模型相关键共享一个原子组；失败或 409 冲突会保留草稿，并提供重试、恢复服务器值或逐字段解决冲突，当前组 Reset 不影响其它设置。连接测试与模型发现不会因自动保存而运行。

> 底层仍以 `LLM_CHANNELS` + `LLM_<CONNECTION>_*` 存储，其中 `LLM_<CONNECTION>_PROVIDER` 保存服务商身份（“渠道/channel”是底层兼容字段与开发者术语）；普通界面统一使用「模型服务商 / 模型连接 / 可用模型 / 任务模型」。

任务路由中的历史值如果不在当前可用模型目录中会保留并标记“当前配置不可用”，保存不会静默删除。删除仍被报告、Agent、Vision 或 fallback 引用的单个模型时，Web 会列出全部引用并允许在同一草稿中选择替代模型；直接 API 请求会返回 `model_in_use` 和 `details.referenced_by`。替换引用与删除模型在同一次更新中可原子成功，未替换的历史失效值仍按 `unknown_model` 处理。

Provider 身份、双语标签、protocol、默认 Base URL、发现能力、本地/自定义属性以及获取凭据、控制台、模型列表和文档地址都来自后端 Catalog；缺少链接时 Web 不渲染空操作。动态 Connection 的 required/visible/enabled 与可写字段集合只来自同一 API 返回的 `connection_fields` Schema：只要该属性存在（包括显式 `[]`），Web 就不读取 Catalog 的 legacy requirement flags；只有旧后端完全省略该属性时才启用隔离的 rolling-upgrade fallback。AND 条件中任一未知 operator 都优先于更早的未满足条件，字段保持可见、只读并显示诊断，同时阻止保存。通用配置 Schema 仍是字段 ownership 与条件契约的唯一真源：AI 字段缺失或携带未知 `ui_placement` 时只进入「高级」只读诊断，滚动部署不会重新暴露第二套普通模型表单。

## Channels 示例

### DeepSeek 官方渠道

```env
LLM_CHANNELS=deepseek
LLM_DEEPSEEK_PROVIDER=deepseek
LLM_DEEPSEEK_PROTOCOL=deepseek
LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_DEEPSEEK_API_KEY=sk-xxx
LLM_DEEPSEEK_MODELS=deepseek-v4-flash,deepseek-v4-pro
LITELLM_MODEL=deepseek/deepseek-v4-flash
```

### OpenAI-compatible 聚合或自定义网关

```env
LLM_CHANNELS=my_proxy
LLM_MY_PROXY_PROVIDER=custom
LLM_MY_PROXY_PROTOCOL=openai
LLM_MY_PROXY_BASE_URL=https://your-proxy.example.com/v1
LLM_MY_PROXY_API_KEY=sk-xxx
LLM_MY_PROXY_MODELS=gpt-5.5,claude-sonnet-4-6
```

OpenAI-compatible Base URL 只填到服务商兼容入口，不额外拼接 `/chat/completions`。本地 `.env`、Docker 和自托管脚本可以直接使用自定义 channel；GitHub Actions 需要 workflow 显式透传同名 `LLM_MY_PROXY_*` 变量。
小米 MiMo 示例同理：适用于本地 `.env`、Docker 或自托管脚本；若在 GitHub Actions 使用 `LLM_CHANNELS=mimo`，需要在 workflow 中手动补齐 `LLM_MIMO_*` 映射后方可生效。

## 常用服务商预设

| 服务商 | 渠道名 | 协议 | Base URL | 模型示例 |
| --- | --- | --- | --- | --- |
| AIHubmix | `aihubmix` | `openai` | `https://aihubmix.com/v1` | `gpt-5.5,claude-sonnet-4-6,gemini-3.1-pro-preview` |
| Anspire Open | `anspire` | `openai` | `https://open-gateway.anspire.cn/v6`（示例） | `Doubao-Seed-2.0-lite,Doubao-Seed-2.0-pro,qwen3.5-flash,MiniMax-M2.7`（示例） |
| OpenAI | `openai` | `openai` | `https://api.openai.com/v1` | `gpt-5.5,gpt-5.4-mini` |
| DeepSeek | `deepseek` | `deepseek` | `https://api.deepseek.com` | `deepseek-v4-flash,deepseek-v4-pro` |
| Gemini | `gemini` | `gemini` | 留空 | `gemini-3.1-pro-preview,gemini-3-flash-preview` |
| Anthropic Claude | `anthropic` | `anthropic` | 留空 | `claude-sonnet-4-6,claude-opus-4-7` |
| Kimi / Moonshot | `moonshot` | `openai` | `https://api.moonshot.cn/v1` | `kimi-k2.6,kimi-k2.5` |
| 通义千问 / DashScope | `dashscope` | `openai` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.6-plus,qwen3.6-flash` |
| 智谱 GLM | `zhipu` | `openai` | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.1,glm-4.7-flash` |
| MiniMax | `minimax` | `openai` | `https://api.minimax.io/v1` | `MiniMax-M3,MiniMax-M2.7,MiniMax-M2.7-highspeed` |
| 小米 MiMo | `mimo` | `openai` | 官方控制台提供（Actions 默认未映射） | 官方文档/控制台为准 |
| 火山方舟 / 豆包 | `volcengine` | `openai` | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-1-6-251015,doubao-seed-1-6-thinking-251015` |
| 硅基流动 / SiliconFlow | `siliconflow` | `openai` | `https://api.siliconflow.cn/v1` | `deepseek-ai/DeepSeek-V3.2,Qwen/Qwen3-235B-A22B-Thinking-2507` |
| OpenRouter | `openrouter` | `openai` | `https://openrouter.ai/api/v1` | `~anthropic/claude-sonnet-latest,~openai/gpt-latest` |
| Ollama | `ollama` | `ollama` | `http://127.0.0.1:11434` | `llama3.2,qwen2.5` |

## 官方来源与兼容性

| 服务商 | 官方来源 | 兼容说明 |
| --- | --- | --- |
| Anspire Open | [Anspire Open](https://open.anspire.cn/) | `ANSPIRE_API_KEYS` 在未配置更高优先级 OpenAI-compatible 来源时可用于大模型网关与搜索；页面与 `.env` 默认示例为 `openai/Doubao-Seed-2.0-lite` + `https://open-gateway.anspire.cn/v6`，是否可用以控制台与模型权限为准。 |
| OpenAI | [模型列表](https://platform.openai.com/docs/models) | 官方模型页建议从 `gpt-5.5` 开始，低延迟/低成本场景使用 `gpt-5.4-mini` 或 `gpt-5.4-nano`。 |
| DeepSeek | [快速开始](https://api-docs.deepseek.com/) | 官方 OpenAI Base URL 为 `https://api.deepseek.com`；`deepseek-chat` / `deepseek-reasoner` 将于 2026-07-24 弃用，当前模板直接使用 `deepseek-v4-flash` / `deepseek-v4-pro`。 |
| Gemini | [模型列表](https://ai.google.dev/gemini-api/docs/models) | Gemini 3.1 Pro / Gemini 3 Flash 仍为 preview；如需生产稳定性，可在控制台改回 2.5 稳定模型。 |
| Anthropic Claude | [模型概览](https://docs.anthropic.com/en/docs/about-claude/models/all-models) | Claude 当前 API ID 包含 `claude-sonnet-4-6`、`claude-opus-4-7`；Sonnet 更适合作为默认性价比入口。 |
| Kimi / Moonshot | [Kimi K2.6 快速开始](https://platform.kimi.com/docs/guide/kimi-k2-6-quickstart)、[模型列表](https://platform.kimi.com/docs/models) | 官方推荐 `kimi-k2.6`；`kimi-k2` 系列将在 2026-05-25 下线，旧 `moonshot-v1-*` 仅保留为稳定旧工作负载选择。 |
| 通义千问 / DashScope | [文本生成](https://help.aliyun.com/zh/model-studio/text-generation-model/) | 百炼推荐 `qwen3.6-plus`，确认效果后可用 `qwen3.6-flash` 降低成本。 |
| 智谱 GLM | [模型概览](https://docs.bigmodel.cn/cn/guide/start/model-overview)、[GLM-5.1](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.1) | `glm-5.1` 是当前旗舰；`glm-4.7-flash` 作为轻量/免费模型示例。 |
| MiniMax | [OpenAI API 兼容](https://platform.minimax.io/docs/api-reference/text-chat)、[获取模型列表](https://platform.minimax.io/docs/api-reference/models/openai/list-models)、[Pricing](https://platform.minimax.io/docs/guides/pricing-paygo) | 官方 OpenAI-compatible Base URL 为 `https://api.minimax.io/v1`，并列出 `MiniMax-M3`（默认，支持图片输入，官方支持最多 1M 输入上下文，pricing 区分 `<=512K` 与 `>512K` 输入两档价格）、`MiniMax-M2.7`、`MiniMax-M2.7-highspeed`，以及 Legacy 模型 `MiniMax-M2.5`。本仓库 fallback 成本估算保守按 `<=512K` 价格档注册 M3，并保留 M2.5 legacy 定价以兼容历史用户配置；中国区 Coding 工具场景可能使用 `.com`/Anthropic 专用入口，以控制台为准。 |
| 小米 MiMo | 官方文档 / 控制台 | 当前按 OpenAI-compatible 方式接入，Base URL、模型名与权限以 MiMo 官方文档/控制台为准；`mimo` 渠道在仓库默认 workflow 中未显式映射，Actions 使用请按本文“GitHub Actions 配置”补齐自定义映射。 |
| 火山方舟 / 豆包 | [在线推理（常规）](https://www.volcengine.com/docs/82379/2121998)、[模型列表](https://www.volcengine.com/docs/82379/1949118) | 官方示例使用 `https://ark.cn-beijing.volces.com/api/v3` 与 `doubao-seed-1-6-251015`；如使用 Coding Plan，请改用其专用 Base URL 和模型名，不要套用本表的在线推理模板。 |
| SiliconFlow | [模型列表](https://docs.siliconflow.cn/quickstart/models)、[获取模型列表 API](https://docs.siliconflow.cn/cn/api-reference/models/get-model-list) | 平台模型实时更新且 `/models` 需要 API Key；模板只给常见新模型示例，保存前建议在 Web 设置页点击「获取模型」确认账号可见性。 |
| OpenRouter | [Models API](https://openrouter.ai/docs/api/api-reference/models/get-models) | OpenRouter 支持 `~anthropic/claude-sonnet-latest`、`~openai/gpt-latest` 等 latest router alias；2026-05-03 的一次手动 live smoke 以 Claude Sonnet latest 作为默认示例通过，GPT latest 保留为可按账号权限切换的备选。 |
| LiteLLM | [OpenAI-Compatible Endpoints](https://docs.litellm.ai/docs/providers/openai_compatible) | OpenAI-compatible 端点需要把运行时模型写成 `openai/<model>`，Base URL 只填到服务商兼容入口，不额外拼接 `/chat/completions`。 |

本页预设只保证配置形状与当前依赖的 OpenAI-compatible 路由规则一致；实际连通性仍取决于服务商账号权限、地域、额度和模型开通状态。当前 LiteLLM 版本约束为 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`（见 `requirements.txt`），保留历史最低版本、显式排除 PyPI 事故版本，并避免未来大版本自动进入。

## OpenAI-compatible 与 LiteLLM 规则

- OpenAI-compatible provider 的 channel `protocol` 通常是 `openai`。
- 运行时模型名通常写成 `openai/<model>`；例如自定义网关里的 `gpt-5.5` 可以作为 `openai/gpt-5.5` 被 LiteLLM 路由。
- `Qwen/...`、`deepseek-ai/...` 这类是服务商或模型仓库组织名前缀，不等同于 LiteLLM provider prefix；不要因为它们包含斜杠就误判为 `provider/model` 路由。
- Base URL 只填官方或网关给出的兼容入口，通常到 `/v1`、`/api/v3` 或厂商文档指定路径；不要手动追加 `/chat/completions`。
- 如果使用 YAML 模式，按 LiteLLM `model_list` / `litellm_params` 的原生语义配置；YAML 有效时优先级高于 Channels。

## GitHub Actions 配置

仓库自带 `.github/workflows/00-daily-analysis.yml` 只会透传 workflow 中显式列出的环境变量。使用渠道模式时，先在 Repository Variables 或 Secrets 中设置 `LLM_CHANNELS`，再按渠道名补齐对应 `LLM_<CHANNEL>_*`。

| 字段 | 建议位置 | 说明 |
| --- | --- | --- |
| `LLM_CHANNELS` | Variables 或 Secrets | 逗号分隔渠道名，例如 `deepseek,minimax,volcengine`。 |
| `LLM_<CHANNEL>_PROVIDER` | Variables 或 Secrets | Provider Catalog ID；与可重命名的连接名分离，新配置应显式填写。 |
| `LLM_<CHANNEL>_PROTOCOL` | Variables 或 Secrets | 非敏感，通常为 `openai`、`deepseek`、`gemini`、`anthropic` 或 `ollama`。 |
| `LLM_<CHANNEL>_BASE_URL` | Variables 或 Secrets | 非敏感时优先放 Variables；私有网关地址可放 Secrets。 |
| `LLM_<CHANNEL>_MODELS` | Variables 或 Secrets | 非敏感模型列表，逗号分隔。 |
| `LLM_<CHANNEL>_ENABLED` | Variables 或 Secrets | 可选，未配置时默认启用；设为 `false` 可跳过该渠道。 |
| `LLM_<CHANNEL>_API_KEY` / `LLM_<CHANNEL>_API_KEYS` | Secrets | 密钥字段必须放 Repository Secrets；同名 Variables 不会被 workflow 读取。 |
| `LLM_<CHANNEL>_EXTRA_HEADERS` | Secrets 或 Variables | JSON 字符串；只要包含鉴权、租户、组织或私有网关信息，就应放 Secrets。 |
| `LITELLM_CONFIG` | Variables 或 Secrets | YAML 文件路径；配合 `LITELLM_CONFIG_YAML` 使用时，workflow 会写入该路径。 |
| `LITELLM_CONFIG_YAML` | Secrets 优先 | YAML 内容本身可能包含私有网关或 header，建议放 Secrets。 |
| `LLM_USAGE_HMAC_SECRET` | Secrets | 可选；只有需要跨部署比较 usage message HMAC 时才配置同一个高熵随机密钥，例如 `openssl rand -hex 32`；不要放 Variables 或提交到版本控制。 |
| `LLM_USAGE_HMAC_KEY_VERSION` | Variables 或 Secrets | 可选；轮换 `LLM_USAGE_HMAC_SECRET` 时同步更新版本标签，避免误比较不同密钥生成的 HMAC。 |

默认 workflow 已显式映射 `primary`、`secondary`、`aihubmix`、`anspire`、`deepseek`、`dashscope`、`zhipu`、`moonshot`、`minimax`、`volcengine`、`siliconflow`、`openrouter`、`gemini`、`anthropic`、`openai`、`ollama`、`hermes`；`mimo` 未在默认 workflow 中映射。若使用 `mimo`（或任何未列渠道名），除了在 Variables/Secrets 配置同名 `LLM_<CHANNEL>_*` 外，还需在 workflow 中同步补齐对应 env 映射；本地 `.env`、Docker 和自托管脚本不受这个限制。

回滚 HMAC 遥测显式配置时，可移除 `LLM_USAGE_HMAC_SECRET` 并恢复或删除 `LLM_USAGE_HMAC_KEY_VERSION`；留空后系统会回到本地生成 `.llm_usage_hmac_secret` 的默认行为。

Ollama 默认 Base URL `http://127.0.0.1:11434` 主要面向本地、Docker 或能访问该服务的 self-hosted runner。GitHub-hosted runner 通常没有本地 Ollama 服务，直接配置 `LLM_CHANNELS=ollama` 大概率会连接失败。

### Hermes 本地 HTTP generation（Phase 3）

Hermes 是 reserved 本地 HTTP generation preset，只通过 `LLM_CHANNELS=hermes` 启用。默认协议为 `openai`，默认地址为 `http://127.0.0.1:8642/v1`，默认模型为 `hermes-agent`：

```env
LLM_CHANNELS=hermes
LLM_HERMES_PROVIDER=custom
LLM_HERMES_PROTOCOL=openai
LLM_HERMES_BASE_URL=http://127.0.0.1:8642/v1
LLM_HERMES_API_KEY=sk-local-hermes
LLM_HERMES_MODELS=hermes-agent
LITELLM_MODEL=openai/hermes-agent
```

Phase 3 只支持普通分析 / JSON generation，不支持 stream/SSE、tools、Vision、Agent tools、remote Hermes 或进程生命周期管理。`LLM_HERMES_API_KEY` 应来自本地 `.env`、运行时配置或 GitHub Secrets；不要写入仓库。Hermes 只允许 loopback `/v1` endpoint，`localhost` 会按 `127.0.0.1` 规范化，`LLM_HERMES_API_KEYS` 与 `LLM_HERMES_EXTRA_HEADERS` 不受支持。Web 设置页保存 reserved Hermes 渠道时会清空这两个旧字段并显示 warning；恢复旧值请使用 `.env` 备份、Git 历史或桌面端导出备份，但非空多 Key / Extra Headers 仍会被后端拒绝。

在 GitHub Actions 中，GitHub-hosted runner 的 `127.0.0.1` 是 runner 自身，不是用户电脑。只有 self-hosted runner 或同机服务能访问本地 Hermes；否则会连接失败。

## 常见错误与处理建议

| `details.reason` / 现象 | 常见原因 | 建议处理 |
| --- | --- | --- |
| `missing_api_key` | API Key 为空，或 `API_KEYS` 逗号分隔后没有任何非空片段。 | 填入至少一个有效 key；本地 Ollama 或 localhost 兼容服务除外。 |
| `api_key_rejected` | 服务商返回 401 / 403，key 无效、权限不足或项目未开通。 | 重新复制 key，检查账号项目、组织、区域和模型权限。 |
| `insufficient_balance` | 余额不足、账单未开通或套餐额度耗尽。 | 到服务商控制台确认余额、账单状态和模型套餐。 |
| `quota_exceeded` | 账号或组织配额耗尽。 | 检查套餐、项目额度、组织额度和服务商账单页。 |
| `rate_limit` | RPM / TPM / 并发限制触发。 | 降低并发，换轻量模型，或在控制台提升限额。 |
| `timeout` | 请求超时，可能是网络慢、服务商响应慢或本地服务无响应。 | 检查代理、防火墙、Base URL、模型冷启动和 timeout 设置。 |
| `dns_error` | 域名无法解析。 | 检查 Base URL 拼写、DNS、代理和运行环境网络。 |
| `tls_error` | TLS 证书、代理或中间人证书异常。 | 检查 HTTPS 证书链、公司代理、自签证书和系统时间。 |
| `connection_refused` | 目标端口无服务，或本地服务未启动。 | 检查 Base URL、端口、防火墙；Ollama 确认本机或 runner 能访问服务。 |
| `endpoint_not_found` | `/models` 或 chat endpoint 路径不存在。 | 确认 Base URL 是否填到兼容入口，不要多拼或少拼厂商要求的路径。 |
| `invalid_url` | base_url 包含不受支持形态（空白/控制字符、反斜杠、`userinfo@host` 等）或解析语义不安全。 | 清理 `LLM_<CHANNEL>_BASE_URL`（建议先置空/删除该变量），保持 provider 默认入口；如需固定网关请先按官方兼容示例填写。 |
| `model_access_denied` | 基于已观测 provider 文案的 best-effort 模型可用性归类：模型可能被禁用、未开通、账号不可见或当前 key 无权限访问。 | 先查看测试结果里的“本次测试模型”，在服务商控制台确认该模型已开通；必要时调整模型顺序、移除不可用模型，或点击「获取模型」核对账号可见模型。 |
| `provider_blocked` | 服务商或中转网关明确拦截了本次请求，可能来自账号风控、地域、请求来源、模型权限、代理商策略或内容安全策略。 | 先查看测试结果里的“本次测试模型”和服务商控制台日志；检查账号/项目状态、地域或来源限制、网关策略和内容安全规则，而不是优先排查 Base URL、TLS 或本地网络。 |
| `provider_prefix_mismatch` | LiteLLM provider prefix 与渠道协议不匹配。 | OpenAI-compatible 渠道通常使用 `openai/<model>`；不要把 `Qwen/...`、`deepseek-ai/...` 误当 provider prefix。 |
| `non_json` | 服务商返回非 JSON 或代理返回 HTML / 文本错误页。 | 检查 Base URL、网关路径、代理错误页和 Chat Completions 兼容入口。 |
| `null_response` | LiteLLM 没有返回可解析响应对象。 | 检查 provider 是否兼容 Chat Completions，必要时换模型或 endpoint 重试。 |
| `null_content` | Chat completion 返回成功但 `content` 为空。 | 换用兼容文本输出的模型，或检查是否强制 tool / vision 响应。 |
| `malformed_choices` | 响应缺少兼容的 `choices` 结构。 | 确认 endpoint 是 Chat Completions 兼容接口，不是 Embeddings、Responses 或其它协议入口。 |
| `capability_unsupported` | JSON / tools / stream / vision smoke 参数不被当前模型或 endpoint 支持。 | 换支持该能力的模型，或把结果视为当前账号、模型和 endpoint 的一次能力诊断，不代表 provider 全局不支持。 |
| `unknown_error` | 服务商或客户端抛出未能细分的异常。 | 先查看 `details.message` / 日志中的原始错误，再按网络、鉴权、模型名和额度逐项排查。 |

完整分类逻辑以 `src/services/system_config_service.py` 中的错误分类实现为准。

`model_access_denied` 不是跨 provider 的官方错误码映射。该分类的可复核依据包括：

- SiliconFlow 官方错误处理文档要求接口错误排查时记录 HTTP 错误码和 `message`，说明 403 表示余额不足或权限不够，其他情况参考报错 `message`，并建议换一个模型确认问题是否仍存在（中文：<https://docs.siliconflow.cn/cn/faqs/error-code>；英文：<https://docs.siliconflow.cn/en/faqs/error-code>）。
- Issue #1208 中真实脱敏样例来自 SiliconFlow / OpenAI Compatible 渠道测试，经 LiteLLM 返回 `litellm.APIError: APIError: OpenAIException - Model disabled.`。
- 线上复核记录（2026-05-06T16:21:21Z）：在 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0` 约束下，本地验证环境为 Python `3.13.12`、LiteLLM `1.82.3`、Base URL `https://api.siliconflow.cn/v1`、模型 `Qwen/Qwen3-235B-A22B-Thinking-2507`。直连 SiliconFlow Chat Completions 返回 HTTP `403`，响应体为 `{"code":30003,"message":"Model disabled.","data":null}`；同一模型通过 LiteLLM `completion(model="openai/Qwen/Qwen3-235B-A22B-Thinking-2507")` 返回 `APIError: OpenAIException - Model disabled.`。

因此当前运行时把该已观测 provider `message` 作为 best-effort 模型可用性诊断，而不是把它声明为官方跨 provider 错误码。实现仅在错误文本同时包含 `model` 和明确权限、禁用或不可用信号时进入该诊断；未覆盖或语义不同的 provider 文案会继续走既有兜底诊断。`provider_blocked` 同样是基于明确拦截文案的 best-effort 诊断，用于区分服务商/网关策略拦截与本地网络、TLS 或模型不可用问题。

## 运行时能力检测边界

- JSON / tools / stream / vision smoke 必须在 Web 中显式触发。
- 检测会产生真实 LLM 请求，可能带来 token / 图像输入费用、RPM/TPM 限流、余额不足或超时。
- 检测结果只代表当前账号、模型和 endpoint 的一次 best-effort 运行时结果。
- 检测结果不会写回 `.env`，也不会阻止保存配置。
- 能力检测失败不等于 provider 全局不支持；失败可能来自账号权限、模型未开通、endpoint 区域、余额、服务商兼容层或 LiteLLM 转换路径。
- 当前实现未对所有真实 provider 做在线 smoke，兼容依据是 `litellm>=1.80.10,!=1.82.7,!=1.82.8,<2.0.0`（见 `requirements.txt`）、[LiteLLM Python SDK / OpenAI I/O format](https://docs.litellm.ai/)、[LiteLLM OpenAI-compatible 路由](https://docs.litellm.ai/docs/providers/openai_compatible)，以及 OpenAI Chat Completions 的 [JSON mode](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat)、[tool calling](https://platform.openai.com/docs/guides/function-calling?api-mode=chat)、[streaming](https://platform.openai.com/docs/guides/streaming-responses?api-mode=chat) 和 [vision input](https://platform.openai.com/docs/guides/images-vision?api-mode=chat) 请求形状。

## 回滚方式

- Web 设置页：删除或禁用对应 channel，重新选择旧的主模型 / Agent 模型 / fallback。
- `.env`：恢复备份中的 `LLM_*`、`LITELLM_MODEL`、`AGENT_LITELLM_MODEL`、`VISION_MODEL`、`LITELLM_FALLBACK_MODELS`。
- 从 Channels 回到 legacy：删除或清空 `LLM_CHANNELS`，保留 legacy provider key 和 `LITELLM_MODEL`。
- 从 YAML 回到 Channels / legacy：移除 `LITELLM_CONFIG` / `LITELLM_CONFIG_YAML`，重启后下层配置重新生效。
- WebUI / 桌面端：使用系统设置中导出的配置备份恢复。
- PR 回滚：revert 对应 docs PR；P4 不涉及配置、数据或代码迁移。
