# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

> For user-friendly release highlights, see the [GitHub Releases](https://github.com/SiinXu/stock-pulse-ai/releases) page.

## [Unreleased]
- [Changed] Added unified Web page and Router patterns with `AppPage`, `WorkspacePage`, `ResponsiveRail`, `PageHeader`, `Toolbar`, `Tabs`, `TabPanel`, `SummaryStrip`, and `WorkspaceNavigation`, plus focus restoration and guards against duplicate navigation primitives.
- [Changed] Formalized the shared Surface migration contract around `canvas`, `section`, `interactive`, and `overlay`, removed unused card styles, and added stable token-count guards with dual-theme and nine-viewport fixtures.
- [Changed] Added fail-open diagnostics for Pipeline `resolve`, `fetch`, `intelligence`, `context`, `analyze`, `persist`, `render`, and `dispatch` stages, including redacted summaries, traces, timing, status, degradation, and retryability.
- [Changed] Added the shared `SelectionChip` control with native button semantics, loading protection, wrapping labels, 36px visible height, 44px coarse-pointer targets, optional pressed state, and geometry guards.
- [Changed] Added the shared `DataTable` foundation with typed columns and row keys, accessible table and sorting semantics, canonical states, keyboard row activation, nested-control isolation, and focusable narrow-screen scrolling.
- [Tests] Added a broad-exception classification guard that fingerprints existing debt, requires explicit cleanup, optional-metadata, or recorded-fallback annotations, and rejects unexplained `BaseException` suppression.
- [Changed] Added shared Filter and Query patterns with `FilterBar`, `AdvancedFilterSheet`, `AppliedFilterChips`, Router-backed draft/applied state, deep-link recovery, and guards against private duplicates.
- [Changed] Migrated `StockScreeningPage` panels and states to semantic `Surface`, `InlineAlert`, and `EmptyState` components while preserving screening behavior and removing the `UI-SCR01` design-guard exception.
- [Changed] Migrated `LLMConfigModeBanner` and `GenerationBackendStatusPanel` from custom bordered panels to semantic interactive `Surface` components without changing behavior.
- [Changed] Migrated `DeepResearchPanel` result and citation cards to semantic `Surface` components and its running and idle states to compact `StatePanel` variants.
- [Changed] Removed the unused `home-panel-card` class from `TaskPanel`, narrowed its design-guard allowlist, and retained valid run-flow custom styles and interactions.
- [Changed] Replaced the remaining ad hoc Alerts rule-loading text with the shared compact `Loading` state while preserving rule-edit behavior.
- [Changed] Added a lightweight `ApplicationServices` composition root for process-wide Config, DatabaseManager, SearchService, and AnalysisTaskQueue instances, with lazy defaults and injectable test instances.
- [Changed] Migrated remaining Settings content panels and scheduler/configuration errors to semantic `Surface` and `InlineAlert` components without changing configuration behavior.
- [Changed] Removed 15 unused `home-panel-card` classes across report components and their design-guard exceptions while retaining intentional report visuals for later QA.
- [Changed] Migrated `PortfolioPage` controls to semantic `Surface` and shared button contracts, replaced sizing overrides with grid layout, and removed the `UI-P01` guard exception without changing portfolio behavior.
- [Changed] Removed unused `home-panel-card` classes from `StockHistoryTrendDrawer`, migrated metric cards to semantic `Surface`, and retained unresolved segmented controls and list-panel work for visual QA.
- [Changed] Migrated three Home analysis buttons to `IconButton` and primary `Button` contracts while preserving 44px targets, loading behavior, strategy menus, and responsive layout.
- [Changed] Replaced bespoke Backtest loading blocks with the shared compact `Loading` state while preserving result copy, metrics, and semantic colors.
- [Changed] Migrated FirstRunSetupCard and SchedulerSettingsCard panels to semantic `Surface` and replaced first-run loading text with the shared `Loading` state.
- [Chore] Broke the `decision_signal_service` and `decision_signal_extractor` import cycle by moving payload construction into `src/services/decision_signal_payload.py`, preserving public imports and adding AST regression coverage.
- [Changed] Migrated Decision Signals re-evaluation, preview, statistics, alerts, and loading states to semantic `Surface`, `StatCard`, `InlineAlert`, and `Loading` components while preserving financial values and copy.
- [Chore] Broke the `llm.usage` and `llm.provider_cache` import cycle by moving provider-family inference into `src/llm/provider_family.py`, preserving compatibility imports and adding AST and runtime tests.
- [Changed] Added shared bottom Sheet and Toast foundations with fixed regions, Dialog-compatible focus and scroll behavior, semantic layering, and persistent live-region accessibility.
- [Changed] Restored the experimental PydanticAI adapter, toolset, optional dependencies, and installed-state CI gate under ADR-002 while keeping Native permanently default and user-facing configuration unchanged.
- [Added] Added an explicit Deep Research mode to Web Chat with typed API support, same-page execution, cancellation, error handling, persistence, and history restoration.
- [Tests] Added a startup DDL guard that permits schema changes only during fresh `metadata.create_all` or registered migration execution and rejects business-layer DDL.
- [Changed] Standardized Web overlay hierarchy: fixed navigation and detail drawer dimensions, shared Modal/Drawer contracts, top-layer keyboard handling, inert backgrounds, scroll locking, and focus restoration.
- [Added] Added Portfolio account editing through the existing account form and `PUT /api/v1/portfolio/accounts/{id}`, preserving account identity and validation.
- [Changed] Converted intelligence scope normalization and composite uniqueness startup compatibility work into formal migrations `202607190004_intelligence_item_scope_values` and `202607190005_intelligence_item_unique_index`.
- [Added] Added Alerts rule editing with server refresh, concurrent-change protection, partial `PATCH` updates, and existing validation behavior.
- [Added] Added `/stocks/:stockCode` with independently loaded and retried real-time quotes and historical candles plus daily, weekly, and monthly periods.
- [Changed] Converted Portfolio idempotency scope columns, indexes, data normalization, and legacy trigger compatibility into migration `202607190003_portfolio_idempotency_scope_schema`.
- [Changed] Converted DecisionSignal `decision_profile`, profile-aware indexing, and legacy metadata backfill into migration `202607190002_decision_signal_profile_schema`.
- [Added] Added Run Postmortem to Decision Signals with safe defaults, explicit confirmation, bounded execution, and retryable-result handling.
- [Added] Added a Create Signal drawer with validated manual-source fields, live preview, confidence controls, and non-forgeable `source_type=manual` and `trigger_source=web_manual` metadata.
- [Changed] Converted `llm_usage` telemetry-column compatibility work into migration `202607190001_llm_usage_telemetry_columns` and made startup apply pending migrations through the runner.
- [Changed] Added authoritative `Surface`, `Section`, `StatePanel`, and `Alert` contracts with L0/L1/L2/Overlay semantics, consistent live-region and busy behavior, and compatibility wrappers for existing state components.
- [Fixed] Tightened Agent Runtime conformance evidence to explicit fixture IDs, removed profile-wide exception expansion, and corrected dependency and ADR claims to match observed dual-environment evidence.
- [Chore] Completed the Native Only runtime decision by removing dormant PydanticAI adapters, toolsets, optional dependencies, injection points, cross-runtime tests, and dedicated CI while retaining vendor-neutral contracts and Native behavior.
- [Changed] Migrated 90 shared `Button` calls from legacy `xsm`/`sm`/`md`/`lg` sizes to semantic `compact`/`default`/`comfortable`/`primary` tiers, removed compatibility styles, and added AST guards while preserving 28/32/36/40px dimensions and behavior.
- [Changed] Established shared, domain-neutral `Button`, `IconButton`, `Input`, `Field`, and `Textarea` contracts with explicit intents, semantic sizing, 44px coarse-pointer targets, and AST enforcement; Chat now waits for the default strategy catalog before allowing submission.
- [Fixed] Limited PR Review Flake8 checks to Python files that still exist after a change, while retaining deleted files in the full diff and automated review scope.
- [Fixed] Added a canonical DecisionSignal `presentation` model driven by `action`, centralizing localized labels, confidence, summaries, risks, timestamps, and provenance while preserving legacy fields for compatibility.
- [Fixed] Standardized administrator passwords, Provider API keys, and sensitive settings on `CredentialInput`, isolating autocomplete identities, keeping autofill changes local until explicit save, and adding localized row-level accessible names.
- [Fixed] Made login security messaging reflect the actual transport: HTTPS reports encryption, local HTTP is neutral, non-local HTTP warns about password exposure, and the fictional `StockPulse-V3-TLS` claim was removed.
- [Fixed] Extended `sanitize_diagnostic_text` and `sanitize_sensitive_text` to redact credentials in non-HTTP connection strings such as PostgreSQL, MySQL, Redis, MongoDB, and AMQP while retaining hosts for diagnostics.
- [Changed] Completed the experimental PydanticAI Single RUN bridge with real tool schemas, lossless multi-turn tool and reasoning traces, canonical prompts, normalized usage recording, deadline and cancellation fences, and explicit unsupported CHAT/RESEARCH results.
- [Changed] Updated the Agent runtime contract so `AgentRuntime.start()` returns a live `ExecutionHandle`; deeply frozen `ExecutionContext` snapshots and terminal first-wins behavior preserve all 36 replay fixtures.
- [Docs] Added `docs/financial-terminology-guide.md` as the governance source for approximately 100 financial concepts across ten UI languages, including semantic boundaries, authoritative language columns, translation baselines, drift tracking, and review rules.
- [Chore] Unified terminal-state writes through `classify_result_terminal_state`, ensuring cancellation wins over success across single-agent, multi-agent, and SSE execution without changing replay output.
- [Changed] Routed Native Agent tool calls through one `BoundToolSession`, removed the parallel ToolRegistry authority, and discarded late tool results after timeout or completion.
- [Tests] Added the `pydanticai-installed` CI job and native-isolation assertions so missing or skipped experimental dependencies fail when `STOCKPULSE_REQUIRE_PYDANTIC_AI=1`.
- [Docs] Adopted dual licensing: upstream code remains MIT, while new and substantially modified StockPulse code uses AGPL-3.0; synchronized LICENSE and all three READMEs.
- [Changed] Added cooperative backend cancellation for `/api/v1/agent/chat/stream` disconnects, recording cancelled rather than failed results and preserving the byte-compatible SSE fallback path.
- [Fixed] Corrected translations for new-language Settings labels, financial alert direction, missing-LLM notices, Markdown, and AlphaSift terminology, and replaced unstable navigation keys.
- [Changed] Aligned shared Button, SegmentedControl, Checkbox, Search, Badge, Notification, and sidebar Profile components with the common Figma specification.
- [Changed] Consolidated page menus, selectors, buttons, and inputs onto shared Popover, Select, Button, and Input components; settings defaults now come from backend schemas and Portfolio CSV no longer invents broker presets.
- [Fixed] Reduced oversized controls and empty states across Chat, Portfolio, Decision Signals, Backtest, and Alerts on desktop viewports.
- [Changed] Reworked the login page into a minimal centered card with a circular brand mark, solid background, and high-contrast primary action while preserving authentication and accessibility.
- [Changed] Standardized global buttons on soft `rounded-lg` corners, updated design guards, and introduced the `--radius-dot` token for decorative dots.
- [Fixed] Prevented stale authentication-status responses from overwriting a newer successful login state.
- [Fixed] Positioned Settings multi-select menus against the viewport, opening upward when necessary and maintaining an 8px narrow-screen margin.
- [Fixed] Made notification routing depend on complete runtime credential sets so partial channel configurations are not treated as routable.
- [Fixed] Derived configured notification channels from the live `Config` snapshot and rejected malformed ntfy/Gotify authorities, userinfo, ports, and NFKC URLs without exposing original values.
- [Fixed] Added latest-request protection to Settings loading, saving, conflict recovery, and external refresh while preserving rolling-upgrade compatibility for missing channel-state fields.
- [Fixed] Hardened login redirects against ASCII controls, spaces, DEL, backslashes, and URL-normalization bypasses.
- [Fixed] Removed the misleading `/` shortcut hint from sidebar search because no global shortcut exists.
- [Fixed] Preserved valid same-origin login deep links while rejecting external, protocol-relative, and backslash variants.
- [Changed] Aligned remaining button-like controls, including help links, Portfolio CSV selection, and Home notification chips, with the global button shape.
- [Fixed] Removed nested `main` landmarks from page containers and Backtest, and added an accessible Backtest h1.
- [Fixed] Expanded text and path settings inputs to the 240px control column while keeping numeric inputs compact.
- [Fixed] Replaced schedule enablement and date/time inputs with shared switch, time picker, and date picker controls, including explicit confirmation and duplicate-time filtering.
- [Fixed] Wrapped password inputs in Settings and the model connection editor in forms to eliminate browser warnings.
- [Fixed] Stabilized the Home History/Watchlist/Today tab bar and added standard tablist semantics with arrow and Home/End navigation.
- [Changed] Replaced flat Settings checkbox groups with searchable multi-select controls that summarize selections and preserve unknown stored values.
- [Changed] Limited report, alert, and system-error routing choices to configured notification channels and added a direct empty-state path to channel configuration.
- [Changed] Converted `REALTIME_SOURCE_PRIORITY` to an order-preserving multi-select while retaining aliases and custom sources.
- [Tests] Added 36 strict Agent Runtime replay fixtures covering A/HK/US finance scenarios, ModelRef routing, fallbacks, tool scope, timeouts, cancellation races, malformed output, and factory contracts.
- [Added] Added complete Traditional Chinese, Japanese, Korean, German, Spanish, Malay, French, and Indonesian Web translations, a ten-language selector, language detection, persistence, HTML language updates, Intl formatting, and completeness checks.
- [Added] Added an ordered database Migration Runner with stable IDs, SHA-256 checksums, single-migration transactions, SQLite write locking, and Desktop/Docker/Actions resource validation.
- [Fixed] Added release-profile compatibility for legacy databases without a migration registry and made `status` and `verify` strictly read-only.
- [Changed] Restricted migration SQL execution to a synchronous leased capability with fail-closed transaction controls, immutable statements, driver-path draining, authorizer preservation, and defense-in-depth guards.
- [Fixed] Rejected coroutine, generator, async-generator, context-manager, and recursive migration callables, requiring an exact `None` result and rolling back invalid executions.
- [Tests] Added Docker CI coverage that upgrades a legacy SQLite fixture through a real `DatabaseManager` and verifies canaries, checksums, target version, and second-start idempotency.
- [Fixed] Constrained searchable selectors inside mobile bottom sheets and opened them upward when space is limited.
- [Changed] Standardized at least 44px touch targets across shared controls and major Web workflows, adopted dynamic viewport units, and unified report h2 typography on a 28px token.
- [Fixed] Made ambiguous legacy bare model routes shared by multiple Connections fail closed with `ambiguous_legacy_model_route` and require a Connection-aware ModelRef.
- [Fixed] Removed raw Provider errors from Agent and Bot user responses, histories, traces, and logs; introduced stable sentinels and error codes with bounded, redacted SearchService diagnostics.
- [Fixed] Treated an analysis 409 as a duplicate task only when `error=duplicate_task`; other conflicts now use shared parsing and retain `params`, `details`, and `trace_id`.
- [Fixed] Replaced remaining user-visible DSA branding with StockPulse while preserving compatibility identifiers in environment variables, APIs, protocols, modules, and historical payloads.
- [Tests] Made ReportMarkdown language-matrix tests wait for actual loading completion instead of treating an early disabled copy button as rendered content.
- [Fixed] Masked all schema-sensitive System Config fields by default and scoped reusable masked Connection credentials to unchanged identity and endpoint attributes.
- [Fixed] Routed exception logging across API, Agent, Bot, System Config, Backtest, image extraction, and AlphaSift through one bounded redaction path with static fail-closed sink guards.
- [Fixed] Removed Pydantic `input` and exception context from global 422 envelopes, retaining only safe locations, types, and generic messages.
- [Tests] Hardened credential-bearing Playwright CI by disabling media artifacts, isolating seeding, scanning raw and staged outputs, validating archives and symlinks, and adding a deliberately failing real-login harness.
- [Changed] Moved configuration backup import/export from System & Security to Advanced while preserving authentication and conflict protection.
- [Fixed] Scoped persistent Portfolio operation IDs by operation, account, owner, and client key, added a seven-day replay window and additive SQLite migration, and retained retry IDs in the Web UI.
- [Changed] Added credential, console, model-list, and documentation URLs to Provider Catalog, restricted quick links to normalized credential-free HTTPS URLs, and removed the frontend Provider-ID link table.
- [Fixed] Propagated conditional field contracts through the Config Schema API and isolated missing or unknown AI placements and conditions in read-only Advanced diagnostics.
- [Changed] Standardized Web-facing errors on `error/message/params/details/trace_id`, retained a deprecated read-only `detail` alias, localized task message codes, and deduplicated reconnect payloads by task ID.
- [Chore] Converted GitHub workflows, templates, reviews, summaries, bot comments, and release notes to English; hardened dynamic output encoding and moved repository ownership and release links to `SiinXu/stock-pulse-ai`.
- [Fixed] Removed upstream AIHubMix referral header injection and Anspire/AIHubMix/SerpAPI promotional defaults while preserving explicitly configured custom headers.
- [Changed] Standardized workflow, email sender, HTTP User-Agent, Web fallback, and OpenAPI branding on StockPulse and moved deployment and stock-index targets to the current repository.
- [Docs] Corrected Docker documentation so upstream or unreleased images are not presented as official StockPulse artifacts and removed the unavailable Discussions link.
- [Tests] Added English-language guards for GitHub collaboration assets and paginated PR file enumeration for labeling and review reports.
- [Tests] Made Settings scheduler runtime hydration tests wait for asynchronous API completion in both state directions.
- [Docs] Clarified in all three READMEs that StockPulse is an independently maintained MIT-licensed fork of `ZhuLinsen/daily_stock_analysis` and updated repository, CI, documentation, and feedback links.
- [Changed] Completed Chinese and English UI coverage for Chat, Screening, Alerts, Portfolio, Settings, shared selectors, stock search, and report diagnostics while separating UI, report, and dynamic-source language boundaries.
- [Changed] Split Web translations into typed locale files for alerts, portfolio, screening, settings, stock search, and report chrome.
- [Tests] Added locale dictionary, interpolation, duplicate, hardcoded-copy, and 30-scenario Playwright i18n gates with precise allowlist validation in `web-gate`.
- [Docs] Added Chinese and English Web internationalization guidance covering UI/report boundaries, dynamic content, error codes, locale-aware formatting, and validation commands.
- [Fixed] Standardized the accessible login brand title on `StockPulse` and removed Playwright smoke dependence on legacy branding.
- [Fixed] Added explicit `LLM_<CONNECTION>_PROVIDER` identity, separating Provider identity from renameable Connection names and preserving multi-connection, rename, discovery, legacy, and Actions behavior.
- [Fixed] Added transactional replacement for deleting models still referenced by report, Agent, Vision, or fallback routes, with structured `model_in_use/details.referenced_by` enforcement.
- [Changed] Made Provider Catalog and `connection_fields` the single metadata and field-contract authorities, with strict rolling-upgrade protection, read-only handling for incomplete schemas, display-name validation, and Ollama discovery through `/api/tags`.
- [Tests] Isolated Playwright `.env`, SQLite, password hash, and session secrets; seeded deterministic Markdown reports and retained backend, Vite, and fake-provider logs without depending on developer state.
- [Docs] Synchronized Chinese and English contribution, model, Provider, Settings, and `.env.example` documentation for Provider/Connection/Model/Task Assignment, discovery, stale values, and E2E isolation.
- [Changed] Replaced free-form report, Agent, Vision, and fallback model inputs with accessible `SearchableSelect` controls backed by the available-model catalog while preserving unavailable stored values.
- [Changed] Added backend `ui_placement` metadata as the sole authority for field ownership and removed the frontend legacy Provider grouping list without changing configuration persistence contracts.
- [Changed] Simplified Settings terminology, removed environment-variable language from normal paths, and replaced magic typography and radius values with design tokens.
- [Changed] Unified Modal, Drawer, ConfirmDialog, Settings Help, and mobile history panels on one overlay stack with top-layer keyboard handling, inert backgrounds, scroll locking, and focus restoration.
- [Changed] Made Home query parameters authoritative for report and Run Flow deep links, refresh, sharing, Back/Forward behavior, invalid-link normalization, and latest-request-wins switching.
- [Chore] Made `web-gate` block on lint, i18n, Vitest, and build, trigger `web-e2e` for related backend changes, and run deterministic isolated services with credential-safe artifacts.
- [Docs] Documented `DSA_WEB_DEV_API_PROXY`, reconciled model-provider and Advanced-view descriptions, and standardized Chinese and English LLM guide paths on Settings > AI & Models > Model Access.
- [Changed] Consolidated AI & Models into Overview, Model Access, Task Routing, and Reliability; removed duplicate Advanced/provider editing paths and moved diagnostics to the top-level Advanced section.
- [Changed] Replaced model entry with `ModelMultiSelect`, searchable discovery, token-based manual addition, paste splitting, richer search, fallback reordering, and explicit preservation of unavailable routes.
- [Fixed] Allowed first-time setup for keyless Providers such as Ollama and required users to select discovered models instead of enabling all results automatically.
- [Changed] Simplified model-access terminology to Primary Model, Fallback Models, Service URL, and API Key, and replaced `KEY=value` examples with plain values.
- [Changed] Rendered notification-channel and `MARKET_REVIEW_REGION` multi-value fields as checkbox groups that preserve unknown values and display backend defaults.
- [Changed] Added authoritative Vision model reference validation when Connection structure changes while allowing unrelated saves with historically stale values.
- [Added] Rendered `MarketStructureCard` in market-review reports when persisted market-structure context is available while silently supporting older reports.
- [Changed] Expanded Web design guards across production CSS/TSX to block nonstandard button shapes, gradients, shimmer, hardcoded colors, magic dimensions, and raw `100vh` while preserving touch and focus accessibility.
- [Docs] Corrected model-access documentation and help paths, clarified stale-reference retention and `model_in_use`, and updated `MARKET_REVIEW_REGION` instructions to match checkbox behavior.
- [Changed] Removed hardcoded model IDs and `placeholder_models` from `src/llm/provider_catalog.py`; new Connections now discover or add models explicitly and remain incomplete without one.
- [Fixed] Isolated ambient LLM, auth, `ENV_FILE`, and `DATABASE_PATH` state in the full test suite and added Provider Catalog regression coverage without weakening assertions or ordering tests.
- [Changed] Made Settings > AI & Models > Model Access the single model service, Connection, and model-management entry, using one responsive modal while retaining YAML and Legacy storage compatibility.
- [Changed] Removed the duplicate `ModelProvidersPanel` and `modelProviders.ts` mapping so Provider metadata comes only from the backend catalog.
- [Changed] Replaced task model inputs with catalog-backed `SearchableSelect` controls, including empty, error/retry, and unavailable-value states.
- [Changed] Derived known LLM Providers from Provider Catalog, enriched available-model records with Provider and Connection metadata, and blocked deletion of referenced Connections with `unknown_model`.
- [Tests] Updated `test_daily_analysis_workflow_llm_env` to derive Provider channels from the backend catalog rather than presentation-only frontend templates.
- [Changed] Moved LLM Provider business metadata in Settings to `GET /system/config/llm/providers`, retaining only presentation copy, placeholders, and documentation links in the frontend.
- [Changed] Added authoritative value-source explanations to field help using `raw_value_exists`, distinguishing explicit, defaulted, unset, and sensitive values.
- [Added] Added Stop Generating to Web Chat, aborting the active stream and restoring input without changing sent messages or history.
- [Fixed] Prevented Enter from sending Chat messages during IME composition while retaining Shift+Enter for line breaks.
- [Added] Added `GET /api/v1/system/config/llm/providers` as the authoritative Provider catalog for labels, protocols, endpoints, credential requirements, discovery, and capabilities.
- [Added] Added Connection-aware `ModelRef` values to `GET /api/v1/system/config/llm/available-models` so same-name models remain independently routable across Connections.
- [Changed] Made the AI & Models overview derive effective, unavailable, and unconfigured states from authoritative available routes instead of non-empty strings.
- [Changed] Rendered finite schema `options` as selects and moved external docs and `KEY=value` examples into field help.
- [Fixed] Made first-run setup persist canonical Connection-aware ModelRefs, respect Provider-specific Base URL and key requirements, merge `LLM_CHANNELS`, select channels mode, retain drafts on errors, and hide internal keys from the summary.
- [Added] Added a responsive first-run Settings wizard for choosing cloud API or local CLI, configuring a Provider, explicitly selecting or adding models, and saving the minimum runnable configuration.
- [Changed] Consolidated internal configuration sources, backend selection, tuning, CLI state, and smoke tests under collapsed Advanced > Developer Diagnostics.
- [Changed] Improved mobile Settings navigation by moving focus and scrolling into the selected section while preserving desktop sidebar behavior.
- [Added] Added `restart_required` field badges and draft-level notices for settings that require a service restart.
- [Added] Added a page-level Settings validation summary that navigates across sections, focuses, and scrolls to every invalid field.
- [Changed] Split Reports, Alerts & Automation, Conversation, and Event Monitoring by field placement so each setting has one visible owner and independent status badges.
- [Changed] Removed runtime route fields from Connection editing; Task Routing now owns report, Agent, Vision, and temperature settings, while Reliability owns fallback order.
- [Added] Added AI & Models Overview and Task Routing views with an effective task matrix and centralized primary and fallback model editing.
- [Changed] Rebuilt Settings navigation as a section/view hierarchy with stable `?section=&view=` deep links, legacy query migration, responsive navigation, and state-only badges.
- [Added] Added 700ms grouped autosave with serialized backend-category updates, atomic AI model groups, explicit save states, conflict recovery, scoped resets, leave protection, and masked-secret handling.
- [Added] Added conditional schema contracts for visibility, enablement, and requirements, with authoritative backend validation and fail-safe handling of unknown operators.
- [Added] Added explicit `LLM_CONFIG_MODE=auto|channels|yaml|legacy` source selection while preserving priority and migration APIs and exposing details only in Developer Diagnostics.
- [Changed] Enforced complete enabled LLM Connections in backend validation while limiting strict checks to touched or newly enabled channels, preserving masked secrets and YAML exemptions.
- [Changed] Aligned Web Connection completeness with backend requirements, allowing incomplete disabled drafts and keyless Ollama or approved localhost endpoints.
- [Changed] Improved Connection card accessibility with one modal, non-nested interactions, delete confirmation, and authoritative reference blocking with a Task Routing link.
- [Changed] Debounced generated-backend draft previews and moved the runtime status panel into collapsed Developer Diagnostics.
- [Changed] Synchronized Settings category and subview state to URL query parameters for refreshable and shareable deep links.
- [Fixed] Displayed the actual Claude Code CLI or OpenCode CLI name in first-run checks instead of always showing Codex CLI.
- [Changed] Added an internal low-sensitivity disagreement-summary input pipeline for multi-agent DecisionAgent explanation work without changing public APIs or dashboard schemas.
- [Changed] Added TickFlow environment mappings to the daily analysis workflow and moved data-source stability details from README to the full guide.
- [Fixed] Ensured explicit WebUI `--host` and `--port` arguments override `.env` values while omitted arguments use resolved runtime configuration.
- [Changed] Added DingTalk notification environment mappings to `.github/workflows/00-daily-analysis.yml` for scheduled cloud analysis.
- [Fixed] Made the first Portfolio snapshot use `include_realtime=false` so holdings render before slow external quote prefetches complete.
- [Fixed] Preserved a valid sentiment score of `0` when task status reconstructs report actions, allowing low scores to resolve to sell recommendations.
- [Fixed] Reported interrupted Agent streams instead of rendering them as empty content while preserving the user's message.
- [Fixed] Normalized desktop `WEBUI_HOST=*` and `WEBUI_HOST=[::]` to `0.0.0.0` and `::` before probing and startup.
- [Changed] Extended `STOCK_LIST` parsing to Chinese punctuation, semicolons, spaces, and newlines across runtime, scheduling, CLI `--stocks`, Web Settings, and watchlist APIs, normalizing writes to commas.
- [Changed] Added `NEWS_INTEL_AUTO_FETCH_ENABLED` to fail-open initialize and refresh local RSS, Atom, and NewsNow pools for stock, Agent, and market-review analysis.
- [Changed] Added primary-stock context to Web AI Recommendations using recent analyses and stock-index candidates, and clarified zero-sample performance statistics.
- [Changed] Promoted DecisionSignal `decision_profile` to a nullable field with consistent same-profile query, deduplication, refresh, invalidation, compatibility, and idempotent SQLite backfill semantics.
- [Changed] Refined Settings layout with horizontally scrollable mobile categories, immediately visible content, and denser desktop field hierarchy and spacing.
- [Docs] Documented Tushare and Longbridge market-data configuration in Quick Start, clarified free AkShare/Baostock/YFinance fallbacks, and synchronized both README translations under `docs/`.
- [Changed] Added the #1743 Phase 6a internal DSA Tool Surface contract for schemas, fail-closed stock scope, structured errors, audit summaries, redacted diagnostics, and wire-level AgentBackend proof.
- [Fixed] Added explicit `orjson` installation to Desktop and Docker releases and a frozen-runtime import probe for desktop PyInstaller builds.
- [Changed] Removed the standalone market-theme and stock-position card from stock reports while retaining its data in analysis context, model prompts, and DecisionSignal extraction.
- [Changed] Removed duplicate AI Decision Signal summaries from notifications and full Markdown/WeChat reports without changing storage, alerts, or Web recommendations.
- [Changed] Added a Shenwan Level-1 industry ranking fallback to TickFlow and increased fundamental and market-structure capability timeouts from 3 to 8 seconds.
- [Docs] Added architecture selection, security checks, and temporary Gatekeeper bypass instructions for unsigned and unnotarized macOS DMGs.
- [Added] Added confirmed persistence of decision-profile signals recomputed from historical report snapshots, with created/existing/refreshed outcomes, profile-aware lifecycle rules, report-time anchoring, and auditable guardrails.
- [Changed] Standardized desktop branding, executables, installers, and release artifacts on StockPulse while preserving the existing `appId` and NSIS identity, migrating legacy user data once, and retaining rollback compatibility.
- [Changed] Moved history deletion code-variant resolution, 10,000-row batching, and no-progress protection into `HistoryService` and `AnalysisRepository`, leaving the API endpoint responsible only for HTTP error mapping.
- [Changed] Moved runtime process and notification request context into core contracts: Bot snapshots immutable context before async boundaries, core services no longer depend on API schemas or Bot DTOs, and reply targets validate platform-scoped credentials.
- [Chore] Broke the `config`, `provider_catalog`, and `config_registry` import cycle by moving static Provider data and accessors into `src/llm/provider_catalog_data.py`.
- [Changed] Migrated the Token Usage Recent Calls block from a native section and custom heading to semantic `Section` title, description, and action slots.
- [Changed] Added a unified in-process `TaskExecutionPort` with immutable task snapshots and events, shared submission, lookup, cancellation, retry, subscription, idempotency, deduplication, and interruption semantics.
- [Changed] Replaced real-time quote and historical candle loading text on `StockDetailsPage` with shared compact `Loading` states.
- [Chore] Moved Agent runtime registry, skill prompt, and executor assembly into `src/agent/runtime_assembly.py`, retained factory re-exports, removed the Native Adapter reverse import, and added an AST regression guard.
- [Changed] Replaced the Home batch-analysis status class mapping and custom state container with semantic compact `InlineAlert` variants.
- [Changed] Restored compact density and typography for `StockBarItem` and Portfolio overview statistics based on PR #35 without changing behavior.
- [Changed] Migrated the Backtest result table from custom `backtest-table` markup to shared `DataTable` semantics and scrolling, removing obsolete styles and guard exceptions.
- [Fixed] Populated US equity real-time `pe_ratio` and `pb_ratio` from yfinance `trailingPE` and `priceToBook` while leaving index quotes unchanged.
- [Changed] Updated the `get_stock_info` tool description to explicitly support A-share, US, and Hong Kong markets so Agents can use fundamental tools across all three.
- [Fixed] Made reasoning-model completion extraction select only the final text block and ignore typed reasoning blocks so JSON remains parseable and persistable.
- [Fixed] Limited MiniMax `<think>` stripping to a complete leading reasoning wrapper, preserved same-named tags inside JSON, supported streamed fragments, and made dict responses field-independent.
- [Added] Restored case-insensitive Chat session search with shared `SearchInput`, existing i18n keys, and a `DashboardStateBlock` no-match state.
- [Changed] Migrated Bot `/analyze` submissions to the shared `AnalysisTaskQueue`, preserving normalized-stock deduplication, task IDs, status and error contracts, reply context, success copy, and notification behavior.
- [Chore] Removed the obsolete `TaskService` singleton, exports, and tests after Bot analysis moved to the unified task authority, and formalized single-process and interrupted-task semantics.
- [Changed] Added typed Pipeline stage results and a thread-safe retry fence so uncommitted failures can retry without duplicating confirmed history, local reports, or per-channel notifications.
- [Added] Added the multi-strategy evidence computation layer with deterministic strategy ordering, aggregation, synthesis, conflict detection, confidence handling, and invalid-opinion diagnostics.
- [Changed] Migrated the Portfolio holdings table from legacy markup to shared `DataTable` semantics, scrolling, and empty states while preserving financial formatting and interactions.
- [Changed] Replaced the Home Run Flow side drawer with a centered fullscreen `Modal` based on PR #35 while preserving existing modal sizes and run-flow behavior.
- [Changed] Migrated the Stock Details historical candle table from legacy markup to shared `DataTable` columns, row keys, semantics, and scrolling.
- [Changed] Restored the Home workspace view switcher to a single-line `SearchInput` plus compact Funnel `Select` based on PR #35.
- [Added] Added Chinese, English, and Korean rendering of multi-strategy evidence in Markdown, WeChat summaries, notifications, and history, including consensus, conflicts, supporting and opposing strategies, and invalid-opinion counts.
- [Changed] Migrated DecisionSignal display, outcome, timeline, and creation components from custom card boundaries to shared `Surface` and `Section` semantics.
- [Fixed] Refined Router focus coordination so cross-page PUSH navigation focuses the destination h1 while same-page query and hash updates retain current focus.
- [Fixed] Added low-sensitivity runtime facts for multi-Agent timeout, budget degradation, and Pipeline termination, and unified dashboard risk application and post-risk signal ordering.
- [Changed] Added localized exception impact, remediation guidance, and safe diagnostic codes to report input-data summaries while distinguishing supplemental data loaded after analysis.
- [Changed] Restored compact AlphaSift strategy configuration based on PR #35 using shared `Select` and `Modal` controls without changing URL, task, or strategy behavior.
- [Changed] Formalized the application shell around typed navigation descriptors, one shared compact navigation trigger, complete branding and Profile access, and the owner-selected framed main surface.
- [Fixed] Tightened application-shell Router focus and responsive contracts, including fail-closed opener restoration and stable 44px compact navigation targets.
- [Changed] Restored the login background grid and radial theme lights, retained the dedicated `--login-bg-main` token, and removed tight brand and authentication-title letter spacing.
- [Changed] Completed the Web UIUX audit by adding controlled detail rows to `DataTable`, migrating the AlphaSift results table, and unifying Backtest, Decision Signals, and Screening query updates.
- [Added] Added an authenticated, unlisted `/playground` component workbench to production Web builds with isolated iframes, deterministic fixtures, an in-memory Mock API, deep-linked viewport/theme/language controls, and sensitive-data isolation.
<!-- New entry format: - [Type] Description (Type: Added/Changed/Fixed/Docs/Tests/Chore) -->
<!-- Append each entry as one line at the end of this section; do not add category headings. -->
- [改进] Web 新增统一页面与 Router Pattern：`AppPage`/`WorkspacePage`、可折叠 `ResponsiveRail`、稳定 H1 ref 的 `PageHeader`、语义 `Toolbar`、同页 `Tabs`/`TabPanel`、`SummaryStrip` 与基于 Router Link/原生紧凑选择器的 `WorkspaceNavigation` 分离页面、工作区、命令、指标和导航职责；应用级焦点协调器在同窗口 PUSH/REPLACE 后等待目标 ready 再聚焦 H1，POP 优先恢复稳定触发点且重复/失效标记回退 H1，direct/refresh/new-tab 不强制移焦，元数据仅存内存。生产守卫禁止复制公共 Pattern 或新增业务 `pushState`/`replaceState`，三处遗留按文件/方法/计数交由页面轨清理。
- [改进] Web 固化共享 Surface 迁移契约：确认 `canvas`/`section`/`interactive`/`overlay` 四层与现有 subtle token 足以替代旧 `glass-card`、raw white-alpha 和无效 `bg-surface`，不新增 glass 层级；删除无生产消费者的 `dashboard-card` 重复样式，并以不依赖行号的“文件 + token 计数”守卫冻结其余 UI1/UI2/UI3 页面迁移债，双主题与九视口 fixture 验证语义边界、填充、分隔线、ring 和横向溢出。
- [改进] Pipeline 新增 `resolve`、`fetch`、`intelligence`、`context`、`analyze`、`persist`、`render`、`dispatch` 阶段诊断，统一记录脱敏输入/输出摘要、trace、耗时、状态、降级与 retryability；观测失败保持 fail-open，通知失败与分析结果分离，既有行为、数据库结构和配置不变。
- [改进] Web 新增共享 `SelectionChip` 选择控件：保持原生非提交 button 与 ref/disabled/loading/键盘语义，loading 期间以 `aria-busy` 禁止重复激活，单行最小可见高度 36px、长标签自动换行增高，粗指针命中区独立扩展至 44px；持续选择可选用 `aria-pressed` 与稳定选中标识，一次性选择命令不伪造 pressed 状态。控件拒绝页面覆盖 height/width/padding/radius/flex 几何，并由生产守卫阻止私有同名实现；Decision Signals 旧候选 Button 仍由 `UI-D01`/`TRACK-UI2` 独立迁移并删除精确 allowlist。
- [改进] Web 新增共享 `DataTable` 基础：typed columns/row keys、原生 caption/column/row 语义、受控 `aria-sort` 排序、唯一 empty/loading/error/retrying 状态、click/Enter/Space 行激活与嵌套控件事件隔离；窄屏使用命名且可聚焦的内部横向滚动区和稳定最小宽度，不造成文档横溢。生产守卫阻止复制 DataTable 或新增 raw table，现有 12 处旧表格按精确行绑定 UI1/UI2/UI3 迁移项。
- [测试] 新增 broad exception 分类门禁，以结构指纹冻结未审查存量，要求新增兜底路径明确标注 cleanup、optional_metadata 或 fallback_recorded，并禁止无说明的 BaseException pass。
- [改进] Web 新增统一 Filter/Query 基础：`FilterBar`、响应式 `AdvancedFilterSheet`、可单项移除的 `AppliedFilterChips` 与 Router 驱动的 draft/applied 查询状态共同保证高级筛选渐进披露、无变化时禁用 Apply、保留无关 URL 参数，并支持刷新及前进/后退恢复；生产守卫阻止页面新增私有同名 Pattern 或直接调用 `pushState`/`replaceState`，现有三处旧筛选写法以精确迁移清单交由页面轨移除。
- [改进] Web 选股页（`StockScreeningPage`）迁移到语义容器与控件契约：5 个 ad-hoc `<section>`/`<form>` 面板、顶部状态 chip 与热点/概念/因子等内部卡片改用 `Surface`（`interactive` 档，边框/圆角/底色/阴影收敛到设计 token），热点错误提示改用 `InlineAlert`、无结果空态改用 `EmptyState`；主"开始选股"按钮不再用 `min-w-40` 覆写共享 `Button`，改由 `grid` 包裹保留最小宽度并清除设计守卫 `UI-SCR01` allowlist 例外；选股结果、涨跌/热度语义色、筛选与提交行为不变。装饰性圆点/徽章、可选卡片按钮与表格行内部按现状保留。
- [改进] Web 设置组件 `LLMConfigModeBanner` 与 `GenerationBackendStatusPanel` 的手搓边框面板迁移到语义 `Surface`（interactive 层级），圆角/边框/背景改由 token 与层级提供，徽章、状态、迁移弹窗与文案行为不变。
- [改进] Web Chat 深度研究面板（`DeepResearchPanel`）收敛 ad-hoc surface 与内联状态：结论与引用两处手搓边框卡片改用语义 `Surface`（interactive 层级），运行中与空闲提示改用语义 `StatePanel`（loading/empty，compact），圆角/边框/背景改由 token 与层级提供，研究运行、取消、持久化与文案行为不变。
- [改进] Web 任务面板（`TaskPanel`）收敛守卫债：移除根 `Card` 上无 CSS 定义的死类 `home-panel-card`（零视觉），保留 `overflow-hidden` 与 `${className}` 透传，设计守卫对应 allowlist 条目 token 收窄为仅 `dynamic:className`。`components/run-flow` 已普遍使用语义 `Button`/`IconButton`，其 `home-subpanel`/`home-accent-chip`/`home-spinner` 为原生元素上的真实定制样式（守卫不 flag），事件行点击包裹与运行流图节点为定制交互，均按现状保留。
- [改进] Web 告警中心页（`AlertsPage`）编辑规则弹窗的加载占位统一走语义 `Loading`：将唯一遗留的 ad-hoc 加载文本 `<p>` 改用页面已引入的共享 `Loading`（compact `StatePanel`），与页内其余的 `Loading`/`EmptyState`/`ApiErrorAlert` 状态一致；加载文案与编辑行为不变。
- [改进] 新增轻量 `ApplicationServices` composition root（`src/application_services.py`）统一持有进程级单例（`Config`/`DatabaseManager`/`SearchService`/`AnalysisTaskQueue`），默认透明惰性委托到现有访问器、行为不变，并可注入隔离实例供测试；`server.py`/`main.py` 启动层在 config 就绪后建立该 root，`get_db()` 改为经 root 委托（默认仍解析到 `DatabaseManager.get_instance()`）。`get_config` 代理因与开放 PR #72（config import-cycle）同改 `src/config.py` 暂缓、`get_search_service` 代理需先做去递归的构造下沉，均记为后续；不改 `system_config_service` 内部与 task queue 独占文件。
- [改进] Web 设置页正文剩余手搓面板迁移到语义 `Surface`（interactive 层级）：快速配置横幅、AlphaSift 面板、版本信息卡片组、桌面更新卡、配置备份卡与调度状态卡内的信息小卡统一走 token/层级;调度器的“上次错误”与配置校验错误从裸 `text-danger` 块改用语义 `InlineAlert`(danger)。间距/圆角/边框/背景改由 token 提供，读写、保存、校验与文案行为不变。
- [改进] Web 报告展示组件收敛守卫债：跨 `ReportOverview`/`ReportNews`/`ReportStrategy`/`ReportDetails`/`ReportDiagnostics`/`AnalysisContextSummary`/`MarketReviewReportView` 移除 15 处 `Card` 上无 CSS 定义的死类 `home-panel-card`（零视觉），并同步删除设计守卫里对应的本轨 allowlist 例外（`ReportOverview` 仍保留真实的 `home-insight-card`/`home-rail-card` 类及其 allowlist token）；`text-left`/`min-w-0` 等既有类不变。报告的 `home-insight-card`/`home-rail-card`/`home-report-hero`/`home-subpanel`/`home-accent-chip` 为真实定制视觉，其到 `Surface` 的收敛待可视化 QA，记为本轨后续。
- [改进] Web 持仓中心页（`PortfolioPage`）迁移到语义容器与控件契约：账户视图控制条改用 `Surface`（`interactive` 档）；账户操作、CSV 导入与交易/现金/分红提交按钮不再用 `flex-1`/`w-full` 覆写共享 `Button` 尺寸，改由 `grid` 布局包裹拉伸，并清除设计守卫中 `PortfolioPage` 的 `UI-P01` allowlist 例外（连带把引用该例外的守卫自测 fixture 改指到仍在册的本轨 `DecisionSignalsPage` 例外，不动守卫规则逻辑）；账户/持仓数字、盈亏语义色、提交与幂等行为不变。滚动事件列表视口与 CSV 文件 chip 属列表内部/紧凑元素，记为本轨后续。
- [改进] Web 历史趋势抽屉（`StockHistoryTrendDrawer`）收敛 ad-hoc 面板：移除 3 处 `Card` 上无 CSS 定义的死类 `home-panel-card`（零视觉，纯守卫债），并同步删除设计守卫里对应的本轨 allowlist 例外；页内 ad-hoc 指标卡片改用语义 `Surface`（`interactive` 档，圆角/内边距/数值不变，边框与底色对齐设计 token）。范围/查看报告按钮为保 44px 粗指针命中区暂不改用 `SegmentedControl`/`Button`，`glass-card` 列表面板的层级取舍待可视化 QA，均记为本轨后续。
- [改进] Web 首页分析主流程的三处 ad-hoc 原生按钮迁移到冻结语义控件：移动端历史抽屉入口与重复任务横幅关闭改用 `IconButton`（视觉档位收敛，粗指针 44px 命中区不变），主“分析”CTA 改用 `Button` primary + `isLoading`/`loadingText`（移除 `btn-primary` 全局样式、`!important` 尺寸覆写与手写 spinner，满宽由 `grid` 包裹保留），可访问名、禁用/加载行为、策略菜单与响应式布局不变。
- [改进] Web 回测页加载态统一走语义 `Loading`：性能侧栏与结果表两处 bespoke `backtest-spinner` 加载块改用共享 `Loading`（compact `StatePanel`），与页面既有的 `EmptyState`/`ApiErrorAlert` 空态/错误态一致；结果表加载文案、指标卡与数字涨跌语义色不变。
- [改进] Web 设置页 FirstRunSetupCard 与 SchedulerSettingsCard 的手搓边框面板迁移到语义 `Surface`（interactive 层级），首次启动检查的裸加载文案改用 `Loading`；间距、圆角、边框与背景改由 token 与层级提供，读写、保存、调度状态与文案行为不变。
- [chore] 解除 `decision_signal_service` 与 `decision_signal_extractor` 的 import 循环：将纯 payload 构建层（`build_decision_signal_payload_from_report` 及全部 helper）下沉到新的叶子模块 `src/services/decision_signal_payload.py`，service 与 extractor 均从叶子复用；service 不再反向 import extractor，行为不变，`build_decision_signal_payload_from_report` 仍可从 extractor 导入，另加 AST 回归守护。
- [改进] Web 决策信号页迁移到冻结语义容器：重评估面板与预览指标块改用 `Surface`，全局后验统计卡改用 `StatCard`（涨跌语义色以内联 span 保留），重评估告警列表改用 `InlineAlert`，块级加载态统一改用 `Loading`（compact `StatePanel`），移除页面内 ad-hoc 卡片边框/背景/圆角；数字、方向、单位与文案不变，候选股多行 chip 按钮受限于基础层暂缺多行控件，保留其既有样式并记 Deferred to UIUX。
- [chore] 解除 `llm.usage` 与 `llm.provider_cache` 的 import 循环：将 provider-family 推断下沉到新的叶子模块 `src/llm/provider_family.py`，两侧改为模块级依赖该叶子并移除两处函数内延迟 import；纯结构调整，provider 推断行为不变，`infer_provider_family` 仍可从 `provider_cache` 导入，另加 AST + 运行时防回归测试。
- [改进] Web 新增统一的底部 Sheet 与 Toast 基础：筛选 Sheet 使用固定 header、单一滚动 body 和固定 footer，并复用 Dialog 的滚动锁、Escape、焦点循环与恢复；Toast 通过应用级 Provider、语义层级和保留 live region 在 Modal/Drawer/Sheet 打开时保持可见可读，设置与决策信号页不再维护私有高位 z-index。
- [改进] Agent Runtime 按 ADR-002 恢复实验 PydanticAI Adapter、toolset、可选依赖清单与 `pydanticai-installed` 安装态 CI 门禁；cross-runtime conformance 改为显式 fixture ID 允许清单并对未知 `single_run` fixture fail closed；Native 保持永久默认、零 PydanticAI 依赖可运行、无 runtime fallback，且不新增用户设置或公开 API。
- [新功能] Web Chat 新增显式“深度研究”模式：新增 typed `agentApi.research` 客户端与 Chat 内 Chat/深度研究模式开关，在同一页面就一个问题运行深度研究（问题 + 可选股票代码），同步执行、可取消（AbortController），错误/超时明确提示；结果含结论（Markdown 渲染）与子问题引用，并按会话持久化到 localStorage 实现刷新恢复（进行中的运行刷新后不可续跑，恢复为可重跑）；不新建 Research Hub。后端 research 为同步、无 task/SSE/会话落库，服务端持久化与乐观续跑记为 Non-goal。
- [测试] 新增启动 DDL 守护回归测试：捕获 `DatabaseManager` 初始化期间的全部 `CREATE`/`ALTER`/`DROP`，断言它们只发生在 `metadata.create_all`（fresh baseline）或 `apply_pending_within_transaction`（已登记 migration）两个相位内，两相位之外的游离 schema DDL（重新引入的启动期 ensure）会被判失败；并断言已迁移库重启时不执行任何 DDL、`migration verify` 对 fresh 与 legacy 库均成功且解释到 target version。
- [改进] Web 浮层基础统一使用语义层级：Navigation Drawer 固定为左侧 320px 导航面板，Detail Drawer 仅提供 480/576/640px 三档右侧宽度，调用方不能再覆写方向、宽度、遮罩或 z-index；Modal 与 Drawer 提供固定 header、可滚动 body 和可选 footer，Popover 在 Dialog 内就近 Portal，父 popup 不再把子 popup 的选项误判为外部点击，并保持 Escape、焦点循环、滚动锁和关闭后焦点恢复；AST 守卫阻止任意浮层几何、高位 z-index 与近全屏面板重新进入生产代码。
- [新功能] Web 持仓中心支持编辑账户：选中具体账户后打开“编辑账户”，复用账户表单的编辑模式修改名称、券商、市场与基准币，经 `PUT /api/v1/portfolio/accounts/{id}` 做真更新——保持 account ID、账本/持仓与幂等关联不变，不删除重建；成功后刷新并选中该账户。后端为 last-write-wins，无单账户 GET 与乐观并发锁，记为 Non-goal。
- [改进] `intelligence_items` 的 legacy scope 值规范化与 legacy url 唯一约束到 scoped 复合唯一键的重建 startup 兼容步骤转为正式 migration `202607190004_intelligence_item_scope_values` + `202607190005_intelligence_item_unique_index`（两者耦合：回填必须先于重建，故合并交付并在 apply_pending 内按序执行）；05 用冻结的原始 SQL 把 legacy 表重建为模型 schema、去除 url 唯一并建 scoped 唯一键，仅在需要时重建、幂等。移除运行时 `_ensure_intelligence_item_scope_values` / `_ensure_intelligence_items_unique_index` / `_rebuild_intelligence_items_table` / `_ensure_intelligence_items_scoped_unique_index_once` DDL。至此启动路径不再执行任何业务 schema DDL 兼容步骤，只保留 `create_all` 与 baseline 记录登记。
- [新功能] Web 告警中心支持编辑告警规则：复用现有规则表单的 edit 模式，点击规则行“编辑”后经 `GET /api/v1/alerts/rules/{id}` 拉取最新服务端值再播种（并发变更防护），保存经 `PATCH` 部分更新；保持 rule ID、启停状态与触发/冷却历史不变，成功后按当前分页刷新列表并提示，失败（如规则已被并发删除返回 404）时明确报错且不丢弃编辑内容。后端为 last-write-wins，乐观并发锁（version/etag）记为 Non-goal。
- [新功能] Web 新增股票行情工作区 `/stocks/:stockCode`：typed client 拉取实时行情与历史 K 线，行情与历史独立加载、独立失败与重试；支持日/周/月周期（周/月由日线数据在本地聚合）与 1–365 天可调，周期与天数写入 URL 并可刷新/前进后退恢复；股票代码统一 canonical 化避免 `00700`/`HK00700`/`00700.HK` 形成不同 URL、缓存键或自选项；提供加自选、分析、手工信号入口；K 线图配套可访问明细表与区间摘要，关键数据不只存在于图表 tooltip；行情如实标注为“最新可用行情 · 抓取时间”，在无法证明实时时不宣称实时。
- [改进] `portfolio_idempotency_records` 的 scope 列、唯一索引、legacy 数据规范化与 legacy 冲突 guard trigger 的 startup 兼容步骤转为正式 migration `202607190003_portfolio_idempotency_scope_schema`（稳定 ID + 源码 checksum，内联冻结 v2 storage-id 哈希，仅规范化未 scoped 的 legacy 行、不发明 owner scope，索引/触发器创建后校验，幂等）；移除运行时 `_ensure_portfolio_idempotency_scope_schema` / `_backfill_portfolio_idempotency_scopes` / `_ensure_portfolio_legacy_idempotency_guard_trigger` DDL/DML。guard trigger 作为持久数据库对象保护回退 runtime 的 legacy 冲突写入，不再依赖每次启动自愈重建。
- [改进] `decision_signals` 的 `decision_profile` 列、profile 感知索引与从 `metadata_json` 的 legacy 回填的 startup 兼容步骤转为正式 migration `202607190002_decision_signal_profile_schema`（稳定 ID + 源码 checksum，冻结的 profile 归一化，仅回填合法 profile 且不覆盖既有值，对无效/非对象/超深 JSON 安全跳过，幂等）；移除运行时 `_ensure_decision_signal_profile_schema` / `_ensure_decision_signal_profile_indexes` / `_backfill_decision_signal_profile_from_metadata` DDL/DML。
- [新功能] Web 决策信号页新增“运行后验”入口：按安全默认参数（仅 active 信号、`force=false`、单次上限 100，只补算缺失或可重试结果）触发后验引擎，需二次确认；显示运行进度、`evaluated`/`created`/`updated`/`skipped` 结果、本会话内最近运行列表和失败时的错误 trace，并通过 in-flight 守卫与禁用态防重复提交，运行完成后刷新后验统计。
- [新功能] Web 决策信号页新增“创建信号”手工创建抽屉：录入基础、交易计划与解释字段，来源固定为 `source_type=manual` / `trigger_source=web_manual` 且不可伪造；提供实时预览、客户端校验、基于规范化内容哈希的确定性 `web_manual:<hash>` trace_id 幂等去重（区分 `created=true` 新建与 `created=false` 去重命中），创建 active 方向性信号后刷新受影响视图以体现服务端相反信号失效，草稿在关闭重开、去重命中和请求失败时保留、仅创建成功后清空。
- [改进] `llm_usage` 遥测列的 startup 兼容 DDL 转为正式 migration `202607190001_llm_usage_telemetry_columns`（稳定 ID + 源码 checksum，legacy 缺列时幂等补列、fresh 库 no-op）；startup 改为在初始化写锁与同一事务内、baseline 证明之前有序应用 pending migration，使 create_all、兼容修复、迁移 DDL 与 baseline 校验保持原子且整体回滚，并移除运行时 `_ensure_llm_usage_telemetry_columns` DDL；`apply_pending` engine 入口仍供独立诊断按 migration 单独取锁提交。
- [改进] Web 新增权威 `Surface`、`Section`、`StatePanel` 与 `Alert` 契约，以 L0/L1/L2/Overlay 语义层级替代默认卡片边界；组件统一拥有 live-region / busy 语义与 compact/default Alert 密度，现有 Card、空态、加载态和 API 错误通过兼容适配器收敛，Token Usage 在加载、无数据与错误时只显示一个主状态、隐藏零值指标墙，并在跨周期请求失败时不再把旧周期数据标为当前结果；AST 守卫阻止页面重新叠加背景、边框、圆角和阴影。
- [修复] Agent Runtime 历史证据治理改为精确 fixture ID：不再按 timeout/cancelrace profile 自动扩大 conformance 例外，删除缺少双环境快照的依赖包数量结论，并将仅覆盖离线子集的 AR-PY-05 状态校准为 `Historical / Partial`；同时明确 provider-error 脱敏不能代表 prompt、reasoning、tool result、日志和其它异常失败面已完成扫描。
- [chore] Agent Runtime 完整执行 `Native Only` 裁决：删除休眠的 PydanticAI Adapter、toolset、可选依赖、内部注入点、cross-runtime 测试与专用 CI；保留 vendor-neutral Contract、Native Adapter、BoundToolSession、生命周期、事件、sanitizer 和 36 个 replay fixture，并将 API key、带凭据 URL、Bearer token 脱敏及 300 字符诊断上限迁入 Native 异常回归。
- [改进] Web 共享 `Button` 的 90 处 `xsm`/`sm`/`md`/`lg` 旧尺寸调用改用 `compact`/`default`/`comfortable`/`primary` 语义档位，并删除兼容类型和重复样式；AST 设计守卫同时阻止共享样式表、直接调用、别名及命名空间调用重新引入旧尺寸，现有 28/32/36/40px 可见高度与交互行为保持不变。
- [改进] Web 共享交互控件建立业务无关的 `Button` / `IconButton` / `Input` / `Field` / `Textarea` 权威：按钮必须显式声明 intent，普通控件使用 28/32/36/40px 可见档位与软圆角，粗指针命中区独立扩展到 44px；移除 Settings/Home/Chat 私有 Button variant、Button 图标尺寸和 29 处非必要 `size="xl"`，新增 AST 守卫阻止页面通过尺寸、圆角、宽度或 flex class 绕过公共契约；Chat 在默认策略目录请求完成前阻断 Composer、Enter 与快捷问题发送，请求失败后再降级为“通用”，避免慢环境绕过已配置的默认策略。
- [修复] PR Review 静态检查只对仍存在的新增、修改、重命名或类型变更 Python 文件运行 Flake8，删除 Python 文件的 PR 不再因不存在路径被误判为代码质量失败；已删除文件仍保留在完整 diff 与自动审查范围内。
- [修复] DecisionSignal 新增 canonical `presentation` 视图模型，以 `action` 统一动作方向，并集中提供本地化标签、置信度、摘要、风险和时间戳；API、通知、Web 卡片/详情/时间线、主报告动作卡、历史 badge 与组合风险不再分别信任可能冲突的 `action_label`、`operation_advice` 或平铺展示字段，状态 metadata 替换会保留正式语言 provenance，旧字段继续保留用于兼容。
- [修复] Web 管理员当前密码、新密码、确认密码、Provider API Key 与通用敏感配置统一使用 `CredentialInput`：稳定且相互隔离的 `name` / `autocomplete` 契约阻止管理员密码被相邻 Provider 字段误接收；首次向导和模型连接弹窗中的填充式变更只保留在本地草稿，不会自动测试连接或保存配置，并由真实首次设密浏览器流程覆盖；多值密钥输入及其显示、隐藏、删除动作提供本地化行级可访问名称。
- [修复] Web 登录页按实际传输协议显示安全状态：HTTPS 仅陈述加密传输，本机 HTTP 使用中性说明，非本机 HTTP 明确警告密码传输风险，并移除虚构的 `StockPulse-V3-TLS` 声明。
- [修复] 诊断脱敏 `sanitize_diagnostic_text` / `sanitize_sensitive_text` 现同时脱敏非 HTTP 连接串（postgresql/mysql/redis/mongodb/amqp 等）userinfo 中的凭据，此前仅覆盖 http(s)，SQLAlchemy 等连接错误可能把数据库密码泄漏进 Agent 诊断与日志；host 保留以维持诊断可读性。
- [改进] 实验性 PydanticAI 运行时的 Single RUN 模型桥补全（RF-05，AR-RF-04/05/06/10/11）：模型桥从 PydanticAI `model_request_parameters` 下发真实工具 schema（不再固定空数组），ToolCall/ToolReturn/reasoning/provider trace 跨轮无损往返，复用 `AgentExecutor.build_run_messages` 的 system/skill/dashboard prompt 权威，usage 每次调用经单一 recorder 记录并修正为 `prompt_tokens/completion_tokens`，execution deadline 与协作取消在每次调用前 fence，CHAT/RESEARCH 显式返回 `unsupported_capability`（RF-06 裁决前冻结）；仍为默认关闭、可整体删除的实验路径，Native 默认路径零 PydanticAI 依赖不变，36 replay fixture 零改。
- [改进] Agent 运行时契约改为运行中控制柄（RF-02，AR-RF-01/02）：`AgentRuntime.start()` 返回可查询状态、消费事件、请求取消并等待终态的运行中 `ExecutionHandle`（原 `execute()` 保留为启动后等待终态的兼容 helper），`ExecutionContext` 深层冻结为只读快照，调用方后续修改嵌套 dict/list/set 不再影响执行；terminal first-wins 与 36 replay fixture 逐字节不变。
- [文档] 新增《多语言金融术语指导》（`docs/financial-terminology-guide.md`）作为十语言 UI 金融术语的单一治理源：约 100 个来自真实产品的概念，含语义边界（UI/report language/用户内容/契约值）、`en`/`zh`/`zh-TW` 权威列与八语言产品译文基线、已知译文漂移清单、风险表达禁止项、格式化与审查流程；同步 `web-i18n.md`/`web-i18n_EN.md` 与 `INDEX.md` 入口。docs-only，不改运行时资源。
- [chore] Agent 各入口的终态写入 fence 统一经单一分类器 `classify_result_terminal_state`（RF-04）：单智能体 `AgentExecutor.chat`、多智能体 `AgentOrchestrator.chat` 与 SSE 端点的 `ExecutionLifecycle.finish_from_result` 现共用同一终态判定，`cancelled` 优先于 `success`，取消的对话不再可能写入成功助手消息；纯内部重构，行为逐字节不变，36 replay fixture 与 SSE 测试零改。
- [改进] Native Agent runtime 的工具调用统一改由单一 `BoundToolSession` 门禁分发（RF-03，AR-RF-03），消除绕过会话的第二套 ToolRegistry 权威：runner 每次运行构造一个 native 兼容会话（等价放行 allowlist/policy/permission，surface 跳过声明式契约校验）并在终态关闭，保持 36 个 replay fixture 逐字节不变；运行结束后迟到的工具结果（如超时 worker）经 late-result fence 丢弃，不再重新进入模型或写入成功结果。
- [测试] CI 新增 `pydanticai-installed` 独立作业与 `backend-gate` 的 native 隔离断言：安装 `requirements-pydanticai.txt` 后强制导入 `pydantic-ai-slim` 并执行实验运行时测试，`STOCKPULSE_REQUIRE_PYDANTIC_AI=1` 下依赖缺失或模块级跳过判为失败（不再以 skip 冒充通过，AR-RF-09）；默认 `backend-gate` 保持零 PydanticAI 依赖。
- [文档] 项目改为双许可证：上游原始代码保持 MIT License，StockPulse 新增与大幅修改的代码采用 AGPL-3.0；同步更新 LICENSE 与三语 README（含 badge、fork 说明与 License 章节）。
- [改进] Agent 流式对话（`/api/v1/agent/chat/stream`）在客户端断连或流提前结束时协作取消后端执行：Agent 循环在每步开始、每次 LLM 调用后与流水线各阶段边界处检查取消意图并及时停止，取消结果记为 cancelled 而非失败，不再写入"分析失败"占位助手消息，也不残留部分 provider trace；SSE 事件线经单一降级点保持逐字节不变。
- [修复] 修正新增界面语言的设置字段标题、金融告警方向、LLM 未配置提示及 Markdown/AlphaSift 产品术语翻译，并将设置导航翻译键改为稳定语义键。
- [改进] Web 共享 Button、SegmentedControl、Checkbox、Search、Badge、Notification 与侧栏 Profile 按统一 Figma 规格收敛；设置和首页标签切换、全站 checkbox、侧栏语言/主题入口、精简配置提示及路由错误页改用共享组件。
- [改进] Web 页面菜单、选择器、按钮和输入框进一步收敛到共享 Popover、Select、Button 与 Input；设置单位和调度默认值改由后端 schema 提供，持仓 CSV 导入不再伪造内置券商目录。
- [修复] Web Chat、持仓、决策信号、回测与告警页面的局部控件尺寸和空态卡片高度，避免筛选行、操作按钮和规则列表在桌面视口中过度撑大。
- [改进] Web 登录页改为极简居中卡片视觉：圆形品牌徽章、黑白反色主按钮、与工作台一致的纯色背景，移除 3D 倾斜、巨型背景图形、网格与渐变品牌字；密码认证流程、可访问性标签与 i18n 文案不变。
- [改进] 全局按钮形状从胶囊形（rounded-full）统一为软圆角（rounded-lg），设计守卫同步反转校验规则；装饰性圆点改用 --radius-dot 语义 token。
- [修复] 修复 Web 前端登录状态竞态：过期的 auth status 响应晚到时不再覆盖较新的登录状态，避免登录成功后偶发被弹回登录页。
- [修复] Web 设置多选下拉改用视口定位并在空间不足时向上展开，避免被设置分组或弹窗的 `overflow` 边界裁切；弹层在窄屏中保留 8px 安全边距。
- [修复] Web 通知路由严格按运行时完整凭据组判断可用渠道，辅助字段或半套 Telegram、邮件、飞书、Discord、Slack、Pushover、ntfy、Gotify 等配置不再误显示为可路由。
- [修复] System Config API 从当前 live `Config` 快照复用通知运行时权威计算已配置渠道，未重载的 `.env` 修改不再被误报为已生效；ntfy / Gotify 畸形 authority、userinfo、端口和 NFKC URL 关闭式判为未配置且不泄漏原值。
- [修复] Web 设置页统一保护加载、保存、冲突恢复和外部编辑刷新产生的配置快照，晚到的旧响应不再覆盖新版本，已被新快照取代的刷新失败也不再误报已提交的保存失败；滚动升级遇到旧后端缺少渠道状态时保留完整通知渠道目录和已有选择，后端明确返回空列表时仍保持关闭式过滤。
- [修复] Web 登录 `redirect` 在解析前拒绝 ASCII 控制字符、空格、DEL 与任意反斜杠，并在固定同源基准上二次校验，防止 URL 规范化绕过或登录后跳转失败。
- [修复] Web 侧栏搜索框移除误导性的 `/` 快捷键提示（此前并无全局 `/` 监听），避免暗示不存在的键盘快捷键。
- [修复] Web 登录深链不再丢失：已登录用户访问带 `?redirect=` 的 `/login`、或登录成功后，都会按 `?redirect=` 返回原页面而非首页；redirect 仅接受同源绝对路径，外部 URL、协议相对与反斜杠变体一律回退首页。
- [改进] Web 剩余按钮观感控件统一为胶囊形（设置帮助弹窗文档链接、持仓 CSV 文件选择、首页通知勾选 chip），与全站按钮形状规范一致。
- [修复] Web 页面容器与回测页不再在应用外壳的 `main` 地标内嵌套第二个 `main`，回测页补充屏幕阅读器可见的 h1 标题，页面地标语义唯一。
- [修复] Web 设置页文本/路径类输入框改为填满 240px 控件列，数值输入保持紧凑宽度，日志目录等长值不再被裁切到约 170px。
- [修复] Web 设置页定时任务启用改为统一开关控件，定时时间改用共享时间选择器；“添加时间”直接展开小时/分钟面板、确认后才保存，并在展示层去重已有时间。新增共享日期选择器并替换回测、持仓页的原生日期控件，统一月历弹层、键盘输入和表单行为。
- [修复] Web 设置页与模型渠道编辑器的密码类输入框统一包裹在 `form` 中，消除浏览器关于表单外密码框的告警。
- [修复] 首页侧栏「历史/自选/今日」标签栏统一到共享容器中，切换视图时标签栏不再位移；标签栏改为标准 tablist/tab 语义并支持方向键与 Home/End 键切换。
- [改进] Web 设置页多选类字段（大盘复盘市场、通知路由渠道等）从平铺 checkbox 改为下拉多选控件，支持搜索、已选摘要与未知存量值保留。
- [改进] Web 通知路由（报告/告警/系统错误渠道）下拉选项只展示已配置成功的通知渠道；未配置任何渠道时展示空态引导并可一键跳转渠道配置。
- [改进] `REALTIME_SOURCE_PRIORITY` 改为保序多选下拉：按选择顺序决定数据源优先级，后端 Schema 提供候选项但不强制 allowed_values，历史别名与自定义源继续兼容。
- [测试] 新增 Agent Runtime characterization 回放数据集与兼容性门禁：36 个 fixture（24 个 A/HK/US 财务场景 + 12 个 ModelRef/fallback/工具范围/超时/取消竞态/畸形输出契约场景）经严格 transcript 回放冻结当前 Native runtime 行为，`tests/test_agent_runtime_compatibility.py` 校验回放期望、manifest 覆盖矩阵与工厂契约（模型路由不可变、数值回退、ToolRegistry 共享、SkillManager 克隆与失效、`build_executor` 别名、Risk(Intel) 输入契约）。
- [新功能] Web 界面新增繁体中文、日语、韩语、德语、西班牙语、马来语、法语和印尼语完整翻译资源与十语言选择器，并同步浏览器语言识别、持久化、HTML language、Intl 格式化及全语言完整性校验。
- [新功能] 增加有序数据库 Migration Runner，以稳定 ID、SHA-256 checksum、单迁移事务和 SQLite 写锁统一 Fresh/历史数据库升级，并补齐 Desktop、Docker 与 Actions 的资源发现和导入校验。
- [修复] Migration Runner 以固定 v3.0.0/v3.4.0/v3.20.0 release profile 兼容无 registry 历史数据库并保留数据；`status`/`verify` 改为 SQLite 强制只读诊断，不再在检查前修改 Schema 或应用 pending migration。
- [改进] Migration Runner 只向 upgrade 提供受限且仅在同步调用期间有效的 SQL execution capability；返回或抛错时先拒绝新调用和排队调用，等待已进入 driver path 的语句在同一事务内完成并物化结果后再撤销连接租约；语句失败与禁用能力请求使用不可清除 latch，migration 捕获异常也不能提交；`execute` 只接受精确 `sqlalchemy.text()` 的单次 SQL 快照，`exec_driver_sql` 只接受内建字符串，任意 executable、实例覆写回调和并发 statement mutation 都不能获得真实 Connection；事务控制 SQL（含注释、空语句或 BOM 前缀）在进入 Connection 前 fail closed，调用方 SQLite authorizer 保持不变，DDL/DML 与 applied row 仍由 runner 独占同一事务，source guard、随机 savepoint 与 transaction 状态检查保留为纵深防御而非 Python 安全沙箱。
- [修复] Migration Runner 递归拒绝 coroutine/generator/async-generator、context-manager wrapper 和循环 upgrade callable，并要求运行时严格返回 `None`；非法返回会关闭可同步关闭的 coroutine/generator 并回滚 DDL/DML，避免未完整执行的 migration 被错误记录为 applied 或产生未 await warning。
- [测试] Docker CI 将受支持的 legacy SQLite fixture 作为 `/app/data` volume 启动真实 `DatabaseManager`，校验业务 canary、migration checksum 和 target version，并复用同一 volume 二次启动验证幂等。
- [修复] Web 可搜索选择器在移动端底部弹窗中会根据可用空间向上展开并限制在视口内，避免模型服务选择列表超出屏幕后无法操作。
- [改进] Web 共享控件、导航、设置、任务、自选股、Chat、报告、Run Flow、告警、决策信号、回测、持仓、选股与 Token Usage 的交互目标统一提供至少 44px 触控命中区，页面高度改用动态视口单位，报告二级标题统一使用 28px 设计 token，提升移动端可达性与版式一致性。
- [修复] Agent runtime 对被多个 Connection 共享的 legacy 裸模型路由改为 fail-closed，并返回 `ambiguous_legacy_model_route` 要求显式选择 Connection-aware ModelRef，避免把其它 Connection 的部署来源误判为当前路由可用。
- [修复] Agent 与 Bot 失败边界不再向用户或会话历史返回 Provider 原始错误；新失败持久化稳定 sentinel，历史 API 以安全 `content` 和 `error + params` 返回并兼容旧 `[分析失败]` 记录，Web 按当前界面语言统一渲染、复制和导出失败消息；Native Tool handler 与未知工具失败使用稳定错误码，内置 Agent 工具的 Portfolio、基本面、资金流与搜索下游失败使用稳定状态、诊断码或公开文案，模型、Single provider trace 与日志均不再包含原始异常详情；SearchService provider 失败日志只保留 provider、HTTP status、error count 与稳定 error code 等有界字段，不再输出 response body、response keys、私有 endpoint 或 API Key 前缀，Tavily / SerpAPI SDK error payload 在成功记账前转为稳定失败。
- [修复] Web 异步分析仅在 409 envelope 的 `error` 为 `duplicate_task` 时构造重复任务错误，其它分析冲突与大盘复盘 409 统一走共享错误解析，并完整保留 `params`、`details` 和 `trace_id` 诊断元数据。
- [修复] Web 用户可见文案与通知测试默认文案中的旧 DSA 品牌统一为 StockPulse；环境变量、API 字段、协议标识、内部模块名和历史载荷中的兼容标识保持不变。
- [测试] ReportMarkdown 四种 UI/report language 组合改用可控延迟请求验证 loading→content 转换，正文与复制控件断言等待真实加载完成信号，避免 CI 资源压力下把已挂载的 disabled 按钮误当成正文就绪。
- [修复] System Config GET 默认遮罩所有 Schema 敏感字段；模型 Connection 的 `API_KEY` / `API_KEYS` / `EXTRA_HEADERS` 遮罩或省略复用增加身份作用域校验，只有 Connection 名称、Provider、协议和 Base URL 未改变时才保留原凭据，动态附加请求头必须是 JSON 对象，切换身份或端点时必须重新输入或明确清空。
- [修复] API、Agent、Bot、System Config、Backtest、图片提取与 AlphaSift 的异常日志统一通过共享安全入口记录：保留 trace ID、稳定错误码和异常类型，同时递归移除凭据、Authorization/Cookie、URL query token 与私有端点，限制诊断长度且不再附带原始 traceback；静态守卫在原始日志 sink 对无注解或异常类参数执行 fail-closed 校验，覆盖同步/异步函数、方法、闭包、别名与提前渲染路径，只有可信 sanitizer 处理后的诊断文本和已证明为普通结构化值的参数可进入日志；未知下游异常仍返回安全的结构化 500，预期校验错误保留明确的 4xx 语义。
- [修复] 全局 422 请求校验 envelope 删除 Pydantic `input` 与异常上下文，只保留安全的字段位置、类型和通用文案，避免登录或配置请求中的 password/API key 被响应与浏览器 trace 复制。
- [测试] 语义 Playwright 的敏感配置播种改用测试进程直接请求；credential-bearing CI 关闭 screenshot、video 和 trace，只保留文本 service logs 与 JSON reporter，并显式关闭 commit 与 PR diff 元数据采集。仓库 smoke 入口拒绝 UI/替代 config，global setup 在 CLI/project 合并后逐 project 校验最终 trace，静态 preflight 覆盖相对 import、`test.use` option 后赋值、`Object.fromEntries` 与 BrowserContext tracing 常见入口；本地无凭据调试仍可显式 opt in 无媒体 trace。CI 先严格扫描原始文本、日志、HAR、意外 trace/ZIP 条目与原始二进制 canary，再以专用脚本校验 JSON、递归文本日志、符号链接、allowlist 和 archive/media magic，生成 SHA-256 manifest 后二次扫描 staging；只有 raw scan、staging 与 staged scan 全部成功才上传安全 JSON/文本诊断。新增独立真实登录故意失败 harness，验证非零退出、JSON failure、服务日志、无 trace/media 及双重扫描，临时 spec 不进入正式 suite。
- [改进] Web 配置备份入口从普通“系统与安全”页移入“高级”，保留原有 `.env` 导入导出、鉴权和冲突保护契约，避免普通设置路径暴露内部部署细节。
- [修复] Portfolio 交易、资金流水、公司行为和 CSV 提交的持久化 operation ID 按操作类型、账户、owner 与客户端 key 隔离；默认 7 天 replay window 内同 payload 回放首次响应、异 payload 稳定冲突，窗口外记录在既有写事务中原子惰性清理且不影响 ledger 数据；旧 SQLite 表采用 additive migration，无法证明历史 owner 的 raw-key 行保持 unscoped，legacy 写入保护 trigger 在代码回滚期间阻止 v2 key 重复入账，并保证再次升级不发生索引冲突。Web 重试继续复用 ID、提交中锁定表单与关闭行为，并将 320px 表单改为单列。
- [改进] Provider Catalog 补充获取凭据、控制台、模型列表与官方文档地址，Web 模型接入和首次向导统一消费后端元数据；快捷链接仅接受不含内嵌用户名或密码的 HTTPS URL，并在规范化后去重，删除按 Provider ID 维护的前端业务外链表。
- [修复] 配置 Schema API 完整透传字段条件契约；Web 对 AI 字段缺失/未知 `uiPlacement` 统一隔离到“高级”只读诊断，对未知条件保持可见但锁定，避免旧 Schema 或滚动部署重新暴露第二套普通编辑入口。
- [改进] Web-facing API 错误统一为稳定 `error/message/params/details/trace_id` envelope，并在弃用窗口内以只读 legacy `detail` 同值别名兼容旧消费者；5xx 两字段都只携带相同安全结构或 `null`。前端优先读取 `details` 并兼容任意 JSON 形态的旧 `detail`，按 UI language 映射主错误并保留安全诊断；任务 POST、SSE 与轮询载荷补齐 `message_code/message_params`，切换语言时已有任务即时重渲染，断线恢复按 task ID 去重合并。
- [chore] GitHub workflows、Issue/PR 模板、自动审查、step summary、bot 评论与自动 Release notes 统一使用英文；动态输出拒绝非英文字母脚本和 HTML 字符实体，并转义非 ASCII / `&` 路径与诊断，手动 Docker 发布 tag 使用 ASCII 格式校验与安全环境变量传递；CODEOWNERS、发布链接和桌面端更新目标切换到 SiinXu/stock-pulse-ai。
- [修复] 移除上游 AIHubMix referral `APP-Code` 自动注入及 Anspire/AIHubMix/SerpAPI 推荐参数和优惠宣称；用户显式配置的自定义 headers 保持不变。
- [改进] Workflow、邮件默认发件人、HTTP User-Agent、Web fallback 标题与 OpenAPI 标题统一使用 StockPulse；部署、桌面发布校验和远程股票索引切换到当前仓库。
- [文档] Docker 指南不再把上游或尚未发布的镜像描述为 StockPulse 官方产物，并移除未启用的 Discussions 入口。
- [测试] 新增 GitHub 协作资产英文守卫，并要求 PR 自动标签与审查报告通过分页 API 统计全部变更文件，避免大型 PR 只报告前 30 个文件。
- [测试] SettingsPage 调度器运行态回填测试在两个状态方向都等待异步 API 响应，避免 CI 高负载下在运行态同步完成前提前断言。
- [文档] 三语 README 将 StockPulse 明确为 ZhuLinsen/daily_stock_analysis 的 MIT License 独立维护 fork，并将当前仓库、CI、文档与反馈入口切换到 SiinXu/stock-pulse-ai。
- [改进] StockPulse Web 补齐 Chat、Screening、Alerts、Portfolio、Settings、公共选择器、股票搜索和报告外围诊断的中英文界面，并将 UI language、report language 与动态原文边界分离。
- [改进] Web 翻译按 alerts、portfolio、screening、settings、stock search、report chrome 等领域拆分为 typed locale 文件，便于后续扩展更多语言，避免单一字典持续膨胀。
- [测试] 新增字典 key/空值/插值/重复项一致性、生产 TSX 中英文硬编码文案守卫及 30 项 Playwright i18n 验收；硬编码扫描扩展到 JSX 表达式、`aria-description`、`alt`、`label`、`message` 等用户可见语境，并要求 allowlist 精确到文件、字符串、语境和用途且仍被实际使用；CI `web-gate` 显式执行 i18n 门禁。
- [文档] 新增中英文 Web 国际化开发约定，说明界面/报告语言边界、动态内容、错误码、locale-aware 格式化和验证命令。
- [修复] 登录页品牌标题统一为可访问的 `StockPulse`，隔离 Playwright 登录 smoke 不再依赖旧 `DAILY STOCK / Analysis Engine` 文案。
- [修复] 模型连接新增显式 `LLM_<CONNECTION>_PROVIDER` 身份契约，Provider 与可重命名的 Connection 名称分离；同一 Provider 多连接、重命名连接、Available Models 的 Provider/Connection 元数据、旧配置精确匹配兼容与 GitHub Actions 变量透传保持一致，不再按 `openai2` 等名称前缀猜测。
- [修复] 删除仍被报告、Agent、Vision 或 fallback 引用的单个模型时，Web 模型管理弹窗列出全部引用并支持在统一草稿中选择替代模型，后端以结构化 `model_in_use/details.referenced_by` 阻止 API 绕过；替换引用与删除可在同一事务原子成功，历史失效值仍保留并标记不可用。
- [改进] Provider Catalog 成为 Provider 身份、双语标签、默认端点、协议、发现能力与本地/自定义属性的唯一元数据来源；同一 API 返回的 `connection_fields` Schema 成为动态 Connection required/visible/enabled 与可写字段集合的唯一权威来源。该属性存在时（包括显式 `[]`）不读取 Catalog 的 legacy requirement flags，仅在旧后端完全省略属性时启用隔离的 rolling-upgrade fallback；只有完整包含 `connection_name`/`display_name`/`provider_id`/`protocol`/`base_url`/`api_key`/`api_keys`/`models`/`extra_headers`/`enabled` 的 Schema 才可启用写入，identity-only/partial Schema 与未知且当前可见必填的字段统一进入只读保护并阻断测试、草稿、自动保存与保存；AND 中任一未知 operator 优先于更早的未满足条件，字段保持可见、只读、诊断并阻止保存。显式空 `display_name` 由前后端一致拒绝，仅兼容完全省略该字段的旧配置；内置 Provider 提供 `label_zh`/`label_en`，旧 `label`/`is_required` 仅为 deprecated 兼容输出；Ollama 使用 `/api/tags` 空 Key 发现，模型多选收起为可搜索 listbox。
- [测试] Playwright 使用隔离 `.env`、SQLite、密码哈希与 session secret，启动时确定性播种 Markdown 报告，结束后清理 runtime，并保留后端/Vite/fake-provider 服务日志；登录 smoke 按当前 StockPulse 首次设密/登录流程执行，不再依赖开发者状态或整套 skip。
- [文档] 中英文贡献指南、模型配置指南、Provider 指南、设置帮助与 `.env.example` 同步 Provider/Connection/Model/Task Assignment、多连接、发现、stale 值保留和 E2E 隔离语义；设置路径统一为「AI 与模型 → 模型接入」。
- [改进] Web 设置页任务模型（报告/Agent/Vision）与备用模型添加控件改为严格列表选择器（`SearchableSelect`，listbox 语义、支持搜索/键盘/读屏）：仅可从后端可用模型目录选择，删除自由输入组件 `CreatableCombobox`；目录外已存值标注「当前配置不可用」，空值显示占位提示而非误报不可用。
- [改进] 后端配置 Schema 新增 `ui_placement` 标记（model_access/task_routing/developer_diagnostics/hidden_legacy）作为字段 UI 归属唯一权威源：Web 通用分类视图按该标记排除专属界面字段与隐藏 legacy Provider 字段，删除前端手写的 legacy Provider 分组名单（`LEGACY_MODEL_PROVIDER_GROUP_IDS`）；不改配置保存/读取契约。
- [改进] Web 设置页普通路径术语与设计收敛：运行时注入密钥的提示不再引用 `.env`/内部变量名，模型备用顺序说明去除内部实现名词；设置面与基础控件清理魔法字号/圆角（`text-[11px]`→`text-xs`、`rounded-[10px]`→`rounded-lg`、`rounded-[6px]`→`rounded-md`）。
- [改进] Web 的 Modal、Drawer、ConfirmDialog、Settings Help 与移动历史面板统一使用 Overlay stack：只允许顶层响应 Escape/Tab，背景 inert、引用计数滚动锁定、打开聚焦和关闭焦点恢复行为一致，Confirm 层级高于 Drawer/Modal，Home/Chat/Help 不再保留自制 Overlay 状态机。
- [改进] Home 以 query 参数作为报告与 Run Flow 对象真源：`recordId`、task/history flow 深链支持刷新、分享与 Back/Forward 恢复，关闭 Drawer 只移除对应 flow 参数；非法/失效参数使用 replace 规范化，快速切换采用 latest-request-wins 且保留无关参数。
- [chore] CI `web-gate` 阻断执行 lint、i18n、Vitest 与 build，关联 API/配置/服务改动同时触发 `web-e2e`；Playwright 使用隔离的真实后端、Vite、fake provider 与确定性数据，Python 按祖先 `.venv`→`python3`→`python` 查找并打印诊断，固定 `retries: 0`；含凭据 canary 的运行禁用 trace，只保留扫描通过的文本日志与 JSON 结果 7 天，PR 页面截图改由不含凭据的独立证据提供。
- [文档] 补充前端开发代理变量 `DSA_WEB_DEV_API_PROXY` 到 `.env.example` 与贡献指南；修正本段中「模型供应商面板/高级视图」删除与保留的矛盾描述，统一为最终四视图状态；LLM 配置指南（中英）的旧术语统一为「设置 → AI 与模型 → 模型接入」。
- [改进] Web 设置页「AI 与模型」收敛为 总览/模型接入/任务路由/可靠性 四个视图：删除「高级」二级视图与遗留「模型供应商」子页映射，legacy Provider 凭据键保持后端（env/YAML）兼容但不再形成 Web 第二编辑入口；模型接入页只展示紧凑连接卡片，内部配置来源、生成后端、CLI 与冒烟测试统一移入顶层「高级 → 开发者诊断」并默认折叠。
- [改进] Web 设置页模型输入全面改为选择器交互：新增 `ModelMultiSelect` 多选组件，连接编辑器「发现的模型」改为搜索并勾选启用；手动添加模型改为每次回车/点击添加一项，粘贴逗号/空白分隔列表自动拆分去重；模型下拉搜索同时匹配显示名/模型路由/所属连接/服务商；可靠性页备用模型列表支持上移/下移排序，目录外的已配置路由保留并标注「当前配置不可用」而不静默清除。
- [修复] 首次配置向导对 Ollama 等免密钥服务的首次配置不再受阻：API 密钥按后端 `connection_fields` Schema 标注「（可选）/可留空」；「自动发现模型」结果不再整批自动启用，改为展示候选列表由用户勾选确认；手动输入逐项添加并兼容粘贴逗号分隔列表。
- [改进] 模型接入术语与文案降低理解成本：统一「主要模型 / 备用模型 / 服务地址 / API 密钥」用语，连接编辑器表单示例从 `KEY=value` 环境变量形式改为纯值示例（如 `https://api.deepseek.com`、`sk-xxxx`），中英文界面与帮助文案术语对齐（model connections）。
- [改进] Web 设置页多值枚举字段（`NOTIFICATION_REPORT_CHANNELS`/`NOTIFICATION_ALERT_CHANNELS`/`NOTIFICATION_SYSTEM_ERROR_CHANNELS`、`MARKET_REVIEW_REGION`）渲染为勾选组，不再要求手输逗号分隔字符串；目录外的已存值保持可见、可取消，保存不静默丢弃；未显式设置的字段回填后端默认值展示（密码控件除外）；后端注册表为上述字段标注 `multi_value` 并修正英文描述措辞。
- [改进] 后端配置保存校验补齐 Vision 模型引用保护：当本次更新触及渠道结构（删除/停用连接、修改 `LLM_CHANNELS` 或渠道键）导致 `VISION_MODEL` 指向已启用连接中不存在的模型时，保存被拒绝（`unknown_model`），与主模型/备用模型引用保护一致；历史失效的 Vision 引用仍不阻断无关配置保存。
- [新功能] 大盘复盘报告页接入市场结构上下文卡片：持久化报告包含市场结构字段时，在复盘报告视图渲染题材主线与个股位置（`MarketStructureCard`），旧报告无该字段时静默跳过。
- [改进] Web 设计守卫扫描全部生产 CSS/TSX，阻断非胶囊按钮覆盖、`primary`/`settings-primary`/`action-primary`/`gradient` CTA 经共享样式、别名、静态拼接、JSX spread 或内联样式引入的渐变/shimmer，以及组件内 hardcoded hex/颜色函数、魔法像素字号/尺寸/圆角和原始 `100vh`；独立 fixture 覆盖每类规则，Login 与 Settings 主操作统一复用共享黑白反色 solid primary 样式，原生按钮由全局胶囊基线兜底，且不牺牲 44px 触控目标或可访问 focus ring。`ParticleBackground` 通过单个实时 `CSSStyleDeclaration` 在 Light/Dark 切换后读取当前 Canvas token，`ScoreGauge` 保留既有类型与三层 SVG 结构并将 glow 样式归零。后端本轮触及的开发日志同步改为英文。
- [文档] 修正模型接入相关文档与帮助文案的矛盾与过时描述：UI 路径统一为「设置 → AI 与模型 → 模型接入」（FAQ、LLM 配置指南、设置帮助、文档索引，中英文同步）；历史失效模型引用明确保留并标记不可用，删除在用模型由 `model_in_use` 阻断；market-support 中 `MARKET_REVIEW_REGION` 的「文本框输入逗号分隔」描述更新为勾选组现状。
- [改进] 后端 Provider Catalog（`src/llm/provider_catalog.py`）不再写死具体模型 ID：移除 `placeholder_models` 字段，保留 provider id/label/protocol/默认端点/发现能力/capabilities/本地或自定义属性；`requires_api_key`/`requires_base_url` 仅作为旧后端 compatibility fallback，不在 `connection_fields` 存在时参与字段规则。新建连接不再用示例模型预填，也不会把示例模型写入运行时/fallback/任务模型；模型改由“获取模型”发现或逐项手动添加，没有模型时连接保持“未完成”。首次配置向导的模型输入同步改为 token-list（发现多选 + 手动逐项添加），不再是逗号输入框；旧的逗号模型配置读取时解析为 token。
- [修复] 修复全量测试在本地开发 `.env` 存在时的模型与认证状态污染：`litellm` 在 import 时 `load_dotenv()` 会把开发者 `.env` 的 `LITELLM_FALLBACK_MODELS` 等 LLM 变量注入 `os.environ`，导致 System Config 校验测试仅在整套运行时因环境泄漏而失败（单文件运行通过）。新增 `tests/_llm_env_isolation.py`，在 `SystemConfigServiceTestCase`/`SystemConfigApiTestCase` 的 `setUp` 隔离 ambient LLM 环境变量并在 `tearDown` 还原；Auth API 与 ConfigManager 测试恢复原 `ENV_FILE`/`DATABASE_PATH`，Intelligence/Usage API 测试显式隔离认证状态，避免开发配置 `ADMIN_AUTH_ENABLED=true` 造成无关 401（不弱化断言、不跳过、不固定顺序）；新增 `tests/test_provider_catalog.py` 覆盖“无具体模型硬编码 / 返回数据不可被调用方污染 / catalog 使用后不影响后续配置校验”回归。仅剩 3 个与模型接入无关、单独运行也失败的既有 `test_decision_signal_service` 时序相关基线用例。
- [改进] Web 设置页「AI 与模型 → 模型接入」收敛为唯一的模型服务/连接/模型配置入口：主页只保留标题、一个「添加模型服务」主操作、紧凑连接卡片与空状态；添加、编辑和模型管理统一使用同一个 Modal（390px 下为底部面板），服务商选择、凭据、模型发现/多选与手动 token 添加不再平铺到主页；同一服务商可创建多条连接，底层存储格式与 YAML/Legacy 兼容不变。
- [改进] Web 设置页删除 AI 与模型「高级」下的独立「模型供应商」面板（`ModelProvidersPanel`）与前端 `modelProviders.ts` 映射：Provider 凭据/端点/模型不再有第二套编辑入口，模型服务商元数据统一来自后端 Provider Catalog（AI 与模型的「高级」二级视图随后在本轮收敛中整体移除，最终态见上文四视图条目）。
- [改进] Web 设置页任务模型选择（报告/Agent/Vision）改为真正的 `SearchableSelect`，仅可从后端可用模型目录中选择；无可用模型时不渲染空选择框，改为统一空状态与单一「前往模型接入」操作；可用模型目录加载失败时展示错误与重试，历史失效值继续保留并标注「当前配置不可用」。
- [改进] 后端 LLM 渠道校验的已知服务商列表由 `KNOWN_LLM_PROVIDER_CHANNEL_NAMES` 硬编码改为从 Provider Catalog 派生（单一权威源）；可用模型 API 每条模型补充 `provider_id/provider_label/connection_id/available` 字段，供 Web 选择器按服务商/连接分组而无需第二套前端清单。删除被引用连接会因任务模型引用失效被后端校验拒绝（`unknown_model`，直接调用 API 也无法绕过），需先改选替代模型再保存。
- [测试] `test_daily_analysis_workflow_llm_env` 的服务商渠道清单来源由已收敛为纯展示层的前端 `llmProviderTemplates.ts`（不再声明 channelId/baseUrl）改为后端 Provider Catalog，使「每日分析 workflow env 与 `.env.example` 覆盖全部服务商渠道」的静态校验回到单一权威源。
- [改进] Web 设置页 LLM 渠道编辑器的服务商业务元数据（标签、默认 Base URL、协议、示例模型、能力标签、是否已知服务商）改为统一从后端服务商目录（`GET /system/config/llm/providers`，经 useProviderCatalog）读取，删除前端并行维护的 `LLM_PROVIDER_TEMPLATES` 业务清单；仅保留能力显示文案、协议级占位与各服务商文档链接/配置提示等纯展示内容。前端不再维护第二套服务商业务源。
- [改进] Web 设置页字段帮助弹窗新增「当前取值来源」说明：依据后端权威的 `raw_value_exists` 标识，明确该字段是「已显式设置」还是「未显式设置、使用内置默认值」（并展示默认值，敏感字段不展示），无内置默认值时提示「未设置」，帮助用户判断当前值来自显式配置还是默认回退。为字段帮助层展示，不改后端。
- [新功能] Web 问股页支持中止生成：流式回复进行中时，发送按钮变为「停止生成」，点击立即中止当前请求并恢复输入框，已发出的用户消息与历史对话不受影响。
- [修复] Web 问股页消息输入框在中文/日文等输入法组词过程中按 Enter 选词不再误发送消息：仅当不处于输入法组字状态（`isComposing`）且未按 Shift 时 Enter 才提交，Shift+Enter 仍为换行。
- [新功能] 后端新增模型服务 Provider 权威目录 `GET /api/v1/system/config/llm/providers`（label/protocol/默认端点/凭据与 Base URL 是否必填/发现能力/capabilities），凭据与端点必填规则由既有渠道完整性契约推导，Web 前端统一消费该目录、不再维护第二套业务规则；首次配置向导改由该目录驱动服务商列表与必填校验（Gemini/Anthropic 免 Base URL、Ollama 免 Key、自定义端点必填 Base URL 就地拦截）。
- [新功能] 后端可用模型目录 `GET /api/v1/system/config/llm/available-models` 使用 connection-aware `ModelRef`（`connection_id + runtime_route`）区分多 Connection 同名模型；报告/Agent/Vision/fallback 保存并解析到具体 Connection。legacy 裸 route 唯一匹配时兼容，多重匹配返回 `ambiguous_model_route` 要求确认；删除、停用和替换引用按 ModelRef 精确处理，不影响另一 Connection 的同名模型。
- [改进] Web 设置页 AI 与模型「总览」任务矩阵的生效状态改为权威判定，不再以模型字符串非空猜测：任务主模型被某个已启用连接声明为可用路由时才显示「生效」，已设置但当前配置不可路由显示「当前配置不可用」，未设置显示「待配置」；本地 CLI 后端按自身可用判定。可用路由集来自 `GET /api/v1/system/config/llm/available-models`，与保存校验一致。
- [改进] Web 设置页字段控件与数据语义对齐：任何带有限枚举 `options` 的字段一律渲染下拉选择（不再因 `ui_control` 提示退化为自由文本框）；普通字段正文不再内联渲染 `schema.docs` 外部文档链接与 `KEY=value` 示例，这些改由字段帮助弹窗提供，普通路径保持无环境变量/配置指南干扰。
- [修复] Web 设置页首次配置向导保存的配置无法通过后端校验：主模型 `LITELLM_MODEL` 现写入包含 Connection 身份与规范运行路由的 ModelRef，不再保存被后端拒绝的裸模型名，也不会因同名模型来自不同 Connection 而丢失身份；Gemini/Anthropic 官方端点不再强制填写 Base URL（走 SDK 默认端点），Ollama 等本地运行时不再强制 API Key；新建连接合并进已有 `LLM_CHANNELS` 而不是整体覆盖；显式写入 `LLM_CONFIG_MODE=channels` 确保配置的渠道生效、不被 YAML/Legacy 静默覆盖；保存失败时错误在向导内当前步骤展示并保留草稿；摘要页只展示"执行方式/模型服务/可用模型/报告主模型"等用户文案，不再显示 `LLM_CHANNELS`、`API_KEY` 等内部 key。新增真实后端契约测试覆盖上述路径（裸模型名被拒、ModelRef 通过、Gemini 空 Base URL、Ollama 免 Key、合并已有渠道）。
- [新功能] Web 设置页新增首次配置向导：在「概览」点击「启动向导」即可分步完成最小可运行配置——选择云 API 或本机 CLI；云 API 下选服务商、填写必要凭据、获取模型候选并由用户多选确认（不再预填或自动全选示例模型），也可逐项手动添加；最后统一「保存并应用」。达到最低可运行配置即可完成，不强制配置通知或高级项；移动端 390×844 全流程可用。
- [改进] Web 设置页顶层「高级」section 按字段 placement 聚合内部/底层配置，并将配置来源、执行后端选择与调优、CLI 状态、冒烟测试等全部收进默认折叠的「开发者诊断」；这些字段不再出现在模型接入、任务路由或可靠性普通路径。
- [改进] Web 设置页移动端（窄屏）用紧凑下拉选择一级 section 后，焦点自动移入内容区并滚动到所选 section，便于屏幕阅读器播报与继续操作；桌面端点击侧栏不受影响。
- [新功能] Web 设置页标注需重启生效的配置：字段 schema 带 `restart_required` 时在字段旁显示"重启生效"徽章；当已修改的草稿中包含此类字段时，内容区顶部提示"部分已修改的配置需要重启服务后才会生效"，避免用户以为保存即时生效。
- [新功能] Web 设置页新增页面级校验错误摘要：任一 section 存在校验错误时，内容区顶部列出所有出错字段及原因，点击可跨 section 跳转到该字段所属的 section/view 并自动聚焦、滚动到该字段，出错字段即使不在当前打开的 section 也能一键定位修正。
- [改进] Web 设置页按字段级 placement 拆分共享后端分类的 section：报告（Reports）只展示报告输出（格式/语言/模板/渲染/完整性），告警与自动化（Alerts）只展示推送路由/频控/静默/摘要等投递规则，二者不再同时列出全部 notification 非渠道字段；对话（Conversation）独占 Agent 上下文压缩字段（`AGENT_CONTEXT_*`），Agent 行为不再重复展示；事件监控（`AGENT_EVENT_*`）从 Agent 行为迁移到告警与自动化下的独立「事件监控」卡片（跨后端 category 呈现）。section 状态徽章改由同一 placement 归属，报告/对话/事件监控可获得与告警/Agent 行为独立的错误/未保存徽章。该拆分为 Web 呈现层，不改后端 category。
- [改进] Web 设置页「AI 与模型」模型配置收敛为唯一入口：连接视图的渠道编辑器不再内嵌运行时主模型/Agent 主模型/Vision/备用模型/Temperature 选择，这些运行时路由改由任务路由视图（报告/Agent/Vision 主模型与 Temperature）与可靠性视图（模型备用顺序）各自独占编辑；任务路由视图对备用模型顺序只读展示并提供“前往可靠性设置”跳转，避免同一键出现多个编辑入口。渠道编辑器在连接视图不再向草稿写入运行时键，字段值统一由任务路由/可靠性视图经统一草稿提交。
- [新功能] Web 设置页「AI 与模型」新增总览与任务路由视图：总览以任务矩阵展示 股票报告/大盘复盘/问股·Agent/Vision 各任务当前的执行方式、主模型（大盘复盘、Agent、Vision 未单独配置时继承报告主模型并标注）、备用模型与生效状态，用户无需查看环境变量即可判断实际生效路径；任务路由视图集中编辑 报告/Agent/Vision 主模型与备用模型顺序。总览与任务路由视图下不再展示渠道编辑器与原始字段列表。
- [改进] Web 设置页导航重构为两级信息架构（section/view）：一级 section（概览 / AI 与模型 / 数据源 / Agent 行为 / 对话 / 报告 / 告警与自动化 / 通知 / 回测 / 系统与安全 / 高级），AI 与模型下含 总览/连接/任务路由/可靠性 二级视图（引入时含「高级」视图，随后在本轮收敛中移除，见上文四视图条目）；桌面为一级侧栏 + 内容区二级 tab，移动端为紧凑横向滚动。URL 改用 `?section=&view=` 并对旧 `?category=&sub=` 深链做 replace 迁移，返回/刷新/深链稳定；侧栏 badge 只表达错误/未保存状态，不再显示字段数量。该重排为 Web 映射层，不改动后端 category、Desktop 或旧 API 消费方；移除旧 `SettingsCategoryNav`，不再维护双导航。
- [新功能] Web 设置页普通配置改为 700ms 分组自动保存并移除全局 Save：后端 category 分组串行提交，Connection、任务路由与 fallback 共享 `ai_model` 原子组；每组显示 scheduled/saving/saved/failed/conflicted，失败保留草稿并可重试或恢复服务器值，409 使用 `base/server/local` 冲突视图，Reset 只作用当前组，保存中或未恢复失败会拦截离开，masked secret 仅实际修改时提交。连接测试与模型发现仍为显式诊断动作，不由自动保存触发。
- [新功能] 配置字段 Schema 引入条件契约（`contract.visibleWhen/enabledWhen/requiredWhen/requirement`，仅 AND、未知 operator fail-safe 保持可见）：后端注册表输出 `contract`、提供 `evaluate_config_conditions`，并按契约执行权威必填校验（隐藏字段不参与校验，`requirement=required` 或 `requiredWhen` 满足时必填、为空则拒绝保存）；Web 依据 `visibleWhen` 隐藏不适用字段、依据 `enabledWhen` 只读、并显示必填/选填/继承徽章，对未保存草稿实时生效。保留 `is_required` 兼容输出。
- [新功能] 新增 `LLM_CONFIG_MODE=auto|channels|yaml|legacy` 显式模型配置来源模式并保留既有优先级与迁移 API；Web 模型接入在外部配置生效时仅显示简洁只读提示与「查看详情」，具体来源、覆盖关系和 Legacy 迁移只在顶层「高级 → 开发者诊断」中按需展开。
- [改进] 后端配置校验对 LLM 渠道增加与前端一致的结构完整性权威门禁：启用渠道必须具备凭据（Ollama/本地端点免）、Base URL（官方 provider 免、自定义端点必填）和至少一个模型，直接调用配置 API 也无法绕过；仅对本次更新涉及、或由停用切为启用的渠道执行严格校验，历史不完整渠道不会阻断无关设置保存；校验失败时整个更新事务失败、不部分落库；已保存并被 mask 的密钥不会被误判为缺失；YAML 模式仍豁免。
- [改进] Web 设置页模型连接完整性门禁与后端契约对齐：启用连接必须具备合法名称、必要凭据、必要服务地址和至少一个模型；Ollama 及后端允许的 localhost OpenAI-compatible 地址可免 Key；未启用连接可保存为未完成草稿，连通性测试不作为保存硬门禁。
- [改进] Web 设置页模型连接卡片改进可访问性：编辑与模型区域打开同一 Modal，菜单和开关不再嵌套交互；删除连接先弹确认，被报告/Agent/Vision/备用模型引用时由后端权威阻断并提供任务路由入口。
- [改进] Web 设置页生成后端状态面板的草稿预览请求改为 debounce，并整体移入顶层「高级 → 开发者诊断」默认折叠区，普通模型接入首屏不再展示运行态诊断。
- [改进] Web 设置页当前分类/子标签同步到 URL（`?category=&sub=`），支持深链直达具体设置入口，并在刷新、分享链接后恢复到同一位置。
- [修复] 首次设置检查在主生成 Backend 为 Claude Code CLI / OpenCode CLI 时不再固定显示“Codex CLI”，改用对应本地 CLI 的显示名。
- [改进] 为 multi-agent DecisionAgent 增加内部低敏分歧摘要输入管线，作为 #1904 P1 解释输出的前置 plumbing；不改变 public API、dashboard schema 或最终解释字段。
- [改进] GitHub Actions 每日分析工作流补齐 TickFlow 数据源环境变量映射，并收敛 README 数据源稳定性说明到完整指南。
- [修复] WebUI 启动时显式 `--host` / `--port` 不再被 `.env` 中的 `WEBUI_HOST` / `WEBUI_PORT` 覆盖，未传 CLI 参数时统一使用解析后的运行时配置。
- [改进] GitHub Actions: 每日分析工作流（`00-daily-analysis.yml`）新增钉钉通知环境变量映射，支持在云端定时任务中直接使用钉钉机器人。
- [修复] Web 持仓页首屏快照改用 `include_realtime=false` 快速估值，跳过逐票实时行情预取后先展示持仓列表，避免外部实时行情源变慢时长时间空白等待。
- [修复] 修复任务状态接口重建报告动作字段时把合法情绪分 `0` 当成空值的问题，确保低分报告能按评分口径纠正为卖出建议。
- [修复] 修复 Agent 流式回复在未收到完成事件就断开时被显示为“（无内容）”的问题，改为提示流式响应中断并保留用户消息，避免误判为空回答。
- [修复] 修复桌面端 `WEBUI_HOST=*` / `WEBUI_HOST=[::]` 会被原样传给端口探测和后端启动导致无法监听的问题，启动前分别规范化为 `0.0.0.0` / `::`。
- [改进] `STOCK_LIST` 自选股解析支持中文逗号、顿号、分号、空格和换行等常见粘贴分隔符，运行时、定时热刷新、CLI `--stocks`、Web 设置保存和自选 API 统一识别，并在写回时规范为英文逗号。
- [改进] 新增 `NEWS_INTEL_AUTO_FETCH_ENABLED` 单开关，开启后个股分析、Agent 分析和大盘复盘会 fail-open 自动初始化并刷新 RSS/Atom/NewsNow 本地资讯池。
- [改进] Web AI 建议页新增主股票上下文，复用最近分析和股票索引候选，并改进表现统计零样本说明。
- [改进] DecisionSignal 将 `decision_profile` 升级为正式 nullable 字段，统一 same-profile 查询、去重、续期和失效语义，并保持 create metadata `null` 兼容与 SQLite 幂等回填诊断。
- [改进] 补充本次设置页布局收敛：移动端分类导航改为横向滚动列表并保证设置内容首屏可见，桌面端保留分类说明并收紧字段布局层级与间距，提升首屏效率与可配置信息密度。
- [文档] 在 README 快速开始中补充行情数据源配置说明（TUSHARE_TOKEN / Longbridge），明确未配置时仍可走 AkShare、Baostock、YFinance 等免费兜底源，日志中相关提示不影响运行。同步更新docs下的中英双份 README
- [改进] 新增 #1743 Phase 6a 内部 DSA Tool Surface 契约，统一工具 schema、stock scope fail-closed guard、结构化错误、审计摘要和脱敏诊断边界，并明确外部 AgentBackend 工具能力仍需 wire-level probe 证明。

- [修复] 桌面与 Docker 发布显式安装 `orjson`，桌面 PyInstaller 产物同时冻结并执行运行时导入探针，避免 LiteLLM 调用时报 `No module named 'orjson'`。
- [改进] 个股报告不再单独展示“题材主线与个股位置”卡片，相关市场结构数据仍保留在分析上下文、模型 Prompt 与决策信号提取链路中。
- [改进] 通知推送与完整 Markdown/微信报告不再重复附加“AI 决策信号”摘要，DecisionSignal 的存储、告警和 Web AI 建议页保持不变。
- [改进] TickFlow 新增基于申万一级行业池的行业涨跌排行 fallback，并将基本面/市场结构单能力默认超时由 3 秒调整为 8 秒，降低正常慢响应被提前降级的概率。
- [文档] 补充 macOS 未签名、未公证 DMG 被 Gatekeeper 拦截时的架构选择、安全排查与官方安装包临时放行步骤。
- [新功能] Web AI 建议页支持确认保存基于历史报告快照重算的决策风格信号，以 created/existing/refreshed 区分新建、原样复用和既有记录续期或维度补齐，复用 profile-aware 去重与失效语义，将历史信号的创建时间、有效期和相反信号失效顺序锚定来源报告时间，并提供可审计 guardrail 提示与阻断。
- [改进] Desktop 可见品牌、可执行文件、安装包与发布产物统一为 `StockPulse`，保留既有 `appId` / NSIS 安装身份；首次升级只迁移新目录中缺失的旧品牌用户数据与更新备份，打包版以单实例锁串行迁移，关键复制失败时清理本次部分结果并回退完整旧目录，旧数据继续保留用于回滚。
- [改进] 历史记录按股票代码删除的代码变体解析、10,000 行分批与无进度保护收敛到 `HistoryService` / `AnalysisRepository`，API endpoint 只负责 HTTP 错误映射；每个级联删除批次保持原子、既有跨批 best-effort 语义不变，并新增 endpoint 事务边界静态守卫与失败回滚回归。
- [改进] 下沉运行流程与通知上下文契约：API 保留兼容重导出，Bot 在异步边界前生成不可变请求快照，核心服务不再依赖 API Schema 或 Bot DTO；上下文回复目标按平台验证并隔离凭据，拒绝的目标继续抑制静态广播。
- [chore] 解除 `config` / `provider_catalog` / `config_registry` 的 import 循环：将 provider 静态目录数据与无配置耦合的访问器（`_PROVIDERS`、`get_provider_ids`、新增 `get_static_provider`）下沉到新的叶子模块 `src/llm/provider_catalog_data.py`，`src.config` 改为模块级从叶子读取 provider 元数据、不再反向 import `provider_catalog`；`provider_catalog` 从叶子读取并 re-export `get_provider_ids`，凭据/base URL 富化仍留在 `provider_catalog`；纯结构调整、行为不变，另加 AST 回归守护。
- [改进] Web 用量页（`TokenUsagePage`）"最近调用"块由原生 `<section>` + 手写 `<h2>` 头部迁移到语义 `Section`（标题/描述/时钟图标走 `title`/`description`/`actions`），与同页其余两块 `Section` 一致；表格容器、数值与交互不变。该页其余部分已使用 `AppPage`/`PageHeader`/`Section`/`SegmentedControl`/`StatePanel`/`StatCard`/`Surface`，本次仅补齐最后一处 ad-hoc 头部容器。
- [改进] 建立统一的进程内 `TaskExecutionPort` 与不可变 task snapshot/event 契约：现有分析队列统一提供 submit/get/cancel/retry/subscribe、幂等与去重权威、首终态获胜的取消竞态、显式 `interrupted` 关停语义及有界 SSE stream，同时保留既有轮询与 SSE 载荷兼容。
- [改进] Web 股票行情工作区页（`StockDetailsPage`）的行情与历史加载占位统一走语义 `Loading`：将实时行情与历史 K 线两处 ad-hoc 加载文本 `<p>` 改用共享 `Loading`（compact `StatePanel`），与页内 `ApiErrorAlert` 错误态一致；加载文案、行情/历史数据与交互行为不变。
- [chore] 下沉 Agent runtime registry、skill prompt 与 executor 装配到 `src/agent/runtime_assembly.py` 叶子模块，`factory` 保留兼容重导出，Native Adapter 不再反向 import `factory`；纯结构调整、行为不变，并新增 AST 回归守护。
- [改进] Web 自选/工作区面板（`HomeStockWorkspace`）的批量分析状态提示统一走语义 `InlineAlert`：移除手搓的 `variant→className` 映射（`statusClassName`）与 ad-hoc 状态 `<div>`，改用共享 `InlineAlert`（compact，`danger`/`warning`/`success` 语义色并补 `role`/`aria-live`）；加载/空/错误态此前已用 `DashboardStateBlock`。自选头部 5 处 `bg-base/35` 半透明 tile 与共享 `glass-card` 面板属基础层玻璃视觉（跨轨复用），保持 cyan/purple/glow 干净并记 Deferred to UIUX。批量分析行为与文案不变。
- [改进] Web 历史记录条目（`StockBarItem`）与持仓页（`PortfolioPage`）概览统计按 PR#35 恢复紧凑密度/排版：条目内边距 `p-2`→`p-1.5`、情绪指示由竖条恢复为圆点（`h-7 w-1`→`h-2 w-2`）、标题去 `tracking-tight`、meta 行距与时间戳字号收紧（`mt-1/gap-2`→`mt-0.5/gap-1`、`text-xs`→`text-[0.6875rem]`）；持仓概览三项统计数字 `text-xl`→`text-2xl`、标签 `text-xs`→`text-sm`。仅密度/排版微调，保留 `home-history-item` 卡片载体与 44px 删除触控目标，行为与数据不变。
- [改进] Web 回测页（`BacktestPage`）结果表从自定义 `backtest-table` `<table>` 迁移到共享 `DataTable`：typed 列/行键、原生 caption/列/行语义与内置横向滚动区取代手搓表格，`backtest-table`/`-head`/`-cell`/`-row`/`-code` 等表内样式收敛到共享组件并同步删除对应 orphaned CSS 规则（保留结果集工具栏与状态 chip 样式）；同步删除 `dataTablePatternGuard` 中 `TRACK-UI2` 的 `UI-BT01` allowlist 例外。股票/日期/阶段/AI 预测（含 Tooltip）/窗口收益或实际表现/方向匹配或准确性/结果/状态各列、涨跌语义色、次日验证的条件表头、加载/空/错误态与筛选分页行为不变；原粘性表头随迁移移除（分页结果表影响有限），未新增 i18n 键。
- [修复] 美股个股实时行情补齐 PE/PB：从已获取的 yfinance `ticker_info` 读取 `trailingPE`/`priceToBook` 填充 `pe_ratio`/`pb_ratio`，实时行情不再恒报估值缺失；美股指数路径无估值，保持不变。
- [改进] `get_stock_info` 工具描述标注多市场（A股/美股/港股），使 agent 对美股/港股标的也调用基本面工具，不再退化为纯行情/资讯回答。
- [修复] MiniMax 等推理模型的补全提取仅取最终文本块，过滤带类型的推理块，避免推理内容与 JSON 拼接导致结果无法解析和持久化。
- [修复] MiniMax 字符串响应仅剥离开头完整的 `<think>` 推理包装，兼容流式分片并保留 JSON 内容中的同名字面标签；dict 形态的渠道测试响应改用字段无关访问读取，修复填写 MiniMax API 时分析/渠道测试报错。
- [新功能] Web 对话页（`ChatPage`）会话侧栏按 PR#35 恢复会话搜索过滤：复用共享 `SearchInput`，按会话标题大小写不敏感即时过滤列表，无匹配时用 `DashboardStateBlock` 显示“无匹配项”空态；复用现有 i18n key（`layout.search`/`common.searchPlaceholder`/`common.noMatches`），不新增文案，会话切换/新建/删除行为不变。

- [改进] Bot `/analyze` 迁移到统一任务执行权威：分析提交改走与 API/Web 同源的 `AnalysisTaskQueue`（共享 Task ID、按规范化股票代码去重、统一状态枚举与错误分类），并经闭包透传发起会话的回复上下文（不落入任务快照/SSE/幂等指纹）以保持结果推送目标等价；成功文案与推送行为不变，同一股票分析进行中的重复请求返回“正在分析中”提示而非并发重复触发。旧 `TaskService` 不再被 Bot 调用，其删除与单进程/interrupted 语义固化由后续 PR 收编。
- [chore] 收编旧 `TaskService`：在 Bot analyze 迁移到统一权威后，删除平行的 `src/services/task_service.py` 单例、`src/services/__init__.py` 中的再导出与 `tests/test_task_service.py`（零生产调用面）；将单进程单一权威（`AnalysisTaskQueue` 为进程内单例，重复实例化返回同一权威、不复位任务状态）与 interrupted 终态判定（优雅关闭把每个非终态任务转 `interrupted`，中断后迟到的 completed/failed 按 first-terminal-wins 拒收、不复活任务）固化为 `docs/task-execution-contract.md` 的显式契约 + `tests/test_task_execution.py` 回归测试，并补充 Bot 语义章节（回复上下文经命令 runner 带外传递、不进入快照/SSE/幂等指纹）。行为不变，无新增用户可见能力。
- [改进] Pipeline 八个阶段新增统一 typed Result 与线程安全重试 fence：未提交失败可重试，同一 query 下已确认的分析历史、本地报告和逐渠道通知会复用结果而不重复持久化或发送；legacy/Agent 共用持久化边界，公开返回值、报告内容、API、数据库 schema 与配置保持不变。
- [新功能] 多策略证据契约计算层：新增 `StrategyEngine`（`src/agent/skills/engine.py`）对 skill 观点做确定性分拣、聚合、综合与冲突检测（方向对立/分值离散/高置信异议/调整矛盾），配套 `synthesis.py`、`protocols` 的策略信号标准化与 `aggregator` 的 `calculate`/`AggregationData`；orchestrator 在决策前统一经引擎处理，invalid 观点移入 `ctx.meta["invalid_opinions"]` 诊断、绝不回流证据链，并在 timeout/budget 早退路径保留诊断；`strategy_synthesis` 由引擎确定性写入 dashboard 载荷（覆盖 LLM 输出）。本片仅计算与接线，报告/通知/模板的本地化呈现随后续 PR。
- [改进] Web 持仓中心页（`PortfolioPage`）持仓明细表从 legacy `<table>` 迁移到共享 `DataTable`：typed 列/行键、原生 caption/列/行语义与内置横向滚动区取代手搓表格，空态改用 DataTable 内建 `emptyState`；账户/代码/数量/均价/最新价（含价格来源与过期提示）/市值/未实现盈亏/收益率/组合信号/操作各列、盈亏语义色（`text-success`/`text-danger`）、右对齐与“分析”按钮不变。同步删除 `dataTablePatternGuard` 中 `TRACK-UI2` 的 `UI-P01` allowlist 例外，并按随表一并移除的 `border-white/10`、`border-white/5` 收敛 `surfaceMigrationGuard` 中本轨对应计数（2→1、4→3）；未新增 i18n 键。
- [改进] Web 首页运行流程（RunFlow）覆盖层按 PR#35 由侧边 `Drawer` 改为居中 `Modal`：共享 `Modal` 新增向后兼容的 `fullscreen` 尺寸（`max-w-[96vw] max-h-[92dvh]`，经 tailwind-merge 覆盖基础 `max-h-[85dvh]`，现有 compact/default/wide 不变），RunFlow 拓扑面板改为近满屏居中弹窗、窄屏自动底部贴边；同步更新 RunFlow 覆盖层单测与 e2e 契约断言（抽屉→Modal、`关闭抽屉`→`关闭`）。RunFlow 数据与交互不变。
- [改进] Web 股票行情工作区页（`StockDetailsPage`）的历史 K 线明细表从 legacy `<table>` 迁移到共享 `DataTable`：typed 列/行键、原生 caption/列/行语义取代手搓表格，日期/开/高/低/收/量各列、日期等宽字体与数值格式不变，表格仍包裹在 `max-h-72` 纵向滚动容器内；同步删除 `dataTablePatternGuard` 中 `TRACK-UI2` 的 StockDetailsPage `UI-SCR01` allowlist 例外。原 sticky 表头随迁移移除（与回测页同类，纵向滚动保留），未新增 i18n 键。
- [改进] Web 首页工作区侧栏（`HomeStockWorkspace`）视图切换器按 PR#35 由 `SegmentedControl` 恢复为单行 `SearchInput`（flex-1）+ 图标 `Select`（Funnel，紧凑 `sm:h-7`）：搜索框与视图切换并列一行，切换器改用共享 `Select`（combobox）下拉选择 历史/自选/今日，面板 role 由 `tabpanel` 改为 `region`；同步更新 `HomeStockWorkspace`/`HomePage` 单测与 smoke e2e 的切换器契约断言（tablist/tab/tabpanel→combobox/option/region，视图切换改经 Select 下拉选择）。视图数据与切换行为不变。
- [新功能] 多策略证据契约新增呈现层：`strategy_synthesis` 以中英韩三语渲染到 Markdown、微信简报、通知与历史报告，展示综合信号、共识、冲突、支持/反方策略及无效观点计数；历史或外部宽松载荷经共享 helper 安全降级，DecisionAgent prompt 明确隔离 Evidence Chain 与 invalid diagnostics。
- [改进] Web 决策信号的 `DecisionSignalDisplay`、`DecisionSignalOutcomeRunPanel`、`DecisionSignalTimeline` 与 `DecisionSignalCreateDrawer` 从手搓或兼容卡片边界迁移到共享 `Surface`/`Section` 语义层级：信号条目与独立运行任务使用 interactive、详情和创建预览使用 section、图表提示使用 overlay，并保留 selected 标识、业务 tone、交互和响应式布局；最近分析候选改用共享 `SelectionChip`，同步删除 `productionDesignGuard` 中 `UI-D01` 的 Button 几何覆盖 allowlist，未新增 i18n 键。
- [修复] Web Router 焦点协调器区分跨路径、完全相同 URL 的新 key PUSH 与同路径 query/hash 状态更新：跨页及同 URL 独立 PUSH 等目标页就绪后聚焦 H1，筛选/分页等 URL 状态更新保留当前控件，同路径 Back 仅恢复唯一稳定触发器；多轮 Back/Forward 不再覆盖已保存 opener，取消及 `useBlocker` proceed/reset 不再污染后续历史项，失效触发器稳定回退 H1。生产守卫覆盖 history 方法的声明/赋值/解构/`bind`/`call`/`apply` 别名，`ResponsiveRail` 复用 `IconButton`，`Toolbar` 类型强制可访问名称。
- [修复] 多 Agent 新增内部低敏 runtime facts，区分 stage 前后 timeout/budget degradation 与 Pipeline termination；dashboard 改为单次 risk application 后按 post-risk signal 收尾，并清除模型伪造的保留解释字段，不新增公开 schema。
- [改进] Web 报告输入数据块在现有低敏 overview 上补充三语异常影响、处理建议与安全诊断码，显式呈现缺少来源和无 reason 的降级状态，并区分本次 LLM 新闻输入与报告页独立加载的补充资讯；组件改用语义 `Surface`/`InlineAlert` 与无嵌套卡片的分隔行，输入/API 字段保持兼容。
- [改进] Web AlphaSift 选股页按 PR#35 恢复紧凑策略配置：策略卡片网格改为共享 `Select`，市场、策略参数和返回数量收纳到共享 `Modal`，策略容器恢复 `p-3` 密度；保留 URL/任务状态、自定义策略与结果清理语义，参数校验或提交失败时保留弹窗和输入，任务受理后关闭弹窗。
- [改进] Web 应用外壳用 typed descriptor 固化九项一级导航并保留 owner 选定的 framed/floating 全局 `main` 表面；1023px 及以下提供唯一共享导航 `IconButton`、完整品牌与可直接访问的 Profile dialog，主题/语言收进 Profile，导航走 Drawer；1024–1279px 无显式偏好时默认 80px compact rail，保存的 80/240px 展开折叠选择在所有桌面断点保持有效。Drawer 仅在 primary same-window 路由激活时关闭，modifier/new-tab 保留原生行为；移动 route 只声明稳定 opener，由 `RouteFocusCoordinator` 按 history entry 捕获并在多轮 Back/Forward 恢复。icon-only 导航统一 labelled Tooltip，44px Profile/偏好/不收缩路由目标与可滚动短视口导航、双轴触摸可达横向内容、Profile 跨断点关闭/焦点交接、light/dark、reduced-motion 由组件和浏览器回归覆盖。
- [修复] Web 应用外壳收敛 Router 焦点与响应式基础契约：`RouteFocusCoordinator` 对临时 Drawer route 的空、缺失或重复 persistent opener alias 统一 fail closed，compact 导航 Tooltip wrapper 禁止 flex 压缩以守住 44px 路由目标；同步撤回无生产 consumer 的 `ResponsiveRail` tablet Drawer API、fixture 与文档声明，避免基础层提前扩张。
- [改进] Web 登录页恢复 24px 背景网格与两处径向主题光层，根画布继续使用专属 `--login-bg-main` token，并移除品牌与认证标题的紧缩字距；认证、传输状态、i18n、响应式和可访问行为不变。
- [改进] Web UIUX 最终审计完成：共享 `DataTable` 新增受控 detail-row 契约并迁移 AlphaSift 十列结果表，保留默认展开且补齐 `aria-expanded`/`aria-controls`；Backtest、Decision Signals 与 Screening 查询更新统一改走 React Router replace；剩余 `glass-card`、raw white-alpha 和无效 `bg-surface` 消费全部迁到语义 Surface/token 后删除兼容 CSS 与 surface allowlist；raw-table 债改用稳定文件/token/计数及具体移除前提，过期 `removeBy` 清零，NotFound 改用 `primary` Button 并删除 `xl` 兼容档。
- [改进] Web 共享 `DataTable` 深化 embedded Surface、固定百分比列、受控选中行、上下文分隔线与稳定行标识契约，并迁移历史趋势、Market Review 指数、Run Flow 尝试、设置 AI 总览及 Token Usage 最近调用五处遗留原生表格；嵌套交互、键盘选择、空态、窄屏内部滚动与业务数值保持一致，生产 raw-table allowance 清零且守卫继续阻断回归。
- [改进] Web 设置、持仓、AI 建议、回测与告警页恢复 PR #35 的页面壳、Tab、筛选区、概览及单一空态结构，共享 `Button` 恢复 20/24/28/32px 可见档位并以 28px 为隐式默认；保留后续新增的账户编辑、手工信号、URL 状态、规则编辑、通知筛选与共享 `DataTable` 能力，并补齐暗色及 391px 响应式回归。
- [修复] Settings restores regular Agent, Conversation, Reports, Alerts, Backtesting, System, Task Routing, Reliability, Advanced, Scheduler, and Event Monitor configuration as visible inline forms using shared controls; data-source configuration and provider/channel directories stay inline, while only discrete add/edit entity, authentication/password, notification-test, and similar submissions use the shared Modal. Settings controls fill one 240px column with aligned Input/Select sizing, the sidebar theme uses the shared vertical menu, and Backtest uses the 32px compact date picker aligned with adjacent filters.
- [改进] Web 设置页「告警与自动化」「系统与安全」「数据源」与顶层「高级」统一改为横向 Tab 视图（推送路由/行为与频控/事件监控，调度/系统设置/Web 与日志/认证与安全/版本与更新，数据源/情报接入/服务商目录，后端状态/开发者诊断/配置备份），URL `?section=&view=` 深链与校验错误跨视图跳转同步生效；「开发者诊断」从默认折叠面板改为独立平铺 Tab（不再折叠），推送路由渠道空态收敛为带「配置渠道」入口的单条紧凑提示。
- [修复] Web 首页个股栏与历史列表的行复选框改为与「全选当前」左对齐同一列（移除行复选框的居中偏移与负外边距），单条删除按钮改为悬停/键盘聚焦时显示（无悬停能力的触屏环境保持常显），与 Chat 会话列表删除交互一致。
- [修复] Web AlphaSift 选股页移除内容区 `max-w-6xl` 限宽，与其他工作区页面一致按全宽展示。
<!-- 新条目格式：- [类型] 描述（类型取值：新功能/改进/修复/文档/测试/chore）-->
<!-- 每条独立一行追加到本段末尾，无需分类标题，合并时冲突最小 -->

## [3.26.3] - 2026-07-15

### Release Highlights

- feat: Standardized the project identity as StockPulse and moved desktop updates, Releases, documentation, and automation links to `SiinXu/stock-pulse-ai`.
- feat: Upgraded the model catalog and task routing to Connection-aware `ModelRef` values so same-name models remain independently selectable and executable.
- feat: Made Settings consume the backend Provider Catalog and Schema, with grouped autosave, conflict recovery, and leave protection replacing the global Save flow.
- fix: Standardized API errors, task messages, asynchronous reads, and Portfolio mutations with reconnect recovery, latest-request-wins guards, and persistent idempotency.
- fix: Hardened secret boundaries across configuration, Agent, AlphaSift, Backtest, and image extraction; sensitive values are masked and excluded from diagnostics and browser traces.
- test: Added blocking i18n, Web unit, build, and 40-scenario Playwright gates covering 320px, 390px, desktop, light, and dark modes.

## [3.26.0] - 2026-07-12

### Release Highlights

- feat: Web homepage added historical, watchlist, and daily workspace, supporting batch analysis, today's coverage judgment, and scoring rankings.
- feat: Added A-shares market structure and theme lines of inquiry, and linked reports, Agents, DecisionSignal, and Web displays.
- feat: Feishu supports report push in file format, multiple Agents support independent timeout clamps for sub-Agents.
- feat: Completed internal DSA Tool Surface, DecisionAgent branch summaries, and DecisionSignal profile contracts.
- fix: Unified report action specifications, fixed batch deletion of historical records and notification reasons with silent interruption issues.
- fix: Improved the stability of Web, desktop, data source cache, and distribution package resources.

### Added

- Added A-shares market structure and theme lines of inquiry, and reused them in reports, Agents, DecisionSignal, and Web market position cards.
- Feishu push added file upload capabilities: `FeishuSender.send_feishu_file(file_path)` uploads files via the App Bot SDK (`im.v1.file.create`) and sends file messages; Webhook mode reverts to sending file content text; added `FEISHU_SEND_AS_FILE=true` configuration switch, which enables Feishu to send reports in file format instead of text messages.
- Multiple Agents Pipeline multi-Agent orchestration added independent timeout clamps for sub-Agents: supports 6 environment variables for TechnicalAgent, IntelAgent, RiskAgent, DecisionAgent, PortfolioAgent, SkillAgent to independently configure hard limits, without encroaching on quotas; default 0 means closed clamp.

### Changed

- Added an internal low-sensitivity branch summary input pipeline for multi-agent DecisionAgent as a pre-plumbing explanation of the output of #1904 P1; does not change public API, dashboard schema or final interpretation fields.
- GitHub Actions daily analysis workflow supplemented TickFlow data source environment variable mapping and consolidated README data source stability notes into a complete guide.
- Web homepage individual stock bar added historical / watchlist / today switch, preserved the default view of historical analysis, and supports one-click analysis of all or only today's uncovered stocks on the watchlist page, and viewing daily analysis rankings by rating on today's page; partial submission failure retains confirmed count, stops subsequent submissions, and refreshes the task list.
- GitHub Actions daily workflow added DingTalk notification environment variable mapping, supporting direct use of DingTalk bots in cloud scheduled tasks.
- `STOCK_LIST` watchlist stocks parsing supports Chinese commas, periods, semicolons, spaces, and line breaks as common paste delimiters. Runtime, scheduled hot refresh, CLI `--stocks`, Web settings save, and unified Watchlist API recognition are implemented, and written back to conform to English commas.
- Added `NEWS_INTEL_AUTO_FETCH_ENABLED` single switch. When enabled, individual stock analysis, Agent analysis, and market review will fail-open automatically initialize and refresh RSS/Atom/NewsNow local news pools.
- The Web AI recommendation page added the main stock context, reused recent analysis and stock index candidates, and improved zero-shot explanations for performance statistics.
- DecisionSignal upgraded `decision_profile` to a formal nullable field, unifying same-profile queries, deduplication, renewals, and invalid semantics. It maintains create metadata `null` compatibility with SQLite idempotent rollback diagnostics.
- The mobile version of the settings page moved horizontal scrolling lists for category navigation and ensured that the settings content was visible on the first screen. The desktop version retained category explanations and tightened field layout hierarchies and spacing.
- Added #1743 Phase 6a internal DSA Tool Surface contract, unifying tool schema, stock scope fail-closed guard, structured error, audit summary, and data masking diagnostic boundaries. It also clearly states that external AgentBackend tool capabilities still need wire-level probe proof.
- `src/services/analysis_service.py` added `details.raw_result` backfill to the `report` layer to ensure consistency with API and historical details payloads; without changing provider, model, Base URL or configuration migration semantics.

### Fixed

- When deleting historical records by stock code, all matching items are cleaned up in batches, and blank codes are rejected to avoid exceeding 10000 entries remaining after cleanup or without filtering deletion.
- When the market structure concept ranking is empty or times out, the results of the previous round are reused to avoid repeatedly requesting the same concept ranking data source for individual stock analysis in batches.
- Windows/macOS desktop backend packaging explicitly collects and validates AkShare `file_fold/calendar.json`, avoiding hot topics and selection line charts being downgraded due to missing trading calendar package data in release packages.
- Summaries shared from DecisionSignal via email, Telegram, and reports fully display the reasons for data masking, avoiding fixed 120-character truncation within sentences; Telegram safely splits according to final Markdown payload length.
- Pushed report, Jinja report and reuse Web/API of historical Markdown export scoring - action scope: high score but old `operation_advice` remains hold and without downgrade reason, suggest text with three statistical display as buy; when there is a clear guardrail reason, continue to keep hold/observe.
- WebUI startup explicitly does not cover `--host`/`--port` in `.env`'s `WEBUI_HOST`/`WEBUI_PORT`, if no CLI parameters are passed, use parsed runtime configuration uniformly.
- Web homepage today's status and ranking uses time zone offset historical timestamp and complete pagination data, maintain safe and accurate when query fails, cross-server time zone boundary or task completion refresh.
- Web homepage stock bar refresh serialization: only the latest request can clear `stockBarRefreshFailed` when concurrent or disordered return, avoid old response overwriting refresh results after task completion.
- Web position page top screen snapshot uses quick valuation with `include_realtime=false`, skips pre-fetching real-time quotes and first displays position list, avoids long blank waiting when external real-time quote source slows down.
- Fixed an issue where a valid sentiment score of `0` was treated as null when reconstructing the task status interface report action field, ensuring low-score reports could be corrected to sell recommendations according to the scoring criteria.
- Fixed the problem that Agent streaming replies were displayed as "(No content)" when they disconnected before receiving a completion event, changed to prompt streaming response interruption and retain user messages.
- Fixed the issue that `WEBUI_HOST=*`/`WEBUI_HOST=[::]` was passed unchanged to port detection and backend startup, causing it to fail to listen. Before starting, normalize them to `0.0.0.0`/`::` respectively.

### Docs

- Added configuration instructions for market data sources ( `TUSHARE_TOKEN` / Longbridge) in the README quick start, clarifying that free fallback sources such as AkShare, Baostock, and YFinance can still be used when not configured, and synchronized complete English and Chinese guides.

## [3.25.0] - 2026-07-03

### Release Highlights

- feat: Added `claude_code_cli`、`opencode_cli` generation-only local CLI backend, and supplemented the status diagnosis, preview, smoke test API and Web status panel generation backend.
- feat: Taiwan stocks report complete access institutional investors data, cover report rendering, LLM prompt, TWD currency marking, closing collection bidding recognition and fetcher resilience reinforcement.
- feat: Added DingTalk group robot notification, Korean report output and AI suggestion decision style re-evaluation preview.
- feat: Agent `/chat/stream` standardized progress event, adding stage start/complete, pipeline timeout and budget skipped semantics.
- fix: Fixed desktop WebUI host/port binding, macOS Homebrew CLI PATH diagnostics, Discord long report chunking, AlphaSift timeouts, yfinance dividend parsing, A-sharesbacktesting code normalization etc. stability issues.

### Added

- DingTalk group robot notification supports `DINGTALK_WEBHOOK_URL` and `DINGTALK_SECRET`, and automatically slices long text to adapt to the 20KB limit.
- Report output language added Korean (`REPORT_LANGUAGE=ko`), covering individual stock reports, market review, Prompt output language, decision fences, notification template tags and Web report details page copy.
- Added `claude_code_cli` and `opencode_cli` generation-only local CLI backend, preserving LiteLLM default path, Agent tool calling boundaries, per-preset extractor, minimum env allowlist and structured error.
- Added generate backend status, preview and smoke test APIs, as well as Web generate backend status panel, distinguishing lightweight checks from JSON smoke tests, and maintaining the local CLI "only generate, no question stock tool calling" boundary.
- Agent `/chat/stream` progress event added `stage_start`, `stage_done`, `pipeline_timeout`, `pipeline_budget_skipped`, completing stage progress, timeout and budget skipped semantics.
- Taiwan stocks individual stock reports' institution block display TWSE T86 / TPEx raw institutional investor net buy/sell amounts, and injecting institutional investor net purchases/sales table into LLM analysis prompt as Taiwan stocks equity filters.
- Added AI suggestion decision style re-evaluation preview interface and page preview.

### Changed

- Taiwan stocks institutional investors fetcher increases concurrent cache anti-collapse, TWSE/TPEx market halts, TPEx date protection and remaining stage budget reuse, reducing the probability of degradation caused by rate limiting, endpoint failure and cold grab timeouts.
- AlphaSift defaults to relying on pin update to `9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf`, accessing wrapper data source caller-side timeout, Dongtai direct connection speed limit/jitter, strategy directory metadata and defensive strategies.
- Stock picking task status polling encounters recoverable timeouts when prompting the background task to automatically retry, `.env.example` supplemented related timeout tuning items.
- Consolidated individual stock analysis scoring with DecisionSignal action guidelines, unifying 80/60/40/20 score ranges and recording raw/adjusted scores, final actions, and reasons during risk control downgrades.
- Web settings page: When switching categories, only displays initial checks and AlphaSift assistant cards in relevant categories to reduce residual issues across categories.

### Fixed

- Fixed the issue where Windows desktop startup fixedly passed `--host 127.0.0.1`, causing `.env`'s `WEBUI_HOST=0.0.0.0` not to take effect, preventing access to WebUI over the network; the desktop client still defaults to `127.0.0.1` and only binds according to configuration after explicit `WEBUI_HOST` configuration.
- Fixed the issue where `.env`'s `WEBUI_PORT` and Electron automatically selected ports were inconsistent during desktop startup, causing the window to continue waiting for the old port and connection timeouts.
- Fixed the issue where macOS desktop clients couldn't find Homebrew Codex CLI in the PATH when starting from Finder/Dock, and clarified the diagnosis of splitting primary analysis calls between Codex CLI and Agent LiteLLM tools.
- Fixed Discord long report pushes being sent in chunks of up to 2000 characters, with retry attempts based on `retry_after`/`Retry-After` when encountering 429 rate limits to avoid partial reports being received after failures.
- Fixed Japanese stocks, Korean stocks, and Taiwan stocks `market_phase` closing session competitive bidding recognition, preventing them from being marked as ordinary `intraday` near the close.
- Fixed A-shares individual stock analysis encountering empty `belong_boards` placeholders not continuing to check related sectors and unstable display of sector modules.
- Fixed market review in LLM title drift or section missing in the body, Web and push reports occasionally lack main sector issues.
- Fixed Web market review structured data transaction volume, index points, percentage change, and high/low value formatting to avoid displaying long-tail floating point numbers or missing values `0.00` directly.
- Fixed the individual stock bar in the Web homepage hidden emotional scores and recommendation indicators when stock-bar summary fields are missing or action suggestions cannot be classified.
- Fixed the background thread for the Web settings page's scheduled task 'Execute Immediately Once' not passing `stock_codes`, causing the task to crash.
- Fixed the static command in `opencode_cli` to avoid global JSON-only constraints impacting `generate_text()` and market review free text output.
- Fixed an issue where `Ticker.dividends` in yfinance 1.2.x returned dividends as a single column DataFrame, causing dividend parsing to be discarded; restored calculation of trailing twelve months (TTM) per-share dividends and dividend counts.
- Fixed currency formatting for Taiwan stocks; converted TWD amounts to "New Taiwan Dollar" to avoid misinterpretation as Renminbi in the context of A-shares.
- Fixed backtesting daily line completion issues with `605066.SH`, `SS605066`, and `SS.605066` A-shares equivalent codes misdirecting requests to the data source `SS605066`, resulting in insufficient backtesting data.

### Docs

- Added Agent `/chat/stream` progress event contract documentation, explaining the meaning of new event fields, web compatibility boundaries, validation methods, and rollback methods.
- Synchronized local CLI backend privacy/deployment boundaries, clarifying that local CLI is not an offline model, Docker/CI/remote endpoints must install login independently, and DSA does not read Claude/OpenCode credential files.
- Updated README with multilingual entry and market support boundary, explaining Taiwan stocks `.TW` / `.TWO`, institutional investors sector, TWD labeling, and closing auction recognition capabilities.

### Tests

- Taiwan stocks and institutional investors fetcher added live-smoke script with `@pytest.mark.network` drift detection tests for verifying TWSE T86 / TPEx core fields and parsing results without blocking network-smoke scheduled tasks.

## [3.24.1] - 2026-06-28

### Fixed

- Fixed Longbridge SDK version constraints to allow platform-based installation versions, preventing failures during `pip install -r requirements.txt` due to the non-existent `0.2.75` version.

## [3.24.0] - 2026-06-28

### Release Highlights

- Added Taiwan stocks, Japanese stocks, and Korean stocks market support, covering Taiwan stocks suffix-only analysis, Taiwan stock institutional investors data layer, JP/KR market review, and cross-service market enumeration.
- Added GenerationBackend abstraction, `codex_cli` local CLI backend, reserved Hermes local HTTP channel, and prompt cache capability registry.
- Added multi-time scheduled push support and runtime scheduler hot rebuild for Web/API/Desktop; Web settings page completed initial startup checks and the scheduled task panel.
- feat: Completed signal attribution chain, individual stock signal timeline, concept sector ranking, and notification/report related sector display.
- fix: Fixed Docker/startup probes, static resource MIME types, backtesting empty results, portfolio valuation, notification Markdown, AlphaSift data source, and test environment isolation stability issues.

### Added

- Added Taiwan stocks suffix-only individual stock analysis MVP: `.TW`/`.TWO` code can access daily and near real-time quotes from YFinance, and supplemented market recognition, trading calendar, and Prompt capability boundaries.
- Taiwan stocks `tw` included in DecisionSignal, Portfolio, Intelligence service layer, API enumerations, and Web filters to prevent Taiwan stock analysis signals from being normalized and silently discarded by the market.
- Added Taiwan stocks institutional investors data layer fetcher `TwInstitutionalFetcher`, supporting TWSE/TPEx sources, date conversion, daily caching, and fail-open fallback.
- market review added `jp`/`kr` markets, supporting Nikkei 225/TOPIX, KOSPI/KOSDAQ index reviews, and expanded `MARKET_REVIEW_REGION`, trading day filtering, and Web settings enumerations.
- Added GenerationBackend Phase 1 abstraction and explicit opt-in of `codex_cli` local CLI generation backend, providing structured error handling, fallback, streaming degradation, and usage unavailable contract.
- Added reserved Hermes local HTTP generation channel, providing JSON generation, no-proxy local calling, and saved secret endpoint binding.
- Added Provider Cache Capability Registry, modeling prompt cache capabilities by provider, API surface, and gateway with verification status.
- Supported `SCHEDULE_TIMES` multi-time scheduled push, long-running Web/API/Desktop processes can save scheduling configuration to hot restart or rebuild the runtime scheduler.
- Added signal attribution analysis and Web AI recommendation page individual stock signal timeline, and wrote default `decision_profile` metadata for automatic generation and historical backfill of DecisionSignal.
- market review, Web report page, and notification related sector completed concept sector ranking and concept signal display.

### Changed

- TickFlow expanded to be an optional data source for A-shares daily K-line charts, real-time market data, and stock lists/names, with added count, integrity validation, and batch prefetch caching protection.
- Hardened JP/KR/TW suffix recognition, Korean stocks seed index, YFinance quotes/fundamentals context, and the boundary between JP/KR Portfolio and Market Light.
- Web settings page added a first-time startup configuration check card and a scheduled task panel, hidden the internal `SCHEDULE_TIMES` key, and improved the close and automatic disappearance experience for repeated task prompts.
- Historical report details no longer embedded AI suggestion cards; structured decision signals are centralized on the AI Suggestion page, and the source report ID/URL parameter is retained for precise positioning.
- `GENERATION_BACKEND=codex_cli` now correctly handles regular analysis and market review when the LiteLLM API Key is missing, using `--output-last-message` to read the final response.
- The local CLI backend limits the total execution time for stdout/stderr diagnostics preview and the final response, and completes the maximum value validation of the new generation backend number configuration.
- AlphaSift defaults to using pin updates to `0a7b9cd59e81718f851890535241bc105d4ddc64` and uses the DSA EastMoney fallback provider by default, exposing source health diagnostics.
- Docker Compose's default memory recommendation increased to 1G; daily analysis workflow is compatible with scenarios where `STOCK_LIST` is mistakenly assigned to the same Environment variables.
- Agent path synchronized signal attribution prompt; report summaries no longer expand AI decision signals in detail, and complete signals are retained in individual stock details and single-stock reports.

### Fixed

- API asynchronous batch analysis shares concept sector ranking cache to avoid duplicate fetching of the entire market concept ranking for multiple stocks.
- Fixed an issue where Markdown table conversion misaligned subsequent content to the wrong header after empty cells.
- Fixed issues with market light region normalization rejecting `jp`/`kr`, misreporting historical list market phase summaries in `analysis_phase`, and missing `dashboard.phase_decision` in default notification reports.
- Fixed Docker installable Longbridge SDK version to 0.2.75 and resolved A-shares data source downgrade issues caused by efinance cache directory owner in the Docker image.
- Updated holding snapshot daily valuation to restricted concurrent prefetch real-time price, reducing Web combination page refresh timeouts when holding a large number of stocks.
- Reanalyzed web homepage automatically switches to the latest report for the same stock and fixed the issue where Windows environment Web/Desktop static JS resources might return as `text/plain`, causing black screens.
- Fixed `--serve --schedule` decoupling from Web/API runtime scheduler status, incorrect prompt of immediate busy state, rebuilt scheduled tasks repeating listen and startup parameter semantics loss.
- Fixed `main.py --serve-only` repeatedly restarting due to lazy import exceeding uvicorn startup check window on low-spec hosts.
- Fixed Web backtesting failing to transmit analysis date range and stock code unnormalized, resulting in successful responses but empty results, providing diagnostics for candidate emptiness, insufficient quotes, and invalid suffixes.
- Fixed unsupported `GENERATION_BACKEND` being treated as an empty response/template fallback, `codex_cli` stdout repeated counting against output limits, and the main analysis JSON schema fallback semantics rollback issue.
- Docker deployment: Web settings page saves custom Webhook templates by escaping `$content_json` placeholders and restoring them at runtime to prevent Compose redeployment expanding to empty.

### Docs

- Completed concept sector ranking field contract, added notification of report industry/concept type column display and data source stability & fault handling chart.
- Added JP/KR/TW suffix-only MVP, `MARKET_REVIEW_REGION` save/validate/rollback matrix, Market Light boundary, and PR submission process constraints.
- Added local CLI backend privacy boundaries, offline model explanations, Docker/CI login state restrictions, and `codex_cli` experimental/limited status.
- Added backtesting request link explanation and synchronized updates to `docs/full-guide.md` and `docs/full-guide_EN.md` examples.

### Tests

- Added Taiwan stocks, JP/KR market review, GenerationBackend, `codex_cli`, Hermes, local CLI, runtime scheduler, backtesting and concept sector ranking regression tests.
- Enhanced temporary `.env` isolation for `tests/test_analysis_api_contract.py`, `tests/test_analysis_history.py` and `tests/test_backtest_service.py` to prevent contamination of system configuration tests with local real `.env` files.

## [3.23.0] - 2026-06-20

### Release Highlights

- feat: DecisionSignal report extraction, web display, feedback/post-mortem, alarm notifications and portfolio risk, AI recommendation signals entering trackable closed loop.
- feat: Added compliance RSS/Atom and NewsNow information source intelligence pool, analysis, Agent and market review can fail-open reuse local information evidence.
- feat: Added Japan/Korea suffix-only individual stock analysis MVP, supporting `.T`, `.KS`, `.KQ` assets via YFinance for market data and technical context.
- feat: Added Token usage monitoring dashboard, legacy LLM usage telemetry and message stability audit, enhancing LLM call observability.
- fix: Fixed live stream running status, AlphaSift cache/field compatibility, release notes diagnostics and Korean stocks ticket input/historical display stability issues.

### Added

- individual stock analysis historical successful save will extract `DecisionSignal` decision signals from the final report best-effort, reuse existing signal deduplication, plan quality calculation and data masking contract.
- Added Web AI recommendation page, latest active holding signal summary, historical report signal display and more complete signal detail cards, displaying rating, confidence, price plans, catalysts, risk and failure conditions.
- Added DecisionSignal user feedback, daily line post-mortem evaluation of signals, statistical API and web display, using outcome/feedback sidecar table and preserving the main signal contract.
- Used DecisionSignal in alarms, notifications and portfolio risk: alarms trigger latest active signals or create minimal alert signals, notifications add low sensitivity signal summaries, holding risk aggregate active sell/reduce/alert signals and maintain fail-open.
- Added compliance RSS/Atom information source configuration, pull, deduplication, import, query, retention and basic security validation API as individual stock/market information intelligence pool baseline.
- Added `newsnow` type, `NEWSNOW_BASE_URL` configuration and `/api/v1/intelligence/sources/defaults` default source initialization interface. Included financial hot spot sources such as CSL Hot Stocks, Xueqihao Hot Stocks, Wall Street Journal Flash News, Jinshan Data and Glory Hu Events.
- Updated individual stock analysis, Agent analysis and market review to fail-open read local news/intelligence pools, and input source links as news context and evidence.
- Added Japan/Korea suffix-only individual stock analysis MVP: `.T` / `.KS` / `.KQ` codes can access YFinance daily and near real-time quotes. Supplemented market recognition, trading calendar, Prompt semantics, Web/API types and ability boundary documentation.
- Added Token usage monitoring dashboard and `/api/v1/usage/dashboard` interface, displaying LLM call total, Prompt/Completion split, model usage, call type distribution and recent call details.

### Changed

- Completed default lifecycle for `DecisionSignal`, relaxed narrow same-origin deduplication, automatically invalidated active signals, and terminal state cannot be PATCH resurrected, and extracted low sensitivity market phase hints.
- Supplemented Web decision-signals typed API wrapper with contract isolation testing, and retrieved historical report AI suggestions precisely to lazy extraction of the exact report.
- DSA data source link added Tencent daily K direct connection fetcher, daily source health short-term circuit break, and upgraded AlphaSift default pin/runtime bridge.
- Default enabled `DAILY_SOURCE=auto`, Sina snapshot priority, candidate-level quote context and LLM ranking timeout/max tokens boundary.
- Added legacy LLM usage provider/cache telemetry, message HMAC diagnostic fields and ordinary individual stock analysis legacy message stability audit, without changing public Usage API, prompt or provider parameters.
- Updated mobile end strategy selection on the Question Stock page to default collapsed button entry, after expanding, multiple strategies can still be selected and automatically collapsed after sending, reducing obstruction of dialogue content.

### Fixed

- Fixed live SSE stream stripping, post-LLM/notification card repetition, data source aggregation card premature success, Web homepage narrow sidebar squeezing stock information, and individual stock analysis automatic generation of the market review context when running diagnostics interfering with each other.
- Fixed AlphaSift hot topics EastMoney instantaneous disconnection and no cache resulting in empty state, desktop update hot cache retention, and `leader_stocks` / `stocks` dual field compatibility issues.
- Fixed Web AI suggestion page filtering/state update pagination, price plan single entry price display, latest position signal refresh, detail JSON secure rendering and card interaction semantic issues.
- Only allow historical reports to trigger decision signals lazy fill when they have a clear `action` or parsable action, avoiding mis-fill of statistics like `decision_type=hold` in scenarios with unclear recommendations.
- Fixed #1390 P6 DecisionSignal omission in combination risk snapshot semantics and default aggregation notification display.
- Default disable creation of the `/api/v1/intelligence/sources/defaults` source, to avoid the default activation of the NewsNow example, while unify 500 response details only log into logs, return generic error information in response.
- Web stock auto-completion, input validation, historical/task display and filtering supplement Japanese Yahoo suffixes code, common Korean stocks index and naked code parsing of stock pool, to avoid crashes with scenarios like `000660`, `005930`, `7203.T`, `005930.KS`, `035720.KQ` or misinterpretation of A-shares semantics or historical split display.
- Korean and Japanese individual stock analysis will use YFinance daily fallback K line and technical indicator context when local history context is missing, to avoid reporting Japanese stocks/Korean stocks core market data and technical data being unavailable.
- When the release note generation query PR author fails, retain downgrade and output a warning containing PR number and exception type, facilitating troubleshooting of token, permission, network or GitHub API exceptions.

### Docs

- README, complete guide and market support document supplement Japanese stocks/Korean stocks examples (`7203.T`, `005930.KS`), and clearly `.T/.KS/.KQ` is currently YFinance-only MVP.
- Added DecisionSignal decision signal documentation, supplementing fields/APIs/Web/alerts notification/combination risk/backtesting, data masking, migration and rollback instructions, and closing Web i18n display boundary.
- Supplement AlphaSift migration and rollback boundaries: clearly `ALPHASIFT_INSTALL_SPEC` explicit override semantics, `requirements.txt + DEFAULT_ALPHASIFT_INSTALL_SPEC` with runtime compatibility boundaries.
- Supplement information source baseline documentation, explaining `NEWS_INTEL_*` configuration, NewsNow self-built suggestions, model/provider/base URL not changing boundary, and disabling or removing intelligence source variable rollback paths.

### Tests

- Added/updated DecisionSignal service, extraction, feedback/backtesting, summarization, documentation, notification, alerts, position risk, Web display and label regression coverage.
- Added/Updated RSS/Atom / NewsNow intelligence source service, API, security validation, analytics access and configuration compatibility testing.
- Added/Updated Japanese market recognition, stock index, YFinance market data fallback, Web auto-completion and input validation testing.
- Added/Updated LLM usage, execution flow, AlphaSift, release notes generation and mobile end interaction related regression.


## [3.22.0] - 2026-06-13

### Release Highlights

- feat: Added DecisionSignal independent storage & API, execution flow snapshots API and Web execution flow view, completed structured fields for recommendation actions and historical/backtesting display link.
- feat: AlphaSift hot topic link upgraded to the new contract, supports hot rankings, topic details, fermentation routes, concept stock details, caching and fallback data source.
- feat: individual stock analysis defaults inject daily market environment summary, and soften aggressive buy recommendations in high-risk/declining environments.
- fix: Fixed question stock historical follow-up target context, watchlist stocks equivalent code matching, low-quality news filtering, execution flow anonymization and AlphaSift hot details display stability issues.

### Added

- Added independent `DecisionSignal` storage, Repository, Service and `/api/v1/decision-signals` API to support deduplication, querying, renewal, status updates, lazy expiration, holding filtering, and sensitive information anonymization based on source/market/stock/action/duration/stage.
- Added analysis task & historical report execution flow snapshot API, provides lanes, nodes, edges, events, summary etc. unified contracts, and builds anonymized data stream/information stream from task queue, running diagnostics and AnalysisContextPack overview.
- Web added running flow view entry for active tasks, historical reports and market review reports, supports viewing execution summaries, topology nodes, event streams and basic fault tolerance details.
- Added AlphaSift hot topic link: backend provides `/api/v1/alphasift/hotspots` & `/api/v1/alphasift/hotspots/{topic}` API, Web stock selection page adds a hot topic area and supports fermentation routes and concept stock viewing.

### Changed

- individual stock analysis added daily/market reusable big market environment summary, normal Pipeline & Agent analysis Prompt can read low-sensitivity big market background; Default enabled `DAILY_MARKET_CONTEXT_ENABLED` configuration, users can still explicitly disable.
- Added: individual stock analysis with historical backtesting display, including optional eight-state `action` / `action_label` recommendation fields, preserving `operation_advice` free text and `decision_type=buy|hold|sell` statistics scope.
- Updated: Added Web decision-signals typed API wrapper and contract isolation test, not yet integrated into UI.
- Improved: Enhanced runtime log context, adding logger name, trigger source, market statistics, and real-time market data prefetch link status for troubleshooting scheduling, API, Bot, and data source degradation paths.
- Fixed: Added account deletion entry to the position holding page, reusing existing account soft-delete interface. Incorrectly created accounts are hidden from default lists, snapshots, risk, input, and event list, and not physically cleaned up historical transactions.
- Updated: Locked AlphaSift dependency update to `d038c52c468543726fc1fd830b53c27d3f09d6da`, completing last-good snapshot, daily history, industry/concept provider cache, hotspot rankings, thematic fermentation routes, concept stock details, and post-analysis metadata for DSA runtime and Web adaptation.
- Updated: AlphaSift hotspots theme reading defaults to using the last successful cache; manual refresh retrieves and overwrites the cache in real time. If real-time retrieval fails, it tries to revert to an older cache.
- Updated: AlphaSift hotspot themes area is now defaulted to be folded; expand and select specific themes to read details; fermentation routes are displayed as a timeline with timestamps; concept stocks can click to enter the homepage and directly start analysis.
- Updated: AlphaSift hotspot theme data links reuse the same time as East Financial sector fluctuation snapshot, and derive trend splits, sustained splits, stages, and leader samples from real percentage change, fluctuations, and high-frequency individual stock.
- Updated: When AlphaSift hotspot theme cards return a small number or lack key fields at the contract level, it uses DSA East Financial sector fluctuation direct ranking list instead, ignoring less than 3 local hotspots cache and supplementing sector bottom-line fields.
- Updated: AlphaSift hotspot theme cards are now in a more compact multi-column layout; concept stock lists are triggered by an independent "Analysis" button to initiate individual stock analysis; details prioritize merging East Financial constituent stocks, Tianhu Shun parsing, and sector fluctuation leader bottom-line data aggregated by day for fermentation time lines.
- Updated: AlphaSift hotspot theme details added DSA side 30-minute disk cache; repeated clicks on the same topic reuse fermentation timelines and concept stock details; thematic events only display AlphaSift contract timelines, Tianhu Shun summaries, configured news search or East Financial sector fluctuation real sources.
- Updated: AlphaSift hotspot theme message catalysis is summarized to display: when configuring LLM, prioritize compressing it into a one-sentence theme catalyst summary; if configuration or calling fails, revert to a local short summary.
- Added AlphaSift hot topic lists with optional `include_details` detail retrieval. Web defaults to batching Top trending themes and concept stocks with the hot topic list and reusing frontend memory cache. News catalysts now fall back to local event summarization when LLM is unavailable.
- Updated `main.py --webui-only` startup behavior: If the FastAPI listening port is occupied, fail-fast throws a clear error and exits.

### Fixed

- Fixed question stock historical report follow-up questions continuing to carry the current stock; switching or reloading existing conversations can restore the basic current stock from the history message, and the backend blocks errors calling incorrect stock tools, exchange fragments, and index abbreviations being routed incorrectly.
- Watchlist stocks added and deleted match Hong Kong stocks and U.S. stocks variants by equivalent stock code, avoiding misinterpretation of `00700`, `HK00700`, `00700.HK` or `aapl`, `AAPL` as different stocks.
- Tightened legacy fallback recommendations: Negative/avoid expressions, Chinese financial context, `buy or sell`, multi-guard ambiguous text and English compound words are no longer incorrectly rendered as action badges; when a structured `action` is present, backtesting/historical trends etc. display the action label in the interface language.
- Stock news and multi-dimensional intelligence search added domain-irrelevant access filtering after relevance sorting, excluding download/install packages, app ratings pages, and adult/prostitution services junk pages, and removing `score=0` background fill items when existing valid stocks or industry candidates are present.
- Fixed historical report running stream snapshots returning 500 errors under mixed time zone event timestamps.
- Fixed running stream live SSE events not reusing the snapshot layer's recursive de-identification rules, avoiding temporary exposure of sensitive diagnostic fields such as local paths, prompt/raw response, and proxy headers before refetching.
- AlphaSift hot topic lists default to returning an empty state when the `alphasift.hotspot` module is missing in an uncacheable and outdated layer; no longer displays AlphaSift not ready immediately after selecting stocks; manual refresh still prompts dependencies that need updating.
- Added fallback naming for THS propagation routes: When `stock_board_concept_summary_ths` returns a missing column, only skip enriching from this source without affecting the hot topic details API return.
- Desktop publishing packaging now uses frozen executable runtime probe validation of `alphasift.dsa_adapter` on macOS PyInstaller to avoid file system/zip scanning misinterpreting modules embedded in executable files as missing.
- AlphaSift hot topic details display prioritizes using the backend-merged `route`, avoiding old `timeline` covering news/LLM summaries; manual refresh of hot topic lists syncs bypassing cached details for the same topics.

### Docs

- Added quick start video tutorial links in the README and adjusted desktop client entry text to the client configuration tutorial.
- Updated `docs/alphasift-integration.md`: clarified AlphaSift lock commit source, Hotspot contract boundary, LLM/LiteLLM compatible semantics, and rollback path when the close switch is enabled.
- Updated based on #1381: runtime scope, compatibility boundaries, official semantic basis, and standard release rollback instructions.

### Tests

- Covered backend runtime and compatibility verification after #1381: `tests/test_main_schedule_mode.py`、`tests/test_pipeline_daily_market_context.py`、`tests/test_daily_market_context.py`、`tests/test_daily_market_context_guardrail.py`、`tests/test_agent_executor.py`、`tests/test_config_env_compat.py`、`tests/test_config_registry.py` and `apps/dsa-web/tests/system_config_i18n.test.ts`.
- Added/Updated AlphaSift backend regression tests: `python -m pytest tests/test_alphasift_api.py -q`, `python -m pytest tests/test_docker_entrypoint.py -q`, `python -m pytest tests/test_main_schedule_mode.py -q -k "start_api_server_fails_before_thread_when_port_is_busy"`.

## [3.21.0] - 2026-06-07

### Release Highlights

- feat: Added English and Feishu App Bot notification modes in the Web UI, improving multi-deployment and enterprise notification scenarios.
- feat: market reviewreport, historical entry, and individual stock columns continued to consolidate into structured data with unified Markdown/GFM rendering; Web/API manual trigger entries are no longer short-circuited by trading day gates.
- feat: Changed the AlphaSift stock selection link to a recoverable background task, and improved DSA LLM runtime bridge, default adapter layer pre-placement, and compatibility regression.
- fix: Fixed English interface residual Chinese, diagnostic display, runtime environment variable display, health check, desktop update path, workflow variable reading, and various Web narrow layout issues.

### Added

- WebUI added independent interface language status and English/Chinese switching entry, covering main navigation, homepage, login, settings page, and common control text; UI language is decoupled from `report_language`, without rewriting the report language link.
- Feishunotification added an App Bot mode, supporting configuration via `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_CHAT_ID`, without creating a custom robot.
- Web market reviewreport added a dedicated display view; historical entry and homepage instant results are unified using Markdown/GFM rendering and hide the exclusive individual stock module.
- Added structured `market_review_payload` for market review, Web, historical details, and push notifications, rendering based on structured data and preserving Markdown compatibility.
- Added a default-closed AlphaSift watchlist tab, controlled via `ALPHASIFT_ENABLED`, and preserved `/install` as an explicit fix path.

### Changed

- Web/API market review manual trigger entry no longer short-circuits or skips due to trading day checks or related market closures; scheduled tasks, GitHub Actions, and CLI default entries maintain original trading day gates.
- AlphaSift Web watchlist switched to background task submission with status polling, adding the ability to recover task states to prevent long browser request timeouts caused by external snapshots, market data, or LLMs.
- AlphaSift watchlist API and service layer consolidated into `AlphaSiftService`, endpoints only receiving routing parameters and error mapping.
- AlphaSift's runtime LLM compatibility bridge with DSA switched to prompt injection, preserving the `provider/model/base_url/custom headers/fallback` semantic link without persistent migration.
- The Web homepage sidebar no longer displays historical market reviews separately. The latest market review has been integrated into the `MARKET` within the individual stock section, sorted by recent analysis time, and leverages existing selection, deletion, full report, and historical trend viewing capabilities.
- The multi-stock notification report now consolidates market phases into a single row under the overall view, no longer repeating data quality and restriction details under each individual stock summary.
- API error response construction consolidated to a shared helper, maintaining existing error envelope shapes and reducing endpoint code duplication.
- WebUI added a runtime warning when binding to public addresses or enabling CORS without administrator authentication; solely for observability, does not block startup or rewrite configurations.
- Database initialization added `schema_migrations` baseline markers for table and idempotency logging to track schema evolution; no migration, cleanup, or rewriting of existing business table data.
- #1386 P6 Reused market stage and AnalysisContextPack summaries with alerts, manual holding analysis, history, backtesting, and notification displays, without adding database migrations.

### Fixed

- Web English interface completed localization of backtesting, portfolio risk, and alarm rule related text; avoids residual Chinese filters, buttons, and enumeration labels in the English mode.
- In comprehensive intelligence search, institutional analysis and performance expectation dimensions have been changed to use a 180-day provider request window to avoid missing cyclical financial materials such as reports and earnings forecasts due to the default short news window.
- The Web individual stock bar and historical cards no longer allow market stage labels to obscure stock names in narrow layouts.
- Question Stock free text follow-up questions no longer misidentify TTM, PE, YOY etc. financial abbreviations as new stock codes.
- [Fixed] GitHub Actions daily analysis workflow supports Variables priority and Secrets fallback when reading SearXNG self-hosted instance address; fixes the issue of URL not working when only Variables are configured.
- Web/desktop left navigation selection state uses border implementation to avoid blue vertical indicator overflowing sidebar boundaries; sidebar expansion width changed from 116px to 136px, and a compact rail mode was added.
- Windows desktop end automatic update installation directory no longer pre-quotes, avoids triggering "missing shortcut / cannot find Daily Stock Analysis.exe" system pop-up when installing with spaces in the path.
- Agent analysis path generates AnalysisContextPack overview by reusing previously stored daily analysis context to avoid displaying `daily_bars_missing` even after successfully fetching daily bars.
- Corrected market review structured availability judgment of `breadth`; does not send `breadth` when the market does not support it or fails to fetch data; displays "No Data" on the front end to avoid misleading 0 values.
- market review language behavior follows global `report_language`, and localizes market labels and strategy blueprints in U.S. stocks Chinese scenarios, avoiding mixed English strategy paragraphs.
- Docker Web settings page reads configuration when the active `.env` file is missing; reverts to displaying the same named environment variable injected during startup and supplements related mounting boundary documentation.
- report page running diagnostics distinguishes between data source fetching success and entering LLM analysis input; news areas in the report page are supplemented/retrieved information, avoiding misinterpretation of input data blocks with status.
- The `/health` root path health check now consistently returns JSON, preventing static web fallbacks from consuming probes. `/api/health` and `/api/v1/health` maintain compatibility.
- `ALPHASIFT_ENABLED` disabled does not trigger `alphasift` runtime injection; enabled prioritizes reusing configured DSA/provider configs and injecting `LITELLM_*` and `LLM_*` runtime variables.
- Complete openai-compatible scenarios with base URL, `extra_headers`, and `LITELLM_FALLBACK_MODELS` path and fallback chain validation.
- Desktop/image packaging link maintains consistent AlphaSift adapter layer pre-provisioning with runtime, avoiding `pip install` as an online fix for dependencies.

### Docs

- Clarified Issue #777 UI language switching uses internal `UiLanguageContext` + `uiText` implementation, persistent key is `dsa.uiLanguage`, and supplemented with corresponding visual acceptance guidelines.
- Clarified market review display link, structured payload, language behavior, trading day gate differences, and rollback boundaries.
- Added LLM / LiteLLM compatibility keys in Settings for displaying and validating the context rollback boundary. Clarified that existing provider/model/base URL persistent configurations are not rewritten, migrated, or cleared.
- Updated #1602 diagnostic scope fix coverage, specifying that only unified input and display scopes are addressed; rollback is performed via a standard release rollback.
- Updated AnalysisContextPack P6 documentation, migration, and rollback boundaries. Synchronized existing `SAVE_CONTEXT_SNAPSHOT` to `.env.example`, registry configurations, Web settings help, and the complete guide.
- Added #1386 entry points for pre-market/during-market/post-market analysis, migration, rollback, and user-visible explanations.
- Added official compatibility basis landing for AlphaSift runtime bridge; clarified provider/model/base_url/extra_headers/fallback and rollback boundary.

### Tests

- Web executed `npm run lint`, `npm run build`, related Vitest and smoke commands. When `DSA_WEB_SMOKE_PASSWORD` is not set, smoke use cases are skipped as designed.
- Web runtime declares Node `>=20.19.0 <27` and npm `>=10`. LocalStorage testing has been added to fully support stable Vitest.
- Enhanced static validation of AlphaSift runtime bridge and packaging scripts, covering `LLM_CHANNELS`、`LITELLM_FALLBACK_MODELS`、`alphasift.dsa_adapter`、`--collect-all alphasift`。

### chore

- Removed screenshot assets mistakenly entering the repository during issue/PR acceptance workflows.  Once-time screenshots should be retained in PR descriptions, comments, attachments or artifacts, not as repository files for inclusion.

## [3.20.0] - 2026-06-03

### Release Highlights

- Added AlphaSift stock selection entry, automatic installation and stable adaptation layer, supporting Web strategy execution, LLM rearrangement display, and controllable enabling with default shutdown.
- Added individual stock history, watchlist queues, market stages and AnalysisContextPack visibility, enhancing the structured context capability of Web reports and APIs.
- Updated MiniMax default model to `MiniMax-M3`, completing related prices, presets and test coverage.
- fix: Repair health check, Windows desktop update and initial run encoding, ETF daily secid, LLM base_url checksum Agent daily context misjudgment and other stability issues.

### Added

- Added default closed AlphaSift stock selection tab, after enabling via `ALPHASIFT_ENABLED`, reads and executes strategies through the stable adapter layer.
- Web homepage left sidebar changed to individual stock bar, displaying stocks by deduplication, market review is top-pinned, clicking individual stock loads the latest report, supports normalization deduplication merge by code variant (.SZ/.SH/.SS).  Retain select all, batch delete and delete confirmation entry; New API `DELETE /api/v1/history/by-code/{stock_code}` for batch deletion by stock code.
- Added a watchlist action to the report details sidebar, allowing users to check whether the current stock is on the watchlist and add or remove it with one click; market review reports do not show this action.
- Added a watchlist action above the AskStock input. After users send a message containing a stock code, the page automatically offers an add-to-watchlist or remove-from-watchlist action.
- Web report page new same-stock historical trend drawer entrance, historical list summary supplement trend, summary, model and analysis field with market data, supports viewing historical analysis by current stock and loading more.
- AnalysisContextPack P4 low sensitivity overview access historical details, synchronize analysis response, completed task status and Web report page, display data block status, source, missing reasons and downgraded summary.
- #1386 P5 for individual stock analysis report adds `dashboard.phase_decision` intraday decision barrier, and sets high confidence buy/sell conclusions in the market stage according to data quality restrictions before saving history.
- #1386 P4a new `analysis_phase=auto|premarket|intraday|postmarket` API parameter, and transmits request phase through asynchronous task accepted, memory status, list, SSE and analysis pipeline.
- #1386 P4b Web report page added final market stage tag, task panel displays request stage, and reuses AnalysisContextPack low-sensitivity data quality summary.
- MiniMax channel model list upgraded: Added `MiniMax-M3` as default, according to official OpenAI-compatible documentation supporting 1M input context (project conservative registration `<=512K`, price_window 512K, `max_tokens` 128K, corresponding $0.6/M input, $2.4/M output, >512K input window unmodeled), retained `MiniMax-M2.7` and `MiniMax-M2.7-highspeed`, and preserved `MiniMax-M2.5` legacy price entries to accommodate existing user configuration cost estimation. Web settings page MiniMax preset models and prices refreshed by M3.
- Added AnalysisContextPack P1 internal contract and de-identification serialization testing.
- Added historical details, analysis response and task status report metadata for market phase sensitivity summary.

### Changed

- Updated: Added missing AI Key, empty STOCK_LIST, Telegram/email paired fields and Webhook URL prefix diagnostics for initial run configuration validation.
- Moved AlphaSift stock selection entry to the ‘Wen Gu’ section of the web sidebar, aligning with Agent/research assistant workflows.
- Docker image build stage pre-installs default AlphaSift adapter layer, avoiding runtime installation like desktop packages.
- Updated: AlphaSift stock selection now depends on the stable `alphasift.dsa_adapter` interface; web strategy lists are dynamically provided by AlphaSift, no longer hardcoded in the frontend.
- Added Run ID, snapshot count, filtered quantity, factors and risk details to the AlphaSift stock selection page; displays real details when expanding candidates; temporarily only supports A-shares market.
- Added AlphaSift selection card to the Web Settings page, allowing direct enabling or disabling of the watchlist tab.
- When AlphaSift selection is enabled, first switch `ALPHASIFT_ENABLED` and check layer availability. If missing, automatically call the controlled installation interface; no longer requiring users to click install manually.
- When AlphaSift is enabled but the adapter layer is missing, the strategy list and selection interface will serially auto-install and lock the source, and forcibly reinstall to overwrite the old `alphasift` package.
- Merged duplicate snapshot source fallback prompts on the AlphaSift selection page and preserved AlphaSift's own Tushare priority snapshot logic.
- AlphaSift selection page displays warning/source error/parse error when LLM reordering is downgraded, and avoids displaying local factor scores as LLM judgments.
- The Web Settings page no longer repeats the display of `ALPHASIFT_ENABLED` as a regular data source configuration item; this value only serves as persistent state behind the ‘enable selection’ button.
- When AlphaSift is closed, the left-side ‘selection’ navigation entry on the web is hidden to avoid misleading users who have not enabled it.
- Added logic for displaying custom AlphaSift selection strategies, avoiding misdisplaying ‘balanced multi-factor’ when not matching preset items.
- Added GET /api/v1/history/stocks endpoint to return a list of individual stocks grouped by code; added GET /api/v1/stocks/watchlist, POST /api/v1/stocks/watchlist/add, POST /api/v1/stocks/watchlist/remove endpoints to support self-selected queue addition, deletion, and querying. STOCK_LIST read/write remains unchanged, without automatic normalization; add/remove normalization comparison judgment equivalent code variants.
- Added useWatchlist hook to uniformly manage the frontend state of the self-selected queue, reusing SystemConfigService’s STOCK_LIST configuration item for persistence.
- AnalysisContextPack P5 added data quality scoring, `fetch_failed` status, Prompt data restriction blocks, and low-sensitivity quality display on the web.
- #1386 P2-full added cross constraints between market stage and downgraded data in AnalysisContextPack Prompt data restrictions, and corrected the phased market data label for Chinese analysis prompts.
- restored default notification report sending path for compatibility with existing channels and channel splitting logic. Added renderer capability only for future expansion.
- When associated sector lacks type data, the sector name is displayed as a single line to avoid generating a sector table with `N/A` entries.
- Optimized Web report detail page information hierarchy, moving input data blocks and running diagnostics below the main content for auxiliary collapsed information.
- Completed in-market analysis, real-time market data acquisition time, provider time, stale, fallback and partial/estimated marking, for AnalysisContextPack mapping input data restrictions.

### Fixed

- Agent analysis path generates AnalysisContextPack overview; reuses previously cached daily analysis context to avoid displaying `daily_bars_missing` after successful daily bar retrieval.
- Registered /api/v1/health route and added authentication exemptions, fixing the issue where this path returned 404 and health probes received 401 errors when ADMIN_AUTH_ENABLED was enabled.
- Windows local first-run environment check compatibility for non-UTF-8 console output, and commented `requirements.txt` to reduce the probability of dependency installation failure under the default code page.
- AlphaSift DSA adapter layer defaults to enabling LLM reordering, backend explicitly requests `use_llm=True`, watchlist page displays LLM scores, judgments, coverage rates, and watch items.
- AlphaSift embedding DSA reuses DSA-parsed LLM models, channels, and key configurations, avoiding Web-configured LLMs but watchlist LLM reordering still downgrading due to missing provider key.
- Added DSA LLM routing filtering for unannounced managed providers, fallback chain replenishment for declared channels to avoid Gemini fallback coverage of available DSA channels.
- Updated AlphaSift default source installation to lock trusted commit GitHub addresses; desktop mode automatic installation does not require administrator sessions; non-desktop deployments require administrator authentication sessions and continue to restrict installation sources.
- Fixed the issue where enabling AlphaSift in the Web interface caused a default closed state due to installing first then writing configuration.
- AlphaSift status and installation interface no longer returns the explicit `install_spec`, only returns non-sensitive status fields such as `install_spec_is_default`.
- AlphaSift status detection distinguishes missing optional dependencies from unexpected exceptions, records warnings in exception scenarios, and returns non-sensitive diagnostic information.
- Adjust AlphaSift screening call compatibility: use `screen` with `max_results` as the primary key and support historical `max_output` keywords, while allowing strategies to transmit parameters to align with manual frontend strategy parameters.
- AlphaSift Web stock selection requests use an independent long timeout to avoid being interrupted by the general 30-second API timeout after enabling LLM rearrangement.
- Pre-install AlphaSift and collect adapter layers during desktop packaging, avoiding requiring administrators to automatically install the package at runtime.
- AlphaSift automatic installation only triggers when the `status` diagnosis is `missing_module` (only module missing scenarios); layer adapters can be imported but runtime exceptions are no longer automatically `pip install`ed, instead returning `424` and retaining the diagnosis to avoid masking real runtime failures with reinstallation.
- Fix Chinese interface remnants and gaps in the settings page help on the Web backtesting page, which is now displayed in Chinese, and only registered configuration items with explanations are shown on the Web settings page.
- Windows desktop automatic updates reuse the current installation directory explicitly during silent installation to avoid failure when uninstalling old versions in custom installation directories.
- The Windows installer adds quotes to the `_?=` install directory parameter when retrying the old uninstaller, fixing a return of 2 caused by installing paths with spaces that cause automatic updates to fail.
- The Windows desktop automatic update adds quotes to the `/D=` directory parameter passed to NSIS when it contains spaces to avoid truncating the registry location.
- Strengthen LLM channel `base_url` validation to prevent SSRF bypass due to parsing differences.
- Correct efinance ETF daily Eastmoney secid routing, avoiding querying Shanghai ETFs with deep-market quote IDs resulting in empty daily data.

### Docs

- Clarified AlphaSift and LiteLLM compatibility boundaries: Only bridges DSA providers/models/base URLs declared for invocation periods, does not migrate `.env` provider/model routes; rollback is to disable AlphaSift and restore original `LITELLM_*`/`LLM_*` configurations.
- Clarified AlphaSift only reuses existing DSA LLM/LiteLLM configuration semantics, does not add `LITELLM_MODEL`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, `LLM_TIMEOUT_SEC` model semantics migration; failure prompts and rollback paths use the existing system configuration link consistently, only affects AlphaSift stock selection capabilities.
- Clarified AlphaSift's automatic installation source locking, `missing_module` and runtime exception behavior boundaries, as well as LLM/provider/base URL and custom channel rollback paths, for easier issue tracing and rollback to original LLM configurations.
- Clarified that the new model field in historical trend data for the same stock is a historical snapshot metadata display, does not affect runtime LLM Provider/Model/Base URL routing and configuration migration cleanup; rollback is to revert this change as usual.
- Clarified the compatibility boundary of #1311: The rendering layer only consumes analysis results `model_used` display fields, has not modified the `wechat/slack/feishu/telegram` sender sending link, does not trigger provider/model/base_url compatibility migration.
- Clarified AlphaSift's locking of the commit `alphasift.dsa_adapter` contract basis, as well as the compatibility boundaries of the current DSA API/Web call structure.
- Clarified that the Settings page for LLM configuration only displays grouping and field merging, without rewriting or triggering LLM migration/rollback paths; compatible with existing `LLM` configuration save and rollback semantics.
- Added AnalysisContextPack P0 context overview.
- Completed alarm center P8 documentation and configuration closure instructions; clarified legacy JSON, advanced rules, Web/API, Docker, GitHub Actions, and Desktop boundaries.

### Tests

- Synchronized updates to `llmProviderTemplates`, LiteLLM fallback pricing, and MiniMax presets with related unit tests; asserted the new default model.
- Supplemented ETF daily data source routing, input variants, fallback, and MA field regression coverage.

### chore

- Added notificationreport channel capability imaging, PreparedMessage, and structural awareness Markdown splitting infrastructure to support #1311 full-channel rendering adaptation.
- Pre-installed WeChat, Feishu, Telegram, DingTalk, Slack platform metadata. Does not change default report entry and visible layout.

## [3.19.0] - 2026-05-29

### Added

- Implemented #1391 Phase 1 running diagnostics minimal link: Added task/SSE `trace_id` and recorded daily and real-time `market data` ProviderRun snapshots.
- Alarm Center added P7 market review red-green light structured rules, supporting `market_light_status` and `market_light_score_drop` reuse of existing workers, historical triggers, notification and cooling links.
- Implemented #1391 Phase 2 running diagnostics summary: Generated user-readable `RunDiagnosticSummary`, provided historical report diagnosis API and data redaction copy text.
- Implemented #1391 Phase 3 running diagnostics visibility: Report details and task panel default folded display of running status, trace and copyable troubleshooting information; Backend provides historical link fill via `api/v1/history/{record_id}/diagnostics` and `context_snapshot.diagnostics`.
- Added AnalysisContextPack P1 internal contract and data redaction serialization testing.
- Added AnalysisContextPack P2 builder, assembling internal context packages from existing artifacts in a standard analysis pipeline.
- WinStock added default closed visible dialogue context compression, supporting Web switch, Agent advanced preset, rolling summary and recent round transcript protection, reducing long session token consumption.
- Stock auto-completion index defaults to refreshing from GitHub main remotely and caching locally, Web/CLI analysis entry failure automatically downgrades to built-in index, reducing pollution of old nicknames after hat removal and renaming.
- Standard Analysis and Agent runtime Prompt access AnalysisContextPack low-sensitivity summary, maintaining history/API/Web output compatibility.

### Changed

- `scripts/fetch_tushare_stock_list.py` can correct names in A-shares with `XD`/`XR`/`DR`/`N`/`C` prefixes, used by default auto-completion refresh workflow.
- Web routing page changed to on-demand loading, reducing the first package size and adding route loading failure recovery prompts.
- Web complete report Markdown drawer changed to on-demand loading.
- Added market stage inference baseline and clarified pre-market, intraday, afternoon rest, near closing, post-market, and non-trading Japanese terms.
- Added running state market stage context construction and downgrade testing.
- Settings page configuration completed market stage fill-in Web settings page actual display/configurable fields Chinese and English bilingual project, covering Agent, backtesting, report, notification routing, system runtime, AI legacy, data source and notification advanced configuration.
- P2-min: LLM Prompt injection market stage context.

### Fixed

- stock auto-completion index generation failed directly when missing `pypinyin` to avoid writing downgrade indexes with missing pinyin fields.
- Unified Tencent real-time market data share volume as stock gauge, avoid magnifying the multiple changes of volume power and misleading analysis report.
- Docker defaults remove `.env` single file mounting, to prevent WebUI configuration saving from triggering `Device or resource busy` due to `os.replace` updating the mount point.
- Resolved #1391 Phase 0 A-shares code ownership boundary: Completed consistency of attribution for scenarios with prefixes `SH`/`SZ`, clarifying the repair scope of `data_provider/baostock_fetcher.py`, `data_provider/pytdx_fetcher.py`, and `data_provider/tushare_fetcher.py`.
- Fixed internal format conversion when using bare A-shares codes in `STOCK_LIST` with Baostock etc. data sources, to maintain user configuration continuing to use 6-digit stock numbers.
- Windows desktop client automatic updates switched to silent execution of installer after user confirms restart installation, and cleans up process references after stopping the built-in backend, reduces probability of installer prompting ‘Japanese stocks ticket analysis cannot be closed’.
- macOS desktop client migrates runtime configuration to user data directory, migrates `.env`, database, and logs when old `.app` package files are still accessible, avoids reconfiguring after subsequent upgrades replacement.
- Restored sector and sector linkage fields extraction in Agent/historical snapshot compatibility, fixed the regression issue where the new homepage report was missing "sector linkage".
- Corrected legacy alarm JSON field names and quiet period delivery semantics in Web settings help.
- Fixed the Chinese setting page on the Web, which had issues with duplicated titles, descriptions, and key dropdown options in the data source, notification, system, and Agent areas.
- Resolved a potential issue where Agent/analysis tasks remained in "in progress" state after switching question-stock conversations and re-linking the homepage task.
- Added provider-aware trace branching for single-agent question-stock, preserving DeepSeek V4 thinking + tool-call `reasoning_content` and tool protocol materials across rounds.
- Increased the call level timeout for Akshare's new Sina/Tencent A-shares historical bottom-fill interface, and completed Tushare `605xxx` Shanghai code routing regression testing to avoid scheduled analysis being suspended due to data source unavailability.
- Increased the minimum dependency of `exchange-calendars` to `4.13.0` to prevent analysis failures caused by the Timedelta unit `T` being invalid in pandas 3 environments when importing trading calendars.
- Interactive command (DingTalk conversations, Feishu conversations, Telegram) triggered analysis results only returned to the source conversation, no longer broadcast to static notification channels.
- Adapted Longbridge OAuth 2.0 authentication and token caching recovery, avoiding misjudgment of the Longbridge data source as unconfigured when the new backend has no Legacy Access Token.
- Longbridge OAuth path explicitly downgraded logging when `OAuthBuilder` / `Config.from_oauth` is not supported in the current SDK, to avoid build failures on Linux/Docker where only old SDKs can be installed.
- Compat with YFinance returning unnamed date index scenarios, to avoid missing `date` column in U.S. stocks daily line fallback.

### Docs

- #1391 Phase 0 running diagnostic contract documentation added, clarifying trace_id, diagnostic summary, key link range, and de-identification/fail-open/retention boundaries.
- Completed documentation and configuration closure for P8 alarm center, clarifying legacy JSON, advanced rules, Web/API, Docker, GitHub Actions, and Desktop boundaries.
- Explained that this desktop fix only covers Windows NSIS update installation links and backend process lifecycle cleanup; it did not modify setting item save/model runtime cleanup semantics. Removed the mistakenly included `docker/Dockerfile` and `npm registry` changes, restoring deployment build and update repair responsibility isolation.
- Added an AnalysisContextPack P0 context inventory, clarifying field quality status, existing state mapping, and the first pack boundary.
- Clarified #1391 Phase 2's structured detection alarm as a non-configuration migration signal: `agent_max_steps`/`agent_orchestrator_timeout_s` illegal values will fallback to default and generate log alarms. Added diagnostic links only added `context_snapshot`/`RunDiagnosticSummary` read/write fields, without rewriting `litellm_model`, `agent_litellm_model`, `openai_base_url`, LLM channel routing or configuration migration semantics.
- Supplemented #1391 Phase 3 compatibility notes: recorded backend diagnostic persistence, historical query and notification write links changes boundaries and rollback strategies, and completed backend gate-level verification requirements.

### Tests

- Converged #1391 Phase 3 backend/API and Web regression checks: `./scripts/ci_gate.sh`, `test_pipeline_market_phase_context.py`, `test_analysis_api_contract.py`, `test_analysis_history.py`, `npm run lint`, `npm run build`.
- Executed `python -c "import exchange_calendars as xcals; xcals.get_calendar('XSHG'); print('ok')"` to cover import and trading calendar initialization compatibility.

## [3.18.0] - 2026-05-21

### Release Highlights

- feat: Extended alarm center to P2-P6, completing background assessment, real notification results, business cooling, technical indicator rules, and watchlist stocks / holdings / account linkage rules.
- feat: Added individual stock analysis support for strategy selection, including hot themes, event-driven, growth quality, and earnings revaluation strategies, and supplemented fundamental data, financial summaries, shareholder returns, and related sectors for HK/US reports.
- feat: Added Finhub / AlphaVantage U.S. stocks data source adapter to extend the U.S. stocks daily failover chain and improve the resilience of U.S. stock market data acquisition.
- fix: Fixed stability issues with desktop end package publishing, analysis status interface, AlphaVantage percentage change, real-time holding valuation, alarm history deduplication, database cold start, and fallback pricing registration.

### What's Changed

- feat: Add alert-center P2-P6, Web strategy selection, HK/US fundamental context, static-report financial sections, and Finnhub / AlphaVantage US-market fallback.
- improve: Refine LiteLLM parameter recovery, yfinance currency/dividend handling, RSI calculation, market-review presentation, stock-news relevance ranking, and report table rendering.
- fix: Harden desktop packaging/update assets, completed analysis-status responses, AlphaVantage pct_chg routing, portfolio realtime snapshots, alert trigger dedupe, DatabaseManager cold start, and fallback pricing registration.
- docs/tests: Add beginner setup and settings-help docs, document compatibility/rollback boundaries, and extend regression coverage for API, alert, packaging, and release paths.

## [3.17.1] - 2026-05-16

### Release Highlights

- fix: Explicitly closed electron-builder automatic publishing in the Windows / macOS desktop end packaging script to avoid failure during tag builds due to missing `GH_TOKEN` after local packaging; Release workflow continues to be responsible for uploading and publishing artifacts.

### What's Changed

- fix: Add `--publish never` to the Windows and macOS Electron packaging scripts so tag builds only create local artifacts and GitHub Actions handles release upload/publish.

## [3.17.0] - 2026-05-16

### Release Highlights

- feat: Added Alert API MVP, supporting CRUD operations for alarm rules, enabling/disabling, one-time testing, and querying trigger/notification results. Initial coverage includes `price_cross` / `price_change_percent` / `volume_spike` and maintains legacy configuration compatibility.
- feat: notification gateway added ntfy and Gotify channels, with completion of notification denoising, static channel isolation, diagnostics, Web testing, and GitHub Actions env alignment verification.
- feat: Windows desktop installation version integrated automatic update installation chain, supporting background download, confirmation restart installation, runtime file backup/restore, and release product metadata validation.
- improve: market review added concept ranking, popularity stocks, and limit-up pools as underlying data sources. Supports index rise/fall color semantic configuration and writes review results to historical records.
- improve: Web settings page supports `.env` configuration backup import/export and notification/Agent area local error fallback; report added `REPORT_SHOW_LLM_MODEL` switch control model information display.
- improve: Docker startup entrypoint automatically fixes mount directory permissions and downgrades to console when the log directory is not writable, reducing manual fix steps in common deployments.
- fix: Data source lacks credentials or connection failure gracefully downgraded; Longbridge / Pytdx added cooling, avoids outputting high-confidence buy conclusions when missing funds flow.
- fix: Compatible with OpenAI-compatible `content_blocks` response for analysis and report links, normalized price fields, and fixed market review scrolling and historical record loss issues.
- docs: Completed notification, alarm center, desktop packaging, README / guide, and PR title governance documentation, clarifying configuration compatibility boundaries and rollback paths.
- test: Increased regression coverage for Alert API, notification denoising/routing, Docker entrypoint, data source pre-fetching, desktop update chain, and historical analysis.

### What's Changed

- feat: Add an Alert API MVP with rule CRUD, enable/disable, one-shot testing, trigger history, notification results, and legacy config compatibility.
- feat: Promote ntfy and Gotify to first-class notification channels with Web tests, routing, Actions integration, diagnostics, and noise control.
- feat: Add the Windows desktop auto-update install flow with runtime state backup/restore and release artifact metadata verification.
- improve: Extend market review data sources, add configurable index color semantics, and persist market review results into analysis history.
- improve: Add Web `.env` backup import/export, local settings panel error boundaries, and a report model visibility toggle.
- improve: Harden Docker startup by repairing mounted directory permissions and falling back to console logging when mounted logs are not writable.
- fix: Cool down unavailable optional fetchers, reduce noisy Longbridge/Pytdx retries, and downgrade buy advice when capital flow data is missing.
- fix: Handle OpenAI-compatible `content_blocks`, normalize strategy price fields, and recover market review scrolling/history behavior.
- docs/tests: Update notification, alert, desktop packaging, README/guide, and governance docs; add focused regression coverage for the new release paths.

## [3.16.0] - 2026-05-10

### Release Highlights

- feat: Web homepage added "market review" trigger entry, task polling and direct output to report upon completion; initial startup configuration status prompts missing gaps and guides to system settings.
- feat: Added notification routing strategy, supporting narrowing notifications to specified channels based on report, alert, and system_error; Web settings page supports one-click testing of notification channels.
- feat: Added configuration item help entry and multi-language help text infrastructure to the system settings page, covering watchlist stocks, LLM main model, LLM channels, Feishu Webhook and WebUI listen address.
- improve: unified `build_market_review_runtime` mounting path for market review API、CLI、Bot; completed backward compatibility notes for `litellm_model`/`llm_model_list` and legacy keys.
- improve: Combined individual stock report operation suggestions with support/resistance, power, momentum, retail investor flow, and leading fund flow calibration to reduce violent buy/sell switching and reinforced Agent decision bottom-line protection.
- improve: Docker image supports non-root user execution; LiteLLM dependency constraints relaxed to fix version 1.x for subsequent security fixes.
- fix: Correctly classified `Model disabled` and `provider blocked` errors in the LLM channel test, preventing them from being misidentified as network issues.
- fix: Hong Kong stocks daily line skipping does not support the built-in historical data source; the `BJ` prefix and `.BJ` suffix code validation with the BJAEX exchange remain consistent.
- fix: Improved observability of Web market review button, Windows fallback process locking detection, and more robust catalyst clue display.
- docs: Added documentation center and configuration help maintenance instructions; cleaned up temporary PR/document synchronization explanations in README, complete guide, and configuration guide.

### What's Changed

- feat: Add a Web home market-review trigger with task polling and inline report display; setup status now points users to missing configuration.
- feat: Add notification routing by report, alert, and system_error; add one-click notification channel testing in Web settings.
- feat: Add settings field help infrastructure with multilingual help text for the first batch of core configuration fields.
- improve: Share `build_market_review_runtime` across API, CLI, and Bot market review paths; document `litellm_model` / `llm_model_list` and legacy key fallback behavior.
- improve: Calibrate stock advice with support/resistance, volume, chips, and main-force capital flow; strengthen Agent decision fallback behavior.
- improve: Run Docker images as a non-root user and relax LiteLLM constraints to allow safe future 1.x fixes.
- fix: Classify `Model disabled`, provider blocked, and related LLM channel test errors more accurately instead of reporting them as generic network failures.
- fix: Avoid unsupported built-in historical providers for Hong Kong daily data; align Beijing Stock Exchange `BJ` prefix and `.BJ` suffix validation.
- fix: Improve Web market-review observability, Windows fallback lock probing, and market catalyst snippet rendering.
- docs: Add the documentation index and settings-help maintenance guide; remove temporary PR/doc-sync notes from README and user-facing guides.

## [3.15.0] - 2026-05-05

### Release Highlights

- LLM channel configuration experience continued upgrade: added Anspire OpenAI-compatible gateway access, and completed common service provider presets, official sources, capability tags, configuration notes, and GitHub Actions explicit mapping.
- Web LLM configuration detection more diagnostic: segmented error reason, and supports user explicit trigger JSON, tools, vision, stream runtime smoke.
- LLM runtime configuration cleanup is more robust: only clean up invalid runtime selections from managed providers, and preserve compatible semantics for direct providers such as `cohere/*`, `google/*`, and `xai/*`.
- notification and Bot status observability enhanced: Custom Webhook supports JSON body templates, and the `/status` Bot displays more complete LLM, Agent, and notification channel statuses.
- market review, real-time alerts, Agent weak bottom-casting and position valuation continue to strengthen, reducing default value coverage, missing price pollution and configuration obstacle avoidance costs.

### Added

- Supports `ANSPIRE_API_KEYS` default access to Anspire OpenAI-compatible large model gateway, and adds Anspire Open presets in the LLM channel editor.
- Custom Webhook supports `CUSTOM_WEBHOOK_BODY_TEMPLATE` JSON body templates, facilitating adaptation for AstrBot, NapCat and self-built push services.
- market review structured blocks added major market red/green light conclusions, based on board temperature output green/yellow/red, core reasons and operational suggestions.
- EventMonitor supports `price_change_percent` percentage change threshold rules, which can trigger real-time alerts in either the upward or downward direction.
- Web LLM channel editor added common service provider configuration templates and presets, covering MiniMax, Huashan Fangzhou, OpenAI, Claude, Gemini, Kimi, Qwen, GLM, Doubao etc. entrances.

### Changed

- Added Web LLM configuration detection to supplement the classification of misclassified errors and added an explicit trigger for JSON/tools/vision/stream runtime smoke; default testing and saving processes remain unchanged, and detection results are used as a current configuration's best-effort diagnosis.
- Bot `/status` displays unified LLM master models, Agent models, channel modes, YAML configurations, and more notification channels status.
- Web LLM channel editor displays provider capability tags, official source links, and configuration note prompts; these tags are used for configuration reference only and do not represent runtime capabilities that have been verified.
- Extracted Web LLM provider preset single template data source, maintaining the existing configuration save semantics unchanged.
- Completed LLM provider channel explicit mapping in GitHub Actions and synchronized `.env` examples with the configuration documentation.

### Fixed

- Agent weak integrity fallback prioritizes retaining local trend analysis results when a model lacks scoring, trends, operation suggestions, or dashboard key blocks, and only supplements truly missing dashboard fields to avoid default 50 coverage of the homepage score.
- Unified holding snapshot output now includes reference price, market value, floating profit/loss, and price component information to avoid stale price pollution.
- LLM channel testing added structured diagnostics and UI troubleshooting prompts for provider, model, Base URL, and authentication configuration issues.
- Runtime cleanup boundary clarified: Only managed providers (`gemini`, `vertex_ai`, `anthropic`, `openai`, `deepseek`) trigger pre-save invalid value clearing; `cohere/*`, `google/*`, `xai/*` direct link values retained on legacy compatible paths, without prompting migration or overwriting.
- Adjusted MiniMax presets to use the official OpenAI-compatible Base URL and current model examples, supplemented with MiniMax, Volcano Engine, LiteLLM compatibility sources and rollback instructions.
- Removed screenshot recognition downgrade logic for Gemini 3 Vision models; defaults to current Gemini model configuration.

### Docs

- Improved LLM provider configuration documentation, adding configuration selection, Actions variable mapping, runtime detection boundaries, error reason troubleshooting, and rollback paths (#1180).
- Added LLM channel editor official source, dependency compatibility window, runtime model cleanup rules during save, and legacy configuration rollback instructions.
- Supplemented official provider/model documentation for `cohere/*`, `google/*`, `xai/*` direct link semantics; added compatibility basis reference for `litellm>=1.80.10,<1.82.7` and clarified that example model names are only for configuration retention, not endorsement of availability.
- Clarified that the `price_change_percent` alert event is solely for configuration and runtime rule expansion; it does not change model/provider/Base URL/LiteLLM compatibility semantics; rollback path is to disable/remove Event Monitor configurations.
- Synchronized README, DEPLOY, full-guide, Anspire, AIHubMix, and SerpAPI related documentation, unifying external links, configuration scope, and review consistency explanations.

### Tests

- Completed AI configuration page and `task_queue` LLM runtime cleanup/sync regression evidence: Restore channel models by preserving fallback, do not silently clear runtime selections during edit model list, clean invalid runtime references when no available models in the channel, and preserve semantic connections to legacy keys and `cohere/*`, `google/*`, `xai/*` direct providers.
- Covered detailed error classification in Web LLM configuration detection, as well as explicit trigger paths for JSON, tools, vision, and stream runtime smoke tests.

## [3.14.2] - 2026-04-30

### Release Highlights

- market review expanded to Hong Kong stocks, and Bot `/market` uses consistent trading day filtering semantics with CLI/scheduling entry.
- Enhanced configuration for question stock and Agent link missing decisions fallback and multi-strategy selection experience.
- Improved stability of LLM and analysis report link: illegal JSON responses continue to attempt backup models, LiteLLM DEBUG logs default noise reduction.
- Added read-only initial startup configuration status interface to lay the foundation for subsequent configuration wizards and smoke run.

### Added

- market review supports Hong Kong stocks market: `MARKET_REVIEW_REGION` added `hk` option; `both` extended to A-shares+Hong Kong stocks+U.S. stocks, and new Hong Kong stocks index (HSI/HSTECH/HSCEI) replay link.
- Added read-only initial startup configuration status interface `GET /api/v1/system/config/setup/status` to identify LLM, Agent, watchlist stocks, notification and local storage configuration gaps; this interface does not reload runtime, write `.env` or create database files.

### Changed

- The `question_stock` page supports selecting multiple Agent strategies.

### Fixed

- Bot `/market` command reuses `get_open_markets_today()` / `compute_effective_region()` for trading day filtering: The result is passed through as `override_region` to `run_market_review`. If the result is an empty string, skip the review and push "Today's related markets are closed". This aligns with CLI/scheduling entry behavior.
- The `question_stock` Agent retains the backend real error reason when no available LLM is configured and maintains `done.success=false` failure semantics to prevent the frontend from misinterpreting configuration absence as a successful response.
- When the Agent mode does not generate an effective decision dashboard, it preserves local trend analysis scoring, trends, and action recommendations, and normalizes strong buy/strong sell fallback to compatible `buy`/`sell` decision types to avoid the homepage results being overwritten by the default value "50 / Watching / Unknown".
- When the holding snapshot current price is missing, it no longer silently reverts to holding cost; the daily snapshot uses historical closing prices first, and only falls back to real-time prices when missing. Missing holdings do not pollute market value and unrealized gains summary, and the holding details return price source, date, stale status, and missing status.
- The analysis Prompt cleanses mutually exclusive reasons by final `trend_status` / `ma_alignment` before injecting `trend_analysis`: Removing bullish reasons from bearish structures, removing bearish risks from bullish structures, and forcefully prompts "Event first, technology pending confirmation" and volume power downgrading when event/technical conflict and abnormal high volume (>10x) occur.
- When the LLM returns a non-JSON response, the backup model switch is triggered: When the main model successfully returns but cannot parse JSON, it no longer immediately downgrades to a pure text fallback; instead, it sequentially tries models in `LITELLM_FALLBACK_MODELS`. If all models cannot return valid JSON, it then downgrades to a text fallback.
- LiteLLM internal DEBUG logs are now default-lowered to WARNING, preventing token-level log pollution during streaming generation to `stock_analysis_debug_*.log`. To troubleshoot LiteLLM internals, temporarily set `LITELLM_LOG_LEVEL=DEBUG` (Fixes #1156).

### Docs

- Added LLM configuration guide and FAQ, clarifying the compatibility priority of the stock Agent for `LITELLM_CONFIG`/`LLM_CHANNELS`/legacy `GEMINI_*` `OPENAI_*` `ANTHROPIC_*` including rollback paths and the conclusion that old configurations will not be silently migrated.

### Tests

- Added `tests/test_bot_market_command.py`, covering `MARKET_REVIEW_REGION=both` + open markets `{"cn","us"}` / `{"cn","hk"}` of `override_region` through assertions, and covering paths to skip closed market trading days and close trading day checks. Added `tests/test_yfinance_hk_indices.py` covering Hong Kong stocks index symbol mapping and partial/full failure downgrade paths.
- Completed lightweight import stub stock code standardization functions for the `task_queue`; Restored `tests/test_task_queue_config_sync.py` collection and execution.

## [3.14.1] - 2026-04-26
- [Test] Fixed market review prompt testing assertion for "tomorrow's trading plan" title, and synchronized desktop version number, restored release gate.

## [3.14.0] - 2026-04-26

### Release Highlights

- 📊 **market review upgraded to post-market desktop structure** — A-shares review fixed outputting board temperature, index details, sector Top tables, news catalysts, tomorrow's trading plans and risk prompts, reducing the repetition and emptiness of pure text reviews.
- 🖥️ **Desktop App Added GitHub Release Update Notifications** — Windows/macOS desktop app automatically detects new versions upon startup, or can be manually checked and navigated to the download page via Settings.
- 🤖 **Pipeline Agent Data Loading Noise Reduction Updated** — Candlestick tool switched to DB-first and preheated 240 days of historical data to avoid duplicate HTTP requests for the same stock.
- 🐳 **Docker release pipeline streamlined** — Release workflow consolidated into two paths: official release and manual patch releases. Official Docker Hub image name unified as `zhulinsen/daily_stock_analysis`。
- 🔧 **LLM channel and DeepSeek V4 configuration strengthened** — GitHub Actions scheduled analysis completed multi-channel variable transmission, DeepSeek official channel preset and examples synchronized to V4。
- 🧩 **Desktop static resource consistency check** — Packaging pipeline and runtime can earlier detect static resource mismatches, reducing the cost of white screen troubleshooting in Release packages.

### Added

- 🏠 **Web homepage historical report area added a new re-analysis entry** — Supports redoing analysis for the same stock on the same date based on the original prompt.
- 🖥️ **Windows/macOS desktop client added GitHub Release update reminder** — Automatically detects new versions after startup and supports jumping to the download page via the settings page after manual check.

### Changed

- 📊 **A-shares market review report converted to a structured post-market workbench layout** — Fixed output of market temperature, index details, sector Top table, news catalysts, and tomorrow's trading plan.
- 🐳 **Docker release workflow consolidated** — Clearly distinguishes between official releases and manual patch releases, unifying the official Docker Hub image name to `zhulinsen/daily_stock_analysis`。
- 🤖 **Agent daily tool prioritizes local cache reuse** — Simultaneously persists newly acquired daily data and news intelligence, reducing redundant data source calls。

### Fixed

- 🤖 **Pipeline Agent K-line tool DB-first loading** — `get_daily_history`, `analyze_trend`, `calculate_ma`, `get_volume_analysis`, `analyze_pattern` now prioritize reading local DB, eliminating 9x5=45 repeated HTTP requests for the same stock (Fixes #1066).
- 🤖 Pipeline Agent preheats 240 days of K-line historical data to DB on demand — Normally, K-line tool calls do not require repeated network requests.
- 🕒 Freeze `target_date` and pass it through ContextVar to Pipeline Agent K-line tool thread — Eliminates time drift across closing boundaries.
- 🪟 Windows desktop backend log copy encoding fix — When copying stdout/stderr, prioritize UTF-8 and support local code page rollback to avoid Chinese logs being garbled.
- ⚙️ GitHub Actions daily workflow completion fills in LLM channel variable propagation — Supports `LLM_CHANNELS`, multiple Keys and common `LLM_<NAME>_*`, avoids local multi-model configurations failing in cloud scheduled tasks (Fixes #1063, #872).
- 📈 Historical report details interface corrects `change_pct` value — Uses `is None` to check and avoid discarding 0.0 (flat) as a missing value, removes the incorrect `change_60d` fallback, and reverts to the original real-time market data field when missing (Fixes #1084).
- 🔧 DeepSeek official channel presets and example configurations synced to V4 — Preserves legacy `deepseek-chat` default values and adds deprecation warnings, while fixes model discovery after runtime selection causing save failure issues (Fixes #1108, #1109).
- 🧩 **Desktop packaging build chain added static resource consistency check** — `scripts/check_static_assets.py` will verify that the resources referenced in `index.html` exist in both the source `static/` and the PyInstaller output, and also writes explicit logs when mismatches occur at runtime to avoid white screens after opening Release packages (Refs #1064 / #1065 / #1050).
- 🧩 **Backend `/assets/*` switched to explicit hosting** — Returns `text/javascript` / `text/css` 404 when resources are missing, matching the request extension, reducing misleading error responses from default JSON errors (Refs #1064).
- 🌙 **`kimi-k2.6` automatically uses fixed temperature** — The main analysis, market review and Agent call this model automatically using `temperature=1.0` to avoid the model rejecting requests with the default temperature (Fixes #1102).

### Docs

- 🐳 **Added official Docker image usage instructions** — Includes instructions for pulling images, `docker run` usage, and `.env`/data directory mapping; no longer only covers Compose deployment paths.
- 📨 **Fixed Feishu custom robot Webhook example** — The example in `feishu_sender.py` is changed to an interactive card JSON, and a Feishu automation Webhook trigger configuration tutorial is added.
- 📚 **Optimized root README structure** — Retains homepage-level feature characteristics, technology stack, quick start, push effect, Web, Agent, sponsors, and news source entry; consolidates fine configurations, trading discipline, and fundamental semantics into a complete guide; and points the Docker badge to the official image page.
- 🌐 **Synchronized simplified README entry structure in English and Traditional Chinese** — Completed LLM usage API and position management documentation in the complete guide.
- 🤝 **Adjusted README maintenance rules in AI collaboration and PR templates** — Clarified that READMEs do not need to be updated unless necessary, prioritizing details in dedicated topic documents.

### Tests

- 🧪 **Stabilized LiteLLM stub behavior for market review tests** — Prevented local LiteLLM installations from affecting market review unit tests when the collection order changed.
- 🧪 **pytest defaults to skipping frontend dependency directories** — `apps/dsa-web/node_modules` is no longer recursively scanned by backend tests when present locally, preventing unrelated directories from slowing down pre-release gates.

## [3.13.0] - 2026-04-21

### Release Highlights

- 🌉 **Longbridge OpenAPI data source integration** — U.S. stocks/Hong Kong stocks market data prioritizes Longbridge; YFinance / AkShare are used as fallback; behavior remains unchanged if not configured.
- 📈 **Tushare Hong Kong stocks full-chain expansion** — Hong Kong stocks daily data is obtained through `hk_daily`; chip distribution for Hong Kong stocks returns `None`; conversion units follow Hong Kong stocks' scale, no longer using A-shares hand/1000 yuan rules.
- 🔍 **Anspire Search Semantic Search Integration** — Configure `ANSPIRE_*` to use Anspire Search for real-time market data and information. Without configuration, it's fully transparent.
- 🚀 **Standard Analytics Link Supports LLM Streaming Generation** — The homepage task SSE has added the `task_progress` event for more granular progress; non-streaming providers automatically fall back to non-streaming calls.
- 🤖 **Web Channel Editor Supports On-Demand Retrieval of Available Model Lists** — `/v1/models` is the unified model discovery entry point, with multiple writes to `LLM_{CHANNEL}_MODELS`, and a fallback to manual input if retrieval fails.
- 🛡️ **Agent Stability and Budget Controls Significantly Reinforced** — `AGENT_MAX_STEPS` semantic unification, skill degradation not interrupting pipelines, SSE exception propagation, skill loading warning logs completed.
- 🛠️ **SQLite write chain atomization** — Batch atomic upsert + WAL + `busy_timeout` + limited retry writes, significantly reduce batch analysis concurrent lock competition.

### Added

- 🌉 **Integrated Longbridge OpenAPI as U.S. stocks/Hong Kong stocks optional data source** (fixes #981) — Configure `LONGBRIDGE_*` to prioritize Longbridge for daily and real-time market data; YFinance / AkShare as fallback; otherwise behavior remains consistent with previous versions. Integration testing uses `tests/longbridge_live_smoke.py` (manual script, not collected by pytest).
- 📈 **Tushare supports daily query for Hong Kong stocks** — After configuring Tushare credentials, call the `hk_daily` interface to obtain Hong Kong stock data; if permissions are insufficient, an exception is thrown, consistent with the original process.
- 🔍 **Integrated Anspire Search optional semantic search backend** — Using `ANSPIRE_*` can access real-time market data and news information through Anspire Search; if not configured, the behavior is consistent with the previous one. Unit testing using `tests/test_anspire_search.py` (manual script).
- 🚀 **The ordinary analysis link supports LiteLLM streaming generation and finer task progress** — stock analysis in the LLM stage prioritizes `stream=True` and accumulates chunks on the server; the homepage task SSE adds the `task_progress` event and more granular `message/progress` updates; only persist historical reports after the final JSON parsing is successful; does not support streaming providers automatically reverting to non-streaming calls.
- 🤖 **Web AI model configuration supports obtaining available models by channel** — The channel editor supports calling `/v1/models` to retrieve available models and writing them back in a multi-select format for `LLM_{CHANNEL}_MODELS`; if retrieval fails, manual input is retained as a fallback path.

### Changed

- 🔎 **SerpAPI content patching range narrowed** — Natural search results are no longer synchronized to grab the webpage content one by one; only a small number of high-level and insufficient summary results are delayed patched, prioritizing reusing the structured summaries returned by SerpAPI to reduce tail latency in the search link and slow site amplification risks.
- 🤖 **Simplified LLM access experience** — The user interface for AI model access is unified as "Main Model / Agent Main Model / Backup Model / Model Channel", no longer treating LiteLLM as a concept that users must learn; existing `LITELLM_*` / `LLM_CHANNELS` configuration keys remain compatible.
- IntelAgent has added company announcement searching and the `get_capital_flow` tool. It includes search dimensions for SSE/SZSE/CNINFO announcements and resolves the frequent missing announcement and capital flow data issues in Agent mode.
- 📦 **Backend stock name parsing prioritized reuse of `stocks.index.json`** — Lazy-load cache frontend static index; silently downgraded to `STOCK_NAME_MAP` and original data source fallback chain in pure backend/missing static resource scenarios.
- 📊 **TushareFetcher Hong Kong stocks unit adaptation** — `get_chip_distribution` directly returns `None` (Hong Kong stocks currently do not support chip distribution); `_normalize_data` no longer performs A-shares hand→share and thousand yuan→yuan scaling for Hong Kong stocks (`hk_daily`) to align with the semantics of Tushare Hong Kong stocks fields.
- Agent Max Steps Error: Added a prompt to help users troubleshoot step limit issues. `AGENT_MAX_STEPS`
- This release introduces support for configuring GitHub Actions task timeouts via `vars`. The `daily_analysis.yml` task's timeout now reads from repository variables, allowing you to adjust the execution timeout limit without modifying the code (fixes #1014).

### Fixed

- 📣 **Market review link integration of `REPORT_LANGUAGE`**: When `REPORT_LANGUAGE=en`, prompts, chapter titles, template fallback text, and notification packaging titles for A-shares/merged reviews are consistently output in English to prevent the mixing of English content with Chinese headings.
- 📈 **EfinanceFetcher index open price mapping compatibility fixes** (#1043) — `get_main_indices()`'s open price mapping was changed to be compatible with `today's open → open → open`, fixing the issue where some efinance versions read index open prices as missing values.
- 🤖 **AGENT_MAX_STEPS semantic unification** (#1026) — In orchestrator multi-Agent mode, it is explicitly defined as "sub-Agent step limit instead of hard cover"; TechnicalAgent and other high default value Agents will be capped, while low default value Agents remain unchanged; User actively increasing ( > 10) covers all sub-Agents uniformly. Fixed the issue where setting 12 resulted in TechnicalAgent running with a default value of 6 and reporting "Agent exceeded max steps".
- 🛡️ **Specialist（Skill）Agent failure changed to graceful degradation** — Skill Agent failures no longer interrupt the entire analysis pipeline, maintaining the same degradation strategy as intel/risk.
- 🔧 **MiniMax-M2.7 Connection Test Fix** — Fixed the issue where LLM channel connection tests in MiniMax-M2.7 returned "Empty response"; increased the `max_tokens` limit from 8 to 256 to accommodate thinking processes, and added `content_blocks` format parsing logic.
- 📊 **Removed `sentiment_score` Range Constraint** (fixes #942) — Removed the `ge=0/le=100` constraint for `sentiment_score` in the `HistoryItem` and `ReportSummary` response schemas; out-of-range values stored in the historical database no longer trigger Pydantic ValidationError.
- 🖥️ **Issued Clear Warning When WebUI Frontend Resources Are Missing** — `webui_frontend.py` issued a warning when `static/index.html` exists but `static/assets/` is missing, preventing CSS/JS resource absence from causing abnormally large pages that are difficult to troubleshoot (fixes #944).
- 🔗 **Analysis Pipeline Optional Service Degradation Initialization** — `StockAnalysisPipeline` search service and social sentiment analysis service will log warnings and continue to run in disabled state if any initialization exception occurs, avoiding external dependencies shaking the main analysis link.
- 🖥️ **Desktop Version Display Unified Read `package.json`** — Unified reading of `apps/dsa-desktop/package.json`, removing the hardcoded `0.1.0` in preload, and setting page to display the real desktop version; fixes version number display errors (fixes #1048).
- 🐋 **Hong Kong stocks Name Acquisition Failure Fix** (fixes #940) — Fixed the problem that Hong Kong stocks names could not be correctly reverted to the backup field when the main data source field was missing.
- 🔄 **SSE Task Flow Disconnect, `CancelledError` Correctly Re-raised** (fixes #967) — Fixed the issue where exceptions were silently swallowed when an SSE flow was interrupted, resulting in no log data.
- 🔄 **Agent SSE Clean Background Task Exception Correctly Reported** (fixes #969) — Exceptions from background executors at flow end are now correctly logged and reported, avoiding errors that could not be perceived.
- 🔇 **Skill Load Exception Added `logger.warning` Log** (fixes #970) — Added logs to the silent except blocks in `ask.py`, `skills/aggregator.py`, and `skills/router.py` to ensure that when the skill list is empty, log data is available.
- 🛠️ **SQLite write chain atomization** (fixes #878) — `stock_daily(code,date)` uses batch atomic upsert; file-type SQLite connections default enable WAL + `busy_timeout` + limited write retries; "New number" is now calculated according to the actual inserted window.
- 💰 **Multiple Agent / Single Agent budget fences semantic unification** — When the remaining budget falls below the minimum threshold, it proactively skips and downgrades; Completed stage-able build report when returning `success=True` and carries non-empty content, otherwise returns `success=False`.
- ⚙️ **GitHub Actions `daily_analysis.yml` supplemented `REPORT_LANGUAGE` injection** (fixes #1013) — Fixes the issue where users configuring `REPORT_LANGUAGE` in Secrets/Variables does not take effect.
- 📊 **Task status API supplemented real-time price fields** (fixes #983) — `GET /api/v1/analysis/status/{task_id}` fills in `current_price` / `change_pct` when retrieving completed tasks from the database, fixes the issue where real-time prices are not displayed next to the reportstock name on the homepage.
- 📅 **Non-trading day data returns the latest trading day** (fixes #1009) — Fixes the problem of fragmented chip distribution and sector ranking returning the second-to-last trading day data for non-trading days (weekends/holidays); now normal returns the latest trading day data.
- 🔍 **A-shares news search restored Chinese priority** — `search_stock_news()` continues to try subsequent engines when the primary provider mainly returns English news in the first batch of results and ranks Chinese news at the front; Non-U.S. stocks queries no longer default to using Brave's `en/US` region language preference.
- Feishunotification now supports signature verification using `FEISHU_WEBHOOK_SECRET` and `FEISHU_WEBHOOK_KEYWORD`. Web settings and documentation clearly distinguish between Webhook push modes and `FEISHU_APP_ID`/`FEISHU_APP_SECRET` application modes to minimize misconfiguration risks.
- ⚡ **LLM Adapter Layer Added `RateLimitError` and `ContextWindowExceeded` Detection** — Identifies and handles rate limit and context window exceeded errors, improving the robustness of the analysis link in high load or long text scenarios (fixes #1002).

### Tests

- 🧪 **TushareFetcher Hong Kong stocks Related Unit Tests** — Added `get_chip_distribution` equity distribution retrieval and `_normalize_data` unit tests for Hong Kong stocks/A-shares/ETF units, covering special paths for Hong Kong stocks.

### Docs

- Added: `DEPLOY.md` supplement with troubleshooting steps for UI elements expanding excessively; added guidance to rebuild Docker images or manually execute `npm run build`. Updated `deploy-webui-cloud.md`.
- Updated: Feishu Webhook configuration instructions - emphasized that `FEISHU_WEBHOOK_URL` is a mandatory field for group notifications, signature verification must be enabled or disabled simultaneously on both ends, and `FEISHU_APP_SECRET` is only used in application/Stream Bot mode; `.env.example` supplemented with inline comments; synchronized English guide.
- Added: FAQ supplement with troubleshooting item (Q12c) for Ollama connection failures - covers 5 check points: service not running, URL configuration error, missing model prefix, model not downloaded, remote firewall.
- 🌉 **README Supplement Longbridge Data Source Usage Instructions** — Chinese/English/Traditional README clarifies Longbridge's "Preferred / Backup / Unconfigured Not Called" boundaries; `docs/` internal relative path links fixed; `LONGBRIDGE_PRINT_QUOTE_PACKAGES` configuration aligned with code and `.env.example`.
- 🐋 **Docker Installation Scenario Version Explanation** — Adds minimal documentation, clarifying that in Docker installation scenarios, version should be determined by Git tag / image tag (fixes #1091).

## [3.12.0] - 2026-04-01

### Release Highlights

- 📊 **backtesting Page New "Next-Day Verification" View** — Allows viewing AI predictions vs. next-day actual gains/losses by stock and date range; reuses historical analysis and 1-day backtesting results to quickly verify analytical accuracy.
- 🔧 **LLM Access Experience Simplified** — User-side text prompts unified to "Main Model / Backup Model / Model Channel", no longer treating LiteLLM as a concept that all users must learn. Existing configuration keys remain compatible.
- 🐳 **Docker / WebUI Runtime Stability Enhanced** — Fixed issues with system settings not taking effect after saving, early startup log missing, and reusing pre-built static resources; reduces friction in containerized deployment.
- 🔒 **Security and Concurrency Stability Simultaneously Strengthened** — Discord inbound Webhook completed Ed25519 signature verification, fixed shared state not being locked when executing concurrently, and notification concurrency reuse in single-stock push mode.
- 🖥️ **Desktop and Scheduled Task Details Polished** — Windows installer supports custom installation directories, with a built-in scheduler that detects changes to the running SCHEDULE_TIME and uses market time zones for resuming from checkpoints.

### Added

- 📊 **Backtesting Page Added "Next Day Verification / 1-Day Window" View** — Allows viewing AI predictions, next-day actual gains/losses, and interval accuracy by stock code and analysis date range. Reuses historical analysis and 1-day backtesting results.
- 🏷️ **Web Settings Page Added Version Information Card** — `apps/dsa-web` now injects the frontend package version and build time during builds. The system settings page includes a read-only "Version Information" block displaying `WebUI Version / Build Identifier / Build Time`. When `package.json` is still at the placeholder version `0.0.0`, it automatically reverts to the build identifier, facilitating quick confirmation of static resource effectiveness after Docker rebuilds.
- The Windows desktop installer now supports custom installation directories. It continues to utilize the existing packaged state directory logic, reading and writing from `.env`, `data/stock_analysis.db`, and `logs/desktop.log` alongside the installation directory. The `win-unpacked` self-install distribution method is preserved. Key features include: `allowElevation: false`, NSIS `.onVerifyInstDir` to prevent system protection directory selection, and support for current user installations.

### Changed

- 🔎 **SerpAPI Text Scraping Range Consolidated** — Natural search results are no longer synchronized by the entire page; instead, it only performs delayed scraping for a small number of high-value results with insufficient summaries within a shorter timeout budget, prioritizing reusing the structured summary returned by SerpAPI to reduce tail latency and risks associated with scaling slow sites.
- 🤖 **LLM Access Experience Simplified** — User-facing AI model access text has been unified into "Main Model / Agent Main Model / Backup Model / Model Channel / Advanced Model Routing Configuration"; Web settings, metadata configuration, validation prompts, and English/Chinese documentation no longer treat LiteLLM as a concept that all users must learn. Existing `LITELLM_*` / `LLM_CHANNELS` configuration keys remain compatible.

### Fixed

- 🚀 **Launch failures now expose the true root cause** — `python main.py` exposes the true root cause via stderr, no longer writing log files to the hardcoded `logs/` directory in the bootstrap stage; file logs are created after `config.log_dir` is available, avoiding residual log files in unexpected paths during healthy startup.
- 🐳 **Docker WebUI runtime prioritizes reusing prebuilt static assets** — `prepare_webui_frontend_assets()` now checks for existing `static/index.html` within the image and reuses it directly if possible. When a container doesn't include the `apps/dsa-web` source directory and doesn't have `npm` installed, it won't falsely report "Unable to find frontend project, cannot automatically build" which restores WebUI opening capabilities after Docker deployments.
- 🐳 **Docker WebUI system settings take effect after saving** — In Docker scenarios, the WebUI saves `STOCK_LIST`, `SCHEDULE_ENABLED`, `SCHEDULE_TIME`, `SCHEDULE_RUN_IMMEDIATELY`, and `RUN_IMMEDIATELY` in `.env`; `Config` prioritizes reading new values from the persistent `.env` file instead of being overwritten by environment variables injected during container creation.
- 📈 **Market Review LLM max_tokens increased** — The Market Review generation link now uses the LLM `max_tokens` from `2048` to `8192`, reducing the probability of content being prematurely truncated due to `MAX_TOKENS`.
- ⏰ **Built-in Scheduled Task Detector perceives SCHEDULE_TIME runtime changes** — The scheduler now detects WebUI saved `SCHEDULE_TIME` changes while running and rebinds the daily job in the next check cycle.
- 🪟 **Windows Release Channel Editor preserves MiniMax model prefix** — When filling in `minimax/<model_name>` under channel mode, the backend normalization will retain the original value and will not miswrite it as `openai/minimax/<model_name>` with the Web settings page runtime model list.
- 🤖 **Discord Incoming Webhook Completed Ed25519 Signature Verification** — `DiscordPlatform` now validates Discord Interaction signatures based on `X-Signature-Ed25519`, `X-Signature-Timestamp`, and the raw request body; it directly rejects requests if signature headers are missing, the public key format is invalid, or the signature does not match, while also performing a ±5-minute time window validation on the timestamp to defend against replay attacks.
- ⚙️ **STOCK_GROUP_N / EMAIL_GROUP_N Relationship Clarification** — Clearly defines the relationship with `STOCK_LIST` and provides a warning for email groups exceeding `STOCK_LIST` during configuration validation.
- 🗓️ **Gap Continuation Transfer Changed to Market Time Zone and Trading Calendar Judgment** (fixes #880) — Stock data existence checks no longer directly use server natural days but instead parse "latest reusable trading day" based on A-shares / Hong Kong stocks / U.S. stocks respective market time zones.
- 📨 **Single Stock Push Mode No Longer Concurrent Reuse of Shared Notification Instance** — `StockAnalysisPipeline.run()` now retains individual stock analysis concurrently, but moves notifications for `SINGLE_STOCK_NOTIFY=true` to the result collection side in serial sending.
- 🔇 **Real-time Market Data Degradation Hint Collapsed to Single Alert** — The main process no longer triggers a one-time real-time market data query when obtaining stock names, and only prompts that it has degraded to historical closing prices to continue analysis when all data sources are unavailable.
- 🔍 **A-shares Chinese News Search Restored Chinese Priority** — `search_stock_news()` now continues to try subsequent engines if the primary provider mainly returns English news in the first batch of results, and ranks Chinese news items to the front in the same batch.
- 🔒 **Concurrency Shared State Completion - Unified Locking** — Fixed a problem where shared state was missing unified locking during concurrent execution, avoiding data competition in multi-threaded scenarios.

### Tests

- 🧪 **Supplement Setting Page Version Information Regression Testing** — Added assertions for rendering version information on the Web setting page and covered the logic to automatically revert to build identifiers when the placeholder version `0.0.0` is present.
- 🧪 **UI Governance & Key Path Regression Reinforcement** — Supplemented testing for `SidebarNav`, `ChatPage`, `BacktestPage` components, and added UI governance guardians to prevent interactive elements from reintroducing native `title` attributes or old `input-terminal` styles causing reflows. Synchronized updates to smoke / markdown drawer validations, covering key main links after theme upgrades.

## [3.11.0] - 2026-03-27

### Release Highlights

- 🎨 **Web Workbench Completed One Round of UI Unification & Dual Theme Upgrade** — The homepage, Question Stocks, backtesting, holdings, and settings pages have been further consolidated with unified design tokens, input surfaces, and state expressions. A complete light theme has been added, and one-click switching between light/dark themes and persistent saving is supported.
- 🤖 **Bot / Agent Capability Reintegration to Main Branch** — Restored `/history`, `/strategies`, `/research` commands; `/ask` continues to support multi-stock comparison and combination perspectives. Deep Research, event monitoring, and schedule polling links have been reconnected to the main line capabilities.
- 🔒 **Security & Stability Synchronization Reinforcement** — Fixed the risk of `X-Forwarded-For` rate limiting bypass, restored the LiteLLM official PyPI installation path, Tushare initialization no longer depends on local SDKs, reducing vulnerabilities during Docker, desktop packaging, and environment reconstruction.
- 🖥️ **Refined daily usage details** — Fixed automatic completion submission for Hong Kong stocks on the homepage, screen flickering on the login page header, overlapping long stock names, and notification interruption when Telegram Markdown parsing failed.

### Added

- 🎨 **New Light Theme and Dual Theme Switching Released** — The Web Workspace now includes a complete light theme and supports one-click switching between light/dark modes in the sidebar. Theme selection is persisted and remains after page refresh.
- 🤖 **Reintroduced Agent / Bot Capabilities** — Issues `#648` / `#649` have been remerged into `main`: Bot restores `/history`, `/strategies`, `/research`, `/ask` retains multi-stock comparison and portfolio view; Deep Research and Event Monitor configurations are now visible and editable in the Web Settings page, and the schedule mode is reconnected to event alarm polling.

### Changed

- 🖥️ **Unified Core Pages to a Single Workspace Visual Language** — `Home / Chat / Backtest / Portfolio / Settings` have been consolidated into a shared design token, `input-surface` input system, empty state/error state expression and drawer mask semantics, reducing visual fragmentation and local private style drift.
- 💬 **Improved Question Stock Interaction Accessibility and Feedback** — The Question Stock page now includes conversation export, notification sending, message copying, history deletion, and follow-up context prompts; AI response operations no longer rely excessively on hover, and key buttons can be directly accessed on touch devices and small screens.
- 📊 **Continued Standardization of Backtesting and Position Pages** — The backtesting page's filtering controls, boolean states, results tables, and summary cards have been unified into shared input/state primitives; the position page’s import feedback, exchange rate refresh prompts, empty state and warning information are further consolidated into shared components, reducing page-level duplication.
- 🧭 **Navigation and page shell layer collaborative optimization** — Side menu theme switching, question stock completion of corner markers, mobile end drawer mask and main content scrolling contract further unified, homepage, question stock and backtesting in desktop and mobile views cut page experience more stable.

### Tests

- 🧪 **UI Governance and key path regression reinforcement** — Supplemented tests for `SidebarNav`, `ChatPage`, `BacktestPage` etc. components, and added UI governance guards to prevent interactive elements from reintroducing native `title` attributes or old `input-terminal` style reflows. Synchronized updates to smoke / markdown drawer related validations, covering key main links after theme upgrades.

### Fixed

- 🌗 **Web homepage default theme preset is set to dark** — `apps/dsa-web/index.html` now reads local saved theme preferences before React mounting; if no saved value exists, immediately sets `<html>` to `dark` and synchronizes `color-scheme`, avoiding the homepage and login page initial screens flashing with a light theme.
- 🔐 **Independent login page theme layer closure** — Login page input boxes, labels, toggle buttons and button text now use independent `--login-*` visual tokens, no longer inheriting global light/dark theme text colors; even if the browser caches a light theme, the login page remains stable dark visuals and blue password input behavior, avoiding password dots and text falling into black.
- 🖥️ **Homepage Hong Kong stocks code input fix** — The web homepage analysis input box can now correctly accept Hong Kong stocks codes and automatically select Hong Kong stocks items, supplementing `00700.HK` / `HK00700` format recognition, to avoid false alarms when submitting “Please enter a valid stock code or stock name”.

- 🔒 **Authentication rate limiting X-Forwarded-For value fix (CWE-345)** (#841 / #842) — `get_client_ip()` changed from taking the leftmost value of `X-Forwarded-For` to the rightmost value, preventing attackers from bypassing brute-force protection by forging header rotation rate limiting buckets; only affects deployments where `TRUST_X_FORWARDED_FOR=true` and single-tier trusted reverse proxies are used, multi-level proxy environments need to be evaluated according to deployment documentation.”
- 📦 **Restored LiteLLM Official PyPI Installation and Locked Security Upper Limit** — Reused the official PyPI installation path of `pip install litellm` in `requirements.txt`, while adding a security upper limit of `<1.82.7` to maintain the historical minimum requirement `>=1.80.10`, avoiding risks of installing removed versions `1.82.7`/`1.82.8`; The Windows desktop packaging script also synchronized back to the standard `pip install -r requirements.txt` link, reducing maintenance costs associated with special download branches.
- Telegram Markdown parsing failure reverts to plain text (fixes #850) — `src/notification_sender/telegram_sender.py` will now automatically remove the `parse_mode` and retry sending plain text if the Telegram return `HTTP 400` and contains `can't parse entities` / Markdown parsing error, avoiding notification failure due to content like `*ST`.
- A-shares same code real-time market data retains exchange prompts (fixes #852) — `DataFetcherManager` and `TushareFetcher` now retain explicit Shanghai and Shenzhen prompts such as `SZ000001` / `000001.SZ`, the old Tushare real-time market data downgraded branch no longer misinterprets Shenzhen's `000001` as the Shanghai Stock Exchange Index `sh000001`.
- Multiple agents' suboptimal buy points do not blindly copy ideal buy points (fixes #851) — When multiple intelligent body results lack independent `secondary_buy`, the dashboard now prioritizes displaying `N/A` instead of copying the `ideal_buy` value to be exactly the same, reducing misleading double buy point display.
- 🧩 **Tushare initialization no longer strongly depends on local SDK packages** — `TushareFetcher` now directly uses the built-in HTTP client to access Tushare Pro, without first `import tushare` during startup; fixed the issue of prematurely reporting `No module named 'tushare'` due to missing the `tushare` package after Docker, desktop packaging, or environment reconstruction, and supplemented corresponding regression tests.
- `daily_analysis` workflow completes `DEEPSEEK_API_KEY` mapping — GitHub Actions daily analysis workflow now correctly transmits `DEEPSEEK_API_KEY`, avoiding the situation where cloud tasks have keys configured but cannot obtain the corresponding environment variables at runtime.
- Historical list too long stock names truncated and hovered display (fixes #815) — Historical lists with excessively long stock names are now automatically truncated (English 15/Chinese 8/mixed 10 characters), displaying the truncated result by default, and showing the full name on hover; solves the problem of stock names overlapping with right-side status label text in a 1920x1080 resolution. Added `stockName.ts` tool function and corresponding test.

### Docs

- README donation entry updated to WeChat QR code — The sponsorship entry in README and English instructions is updated to a WeChat QR code material, keeping the display consistent.

## [3.10.1] - 2026-03-24

### Added

- Web-end analysis push notification switch ( #808) — A "Push Notification" checkbox has been added next to the Analysis button on the homepage, which is checked by default; when unchecked, this analysis will not send Telegram/Enterprise WeChat notifications. API `POST /api/v1/analysis/analyze` adds a `notify` field (`bool`, default `true`), and if not passed, the behavior is consistent with before, Bot and scheduled tasks are unaffected.

### Changed

- Question Stock / Backtesting page layout and shell layer collaborative optimization — Unified Chat / Backtest page container, shared UI state and followed question-answer interaction path, removed some hardcoded height restrictions, making the filling and scrolling behavior within the navigation framework more coherent.
- Global visual and shared components continue to converge — The Light theme introduces a dynamic HSL shadow system, unifies the side bar active state, warning component contrast and chat bubble styles, and consolidates some scattered inline styles into semantic CSS variables to improve consistency and maintainability.

### Fixed

- System Settings Smart Import File Selection Recovery — Fixes the unresponsive click issue of the two buttons "Select Image" / "Select File" in the "System Settings > Basic Settings > Smart Import" module.
- 🖥️ **Mobile Scroll and Layer Interaction Hierarchy Fix** — Resolved z-index conflicts that caused the theme switching menu to be obscured by main content on mobile, and restored normal vertical scrolling in long report scenarios on the homepage, without affecting existing scrolling behavior on other pages.
- 🧾 **Markdown Plain Text Copy Cleaning Enhancement** — Improved the plain text export algorithm; copying analysis reports will more stably clear table delimiters and other Markdown traces, improving the purity of sharing and archiving content.
- 🧠 **Trading Philosophy Injection Coverage for Legacy + Agent Full-Link**（#810）— `GeminiAnalyzer`, single Agent mode, and skill-aware Prompt now share the same strategy injection state; only fall back to the built-in default `bull_trend` will retain the old trend-based prompts, explicit strategy selection or custom default skill will no longer be secretly overlaid with `MA5>MA10>MA20` bullish baseline.
- 🛠️ **Backend CI Dependency Installation Link Stabilization**（#835）— Split the backend gate stage, added retry for dependency installation, and adjusted the source of `litellm` used in CI to a more stable GitHub source to reduce backend gate occasional failures caused by jittery dependency parsing.
- Improved LiteLLM Windows desktop build compatibility. The `scripts/build-backend.ps1` now filters LiteLLM GitHub sources from `requirements.txt`, downloads corresponding tag zipballs to remove the optional `enterprise/` directory, and installs them, bypassing issues caused by Poetry wheel builds on Windows runners mistakenly packaging directories as files. Additionally, it incorporates `pip install` exit code checking to prevent secondary errors from appearing only during the subsequent `python-multipart` validation stage following dependency installation failures.

### Tests

- 🧪 **Ask Stock / Backtesting / Intelligent Import Regression Coverage Completion** — Synchronized updates to E2E smoke test expectations, supplemented `DashboardStateBlock`, Chat page, intelligent import file selection and related interaction assertions, ensuring that key paths remain stable through recent UI adjustments.

## [3.10.0] - 2026-03-24

### Release Highlights

- 🔎 **Automatic completion and indexing tool expanded to three markets** — Completion index generation link now covers A-shares, Hong Kong stocks, and U.S. stocks; new Tushare stock list retrieval tools and more complete static index data were added, allowing the homepage search entry to move from "usable" to "more comprehensive and stable".
- 🖥️ **Dashboard and report viewing experience continued to shrink** — The homepage Dashboard panel, status boundary, font hierarchy, and complete report table density have been unified in one round; report details have also completed Markdown/plain text copy and more reliable button interactions, reducing friction when viewing and sharing historical reports.
- 🤖 **Agent skill and market semantic boundaries are clearer** — Skill bundles, default strategies, backtesting summary semantics, and compatible interfaces have been further converged; at the same time, Prompt no longer defaults to writing A-shares context, U.S. stocks and Hong Kong stocks analysis can generate more appropriate content according to their respective market rules.
- ⏰ **Scheduled and desktop configuration capabilities are closer to real usage scenarios** — The desktop supports `.env` import and export; `python main.py --schedule --stocks ...` no longer brings stock snapshot errors into subsequent plan execution, and scheduled tasks will follow the latest saved `STOCK_LIST`.
### Added

- 💾 **Desktop-end `.env` backup/restore entry** (#754) — A new ‘Export .env’ / ‘Import .env’ button has been added to the system settings page in desktop mode, allowing you to directly back up your currently saved configuration or restore the key-value pairs from a backup file into the current desktop-end `.env`; import uses existing `config_version` conflict protection and runtime reload link, without changing the existing portable mode path of the desktop end.
- 📊 **Tushare stock list retrieval tool** — A new `scripts/fetch_tushare_stock_list.py` has been added to support retrieving A-shares, Hong Kong stocks, and U.S. stocks lists from Tushare Pro and saving them as CSV files; it includes pagination reading, intelligent rate limiting, error handling, and progress prompts; a corresponding usage document `docs/TUSHARE_STOCK_LIST_GUIDE.md` has also been added.
- 🔎 **Index generation script multi-market support** — `generate_index_from_csv.py` rebuilt to support Tushare and AkShare dual data sources, covering A-shares、Hong Kong stocks、U.S. stocks markets; added market-specific aliases (A-shares、Hong Kong stocks common aliases, U.S. stocks common stock English abbreviations); added `--source` parameter to switch data source、`--test` parameter for validation mode; strictly filter U.S. stocks DUMMY records.
- 🔎 **Index generation script enhanced** — `generate_stock_index.py` added `--test`/`-t` test mode and `--verbose`/`-v` detailed output mode, added market distribution statistics, optimized JSON output format.
- 📋 **Complete report support dual-mode copy** — Historical report details header added "Copy Markdown source" and "Copy plain text" tool buttons; the former preserves the original Markdown structure, the latter removes common Markdown formatting symbols, facilitating sharing、archiving、and cross-report comparison. Copy button text will follow `REPORT_LANGUAGE` to maintain consistency between Chinese and English.
- 🧩 **Individual stock analysis page complete association sector display**（#669）— A-shares analysis path now writes `belong_boards` to `fundamental_context` / `fundamental_snapshot` once, structuring report details and synchronizing the addition of `belong_boards` and `sector_rankings` fields; the Web individual stock analysis page's first screen can directly display its sector and whether it hits the daily sector rise-fall ranking; fail-open hidden when no data is available, without affecting the existing analysis main process.

### Changed

- 🖥️ **Dashboard panel unification (PR7-2)** — Added `DashboardPanelHeader` and `DashboardStateBlock` as common components for historical、report、news、task and transparency panels; unified panel title hierarchy、loading/empty state/error state and CSS variable tokens.
- Implemented `useHomeDashboardState` hook to centralize `stockPoolStore` state selection logic within the `HomePage`, removing redundant local state derivations and callback definitions.
- 🧭 **Agent skill unified to single configuration semantics** — Multi-Agent runtime、API、Web chat and configuration metadata have been consolidated around the `skill` concept; `/api/v1/agent/skills` becomes the main discovery entry, `AGENT_SKILL_*` is the main configuration face, and built-in skill metadata also starts to declare default enable status, sorting priority, market regime tag information, reducing implicit coupling scattered in code defaults.
- 🔎 **Automatic completion index data update** — Regenerate `stocks.index.json`, covering A-shares、Hong Kong stocks、U.S. stocks three markets, improving automatic completion coverage.
- 🧾 **Dashboard font and complete report table density fine-tuned** — Consolidate the sidebar on the homepage, empty state, and historical operation area fonts, and adjust the inner margins of the complete Markdown report tables `th/td` to a tighter 4-6px range, making the information density more consistent with the existing Dashboard visual rhythm.

### Fixed

- ⏰ **Scheduled mode no longer locks startup CLI stock snapshot** — `python main.py --schedule --stocks ...` will now not allow subsequent scheduled execution to inherit the old stock list from startup; each time the scheduled task is triggered, it will re-read the latest saved `STOCK_LIST`, ensuring that watchlist stocks configured in WebUI or `.env` can participate in subsequent pushes.
- 🌍 **LLM Prompt injected with stock market context dynamically** — The analysis link no longer writes market rules as A-shares; the system prompt will identify A-shares、Hong Kong stocks or U.S. stocks based on stock code and inject corresponding role descriptions and trading rule prompts, reducing the problem of inconsistent statements or conclusions appearing across markets.
- 🔎 **U.S. stocks automatic completion ticker deduplication** — `generate_index_from_csv.py` will first fold reusable U.S. stocks tickers by `ts_code` when importing Tushare `us_basic` CSV, prioritizing the records that are more likely to remain in use, and avoiding duplicate `canonicalCode` appearing in `stocks.index.json` so that Web automatic completion can display historical names or ambiguous codes.
- 🧾 **Web report details copy interaction stability fix** (#749) — Added `ReportDetails` support to ensure the "original analysis results / analysis snapshot" copy button is clickable and avoids being covered by underlying JSON content. Updated copy prompts for both panels to display independently, eliminating misleading feedback when one button shows "Copied" after another is clicked.
- The `get_skill_backtest_summary` function now requires explicit input of the `skill_id`. Missing values return clear validation prompts. When skill-level summaries are not persisted in the repository, a clear unsupported/info response is returned, and compatible `normalized` and `*_pct` fields are retained to prevent misleading Agents or users with overall metrics.
- 🔧 **Stabilized Default Skill Selection and Compatibility Layer Behavior** — `allowed-tools` will continue to serve only as `SKILL.md` bundle metadata, no longer leaking to runtime tool selection; `/api/v1/agent/strategies` restored old payload shape; explicitly passing `skills: []` clears stale context; when a user explicitly selects a strategy skill, it no longer secretly overlays the default bull-trend, and when `AGENT_SKILLS` is empty, it defaults to a single main default skill.

### Tests

- 🧪 **Dashboard Component Test Coverage Expansion (PR7-2)** — Added tests for `ReportNews` and `TaskPanel`. Enhanced assertions in `HistoryList`, `ReportDetails`, `HomePage`, `useDashboardLifecycle`, and `stockPoolStore`, including rollback, mobile drawer, and task lifecycle scenarios.
- 🧪 **Multi-Market Index Generation Test Completion** — Added `tests/test_generate_index_from_csv.py`, covering Tushare/AkShare dual data source parsing, multi-market judgment, U.S. stocks DUMMY filtering and duplicate ticker deduplication core paths.
- 🧪 **Sector Association Writing & API Contract Regression** — Added `tests/test_pipeline_related_boards.py`, and supplemented historical and analytical interface contract testing to ensure `belong_boards` / `sector_rankings` only perform incremental expansion while maintaining fail-open.
- 🧪 **Scheduled Mode Stock List Semantic Regression Test** — Added `tests/test_main_schedule_mode.py`, covering scenarios where the scheduled mode ignores the `--stocks` snapshot at startup and single runs retain CLI stock coverage.

### Docs

- 📘 **New Tushare Stock List Tool Documentation** — Added `docs/TUSHARE_STOCK_LIST_GUIDE.md`, explaining how to use the stock list retrieval tool, data formats, and common issues.
- 🌍 **Complete Bilingual Explanation of Scheduled Mode and Associated Sectors** — `docs/full-guide.md` / `docs/full-guide_EN.md` now clearly state that scheduled mode will re-read the `STOCK_LIST` before each execution and synchronize the explanation of individual stock association with sector display, reducing configuration expectation discrepancies.
- 🧭 **Adjust Agent terminology text** — README, bilingual documents, settings page and question-stock interface continue to use “strategy” as the main user entry name, while supplementing `skill` as a unified internal naming, reducing migration period understanding costs.

## [3.9.0] - 2026-03-20

### Release Highlights

- 🤖 **Model link and report language more flexible** — Agent can now independently select model links through `AGENT_LITELLM_MODEL`, ordinary analysis and Agent reports can output unified languages through `REPORT_LANGUAGE=zh|en` to reduce “English content + Chinese shell” mixed formatting issues, and teams can separately weigh the cost, speed and ability of main analysis and Agents.
- 🔎 **Homepage analysis experience completed a round of closed-loop optimization** — The homepage adds A-shares automatic completion, supports code, Chinese name, pinyin and alias retrieval; at the same time, Dashboard status is consolidated into a unified store, the interaction between historical data, reports, news and Markdown drawers is more stable, and “Ask AI” follow-up questions will also prioritize carrying the current report context.
- 💬 **Expanded notification and search capabilities** — Added Slack as a notification channel; SearXNG can automatically discover public instances and use controlled polling for degradation when no self-hosted instance is configured; Tavily fixed the timeliness link after the timeout, and strict timeliness filtering will no longer lose effective results.
- 💼 **Improved holding and market review link stability** — A-shares market review optionally integrates TickFlow to enhance index and percentage change statistics; holdings ledger writes are serialized to reduce concurrency over-sell windows; currency refresh entry and disabled state prompts are clearer, reducing user misinterpretations.

### Added

- 🔎 **Web stock auto-complete MVP** — The homepage analysis input box now includes local index-driven auto-completion supporting stock codes, Chinese names, pinyin, and aliases matching; selecting a candidate submits the canonical code and passes `stock_name`, `original_query`, and `selection_source` to the analysis request, task status, and SSE events; if index loading fails, it automatically reverts to the old input mode without interrupting existing query flows. Synchronized static index loader, index generation script, and frontend/backend contract tests. Developed in stages, initially supporting A-shares.
- 💬 **Slack notification channel** — Added Slack native notification support, supporting both Bot Token and Incoming Webhook access methods. When configuring, the Bot API is prioritized to ensure text and images are sent to the same channel. The Bot Token mode supports image uploads (raw body POST, without multipart). New configuration options `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`, `SLACK_WEBHOOK_URL` have been added, and GitHub Actions workflows have been synchronized to pass Secrets.
- 🌍 **report output language configurable** (Issue #758) — Added `REPORT_LANGUAGE=zh|en`, default `zh`; language settings will sync with regular analysis and Agent Prompt, and override Markdown/Jinja templates, notification fallback, historical/API `report_language` metadata, and Web report page fixed text, to avoid mixed output of "English content + Chinese shell".
- 🚀 **Agent Decoupled from Standard Analysis Models** (Issue #692) – Added `AGENT_LITELLM_MODEL` (empty inheritance of `LITELLM_MODEL`, prefixed `openai/<model>` normalization); Agent execution links now utilize the `/api/v1/agent/models` `is_primary/is_fallback` markers based on actual model paths; System configuration and startup validation have been completed with a check for `AGENT_LITELLM_MODEL`'s `unknown_model/missing_runtime_source`; The Web settings page now includes Agent primary model selection synchronized with channel runtime configurations.
- 🔎 **SearXNG public instance automatic discovery and controlled polling** (#752) — Added `SEARXNG_PUBLIC_INSTANCES_ENABLED`, defaulting to fetching public instance lists from `searx.space` when `SEARXNG_BASE_URLS` is not configured, and selecting instances in a controlled polling order; within the same request, automatic switching to the next instance if timeouts, connection errors, HTTP non-200 status codes, or invalid JSON are encountered. Users with self-hosted instances maintain their original priority and semantics unchanged; the `daily_analysis` GitHub Actions workflow also supports explicitly passing this switch and displays its current state in startup logs.
- 📈 **TickFlow market review enhancement** (#632) — Added optional `TICKFLOW_API_KEY`; on A-sharesmarket review, the primary index market data prioritizes TickFlow; if the current TickFlow package supports target pool queries, market rise and fall statistics also prioritize TickFlow. Failure or insufficient permissions immediately revert to the existing `AkShare / Tushare / efinance` chain; sector rise and fall rankings maintain their reversion order. The access layer adapts to real SDK contracts: primary index queries batch fetch based on request limits, and converts TickFlow's proportional `change_pct` / `amplitude` into the project’s percentage format.

### Changed

- **Dashboard state slice and workspace closure** — moved Home / Dashboard state into `stockPoolStore`, consolidated history selection, report loading, task syncing, polling refresh, and markdown drawer handling under a single state slice.
- **Dashboard panel standardization** — kept the current dashboard layout contract stable while unifying history, report, news, and markdown presentation with shared tokens, standardized states, and bounded in-panel scrolling for the history list.
- **Dashboard-to-chat follow-up bridge** — routed “Ask AI” follow-ups through report-context hydration instead of direct cross-page state coupling, while keeping chat sends usable when enriched history context is still loading.
- 💼 **Position Book concurrent write serialization** (#742) — Position source events writing/deleting now acquire serial write locks in SQLite to reduce the window for overflowing transactions being written to the ledger; the direct position write interface returns `409 portfolio_busy` when competing for locks, CSV import maintains sequential submission and counts busy items in `failed_count`.
- 💱 **Portfolio Page Currency Manual Refresh Entry Completed** ( #748 ) — Web `/portfolio` page now displays a "Refresh Rate" button in the "Rate Status" card, directly calling existing `POST /api/v1/portfolio/fx/refresh` interface; after refresh, it only reloads snapshots and risk data, and provides inline summary feedback of "Updated / Still stale / Refresh failed", reducing user misunderstanding of `fxStale` lingering.

### Fixed

- 🔎 **Web Automatic Completion Enter Submit Semantic Correction** — stock auto-completion no longer defaults to highlighting the first item when search candidates are hit; when candidate list is expanded but the user has not explicitly selected an item with arrow keys or mouse, pressing Enter will continue to submit the original input, avoiding the first candidate silently overriding manual input.
- 🌍 **Completed `REPORT_LANGUAGE` localization initialization for history display.** The `Config` follows "real environment variable first, then `.env` fallback" semantics during startup, outputting explicit warnings on conflicts. Additionally, the English detail response at `/api/v1/history/{id}` synchronizes localized `sentiment_label`, and correctly identifies the risk level emoji (`bias_status`) to avoid mixed Chinese and English content or false alarms (including `🚨Safe`).
- 📰 **Tavily News Retrieval Release Time Mapping Fix** (#782) — Tavily now explicitly uses `topic="news"` in both stock news and strict timeliness intelligence dimensions, and is compatible with `published_date`/`publishedDate` release time fields. This fix resolves an issue where results were incorrectly marked as `drop_unknown` during subsequent hard filtering. Additionally, analytical dimensions such as institutional analysis, performance expectations, and industry analysis have been restored to broad-source searching, no longer unified into a news mode. `published_date` `publishedDate` `drop_unknown` `topic="news"`
- Fixed semantic correction when `PORTFOLIO_FX_UPDATE_ENABLED=false`: `POST /api/v1/portfolio/fx/refresh` now returns explicit `refresh_enabled=false` and `disabled_reason`, and the Web `/portfolio` page clearly indicates "Online rate refresh is disabled", avoiding false alerts for ranges with no refreshable rates."
- 🤖 **Agent timeout and config hardening** — `AGENT_ORCHESTRATOR_TIMEOUT_S` now also protects the legacy single-agent ReAct loop, parallel tool batches stop waiting once the remaining budget is exhausted, and invalid numeric `.env` values fall back to safe defaults with warnings instead of crashing startup.
- 🌐 **CORS wildcard + credentials compatibility** — `CORS_ALLOW_ALL=true` no longer combines `allow_origins=["*"]` with credentialed requests, avoiding browser-side cross-origin failures in demo/development setups.
- 🧭 **Unavailable Agent settings hidden from Web UI** — Deep Research / Event Monitor controls are now treated as compatibility-only metadata in the current branch and are removed from the Settings page to avoid exposing non-functional toggles.

### Docs

- Added Ollama local model configuration instructions, updating `README.md` and `docs/README_EN.md` (Fixes #690)
- Improved Ollama configuration instructions: `docs/full-guide.md` / `docs/full-guide_EN.md`. Updated environment variable table and Note supplement `OLLAMA_API_BASE` to avoid English users mistakenly believing that Ollama cannot be used as a standalone configuration entry. Merged duplicate `OLLAMA_API_BASE` entries into a single item.
- Clarified document synchronization governance boundaries: Added default synchronization rules between `README.md`, topic documents, bilingual documents, and delivery instructions to reduce subsequent document drift.

## [3.8.0] - 2026-03-17

### Release Highlights

- 🎨 **Web Interface Completed a Round of Skeleton Upgrade** — The new App Shell, side navigation, theme capabilities, login, and system settings flow have been strung together into a unified experience. Desktop background loading has also completed alignment.
- 📈 **Enhanced analytical context** — Added social sentiment intelligence for U.S. stocks; A-shares completed structured contextual data for financial reports and dividends; Tushare newly integrated with call distribution and industry sector rise/fall data.
- 🔒 **Improved stability and configuration compatibility** — Logging out will immediately invalidate old sessions, scheduled startup to maintain compatibility with old configurations, `MAX_WORKERS` adjustments in running instances, and clearer feedback for news timeliness windows.
- 💼 **More complete holding correction link** — Oversold conditions are now proactively intercepted, erroneous transactions/funds flows/company behaviors can be directly deleted and rolled back to facilitate the repair of dirty data.

### Added

- 📱 **U.S. Stocks Social Sentiment Intelligence** — New Reddit / X / Polymarket social media sentiment data source added to provide real-time social heat, sentiment scores, and mention volume indicators for U.S. stocks analysis. This is fully optional and only activates for U.S. stocks after configuring `SOCIAL_SENTIMENT_API_KEY`.
- Added `fundamental_context.earnings.data` fields for `financial_report` and `dividend`. Dividend calculations are now standardized using a "pre-tax cash dividend" approach, including the addition of `ttm_cash_dividend_per_share` and `ttm_dividend_yield_pct`. The `details` field in analysis/historical APIs has been extended with optional `financial_report` and `dividend_metrics` fields, maintaining fail-open behavior and backward compatibility.
- 🔍 **Added access to Tushare stock and sector concept sector interface** — Added the ability to retrieve data on chip distribution and sector concept sector gains/losses, and unified them into a configurable data source priority. Defaults to distinguishing intra-day/after-hours trading days by Shanghai time, prioritizing the Tushare Tonghu Network API, and falling back to the Dongtai API if necessary.
- The Web UI base skeleton has been upgraded, rebuilding shared design tokens and common components. New features include App Shell, Theme Provider, and Side Navigation, along with synchronized adjustments to the Electron background loading for a unified experience across Web and Desktop.
- 🔐 **Redesigned Login and System Settings Workflow** — Refactored Login, Settings, and Auth management flows, adding explicit authentication setup-state handling and aligning Web endpoint behavior with runtime authentication configuration APIs.
- 🧪 **Enhanced Frontend Regression and Smoke Coverage** — Added and expanded component tests and Playwright smoke coverage for key paths including login, homepage, chat, mobile Shell, settings page, and backtesting entry.

### Changed

- 🧭 **Added new Shell layout contract for page access** — Home, Chat, Settings, Backtest have been unified into the new page container, drawer and scrolling agreement to reduce UI migration page behavior inconsistency.
- 💾 **Improved stability of settings page state synchronization** — Optimized draft retention, direct save synchronization and conflict resolution, reducing module-level save after and before configuration status inconsistencies.
- 🎭 **Returned login page visual baseline** — The login page has been restored to the visual baseline of branch `006`, while retaining the new authentication state logic and unified form interaction model.
- 🏛️ **Reinforced AI Collaboration Governance Asset Management** — Consolidated and strengthened consistency constraints for `AGENTS.md`, `CLAUDE.md`, Copilot directives, and validation scripts to reduce the long-term drift risk of governance assets.

### Added

- **Web UI foundation refresh** — rebuilt shared design tokens and common primitives, introduced the app shell, theme provider, sidebar navigation, and Electron loading background alignment for the upgraded desktop/web experience
- **Settings and auth workflow overhaul** — rebuilt the Login, Settings, and Auth management flows, added explicit auth setup-state handling, and aligned the Web UI with the runtime auth configuration APIs
- **UI regression coverage and smoke checks** — expanded targeted frontend tests and added Playwright smoke coverage for login, home, chat, mobile shell, settings, and backtest entry flows

### Changed

- **Shell-driven page integration** — aligned Home, Chat, Settings, and Backtest with the new shell layout contract so routing, drawer behavior, and page-level scrolling are consistent during the UI migration
- **Settings state consistency** — refined draft preservation, direct-save synchronization, and conflict handling so module-level saves no longer leave the page out of sync with backend config state
- **Login visual baseline** — restored the login page visual treatment to the established `006` branch baseline while keeping the newer auth-state logic and unified form interaction model

### Fixed

- ⏰ **Scheduled Start Immediate Execution Compatible with Old Configurations** (Issue #726) — `SCHEDULE_RUN_IMMEDIATELY` not set will revert to reading `RUN_IMMEDIATELY`, fixing compatibility issues with old `.env` files in scheduled mode after upgrades; also clarified the scope of the two configuration items in `.env.example` / README and noted that Outlook / Exchange force OAuth2 currently does not support it.
- 🧵 **Runtime `MAX_WORKERS` Configuration Effectiveness and Interpretability Enhanced** (Issue #633) — Fixed asynchronous analysis queue issues not syncing according to `MAX_WORKERS`; added task queue in-place synchronization mechanism (idle immediate effect, busy delayed), and clearly outputted `profile/max/effective` in setting save feedback and running logs to reduce the misunderstanding of "parameter not effective".
- 🔐 **Session invalidation now immediate** — `POST /api/v1/auth/logout` Now rotating the session secret to prevent old cookies from continuing to access protected interfaces after logout. Browser tabs and concurrent pages are also synchronized logged out. When authentication is enabled, this interface no longer belongs to the anonymous whitelist, and unauthenticated requests will return `401`.
- 🧮 **Tushare sector/pickup rate limiting and cross-day caching fixed** — The new `trade_cal`, industry sector ranking, and pickup distribution links have been unified into `_check_rate_limit()`. The transaction calendar cache has been changed to refresh by natural days to avoid the service continuing to run across days and using old transaction day judgment dates for data retrieval.
- 💼 **Holding inventory oversell interception and error ledger recovery** (#718) — `POST /api/v1/portfolio/trades` now checks sellable quantity before writing, returns `409 portfolio_oversell` if oversold. The holding page has added the ability to delete trades/funds/company behavior, which synchronizes the invalidation of warehouse cache and future snapshots after deletion, making it easy to recover from error ledgers.
- 📧 **Email Sender Name Encoding** (#708) — Email notifications now automatically perform RFC 2047 encoding on `EMAIL_SENDER_NAME` containing Chinese, and supplement SMTP connection cleanup in abnormal paths to fix sending failures caused by `'ascii' codec can't encode characters` under GitHub Actions / QQ SMTP.
- 🐛 Hong Kong stocks agent real-time market data deduplication and fast routing — Unified code normalization rules for `HK01810`/`1810.HK`/`01810` etc. Hong Kong stocks; change Hong Kong stocks real-time market data to directly use the single `akshare_hk` path to avoid triggering duplicate failures based on A-shares source priority; Agent runtime adds short-circuit caching for tools with explicit `retriable=false` to reduce repeated failed calls in the same analysis round.
- 📰 News timeliness hard filtering and strategy windowing (#697) — Added `NEWS_STRATEGY_PROFILE` (`ultra_short/short/medium/long`) and unified calculation with `NEWS_MAX_AGE_DAYS`; search results execute time hard filtering after return (excluding unknown times, excluding out-of-window, only tolerant of 1 day in the future), and add the same constraint to the historical fallback link to avoid old news entering 'latest dynamics / risk alerts'.

### Docs

- ☁️ New cloud server web interface deployment and access tutorial (Fixes #686) — Supplement the explanation from cloud deployment to external access, reducing the remote self-hosting threshold.
- 🌍 Complete English document indexing and collaborative documents — Added English document index, contribution guide, Bot command documentation, and supplemented bilingual issue / PR templates in Chinese and English, making it easier for Chinese and English collaboration and external contributors to understand the project entry.
- 🏷️ Supplement Trendshift badge in local README — Synchronize adding new capability entry indicators in multi-language READMEs to reduce inconsistencies between Chinese and English explanations.

## [3.7.0] - 2026-03-15

### Added

- 💼 Holding management P0 full functionality online (#677, corresponding Issue #627)
  - **Core ledger and snapshot closure**: Added core data models and API endpoints for accounts, transactions, cash flow, corporate behavior, holding cache, daily snapshots; supports FIFO / AVG dual cost methods backtesting; the same-day event order is fixed as `cash → corporate behavior → transaction`; Holding snapshot writing uses atomic transactions.
  - **Broker CSV import**: Supports initial adaptation of Haitong Securities / CITIC Securities / Zhonghang Securities, including column name aliases and compatibility; two-stage interface (preview parsing + confirm submission); idempotent deduplication based on `trade_uid` priority and key-field hash fallback; preserves stock codes with leading zeros.
  - **Combination risk report**: Concentrated risk (Top Positions + A-shares sector), historical backtest monitoring (supports missing snapshot filling), stop-loss proximity warning; unified multi-currency conversion to CNY; when failure occurs, revert to the most recent successful exchange rate and mark it as stale.
  - **Web holding page** (`/portfolio`): Combination overview, holding details, concentrated risk pie chart, risk summary, combination / single account switching; manual input of transactions / funds flow / corporate behavior; embedded account creation entry; CSV parsing + submission closure and broker selector.
  - **Agent holding tool**: Added `get_portfolio_snapshot` data tool, default compact summary, optional holding details and risk data.
  - **Event Query API**：Added `GET /portfolio/trades`, `GET /portfolio/cash-ledger`, `GET /portfolio/corporate-actions`，supports date filtering and pagination.
  - **Expandable Parser Registry**：Application-level shared registry, supports runtime registration of new brokers; Added `GET /portfolio/imports/csv/brokers` discovery interface.

- 🎨 **Frontend Design System & Atomic Component Library**（#662）
  - Introduced progressive dual-theme architecture (HSL variable design token), cleaned up historical Legacy CSS; Refactored Button / Card / Badge / Collapsible / Input / Select etc. 20+ core components; Added `clsx` + `tailwind-merge` class merging tool; Improved readability of history, LLM configuration pages.

- ⚡ **Analysis API Asynchronous Contract & Startup Optimization**（#656）
  - Standardized `POST /api/v1/analysis/analyze` asynchronous request return contract; Optimized service startup auxiliary logic; Fixed frontend report type union definition and backend response alignment issue.

### Fixed

- 🔔 **Discord Environment Variable Backward Compatibility** (#659): Added `DISCORD_CHANNEL_ID` → `DISCORD_MAIN_CHANNEL_ID` fallback reading at runtime; historical configuration users can restore Discord Bot notifications without modification; all related documentation and `.env.example` are aligned.
- 🔧 GitHub Actions Node 24 Upgrade (#665): Upgraded all official GitHub actions to Node 24 compatible versions, eliminating Node.js 20 deprecation warnings in CI logs (affecting mandatory upgrade window on 2026-06-02).
- 📅 Holding Page Default Date Localization: Manual entry forms now use local time (`getFullYear/Month/Date`), fixing date offset issues for UTC-N timezone users in the evening.
- Reinforced CSV import deduplication logic: included trade row number as a distinguishing factor to ensure legitimate split trades are not incorrectly merged; also persisted hash when `trade_uid` exists to prevent duplicate writes from mixed sources.

### Changed

- `POST /api/v1/portfolio/trades` returns `409` when there is a `trade_uid` conflict within the same account.
- Added `sector_concentration` field (incremental expansion) to position risk response; the original `concentration` field remains unchanged.
- Analysis API `analyze` Interfacing heterobic contract documentation; joint update of front-end reporting type.

### Tests

- Add a core service test (FIFO / AVG part sold, sequence of events on the same day, repeat) `trade_uid` returns 409, snapshot API contract.
- Adds a new CSV import equation, a valid cut-off transaction, deweighting, risk threshold boundary, exchange rate downgrading behaviour test.
- Add Agent `get_portfolio_snapshot` Tools call tests.
- Add an API recede test.

## [3.6.0] - 2026-03-14

### Added
- 📊 **Web UI Design System** — implemented dual-theme architecture and terminal-inspired atomic UI components
- 📊 **UI Components Refactoring** — integrated `clsx` and `tailwind-merge` for robust class composition across Web UI

- 🗑️ **History batch deletion** — Web UI now supports multi-selection and batch deletion of analysis history; added `POST /api/v1/history/batch-delete` endpoint and `ConfirmDialog` component.
- 🔐 **Auth settings API** — new `POST /api/v1/auth/settings` endpoint to enable or disable Web authentication at runtime and set the initial admin password when needed
- Openclaw Skill Integration Guide - Add [docs/openclaw-skill-integration.md] (openclaw-skill-integration.md) to explain how to call DSA API through openclaw Skill
- ⚙️ **LLM channel protocol/test UX** — `.env` and Web settings now share the same channel shape (`LLM_CHANNELS` + `LLM_<NAME>_PROTOCOL/BASE_URL/API_KEY/MODELS/ENABLED`); settings page adds per-channel connection testing, primary/fallback/vision model selection, and protocol-aware model prefixing
- 🤖 **Agent architecture Phase 0+1** — shared protocols (`AgentContext`, `AgentOpinion`, `StageResult`), extracted `run_agent_loop()` runner, `AGENT_ARCH` switch (`single`/`multi`), config registry entries
- 🔍 **Bot NL routing** — two-layer natural-language routing: cheap regex pre-filter (stock codes + finance keywords) → lightweight LLM intent parsing; controlled by `AGENT_NL_ROUTING=true`; supports multi-stock and strategy extraction
- 💬 **`/ask` multi-stock analysis** — comma or `vs` separated codes (max 5), parallel thread execution with 150s timeout (preserves partial results), Markdown comparison summary table at top
- 📋 **`/history` command** — per-user session isolation via `{platform}_{user_id}:{scope}` format (colon delimiter prevents prefix collision); lists both `/chat` and `/ask` sessions; view detail or clear
- 📊 **`/strategies` Common** — questions capable of strategy YamL grouped by typegory with trend/form/reverse/framework
- 🔧 **Backtest summary tools** — `get_strategy_backtest_summary` and `get_stock_backtest_summary` registered as read-only Agent tools
- ⚙️ **Agent auto-detection** — `is_agent_available()` auto-detects from `LITELLM_MODEL`; explicit `AGENT_MODE=true/false` takes full precedence
- 🏗️ **Multi-Agent orchestrator (Phase 2)** — `AgentOrchestrator` with 4 modes (`quick`/`standard`/`full`/`strategy`); drop-in replacement for `AgentExecutor` via `AGENT_ARCH=multi`; `BaseAgent` ABC with tool subset filtering, cached data injection, and structured `AgentOpinion` output
- 🧩 **Specialised agents (Phase 2-4)** — `TechnicalAgent` (8 tools, trend/MA/MACD/volume/pattern analysis), `IntelAgent` (news & sentiment, risk flag propagation), `DecisionAgent` (synthesis into Decision Dashboard JSON), `RiskAgent` (7 risk categories, two-level severity with soft/hard override)
- 📈 **Strategy system (Phase 3)** — `StrategyAgent` (per-strategy evaluation from YAML skills), `StrategyRouter` (rule-based regime detection → strategy selection), `StrategyAggregator` (weighted consensus with backtest performance factor)
- 🔬 **Deep Research agent (Phase 5)** — `ResearchAgent` with 3-phase approach (decompose → research sub-questions → synthesise report); token budget tracking; new `/research` bot command with aliases (`/deep-research`, `/deepsearch`)
- 🧠 **Memory & calibration (Phase 6)** — `AgentMemory` with prediction accuracy tracking, confidence calibration (activates after minimum sample threshold), strategy auto-weighting based on historical win rate
- 📊 **Portfolio Agent (Phase 7)** — `PortfolioAgent` for multi-stock portfolio analysis (position sizing, sector concentration, correlation risk, cross-market linkage, rebalance suggestions)
- 🔔 **Event-driven alerts (Phase 7)** — `EventMonitor` with `PriceAlert`, `VolumeAlert`, `SentimentAlert` rules; async checking, callback notifications, serializable persistence
- ⚙️ **New config entries** — `AGENT_ORCHESTRATOR_MODE`, `AGENT_RISK_OVERRIDE`, `AGENT_DEEP_RESEARCH_BUDGET`, `AGENT_MEMORY_ENABLED`, `AGENT_STRATEGY_AUTOWEIGHT`, `AGENT_STRATEGY_ROUTING` — all registered in `config.py` + `config_registry.py` (WebUI-configurable)

### Changed
- 🔐 **Auth password state semantics** — stored password existence is now tracked independently from auth enablement; when auth is disabled, `/api/v1/auth/status` returns `passwordSet=false` while preserving the saved password for future re-enable
- 🔐 **Auth settings re-enable hardening** — re-enabling auth with a stored password now requires `currentPassword`, and failed session creation rolls back the auth toggle to avoid lockout
- ♻️ **AgentExecutor refactored** — `_run_loop` delegates to shared `runner.run_agent_loop()`; removed duplicated serialization/parsing/thinking-label code
- ♻️ **Unified agent switch** — Bot, API, and Pipeline all use `config.is_agent_available()` instead of divergent `config.agent_mode` checks
- 📖 **README.md** — expanded Bot commands section (ask/chat/strategies/history), added NL routing note, updated agent mode description
- 📖 **.env.example** — added `AGENT_ARCH` and `AGENT_NL_ROUTING` configuration documentation
- 🔌 **Analysis API async contract** — `POST /api/v1/analysis/analyze` now documents distinct async `202` payloads for single-stock vs batch requests, and `report_type=full` is treated consistently with the existing full-report behavior

### Fixed
- 🐛 **Analysis API blank-code guardrails** — `POST /api/v1/analysis/analyze` now drops whitespace-only entries before batch enqueue and returns `400` when no valid stock code remains
- 🐛 **Bare `/api` SPA fallback** — unknown API paths now return JSON `404` consistently for both `/api/...` and the exact `/api` path
- 🎮 **Discord channel env compatibility** — runtime now accepts legacy `DISCORD_CHANNEL_ID` as a fallback for `DISCORD_MAIN_CHANNEL_ID`, and the docs/examples now use the same variable name as the actual workflow/config implementation
- 🐛 **Session secret rotation on Windows** — use atomic replace so auth toggles invalidate existing sessions even when `.session_secret` already exists
- 🐛 **Auth toggle atomicity** — persist `ADMIN_AUTH_ENABLED` before rotating session secret; on rotation failure, roll back to the previous auth state
- **LLM runtime field Guardrails**  **YAML mode channel editor no longer overwrites `LITELLM_MODEL` / fallback / Vision; system configuration to complete run-time source check after all channels are disabled and fix `vertexai/...` The problem of these protocol aliases being duplicated with prefixes
- 🐛 **Multi-stock `/ask` follow-up regressions** — portfolio overlay now shares the same timeout budget as the per-stock phase and is skipped on timeout instead of blocking the bot reply; `/history` now stores the readable per-stock summary instead of raw dashboard JSON; condensed multi-stock output now renders numeric `sniper_points` values
- 🐛 **Decision dashboard enum compatibility** — multi-agent `DecisionAgent` now keeps `decision_type` within the legacy `buy|hold|sell` contract and normalizes stray `strong_*` Outputs before risk override, Pipeline review, and downstream statistics/summation of notifications
- 🛟 **Multi-Agent partial-result fallback** — `IntelAgent` now caches parsed intel for downstream reuse, shared JSON parsing tolerates lightly malformed model output, and the orchestrator preserves/synthesizes a minimal dashboard on timeout or mid-pipeline parse failure instead of always collapsing to `50/Wait and See/Unknown`
- 🐛 **Shared LiteLLM routing restored** — bot NL intent parsing and `ResearchAgent` planning/synthesis now reuse the same LiteLLM adapter / Router / fallback / `api_base` injection path as the main Agent flow, so `LLM_CHANNELS` / `LITELLM_CONFIG` / OpenAI-compatible deployments behave consistently
- 🐛 **Bot chat session backward compatibility** — `/chat` now keeps using the legacy `{platform}_{user_id}` session id when old history already exists, and `/history` can still list / view / clear those pre-migration sessions alongside the new `{platform}_{user_id}:chat` format
- 🐛 **EventMonitor unsupported rule rejection** — config validation/runtime loading now reject or skip alert types the monitor cannot actually evaluate yet, so schedule mode no longer silently accepts permanent no-op rules
- **P0 Basic surface polymer stabilization repair** (#614) — rehabilitation `get_stock_info` Syntax Return (New) `belong_boards` And keep it. `boards` Compatible aliases), introduce a simple return to the base context to control token, add the maximum entry to the base cache, and complete the ETF General Status Convergence with the NN Board field filter to ensure fail-open and minimum intrusion.
-  **GitHub Actions Environment Variable Supplement** - Workflow Add `MINIMAX_API_KEYS`、`BRAVE_API_KEYS`、`SEARXNG_BASE_URLS` Environmental variable mapping to enable GitHub Actions users to configure MiniMax, Brave, SeaxNG search services (previously v3.5.0 has been added programr achieved but missing workflow configuration)
- 🤖 **Multi-Agent runtime consistency** — `AGENT_MAX_STEPS` now propagates to each orchestrated sub-agent; added cooperative `AGENT_ORCHESTRATOR_TIMEOUT_S` budget to stop overlong pipelines before they cascade further
- 🔌 **Multi-Agent feature wiring** — `AGENT_RISK_OVERRIDE` now actively downgrades final dashboards on hard risk findings; `AGENT_MEMORY_ENABLED` now injects recent analysis memory + confidence calibration into specialised agents; multi-stock `/ask` now runs `PortfolioAgent` to add portfolio-level allocation and concentration guidance
- 🔔 **EventMonitor runtime wiring** — schedule mode can now load alert rules from `AGENT_EVENT_ALERT_RULES_JSON`, poll them at `AGENT_EVENT_MONITOR_INTERVAL_MINUTES`, and send triggered alerts through the existing notification service
- 🛠️ **Follow-up stability fixes** — multi-stock `/ask` now falls back to usable text output when dashboard JSON parsing fails; EventMonitor skips semantically invalid rules instead of aborting schedule startup; background alert polling now runs independently of the main scheduled analysis loop
- 🧪 **Multi-Agent regression coverage** — added orchestrator execution tests for `run()`, `chat()`, critical-stage failure, graceful degradation, and timeout handling
- 🧹 **PortfolioAgent cleanup** — `post_process()` now reuses shared JSON parsing and removed stale unused imports
- 🚦 **Bot async dispatch** — `CommandDispatcher` now exposes `dispatch_async()`; NL intent parsing and default command execution are offloaded from the event loop, DingTalk stream awaits async handlers directly, and Feishu stream processing is moved off the SDK callback thread
- 🌐 **Async webhook handler** — new `handle_webhook_async()` function in `bot/handler.py` for use from async contexts (e.g. FastAPI); calls `dispatch_async()` directly without thread bridging
- 🧵 **Feishu stream ThreadPoolExecutor** — replaced unbounded per-message `Thread` spawning with a capped `ThreadPoolExecutor(max_workers=8)` to prevent thread explosion under message bursts
- 🔒 **EventMonitor safety** — `_check_volume()` now safely handles `get_daily_data` returning `None` (no tuple-unpacking crash); `on_trigger` callbacks support both sync and async callables via `asyncio.to_thread`/`await`
- 🧹 **ResearchAgent dedup** — `_filtered_registry()` now delegates to `BaseAgent._filtered_registry()` instead of duplicating the filtering logic
- 🧹 **Bot trailing whitespace cleanup** — removed W291/W293 whitespace issues across `bot/handler.py`, `bot/dispatcher.py`, `bot/commands/base.py`, `bot/platforms/feishu_stream.py`, `bot/platforms/dingtalk_stream.py`
- 🐛 **Dispatcher `_parse_intent_via_llm` safety** — replaced fragile `'raw' in dir()` with `'raw' in locals()` for undefined-variable guard in `JSONDecodeError` handler
- **Clip structure LLM completed when not completed** (#589) - DeepSeek etc. not correctly completed `chip_structure` , automatically complete the data obtained from the data source to ensure consistency in the presentation of the models; normal analysis is valid with Agent mode
- **History report sniper spot displays original text** (#452) - History details page is now displayed first `raw_result.dashboard.battle_plan.sniper_points` , avoid `analysis_history` Value column compresses the interval, description or complex bits into a single number; the original value column is maintained as a retreat
- 🐛 **Session prefix collision** — user ID `123` could see sessions of user `1234` via `startswith`; fixed with colon delimiter in session_id format
- 🐛 **NL pre-filter false positives** — `re.IGNORECASE` caused `[A-Z]{2,5}` to match common English words like "hello"; removed global flag, use inline `(?i:...)` only for English finance keywords
- 🐛 **Dotted ticker in strategy args** — `_get_strategy_args()` didn't recognize `BRK.B` as a stock code, leaving it in strategy text; now accepts `TICKER.CLASS` format
-  **efinance Long Call Hangup Repair** (#660) — Introduction for all efinance API calls `_ef_call_with_timeout()` Packaging (default 30 seconds, by `EFINANCE_CALL_TIMEOUT` Configure); using `executor.shutdown(wait=False)` Make sure you don't block the main route after the clock's running.
- ** Type security content integrity check** (#660) — `check_content_integrity()` Now do not string type `operation_advice` / `analysis_summary` Consider missing fields to avoid downstream `get_emoji()` Because `dict.strip()` Crash
- ** Report saving and notification decoupling** (#660) — `_save_local_report()` No longer dependent `send_notification` Marks trigger,`--no-notify` Keep local reports as usual in mode
-  **operation_advice Dictionary Normalization** (#660) — Pipeline and BacktestEngine are now returning LLM `dict` Format `operation_advice` Pass. `decision_type`Map to standard string (not case sensitive) to prevent collapse due to changes in model output format
- **runner.py usage nete** (#660) — `response.usage` Yes `None` Do not throw anymore `AttributeError`Back to 0 token count
-  **orchestor failed silently to log warning** (#660) — `IntelAgent` / `RiskAgent` Phase failure is now recorded. `WARNING` Instead of skipping quietly, it's easy to diagnose.

### Notes
- ⚠️ **Multi-worker auth toggles** — runtime auth updates are process-local; multi-worker deployments must restart/roll workers to keep auth state consistent

## [3.5.0] - 2026-03-12

### Added
- 📊 **Web UI full report drawer** (Fixes #214) — history page adds "Full Report" button to display the complete Markdown analysis report in a side drawer; new `GET /api/v1/history/{record_id}/markdown` endpoint
- 📊 **LLM cost tracking** — all LLM calls (analysis, agent, market review) recorded in `llm_usage` table; new `GET /api/v1/usage/summary?period=today|month|all` endpoint returns aggregated token usage by call type and model
- 🔍 **SearXNG search provider** (Fixes #550) — quota-free self-hosted search fallback; priority: Bocha > Tavily > Brave > SerpAPI > MiniMax > SearXNG
- 🔍 **MiniMax web search provider** — `MiniMaxSearchProvider` with circuit breaker (3 failures → 300s cooldown) and dual time-filtering; configured via `MINIMAX_API_KEYS`
- 🤖 **Agent models discovery API** — `GET /api/v1/agent/models` returns available model deployments (primary/fallback/source/api_base) for Web UI model selector
- 🤖 **Agent chat export & send** (#495) — export conversation to .md file; send to configured notification channels; new `POST /api/v1/agent/chat/send`
- 🤖 **Agent background execution** (#495) — analysis continues when switching pages; badge notification on completion; auto-cancel in-progress stream on session switch
- 📝 **Report Engine P0** — Pydantic schema validation for LLM JSON; Jinja2 templates (markdown/wechat/brief) with legacy fallback; content integrity checks with retry; brief mode (`REPORT_TYPE=brief`); history signal comparison
- 📦 **Smart import** — multi-source import from image/CSV/Excel/clipboard; Vision LLM extracts code+name+confidence; name→code resolver (local map + pinyin + AkShare); confidence-tiered confirmation
- ⚙️ **GitHub Actions LiteLLM config** — workflow supports `LITELLM_CONFIG`/`LITELLM_CONFIG_YAML` for flexible AI provider configuration
- ⚙️ **Config engine refactor & system API** (#602) — unified config registry, validation and API exposure
- 📖 **LLM configuration guide** — new `docs/LLM_CONFIG_GUIDE.md` covering 3-tier config, quick start, Vision/Agent/troubleshooting

### Fixed
- 🐛 **analyze_trend always reports No historical data** (#600) — now fetches from DB/DataFetcher instead of broken `get_analysis_context`
- 🐛 **Chip structure fallback when LLM omits it** (#589) — auto-fills from data source chip data for consistent display across models
- 🐛 **History sniper points show raw text** (#452) — prioritizes original strings over compressed numeric values
- 🐛 **GitHub Actions ENABLE_CHIP_DISTRIBUTION configurable** (#617) — no longer hardcoded, supports vars/secrets override
- 🐛 **`.env` save preserves comments and blank lines** — Web settings no longer destroys `.env` formatting
- 🐛 **Agent model discovery fixes** — legacy mode includes LiteLLM-native providers; source detection aligned with runtime; fallback deployments no longer expanded per-key
- 🐛 **Stooq US stock previous close semantics** — no longer misuses open price as previous close
- 🐛 **Stock name prefetch regression** — prioritizes local `STOCK_NAME_MAP` before remote queries
- 🐛 **AkShare limit-up/down calculation** (#555) — fixed market analysis statistics
- 🐛 **AkShare Tencent source field index & ETF quote mapping** (#579)
- 🐛 **Pytdx stock name cache pagination** (#573) — prevents cache overflow
- 🐛 **PushPlus oversized report chunking** (#489) — auto-segments long content
- 🐛 **Agent chat cancel & switch** (#495) — cancel no longer misreports as failure; fast switch no longer overwrites stream state
- 🐛 **MiniMax search status in `/status` command** (#587)
- 🐛 **config_registry duplicate BOCHA_API_KEYS** — removed duplicate dict entry that silently overwrote config

### Changed
- 🔎 **Fetcher failure observability** — logs record start/success/failure with elapsed time, failover transitions; Efinance/Akshare include upstream endpoint and classified failure categories
- ♻️ **Data source resilience & cleanup** (#602) — fallback chain optimization
- ♻️ **Image extract API response extension** — new `items` field (code/name/confidence); `codes` preserved for backward compatibility
- ♻️ **Import parse error messages** — specific failure reasons for Excel/CSV; improved logging with file type and size

### Docs
- 📖 LLM config guide refactored for clarity (#583)
- 📖 `image-extract-prompt.md` with full prompt documentation
- 📖 AkShare fallback cache TTL documentation
## [3.4.10] - 2026-03-07

### Fixed
- 🐛 **EfinanceFetcher ETF OHLCV data** (#541, #527) — switch `_fetch_etf_data` from `ef.fund.get_quote_history` (NAV-only, no OHLCV, no `beg`/`end` params) to `ef.stock.get_quote_history`; ETFs now return proper open/high/low/close/volume/amount instead of zeros; remove obsolete NAV column mappings from `_normalize_data`
- 🐛 **tiktoken 0.12.0 `Unknown encoding cl100k_base`** (#537) — pin `tiktoken>=0.8.0,<0.12.0` in requirements.txt to avoid plugin-registration regression introduced in 0.12.0
- 🐛 **Web UI API error classification** (#540) — frontend no longer treats every HTTP 400 as the same "server/network" failure; now distinguishes Agent disabled / missing params / model-tool incompatibility / upstream LLM errors / local connection failures
- **Beijing Stock Exchange code recognition** (#491, #533) — Six-digit codes beginning with 8, 4, or 92 are now correctly identified as Beijing Stock Exchange securities. Tushare, AkShare, and YFinance support the `.BJ` or `bj` prefix, while Baostock and Pytdx switch to compatible providers, avoiding confusion with Shanghai B-share `900xxx` codes.
-  ** Sniper spot resolution error** (#488, #532) — ideal buy-in/second buy-in phrases erroneously extract technical indicators in brackets without the word “metas”; first brackets after first brackets are removed before extraction

### Added
- ** Markdown-to-image for dashboard report** (#455, #535) — stock paper aggregate support for markdown rollover (Telegram, WeChat, Custom, Email) consistent with large disc behaviour
- **markdown-to-file engine** (#455) — `MD2IMG_ENGINE=markdown-to-file` Optional, better for emoji support, need `npm i -g markdown-to-file`
- **PREFETCH_REALTIME_QUOTES** (#455) — with `false` Disable real-time liner preset to avoid efinance/akshare_em
- **Stock name prefetch** (#455) — Pre-prioritize the name of the stock and reduce the xxx placeholder in the report
- ** Analyzing model tag** (#528, #534) — presented in analysis meta, at end of report, in transfer `model_used`(full LLM model name); Agent multi-rotation time to record and display the actual model used per round (support fallback switch)

### Changed
- ** Enhanced markdown-to-image justice warning** (#455) _ _ _ _ _(#455) _ _ _ _ _ _ _  ** _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _  ** _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _wkhtmltopdf or m2f _
- **WeChat-only excepting optimation** (#455) — no more redundancies on complete reports and avoidance of misleading failure log
- **Stock name prefetch light Mode** (#455) - Skip realtime queen query to reduce extra network costs

## [3.4.9] - 2026-03-06

### Added
- 🧠 **Structured config validation** — `ConfigIssue` dataclass and `validate_structured()` with severity-aware logging; `CONFIG_VALIDATE_MODE=strict` aborts startup on errors
- 🖼️ **Vision model config** — `VISION_MODEL` and `VISION_PROVIDER_PRIORITY` for image stock extraction; provider fallback (Gemini → Anthropic → OpenAI → DeepSeek) when primary fails
- 🚀 **CLI init wizard** — `python -m dsa init` 3-step interactive bootstrap (model → data source → notification), 9 provider presets, incremental merge by default
- 🔧 **Multi-channel LLM support** with visual channel editor (#494)

### Changed
- ♻️ **Vision extraction** — migrated from gemini-3 hardcode to `litellm.completion()` with configurable model and provider fallback; `OPENAI_VISION_MODEL` deprecated in favor of `VISION_MODEL`
- ♻️ **Market analyzer** — uses `Analyzer.generate_text()` for LLM calls; fixes bypass and Anthropic `AttributeError` when using non-Router path
- ♻️ **Config validation refinements** — test_env output format syncs with `validate_structured` (severity-aware ✓/✗/⚠/·); Vision key warning when `VISION_MODEL` set but no provider API key; market_analyzer test covers `generate_market_review` fallback when `generate_text` returns None
- ⚙️ **Auto-tag workflow defaults to NO tag** — only tags when commit message explicitly contains `#patch`, `#minor`, or `#major`
- ♻️ **Formatter and notification refactor** (#516)

### Fixed
- 🐛 **STOCK_LIST not refreshed on scheduled runs** — `.env` or WebUI changes to `STOCK_LIST` now hot-reload before each scheduled analysis (#529)
- 🐛 **WebUI fails to load with MIME type error** — SPA fallback route now resolves correct `Content-Type` for JS/CSS files (#520)
- 🐛 **AstrBot sender docstring misplaced** — `import time` placed before docstring in `_send_astrbot`, causing it to become dead code
- 🐛 **Telegram Markdown link escaping** — `_convert_to_telegram_markdown` escaped `[]()` characters, breaking all Markdown links in reports
- 🐛 **Duplicate `discord_bot_status` field** in Config dataclass — second declaration silently shadowed the first
- 🧹 **Unused imports** — removed `shutil`/`subprocess` from `main.py`
- 🔧 **Config validation and Vision key check** (#525)

### Docs
- 📝 Clarified GitHub Actions non-trading-day manual run controls (`TRADING_DAY_CHECK_ENABLED` + `force_run`) for Issue #461 / PR #466

## [3.4.8] - 2026-03-02

### Fixed
- 🐛 **Desktop exe crashes on startup with `FileNotFoundError`** — PyInstaller build was missing litellm's JSON data files (e.g. `model_prices_and_context_window_backup.json`). Added `--collect-data litellm` to both Windows and macOS build scripts so the files are correctly bundled in the executable.

### CI
- 🔧 Cache Electron binaries on macOS CI runners to prevent intermittent EOF download failures when fetching `electron-vX.Y.Z-darwin-*.zip` from GitHub CDN
- 🔧 Fix macOS DMG `hdiutil Resource busy` error during desktop packaging

### Docs
- 📝 Clarify non-trading-day manual run controls for GitHub Actions (`TRADING_DAY_CHECK_ENABLED` + `force_run`) (#474)

## [3.4.7] - 2026-02-28

### Added
- 🧠 **CN/US Market Strategy Blueprint System** (#395) — market review prompt injects region-specific strategy blueprints with position sizing and risk trigger recommendations

### Fixed
- 🐛 **`TRADING_DAY_CHECK_ENABLED` env var and `--force-run` for GitHub Actions** (#466)
- 🐛 **Agent pipeline preserved resolved stock names** (#464) — placeholder names no longer leak into reports
- 🐛 **Code cleanup** (#462, Fixes #422)
- 🐛 **WebUI auto-build on startup** (#460)
- 🐛 **ARCH_ARGS unbound variable** (#458)
- 🐛 **Time zone inconsistency & right panel flash** (#439)

### Docs
- 📝 Clarify potential ambiguities in code (#343)
- 📝 ENABLE_EASTMONEY_PATCH guidance for Issue #453 (#456)

## [3.4.0] - 2026-02-27

### Added
- 📡 **LiteLLM Direct Integration + Multi API Key Support** (#454, Fixes #421 #428)
  - Removed native SDKs (google-generativeai, google-genai, anthropic); unified through `litellm>=1.80.10`
  - New config: `LITELLM_MODEL`, `LITELLM_FALLBACK_MODELS`, `GEMINI_API_KEYS`, `ANTHROPIC_API_KEYS`, `OPENAI_API_KEYS`
  - Multi-key auto-builds LiteLLM Router (simple-shuffle) with 429 cooldown
  - **Breaking**: `.env` `GEMINI_MODEL` (no prefix) only for fallback; explicit config must include provider prefix

### Changed
- ♻️ **Notification Refactoring** (#435) — extracted 10 sender classes into `src/notification_sender/`

### Fixed
- 🐛 LLM NoneType crash, history API 422, sniper points extraction
- 🐛 Auto-build frontend on WebUI startup — `WEBUI_AUTO_BUILD` env var (default `true`)
- 🐛 Docker explicit project name (#448)
- 🐛 Bocha search SSL retry (#445, #446) — transient errors retry up to 3 times
- 🐛 Gemini google-genai SDK migration (Fixes #440, #444)
- 🐛 Mobile home page scrolling (Fixes #419, #433)
- 🐛 History list scroll reset (#431)
- 🐛 Settings save button false positive (fixes #417, #430)

## [3.3.22] - 2026-02-26

### Added
- 💬 **Chat History Persistence** (Fixes #400, #414) — `/chat` page survives refresh, sidebar session list
- 🎨 Project VI Assets — logo icon set, PSD, vector, banner (#425)
- 🚀 Desktop CI Auto-Release (#426) — Windows + macOS parallel builds

### Fixed
- 🐛 Agent Reasoning 400 & LiteLLM Proxy (fixes #409, #427)
- 🐛 Discord chunked sending (#413) — `DISCORD_MAX_WORDS` config
- 🐛 yfinance shared DataFrame (#412)
- 🐛 sniper_points parsing (#408)
- 🐛 Agent framework category missing (#406)
- 🐛 Date inconsistency & query id (fixes #322, #363)

## [3.3.12] - 2026-02-24

### Added
- 📈 **Intraday Realtime Technical Indicators** (Issue #234, #397) — MA calculated from realtime price, config: `ENABLE_REALTIME_TECHNICAL_INDICATORS`
- 🤖 **Agent Strategy Chat** (#367) — full ReAct pipeline, 11 YAML strategies, SSE streaming, multi-turn chat
- 📢 PushPlus Group Push — `PUSHPLUS_TOPIC` (#402)
- 📅 Trading Day Check (Issue #373, #375) — `TRADING_DAY_CHECK_ENABLED`, `--force-run`

### Fixed
- 🐛 DeepSeek reasoning mode (Issue #379, #386)
- 🐛 Agent news intel persistence (Fixes #396, #405)
- 🐛 Bare except clauses replaced with `except Exception` (#398)
- 🐛 UUID fallback for HTTP non-secure context (fixes #377, #381)
- 🐛 Docker DNS resolution (Fixes #372, #374)
- 🐛 Agent session/strategy bugs — multiple follow-up fixes for #367
- 🐛 yfinance parallel download data filtering

### Changed
- Market review strategy consistency — unified cn/us template
- Agent test assertions updated (`6 -> 11`)


## [3.2.11] - 2026-02-23

### Fixed (#patch)
- ** StockTrendAnalyzer never implemented** (Issue #357)
  - GEN:`get_analysis_context` returns only 2 days data without `raw_data`,peline `raw_data in context` Always as False
  - Repair: Step 3 Direct call `get_data_range` Get 90 calendar days (approximately 60 trading days) for trend analysis
  - Improvement: Use when trend analysis fails `logger.warning(..., exc_info=True)` full trackback

## [3.2.10] - 2026-02-22

### Added
- Support `RUN_IMMEDIATELY` Configure Item to `true` Carry out an analysis immediately after the time-bound task trigger without waiting for the first point

### Fixed
- 🐛 Fix Web UI Page Centre Problem
- Fix Settings returns 500 error

## [3.2.9] - 2026-02-22

### Fixed
- **ETF analysis only focuses on index trends** (Issue #274)
  - ETF (e.g. VOO, QQQQ) and A ETF no longer include risk at the Fund ' s corporate level (litigation, reputation, etc.)
  - Search dimensions: ETF/Indicator-specific risk_check, earnings, industry queries to avoid hitting Fund Manager News
  - AI tip: analytical constraints on index-type indicators,`risk_alerts` No risks to the operations of the Fund Manager company

## [3.2.8] - 2026-02-21

### Fixed
- **BOT and WEB UI stock code customised** (Issue #355)
  - BOT `/analyze` Harmonize the stock code with the WEB UI trigger analysis to capitalise (e. g. `aapl` → `AAPL`）
  - Added `canonical_stock_code()`Regularize at BOT, API, Config, CLI, task_queue entrance
  - Historic records and missions re-integrate correctly the same stock (case no longer affected)

## [3.2.7] - 2026-02-20

### Added
-  **Web Page Password Validation** (Issue #320, #349)
  - Support `ADMIN_AUTH_ENABLED=true` Enable Web Login Protection
  - First access to set initial passwords on the web page; supporting System Settings > Change Passwords and CLI `python -m src.auth reset_password` Reset

## [3.2.6] - 2026-02-20
### ⚠️ Breaking Changes

- **History API Change (Issue #322)**
  - Route change:`GET /api/v1/history/{query_id}` → `GET /api/v1/history/{record_id}`
  - Parameter changes:`query_id` (strings) `record_id` (integer)
  - News interface changes:`GET /api/v1/history/{query_id}/news` → `GET /api/v1/history/{record_id}/news`
  - Reason:`query_id` The bulk analysis may be repeated and it is not possible to identify a single historical record. Change to Database Primary Key `id` Ensuring uniqueness
  - Impact range: All clients using the old version of history details need to update simultaneously

### Fixed
- Remedial U.S.U. (e.g. ADBE) technical indicator contradiction: kshare U.S. share-gain data anomaly, U.S. share historical data source is YFinance (Issue #311)
- ** Historical record queries and displays (Issue #322)**
  - Fix date inconsistencies in the historical record list query: use tomorrow as endDate to ensure that today's full-day data are included
  - Fix server UI report selection problem: because multiple records are shared `query_id`, leads to always showing the first. Reused `analysis_history.id` As unique identifier
  - History details, news interfaces and front-end components are fully adapted `record_id`
  - Add a new back-stage round of queries (per 30s) to the historical list to be updated silently when page visibility changes are made to ensure that the CLI-initiated analysis is synchronized and used at the front end in a timely manner `silent` Mode to avoid trigger status
- ** United States equity index real-time behaviour and dayline data** (Issue #273)
  - Fixing problems where US stock indices such as SPX, DJI, IXIC, NDX, VIX, RUT cannot be accessed in real time
  - Added `us_index_mapping` module, map user input (e.g. SPX) to Yahoo Finance symbol (e. g. ^GSPC)
  - U.S. stock index and U.S. stock day data directly route to YfinanceFetcher, avoiding running through unsupported data sources
  - Eliminate duplicated U.S. stock recognition logic and use it uniformly `is_us_stock_code()` Functions

### Changed
- ** Front page input bar aligned to Market Series layout optimized**
  - Stock code input left alignment with historical glass-card left
  - Analyse button right edge aligned to market frame right
  - Market Sention card stretches down to fill the grid and removes the gap with STRATEGY POINTS
  - Fills the width of the input bar and aligns the response to the screen

## [3.2.5] - 2026-02-19

### Added
- **Market review region selection** (Issue #299)
  - Added the `MARKET_REVIEW_REGION` environment variable with `cn` (A-shares), `us` (U.S. stocks), and `both` options.
  - The us model uses an index such as SPX/ NASDAK/ Dow/ VIX; both models can be redisplayed simultaneously with A and U.S. shares
  - Default `cn`Keep it backward.

## [3.2.4] - 2026-02-18

### Fixed
- ** Harmonized United States share data source YFinance** (Issue #311)
  - kshare U.S. share compound data anomaly, U.S. share historical data source YFinance
  - Fix the technical discrepancies between the ADBE and the United States stock

## [3.2.3] - 2026-02-18

### Fixed
- **Pop 500 real-time data missing** (Issue #273)
  - Fixing problems where US stock indices such as SPX, DJI, IXIC, NDX, VIX, RUT cannot be accessed in real time
  - Added `us_index_mapping` module, map user input (e. g. SPX) to Yahoo Finance symbol (e. g. `^GSPC`）
  - U.S. stock index and U.S. stock day data directly route to YfinanceFetcher, avoiding running through unsupported data sources

## [3.2.2] - 2026-02-16

### Added
- ** PE indicator support** (Issue #296)
  - AI System Prompt Add PE Valuation Concerns
- ** Time-bound news screening** (Issue #296)
  - `NEWS_MAX_AGE_DAYS`: maximum news time (days), default 3, avoid using outdated information
- **Relaxed deviation limits for strong-trend stocks** (Issue #296)
  - `BIAS_THRESHOLD`: Validity rate threshold (%), default 5.0, configured
  - Strong-trend stocks with multiple bullish signals and trend strength above 70 automatically relax the deviation threshold to 1.5 times its configured value.

## [3.2.1] - 2026-02-16

### Added
- **Toxie interface patch to configure switches**
  - Support `EFINANCE_PATCH_ENABLED` Environmental Variable Switch East Finance Interface Patch (default) `true`）
  - Patches can be downgraded when not available to avoid affecting the main process

## [3.2.0] - 2026-02-15

### Added
- ** CI Door Ban Uniform (P0)**
  - Added `scripts/ci_gate.sh` Disable single entry as back door
  - The main CI should read `backend-gate`、`docker-build`、`web-gate` Three-part pattern
  - CI Trigger to all PRs to avoid limiting merge due to missing path filters
  - `web-gate` Support front-end path changes to trigger as required
  - Added `network-smoke` Workstream carrying non-stop web scene return
- ** Releasing of release links (P0)**
  - `docker-publish` Adjust to tag primary trigger and add front door unverified verification
  - Increase manual distribution `release_tag` Enter and check strongly with semver/changelog
  - Add Docker smoke before release
- **PR template upgrade (P0)**
  - Add mandatory entries such as background, scope, authentication commands and results, rollback programs, Issue connections
- **AI review coverage enhancement (P0)**
  - `pr-review` Inclusion `.github/workflows/**` Scope
  - Added `AI_REVIEW_STRICT` Switch to upgrade AI review failure to block

## [3.1.13] - 2026-02-15

### Added
- **Summary-only analysis reports** (Issue #262)
  - Added the `REPORT_SUMMARY_ONLY` environment variable. When set to `true`, notifications send only the summary without individual-stock details.
  - Default `false`, which allows quick browsing during multiple shares

## [3.1.12] - 2026-02-15

### Added
- **Combined individual-stock and market review emails** (Issue #190)
  - Added the `MERGE_EMAIL_NOTIFICATION` environment variable. When set to `true`, individual-stock analysis and the market review are sent in one email.
  - Default `false`Reduced number of mail and reduced risk of being identified as spam

## [3.1.11] - 2026-02-15

### Added
- **Anthropic Claude API Support** (Issue #257)
  - Support `ANTHROPIC_API_KEY`、`ANTHROPIC_MODEL`、`ANTHROPIC_TEMPERATURE`、`ANTHROPIC_MAX_TOKENS`
  - AI Analysis Priority: Gemini > Anthropic > OpenAI
- **Identified stock code from pictures** (Issue #257)
  - Upload a self-selected stock screenshot and automatically extract the stock code from the Vision LLM
  - API: `POST /api/v1/stocks/extract-from-image`;support JPEG/PNG/WebP/GIF, max. 5MB
  - Support `OPENAI_VISION_MODEL` Configure image recognition model separately
- **Mercure data source manual configuration** (Issue #257)
  - Support `PYTDX_HOST`、`PYTDX_PORT` or `PYTDX_SERVERS` Configure self-constructed tom server

## [3.1.10] - 2026-02-15

### Added
- (Issue #332)
  - Support `RUN_IMMEDIATELY` Environmental variables,`true` Once a time-bound mission starts
- Fix Docker Build Problem

## [3.1.9] - 2026-02-14

### Added
- ** East Timor interface patch mechanism**
  - Added `patch/eastmoney_patch.py` Recover efinance upstream interface changes
  - Not affecting the normal operation of other data sources

## [3.1.8] - 2026-02-14

### Added
-  **Webhook Certificate Validation Switch** (Issue #265)
  - Support `WEBHOOK_VERIFY_SSL` Environment variable to close HTTPS certificate validation to support self-signed certificate
  - Default to maintain validation, close with MITM risk, only recommended for use in a trusted Intranet

## [3.1.7] - 2026-02-14

### Fixed
- Fix package import error (package effect error)

## [3.1.6] - 2026-02-13

### Fixed
- Rehabilitation `news_intel` Medium `query_id` Inconsistencies

## [3.1.5] - 2026-02-13

### Added
- ** Markdown Photo Circular** (Issue #289)
  - Support `MARKDOWN_TO_IMAGE_CHANNELS` Configuration, photo-format report for Telegram, Enterprise Micro-Credit, Custom Webbook (Discord), Email
  - Mail as an inline attachment to enhance compatibility with unsupported HTML client
  - Requires installation `wkhtmltopdf` and `imgkit`

## [3.1.4] - 2026-02-12

### Added
- **Equities group sent to different mailboxes** (Issue #268)
  - Support `STOCK_GROUP_N` + `EMAIL_GROUP_N` Configure, different stock group reports sent to corresponding mailboxes
  - Big Rewind to all configured mailboxes

## [3.1.3] - 2026-02-12

### Fixed
- Error reporting through page modification while repairing Docker's running `[Errno 16] Device or resource busy` Issues

## [3.1.2] - 2026-02-11

### Fixed
- Rehabilitation of Docker consistency issues and resolution of critical batch processing and notification Bug

## [3.1.1] - 2026-02-11

### Changed
- ♻️ `API_HOST` → `WEBUI_HOST`: Docker Compose configuration unified

## [3.1.0] - 2026-02-11

### Added
- **ETF supports enhancement and code standardization**
  - Harmonize ETF code processing logic across data sources
  - Added `canonical_stock_code()` Harmonize code formats to ensure the correct route of data sources

## [3.0.5] - 2026-02-08

### Fixed
- 🐛 Remedial signal emoji inconsistent with recommendation (complex recommendations such as "sale/see" not correctly map)
- Rehabilitation `*ST` Markdown conversion in Twitter/Dashboard
- Fixed a market review `TypeError` when `idx.amount` is `None`.
- API returns `report=None` and ReportStrategy type inconsistencies
- Fix Tushare Return Type Errors (dict →United RealtimeQuote) and API Endpoint

### Added
- Market review reports now include structured data such as advance/decline statistics, index tables, and sector rankings.
- 🔍 Search result TTL cache (500 caps, FIFO phase-out)
- 🔧 Tushare Token automatically injects real-time line priority when it exists
- The length of the news summary cut-off 50 → 200 words

### Changed
- • Limit requests for additional line fields to a maximum of 1 and reduce invalid requests

## [3.0.4] - 2026-02-07

### Added
- (PR #269)
  - Add a new retrospect system based on historical analysis to support the assessment of indicators such as rate of return, success, maximum retreat
  - WebUI IR presentation

## [3.0.3] - 2026-02-07

### Fixed
- 🐛 Fixing Sniper Point Data Parsing Error (PR #271)

## [3.0.2] - 2026-02-06

### Added
- ✉️ Configure sender name (PR #272)
- • Foreign equity supports the English keyword search

## [3.0.1] - 2026-02-06

### Fixed
- • Fix ETF real-time access, market data retreat, enterprise micromessage problem
- CI Simplified Process

## [3.0.0] - 2026-02-06

### Removed
- ** Remove old version of WebUI**
  - Removed the legacy `web/` package based on `http.server.ThreadingHTTPServer`.
  - Replaced the legacy WebUI with the FastAPI (`api/`) and React frontend implementation.
  - `--webui` / `--webui-only` Command line arguments are marked as obsolete and automatically redirected to `--serve` / `--serve-only`
  - `WEBUI_ENABLED` / `WEBUI_HOST` / `WEBUI_PORT` Environmental variables are compatible and automatically forwarded to FastAPI services
  - `webui.py` Keep as compatible entry, call FastAPI backend on startup
  - Remove in Docker Company `webui` Service definition, common use `server` Services

### Changed
- ** Restructured service level**
  - Will `web/services.py` In which different tasks are migrated to `src/services/task_service.py`
  - Bot Analytic Commands`bot/commands/analyze.py`) Replace with `src.services.task_service`
  - Docker Environmental Variable `WEBUI_HOST`/`WEBUI_PORT` Change name `API_HOST`/`API_PORT`(old name still compatible)

## [2.3.0] - 2026-02-01

### Added
- (Issue #153)
  - Getting US share of historical data based on Akshare`ak.stock_us_daily()`)
  - Real-time United States share acquisition based on Yfinance (priority strategy)
  - Add U.S. stock code filtering and rapid downgrading to unsupported data sources (Tushare/Baostock/Pytdx/Efinance)

### Fixed
- The AMD et al. code is misidentified as an A unit problem (Issue #153)

## [2.2.5] - 2026-02-01

### Added
- **AstrBot Post** (PR #217)
  - Add AstrBot notification channel to support push to QQQ and Twitter
  - Support HMAC SHA256 signature authentication to secure communications
  - Pass. `ASTRBOT_URL` and `ASTRBOT_TOKEN` Configure

## [2.2.4] - 2026-02-01

### Added
- ** Configure data source priorities** (PR #215)
  - Support the adoption of environmental variables (e.g. `YFINANCE_PRIORITY=0`) Dynamically adjust data source priorities
  - Priority is given to specific data sources without changing codes (e.g. Yahoo Finance)

## [2.2.3] - 2026-01-31

### Fixed
- Updates.txt, add `lxml_html_clean` Dependency to address compatibility

## [2.2.2] - 2026-01-31

### Fixed
- Fixing the proxy configuration case-sensitive problem (fixes #211)

## [2.2.1] - 2026-01-31

### Fixed
-  **YFinance Compatibility Restoration** (PR #210, fixes #209)
  - Fix a new version of yfinance returning the data parsing error due to MultiIndex listing

## [2.2.0] - 2026-01-31

### Added
- ** Multisource regression strategy enhancements**
  - (feat: multi-source fallback system)
  - Optimizing automatic switching logic when data source malfunctions

### Fixed
- Fix stocks that cannot be tracked by changing the .env file 's stock_list content after running

## [2.1.14] - 2026-01-31

### Docs
- Update README and Optimize auto-tag rules

## [2.1.13] - 2026-01-31

### Fixed
- **Tushare Priority and Real-Time Line** (Fixed #185)
  - Fixing Tushare Data Source Priority Settings
  - Fix Tushare Real-time line acquisition

## [2.1.12] - 2026-01-30

### Fixed
- Refurbishment of case-sensitive problems of proxy configuration in certain cases
- The logic of fixing local environments to disable agents

## [2.1.11] - 2026-01-30

### Changed
- **Feishu streaming optimization** (PR #192)
  - Optimized message types for Feishu streaming mode.
  - Modifying Stream message mode to close by default to prevent error reporting when configuring error

## [2.1.10] - 2026-01-30

### Changed
- Consolidation PR #154 Contribution

## [2.1.9] - 2026-01-30

### Added
- ** Microtext Message Support** (PR #137)
  - Add text-based message type support for tweets
  - Add `WECHAT_MSG_TYPE` Configure Item

## [2.1.8] - 2026-01-30

### Fixed
- 🐛 Correcting errors in API provider (PR #197)

## [2.1.7] - 2026-01-30

### Fixed
- Disable proxy settings in local settings to avoid network connection problems

## [2.1.6] - 2026-01-29

### Added
- **Pytdx Data Source (Priority 2)**
  - Add a new contact data source without registration for free
  - Multiple Server Auto Switch
  - Support real-time patterns and historical data
- ** Multi-source stock name resolution**
  - DataFetcherManager Add `get_stock_name()` Methodology
  - Added `batch_get_stock_names()` Batch queries
  - Autoback between multiple data sources
  - Tushare and Baustock add a name/list method
- ** Enhanced search retreat**
  - Added `search_stock_price_fallback()` When all data sources fail
  - New search dimension: market analysis, industry analysis
  - Maximum number of searches increased from 3 to 5
  - Improve search results format (4 results per dimension)

### Changed
- Update search query templates to improve relevance
- Enhanced `format_intel_report()` Output Structure

## [2.1.5] - 2026-01-29

### Added
- New Pytdx data source and multi-source stock name resolution function

## [2.1.4] - 2026-01-29

### Docs
- Update sponsor information

## [2.1.3] - 2026-01-28

### Docs
- Restructure README
- New Chinese translation (README_CHT.md)

### Fixed
- WebUI can't enter a U.S. stock code problem.
  - Enter box logic to all letters into uppercase
  - Support `.` input (e.g. `BRK.B`）

## [2.1.2] - 2026-01-27

### Fixed
- • Rehabilitation of units to analyse the failure of transmission and the problem of reporting routes (fixes #166)
- Modify CR error to ensure maximum byte configuration of tweets

## [2.1.1] - 2026-01-26

### Added
- 🔧 Add GitHub Operations auto-tag workflow
- Add yfinance bottom data source and data missing warning

### Fixed
- Fix docker-compose path and document commands
- 🐳Dockerfile Supplement to copy src folder (fixes #145)

## [2.1.0] - 2026-01-25

### Added
- ** United States share analytical support**
  - Supports direct input of U.S. stock codes `AAPL`, `TSLA`）
  - Use YFinance as an American share data source
- **MACD and RSI technical indicators**
  - MACD: Trend confirmation, Golden fork signal (Gold fork on zero axis, Golden fork, Dead fork)
  - RSI: Super-sale judgement (over-sale, powerful, over-sale)
  - Indicator signals integrated into the integrated rating system
-  **Discord push support** (PR#124, #125, #144)
  - Support for Discord Webbook and Bot API
  - Pass. `DISCORD_WEBHOOK_URL` or `DISCORD_BOT_TOKEN` + `DISCORD_MAIN_CHANNEL_ID` Configure
- ** Robotic command interactive**
  - DingTalk bot support. Use `/analyze stock_code` to trigger analysis.
  - Support Stream Long Connection Mode
- **AI temperature parameters can be configured** (PR #142)
  - Supports custom AI model temperature parameters
- ** Zeabur Deployment Support**
  - Add Zeabur mirror deployment workflow
  - Support double tags for group Hash and last

### Refactored
- ** Project structure optimization**
  - Core Code To `src/` The directories. The root directories are cleaner.
  - Move Document to `docs/` Contents
  - Docker Configuration Move to `docker/` Contents
  - Fix all Import paths and maintain backward compatibility
- ** Data source architecture upgrade**
  - Adds a new data source melting mechanism, and single data sources fail to switch automatically
  - Real-time line Cache Optimization, Batch Pre-Access Reduction API Call
  - Network proxy intelligence diversion, automatic direct connection to domestic interface
- 🤖 Discord robot recast to platform adaptor structure

### Fixed
- ** Network stability enhanced**
  - Automatically detect proxy configurations and force direct connections to domestic line interfaces
  - Fix EfinanceFetcher. `ProtocolError`
  - Increase capture and retest mechanisms for bottom network errors
-  ** Mail Rendering Optimization**
  - Fix table unrendered in mail (#134)
  - Optimizing mail layouts. Closer look.
- ** Enterprise Micro-Mechanism Rehabilitation**
  - Fixing the big disc drop incomplete
  - Enhance message partition logic and support more title formats
  - Increase frequency of batch delivery to avoid loss of flow limit
- **CI/CD rehabilitation**
  - Fix path references error in GitHub Actions

## [2.0.0] - 2026-01-24

### Added
- ** United States share analytical support**
  - Supports direct input of U.S. stock codes `AAPL`, `TSLA`）
  - Use YFinance as an American share data source
- (PR #113)
  - DingTalk bot support. Use `/analyze stock_code` to trigger analysis.
  - Support Stream Long Connection Mode
  - Support the selection of streamlined or complete reports
-  **Discord push support** (PR #124)
  - Support Discord Webhook delivery
  - Add Discord Environment Variable to Workstream

### Fixed
- WebUI fixes 0.0.0.0 in Docker (fixed #118)
- 🔔 Rehabilitating the Secretary-General's connection notification
- Rehabilitation `analysis_delay` Undefined Error
- 🔧 Config.py detection notification channel at startup, still prompting unconfigured problem when configured custom channels are restored

### Changed
- 🔧 Optimizing Tushare priority judgement logic and increasing containment
- 🔧 Fix Tushare priority upgrades after Efinance
- Automatically raise the Tushare data source priority during the configuration of Tushare_Token
- achieve 4 user feedback issues (#112, #128, #38, #119)

## [1.6.0] - 2026-01-19

### Added
- 🖥️WebUI management interface and API support (PR #72)
  - New Web Architecture: Layer Design (Server/Router/Handler/Service)
  - Core API: Support `/analysis` (trigger analysis), `/tasks` (Query progress), `/health` (health check)
  - Interactive interface: support page direct input of code and trigger analysis, real-time display of progress
  - Run mode: add `--webui-only` Mode, start Web service only
  - [#70]https://github.com/ZhuLinsen/daily_stock_analysis/issues/70Core needs (provide interfaces for trigger analysis)
- ⚙️ GitHub Actions configuration flexibility enhanced ([#79]https://github.com/ZhuLinsen/daily_stock_analysis/issues/79)）
  - Supports reading non-sensitive configurations from Repository Variables (e. g. STOCK_LIST, GEMINI_MODEL)
  - Keep Secrets Down Compatible

### Fixed
- • Question of the cut-off in the repair of enterprise micro-intelligence/flying reports ([#73])https://github.com/ZhuLinsen/daily_stock_analysis/issues/73)）
  - Remove unnecessary length break logic in note.py
  - Use bottom auto-species to process long messages
- • Fix GitHub Workflow environmental variable missing ([#80]https://github.com/ZhuLinsen/daily_stock_analysis/issues/80)）
  - Fixed `CUSTOM_WEBHOOK_BEARER_TOKEN` Problem not correctly passed to Runner

## [1.5.0] - 2026-01-17

### Added
- Single share delivery mode ([#55](https://github.com/ZhuLinsen/daily_stock_analysis/issues/55)）
  - Every stock that's analysed is sent out without waiting for the full analysis.
  - Command line parameters:`--single-notify`
  - Environmental variables:`SINGLE_STOCK_NOTIFY=true`
- Customise Webhook Bearer Token authentication ([#51]()https://github.com/ZhuLinsen/daily_stock_analysis/issues/51)）
  - Support Webbook peer that requires Token authentication
  - Environmental variables:`CUSTOM_WEBHOOK_BEARER_TOKEN`

## [1.4.0] - 2026-01-17

### Added
- 📱 Pushover push support (PR #26)
  - Support iOS/Android cross-platform delivery
  - Pass. `PUSHOVER_USER_KEY` and `PUSHOVER_API_TOKEN` Configure
- 🔍Bocha search for API integration (PR #27)
  - Chinese search optimization in support of AI Summary
  - Pass. `BOCHA_API_KEYS` Configure
- Efinance Data Source Support (PR#59)
  - Add efinance as Data Source Options
- • Port Unit support (PR #17)
  - Supports 5-bit code or HK prefix (e. g. `hk00700`、`hk1810`）

### Fixed
- 🔧 Feishu Markdown rendering optimization (PR #34)
  - Fix rendering problems using interactive cards and formatting
- • Thermal load of the stock list (PR #42 repaired)
  - Autoreload Before Analyse `STOCK_LIST` Configure
- Webhouk 20KB restricted processing
  - The long message is automatically separated to avoid interruption
- AkShare API Retest Enhancement
  - Add failed caches to avoid failed interfaces

### Changed
- README Simplified Optimization
  - Advanced Configuration To `docs/full-guide.md`


## [1.3.0] - 2026-01-12

### Added
- Customised Webbook Support
  - Webhook peer support for any POST JSON
  - Automatically recognize common service formats such as nails, Discord, Slack, Bark
  - Support the configuration of multiple Webholes
  - Pass. `CUSTOM_WEBHOOK_URLS` Environmental Variable Configuration

### Fixed
- 📝 Micro-mail messages sent in batches
  - Solving the problem where the content exceeding the 4096 character limit in a self-selected share has failed to be sent
  - Intelligently divided by stock analysis blocks, adding page breaks per batch (e.g. 1/3, 2/3)
  - Batch interval 1 sec to avoid trigger frequency limitation

## [1.2.0] - 2026-01-11

### Added
- 📢 Multi-channel support
  - Webhook
  - Feishu
  - Mail SMTP (New)
  - Automatically recognize the type of channel, more easily configured

### Changed
- Unified use `NOTIFICATION_URL` Configure, fit old `WECHAT_WEBHOOK_URL`
- Mail Support Markdown Rotate HTML Rendering

## [1.1.0] - 2026-01-11

### Added
- 🤖OpenAI compatible API support
  - Support for DeepSeek, Tunyu, Moonshot, GLM, etc.
  - Gemini & OpenAI Format Selected
  - Automatic downgrade retest mechanism

## [1.0.0] - 2026-01-10

### Added
- AI Decision dashboard analysis
  - Core conclusion of the sentence
  - Accurate purchase/loss/target position
  - Checklist (✅⚠️❌)
  - Warehousing proposal (Airwaret vs Warender)
- Market review overhaul
  - Main index lines
  - Statistics of rise and fall
  - The plate goes up and down.
  - AI Generate Bulk Report
- Multiple data sources support
  - AkShare (Main data source, free of charge)
  - Tushare Pro
  - Baostock
  - YFinance
- News search services
  - Tavily API
  - SerpAPI
- 💬 Micro-intelligence robot push
- Timed schedule
- 🐳 Docker Deployment Support
- 🚀 GitHub Actions Zero Cost Deployment

### Technical Features
- Gemini AI model (gemini-3-flash-preview)
- 429. Limit flow automatic retry + model switching
- Interval between requests
- Multiple API Key Load Balance
- SQLite Local Data Storage

---

[Unreleased]: https://github.com/SiinXu/stock-pulse-ai/compare/v3.26.3...HEAD
[3.26.3]: https://github.com/SiinXu/stock-pulse-ai/compare/v3.26.2...v3.26.3
[3.25.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.24.1...v3.25.0
[3.24.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.24.0...v3.24.1
[3.24.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.23.0...v3.24.0
[3.23.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.22.0...v3.23.0
[3.22.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.21.1...v3.22.0
[3.21.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.21.0...v3.21.1
[3.21.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.20.0...v3.21.0
[3.20.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.19.0...v3.20.0
[3.19.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.18.0...v3.19.0
[3.18.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.17.1...v3.18.0
[3.17.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.17.0...v3.17.1
[3.17.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.16.0...v3.17.0
[3.16.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.15.0...v3.16.0
[3.15.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.14.2...v3.15.0
[3.14.2]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.14.1...v3.14.2
[3.14.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.14.0...v3.14.1
[3.14.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.13.0...v3.14.0
[3.13.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.12.0...v3.13.0
[3.12.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.11.0...v3.12.0
[3.11.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.10.1...v3.11.0
[3.10.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.10.0...v3.10.1
[3.10.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.9.0...v3.10.0
[3.9.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.8.0...v3.9.0
[3.8.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.7.0...v3.8.0
[3.7.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.6.0...v3.7.0
[3.6.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.5.0...v3.6.0
[3.5.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.10...v3.5.0
[3.4.10]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.9...v3.4.10
[3.4.9]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.8...v3.4.9
[3.4.8]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.7...v3.4.8
[3.4.7]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.0...v3.4.7
[3.4.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.3.22...v3.4.0
[3.3.22]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.3.12...v3.3.22
[3.3.12]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.2.11...v3.3.12
[3.2.11]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.2.10...v3.2.11
[2.3.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.5...v2.3.0
[2.2.5]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.4...v2.2.5
[2.2.4]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.3...v2.2.4
[2.2.3]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.2...v2.2.3
[2.2.2]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.1...v2.2.2
[2.2.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.14...v2.2.0
[2.1.14]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.13...v2.1.14
[2.1.13]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.12...v2.1.13
[2.1.12]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.11...v2.1.12
[2.1.11]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.10...v2.1.11
[2.1.10]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.9...v2.1.10
[2.1.9]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.8...v2.1.9
[2.1.8]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.7...v2.1.8
[2.1.7]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.6...v2.1.7
[2.1.6]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.5...v2.1.6
[2.1.5]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.4...v2.1.5
[2.1.4]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.3...v2.1.4
[2.1.3]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.6.0...v2.0.0
[1.6.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/ZhuLinsen/daily_stock_analysis/releases/tag/v1.0.0
