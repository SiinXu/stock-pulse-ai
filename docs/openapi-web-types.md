# OpenAPI Web Types And Runtime Validation

English developer guide for generating TypeScript types from the backend OpenAPI
schema and piloting runtime response validation in the Web app.

## Why this exists

The backend exposes Pydantic schemas through FastAPI. The Web app historically
maintained independent hand-written TypeScript modules under
`apps/dsa-web/src/types/` and converted API payloads with
`toCamelCase<T>()` — an unchecked cast. A backend field rename can compile on
both sides and fail only at runtime deep in a React component.

This track closes that gap in two layers:

1. **Generated types** from the live OpenAPI document (compile-time drift gate).
2. **Runtime validation** on selected API modules (fail closed with the existing
   `ParsedApiError` UX).

## Artifacts

| Path | Role |
| --- | --- |
| `scripts/export_openapi.py` | Offline, deterministic OpenAPI JSON export |
| `apps/dsa-web/openapi.json` | Checked-in schema snapshot consumed by codegen |
| `apps/dsa-web/src/types/api.generated.ts` | Generated TypeScript (`openapi-typescript`) |
| `apps/dsa-web` script `generate:api-types` | Regenerates `api.generated.ts` |
| CI job `openapi-types-gate` | Regenerates and fails on uncommitted drift |

Hand-written modules under `apps/dsa-web/src/types/*.ts` remain the **public
camelCase contract** for UI code during the migration. Generated types document
the backend snake_case OpenAPI shapes and are imported where a module needs a
schema anchor or path reference.

## Local workflow

From the repository root, with backend CI Python deps installed:

```bash
# 1. Export OpenAPI (offline: temp DATABASE_PATH, no credentials, litellm stub)
python scripts/export_openapi.py

# 2. Regenerate frontend types
cd apps/dsa-web
npm ci
npm run generate:api-types

# 3. Confirm no drift
git diff --exit-code -- apps/dsa-web/openapi.json apps/dsa-web/src/types/api.generated.ts
```

`export_openapi.py` mirrors the E2E backend isolation pattern: it clears ambient
product env, writes a temporary `ENV_FILE`, points `DATABASE_PATH` at a temp
sqlite file, and stubs optional heavy imports. Run it twice and `diff` the
outputs when diagnosing non-determinism.

**Version pin:** regenerate with the same FastAPI / Pydantic versions as
`.github/requirements-ci.txt` / `constraints.txt` (for example
`fastapi==0.140.0`). A newer or older FastAPI can change binary-upload and
`ValidationError` OpenAPI shapes and will fail `openapi-types-gate` even when
route contracts are unchanged.

## Runtime-validation pilot pattern

Pilot module: `apps/dsa-web/src/api/stocks.ts` (`getQuote`, `getDailyHistory`).

Pattern:

1. Receive the snake_case JSON body from axios.
2. Convert with `toCamelCase` (same helper as before).
3. `zod.safeParse` against a camelCase schema aligned with the OpenAPI field set.
4. On **success**: return the **toCamelCase object** (not Zod's stripped output)
   so valid payloads stay byte-identical to the pre-validation path.
5. On **mismatch**: `throw createApiError(createParsedApiError({ code:
   'api_response_validation_failed', ... }))` so UI layers already using
   `getParsedApiError` surface a stable error without a new UX channel.

Do **not** invent a parallel toast or error surface. Reuse `ParsedApiError`.

## Migration checklist for remaining modules

When migrating another `apps/dsa-web/src/api/*.ts` module:

1. Identify OpenAPI path + `components.schemas` entries in `api.generated.ts`.
2. Add a camelCase Zod schema for each response shape the module returns.
3. Replace `toCamelCase<T>(...)` return sites with the parse helper (success path
   still returns the camelCase object). Prefer shared
   `apps/dsa-web/src/api/parseCamelCasePayload.ts` over a local copy.
4. Extend the module's vitest file for pass-through (including unexpected extra
   keys when using `.passthrough()`) and mismatch → `api_response_validation_failed`.
5. Keep request encoding (snake_case bodies) unchanged unless the module already
   validates requests.
6. Do not delete the hand-written type module until all call sites and the UI
   agree on generated/camelCase projection helpers (follow-up work).


## Convention for new Web API modules (required)

Any **new** resource client under `apps/dsa-web/src/api/` that returns JSON from
the FastAPI surface **must**:

1. Anchor response (and request, when useful) shapes on
   `components['schemas'][...]` from `api.generated.ts`.
