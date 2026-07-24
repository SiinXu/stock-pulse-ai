# StockPulse Architecture Overview

- Status: `Living`
- Last verified: 2026-07-24
- Scope: current technical component boundaries, process entrypoints, and analysis data flow

This document is the technical view of the current implementation. For
stakeholder capabilities and value flow, start with the
[business architecture](business-architecture.md). This document is not an API
specification or a product roadmap. Durable design rationale belongs in the
[ADR registry](adr/README.md); focused contracts remain authoritative for their
specific mechanics.

## View Boundary

| View | Answers | Includes |
| --- | --- | --- |
| [Business architecture](business-architecture.md) | Who receives value, what capabilities participate, and how an intent becomes an outcome | Stakeholders, capabilities, and the business value flow |
| Technical architecture (this document) | How the current repository executes and connects those capabilities | Entrypoints, module ownership, process modes, data paths, persistence, and runtime constraints |

Reliability mechanisms such as runtime guards, cache layers, provider health,
and circuit control belong in this technical view or a focused technical
contract. They are represented in the business view only by the outcome they
protect, not as business capabilities.

## Technical System At A Glance

```mermaid
flowchart LR
  CLI[CLI and scheduler<br/>main.py and src/app/cli.py] -->|direct analysis| PIPE
  WEB[React Web<br/>apps/dsa-web] -->|HTTP and SSE| API
  DESKTOP[Electron shell<br/>apps/dsa-desktop] -->|starts backend and loads Web UI| API
  BOT[Bot adapters<br/>bot/] -->|/analyze| QUEUE
  BOT -->|/batch| PIPE
  API[FastAPI<br/>server.py and api/] -->|async task| QUEUE[Process-local task queue<br/>src/services/task_queue.py]
  API -->|synchronous use case| SERVICES[Application services<br/>src/services/]
  QUEUE -->|execute task| SERVICES
  SERVICES -->|invoke analysis| PIPE[StockAnalysisPipeline<br/>src/core/pipeline.py]
  PIPE -->|fetch through adapters| DATA[Market providers<br/>data_provider/]
  PIPE -->|retrieve and analyze| INTEL[Search, context, LLM, and Agent]
  PIPE -->|domain writes| STORE[Storage and repositories<br/>src/storage.py and src/repositories/]
  PIPE -->|render and dispatch| OUTPUT[Reports and notifications<br/>templates, renderer, delivery]
```

Edges in this component view mean caller to dependency; they do not add a
second arrow for the return value. The directional stage and fallback flow is
shown below.

The canonical pipeline stage vocabulary is:

```text
resolve -> fetch -> intelligence -> context -> analyze -> persist -> render -> dispatch
```

## Entrypoints And Process Modes

| Entrypoint | Responsibility | Important boundary |
| --- | --- | --- |
| `main.py` | Process bootstrap, analysis and scheduling coordination, optional API serving, Bot stream startup, and compatibility exports | Runtime helpers and direct analysis remain here; parsing and mode dispatch are rebound from `src/app/cli.py` to preserve the existing import surface. |
| `src/app/cli.py` | CLI argument parsing and mode dispatch | Dispatches through `main.py` runtime helpers; it does not own a second analysis or service lifecycle. |
| `server.py` | Direct ASGI/uvicorn entry | Installs `ApplicationServices` and exports the FastAPI application; it does not start Bot stream clients. |
| `webui.py` | Retained compatibility launcher for direct FastAPI startup | Reads `WEBUI_HOST` / `WEBUI_PORT` with legacy `API_HOST` / `API_PORT` fallback and starts `api.app:app`. Primary documentation and Docker startup use `main.py`; this entrypoint is not deprecated. |
| `api/app.py` | FastAPI factory and lifespan | Owns auth/CORS/errors, routes, static Web hosting, `RuntimeSchedulerService`, and app-scoped `SystemConfigService`. |
| `bot/` | Platform adapters, dispatcher, and commands | Bot `/analyze` submits to the shared process-local queue. Stream clients are started by `main.py`; Bot webhooks are not FastAPI routes. |
| `apps/dsa-web/` | React/Vite product client | Calls `/api/v1` and observes analysis state through polling and task SSE. The production build is served by FastAPI. |
| `apps/dsa-desktop/` | Electron packaging and desktop process coordination | Starts the packaged or local Python backend, waits for `/api/health`, then loads the FastAPI-hosted Web UI. |

