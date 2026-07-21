# Foundation Pipeline And Product Layer

- Status: `Living`
- Last verified: 2026-07-21
- Scope: contribution placement, contract direction, upstream porting, and provenance

StockPulse uses two architectural responsibility tracks inside one repository:
a reusable **foundation pipeline** and a **product layer** built on its contracts.
This note explains where a change belongs and how the tracks evolve together.
The [architecture overview](architecture-overview.md) remains the source for the
current component map, entrypoints, and execution paths.

## Scope And Non-Goals

The two tracks are review and ownership lenses. They are not separate Git
branches, repositories, packages, services, deployables, or release trains.
Both integrate through this repository's `main` branch. A module can contain
code serving both tracks, so placement follows the source of truth and behavior
being changed rather than a directory label alone.

This policy does not redesign the runtime, introduce an upstream synchronization
mechanism, or replace detailed contracts. Significant new decisions still use
the [ADR process](adr/README.md); current mechanics remain in their focused
documents.

## Responsibility Tracks

| Track | Owns | Typical homes | Must avoid |
| --- | --- | --- | --- |
| Foundation pipeline | Headless analysis semantics; provider capability routing, normalization, caching, health, fallback, and circuit behavior; shared domain schemas and persistence; canonical analysis and pipeline-stage contracts, including domain report meaning and render/dispatch outcomes | `data_provider/`, `src/core/`, and the relevant foundation-facing parts of `src/services/`, `src/schemas/`, `src/repositories/`, `src/llm/`, and storage/report modules | Depending on Web, Desktop, repository governance, or product-only presentation to perform a reusable analysis |
| Product layer | FastAPI transport DTOs, projections, and product use cases; process-local task submission, execution, lifecycle, retry/cancel, and observation; Web and Desktop experiences; Bot integrations; conversational and advanced Agent experiences; product report presentation, notification channel integrations, release automation, and community governance | `api/`, `apps/dsa-web/`, `apps/dsa-desktop/`, `bot/`, product-facing services and Agent modules, `.github/`, and product documentation | Reimplementing provider selection, pipeline orchestration, domain persistence, domain report meaning, or task authority behind a product-specific path |

These tracks define the preferred responsibility direction, not proof that every
current dependency is already separated. The pipeline currently composes report
and notification delivery. Treat that as an evolution seam: the foundation owns
render/dispatch sequencing and outcome contracts, while product presentation and
notification channel adapters remain product concerns. Decoupling must preserve
current behavior and follow the compatibility and ADR rules below.