2. Validate camelCase responses with Zod (or the shared parse helper) before
   returning to UI code.
3. On mismatch throw `createApiError(createParsedApiError({ code:
   'api_response_validation_failed', ... }))` — no parallel error UX.
4. Ship vitest coverage for pass-through and at least one mismatch path.
5. Regenerate and commit `openapi.json` + `api.generated.ts` in the same change
   when the backend schema changes (`openapi-types-gate` is blocking).

**Documented skips** (do not invent a second contract system for these):

- SSE / streaming (`EventSource`, chunked chat stream)
- Binary blob downloads (`responseType: 'blob'`) and browser download helpers
- Pure URL builders with no response body
- Shared infrastructure (`error/`, `utils.ts`, `parseCamelCasePayload.ts`,
  `index.ts`)

If a backend route cannot be anchored because OpenAPI emits an empty response
schema, keep runtime validation and file a backend schema fix; do not
reintroduce unchecked casts. Historical `/api/v1/auth/status` was this case;
generated `AuthStatusResponse` is now the Web client export (`auth.ts` binds
`components['schemas']['AuthStatusResponse']`, requires all five fields, and
accepts only `enabled` / `password_retained` / `no_password`).

## Suggested optional guard (owner decides whether to gate)

A lightweight inventory helper can flag resource clients that still use unchecked
`toCamelCase` without importing `api.generated` or `parseCamelCasePayload`:

```bash
python scripts/check_web_api_openapi_migration.py
# optional strict mode for CI later:
# python scripts/check_web_api_openapi_migration.py --fail-on-pending
```

**Default:** advisory only (exit 0, prints pending modules). Turning
`--fail-on-pending` into a blocking CI job is an **owner decision** — do not
enable it until the remaining documented skips and intentional projections are
explicitly allowlisted. Existing blocking gate remains `openapi-types-gate`
(artifact drift only).

## Migration status snapshot (issue #721)

Clusters already on generated types + runtime validation:

- Pilot: `stocks` (`getQuote` / `getDailyHistory` / `getFieldTrust`, plus POST
  `/stocks/extract-from-image` and POST `/stocks/parse-import` sharing generated
  `ExtractFromImageResponse` / `ExtractItem`; both path 200 JSON bodies are
  mutually equivalent to the component; the compile-time bind is snake_case
  `components['schemas']`; runtime Zod is a camelCase projection through shared
  `parseCamelCasePayload` and does not re-export the generated snake_case type
  as the UI `ExtractFromImageResponse`; this is not the auth export-alias
  pattern)
- Portfolio: `portfolio`, `backtest`, `decisionSignals`, `scorecard`
- System: `systemConfig`, `approvals`, `usage`, `securityAudit`
- Integrations: `alerts`, `alphasift`, `intelligence`, `investmentFramework`,
  `localModels`, `modelPacks`, `plugins`, `calculators`
- Analysis: `analysis`, `history`, `scheduledTasks`, `agent` (plain JSON)

Additional modules completed in the remaining-module batch:

- Full migrate: `configProfiles`, `skillOutcomes`, `reportVersionCompare`,
  `valuation`, `reportExport` (capabilities JSON; blob download remains a skip)
- Onboarding JSON: `plan` / `apply` / `state` / `reset` now use the same
  generated-anchor + `parseCamelCasePayload` fail-closed path as first-run and
  demo-analysis. Omitted collection fields default to `[]` after a successful
  parse so wizard `.map` / `.length` call sites stay defined. Extra server keys
  remain via `.passthrough()`.
- Anchors on already-validated clients: `auth` (exported `AuthStatusResponse`
  binds generated `components['schemas']['AuthStatusResponse']`; `authEnabled`,
  `loggedIn`, `passwordSet`, `passwordChangeable`, and `setupState` are required;
  `setupState` accepts only `enabled` / `password_retained` / `no_password`; GET
  `/status` and POST `/settings` share the same passthrough parser),
  `notificationInbox`, `outboundActivity`, `todaysFocus`, `watchlistGroups`,
  `watchlistScores`, `portfolioRiskMetrics`, `portfolioHealth` (GET
  `/portfolio/health` and POST `/portfolio/health/refresh` share generated
  `PortfolioHealthResponse`; the compile-time bind is snake_case
  `components['schemas']`; runtime Zod stays a camelCase projection and does
  not re-export the generated snake_case type as the UI
  `PortfolioHealthResponse`; this is not the auth export-alias pattern),
  `eventCalendar` (alert-trigger list composition)

