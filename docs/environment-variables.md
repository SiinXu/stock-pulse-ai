# 环境变量清单与配置事实源

本文是 StockPulse **配置键清单** 与 **配置项新增流程** 的文档入口。它与以下两处共同构成配置真相：

| 事实源 | 路径 | 职责 |
|--------|------|------|
| 模板默认值 | [`.env.example`](../.env.example) | 键名、示例/默认值、敏感占位符、注释中的行为说明 |
| 配置注册表 | [`src/core/config_registry_parts/`](../src/core/config_registry_parts/) | Web 设置页分组、控件类型、校验、help 元数据、默认值提示 |
| 本文档清单 | 下方机器校验表格 | 键是否已被文档收录；与模板默认值对齐 |

面向场景的说明仍以专题文档与 [完整配置与部署指南](full-guide.md) 的精选表为准；**完整键集合**以 `.env.example` 与本清单为准。

设置页帮助文案的维护规则见 [settings-help.md](settings-help.md)。

## 为什么需要三方对齐

配置键如果只改其中一方，会出现：

- 用户按文档配置但键不存在，或默认值与模板不一致；
- 键已写入 `.env.example` 但未登记注册表 → Web 设置页落入「其他 / uncategorized」、控件类型错误，或对从未保存过的键完全不可见；
- 键已在注册表或代码中生效，但模板与文档未收录 → 自托管用户无法发现。

仓库提供本地/CI 可运行的一致性检查：

```bash
python scripts/check_config_doc_consistency.py
python scripts/check_config_doc_consistency.py --json
python scripts/check_config_doc_consistency.py --write-inventory
python scripts/check_config_doc_consistency.py --self-test
```

检查输出三类主清单（以及中英清单不一致、默认值不一致）：

1. **文档缺失**（`missing_from_docs`）：在 `.env.example` 中存在，但中/英清单缺一或双缺；
2. **`.env.example` 缺失**（`missing_from_env`）：在清单或注册表中存在，但模板没有 `KEY=`（含注释行）；
3. **注册表缺失**（`missing_from_registry`）：在 `.env.example` 中存在，但未在配置注册表显式登记。

默认失败类为 `docs,env,cn_en,defaults`：**注册表缺口默认只报告、不使检查失败**，由注册表分区任务与 Task 1 守卫收敛。需要把注册表也变成硬门禁时：

```bash
python scripts/check_config_doc_consistency.py --fail-on all
```

## 配置项新增流程（必读）

新增或修改用户可见 / 运行时可配环境变量时，**必须在同一变更中**完成下列步骤（缺一不可）：

1. **`.env.example`**
   - 增加或更新 `KEY=value`（可选能力可保持注释行 `# KEY=value`）；
   - 写清默认值或安全占位符；
   - 在键上方或行尾注释说明用途、取值范围与相关专题文档链接。

2. **配置注册表**（`src/core/config_registry_parts/` 对应分区）
   - 为 Web 可编辑或需要元数据的键补充 `title` / `description` / `category` / `data_type` / `ui_control` / `default_value` / `options` / `validation` / `help_key` 等；
   - 布尔键使用开关控件，枚举键使用 select + `options`，避免落入 uncategorized 文本框；
   - 同步设置页 i18n 标题与 help（见 [settings-help.md](settings-help.md)）；
   - **Task 1 守卫**：注册表与模板/呈现契约的自动化拦截由 Task 1 交付（仓库内既有局部契约见 `tests/test_config_registry.py::TestEnvExampleWebSettingsCoverage`；完整「未登记键」守卫合并后以该任务脚本/CI 步骤为准）。本仓库的三方文档检查脚本负责文档侧清单，**不**代替注册表登记。

3. **文档**
   - 运行 `python scripts/check_config_doc_consistency.py --write-inventory` 刷新下方中英清单表；
   - 若键影响用户路径，更新 [full-guide.md](full-guide.md) / [full-guide_EN.md](full-guide_EN.md) 精选表或对应专题文档（中英文同步评估）；
   - 用户可见能力变更时更新 `docs/CHANGELOG.md` 的 `[Unreleased]` 扁平条目。

4. **验证**
   - `python scripts/check_config_doc_consistency.py`（文档/模板/中英/默认值）；
   - 涉及注册表时再跑相关 `tests/test_config_registry.py` 与设置页契约测试；
   - 不要在未登记注册表的情况下声称「设置页已支持」。

### 废弃配置

- 从 `.env.example` 删除或标注废弃前，确认代码读取路径与迁移/兼容策略；
- 从本清单与 full-guide 精选表删除对应行，避免文档继续推荐死键；
- 注册表删除或隐藏由注册表任务处理，并保持 Web 标题/help 不残留幽灵键。

## 相关文档

