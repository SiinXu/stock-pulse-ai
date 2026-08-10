# Environment variable inventory and configuration sources

This page is the StockPulse **configuration key inventory** and **config addition process** entry. It is one of three configuration sources of truth:

| Source | Path | Role |
|--------|------|------|
| Template defaults | [`.env.example`](../.env.example) | Key names, sample/default values, secret placeholders, behavioral comments |
| Configuration registry | [`src/core/config_registry_parts/`](../src/core/config_registry_parts/) | Web Settings grouping, control types, validation, help metadata, default hints |
| This inventory | Machine-checked table below | Whether each key is documented; default alignment with the template |

Scenario-oriented guidance still lives in topic docs and the curated tables in the [Full configuration guide](full-guide_EN.md). The **complete key set** is defined by `.env.example` and this inventory.

Settings-page help maintenance rules: see the Chinese [settings-help.md](settings-help.md) (help contract is bilingual in locales).

## Why three-way alignment matters

If only one of the three sources is updated:

- Users follow docs for keys that do not exist, or for wrong defaults;
- Keys land in `.env.example` without registry metadata → Web Settings puts them in **Uncategorized**, renders the wrong control type, or hides never-saved keys entirely;
- Keys work in code/registry but never appear in the template or docs → self-hosters cannot discover them.

Local / CI checker:

```bash
python scripts/check_config_doc_consistency.py
python scripts/check_config_doc_consistency.py --json
python scripts/check_config_doc_consistency.py --write-inventory
python scripts/check_config_doc_consistency.py --self-test
```

Primary gap classes (plus CN/EN inventory drift and default mismatches):

1. **missing_from_docs**: present in `.env.example` but missing from one or both language inventories;
2. **missing_from_env**: present in inventory docs or the registry but missing from `.env.example` (`KEY=`, active or commented);
3. **missing_from_registry**: present in `.env.example` but not explicitly registered.

Default failure classes are `docs,env,cn_en,defaults`. **Registry gaps are reported but non-fatal by default**; registry partition workers and the Task 1 guard own registration. To fail on registry coverage as well:

```bash
python scripts/check_config_doc_consistency.py --fail-on all
```

## Configuration addition process (required)

When adding or changing a user-visible or runtime-configurable environment variable, complete **all** of the following in the same change:

1. **`.env.example`**
   - Add or update `KEY=value` (optional capabilities may stay commented as `# KEY=value`);
   - Document the default or a safe placeholder;
   - Comment purpose, allowed values, and links to topic docs above the key or inline.

2. **Configuration registry** (`src/core/config_registry_parts/` for the owning partition)
   - Register Web-editable or metadata-backed keys with `title` / `description` / `category` / `data_type` / `ui_control` / `default_value` / `options` / `validation` / `help_key` as needed;
   - Use toggle controls for booleans and select + `options` for enums so keys do not fall into uncategorized text boxes;
   - Keep Settings i18n titles and help in sync (see [settings-help.md](settings-help.md));
   - **Task 1 guard**: automated enforcement of the registry/presentation contract is delivered by Task 1 (partial existing coverage: `tests/test_config_registry.py::TestEnvExampleWebSettingsCoverage`; the full “unregistered key” guard lands with that task’s script/CI step). The three-way docs checker covers documentation inventory only and **does not** register keys.

3. **Documentation**
   - Run `python scripts/check_config_doc_consistency.py --write-inventory` to refresh both language inventory tables below;
   - If the key affects a user path, update [full-guide_EN.md](full-guide_EN.md) / [full-guide.md](full-guide.md) curated tables or the relevant topic doc (evaluate both languages);
   - For user-visible capability changes, add a flat `[Unreleased]` line in `docs/CHANGELOG.md`.

4. **Verification**
   - `python scripts/check_config_doc_consistency.py` (docs / template / CN-EN / defaults);
   - Registry changes also need `tests/test_config_registry.py` and Settings contract tests;
   - Do not claim Web Settings support without a registry entry.

### Deprecating configuration

- Before removing a key from `.env.example`, confirm code readers and any migration/compat path;
- Remove the key from this inventory and from full-guide curated tables so docs stop recommending dead keys;
- Registry removal/hiding is owned by registry tasks; keep Web titles/help free of ghost keys.

## Related docs