`apps/dsa-web/src/types/portfolioInsights.ts` now CamelizeKeys-binds the four
generated response components (`PortfolioLevelAnalysisResponse`,
`StressScenarioListResponse`, `PortfolioStressTestResponse`,
`PortfolioRebalancingResponse`) plus nested shock, scenario, and impact
schemas. `Override` preserves today's public required arrays, literals
(`autoExecute: false`, `isSuggestionOnly: true`), and the narrow
`StressPositionImpact` / assumptions projections; extra generated keys are
optional only. This is **not** the auth export-alias pattern: generated
snake_case is not the UI type. Request types (`PortfolioBasketRequest`,
`PortfolioStressPresetQuery`, `PortfolioStressCustomRequest`,
`PortfolioRebalanceQuery`) stay handwritten optional because OpenAPI marks
defaulted fields required. Runtime Zod in `api/portfolioInsights.ts` is
unchanged.

`apps/dsa-web/src/types/outboundActivity.ts` now CamelizeKeys-binds the three
generated response components (`LocalOnlyModeStatus`, `OutboundActivityItem`,
`OutboundActivityPage`). `Override` preserves today's required
`allowedDestinationClasses` / `items` arrays and the handwritten
`OutboundDecision` `'allowed' | 'blocked'` union. Path 200 JSON for GET
`/api/v1/security/local-only` and GET `/api/v1/security/outbound-activity` is
mutually equivalent to those components. This is **not** the auth export-alias
pattern: generated snake_case is not the UI type. `OutboundActivityListQuery`
stays handwritten optional `{ limit?: number }` because there is no generated
query schema. Runtime Zod in `api/outboundActivity.ts` is unchanged.

`apps/dsa-web/src/types/scorecard.ts` now CamelizeKeys-binds the five
generated response components (`SignalScorecardResponse`, `ScorecardBucket`,
`ScorecardOverall`, `ScorecardReturnBand`, `ScorecardMiss`). `Override`
preserves today's required-nullable nested metrics (`hitRatePct`,
`avgReturnPct`, `sharePct`, `returnPct`, `anchorDate`) and the handwritten
`ScorecardBucketStatus` `'ok' | 'insufficient_data' | string` documentation
union. Path 200 JSON for GET `/api/v1/scorecard` (`getPublicSignalScorecard`)
is mutually equivalent to `SignalScorecardResponse`. This is **not** the auth
export-alias pattern: generated snake_case is not the UI type. Runtime Zod in
`api/scorecard.ts` is unchanged.

`apps/dsa-web/src/types/approvals.ts` now CamelizeKeys-binds the six
generated Approval object components (`ApprovalContext`, `ApprovalProposal`,
`ApprovalProposalPage`, `ApprovalRule`, `ApprovalRuleUpdateRequest`,
`ApprovalDecisionRequest`) plus three closed string-enum aliases
(`ApprovalRiskSource`, `ApprovalStatus`, `ApprovalDecision`). Enum aliases
are allowed (string enums, not objects). `Override` preserves today's
optional `stockCode`, optional widened `action` (`'risk_control_bypass' |
string`), closed signal/status/decision/risk-source unions, optional
`consumedAt` / `updatedAt`, overridden nested `items` / `context` arrays,
and mixed-alias `expectedVersion` on the rule-update request (generated
key is already `expectedVersion`, not `expected_version`; `expires_in_seconds`
/ `risk_sources` stay snake on the generated schema; this is documented as
generated fact, not fixed). Path 200 JSON for GET `/api/v1/approvals`, GET
and PUT `/api/v1/approvals/rules/risk-control-bypass`, GET
`/api/v1/approvals/{proposal_id}`, and POST
`/api/v1/approvals/{proposal_id}/decision` is mutually equivalent to those
components; PUT and decision request bodies pin `ApprovalRuleUpdateRequest`
/ `ApprovalDecisionRequest`. This is **not** the auth object export-alias
pattern: generated snake_case is not the UI type, and
`ApprovalDecisionRequest` is not a public export (`approvalsApi.decide`
stays three arguments). Runtime Zod in `api/approvals.ts` is unchanged.