- [完整配置与部署指南](full-guide.md#环境变量完整列表)（精选说明与部署上下文）
- [LLM 配置指南](LLM_CONFIG_GUIDE.md)
- [settings-help.md](settings-help.md)
- [config-access-ratchet.md](config-access-ratchet.md)（代码访问 `get_config()` 棘轮，不同于本清单）
- English: [environment-variables_EN.md](environment-variables_EN.md)

## 完整键清单（机器校验）

下表由 `scripts/check_config_doc_consistency.py --write-inventory` 根据 `.env.example` 与当前注册表生成。

- **默认值**列对齐 `.env.example` 赋值（空值记为 `空`）。
- **已注册**列表示是否出现在 `get_registered_field_keys()`；`否` 表示注册表缺口（见 [#1026](https://github.com/SiinXu/stock-pulse-ai/issues/1026)，勿在文档 PR 中顺手改注册表）。
- 长说明、枚举取值与排障以 `.env.example` 注释及专题文档为准。

<!-- config-env-inventory:start -->

| 键名 | 默认值（``.env.example``） | 已注册 | 备注 |
|------|---------------------------|--------|------|
| `ADMIN_AUTH_ENABLED` | `false` | 是 | =================================== Web login authentication (optional) =================================== Set to tr... |
| `ADMIN_SESSION_MAX_AGE_HOURS` | `24` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `AGENT_ARCH` | `single` | 是 | 模板中注释; Agent architecture mode (default single; multi is multi-agent orchestration mode) |
| `AGENT_CONTEXT_COMPRESSION_ENABLED` | `false` | 是 | 模板中注释; AskStock visible conversation context compression (disabled by default) |
| `AGENT_CONTEXT_COMPRESSION_PROFILE` | `balanced` | 是 | 模板中注释; Compression strategy: cost=save tokens / balanced=balance both goals / long_context_raw_first=preserve more original ... |
| `AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS` | `空` | 是 | 模板中注释; Historical token threshold that triggers compression; leave empty to use the current profile preset |
| `AGENT_CONTEXT_PROTECTED_TURNS` | `空` | 是 | 模板中注释; Preserve the most recent N user turns and the replies that follow them verbatim during compression; leave empty to us... |
| `AGENT_CRITIC_ENABLED` | `false` | 是 | 模板中注释; Optional bounded Critic for Native Multi analysis (default false) |
| `AGENT_DECISION_AGENT_TIMEOUT_S` | `0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `AGENT_DEEP_RESEARCH_BUDGET` | `30000` | 是 | 模板中注释; Deep-research tool token budget and timeout (seconds) for Agent analysis paths that enable deep research. |
| `AGENT_DEEP_RESEARCH_TIMEOUT` | `180` | 是 | 模板中注释 |
| `AGENT_EVENT_ALERT_RULES_JSON` | `[{"stock_code":"600519","alert_type":"price_cross","direction":"above","price":1800},{"stock_code":"300750","alert_type":"price_change_percent","direction":"down","change_pct":3.0},{"stock_code":"000858","alert_type":"volume_spike","multiplier":2.5}]` | 是 | 模板中注释 |
| `AGENT_EVENT_IMPACT_CONTEXT_ENABLED` | `true` | 是 | 模板中注释; Attach holdings/watchlist impact context to triggered alert notifications (managed data only; default true). |
| `AGENT_EVENT_MONITOR_ENABLED` | `false` | 是 | 模板中注释 |
| `AGENT_EVENT_MONITOR_INTERVAL_MINUTES` | `5` | 是 | 模板中注释 |
| `AGENT_FEATURES_ACKNOWLEDGED_OFF` | `false` | 是 | 模板中注释; When true, settles the Agent readiness check for CLI-only users who do not need Q&A Agent |
| `AGENT_GENERATION_BACKEND` | `auto` | 是 | Agent Chat backend; Web settings page only exposes auto/litellm, hand-written local CLI backend will return unsupport... |
| `AGENT_INTEL_AGENT_TIMEOUT_S` | `0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `AGENT_INVESTMENT_COMMITTEE_MODE` | `false` | 是 | 模板中注释; Investment Committee mode (default off) |
| `AGENT_LITELLM_MODEL` | `空` | 是 | 模板中注释; Agent main model (optional): Empty when inheriting from the main model; without provider prefix will parse as openai/... |
| `AGENT_MAX_IDENTICAL_TOOL_CALLS` | `3` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `AGENT_MAX_STAGE_ENTRIES` | `1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `AGENT_MAX_STEPS` | `10` | 是 | 模板中注释; Agent maximum inference step limit (default 10, each sub-agent runs according to its preset value; higher than the de... |
| `AGENT_MEMORY_ENABLED` | `false` | 是 | 模板中注释; Memory and calibration system (tracks historical accuracy and automatically adjusts confidence) |
| `AGENT_MODE` | `true` | 是 | 模板中注释; =================================== Agent strategy dialogue configuration (Web dialogue page) =======================... |
| `AGENT_MULTI_STRATEGY_DELIBERATION` | `false` | 是 | 模板中注释; Multi-strategy deliberation cluster (default off) |
| `AGENT_NL_ROUTING` | `false` | 是 | 模板中注释; Route high-confidence stock-related bot messages to the Agent without an explicit command (default false). |
| `AGENT_OBSERVABILITY_DEEP_PAYLOAD` | `false` | 是 | 模板中注释 |
| `AGENT_OBSERVABILITY_ENABLED` | `true` | 是 | 模板中注释; Agent observability L0 (structured run events with trace/span ids) Lightweight events are default-on and persist via ... |
| `AGENT_ORCHESTRATOR_MODE` | `standard` | 是 | 模板中注释; Multi-agent orchestration mode (applies only when AGENT_ARCH=multi) quick: technical analysis -> decision (fastest, a... |
| `AGENT_ORCHESTRATOR_TIMEOUT_S` | `600` | 是 | 模板中注释; Agent execution timeout budget in seconds (0 disables it; single-agent uses it for the full loop, multi-agent for col... |
| `AGENT_PORTFOLIO_AGENT_TIMEOUT_S` | `0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `AGENT_RISK_AGENT_TIMEOUT_S` | `0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `AGENT_RISK_OVERRIDE` | `true` | 是 | 模板中注释; Whether the risk-control agent may reject buy signals (enabled by default) |
| `AGENT_SKILLS` | `空` | 是 |  |
| `AGENT_SKILL_AGENT_TIMEOUT_S` | `0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `AGENT_SKILL_AUTOWEIGHT` | `true` | 是 | 模板中注释; Automatically weight strategy opinions based on backtesting performance. |
| `AGENT_SKILL_DIR` | `./strategies` | 是 | 模板中注释; Custom strategy directory (optional, place custom YAML strategy files; environment variable name follows internal ski... |
| `AGENT_SKILL_ROUTING` | `auto` | 是 | 模板中注释; Strategy routing mode (auto=select from market state / manual=use the AGENT_SKILLS list) |
| `AGENT_STAGE_FAILURE_POLICY` | `isolate` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `AGENT_TECHNICAL_AGENT_TIMEOUT_S` | `0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `AGENT_TOOL_TIMEOUT_S` | `120` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `AIHUBMIX_KEY` | `空` | 是 | 模板中注释; AIHubmix Aggregation(https://aihubmix.com/) A Key using GPT/Claude/Gemini/GLM/Qwen models, without requiring VPN access |
| `AKSHARE_PRIORITY` | `1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ALLOW_INSECURE_PUBLIC_BIND` | `false` | 否 | 注册表缺口（见 issue #1026） |
| `ALPHASIFT_DAILY_CALL_TIMEOUT_SEC` | `20` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ALPHASIFT_DAILY_HISTORY_CACHE_DIR` | `data/alphasift/daily_history` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ALPHASIFT_DATA_DIR` | `data/alphasift` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ALPHASIFT_EASTMONEY_JITTER_SEC` | `0.3` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ALPHASIFT_EASTMONEY_MIN_INTERVAL_SEC` | `1.0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ALPHASIFT_ENABLED` | `false` | 是 | AlphaSift stock selection integration (default closed; typically maintained by the Web "Enable Stock Selection" button) |
| `ALPHASIFT_FALLBACK_SNAPSHOT_PATH` | `data/alphasift/snapshot.last_good.json` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ALPHASIFT_INDUSTRY_PROVIDER_CACHE_DIR` | `data/alphasift/industry_provider_cache` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ALPHASIFT_INSTALL_SPEC` | `git+https://github.com/ZhuLinsen/alphasift.git@9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf` | 是 | Switch instructions: - ALPHASIFT_ENABLED Only affects AlphaSift Stock selection process, Do not rewrite/Migrate/Clean... |
| `ALPHASIFT_SNAPSHOT_CALL_TIMEOUT_SEC` | `60` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ALPHASIFT_SOURCE_CALL_TIMEOUT_SEC` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ALPHAVANTAGE_API_KEY` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ANALYSIS_DELAY` | `0` | 是 | 模板中注释; =================================== Analyze interval configuration (optional) =================================== Del... |
| `ANSPIRE_API_KEYS` | `空` | 是 | Anspire Open API keys (supports multiple comma-separated values) Get keys from: https://open.anspire.cn/ When no high... |
| `ANSPIRE_LLM_BASE_URL` | `https://open-gateway.anspire.cn/v6` | 是 | 模板中注释 |
| `ANSPIRE_LLM_ENABLED` | `true` | 是 | 模板中注释 |
| `ANSPIRE_LLM_MODEL` | `Doubao-Seed-2.0-lite` | 是 | 模板中注释 |
| `ANTHROPIC_API_KEY` | `空` | 是 | 模板中注释; Anthropic Claude（https://console.anthropic.com） |
| `ANTHROPIC_API_KEYS` | `key1,key2,key3` | 是 | 模板中注释; Multi-key load balancing (comma-separated); takes priority over ANTHROPIC_API_KEY when set. |
| `ANTHROPIC_MAX_TOKENS` | `8192` | 是 | 模板中注释; Legacy Claude max response tokens. |
| `ANTHROPIC_MODEL` | `空` | 是 | 模板中注释; Legacy Claude model name (prefer LITELLM_MODEL / LLM Channels for new setups). |
| `ANTHROPIC_TEMPERATURE` | `0.7` | 是 | 模板中注释; Legacy Claude sampling temperature (0.0-1.0); prefer LLM_TEMPERATURE for new setups. |
| `ASTRBOT_TOKEN` | `空` | 是 | 模板中注释; Optional for AstrBot Webhook requiring Bearer Token |
| `ASTRBOT_URL` | `空` | 是 | 模板中注释; AstrBot Configuration |
| `BACKTEST_ENABLED` | `true` | 是 | =================================== Backtesting configuration (optional) =================================== Enable b... |
| `BACKTEST_ENGINE_VERSION` | `v1` | 是 | Backtesting engine version (used to differentiate results when backtesting logic is upgraded). |
| `BACKTEST_EVAL_WINDOW_DAYS` | `10` | 是 | Backtesting evaluation window (trading days) |
| `BACKTEST_MIN_AGE_DAYS` | `14` | 是 | Only retrieve historical analysis records of N days ago (to avoid incomplete data for that day/recently) |
| `BACKTEST_NEUTRAL_BAND_PCT` | `2.0` | 是 | Neutral-band threshold (%); for example, 2 treats -2% through +2% as neutral/sideways. |
| `BAOSTOCK_PRIORITY` | `3` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `BIAS_THRESHOLD` | `5.0` | 是 | 模板中注释; Bias-ratio threshold (%); when deviation from MA5 exceeds this value, strong-trend stocks use a 1.5x threshold before... |
| `BOCHA_API_KEYS` | `your_bocha_key_here` | 是 | 模板中注释; =================================== Search engine configuration (for fetching stock news) |
| `BRAVE_API_KEYS` | `空` | 是 | Brave Search API Keys(Supports multiple, Comma-separated) Get: https://brave.com/search/api/ |
| `COINGECKO_API_BASE` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `COINGECKO_API_KEY` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `COINGECKO_API_PLAN` | `keyless` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `CRYPTO_COINGECKO_PRIORITY` | `10` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `CRYPTO_PROVIDER_ENABLED` | `false` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | `空` | 是 | 模板中注释; Optional: For Webhooks requiring authentication (Header Authorization: Bearer <token>) |
| `CUSTOM_WEBHOOK_BODY_TEMPLATE` | `空` | 是 | 模板中注释; Optional global JSON body template, overrides Bark/Slack/Discord etc |
| `CUSTOM_WEBHOOK_URLS` | `https://oapi.dingtalk.com/robot/send?access_token=xxx,https://hooks.slack.com/services/xxx` | 是 | 模板中注释; Custom Webhook (Supports multiple, comma-separated) Suitable for: DingTalk, Discord, Slack, Bark, and any service tha... |
| `DAILY_BRIEF_ENABLED` | `false` | 是 | 模板中注释; Daily brief with historical accuracy review (Issue #466; default off) When enabled, the runtime scheduler may emit at... |
| `DAILY_BRIEF_MIN_SAMPLES` | `10` | 是 | 模板中注释 |
| `DAILY_BRIEF_NOTIFY` | `true` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DAILY_BRIEF_PERSIST_HISTORY` | `true` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DAILY_BRIEF_SAVE_REPORT_FILE` | `true` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DAILY_BRIEF_SCHEDULE_TIME` | `08:30` | 是 | 模板中注释 |
| `DAILY_BRIEF_TIMEZONE` | `Asia/Shanghai` | 是 | 模板中注释 |
| `DAILY_MARKET_CONTEXT_ENABLED` | `true` | 是 | Should the market summary be injected into individual stock analysis prompts and should conservative barriers be enab... |
| `DATABASE_PATH` | `./data/stock_analysis.db` | 否 | 注册表缺口（见 issue #1026） |
| `DATA_VALIDATION_ENABLED` | `true` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DATA_VALIDATION_INSTRUMENT_OVERRIDES` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DATA_VALIDATION_STRICT` | `false` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DATA_VALIDATION_STRICT_SCOPES` | `*/*` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DATA_VALIDATION_UPPER_LAYER_MODE` | `warn` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DEBUG` | `false` | 是 | Enable debugging logs |
| `DECISION_MEMORY_ENABLED` | `true` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DECISION_MEMORY_LOOKBACK` | `5` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DECISION_MEMORY_MIN_AGE_DAYS` | `3` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DECISION_MEMORY_MIN_SAMPLES` | `5` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DECISION_PROFILE_CALIBRATION_ENABLED` | `false` | 是 | 模板中注释 |
| `DEEPSEEK_API_KEY` | `空` | 是 | 模板中注释; DeepSeek（https://platform.deepseek.com） Compatibility default: Only fill in DEEPSEEK_API_KEY, still using deepseek-ch... |
| `DEEPSEEK_API_KEYS` | `key1,key2,key3` | 是 | 模板中注释; Multi-key load balancing (comma-separated); takes priority over DEEPSEEK_API_KEY when set. |
| `DINGTALK_APP_KEY` | `xxxx` | 是 | Application AppKey (shared with Webhook mode) |
| `DINGTALK_APP_SECRET` | `xxxx` | 是 | AppSecret (shared with Webhook mode) |
| `DINGTALK_SECRET` | `空` | 是 | Signing secret for the DingTalk robot (a string starting with 'SEC'); leave empty when signing is disabled. |
| `DINGTALK_STREAM_ENABLED` | `false` | 是 | Enable Stream mode |
| `DINGTALK_WEBHOOK_URL` | `空` | 是 | ====== DingTalk Robot ====== Webhook URL for DingTalk group robots |
| `DISCORD_BOT_TOKEN` | `空` | 是 | 模板中注释; Method 2: Discord Bot API (requires Bot account and channel ID) 1 |
| `DISCORD_CHANNEL_ID` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DISCORD_INTERACTIONS_PUBLIC_KEY` | `空` | 是 | 模板中注释; If you need to receive Discord Interaction / Webhook callbacks, you must configure the public key for verification |
| `DISCORD_MAIN_CHANNEL_ID` | `空` | 是 | 模板中注释 |
| `DISCORD_MAX_WORDS` | `2000` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `DISCORD_WEBHOOK_URL` | `https://discord.com/api/webhooks/your_webhook_id/your_webhook_token` | 是 | 模板中注释; Discord Configuration Supports two methods: Webhook (recommended, simple configuration) and Bot API (high permissions) |
| `DSA_WEB_DEV_API_PROXY` | `http://127.0.0.1:8000` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `EFINANCE_CALL_TIMEOUT` | `30` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `EFINANCE_PRIORITY` | `99` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `EMAIL_GROUP_1` | `user1@example.com` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `EMAIL_GROUP_2` | `user2@example.com` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `EMAIL_PASSWORD` | `空` | 是 | 模板中注释 |
| `EMAIL_RECEIVERS` | `receiver@example.com` | 是 | 模板中注释; Optional: Leave empty to send to yourself |
| `EMAIL_SENDER` | `空` | 是 | 模板中注释; [Method Four]Email Push (requires only 2 configurations, SMTP auto-recognition) Supports QQ email, 163 email, Gmail, etc |
| `ENABLE_CHIP_DISTRIBUTION` | `true` | 是 | 模板中注释; Enable chip distribution analysis (the upstream API is unstable; disabling it is recommended for cloud deployments) |
| `ENABLE_EASTMONEY_PATCH` | `false` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ENABLE_FUNDAMENTAL_PIPELINE` | `true` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `ENABLE_REALTIME_QUOTE` | `true` | 是 | 模板中注释; Enable real-time quotes (disabling uses historical closing prices for analysis) |
| `ENABLE_REALTIME_TECHNICAL_INDICATORS` | `true` | 是 | 模板中注释; Intraday technical analysis: when enabled, real-time prices are used to calculate moving averages and bullish MA alig... |
| `FAILURE_NOTIFY_ENABLED` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `FEISHU_APP_ID` | `xxxx` | 是 | Feishu app configuration (for App Bot active push / Stream Bot / Cloud Docs; does not directly enable group Webhook p... |
| `FEISHU_APP_SECRET` | `xxxx` | 是 | App Bot push also requires FEISHU_CHAT_ID; prefer FEISHU_WEBHOOK_URL for simple group delivery. |
| `FEISHU_CHAT_ID` | `oc_xxxxxxxxxxxxx` | 是 | 模板中注释; App Bot proactively pushes targets; Stream Bot or Cloud Docs do not need this item |
| `FEISHU_DOMAIN` | `feishu` | 是 | 模板中注释; Use lark for the international Lark API and Stream endpoint |
| `FEISHU_MAX_BYTES` | `20000` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `FEISHU_RECEIVE_ID_TYPE` | `chat_id` | 是 | 模板中注释 |
| `FEISHU_SEND_AS_FILE` | `false` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `FEISHU_STREAM_ENABLED` | `false` | 是 | Enable long connection mode |
| `FEISHU_WEBHOOK_KEYWORD` | `股票日报` | 是 | 模板中注释 |
| `FEISHU_WEBHOOK_SECRET` | `your_feishu_webhook_secret` | 是 | 模板中注释; Feishu group robot Webhook security configuration (only used in Webhook push mode) |
| `FEISHU_WEBHOOK_URL` | `https://open.feishu.cn/open-apis/bot/v2/hook/your_key_here` | 是 | 模板中注释; Method Two: Feishu Robot (Choose one of two) Method 2a — Group Custom Robot Webhook In Feishu group -> Settings -> Gr... |
| `FINNHUB_API_KEY` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `FUNDAMENTAL_CACHE_MAX_ENTRIES` | `256` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `FUNDAMENTAL_CACHE_TTL_SECONDS` | `120` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `FUNDAMENTAL_FETCH_TIMEOUT_SECONDS` | `8.0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `FUNDAMENTAL_RETRY_MAX` | `1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS` | `8.0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `FUTU_ACC_ID` | `空` | 是 | Leave empty to merge eligible ACTIVE REAL NORMAL/MASTER securities accounts. |
| `FUTU_OPEND_HOST` | `127.0.0.1` | 是 | Optional Futu OpenD gateway for `python main.py --portfolio futu` (analysis scope) and POST /api/v1/portfolio/imports... |
| `FUTU_OPEND_PORT` | `11111` | 是 |  |
| `FUTU_SECURITY_FIRM` | `NONE` | 是 | NONE uses the Futu SDK's official security-firm auto-detection. |
| `GEMINI_API_KEY` | `空` | 是 | Gemini（https://aistudio.google.com） |
| `GEMINI_API_KEYS` | `key1,key2,key3` | 是 | 模板中注释; Multi-key load balancing (comma-separated); takes priority over GEMINI_API_KEY when set. |
| `GEMINI_MODEL` | `空` | 是 | 模板中注释; Legacy single-provider model name (prefer LITELLM_MODEL / LLM Channels for new setups). |
| `GEMINI_MODEL_FALLBACK` | `空` | 是 | 模板中注释; Legacy Gemini fallback model when the primary Gemini model fails. |
| `GEMINI_TEMPERATURE` | `0.7` | 是 | 模板中注释; Legacy Gemini sampling temperature (0.0-1.0); prefer LLM_TEMPERATURE for new setups. |
| `GENERATION_BACKEND` | `litellm` | 是 | Generate backend: defaults to litellm; codex_cli / claude_code_cli / opencode_cli are explicit local CLI backends (ex... |
| `GENERATION_BACKEND_MAX_CONCURRENCY` | `1` | 是 |  |
| `GENERATION_BACKEND_MAX_OUTPUT_BYTES` | `1048576` | 是 |  |
| `GENERATION_BACKEND_TIMEOUT_SECONDS` | `300` | 是 | Local CLI backend execution limit; timeout maximum 3600, output maximum 33554432 bytes, concurrent maximums are 16/4 ... |
| `GENERATION_FALLBACK_BACKEND` | `litellm` | 是 | Backend-level fallback; Local .env empty values disable backend-level fallback, litellm -> litellm will be parsed as ... |
| `GOTIFY_TOKEN` | `空` | 是 | 模板中注释; Gotify application token |
| `GOTIFY_URL` | `空` | 是 | 模板中注释; Gotify Configuration GOTIFY_URL is the Gotify server base URL, without /message; the system will append /message and ... |
| `HTTP_PROXY` | `http://127.0.0.1:10809` | 是 | 模板中注释; Standard HTTP(S) proxy URL for outbound requests (data sources, LLM, search, notifications) |
| `INDICATOR_MACD_FAST` | `12` | 是 | 模板中注释 |
| `INDICATOR_MACD_SIGNAL` | `9` | 是 | 模板中注释 |
| `INDICATOR_MACD_SLOW` | `26` | 是 | 模板中注释 |
| `INDICATOR_MA_PERIODS` | `5,10,20,60` | 是 | 模板中注释; Technical indicator periods for trend analysis (Issue #172) |
| `INDICATOR_RSI_PERIODS` | `6,12,24` | 是 | 模板中注释 |
| `INDUSTRY_PROVIDER` | `none` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `INDUSTRY_PROVIDER_MAX_BOARDS` | `80` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `KRONOS_ENABLED` | `false` | 是 | Optional local Kronos K-line forecasting Agent Tool |
| `KRONOS_MODEL_SIZE` | `mini` | 是 |  |
| `KRONOS_WEIGHTS_DIR` | `/absolute/path/to/kronos-weights` | 是 | 模板中注释 |
| `LITELLM_CONFIG` | `./litellm_config.yaml` | 是 | 模板中注释; Advanced: Model Routing YAML Configuration (optional, see docs/examples/litellm_config.example.yaml) |
| `LITELLM_FALLBACK_MODELS` | `空` | 是 | 模板中注释; First-run readiness: GET /api/v1/onboarding/first-run (read-only; never writes .env) |
| `LITELLM_LOG_LEVEL` | `WARNING` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LITELLM_MODEL` | `openai/~anthropic/claude-sonnet-latest` | 是 | 模板中注释 |
| `LLM_AIHUBMIX_API_KEY` | `sk-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_AIHUBMIX_BASE_URL` | `https://aihubmix.com/v1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_AIHUBMIX_MODELS` | `gpt-5.5,claude-sonnet-4-6,gemini-3.1-pro-preview` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_AIHUBMIX_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_AIHUBMIX_PROVIDER` | `aihubmix` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ANSPIRE_API_KEY` | `sk-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ANSPIRE_BASE_URL` | `https://open-gateway.anspire.cn/v6 (example)` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ANSPIRE_MODELS` | `Doubao-Seed-2.0-lite,Doubao-Seed-2.0-pro (example models)` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ANSPIRE_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ANSPIRE_PROVIDER` | `anspire` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ANTHROPIC_API_KEY` | `sk-ant-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ANTHROPIC_MODELS` | `claude-sonnet-4-6,claude-opus-4-7` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ANTHROPIC_PROTOCOL` | `anthropic` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ANTHROPIC_PROVIDER` | `anthropic` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_CHANNELS` | `openrouter` | 是 | 模板中注释; OpenRouter（OpenAI Compatible） Source: Official Models API https://openrouter.ai/docs/api/api-reference/models/get-models |
| `LLM_CONFIG_MODE` | `auto` | 是 | 模板中注释; --- Model Configuration Source Mode (Optional) --- auto(Default): Maintain historical priority YAML > Channels > Lega... |
| `LLM_DASHSCOPE_API_KEY` | `sk-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_DASHSCOPE_MODELS` | `qwen3.6-plus,qwen3.6-flash` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_DASHSCOPE_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_DASHSCOPE_PROVIDER` | `dashscope` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_DEEPSEEK_API_KEY` | `sk-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_DEEPSEEK_MODELS` | `deepseek-v4-flash,deepseek-v4-pro` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_DEEPSEEK_PROTOCOL` | `deepseek` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_DEEPSEEK_PROVIDER` | `deepseek` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_GEMINI_API_KEY` | `xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_GEMINI_API_KEYS` | `key1,key2` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_GEMINI_MODELS` | `gemini-3.1-pro-preview,gemini-3-flash-preview` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_GEMINI_PROTOCOL` | `gemini` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_GEMINI_PROVIDER` | `gemini` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_HERMES_API_KEY` | `sk-local-hermes` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_HERMES_BASE_URL` | `http://127.0.0.1:8642/v1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_HERMES_MODELS` | `hermes-agent` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_HERMES_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_HERMES_PROVIDER` | `custom` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MAX_TOKENS` | `2048` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MIMO_API_KEY` | `sk-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MIMO_BASE_URL` | `https://your-mimo-endpoint.example/v1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MIMO_MODELS` | `mimo-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MIMO_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MIMO_PROVIDER` | `custom` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MINIMAX_API_KEY` | `xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MINIMAX_BASE_URL` | `https://api.minimax.io/v1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MINIMAX_MODELS` | `MiniMax-M2.7,MiniMax-M2.7-highspeed` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MINIMAX_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MINIMAX_PROVIDER` | `minimax` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MOONSHOT_API_KEY` | `sk-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MOONSHOT_BASE_URL` | `https://api.moonshot.cn/v1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MOONSHOT_MODELS` | `kimi-k2.6,kimi-k2.5` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MOONSHOT_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MOONSHOT_PROVIDER` | `moonshot` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MY_PROXY_API_KEY` | `sk-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MY_PROXY_BASE_URL` | `https://your-proxy.example.com/v1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MY_PROXY_MODELS` | `gpt-5.5,claude-sonnet-4-6` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MY_PROXY_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_MY_PROXY_PROVIDER` | `custom` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OLLAMA_BASE_URL` | `http://localhost:11434` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OLLAMA_MODELS` | `qwen3:8b,qwen3:4b` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OLLAMA_PROVIDER` | `ollama` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OPENAI_API_KEY` | `sk-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OPENAI_BASE_URL` | `https://api.openai.com/v1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OPENAI_MODELS` | `gpt-5.5,gpt-5.4-mini` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OPENAI_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OPENAI_PROVIDER` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OPENROUTER_API_KEY` | `sk-or-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OPENROUTER_MODELS` | `~anthropic/claude-sonnet-latest,~openai/gpt-latest` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OPENROUTER_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_OPENROUTER_PROVIDER` | `openrouter` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL` | `off` | 是 | 模板中注释 |
| `LLM_PROMPT_CACHE_HINTS_ENABLED` | `false` | 是 | 模板中注释 |
| `LLM_PROMPT_CACHE_TELEMETRY_ENABLED` | `true` | 是 | 模板中注释; Provider prompt cache Configuration(Optional) TELEMETRY controls only the recording of provider cache usage and diagn... |
| `LLM_SILICONFLOW_API_KEY` | `sk-xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_SILICONFLOW_MODELS` | `deepseek-ai/DeepSeek-V3.2,Qwen/Qwen3-235B-A22B-Thinking-2507` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_SILICONFLOW_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_SILICONFLOW_PROVIDER` | `siliconflow` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_TEMPERATURE` | `0.7` | 是 | 模板中注释; Sampling temperature (0.0-2.0, default 0.7; 0 is most deterministic and 2 is most random) |
| `LLM_TIMEOUT_SEC` | `60` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_USAGE_HMAC_KEY_VERSION` | `local-v1` | 是 | 模板中注释 |
| `LLM_USAGE_HMAC_SECRET` | `空` | 是 | 模板中注释; LLM usage telemetry message HMAC configuration (optional) |
| `LLM_VOLCENGINE_API_KEY` | `xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_VOLCENGINE_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_VOLCENGINE_MODELS` | `doubao-seed-1-6-251015,doubao-seed-1-6-thinking-251015` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_VOLCENGINE_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_VOLCENGINE_PROVIDER` | `volcengine` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ZHIPU_API_KEY` | `xxx` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ZHIPU_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ZHIPU_MODELS` | `glm-5.1,glm-4.7-flash` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ZHIPU_PROTOCOL` | `openai` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LLM_ZHIPU_PROVIDER` | `zhipu` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LOCAL_CLI_BACKEND_MAX_CONCURRENCY` | `1` | 是 |  |
| `LOCAL_ONLY_MODE` | `false` | 是 | 模板中注释; Local Only / privacy mode (default off) |
| `LOCAL_RUNTIME_AUTO_DETECT` | `true` | 是 | 模板中注释; Zero-config first success: setup readiness probes loopback Ollama by default (never blocks startup; failures are log-... |
| `LOCAL_RUNTIME_DETECT_TIMEOUT_SECONDS` | `0.35` | 是 | 模板中注释 |
| `LOG_DIR` | `./logs` | 是 | System configuration Log directory |
| `LOG_LEVEL` | `INFO` | 是 | Log level (DEBUG/INFO/WARNING/ERROR) |
| `LONGBRIDGE_ACCESS_TOKEN` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_APP_KEY` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_APP_SECRET` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS` | `15` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_ENABLE_OVERNIGHT` | `false` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_HTTP_URL` | `https://openapi.longbridge.com` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_OAUTH_CLIENT_ID` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_OAUTH_TOKEN_CACHE_B64` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_PRINT_QUOTE_PACKAGES` | `false` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_PRIORITY` | `5` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_PUSH_CANDLESTICK_MODE` | `realtime` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_QUOTE_WS_URL` | `wss://openapi-quote.longbridge.com/v2` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_REGION` | `hk` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_STATIC_INFO_TTL_SECONDS` | `86400` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `LONGBRIDGE_TRADE_WS_URL` | `wss://openapi-trade.longbridge.com/v2` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MARKDOWN_TO_IMAGE_CHANNELS` | `telegram,wechat,custom,email,slack` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MARKDOWN_TO_IMAGE_MAX_CHARS` | `15000` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MARKET_REVIEW_COLOR_SCHEME` | `green_up` | 是 | 模板中注释; Market-review index gain/loss colors: green_up=green for gains and red for losses (default); red_up=red for gains and... |
| `MARKET_REVIEW_ENABLED` | `true` | 是 | Enable market review (true/false) |
| `MARKET_REVIEW_REGION` | `cn` | 是 | 模板中注释; Main Market Review Market Region: cn(A-shares), hk(Hong Kong stocks), us(U.S |
| `MAX_WORKERS` | `3` | 是 | Maximum number of concurrent threads (recommended to keep low concurrency to avoid bans) |
| `MCP_ANALYSIS_MAX_STOCKS` | `5` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_ANALYSIS_RATE_LIMIT_PER_MINUTE` | `2` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_HTTP_ALLOWED_HOSTS` | `127.0.0.1:*,localhost:*,[::1]:*` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_HTTP_ALLOWED_ORIGINS` | `http://127.0.0.1:*,http://localhost:*,http://[::1]:*` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_HTTP_BACKLOG` | `16` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_HTTP_KEEPALIVE_TIMEOUT_SECONDS` | `5` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_HTTP_MAX_BODY_BYTES` | `1000000` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_HTTP_MAX_CONNECTIONS` | `32` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_HTTP_MAX_HEADER_BYTES` | `32768` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_HTTP_READ_TIMEOUT_SECONDS` | `10` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_HTTP_RESOURCE` | `http://127.0.0.1:8765/mcp` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_HTTP_SCOPES` | `market.read,history.read` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_HTTP_SESSION_TOKEN_SHA256` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_MAX_CONCURRENT_TOOLS` | `8` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_RATE_LIMIT_PER_MINUTE` | `60` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_SERVER_ENABLED` | `false` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_SERVER_HOST` | `127.0.0.1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_SERVER_PORT` | `8765` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_SERVER_TRANSPORT` | `stdio` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_STDIO_PRINCIPAL` | `local-operator` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MCP_STDIO_SCOPES` | `market.read,history.read` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MD2IMG_ENGINE` | `wkhtmltoimage` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `MERGE_EMAIL_NOTIFICATION` | `false` | 是 | 模板中注释; Merge individual-stock analysis and market-review notifications (default false) to reduce email volume and spam risk. |
| `MINIMAX_API_KEYS` | `your_minimax_key_here` | 是 | 模板中注释; MiniMax API Key(Coding Plan Web Search, Supports multiple, Comma-separated) Get: https://platform.minimax.io/ |
| `MULTIMODAL_AGENT_TOOLS_ENABLED` | `false` | 是 | Optional multimodal PDF/chart/transcript Agent Tools (issue #253) |
| `MULTIMODAL_FILE_ROOT` | `/absolute/path/to/multimodal-uploads` | 是 | 模板中注释 |
| `NEWSNOW_BASE_URL` | `https://newsnow.busiyi.world` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `NEWS_INTEL_AUTO_FETCH_ENABLED` | `false` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `NEWS_INTEL_FETCH_TIMEOUT_SEC` | `8` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `NEWS_INTEL_MAX_ITEMS_PER_SOURCE` | `50` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `NEWS_INTEL_RETENTION_DAYS` | `30` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `NEWS_MAX_AGE_DAYS` | `3` | 是 | 模板中注释; Maximum news timeliness (days), limit search results to recent periods, avoid using outdated information |
| `NEWS_STRATEGY_PROFILE` | `short` | 是 | 模板中注释; =================================== News timeliness and analysis filtering configuration ============================... |
| `NOTIFICATION_ALERT_CHANNELS` | `空` | 是 | 模板中注释 |
| `NOTIFICATION_COOLDOWN_SECONDS` | `0` | 是 | 模板中注释; Limit the frequency of the same cooling key within the window; 0 disables |
| `NOTIFICATION_DAILY_DIGEST_ENABLED` | `false` | 是 | 模板中注释; Reserve configuration; daily summary will not be sent currently |
| `NOTIFICATION_DEDUP_TTL_SECONDS` | `0` | 是 | 模板中注释; [Notification Noise Reduction Mechanism](Issue #1200 P4) Default to disable all; only affects static notification cha... |
| `NOTIFICATION_MIN_SEVERITY` | `空` | 是 | 模板中注释; info,warning,error,critical; Leave blank to keep the status quo |
| `NOTIFICATION_QUIET_HOURS` | `空` | 是 | 模板中注释; Silent time period, format HH:MM-HH:MM, supports crossing midnight |
| `NOTIFICATION_REPORT_CHANNELS` | `空` | 是 | 模板中注释; Image conversion tool: wkhtmltopdf (apt install wkhtmltopdf / brew install wkhtmltopdf), or markdown-to-file [Notific... |
| `NOTIFICATION_SYSTEM_ERROR_CHANNELS` | `空` | 是 | 模板中注释 |
| `NOTIFICATION_TIMEZONE` | `空` | 是 | 模板中注释; Silent time zone, such as Asia/Shanghai; leave empty to follow TZ/system local time zone |
| `NTFY_TOKEN` | `空` | 是 | 模板中注释; Optional: For topics requiring a Bearer Token or self-hosted ntfy server |
| `NTFY_URL` | `空` | 是 | 模板中注释; ntfy Configuration NTFY_URL must contain topic path, e.g., https://ntfy.sh/my-topic or https://self-hosted:port/my-to... |
| `OCR_AGENT_TOOL_ENABLED` | `false` | 是 | Optional offline OCR Agent Tool (issue #196) |
| `OCR_FILE_ROOT` | `/absolute/path/to/ocr-uploads` | 是 | 模板中注释 |
| `OCR_LANGS` | `chi_sim+eng` | 是 | 模板中注释; Falls back to MULTIMODAL_FILE_ROOT when OCR_FILE_ROOT is unset. |
| `OCR_TIMEOUT_SECONDS` | `30` | 是 | 模板中注释; hard wall-clock bound, 1-120 seconds |
| `OLLAMA_API_BASE` | `http://localhost:11434` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `OPENAI_API_KEY` | `空` | 是 | 模板中注释; OpenAI / Compatible API |
| `OPENAI_API_KEYS` | `key1,key2,key3` | 是 | 模板中注释; Multi-key load balancing (comma-separated); takes priority over OPENAI_API_KEY when set. |
| `OPENAI_BASE_URL` | `空` | 是 | 模板中注释; Third-party API address (proxy/relay), leave empty to use official. |
| `OPENAI_MODEL` | `空` | 是 | 模板中注释; Legacy OpenAI-compatible model name (prefer LITELLM_MODEL / LLM Channels for new setups). |
| `OPENAI_TEMPERATURE` | `0.7` | 是 | 模板中注释; Legacy OpenAI sampling temperature (0.0-2.0); prefer LLM_TEMPERATURE for new setups. |
| `OPENAI_VISION_MODEL` | `空` | 是 | 模板中注释; Deprecated OpenAI-only vision model; prefer VISION_MODEL for image stock extraction. |
| `OPENCODE_CLI_MODEL` | `provider/model` | 是 | 模板中注释 |
| `OUTBOUND_HTTP_ALLOWLIST` | `192.168.1.100:11434,searxng.internal:8080,10.0.0.20:3000` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PAPER_PORTFOLIO_INITIAL_CASH` | `1000000` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PLUGINS_DIR` | `/absolute/path/to/reviewed/plugins` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PLUGIN_DATA_PROVIDER_AUTO_BIND` | `false` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PLUGIN_STATE_PATH` | `./data/plugin_lifecycle_state.json` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PORTFOLIO_FX_UPDATE_ENABLED` | `true` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PORTFOLIO_HEALTH_CASH_HIGH_ALERT_PCT` | `50.0` | 是 | 模板中注释 |
| `PORTFOLIO_HEALTH_CASH_LOW_ALERT_PCT` | `2.0` | 是 | 模板中注释 |
| `PORTFOLIO_HEALTH_CONCENTRATION_ALERT_PCT` | `35.0` | 是 | 模板中注释; Optional finite insight thresholds (cash low must be strictly below cash high): |
| `PORTFOLIO_HEALTH_DIVERSIFICATION_ALERT` | `0.35` | 是 | 模板中注释 |
| `PORTFOLIO_HEALTH_PNL_LOSS_ALERT_PCT` | `-15.0` | 是 | 模板中注释 |
| `PORTFOLIO_HEALTH_VAR_ALERT_PCT` | `5.0` | 是 | 模板中注释 |
| `PORTFOLIO_HEALTH_WEIGHT_CASH_RATIO` | `0.15` | 是 | 模板中注释 |
| `PORTFOLIO_HEALTH_WEIGHT_CONCENTRATION` | `0.25` | 是 | 模板中注释; Daily portfolio health score (issue #151) |
| `PORTFOLIO_HEALTH_WEIGHT_DIVERSIFICATION` | `0.20` | 是 | 模板中注释 |
| `PORTFOLIO_HEALTH_WEIGHT_PNL` | `0.15` | 是 | 模板中注释 |
| `PORTFOLIO_HEALTH_WEIGHT_RISK_EXPOSURE` | `0.25` | 是 | 模板中注释 |
| `PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS` | `7` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT` | `35.0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PORTFOLIO_RISK_DRAWDOWN_ALERT_PCT` | `15.0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PORTFOLIO_RISK_LOOKBACK_DAYS` | `180` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PORTFOLIO_RISK_STOP_LOSS_ALERT_PCT` | `10.0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PORTFOLIO_RISK_STOP_LOSS_NEAR_RATIO` | `0.8` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PORTFOLIO_STRESS_SCENARIOS_PATH` | `空` | 是 | 模板中注释; Optional YAML path (maximum 1,024 characters) that adds/overrides bounded portfolio stress scenarios by id |
| `PREFETCH_REALTIME_QUOTES` | `true` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_ADAPTIVE_PRIORITY_ENABLED` | `true` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES` | `3` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_CIRCUIT_BREAKER_ENABLED` | `true` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_CIRCUIT_COOLDOWN_SECONDS` | `300` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_CIRCUIT_FAILURE_THRESHOLD` | `3` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_DAILY_CACHE_DIR` | `data/provider_cache/daily` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_DAILY_CACHE_ENABLED` | `true` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_DAILY_CACHE_LOCAL_ONLY_MAX_AGE_SECONDS` | `2592000` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_DAILY_CACHE_MEMORY_MAX_ENTRIES` | `256` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_DAILY_CACHE_MEMORY_TTL_SECONDS` | `60` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_DAILY_CACHE_PERSISTENT_MAX_AGE_SECONDS` | `7776000` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_DAILY_CACHE_PERSISTENT_MAX_ENTRIES` | `512` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_DAILY_CACHE_PERSISTENT_TTL_SECONDS` | `3600` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_DAILY_CACHE_ROLLOVER_GRACE_DAYS` | `1` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_DAILY_CACHE_STALE_IF_ERROR_SECONDS` | `86400` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_HEALTH_WINDOW_SIZE` | `20` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROVIDER_MARKET_DATA_MODE` | `auto` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PROXY_HOST` | `127.0.0.1` | 是 | Proxy server address (default 127.0.0.1) |
| `PROXY_PORT` | `10809` | 是 | Proxy server port (default 10809) |
| `PUSHOVER_API_TOKEN` | `空` | 是 | 模板中注释 |
| `PUSHOVER_USER_KEY` | `空` | 是 | 模板中注释; Pushover Configuration Register Pushover account and create app Token https://pushover.net/apps/build |
| `PUSHPLUS_TOKEN` | `空` | 是 | 模板中注释; Method Seven: PushPlus Configuration (Domestic Push Service, Recommended) Register PushPlus account and get Token htt... |
| `PUSHPLUS_TOPIC` | `空` | 是 | 模板中注释; Group push: Fill in the group code to send messages to all subscription users of the group (one-to-many). |
| `PYTDX_HOST` | `192.168.1.100` | 是 | 模板中注释; Pytdx custom server (for intranet/deploy): use custom host instead of built-in public servers |
| `PYTDX_PORT` | `7709` | 是 | 模板中注释 |
| `PYTDX_PRIORITY` | `2` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `PYTDX_SERVERS` | `192.168.1.100:7709,10.0.0.1:7709` | 是 | 模板中注释; Comma-separated ip:port list; overrides PYTDX_HOST/PYTDX_PORT when set. |
| `REALTIME_SOURCE_PRIORITY` | `tencent,akshare_sina,efinance,akshare_em` | 是 | 模板中注释 |
| `REASONING_TRACE_EXPORT_ENABLED` | `false` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `REASONING_TRACE_EXPORT_MAX_CHARS` | `500000` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `REPORT_EXPORT_PDF_FONT_PATH` | `空` | 是 | 模板中注释; Report export (optional PDF) |
| `REPORT_HISTORY_COMPARE_N` | `0` | 是 | 模板中注释 |
| `REPORT_INTEGRITY_ENABLED` | `true` | 是 | 模板中注释 |
| `REPORT_INTEGRITY_RETRY` | `1` | 是 | 模板中注释 |
| `REPORT_LANGUAGE` | `zh` | 是 | 模板中注释; Report output language: zh(Chinese, default) / en(English) / ko(Korean) |
| `REPORT_MODE` | `standard` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `REPORT_RENDERER_ENABLED` | `false` | 是 | 模板中注释 |
| `REPORT_SHOW_LLM_MODEL` | `true` | 是 | 模板中注释; The bottom of the notification report displays the name of the LLM model used in this analysis; set to false to hide it |
| `REPORT_SUMMARY_ONLY` | `false` | 是 | 模板中注释; Only analyze the result summary: when set to true, it only pushes summaries, without individual stock details |
| `REPORT_TEMPLATES_DIR` | `templates` | 是 | 模板中注释; Report Engine P0 (Jinja2 / integrity check / Historical comparison) |
| `REPORT_TYPE` | `simple` | 是 | 模板中注释; Report type: simple (concise), full (complete), brief (3-5 sentence summary) In a Docker environment, if content is n... |
| `RISK_GATE_PROFILE` | `balanced` | 是 | 模板中注释; Mandatory Risk Manager profile before final buy/hold/sell recommendations |
| `RSS_NEWS_FEED_URLS` | `https://www.sec.gov/news/pressreleases.rss,https://feeds.example.com/market.atom` | 是 | 模板中注释; Optional RSS/Atom market-news feeds for the on-demand search pipeline (issue #271) |
| `RSS_NEWS_FETCH_TIMEOUT_SEC` | `8` | 是 | 模板中注释; Per-feed pull timeout in seconds (1-30, default 8) |
| `RUN_IMMEDIATELY` | `true` | 是 | Whether to immediately execute an analysis when the non-time mode is started (true/false) |
| `SAVE_CONTEXT_SNAPSHOT` | `true` | 是 | Analyze historical snapshot: Do not persist the entire context_snapshot when set to false Includes enhanced_context, ... |
| `SCHEDULE_ENABLED` | `false` | 是 | === Scheduled Task Configuration (legacy day-batch — DEPRECATED) === Prefer versioned scheduled tasks: Web Settings →... |
| `SCHEDULE_RUN_IMMEDIATELY` | `true` | 是 | Whether to immediately execute an analysis upon startup (true/false) |
| `SCHEDULE_TIME` | `18:00` | 是 | Daily execution time (HH:MM format, 24-hour clock) |
| `SCHEDULE_TIMES` | `空` | 是 | List execution over multiple time periods (comma-separated, use SCHEDULE_TIME if empty) |
| `SEARXNG_BASE_URLS` | `空` | 是 | SearXNG instance address (comma-separated, private deployments have no quotas; enable format: json in settings.yml) P... |
| `SEARXNG_PUBLIC_INSTANCES_ENABLED` | `true` | 是 |  |
| `SERPAPI_API_KEYS` | `空` | 是 | SerpAPI Keys (supports multiple, comma-separated) |
| `SERVERCHAN3_SENDKEY` | `空` | 是 | 模板中注释; Method Ten: ServerChan 3 configuration (domestic push service with WeChat delivery) Register a ServerChan 3 account a... |
| `SHARE_IMAGE_MAX_CHARS` | `100000` | 是 | 模板中注释; Web/API history share-image Markdown cap (independent of MARKDOWN_TO_IMAGE_MAX_CHARS) |
| `SHARE_IMAGE_XIAOHONGSHU_HANDLE` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `SHARE_IMAGE_XIAOHONGSHU_ID` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `SHARE_IMAGE_XIAOHONGSHU_QR_PATH` | `src/assets/share_image/xiaohongshu_qr.jpg` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `SHARE_IMAGE_XIAOHONGSHU_URL` | `空` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `SIGNAL_SCORECARD_MIN_SAMPLES` | `10` | 是 | 模板中注释; Buckets below this decided sample render as insufficient_data |
| `SIGNAL_SCORECARD_PUBLIC_ENABLED` | `false` | 是 | 模板中注释; Public signal scorecard (Issue #379; default off so self-hosted stays private) Exposes an aggregated, non-sensitive n... |
| `SINGLE_STOCK_NOTIFY` | `false` | 是 | 模板中注释; =================================== (Optional) Single stock push configuration =================================== Si... |
| `SKILL_OPINION_OUTCOME_WEIGHTS_ENABLED` | `false` | 是 | 模板中注释; Default-off Bayesian outcome weights for skill aggregation (issue #714) |
| `SKILL_OPINION_RECORDING_ENABLED` | `false` | 是 | 模板中注释; Record individual skill opinions into the offline outcome-evaluation store (default off) |
| `SLACK_BOT_TOKEN` | `xoxb-...` | 是 | 模板中注释; Method Nine: Slack Configuration Supports two methods: Bot API (recommended) and Incoming Webhook |
| `SLACK_CHANNEL_ID` | `C01234567` | 是 | 模板中注释 |
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/services/T.../B.../xxx` | 是 | 模板中注释; Method 2: Slack Incoming Webhook (simple configuration, does not support image uploads) Create Incoming Webhook in Sl... |
| `SMARTMONEY_ENABLED` | `false` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `SNAPSHOT_SOURCE_PRIORITY` | `tushare,sina,efinance,akshare_em,em_datacenter` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `SOCIAL_SENTIMENT_API_KEY` | `sk_live_your_key_here` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `SOCIAL_SENTIMENT_API_URL` | `https://api.adanos.org` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | 否 | 注册表缺口（见 issue #1026） |
| `SQLITE_WAL_ENABLED` | `true` | 否 | 注册表缺口（见 issue #1026） |
| `SQLITE_WRITE_RETRY_BASE_DELAY` | `0.1` | 否 | 注册表缺口（见 issue #1026） |
| `SQLITE_WRITE_RETRY_MAX` | `3` | 否 | 注册表缺口（见 issue #1026） |
| `STOCK_GROUP_1` | `600519,300750` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `STOCK_GROUP_2` | `002594,AAPL` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `STOCK_INDEX_REMOTE_UPDATE_ENABLED` | `true` | 是 | Stock Auto-completion Index Remote Update (default enabled; falls back to local built-in index if GitHub is inaccessi... |
| `STOCK_LIST` | `600519,300750,002594` | 是 | Watchlist stocks list (comma-separated, supports Shanghai and Shenzhen stock codes) Shanghai stocks: 600xxx, 601xxx, ... |
| `TAVILY_API_KEYS` | `空` | 是 | Tavily API Keys (supports multiple, comma-separated) |
| `TELEGRAM_BOT_TOKEN` | `123456789:ABCdefGHIjklMNOpqrsTUVwxyz` | 是 | 模板中注释; Method Three: Telegram Robot (Requires configuring both items simultaneously) 1 |
| `TELEGRAM_CHAT_ID` | `123456789` | 是 | 模板中注释 |
| `TELEGRAM_MESSAGE_THREAD_ID` | `2780` | 是 | 模板中注释 |
| `TENCENT_PRIORITY` | `5` | 是 | 模板中注释; Tencent direct daily K-line (China) - final A-share fallback |
| `TICKFLOW_API_KEY` | `空` | 是 | 模板中注释; TickFlow API Key (optional; used for A-shares daily K-line, real-time quotes, stock list/name and market review enhan... |
| `TICKFLOW_BATCH_DAILY_ENABLED` | `true` | 是 | 模板中注释; Batch pre-fetch daily K data through TickFlow when permission is granted. |
| `TICKFLOW_BATCH_SIZE` | `100` | 是 | 模板中注释; Maximum number of securities in a single batch request for TickFlow |
| `TICKFLOW_KLINE_ADJUST` | `none` | 是 | 模板中注释; none/forward/backward/forward_additive/backward_additive |
| `TICKFLOW_PRIORITY` | `2` | 是 | 模板中注释; TickFlow (A-shares) - Default: 2; Optional, must be configured with TICKFLOW_API_KEY |
| `TRADING_DAY_CHECK_ENABLED` | `true` | 是 | 模板中注释; Skip scheduled/CLI/GitHub Actions runs on non-trading days (true/false, default true) |
| `TRUST_X_FORWARDED_FOR` | `false` | 是 | 模板中注释; Trust X-Forwarded-For to get the real IP under a single-layer trusted reverse proxy (e.g., Nginx → App), take the rig... |
| `TUSHARE_HTTP_URL` | `http://api.tushare.pro` | 是 | 模板中注释; Tushare Pro API endpoint (optional) |
| `TUSHARE_PRIORITY` | `2` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `TUSHARE_TOKEN` | `空` | 是 | Data source configuration Tushare Pro Token (optional, obtained from https://tushare.pro/) |
| `USE_PROXY` | `false` | 是 | =================================== Proxy configuration (optional) =================================== Enable proxy (... |
| `VALUATION_AGENT_TOOL_ENABLED` | `false` | 是 | Optional DCF / relative valuation Agent Tool (issue #238) |
| `VISION_MODEL` | `空` | 是 | 模板中注释; Vision / image stock-code extraction model (preferred over OPENAI_VISION_MODEL) |
| `WEBHOOK_VERIFY_SSL` | `true` | 是 | 模板中注释; When hand-writing .env in Docker Compose, write it as $$content_json/$$title_json; The Web settings page will automat... |
| `WEBUI_AUTO_BUILD` | `true` | 是 | Automatically build the frontend before starting the Web service (npm install && npm run build, default true)? |
| `WEBUI_ENABLED` | `false` | 是 | =================================== WebUI configuration (optional) =================================== Should the Web... |
| `WEBUI_HOST` | `127.0.0.1` | 是 | WebUI listening address (default 127.0.0.1) |
| `WEBUI_PORT` | `8000` | 是 | WebUI listening port (default 8000) |
| `WECHAT_MAX_BYTES` | `4000` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |
| `WECHAT_WEBHOOK_URL` | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_key_here` | 是 | 模板中注释; =================================== Notification Channel Configuration (multiple can be configured simultaneously, al... |
| `YFINANCE_PRIORITY` | `0` | 否 | 模板中注释; 注册表缺口（见 issue #1026） |

<!-- config-env-inventory:end -->