## Repository Directory Boundary

| Path | Responsibility |
| --- | --- |
| `src/` | Primary application package for orchestration, services, schemas, persistence, report rendering, and shared runtime logic. |
| `src/market/` | Canonical market-analysis, market-context, phase-prompt, phase-summary, and structure-prompt implementations. The top-level `src/market_analyzer.py`, `src/market_context.py`, `src/market_phase_prompt.py`, `src/market_phase_summary.py`, and `src/market_structure_prompt.py` modules remain compatibility facades. |
| `src/analysis_context_pack/` | Canonical context projection and prompt-rendering implementations. `src/analysis_context_pack_overview.py` and `src/analysis_context_pack_prompt.py` remain compatibility facades. |
| `data_provider/` | Provider adapters, capability routing, normalization, caching, fallback, and health control. |
| `api/` | FastAPI transport, middleware, lifecycle, and public HTTP schemas. |
| `bot/` | Messaging-platform adapters, dispatch, commands, and stream integrations. |
| `strategies/` | Built-in natural-language trading Skill definitions loaded from top-level YAML files and the reserved `personas/` YAML collection. |
| `templates/` | Jinja report presentation templates consumed by the report renderer. |

`src/`, `data_provider/`, `api/`, and `bot/` intentionally remain separate
top-level Python packages. They are stable ownership boundaries, not an
unfinished migration into a single umbrella namespace. GitHub Actions path
filters name the current `api/**` and selected `src/**` surfaces, CI and Docker
smoke checks import all four roots directly, and imports plus documentation
reference these paths throughout the repository. Rehousing them for namespace
aesthetics would create a broad workflow, container, test, and documentation
migration without changing product behavior. Any future unification therefore
requires a separately reviewed migration plan with explicit compatibility,
path-filter, container-smoke, and reference-update coverage.

## Ownership Boundaries

| Area | Owns | Does not own |
| --- | --- | --- |
| `src/application_services.py` | Lazy access to Config, DatabaseManager, SearchService, and AnalysisTaskQueue plus explicit injection | Full dependency injection for every caller; adoption is currently incremental. |
| `src/services/` | Application use cases, task queue adapter, scheduling, analysis, history, portfolio, alerts, intelligence, and rendering services | HTTP transport schemas or provider-specific normalization. |
| `src/core/pipeline.py` and `src/core/stages/` | Analysis orchestration, typed stage outcomes, analysis stages, rendering, and dispatch sequencing | Transport lifecycle or persistent query APIs. |
| `data_provider/` | Market/provider adapters, capability routing, normalization, layered daily caching, priority fallback, health, and circuit control | Product task lifecycle or report presentation. |
| `src/search_service.py` and intelligence/context services | News and intelligence retrieval, context assembly, and source diagnostics | Market-price provider ownership or HTTP presentation. |
| `src/agent/` and `src/llm/` | Native Agent execution, tools, skills, conversation/runtime contracts, and model invocation adapters | Provider configuration source of truth, task lifecycle, or public report persistence. |
| `src/schemas/` | Internal analysis and domain contracts | HTTP request/response DTOs, which live in `api/v1/schemas/`. |
| `src/storage.py`, `src/repositories/`, `src/migrations/` | ORM/database lifecycle, domain persistence adapters, and ordered schema migrations | Pipeline sequencing or transport behavior. |
| `api/` | HTTP routing, middleware, lifespan, transport schemas, SSE and static asset delivery | A second business lifecycle or task status authority. |
| Report and notification paths | `src/schemas/report_schema.py`, `src/services/report_renderer.py`, `templates/`, `src/core/stages/delivery.py`, and notification modules | A `src/reports/` package; no such package exists in the current tree. |

## Analysis Execution Paths

### CLI And Scheduler

```text
main.py
  -> StockAnalysisPipeline.run()
  -> per-stock processing and pipeline stages
```

CLI and scheduled work can use the pipeline's own bounded per-stock concurrency.
This lane is distinct from the API/Bot task lifecycle.

### API And Bot Queue

