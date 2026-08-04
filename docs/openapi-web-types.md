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
   still returns the camelCase object).
4. Extend the module's vitest file for pass-through (including unexpected extra
   keys when using `.passthrough()`) and mismatch → `api_response_validation_failed`.
5. Keep request encoding (snake_case bodies) unchanged unless the module already
   validates requests.
6. Do not delete the hand-written type module until all call sites and the UI
   agree on generated/camelCase projection helpers (follow-up work).

## CI drift gate

Job name: **`openapi-types-gate`** (blocking, always runs after `ai-governance`).

Steps:

1. Install backend CI requirements.
2. `python scripts/export_openapi.py --output apps/dsa-web/openapi.json`
3. `npm ci` + `npm run generate:api-types` in `apps/dsa-web`
4. `git diff --exit-code` on the two checked-in artifacts

If the gate fails: regenerate locally, commit both files, and push. Do not hand-
edit `api.generated.ts`.

## Related documents

- Historical OpenAPI snapshot: [`architecture/api_spec.json`](architecture/api_spec.json)
  (not the CI-gated artifact; prefer `apps/dsa-web/openapi.json` for typegen).
- Web API modules: `apps/dsa-web/src/api/`
- Error contract: `apps/dsa-web/src/api/error.ts`