- [Full configuration guide (EN)](full-guide_EN.md#complete-environment-variables-list)
- [LLM Config Guide (EN)](LLM_CONFIG_GUIDE_EN.md)
- [settings-help.md](settings-help.md)
- [config-access-ratchet.md](config-access-ratchet.md) (code `get_config()` ratchet; different from this inventory)
- Chinese: [environment-variables.md](environment-variables.md)

## Full key inventory (machine-checked)

The table below is generated by `scripts/check_config_doc_consistency.py --write-inventory` from `.env.example` and the current registry.

- **Default** matches the `.env.example` assignment (empty values are recorded as `empty`).
- **Registered** is whether the key appears in `get_registered_field_keys()`; `no` marks a registry gap (see the tracking issue; do not edit registry parts in a docs-only PR).
- Long descriptions, enum values, and troubleshooting stay in `.env.example` comments and topic docs.

<!-- config-env-inventory:start -->

| Key | Default (``.env.example``) | Registered | Notes |
|-----|----------------------------|------------|-------|
| `ADMIN_AUTH_ENABLED` | `false` | yes | =================================== Web login authentication (optional) =================================== Set to tr... |
| `ADMIN_SESSION_MAX_AGE_HOURS` | `24` | no | commented template; registry gap (see issue #1026) |
| `AGENT_ARCH` | `single` | yes | commented template; Agent architecture mode (default single; multi is multi-agent orchestration mode) |
| `AGENT_CONTEXT_COMPRESSION_ENABLED` | `false` | yes | commented template; AskStock visible conversation context compression (disabled by default) |
| `AGENT_CONTEXT_COMPRESSION_PROFILE` | `balanced` | yes | commented template; Compression strategy: cost=save tokens / balanced=balance both goals / long_context_raw_first=preserve more original ... |
| `AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS` | `empty` | yes | commented template; Historical token threshold that triggers compression; leave empty to use the current profile preset |
| `AGENT_CONTEXT_PROTECTED_TURNS` | `empty` | yes | commented template; Preserve the most recent N user turns and the replies that follow them verbatim during compression; leave empty to us... |
| `AGENT_CRITIC_ENABLED` | `false` | yes | commented template; Optional bounded Critic for Native Multi analysis (default false) |
| `AGENT_DECISION_AGENT_TIMEOUT_S` | `0` | no | commented template; registry gap (see issue #1026) |
| `AGENT_DEEP_RESEARCH_BUDGET` | `30000` | yes | commented template; Deep-research tool token budget and timeout (seconds) for Agent analysis paths that enable deep research. |
| `AGENT_DEEP_RESEARCH_TIMEOUT` | `180` | yes | commented template |
| `AGENT_EVENT_ALERT_RULES_JSON` | `[{"stock_code":"600519","alert_type":"price_cross","direction":"above","price":1800},{"stock_code":"300750","alert_type":"price_change_percent","direction":"down","change_pct":3.0},{"stock_code":"000858","alert_type":"volume_spike","multiplier":2.5}]` | yes | commented template |
| `AGENT_EVENT_IMPACT_CONTEXT_ENABLED` | `true` | yes | commented template; Attach holdings/watchlist impact context to triggered alert notifications (managed data only; default true). |
| `AGENT_EVENT_MONITOR_ENABLED` | `false` | yes | commented template |
| `AGENT_EVENT_MONITOR_INTERVAL_MINUTES` | `5` | yes | commented template |
| `AGENT_FEATURES_ACKNOWLEDGED_OFF` | `false` | yes | commented template; When true, settles the Agent readiness check for CLI-only users who do not need Q&A Agent |
| `AGENT_GENERATION_BACKEND` | `auto` | yes | Agent Chat backend; Web settings page only exposes auto/litellm, hand-written local CLI backend will return unsupport... |
| `AGENT_INTEL_AGENT_TIMEOUT_S` | `0` | no | commented template; registry gap (see issue #1026) |
| `AGENT_INVESTMENT_COMMITTEE_MODE` | `false` | yes | commented template; Investment Committee mode (default off) |
| `AGENT_LITELLM_MODEL` | `empty` | yes | commented template; Agent main model (optional): Empty when inheriting from the main model; without provider prefix will parse as openai/... |
| `AGENT_MAX_IDENTICAL_TOOL_CALLS` | `3` | no | commented template; registry gap (see issue #1026) |
| `AGENT_MAX_STAGE_ENTRIES` | `1` | no | commented template; registry gap (see issue #1026) |
| `AGENT_MAX_STEPS` | `10` | yes | commented template; Agent maximum inference step limit (default 10, each sub-agent runs according to its preset value; higher than the de... |
| `AGENT_MEMORY_ENABLED` | `false` | yes | commented template; Memory and calibration system (tracks historical accuracy and automatically adjusts confidence) |
| `AGENT_MODE` | `true` | yes | commented template; =================================== Agent strategy dialogue configuration (Web dialogue page) =======================... |
| `AGENT_MULTI_STRATEGY_DELIBERATION` | `false` | yes | commented template; Multi-strategy deliberation cluster (default off) |
| `AGENT_NL_ROUTING` | `false` | yes | commented template; Route high-confidence stock-related bot messages to the Agent without an explicit command (default false). |
| `AGENT_OBSERVABILITY_DEEP_PAYLOAD` | `false` | yes | commented template |
| `AGENT_OBSERVABILITY_ENABLED` | `true` | yes | commented template; Agent observability L0 (structured run events with trace/span ids) Lightweight events are default-on and persist via ... |
| `AGENT_ORCHESTRATOR_MODE` | `standard` | yes | commented template; Multi-agent orchestration mode (applies only when AGENT_ARCH=multi) quick: technical analysis -> decision (fastest, a... |
| `AGENT_ORCHESTRATOR_TIMEOUT_S` | `600` | yes | commented template; Agent execution timeout budget in seconds (0 disables it; single-agent uses it for the full loop, multi-agent for col... |
| `AGENT_PORTFOLIO_AGENT_TIMEOUT_S` | `0` | no | commented template; registry gap (see issue #1026) |
| `AGENT_RISK_AGENT_TIMEOUT_S` | `0` | no | commented template; registry gap (see issue #1026) |
| `AGENT_RISK_OVERRIDE` | `true` | yes | commented template; Whether the risk-control agent may reject buy signals (enabled by default) |
| `AGENT_SKILLS` | `empty` | yes |  |
| `AGENT_SKILL_AGENT_TIMEOUT_S` | `0` | no | commented template; registry gap (see issue #1026) |
| `AGENT_SKILL_AUTOWEIGHT` | `true` | yes | commented template; Automatically weight strategy opinions based on backtesting performance. |
| `AGENT_SKILL_DIR` | `./strategies` | yes | commented template; Custom strategy directory (optional, place custom YAML strategy files; environment variable name follows internal ski... |
| `AGENT_SKILL_ROUTING` | `auto` | yes | commented template; Strategy routing mode (auto=select from market state / manual=use the AGENT_SKILLS list) |
| `AGENT_STAGE_FAILURE_POLICY` | `isolate` | no | commented template; registry gap (see issue #1026) |
| `AGENT_TECHNICAL_AGENT_TIMEOUT_S` | `0` | no | commented template; registry gap (see issue #1026) |
| `AGENT_TOOL_TIMEOUT_S` | `120` | no | commented template; registry gap (see issue #1026) |
| `AIHUBMIX_KEY` | `empty` | yes | commented template; AIHubmix Aggregation(https://aihubmix.com/) A Key using GPT/Claude/Gemini/GLM/Qwen models, without requiring VPN access |
| `AKSHARE_PRIORITY` | `1` | no | commented template; registry gap (see issue #1026) |
| `ALLOW_INSECURE_PUBLIC_BIND` | `false` | no | registry gap (see issue #1026) |
| `ALPHASIFT_DAILY_CALL_TIMEOUT_SEC` | `20` | no | commented template; registry gap (see issue #1026) |
| `ALPHASIFT_DAILY_HISTORY_CACHE_DIR` | `data/alphasift/daily_history` | no | commented template; registry gap (see issue #1026) |
| `ALPHASIFT_DATA_DIR` | `data/alphasift` | no | commented template; registry gap (see issue #1026) |
| `ALPHASIFT_EASTMONEY_JITTER_SEC` | `0.3` | no | commented template; registry gap (see issue #1026) |
| `ALPHASIFT_EASTMONEY_MIN_INTERVAL_SEC` | `1.0` | no | commented template; registry gap (see issue #1026) |
| `ALPHASIFT_ENABLED` | `false` | yes | AlphaSift stock selection integration (default closed; typically maintained by the Web "Enable Stock Selection" button) |
| `ALPHASIFT_FALLBACK_SNAPSHOT_PATH` | `data/alphasift/snapshot.last_good.json` | no | commented template; registry gap (see issue #1026) |
| `ALPHASIFT_INDUSTRY_PROVIDER_CACHE_DIR` | `data/alphasift/industry_provider_cache` | no | commented template; registry gap (see issue #1026) |
| `ALPHASIFT_INSTALL_SPEC` | `git+https://github.com/ZhuLinsen/alphasift.git@9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf` | yes | Switch instructions: - ALPHASIFT_ENABLED Only affects AlphaSift Stock selection process, Do not rewrite/Migrate/Clean... |
| `ALPHASIFT_SNAPSHOT_CALL_TIMEOUT_SEC` | `60` | no | commented template; registry gap (see issue #1026) |
| `ALPHASIFT_SOURCE_CALL_TIMEOUT_SEC` | `empty` | no | commented template; registry gap (see issue #1026) |
| `ALPHAVANTAGE_API_KEY` | `empty` | no | commented template; registry gap (see issue #1026) |
| `ANALYSIS_DELAY` | `0` | yes | commented template; =================================== Analyze interval configuration (optional) =================================== Del... |
| `ANSPIRE_API_KEYS` | `empty` | yes | Anspire Open API keys (supports multiple comma-separated values) Get keys from: https://open.anspire.cn/ When no high... |
| `ANSPIRE_LLM_BASE_URL` | `https://open-gateway.anspire.cn/v6` | yes | commented template |
| `ANSPIRE_LLM_ENABLED` | `true` | yes | commented template |
| `ANSPIRE_LLM_MODEL` | `Doubao-Seed-2.0-lite` | yes | commented template |
| `ANTHROPIC_API_KEY` | `empty` | yes | commented template; Anthropic Claude（https://console.anthropic.com） |
| `ANTHROPIC_API_KEYS` | `key1,key2,key3` | yes | commented template; Multi-key load balancing (comma-separated); takes priority over ANTHROPIC_API_KEY when set. |
| `ANTHROPIC_MAX_TOKENS` | `8192` | yes | commented template; Legacy Claude max response tokens. |
| `ANTHROPIC_MODEL` | `empty` | yes | commented template; Legacy Claude model name (prefer LITELLM_MODEL / LLM Channels for new setups). |
| `ANTHROPIC_TEMPERATURE` | `0.7` | yes | commented template; Legacy Claude sampling temperature (0.0-1.0); prefer LLM_TEMPERATURE for new setups. |
| `ASTRBOT_TOKEN` | `empty` | yes | commented template; Optional for AstrBot Webhook requiring Bearer Token |
| `ASTRBOT_URL` | `empty` | yes | commented template; AstrBot Configuration |
| `BACKTEST_ENABLED` | `true` | yes | =================================== Backtesting configuration (optional) =================================== Enable b... |
| `BACKTEST_ENGINE_VERSION` | `v1` | yes | Backtesting engine version (used to differentiate results when backtesting logic is upgraded). |
| `BACKTEST_EVAL_WINDOW_DAYS` | `10` | yes | Backtesting evaluation window (trading days) |
| `BACKTEST_MIN_AGE_DAYS` | `14` | yes | Only retrieve historical analysis records of N days ago (to avoid incomplete data for that day/recently) |
| `BACKTEST_NEUTRAL_BAND_PCT` | `2.0` | yes | Neutral-band threshold (%); for example, 2 treats -2% through +2% as neutral/sideways. |
| `BAOSTOCK_PRIORITY` | `3` | no | commented template; registry gap (see issue #1026) |
| `BIAS_THRESHOLD` | `5.0` | yes | commented template; Bias-ratio threshold (%); when deviation from MA5 exceeds this value, strong-trend stocks use a 1.5x threshold before... |
| `BOCHA_API_KEYS` | `your_bocha_key_here` | yes | commented template; =================================== Search engine configuration (for fetching stock news) |
| `BRAVE_API_KEYS` | `empty` | yes | Brave Search API Keys(Supports multiple, Comma-separated) Get: https://brave.com/search/api/ |
| `COINGECKO_API_BASE` | `empty` | no | commented template; registry gap (see issue #1026) |
| `COINGECKO_API_KEY` | `empty` | no | commented template; registry gap (see issue #1026) |
| `COINGECKO_API_PLAN` | `keyless` | no | commented template; registry gap (see issue #1026) |
| `CRYPTO_COINGECKO_PRIORITY` | `10` | no | commented template; registry gap (see issue #1026) |
| `CRYPTO_PROVIDER_ENABLED` | `false` | no | commented template; registry gap (see issue #1026) |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | `empty` | yes | commented template; Optional: For Webhooks requiring authentication (Header Authorization: Bearer <token>) |
| `CUSTOM_WEBHOOK_BODY_TEMPLATE` | `empty` | yes | commented template; Optional global JSON body template, overrides Bark/Slack/Discord etc |
| `CUSTOM_WEBHOOK_URLS` | `https://oapi.dingtalk.com/robot/send?access_token=xxx,https://hooks.slack.com/services/xxx` | yes | commented template; Custom Webhook (Supports multiple, comma-separated) Suitable for: DingTalk, Discord, Slack, Bark, and any service tha... |
| `DAILY_BRIEF_ENABLED` | `false` | yes | commented template; Daily brief with historical accuracy review (Issue #466; default off) When enabled, the runtime scheduler may emit at... |
| `DAILY_BRIEF_MIN_SAMPLES` | `10` | yes | commented template |
| `DAILY_BRIEF_NOTIFY` | `true` | no | commented template; registry gap (see issue #1026) |
| `DAILY_BRIEF_PERSIST_HISTORY` | `true` | no | commented template; registry gap (see issue #1026) |
| `DAILY_BRIEF_SAVE_REPORT_FILE` | `true` | no | commented template; registry gap (see issue #1026) |
| `DAILY_BRIEF_SCHEDULE_TIME` | `08:30` | yes | commented template |
| `DAILY_BRIEF_TIMEZONE` | `Asia/Shanghai` | yes | commented template |
| `DAILY_MARKET_CONTEXT_ENABLED` | `true` | yes | Should the market summary be injected into individual stock analysis prompts and should conservative barriers be enab... |
| `DATABASE_PATH` | `./data/stock_analysis.db` | no | registry gap (see issue #1026) |
| `DATA_VALIDATION_ENABLED` | `true` | no | commented template; registry gap (see issue #1026) |
| `DATA_VALIDATION_INSTRUMENT_OVERRIDES` | `empty` | no | commented template; registry gap (see issue #1026) |
| `DATA_VALIDATION_STRICT` | `false` | no | commented template; registry gap (see issue #1026) |
| `DATA_VALIDATION_STRICT_SCOPES` | `*/*` | no | commented template; registry gap (see issue #1026) |
| `DATA_VALIDATION_UPPER_LAYER_MODE` | `warn` | no | commented template; registry gap (see issue #1026) |
| `DEBUG` | `false` | yes | Enable debugging logs |
| `DECISION_MEMORY_ENABLED` | `true` | no | commented template; registry gap (see issue #1026) |
| `DECISION_MEMORY_LOOKBACK` | `5` | no | commented template; registry gap (see issue #1026) |
| `DECISION_MEMORY_MIN_AGE_DAYS` | `3` | no | commented template; registry gap (see issue #1026) |
| `DECISION_MEMORY_MIN_SAMPLES` | `5` | no | commented template; registry gap (see issue #1026) |
| `DECISION_PROFILE_CALIBRATION_ENABLED` | `false` | yes | commented template |
| `DEEPSEEK_API_KEY` | `empty` | yes | commented template; DeepSeek（https://platform.deepseek.com） Compatibility default: Only fill in DEEPSEEK_API_KEY, still using deepseek-ch... |
| `DEEPSEEK_API_KEYS` | `key1,key2,key3` | yes | commented template; Multi-key load balancing (comma-separated); takes priority over DEEPSEEK_API_KEY when set. |
| `DINGTALK_APP_KEY` | `xxxx` | yes | Application AppKey (shared with Webhook mode) |
| `DINGTALK_APP_SECRET` | `xxxx` | yes | AppSecret (shared with Webhook mode) |
| `DINGTALK_SECRET` | `empty` | yes | Signing secret for the DingTalk robot (a string starting with 'SEC'); leave empty when signing is disabled. |
| `DINGTALK_STREAM_ENABLED` | `false` | yes | Enable Stream mode |
| `DINGTALK_WEBHOOK_URL` | `empty` | yes | ====== DingTalk Robot ====== Webhook URL for DingTalk group robots |
| `DISCORD_BOT_TOKEN` | `empty` | yes | commented template; Method 2: Discord Bot API (requires Bot account and channel ID) 1 |
| `DISCORD_CHANNEL_ID` | `empty` | no | commented template; registry gap (see issue #1026) |
| `DISCORD_INTERACTIONS_PUBLIC_KEY` | `empty` | yes | commented template; If you need to receive Discord Interaction / Webhook callbacks, you must configure the public key for verification |
| `DISCORD_MAIN_CHANNEL_ID` | `empty` | yes | commented template |
| `DISCORD_MAX_WORDS` | `2000` | no | commented template; registry gap (see issue #1026) |
| `DISCORD_WEBHOOK_URL` | `https://discord.com/api/webhooks/your_webhook_id/your_webhook_token` | yes | commented template; Discord Configuration Supports two methods: Webhook (recommended, simple configuration) and Bot API (high permissions) |
| `DSA_WEB_DEV_API_PROXY` | `http://127.0.0.1:8000` | no | commented template; registry gap (see issue #1026) |
| `EFINANCE_CALL_TIMEOUT` | `30` | no | commented template; registry gap (see issue #1026) |
| `EFINANCE_PRIORITY` | `99` | no | commented template; registry gap (see issue #1026) |
| `EMAIL_GROUP_1` | `user1@example.com` | no | commented template; registry gap (see issue #1026) |
| `EMAIL_GROUP_2` | `user2@example.com` | no | commented template; registry gap (see issue #1026) |
| `EMAIL_PASSWORD` | `empty` | yes | commented template |
| `EMAIL_RECEIVERS` | `receiver@example.com` | yes | commented template; Optional: Leave empty to send to yourself |
| `EMAIL_SENDER` | `empty` | yes | commented template; [Method Four]Email Push (requires only 2 configurations, SMTP auto-recognition) Supports QQ email, 163 email, Gmail, etc |
| `ENABLE_CHIP_DISTRIBUTION` | `true` | yes | commented template; Enable chip distribution analysis (the upstream API is unstable; disabling it is recommended for cloud deployments) |
| `ENABLE_EASTMONEY_PATCH` | `false` | no | commented template; registry gap (see issue #1026) |
| `ENABLE_FUNDAMENTAL_PIPELINE` | `true` | no | commented template; registry gap (see issue #1026) |
| `ENABLE_REALTIME_QUOTE` | `true` | yes | commented template; Enable real-time quotes (disabling uses historical closing prices for analysis) |
| `ENABLE_REALTIME_TECHNICAL_INDICATORS` | `true` | yes | commented template; Intraday technical analysis: when enabled, real-time prices are used to calculate moving averages and bullish MA alig... |
| `FAILURE_NOTIFY_ENABLED` | `empty` | no | commented template; registry gap (see issue #1026) |
| `FEISHU_APP_ID` | `xxxx` | yes | Feishu app configuration (for App Bot active push / Stream Bot / Cloud Docs; does not directly enable group Webhook p... |
| `FEISHU_APP_SECRET` | `xxxx` | yes | App Bot push also requires FEISHU_CHAT_ID; prefer FEISHU_WEBHOOK_URL for simple group delivery. |
| `FEISHU_CHAT_ID` | `oc_xxxxxxxxxxxxx` | yes | commented template; App Bot proactively pushes targets; Stream Bot or Cloud Docs do not need this item |
| `FEISHU_DOMAIN` | `feishu` | yes | commented template; Use lark for the international Lark API and Stream endpoint |
| `FEISHU_MAX_BYTES` | `20000` | no | commented template; registry gap (see issue #1026) |
| `FEISHU_RECEIVE_ID_TYPE` | `chat_id` | yes | commented template |
| `FEISHU_SEND_AS_FILE` | `false` | no | commented template; registry gap (see issue #1026) |
| `FEISHU_STREAM_ENABLED` | `false` | yes | Enable long connection mode |
| `FEISHU_WEBHOOK_KEYWORD` | `股票日报` | yes | commented template |
| `FEISHU_WEBHOOK_SECRET` | `your_feishu_webhook_secret` | yes | commented template; Feishu group robot Webhook security configuration (only used in Webhook push mode) |
| `FEISHU_WEBHOOK_URL` | `https://open.feishu.cn/open-apis/bot/v2/hook/your_key_here` | yes | commented template; Method Two: Feishu Robot (Choose one of two) Method 2a — Group Custom Robot Webhook In Feishu group -> Settings -> Gr... |
| `FINNHUB_API_KEY` | `empty` | no | commented template; registry gap (see issue #1026) |
| `FUNDAMENTAL_CACHE_MAX_ENTRIES` | `256` | no | commented template; registry gap (see issue #1026) |
| `FUNDAMENTAL_CACHE_TTL_SECONDS` | `120` | no | commented template; registry gap (see issue #1026) |
| `FUNDAMENTAL_FETCH_TIMEOUT_SECONDS` | `8.0` | no | commented template; registry gap (see issue #1026) |
| `FUNDAMENTAL_RETRY_MAX` | `1` | no | commented template; registry gap (see issue #1026) |
| `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS` | `8.0` | no | commented template; registry gap (see issue #1026) |
| `FUTU_ACC_ID` | `empty` | yes | Leave empty to merge eligible ACTIVE REAL NORMAL/MASTER securities accounts. |
| `FUTU_OPEND_HOST` | `127.0.0.1` | yes | Optional Futu OpenD gateway for `python main.py --portfolio futu` (analysis scope) and POST /api/v1/portfolio/imports... |
| `FUTU_OPEND_PORT` | `11111` | yes |  |
| `FUTU_SECURITY_FIRM` | `NONE` | yes | NONE uses the Futu SDK's official security-firm auto-detection. |
| `GEMINI_API_KEY` | `empty` | yes | Gemini（https://aistudio.google.com） |
| `GEMINI_API_KEYS` | `key1,key2,key3` | yes | commented template; Multi-key load balancing (comma-separated); takes priority over GEMINI_API_KEY when set. |
| `GEMINI_MODEL` | `empty` | yes | commented template; Legacy single-provider model name (prefer LITELLM_MODEL / LLM Channels for new setups). |
| `GEMINI_MODEL_FALLBACK` | `empty` | yes | commented template; Legacy Gemini fallback model when the primary Gemini model fails. |
| `GEMINI_TEMPERATURE` | `0.7` | yes | commented template; Legacy Gemini sampling temperature (0.0-1.0); prefer LLM_TEMPERATURE for new setups. |
| `GENERATION_BACKEND` | `litellm` | yes | Generate backend: defaults to litellm; codex_cli / claude_code_cli / opencode_cli are explicit local CLI backends (ex... |
| `GENERATION_BACKEND_MAX_CONCURRENCY` | `1` | yes |  |
| `GENERATION_BACKEND_MAX_OUTPUT_BYTES` | `1048576` | yes |  |
| `GENERATION_BACKEND_TIMEOUT_SECONDS` | `300` | yes | Local CLI backend execution limit; timeout maximum 3600, output maximum 33554432 bytes, concurrent maximums are 16/4 ... |
| `GENERATION_FALLBACK_BACKEND` | `litellm` | yes | Backend-level fallback; Local .env empty values disable backend-level fallback, litellm -> litellm will be parsed as ... |
| `GOTIFY_TOKEN` | `empty` | yes | commented template; Gotify application token |
| `GOTIFY_URL` | `empty` | yes | commented template; Gotify Configuration GOTIFY_URL is the Gotify server base URL, without /message; the system will append /message and ... |
| `HTTP_PROXY` | `http://127.0.0.1:10809` | yes | commented template; Standard HTTP(S) proxy URL for outbound requests (data sources, LLM, search, notifications) |
| `INDICATOR_MACD_FAST` | `12` | yes | commented template |
| `INDICATOR_MACD_SIGNAL` | `9` | yes | commented template |
| `INDICATOR_MACD_SLOW` | `26` | yes | commented template |
| `INDICATOR_MA_PERIODS` | `5,10,20,60` | yes | commented template; Technical indicator periods for trend analysis (Issue #172) |
| `INDICATOR_RSI_PERIODS` | `6,12,24` | yes | commented template |
| `INDUSTRY_PROVIDER` | `none` | no | commented template; registry gap (see issue #1026) |
| `INDUSTRY_PROVIDER_MAX_BOARDS` | `80` | no | commented template; registry gap (see issue #1026) |
| `KRONOS_ENABLED` | `false` | yes | Optional local Kronos K-line forecasting Agent Tool |
| `KRONOS_MODEL_SIZE` | `mini` | yes |  |
| `KRONOS_WEIGHTS_DIR` | `/absolute/path/to/kronos-weights` | yes | commented template |
| `LITELLM_CONFIG` | `./litellm_config.yaml` | yes | commented template; Advanced: Model Routing YAML Configuration (optional, see docs/examples/litellm_config.example.yaml) |
| `LITELLM_FALLBACK_MODELS` | `empty` | yes | commented template; First-run readiness: GET /api/v1/onboarding/first-run (read-only; never writes .env) |
| `LITELLM_LOG_LEVEL` | `WARNING` | no | commented template; registry gap (see issue #1026) |
| `LITELLM_MODEL` | `openai/~anthropic/claude-sonnet-latest` | yes | commented template |
| `LLM_AIHUBMIX_API_KEY` | `sk-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_AIHUBMIX_BASE_URL` | `https://aihubmix.com/v1` | no | commented template; registry gap (see issue #1026) |
| `LLM_AIHUBMIX_MODELS` | `gpt-5.5,claude-sonnet-4-6,gemini-3.1-pro-preview` | no | commented template; registry gap (see issue #1026) |
| `LLM_AIHUBMIX_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_AIHUBMIX_PROVIDER` | `aihubmix` | no | commented template; registry gap (see issue #1026) |
| `LLM_ANSPIRE_API_KEY` | `sk-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_ANSPIRE_BASE_URL` | `https://open-gateway.anspire.cn/v6 (example)` | no | commented template; registry gap (see issue #1026) |
| `LLM_ANSPIRE_MODELS` | `Doubao-Seed-2.0-lite,Doubao-Seed-2.0-pro (example models)` | no | commented template; registry gap (see issue #1026) |
| `LLM_ANSPIRE_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_ANSPIRE_PROVIDER` | `anspire` | no | commented template; registry gap (see issue #1026) |
| `LLM_ANTHROPIC_API_KEY` | `sk-ant-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_ANTHROPIC_MODELS` | `claude-sonnet-4-6,claude-opus-4-7` | no | commented template; registry gap (see issue #1026) |
| `LLM_ANTHROPIC_PROTOCOL` | `anthropic` | no | commented template; registry gap (see issue #1026) |
| `LLM_ANTHROPIC_PROVIDER` | `anthropic` | no | commented template; registry gap (see issue #1026) |
| `LLM_CHANNELS` | `openrouter` | yes | commented template; OpenRouter（OpenAI Compatible） Source: Official Models API https://openrouter.ai/docs/api/api-reference/models/get-models |
| `LLM_CONFIG_MODE` | `auto` | yes | commented template; --- Model Configuration Source Mode (Optional) --- auto(Default): Maintain historical priority YAML > Channels > Lega... |
| `LLM_DASHSCOPE_API_KEY` | `sk-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | no | commented template; registry gap (see issue #1026) |
| `LLM_DASHSCOPE_MODELS` | `qwen3.6-plus,qwen3.6-flash` | no | commented template; registry gap (see issue #1026) |
| `LLM_DASHSCOPE_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_DASHSCOPE_PROVIDER` | `dashscope` | no | commented template; registry gap (see issue #1026) |
| `LLM_DEEPSEEK_API_KEY` | `sk-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | no | commented template; registry gap (see issue #1026) |
| `LLM_DEEPSEEK_MODELS` | `deepseek-v4-flash,deepseek-v4-pro` | no | commented template; registry gap (see issue #1026) |
| `LLM_DEEPSEEK_PROTOCOL` | `deepseek` | no | commented template; registry gap (see issue #1026) |
| `LLM_DEEPSEEK_PROVIDER` | `deepseek` | no | commented template; registry gap (see issue #1026) |
| `LLM_GEMINI_API_KEY` | `xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_GEMINI_API_KEYS` | `key1,key2` | no | commented template; registry gap (see issue #1026) |
| `LLM_GEMINI_MODELS` | `gemini-3.1-pro-preview,gemini-3-flash-preview` | no | commented template; registry gap (see issue #1026) |
| `LLM_GEMINI_PROTOCOL` | `gemini` | no | commented template; registry gap (see issue #1026) |
| `LLM_GEMINI_PROVIDER` | `gemini` | no | commented template; registry gap (see issue #1026) |
| `LLM_HERMES_API_KEY` | `sk-local-hermes` | no | commented template; registry gap (see issue #1026) |
| `LLM_HERMES_BASE_URL` | `http://127.0.0.1:8642/v1` | no | commented template; registry gap (see issue #1026) |
| `LLM_HERMES_MODELS` | `hermes-agent` | no | commented template; registry gap (see issue #1026) |
| `LLM_HERMES_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_HERMES_PROVIDER` | `custom` | no | commented template; registry gap (see issue #1026) |
| `LLM_MAX_TOKENS` | `2048` | no | commented template; registry gap (see issue #1026) |
| `LLM_MIMO_API_KEY` | `sk-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_MIMO_BASE_URL` | `https://your-mimo-endpoint.example/v1` | no | commented template; registry gap (see issue #1026) |
| `LLM_MIMO_MODELS` | `mimo-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_MIMO_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_MIMO_PROVIDER` | `custom` | no | commented template; registry gap (see issue #1026) |
| `LLM_MINIMAX_API_KEY` | `xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_MINIMAX_BASE_URL` | `https://api.minimax.io/v1` | no | commented template; registry gap (see issue #1026) |
| `LLM_MINIMAX_MODELS` | `MiniMax-M2.7,MiniMax-M2.7-highspeed` | no | commented template; registry gap (see issue #1026) |
| `LLM_MINIMAX_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_MINIMAX_PROVIDER` | `minimax` | no | commented template; registry gap (see issue #1026) |
| `LLM_MOONSHOT_API_KEY` | `sk-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_MOONSHOT_BASE_URL` | `https://api.moonshot.cn/v1` | no | commented template; registry gap (see issue #1026) |
| `LLM_MOONSHOT_MODELS` | `kimi-k2.6,kimi-k2.5` | no | commented template; registry gap (see issue #1026) |
| `LLM_MOONSHOT_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_MOONSHOT_PROVIDER` | `moonshot` | no | commented template; registry gap (see issue #1026) |
| `LLM_MY_PROXY_API_KEY` | `sk-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_MY_PROXY_BASE_URL` | `https://your-proxy.example.com/v1` | no | commented template; registry gap (see issue #1026) |
| `LLM_MY_PROXY_MODELS` | `gpt-5.5,claude-sonnet-4-6` | no | commented template; registry gap (see issue #1026) |
| `LLM_MY_PROXY_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_MY_PROXY_PROVIDER` | `custom` | no | commented template; registry gap (see issue #1026) |
| `LLM_OLLAMA_BASE_URL` | `http://localhost:11434` | no | commented template; registry gap (see issue #1026) |
| `LLM_OLLAMA_MODELS` | `qwen3:8b,qwen3:4b` | no | commented template; registry gap (see issue #1026) |
| `LLM_OLLAMA_PROVIDER` | `ollama` | no | commented template; registry gap (see issue #1026) |
| `LLM_OPENAI_API_KEY` | `sk-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_OPENAI_BASE_URL` | `https://api.openai.com/v1` | no | commented template; registry gap (see issue #1026) |
| `LLM_OPENAI_MODELS` | `gpt-5.5,gpt-5.4-mini` | no | commented template; registry gap (see issue #1026) |
| `LLM_OPENAI_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_OPENAI_PROVIDER` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_OPENROUTER_API_KEY` | `sk-or-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | no | commented template; registry gap (see issue #1026) |
| `LLM_OPENROUTER_MODELS` | `~anthropic/claude-sonnet-latest,~openai/gpt-latest` | no | commented template; registry gap (see issue #1026) |
| `LLM_OPENROUTER_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_OPENROUTER_PROVIDER` | `openrouter` | no | commented template; registry gap (see issue #1026) |
| `LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL` | `off` | yes | commented template |
| `LLM_PROMPT_CACHE_HINTS_ENABLED` | `false` | yes | commented template |
| `LLM_PROMPT_CACHE_TELEMETRY_ENABLED` | `true` | yes | commented template; Provider prompt cache Configuration(Optional) TELEMETRY controls only the recording of provider cache usage and diagn... |
| `LLM_SILICONFLOW_API_KEY` | `sk-xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` | no | commented template; registry gap (see issue #1026) |
| `LLM_SILICONFLOW_MODELS` | `deepseek-ai/DeepSeek-V3.2,Qwen/Qwen3-235B-A22B-Thinking-2507` | no | commented template; registry gap (see issue #1026) |
| `LLM_SILICONFLOW_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_SILICONFLOW_PROVIDER` | `siliconflow` | no | commented template; registry gap (see issue #1026) |
| `LLM_TEMPERATURE` | `0.7` | yes | commented template; Sampling temperature (0.0-2.0, default 0.7; 0 is most deterministic and 2 is most random) |
| `LLM_TIMEOUT_SEC` | `60` | no | commented template; registry gap (see issue #1026) |
| `LLM_USAGE_HMAC_KEY_VERSION` | `local-v1` | yes | commented template |
| `LLM_USAGE_HMAC_SECRET` | `empty` | yes | commented template; LLM usage telemetry message HMAC configuration (optional) |
| `LLM_VOLCENGINE_API_KEY` | `xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_VOLCENGINE_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | no | commented template; registry gap (see issue #1026) |
| `LLM_VOLCENGINE_MODELS` | `doubao-seed-1-6-251015,doubao-seed-1-6-thinking-251015` | no | commented template; registry gap (see issue #1026) |
| `LLM_VOLCENGINE_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_VOLCENGINE_PROVIDER` | `volcengine` | no | commented template; registry gap (see issue #1026) |
| `LLM_ZHIPU_API_KEY` | `xxx` | no | commented template; registry gap (see issue #1026) |
| `LLM_ZHIPU_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | no | commented template; registry gap (see issue #1026) |
| `LLM_ZHIPU_MODELS` | `glm-5.1,glm-4.7-flash` | no | commented template; registry gap (see issue #1026) |
| `LLM_ZHIPU_PROTOCOL` | `openai` | no | commented template; registry gap (see issue #1026) |
| `LLM_ZHIPU_PROVIDER` | `zhipu` | no | commented template; registry gap (see issue #1026) |
| `LOCAL_CLI_BACKEND_MAX_CONCURRENCY` | `1` | yes |  |
| `LOCAL_ONLY_MODE` | `false` | yes | commented template; Local Only / privacy mode (default off) |
| `LOCAL_RUNTIME_AUTO_DETECT` | `true` | yes | commented template; Zero-config first success: setup readiness probes loopback Ollama by default (never blocks startup; failures are log-... |
| `LOCAL_RUNTIME_DETECT_TIMEOUT_SECONDS` | `0.35` | yes | commented template |
| `LOG_DIR` | `./logs` | yes | System configuration Log directory |
| `LOG_LEVEL` | `INFO` | yes | Log level (DEBUG/INFO/WARNING/ERROR) |
| `LONGBRIDGE_ACCESS_TOKEN` | `empty` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_APP_KEY` | `empty` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_APP_SECRET` | `empty` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS` | `15` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_ENABLE_OVERNIGHT` | `false` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_HTTP_URL` | `https://openapi.longbridge.com` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_OAUTH_CLIENT_ID` | `empty` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_OAUTH_TOKEN_CACHE_B64` | `empty` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_PRINT_QUOTE_PACKAGES` | `false` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_PRIORITY` | `5` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_PUSH_CANDLESTICK_MODE` | `realtime` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_QUOTE_WS_URL` | `wss://openapi-quote.longbridge.com/v2` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_REGION` | `hk` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_STATIC_INFO_TTL_SECONDS` | `86400` | no | commented template; registry gap (see issue #1026) |
| `LONGBRIDGE_TRADE_WS_URL` | `wss://openapi-trade.longbridge.com/v2` | no | commented template; registry gap (see issue #1026) |
| `MARKDOWN_TO_IMAGE_CHANNELS` | `telegram,wechat,custom,email,slack` | no | commented template; registry gap (see issue #1026) |
| `MARKDOWN_TO_IMAGE_MAX_CHARS` | `15000` | no | commented template; registry gap (see issue #1026) |
| `MARKET_REVIEW_COLOR_SCHEME` | `green_up` | yes | commented template; Market-review index gain/loss colors: green_up=green for gains and red for losses (default); red_up=red for gains and... |
| `MARKET_REVIEW_ENABLED` | `true` | yes | Enable market review (true/false) |
| `MARKET_REVIEW_REGION` | `cn` | yes | commented template; Main Market Review Market Region: cn(A-shares), hk(Hong Kong stocks), us(U.S |
| `MAX_WORKERS` | `3` | yes | Maximum number of concurrent threads (recommended to keep low concurrency to avoid bans) |
| `MCP_ANALYSIS_MAX_STOCKS` | `5` | no | commented template; registry gap (see issue #1026) |
| `MCP_ANALYSIS_RATE_LIMIT_PER_MINUTE` | `2` | no | commented template; registry gap (see issue #1026) |
| `MCP_HTTP_ALLOWED_HOSTS` | `127.0.0.1:*,localhost:*,[::1]:*` | no | commented template; registry gap (see issue #1026) |
| `MCP_HTTP_ALLOWED_ORIGINS` | `http://127.0.0.1:*,http://localhost:*,http://[::1]:*` | no | commented template; registry gap (see issue #1026) |
| `MCP_HTTP_BACKLOG` | `16` | no | commented template; registry gap (see issue #1026) |
| `MCP_HTTP_KEEPALIVE_TIMEOUT_SECONDS` | `5` | no | commented template; registry gap (see issue #1026) |
| `MCP_HTTP_MAX_BODY_BYTES` | `1000000` | no | commented template; registry gap (see issue #1026) |
| `MCP_HTTP_MAX_CONNECTIONS` | `32` | no | commented template; registry gap (see issue #1026) |
| `MCP_HTTP_MAX_HEADER_BYTES` | `32768` | no | commented template; registry gap (see issue #1026) |
| `MCP_HTTP_READ_TIMEOUT_SECONDS` | `10` | no | commented template; registry gap (see issue #1026) |
| `MCP_HTTP_RESOURCE` | `http://127.0.0.1:8765/mcp` | no | commented template; registry gap (see issue #1026) |
| `MCP_HTTP_SCOPES` | `market.read,history.read` | no | commented template; registry gap (see issue #1026) |
| `MCP_HTTP_SESSION_TOKEN_SHA256` | `empty` | no | commented template; registry gap (see issue #1026) |
| `MCP_MAX_CONCURRENT_TOOLS` | `8` | no | commented template; registry gap (see issue #1026) |
| `MCP_RATE_LIMIT_PER_MINUTE` | `60` | no | commented template; registry gap (see issue #1026) |
| `MCP_SERVER_ENABLED` | `false` | no | commented template; registry gap (see issue #1026) |
| `MCP_SERVER_HOST` | `127.0.0.1` | no | commented template; registry gap (see issue #1026) |
| `MCP_SERVER_PORT` | `8765` | no | commented template; registry gap (see issue #1026) |
| `MCP_SERVER_TRANSPORT` | `stdio` | no | commented template; registry gap (see issue #1026) |
| `MCP_STDIO_PRINCIPAL` | `local-operator` | no | commented template; registry gap (see issue #1026) |
| `MCP_STDIO_SCOPES` | `market.read,history.read` | no | commented template; registry gap (see issue #1026) |
| `MD2IMG_ENGINE` | `wkhtmltoimage` | no | commented template; registry gap (see issue #1026) |
| `MERGE_EMAIL_NOTIFICATION` | `false` | yes | commented template; Merge individual-stock analysis and market-review notifications (default false) to reduce email volume and spam risk. |
| `MINIMAX_API_KEYS` | `your_minimax_key_here` | yes | commented template; MiniMax API Key(Coding Plan Web Search, Supports multiple, Comma-separated) Get: https://platform.minimax.io/ |
| `MULTIMODAL_AGENT_TOOLS_ENABLED` | `false` | yes | Optional multimodal PDF/chart/transcript Agent Tools (issue #253) |
| `MULTIMODAL_FILE_ROOT` | `/absolute/path/to/multimodal-uploads` | yes | commented template |
| `NEWSNOW_BASE_URL` | `https://newsnow.busiyi.world` | no | commented template; registry gap (see issue #1026) |
| `NEWS_INTEL_AUTO_FETCH_ENABLED` | `false` | no | commented template; registry gap (see issue #1026) |
| `NEWS_INTEL_FETCH_TIMEOUT_SEC` | `8` | no | commented template; registry gap (see issue #1026) |
| `NEWS_INTEL_MAX_ITEMS_PER_SOURCE` | `50` | no | commented template; registry gap (see issue #1026) |
| `NEWS_INTEL_RETENTION_DAYS` | `30` | no | commented template; registry gap (see issue #1026) |
| `NEWS_MAX_AGE_DAYS` | `3` | yes | commented template; Maximum news timeliness (days), limit search results to recent periods, avoid using outdated information |
| `NEWS_STRATEGY_PROFILE` | `short` | yes | commented template; =================================== News timeliness and analysis filtering configuration ============================... |
| `NOTIFICATION_ALERT_CHANNELS` | `empty` | yes | commented template |
| `NOTIFICATION_COOLDOWN_SECONDS` | `0` | yes | commented template; Limit the frequency of the same cooling key within the window; 0 disables |
| `NOTIFICATION_DAILY_DIGEST_ENABLED` | `false` | yes | commented template; Reserve configuration; daily summary will not be sent currently |
| `NOTIFICATION_DEDUP_TTL_SECONDS` | `0` | yes | commented template; [Notification Noise Reduction Mechanism](Issue #1200 P4) Default to disable all; only affects static notification cha... |
| `NOTIFICATION_MIN_SEVERITY` | `empty` | yes | commented template; info,warning,error,critical; Leave blank to keep the status quo |
| `NOTIFICATION_QUIET_HOURS` | `empty` | yes | commented template; Silent time period, format HH:MM-HH:MM, supports crossing midnight |
| `NOTIFICATION_REPORT_CHANNELS` | `empty` | yes | commented template; Image conversion tool: wkhtmltopdf (apt install wkhtmltopdf / brew install wkhtmltopdf), or markdown-to-file [Notific... |
| `NOTIFICATION_SYSTEM_ERROR_CHANNELS` | `empty` | yes | commented template |
| `NOTIFICATION_TIMEZONE` | `empty` | yes | commented template; Silent time zone, such as Asia/Shanghai; leave empty to follow TZ/system local time zone |
| `NTFY_TOKEN` | `empty` | yes | commented template; Optional: For topics requiring a Bearer Token or self-hosted ntfy server |
| `NTFY_URL` | `empty` | yes | commented template; ntfy Configuration NTFY_URL must contain topic path, e.g., https://ntfy.sh/my-topic or https://self-hosted:port/my-to... |
| `OCR_AGENT_TOOL_ENABLED` | `false` | yes | Optional offline OCR Agent Tool (issue #196) |
| `OCR_FILE_ROOT` | `/absolute/path/to/ocr-uploads` | yes | commented template |
| `OCR_LANGS` | `chi_sim+eng` | yes | commented template; Falls back to MULTIMODAL_FILE_ROOT when OCR_FILE_ROOT is unset. |
| `OCR_TIMEOUT_SECONDS` | `30` | yes | commented template; hard wall-clock bound, 1-120 seconds |
| `OLLAMA_API_BASE` | `http://localhost:11434` | no | commented template; registry gap (see issue #1026) |
| `OPENAI_API_KEY` | `empty` | yes | commented template; OpenAI / Compatible API |
| `OPENAI_API_KEYS` | `key1,key2,key3` | yes | commented template; Multi-key load balancing (comma-separated); takes priority over OPENAI_API_KEY when set. |
| `OPENAI_BASE_URL` | `empty` | yes | commented template; Third-party API address (proxy/relay), leave empty to use official. |
| `OPENAI_MODEL` | `empty` | yes | commented template; Legacy OpenAI-compatible model name (prefer LITELLM_MODEL / LLM Channels for new setups). |
| `OPENAI_TEMPERATURE` | `0.7` | yes | commented template; Legacy OpenAI sampling temperature (0.0-2.0); prefer LLM_TEMPERATURE for new setups. |
| `OPENAI_VISION_MODEL` | `empty` | yes | commented template; Deprecated OpenAI-only vision model; prefer VISION_MODEL for image stock extraction. |
| `OPENCODE_CLI_MODEL` | `provider/model` | yes | commented template |
| `OUTBOUND_HTTP_ALLOWLIST` | `192.168.1.100:11434,searxng.internal:8080,10.0.0.20:3000` | no | commented template; registry gap (see issue #1026) |
| `PAPER_PORTFOLIO_INITIAL_CASH` | `1000000` | no | commented template; registry gap (see issue #1026) |
| `PLUGINS_DIR` | `/absolute/path/to/reviewed/plugins` | no | commented template; registry gap (see issue #1026) |
| `PLUGIN_DATA_PROVIDER_AUTO_BIND` | `false` | no | commented template; registry gap (see issue #1026) |
| `PLUGIN_STATE_PATH` | `./data/plugin_lifecycle_state.json` | no | commented template; registry gap (see issue #1026) |
| `PORTFOLIO_FX_UPDATE_ENABLED` | `true` | no | commented template; registry gap (see issue #1026) |
| `PORTFOLIO_HEALTH_CASH_HIGH_ALERT_PCT` | `50.0` | yes | commented template |
| `PORTFOLIO_HEALTH_CASH_LOW_ALERT_PCT` | `2.0` | yes | commented template |
| `PORTFOLIO_HEALTH_CONCENTRATION_ALERT_PCT` | `35.0` | yes | commented template; Optional finite insight thresholds (cash low must be strictly below cash high): |
| `PORTFOLIO_HEALTH_DIVERSIFICATION_ALERT` | `0.35` | yes | commented template |
| `PORTFOLIO_HEALTH_PNL_LOSS_ALERT_PCT` | `-15.0` | yes | commented template |
| `PORTFOLIO_HEALTH_VAR_ALERT_PCT` | `5.0` | yes | commented template |
| `PORTFOLIO_HEALTH_WEIGHT_CASH_RATIO` | `0.15` | yes | commented template |
| `PORTFOLIO_HEALTH_WEIGHT_CONCENTRATION` | `0.25` | yes | commented template; Daily portfolio health score (issue #151) |
| `PORTFOLIO_HEALTH_WEIGHT_DIVERSIFICATION` | `0.20` | yes | commented template |
| `PORTFOLIO_HEALTH_WEIGHT_PNL` | `0.15` | yes | commented template |
| `PORTFOLIO_HEALTH_WEIGHT_RISK_EXPOSURE` | `0.25` | yes | commented template |
| `PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS` | `7` | no | commented template; registry gap (see issue #1026) |
| `PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT` | `35.0` | no | commented template; registry gap (see issue #1026) |
| `PORTFOLIO_RISK_DRAWDOWN_ALERT_PCT` | `15.0` | no | commented template; registry gap (see issue #1026) |
| `PORTFOLIO_RISK_LOOKBACK_DAYS` | `180` | no | commented template; registry gap (see issue #1026) |
| `PORTFOLIO_RISK_STOP_LOSS_ALERT_PCT` | `10.0` | no | commented template; registry gap (see issue #1026) |
| `PORTFOLIO_RISK_STOP_LOSS_NEAR_RATIO` | `0.8` | no | commented template; registry gap (see issue #1026) |
| `PORTFOLIO_STRESS_SCENARIOS_PATH` | `empty` | yes | commented template; Optional YAML path (maximum 1,024 characters) that adds/overrides bounded portfolio stress scenarios by id |
| `PREFETCH_REALTIME_QUOTES` | `true` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_ADAPTIVE_PRIORITY_ENABLED` | `true` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES` | `3` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_CIRCUIT_BREAKER_ENABLED` | `true` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_CIRCUIT_COOLDOWN_SECONDS` | `300` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_CIRCUIT_FAILURE_THRESHOLD` | `3` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_DAILY_CACHE_DIR` | `data/provider_cache/daily` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_DAILY_CACHE_ENABLED` | `true` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_DAILY_CACHE_LOCAL_ONLY_MAX_AGE_SECONDS` | `2592000` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_DAILY_CACHE_MEMORY_MAX_ENTRIES` | `256` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_DAILY_CACHE_MEMORY_TTL_SECONDS` | `60` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_DAILY_CACHE_PERSISTENT_MAX_AGE_SECONDS` | `7776000` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_DAILY_CACHE_PERSISTENT_MAX_ENTRIES` | `512` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_DAILY_CACHE_PERSISTENT_TTL_SECONDS` | `3600` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_DAILY_CACHE_ROLLOVER_GRACE_DAYS` | `1` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_DAILY_CACHE_STALE_IF_ERROR_SECONDS` | `86400` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_HEALTH_WINDOW_SIZE` | `20` | no | commented template; registry gap (see issue #1026) |
| `PROVIDER_MARKET_DATA_MODE` | `auto` | no | commented template; registry gap (see issue #1026) |
| `PROXY_HOST` | `127.0.0.1` | yes | Proxy server address (default 127.0.0.1) |
| `PROXY_PORT` | `10809` | yes | Proxy server port (default 10809) |
| `PUSHOVER_API_TOKEN` | `empty` | yes | commented template |
| `PUSHOVER_USER_KEY` | `empty` | yes | commented template; Pushover Configuration Register Pushover account and create app Token https://pushover.net/apps/build |
| `PUSHPLUS_TOKEN` | `empty` | yes | commented template; Method Seven: PushPlus Configuration (Domestic Push Service, Recommended) Register PushPlus account and get Token htt... |
| `PUSHPLUS_TOPIC` | `empty` | yes | commented template; Group push: Fill in the group code to send messages to all subscription users of the group (one-to-many). |
| `PYTDX_HOST` | `192.168.1.100` | yes | commented template; Pytdx custom server (for intranet/deploy): use custom host instead of built-in public servers |
| `PYTDX_PORT` | `7709` | yes | commented template |
| `PYTDX_PRIORITY` | `2` | no | commented template; registry gap (see issue #1026) |
| `PYTDX_SERVERS` | `192.168.1.100:7709,10.0.0.1:7709` | yes | commented template; Comma-separated ip:port list; overrides PYTDX_HOST/PYTDX_PORT when set. |
| `REALTIME_SOURCE_PRIORITY` | `tencent,akshare_sina,efinance,akshare_em` | yes | commented template |
| `REASONING_TRACE_EXPORT_ENABLED` | `false` | no | commented template; registry gap (see issue #1026) |
| `REASONING_TRACE_EXPORT_MAX_CHARS` | `500000` | no | commented template; registry gap (see issue #1026) |
| `REPORT_EXPORT_PDF_FONT_PATH` | `empty` | yes | commented template; Report export (optional PDF) |
| `REPORT_HISTORY_COMPARE_N` | `0` | yes | commented template |
| `REPORT_INTEGRITY_ENABLED` | `true` | yes | commented template |
| `REPORT_INTEGRITY_RETRY` | `1` | yes | commented template |
| `REPORT_LANGUAGE` | `zh` | yes | commented template; Report output language: zh(Chinese, default) / en(English) / ko(Korean) |
| `REPORT_MODE` | `standard` | no | commented template; registry gap (see issue #1026) |
| `REPORT_RENDERER_ENABLED` | `false` | yes | commented template |
| `REPORT_SHOW_LLM_MODEL` | `true` | yes | commented template; The bottom of the notification report displays the name of the LLM model used in this analysis; set to false to hide it |
| `REPORT_SUMMARY_ONLY` | `false` | yes | commented template; Only analyze the result summary: when set to true, it only pushes summaries, without individual stock details |
| `REPORT_TEMPLATES_DIR` | `templates` | yes | commented template; Report Engine P0 (Jinja2 / integrity check / Historical comparison) |
| `REPORT_TYPE` | `simple` | yes | commented template; Report type: simple (concise), full (complete), brief (3-5 sentence summary) In a Docker environment, if content is n... |
| `RISK_GATE_PROFILE` | `balanced` | yes | commented template; Mandatory Risk Manager profile before final buy/hold/sell recommendations |
| `RSS_NEWS_FEED_URLS` | `https://www.sec.gov/news/pressreleases.rss,https://feeds.example.com/market.atom` | yes | commented template; Optional RSS/Atom market-news feeds for the on-demand search pipeline (issue #271) |
| `RSS_NEWS_FETCH_TIMEOUT_SEC` | `8` | yes | commented template; Per-feed pull timeout in seconds (1-30, default 8) |
| `RUN_IMMEDIATELY` | `true` | yes | Whether to immediately execute an analysis when the non-time mode is started (true/false) |
| `SAVE_CONTEXT_SNAPSHOT` | `true` | yes | Analyze historical snapshot: Do not persist the entire context_snapshot when set to false Includes enhanced_context, ... |
| `SCHEDULE_ENABLED` | `false` | yes | === Scheduled Task Configuration (legacy day-batch — DEPRECATED) === Prefer versioned scheduled tasks: Web Settings →... |
| `SCHEDULE_RUN_IMMEDIATELY` | `true` | yes | Whether to immediately execute an analysis upon startup (true/false) |
| `SCHEDULE_TIME` | `18:00` | yes | Daily execution time (HH:MM format, 24-hour clock) |
| `SCHEDULE_TIMES` | `empty` | yes | List execution over multiple time periods (comma-separated, use SCHEDULE_TIME if empty) |
| `SEARXNG_BASE_URLS` | `empty` | yes | SearXNG instance address (comma-separated, private deployments have no quotas; enable format: json in settings.yml) P... |
| `SEARXNG_PUBLIC_INSTANCES_ENABLED` | `true` | yes |  |
| `SERPAPI_API_KEYS` | `empty` | yes | SerpAPI Keys (supports multiple, comma-separated) |
| `SERVERCHAN3_SENDKEY` | `empty` | yes | commented template; Method Ten: ServerChan 3 configuration (domestic push service with WeChat delivery) Register a ServerChan 3 account a... |
| `SHARE_IMAGE_MAX_CHARS` | `100000` | yes | commented template; Web/API history share-image Markdown cap (independent of MARKDOWN_TO_IMAGE_MAX_CHARS) |
| `SHARE_IMAGE_XIAOHONGSHU_HANDLE` | `empty` | no | commented template; registry gap (see issue #1026) |
| `SHARE_IMAGE_XIAOHONGSHU_ID` | `empty` | no | commented template; registry gap (see issue #1026) |
| `SHARE_IMAGE_XIAOHONGSHU_QR_PATH` | `src/assets/share_image/xiaohongshu_qr.jpg` | no | commented template; registry gap (see issue #1026) |
| `SHARE_IMAGE_XIAOHONGSHU_URL` | `empty` | no | commented template; registry gap (see issue #1026) |
| `SIGNAL_SCORECARD_MIN_SAMPLES` | `10` | yes | commented template; Buckets below this decided sample render as insufficient_data |
| `SIGNAL_SCORECARD_PUBLIC_ENABLED` | `false` | yes | commented template; Public signal scorecard (Issue #379; default off so self-hosted stays private) Exposes an aggregated, non-sensitive n... |
| `SINGLE_STOCK_NOTIFY` | `false` | yes | commented template; =================================== (Optional) Single stock push configuration =================================== Si... |
| `SKILL_OPINION_OUTCOME_WEIGHTS_ENABLED` | `false` | yes | commented template; Default-off Bayesian outcome weights for skill aggregation (issue #714) |
| `SKILL_OPINION_RECORDING_ENABLED` | `false` | yes | commented template; Record individual skill opinions into the offline outcome-evaluation store (default off) |
| `SLACK_BOT_TOKEN` | `xoxb-...` | yes | commented template; Method Nine: Slack Configuration Supports two methods: Bot API (recommended) and Incoming Webhook |
| `SLACK_CHANNEL_ID` | `C01234567` | yes | commented template |
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/services/T.../B.../xxx` | yes | commented template; Method 2: Slack Incoming Webhook (simple configuration, does not support image uploads) Create Incoming Webhook in Sl... |
| `SMARTMONEY_ENABLED` | `false` | no | commented template; registry gap (see issue #1026) |
| `SNAPSHOT_SOURCE_PRIORITY` | `tushare,sina,efinance,akshare_em,em_datacenter` | no | commented template; registry gap (see issue #1026) |
| `SOCIAL_SENTIMENT_API_KEY` | `sk_live_your_key_here` | no | commented template; registry gap (see issue #1026) |
| `SOCIAL_SENTIMENT_API_URL` | `https://api.adanos.org` | no | commented template; registry gap (see issue #1026) |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | no | registry gap (see issue #1026) |
| `SQLITE_WAL_ENABLED` | `true` | no | registry gap (see issue #1026) |
| `SQLITE_WRITE_RETRY_BASE_DELAY` | `0.1` | no | registry gap (see issue #1026) |
| `SQLITE_WRITE_RETRY_MAX` | `3` | no | registry gap (see issue #1026) |
| `STOCK_GROUP_1` | `600519,300750` | no | commented template; registry gap (see issue #1026) |
| `STOCK_GROUP_2` | `002594,AAPL` | no | commented template; registry gap (see issue #1026) |
| `STOCK_INDEX_REMOTE_UPDATE_ENABLED` | `true` | yes | Stock Auto-completion Index Remote Update (default enabled; falls back to local built-in index if GitHub is inaccessi... |
| `STOCK_LIST` | `600519,300750,002594` | yes | Watchlist stocks list (comma-separated, supports Shanghai and Shenzhen stock codes) Shanghai stocks: 600xxx, 601xxx, ... |
| `TAVILY_API_KEYS` | `empty` | yes | Tavily API Keys (supports multiple, comma-separated) |
| `TELEGRAM_BOT_TOKEN` | `123456789:ABCdefGHIjklMNOpqrsTUVwxyz` | yes | commented template; Method Three: Telegram Robot (Requires configuring both items simultaneously) 1 |
| `TELEGRAM_CHAT_ID` | `123456789` | yes | commented template |
| `TELEGRAM_MESSAGE_THREAD_ID` | `2780` | yes | commented template |
| `TENCENT_PRIORITY` | `5` | yes | commented template; Tencent direct daily K-line (China) - final A-share fallback |
| `TICKFLOW_API_KEY` | `empty` | yes | commented template; TickFlow API Key (optional; used for A-shares daily K-line, real-time quotes, stock list/name and market review enhan... |
| `TICKFLOW_BATCH_DAILY_ENABLED` | `true` | yes | commented template; Batch pre-fetch daily K data through TickFlow when permission is granted. |
| `TICKFLOW_BATCH_SIZE` | `100` | yes | commented template; Maximum number of securities in a single batch request for TickFlow |
| `TICKFLOW_KLINE_ADJUST` | `none` | yes | commented template; none/forward/backward/forward_additive/backward_additive |
| `TICKFLOW_PRIORITY` | `2` | yes | commented template; TickFlow (A-shares) - Default: 2; Optional, must be configured with TICKFLOW_API_KEY |
| `TRADING_DAY_CHECK_ENABLED` | `true` | yes | commented template; Skip scheduled/CLI/GitHub Actions runs on non-trading days (true/false, default true) |
| `TRUST_X_FORWARDED_FOR` | `false` | yes | commented template; Trust X-Forwarded-For to get the real IP under a single-layer trusted reverse proxy (e.g., Nginx → App), take the rig... |
| `TUSHARE_HTTP_URL` | `http://api.tushare.pro` | yes | commented template; Tushare Pro API endpoint (optional) |
| `TUSHARE_PRIORITY` | `2` | no | commented template; registry gap (see issue #1026) |
| `TUSHARE_TOKEN` | `empty` | yes | Data source configuration Tushare Pro Token (optional, obtained from https://tushare.pro/) |
| `USE_PROXY` | `false` | yes | =================================== Proxy configuration (optional) =================================== Enable proxy (... |
| `VALUATION_AGENT_TOOL_ENABLED` | `false` | yes | Optional DCF / relative valuation Agent Tool (issue #238) |
| `VISION_MODEL` | `empty` | yes | commented template; Vision / image stock-code extraction model (preferred over OPENAI_VISION_MODEL) |
| `WEBHOOK_VERIFY_SSL` | `true` | yes | commented template; When hand-writing .env in Docker Compose, write it as $$content_json/$$title_json; The Web settings page will automat... |
| `WEBUI_AUTO_BUILD` | `true` | yes | Automatically build the frontend before starting the Web service (npm install && npm run build, default true)? |
| `WEBUI_ENABLED` | `false` | yes | =================================== WebUI configuration (optional) =================================== Should the Web... |
| `WEBUI_HOST` | `127.0.0.1` | yes | WebUI listening address (default 127.0.0.1) |
| `WEBUI_PORT` | `8000` | yes | WebUI listening port (default 8000) |
| `WECHAT_MAX_BYTES` | `4000` | no | commented template; registry gap (see issue #1026) |
| `WECHAT_WEBHOOK_URL` | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your_key_here` | yes | commented template; =================================== Notification Channel Configuration (multiple can be configured simultaneously, al... |
| `YFINANCE_PRIORITY` | `0` | no | commented template; registry gap (see issue #1026) |

<!-- config-env-inventory:end -->