```text
API POST /api/v1/analysis/analyze with async_mode=true or Bot /analyze
  -> AnalysisTaskQueue
  -> TaskCommand / TaskRunContext
  -> AnalysisService.analyze_stock()
  -> StockAnalysisPipeline.process_single_stock()
  -> polling, SSE, history, or contextual Bot notification
```

The queue is a singleton authority inside one process. The API's synchronous
mode calls `AnalysisService` directly, and Bot `/batch` creates a pipeline in a
background thread; neither path participates in the queue lifecycle. The queue
is not an external broker, durable scheduler, or multi-worker coordination
service. See
[ADR-004](adr/ADR-004-process-local-task-execution-authority.md) and the
[task execution contract](task-execution-contract.md).

### Direct API Services

Some synchronous endpoints call focused application services directly. The queue
is used for background analysis lifecycle, not as a universal service bus.

## Canonical Analysis Data Flow

```mermaid
flowchart TB
  START[Analysis request] -->|start run| RESOLVE[resolve<br/>effective trading date]
  RESOLVE -->|frozen run scope| FETCH[fetch<br/>market inputs]

  subgraph DAILY[Daily-data cache and provider branch]
    direction LR
    DB{Reusable stock_daily data?}
    DB -->|fresh hit| READY[Daily market data prepared]
    DB -->|miss or refresh| CACHE{Provider L1 or L2 fresh hit?}
    CACHE -->|fresh hit| READY
    CACHE -->|miss| PROVIDERS[Capability-filtered provider priority chain]
    PROVIDERS -->|success; cache and stock_daily write| READY
    PROVIDERS -->|all providers fail| STALE{Eligible last-good cache data?}
    STALE -->|yes; marked stale| READY
    STALE -->|no| DEGRADED[Recorded fetch degradation]
  end

  FETCH -->|daily-data lookup| DB

  READY -->|market evidence| INTELLIGENCE[intelligence<br/>news and optional evidence]
  DEGRADED -->|continue with eligible stored data if available| INTELLIGENCE
  INTELLIGENCE -->|evidence with provenance| CONTEXT[context<br/>bounded analysis context]
  CONTEXT -->|analysis input| ANALYZE[analyze<br/>LLM or approved Agent path]
  ANALYZE -->|normalized guarded result| PERSIST[persist<br/>history and eligible context]
  PERSIST -->|stored result| RENDER[render<br/>report representation and artifact]
  RENDER -->|selected output| DISPATCH[dispatch<br/>isolated channel attempts]
  DISPATCH -->|per-channel outcome| COMPLETE[History, report, notification, or contextual reply]
```

The diagram uses one-way, labeled edges. A cache hit bypasses provider calls;
a cache miss enters the configured provider chain; an eligible stale candidate
from the memory or persistent cache is considered only after every provider
fails. With no eligible stale entry, the
`fetch` stage records a typed degradation and the Pipeline may continue with
eligible data already in storage; later stages still surface insufficient data
rather than manufacturing evidence. Provider capability, priority, health,
circuit, cache freshness, and stale-window rules are defined in
[data-source stability](data-source-stability.md) and
[ADR-005](adr/ADR-005-provider-fallback-and-circuit-control.md).

| Stage | Current responsibility | Primary owners |
| --- | --- | --- |
| `resolve` | Resolve and freeze the effective trading date used by resume and history lookup for one stock run. | `src/core/pipeline.py`, market-time and history services |
| `fetch` | Prepare daily, realtime, chip, fundamental, market-phase, and market-structure inputs through database/cache/provider paths. | `data_provider/`, `src/storage.py`, market services |
| `intelligence` | Retrieve fresh or persisted news, social sentiment, and other optional intelligence evidence. | search and intelligence services |
| `context` | Assemble bounded historical, request, and prompt context with provenance and quality state. | analysis context services and schemas |
| `analyze` | Execute normal LLM analysis or the approved Agent path, then normalize and guard the result. | `src/analyzer.py`, `src/analyzer_parts/`, `src/llm/`, `src/agent/` |
| `persist` | Store analysis history and its eligible context snapshot. | `src/repositories/`, `src/storage.py` |
| `render` | Generate the selected report representation and persist local report artifacts. | report schema, renderer, templates, delivery stage |
| `dispatch` | Isolate notification and contextual-reply attempts across configured delivery channels. | delivery stage and notification modules |