`apps/dsa-web/src/types/watchlistScore.ts` now CamelizeKeys-binds the seven
generated WatchlistScore object components (`WatchlistScoreFactorSource`,
`WatchlistScoreFactor`, `WatchlistScoreItem`, `WatchlistScoreQueryCount`,
`WatchlistScoreSourceRows`, `WatchlistScoreResponse`,
`WatchlistScoreRequest`) plus closed string-enum aliases
(`WatchlistScoreFactorKey`, `WatchlistScoreFactorStatus`,
`WatchlistScoreDegradationReason`, `WatchlistScoreStatus`,
`WatchlistScoreSortMode`, `WatchlistScoreFreshness`). Enum aliases are
allowed (string enums, not objects). `Override` preserves today's
required-nullable fields (`id` / `sourceReportId` / `profile` / `asOf` /
`expiresAt` / `value` / `reason` / `score` / `asOf` / `ageDays` /
`analysisId` / `operationAdvice`) and required arrays (`factors` /
`degradedReasons` / `items`). There is **no** mixed-alias `expectedVersion`
on this schema: every generated object key is snake_case
(`stock_code`, `formula_version`, `query_count`, `source_rows`,
`degraded_reasons`, `age_days`, `analysis_id`, `as_of`, `expires_at`,
`source_report_id`, `operation_advice`, `disclaimer_key`, `scoring_mode`).
Path 200 JSON for POST `/api/v1/watchlist/scores`
(`scoreWatchlistSymbols`) is mutually equivalent to
`WatchlistScoreResponse`; the request body pins generated
`WatchlistScoreRequest` (internal only; `watchlistScoresApi.score` stays
`ScoreWatchlistParams`). This is **not** the auth object export-alias
pattern: generated snake_case is not the UI type.
`WatchlistScoreRequest` / `WatchlistScoreQueryCount` /
`WatchlistScoreSourceRows` are not public exports. Runtime Zod in
`api/watchlistScores.ts` is unchanged, including the local `toCamelCase`
helper and `.strict()` schemas.

Keep issue #721 open until residual intentional skips are documented and
owners accept residual risk: SSE/streaming, binary blob downloads, checker
`[review]` allowlist (`backtestRunOutcome`, evidence/research pack exporters),
and whether `--fail-on-pending` becomes a CI gate. Use `Refs #721` /
`Refs #226` on incremental PRs. Do not close #721 from an onboarding-only
slice.

## CI drift gate

Job name: **`openapi-types-gate`** (blocking, always runs after `ai-governance`).
The active `main` ruleset requires this exact check-run context, so generated
artifact drift cannot be bypassed by merging after unrelated checks pass.

Steps:

1. Install backend CI requirements.
2. `python scripts/export_openapi.py --output apps/dsa-web/openapi.json`
3. `npm ci` + `npm run generate:api-types` in `apps/dsa-web`
4. `git diff --exit-code` on the two checked-in artifacts

If the gate fails: regenerate locally, commit both files, and push. Do not hand-
edit `api.generated.ts`.

## Web error contract

`apps/dsa-web/src/api/error.ts` is the compatibility facade for existing Web
imports. Parsing, heuristic categorization, stable display copy, formatting,
taxonomy classification, and public exports live under `apps/dsa-web/src/api/error/`;
callers should not import those implementation modules directly.

The version-one API envelope keeps `error` as the stable machine code and
adds optional `category` / `severity` taxonomy fields derived from that code
(see [API Error Taxonomy](api-error-taxonomy_EN.md)). Clients must not replace
or ignore `error` when taxonomy fields are present.

`ApiErrorAlert` presents errors through the shared persistent Toast. A caller
action is rendered only when it has both a label and a handler. The remediation
catalog and taxonomy may supply an existing localized label for a
caller-provided retry handler, a localized label plus an in-app Settings/login
destination, or a Related-docs link that opens repository documentation.
Retry is never inferred without an operation-owned handler (clearing the error
alone is not a retry). Entries without either a handler or destination remain
guidance-only and never render a dead button. Raw diagnostic messages are
intentionally not rendered in the Toast.

This is the Web V0+taxonomy contract. CLI and desktop-native error presentation
are not covered by the catalog or Toast remediation in this phase.

Long-running work, 409 busy/duplicate, queue/in-progress/terminal presentation,
and launch-block recovery are documented separately in the
[async task UX contract](async-task-ux-contract.md) (issue #885). That contract
consumes this parse/catalog surface; it does not replace it.

## Related documents


- Historical OpenAPI snapshot: [`architecture/api_spec.json`](architecture/api_spec.json)
  (not the CI-gated artifact; prefer `apps/dsa-web/openapi.json` for typegen).
- Web API modules: `apps/dsa-web/src/api/`
- Error compatibility facade: `apps/dsa-web/src/api/error.ts`
- Error implementation modules: `apps/dsa-web/src/api/error/`
- Async task / busy UX: [`async-task-ux-contract.md`](async-task-ux-contract.md)