The stages in the
[canonical analysis data flow](architecture-overview.md#canonical-analysis-data-flow)
describe reusable analysis responsibilities, not mandatory processes or public
APIs. Product code may initiate or observe a run, but it must consume the shared
pipeline, service, task, schema, and report contracts. Domain report schema and
meaning belong in the foundation; API DTOs and enrichment plus client views
belong in the product layer. Changes must preserve the mapping between them.

Agent placement follows the same rule. A headless capability required for the
canonical `analyze` stage belongs with the foundation contract. Conversation
sessions, interactive research flows, UI controls, and product-specific Agent
orchestration belong in the product layer. The directory name alone does not
decide the track.

## Interaction Boundary

The current paths cross the boundary in these ways:

- CLI and scheduled runs call the analysis pipeline directly.
- Synchronous API analysis and Bot `/batch` call shared application or pipeline
  paths directly. Async API analysis and Bot `/analyze` submit work to the
  process-local task queue; the queue is not a durable broker or a universal
  service bus.
- The Web client consumes `/api/v1` through credential-bearing HTTP and SSE,
  with admin-session enforcement only when authentication is enabled. Task
  polling provides a recovery path. The client does not call market providers
  or storage directly.
- Desktop starts the Python backend, waits for `/api/health`, and loads the same
  FastAPI-hosted Web application. It is a product shell, not another analysis
  implementation.

See the [task execution contract](task-execution-contract.md) for task lifecycle
semantics, the [Web architecture contract](../apps/dsa-web/ARCHITECTURE.md) for
dependency direction inside the Web client, and
[desktop packaging](desktop-package.md) for distribution mechanics.

## Contribution Placement

Route a change by asking which contract must remain authoritative:

| Change | Primary track | Required boundary check |
| --- | --- | --- |
| Add or repair a market provider, normalization rule, cache, or fallback | Foundation | Preserve provider capability, priority, diagnostics, timeout, and degradation contracts. |
| Change analysis inputs, stage outcomes, persistence, or domain report meaning | Foundation first | Preserve existing consumers or evolve the contract additively, then update every affected product projection and surface. |
| Add an API endpoint or DTO/projection, Web page, Desktop behavior, Bot interaction, or product-specific notification | Product | Reuse application and domain contracts; do not create a second analysis or task lifecycle. |
| Add an Agent tool used by every headless analysis | Foundation | Keep the tool independent of product sessions and rendering. |
| Add interactive chat, research, or Agent presentation | Product | Consume stable Agent and analysis contracts and keep UI/session concerns out of the foundation. |
| Change CI, releases, issue automation, contribution policy, or repository governance | Product | Keep permissions minimal and do not couple foundation runtime behavior to repository automation. |

A cross-track PR must identify the shared source of truth, preserve compatibility
across domain schemas, API projections, task state, and report views, and
validate all affected consumers.
Prefer additive evolution. If a breaking change is unavoidable, document its
migration and rollback and sequence the foundation contract before or together
with product adoption. Follow [AGENTS.md](../AGENTS.md) for validation and
documentation duties.

Changing a durable boundary, runtime model, persistence model, security/failure
policy, or cross-module authority requires ADR consideration. Reuse an accepted
record when it already governs the change; otherwise add a new ADR. Structural
work that claims no behavior change follows
[ADR-006](adr/ADR-006-behavior-preserving-module-decomposition.md).

## Upstream Porting Policy

`SiinXu/stock-pulse-ai` and its `main` branch are the integration authority for
StockPulse. `ZhuLinsen/daily_stock_analysis` is a read-only source and reference
for this project. The repository has no tracked automatic upstream-sync
workflow, and contributors must not assume that an `upstream` Git remote exists.

Port an upstream-compatible foundation fix deliberately:

1. Record the source repository and commit or PR so provenance is reviewable.
2. Isolate the relevant behavior in a focused change; do not wholesale-merge or
   overwrite StockPulse product work.
3. Adapt the fix to current StockPulse schemas, task and pipeline contracts,
   accepted ADRs, security rules, and licensing notices.
4. Run the validation required for the affected paths and pass the normal
   StockPulse PR and CI process.
5. Resolve conflicts in favor of current accepted StockPulse contracts, or
   record a deliberate contract change in a new ADR.

Generic foundation fixes should remain free of Web, Desktop, and governance
dependencies so they stay portable. Product-only work is not an upstream-port
candidate by default. Any proposal to send a change to the upstream project is
a separate maintainer decision and is never a prerequisite for merging a
StockPulse fix.

## License And Provenance Boundary

Architectural track does not determine license. The root [LICENSE](../LICENSE)
is authoritative:

- Upstream or original `ZhuLinsen/daily_stock_analysis` code remains under its
  MIT license and copyright notice.
- New and substantially modified StockPulse contributions in either track are
  AGPL-3.0-only.
- Both copyright notices and license texts must be retained. When code is
  ported, preserve its source provenance as well as the applicable notices.
- The combined work and network-use obligations follow the terms stated in the
  root license notice.

Do not infer a file's license from whether it is called foundation or product,
or from its directory. When provenance is uncertain, resolve it before merging.

## Keeping This Policy Current

Update this note when contribution placement, contract direction, upstream
porting, or license-provenance rules change. Update the architecture overview
when runtime topology or component ownership changes. A policy reversal should
be recorded through the ADR process rather than silently rewriting history.