## Product Skill And Strategy Execution

Product terminology is **Skill**; **Strategy** remains in user-facing trading
language and compatibility names. The current implementation has one product
runtime authority, not parallel Skill and Strategy engines.

These Skill definitions are declarative packages, not trusted Python system
plugins. Contributors choosing between a YAML / `SKILL.md` definition, a wired
plugin extension point, and a new ADR must follow the
[extension-mechanism decision matrix](plugin-extension-contract.md#choosing-an-extension-mechanism).

```mermaid
flowchart TB
  BUILTIN[Built-in definitions<br/>top-level YAML<br/>and strategies/personas YAML] -->|load| MANAGER[SkillManager<br/>src/agent/skills/base.py]
  CUSTOM[Configured custom directory<br/>top-level YAML or nested SKILL.md] -->|load; same name overrides built-in| MANAGER
  MANAGER -->|catalog clone and activation| ASSEMBLY[Runtime assembly<br/>src/agent/runtime_assembly.py]

  ASSEMBLY -->|active instructions| SINGLE[Single-Agent prompt path]
  SINGLE -->|guarded analysis result| RESULT[Analysis result and dashboard]

  ASSEMBLY -->|active instructions and catalog| MULTI[Multi-Agent orchestration]
  MULTI -->|technical, intelligence, and risk opinions| ENGINE[StrategyEngine<br/>partition, aggregate, synthesize]
  MULTI -->|specialist mode only, after technical opinion| ROUTER[SkillRouter]
  MANAGER -->|available catalog| ROUTER
  ROUTER -->|up to three selected skill ids| AGENTS[SkillAgent specialists]
  MANAGER -->|registered definition and required tools| AGENTS
  AGENTS -->|skill opinions| ENGINE
  ENGINE -->|valid evidence and consensus| DECISION[DecisionAgent]
  ENGINE -->|deterministic strategy_synthesis when skill evidence exists| RESULT
  DECISION -->|guarded decision| RESULT
  RESULT -->|eligible run outputs| CONSUMERS[History and reports]
```

The flow has two execution shapes:

1. `SkillManager` loads built-in top-level YAML definitions from `strategies/`
   plus YAML definitions from the reserved `strategies/personas/` collection.
   Other built-in YAML subdirectories are not discovered. When `AGENT_SKILL_DIR`
   is configured, the manager loads top-level `*.yaml` / `*.yml` files plus
   nested `SKILL.md` bundles from that custom directory. A custom definition
   with the same name replaces the built-in catalog entry.
2. `src/agent/runtime_assembly.py` caches the disk-loaded prototype, returns an
   isolated clone per assembly, resolves active skills, and supplies their prompt
   instructions to both Single-Agent and Multi-Agent paths. `src/agent/factory.py`
   preserves the legacy assembly import and patch surface.
3. In Multi-Agent `specialist` mode only, `SkillRouter` selects explicit,
   manually configured, market-regime, or default skills after the technical
   opinion exists. At most three `SkillAgent` specialists execute their selected
   definitions. Other modes can still receive active skill prompt instructions
   without creating specialist agents.
4. `StrategyEngine` is the current class name for the authoritative skill-opinion
   evidence facade. It removes invalid skill signals to diagnostics, retains
   valid and non-skill opinions, applies eligible aggregation and synthesis, and
   provides the consensus evidence consumed by `DecisionAgent`. Backtest history
   can influence eligible skill weights; Backtesting does not become a Pipeline
   stage.
5. The orchestrator rejects an LLM-authored `strategy_synthesis` and attaches the
   deterministic engine result to the dashboard. History and report renderers
   consume that evidence downstream.

| Surface | Current role | Boundary |
| --- | --- | --- |
| `strategies/` | Built-in natural-language Skill definitions in top-level YAML files plus the reserved `personas/` YAML collection; the directory name is retained for product language and compatibility | Definition catalog, not a second loader or execution engine; other nested YAML directories are not discovered |
| Configured `AGENT_SKILL_DIR` | Optional custom top-level YAML definitions and nested `SKILL.md` bundles | Custom names can override built-ins; no directory is loaded when the setting is empty |
| `src/agent/skills/` | Canonical product runtime: model, loaders, `SkillManager`, defaults, `SkillRouter`, `SkillAgent`, aggregation, synthesis, and `StrategyEngine` | Source of truth for current Skill/Strategy execution semantics |
| `src/agent/runtime_assembly.py` | Tool and Skill catalog assembly, activation, prompt-state resolution, and Single/Multi executor construction | `src/agent/factory.py` remains a compatibility facade, not another authority |
| `src/agent/orchestrator.py` and `src/agent/orchestrator_parts/` | Public `AgentOrchestrator` facade plus private pipeline, execution, dashboard, and chat method owners | The facade retains the legacy class, import, patch, reflection, and reload surface; the parts are internal implementation owners, not another runtime |
| `src/agent/strategies/` | Re-exports legacy `StrategyAgent`, `StrategyRouter`, and `StrategyAggregator` names from `src/agent/skills/` | Compatibility aliases only; do not add a parallel implementation here |
| `.claude/skills/` | Repository collaboration workflows for issue analysis, PR analysis, and issue fixing | Not scanned by `SkillManager` and not part of product runtime architecture |

The root `SKILL.md` documents an external integration and is likewise not the
built-in product Skill catalog. The accepted runtime boundary remains Native
production assembly under [ADR-001](architecture/ADR-001-agent-runtime.md), with
the isolated PydanticAI test/evidence scope governed by
[ADR-002](architecture/ADR-002-pydanticai-runtime-reinstatement.md). This flow
does not expand the lightweight composition root in
[ADR-003](adr/ADR-003-application-services-composition-root.md), replace the
process-local task authority in
[ADR-004](adr/ADR-004-process-local-task-execution-authority.md), or bypass the
provider evidence rules in
[ADR-005](adr/ADR-005-provider-fallback-and-circuit-control.md). Any later
structural extraction must preserve compatibility or record a deliberate
contract change as required by
[ADR-006](adr/ADR-006-behavior-preserving-module-decomposition.md).

<a id="extension-points"></a>
## Extension Points

The versioned plugin boundary is defined by the
[plugin extension contract](plugin-extension-contract.md) and
[ADR-007](adr/ADR-007-versioned-plugin-extension-boundary.md). This section
remains a stable navigation target and does not duplicate or extend that
separately owned contract.

## Runtime Constraints

- The [composition root](adr/ADR-003-application-services-composition-root.md)
  is a compatibility-preserving seam, not proof that every dependency is already
  injected through one object.
- The task authority is process-local. Durable recovery or multi-worker state
  requires a new decision and implementation.
- Agent production assembly is Native-only. PydanticAI is an optional Single RUN
  test/evidence POC with no config, environment, API, Web, Desktop, or Bot
  selector and no runtime fallback. See [ADR-001](architecture/ADR-001-agent-runtime.md)
  and [ADR-002](architecture/ADR-002-pydanticai-runtime-reinstatement.md).
- Database schema changes run through the ordered migration registry. Startup
  compatibility work must not create a second schema-mutation path.
- Provider fallback keeps configured priority and market capability boundaries;
  health and circuit state are process-local observations. See
  [ADR-005](adr/ADR-005-provider-fallback-and-circuit-control.md).

## Focused Documentation

- [Business architecture](business-architecture.md)
- [Foundation pipeline and product layer](foundation-product-architecture.md)
- [ADR registry and process](adr/README.md)
- [Task execution contract](task-execution-contract.md)
- [Data-source stability and fallback](data-source-stability.md)
- [Analysis Context Pack](analysis-context-pack.md)
- [Agent stream events](agent-stream-events.md)
- [Database migrations](database-migrations.md)
- [Notification capabilities](notifications.md)
- [Bot commands and integration](bot-command_EN.md)
- [Desktop packaging](desktop-package.md)
- [Web UI foundation](web-ui-foundation.md)
- [API specification artifact](architecture/api_spec.json)
- [Behavior-preserving decomposition method](adr/ADR-006-behavior-preserving-module-decomposition.md)

## Keeping This Overview Current

Update this document when an entrypoint, ownership boundary, pipeline stage name,
data path, or process constraint changes. Update the business architecture when
a stakeholder, capability, outcome, or value-flow relationship changes. Use an
ADR when the reason or durable policy changes; use the focused living contract
when only detailed mechanics change.
