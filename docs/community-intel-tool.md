# Community Intelligence Agent Tool Contract

StockPulse defines a stock-scoped `get_community_intel_brief` Agent Tool for
bounded community and social evidence. This document describes Phase A of the
contract. Phase A is deterministic and provider-neutral: it does not call a
live social API, scrape websites, register the tool in the default catalog, or
change an existing analysis path.

The pull request for this phase references Issue #548 without closing it.
Live-provider wiring, an optional Skill, report projection, and additional
sources remain later phases.

## Execution Boundary

The tool is a built-in `ToolDefinition` created by
`build_community_intel_tool(provider)`. A caller must explicitly register the
definition in a `ToolRegistry`; every call then runs through `ToolSurface` or a
`BoundToolSession`. The definition sets `enforce_contract=True`, declares the
`stock` scope dimension, and requires `community_intel:read` permission.

This preserves the existing execution boundaries:

- exact tool-name and allowlist checks;
- strict input schema and optional-default materialization;
- stock-scope rejection before provider dispatch;
- timeout, serialization, result-size, audit, and late-result boundaries;
- redacted diagnostics.

The factory is intentionally absent from `ALL_SEARCH_TOOLS` and the process
registry. An installation with no future adapter therefore exposes no new tool
to Single or Multi Agent runs and has no new prompt, request, latency, rate
limit, or cost behavior.

## Input Contract

| Field | Contract |
| --- | --- |
| `stock_code` | Required provider-portable stock symbol; it must also match the frozen analysis stock scope |
| `window_days` | Optional integer, default `7`, minimum `1`, hard maximum `30` |
| `language_hint` | Optional `en` or `zh`, default `en` |

An Agent cannot supply a provider URL, credential, query, account, cookie, or
source list. A definition-level stock scope is mandatory even on the Native
compatibility runner.

## Output Contract

Every handler result uses `schema_version=community-intel-brief-v1` and the
same strict shape:

| Field | Meaning |
| --- | --- |
| `status` / `degraded` / `reason_code` | `available`, `degraded`, or `unavailable`, with a stable reason for every non-available result |
| `stock_code` / `language` | Canonical subject and requested projection language |
| `as_of` / `window` | Timezone-qualified evidence time and bounded source window; unavailable results use `null` source times |
| `summary` / `tone` | Bounded neutral summary and `bullish`, `bearish`, `mixed`, or `unclear` tone |
| `confidence` / `confidence_basis` | A validated `0..1` score with a bounded basis; no-evidence results use `null`, never an invented neutral score |
| `themes` / `volume_signal` | Capped themes and `low`, `normal`, `elevated`, or `unavailable` activity signal |
| `coverage` / `citations` / `gaps` | Capped source coverage, credential-free references, and explicit evidence gaps; raw posts are forbidden |
| `disclaimer` | Mandatory financial-risk statement |

Provider observations use immutable Pydantic v2 models with strict types,
forbidden extra fields, finite confidence bounds, timezone-aware ordered
timestamps, unique source coverage, and citations tied to a covered source.
The tool rejects a mapping, free-form text, raw post list, mismatched stock,
mismatched window, or mismatched language as invalid provider output.

Prompt-facing strings pass through the central sensitive-data sanitizer.
Counts and field lengths are capped, and the complete serialized result has an
8 KiB hard limit. A citation URL replaced by the sanitizer is omitted while its
safe source/reference id is retained and `citation_url_redacted` is recorded as
an evidence gap.

## Degradation Contract

| Reason | Result behavior |
| --- | --- |
| `provider_not_configured` | `unavailable`; provider is absent or explicitly reports no credential/configuration |
| `no_data` | `unavailable`; the bounded provider found no evidence for the stock/window |
| `provider_timeout` | `degraded`; a provider reports its own bounded timeout without exposing technical details |
| `provider_error` | `degraded`; an optional provider failure is safely logged and isolated |
| `invalid_provider_output` | `degraded`; strict output, identity, time, or source relationships failed |
| `output_too_large` | `degraded`; the validated projection exceeded the prompt payload limit |
| `partial_coverage` | `degraded`; usable evidence exists with missing/partial sources or redacted references |

A harder `ToolSurface` execution deadline returns its existing structured
`timeout` error instead of publishing a late provider result. Both timeout
paths preserve the surrounding Agent degradation semantics; neither invents a
brief or turns social tone into trading authority.

## Provider And Outbound Boundary

Phase A tests inject deterministic in-memory providers. There is no operator
setup, API key, live account, network request, quota, or provider charge for
this phase. In particular, the existing `SOCIAL_SENTIMENT_API_KEY` setting and
legacy `SocialSentimentService` prompt injection are not connected to this
tool contract.

A later live adapter must reuse an approved existing service or other bounded
provider, use StockPulse's central outbound HTTP policy for every request,
document terms, rate limits, cost, and retention, and return the strict
observation model. It must not add browser cookies, unrestricted scraping, raw
post dumps, a parallel plugin execution route, or a second Agent framework.

## Limitations And Disclaimer

- Phase A proves the execution and evidence contract only; it supplies no real
  community coverage.
- Community data can be incomplete, manipulated, duplicated, delayed, or
  unrepresentative of the broader market.
- Tone and volume are supporting evidence. Risk and Decision stages retain
  their existing authority.
- No result should be interpreted as a recommendation, target price, or
  prediction of future performance.

Every result includes:

> Community and social signals are unverified supporting evidence, not
> investment advice or trading authority.

## Verification And Rollback

Deterministic tests cover allowed execution, real stock-scope denial before
provider dispatch, hard ToolSurface timeout, provider timeout, empty/no-key
states, provider failure, invalid output, redaction, payload size, strict JSON,
and absence from the default catalog. Tests do not access a real provider.

Rollback is a revert of the Phase A pull request. There is no database
migration, configuration value, remote data, default registry entry, API
contract, Web/Desktop behavior, report field, or notification payload to
restore.
