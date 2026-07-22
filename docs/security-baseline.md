# Security and Compliance Baseline

Status: Maintainer baseline
Last reviewed: 2026-07-21
Applies to: StockPulse backend, API, Web and desktop clients, Agent and Bot integrations, data providers, notifications, reports, automation, and release workflows

## Scope

This document defines the minimum security and compliance expectations for StockPulse. It is a review baseline, not a certification, legal opinion, privacy policy, penetration-test report, or claim that every requirement is already implemented. The [current gaps](#current-gaps) section records incomplete coverage and links each public remediation track.

The baseline covers:

- access control, administrator sessions, and high-risk changes;
- request, configuration, file, tool, and model-input boundaries;
- secrets, credentials, logs, traces, diagnostics, and exported artifacts;
- outbound search, news, model-provider, data-provider, and notification traffic;
- security-relevant audit records and human approval boundaries;
- application dependencies, CI permissions, and third-party Actions;
- investment-analysis disclosures and privacy obligations.

It does not make StockPulse suitable for regulated use by itself. Operators remain responsible for their deployment, network exposure, data processing, retention, licensing, and jurisdiction-specific obligations.

## Threat Model

### Assets

- Provider keys, bot tokens, webhook credentials, administrator credentials, session cookies, and local secret files.
- User configuration, watchlists, reports, analysis history, portfolio data, Agent context, and operational diagnostics.
- Integrity of market data, model prompts and outputs, notifications, release artifacts, and repository automation.

### Actors and trust boundaries

- Anonymous network clients are untrusted.
- Authenticated administrator sessions are trusted only for the permissions explicitly granted to that session. A session is not proof of fresh password possession.
- User-supplied URLs, imported configuration, uploaded files, model output, search results, feed content, provider errors, and webhook responses are untrusted.
- External APIs, package registries, GitHub Actions, model providers, data providers, and notification services are separate trust domains.
- Local filesystem and terminal access are stronger operator privileges, but local files and generated artifacts can still leak credentials.

### Primary threats

- Authentication bypass, session theft, cross-user data access, and unsafe privilege changes.
- Injection, unsafe deserialization, unbounded input, malicious tool arguments, and model-driven capability abuse.
- Secret disclosure through logs, errors, traces, reports, notifications, backups, CI artifacts, or URLs.
- Server-side request forgery (SSRF), redirect or DNS rebinding, proxy abuse, and credential forwarding to an unintended host.
- Dependency or CI compromise, excessive workflow permissions, and non-reproducible builds.
- Misleading financial certainty, missing risk disclosures, or retention and processing of personal data without an explicit contract.

## Requirement Levels

- **MUST**: Required before the affected capability is treated as production-ready or exposed outside a trusted local environment.
- **SHOULD**: Expected unless the change documents a concrete reason, compensating control, owner, and review date.

## Baseline Requirements

### Access and sessions

| ID | Level | Requirement |
| --- | --- | --- |
| `AUTH-01` | MUST | Any API or UI exposed beyond a trusted local environment must enable authentication and use HTTPS. Disabling authentication is a local-development default, not a secure public-deployment mode. |
| `AUTH-02` | MUST | Non-exempt protected routes must reject missing, invalid, expired, or invalidated sessions. Authentication exemptions must be explicit, minimal, and reviewed. |
| `AUTH-03` | MUST | Session cookies must be `HttpOnly`, use an appropriate `SameSite` policy, set `Secure` when served over HTTPS, have a bounded lifetime, and never appear in logs or diagnostics. |
| `AUTH-04` | MUST | Changes that disable or materially weaken authentication must require fresh credential verification. A valid session alone is insufficient. Generic configuration paths must not bypass that check. |
| `AUTH-05` | MUST | Authorization and data ownership must deny cross-user or cross-workspace access by default. Until a multi-user model exists, administrator authentication must not be described as user isolation or role-based access control. |
| `AUTH-06` | SHOULD | Login attempts and other abuse-sensitive endpoints should use bounded rate limits whose client identity is derived only from a documented trusted-proxy topology. |

Current anchors: [`api/middlewares/auth.py`](../api/middlewares/auth.py), [`api/v1/endpoints/auth.py`](../api/v1/endpoints/auth.py), and [PR #292](https://github.com/SiinXu/stock-pulse-ai/pull/292). The current implementation uses an opt-in single-administrator session, signed expiring cookies, file-backed password hashes and session secrets, login throttling, session-secret rotation, and current-password verification before disabling authentication. It is not a multi-user identity or authorization system.

### Input and capability boundaries

| ID | Level | Requirement |
| --- | --- | --- |
| `INPUT-01` | MUST | Validate data at the first trusted boundary with typed schemas or structured parsers. Reject unknown or malformed security-relevant fields instead of silently coercing them. |
| `INPUT-02` | MUST | Bound request bodies, uploaded files, feed and provider responses, text fields, collection sizes, redirects, timeouts, and recursive structures before processing or persistence. |
| `INPUT-03` | MUST | Configuration keys must use canonical syntax, sensitive fields must retain sensitivity metadata, and imports must pass the same validation and authorization rules as interactive updates. |
| `INPUT-04` | MUST | Agent and automation tools must deny unknown tools, schema-invalid arguments, out-of-scope symbols or data, and capabilities not granted to the current execution. Model output must never directly grant a capability. |
| `INPUT-05` | SHOULD | Validation failures should return stable error codes and bounded safe details suitable for correlation without echoing the raw rejected secret or payload. |

Current anchors include the Pydantic API schemas under [`api/v1/schemas/`](../api/v1/schemas/), the configuration registry under [`src/core/config_registry.py`](../src/core/config_registry.py), and the Agent tool contract under [`src/agent/tool_surface.py`](../src/agent/tool_surface.py). Coverage remains capability-specific rather than one complete platform contract.

### Secrets and redaction

| ID | Level | Requirement |
| --- | --- | --- |
| `SECRET-01` | MUST | Secrets must enter through runtime environment variables, deployment secret stores, or explicitly protected local files. Literal secrets must not be committed, embedded in URLs intended for display, or copied into tests and examples. |
| `SECRET-02` | MUST | `.env`, credential files, session secrets, local databases, logs, and generated reports must remain outside version control. Example configuration must use empty values or unmistakable placeholders. |
| `SECRET-03` | MUST | Logs, exception chains, API errors, traces, notification diagnostics, reports, exports, and CI artifacts must remove credentials, authorization headers, cookies, credential-bearing URLs, and caller-supplied exact secret values before they reach a sink. Debug mode does not waive this rule. |
| `SECRET-04` | MUST | Raw configuration backup and restore must require an explicit trusted local mode or authenticated administrator session. Returned settings must mask sensitive fields and must not treat a mask placeholder as a new secret. |
| `SECRET-05` | SHOULD | Operators should rotate a credential after suspected disclosure, remove exposed artifacts, invalidate affected sessions, and record the incident without reproducing the secret. |

Current anchors: [`.gitignore`](../.gitignore), [`.env.example`](../.env.example), [`src/utils/sanitize.py`](../src/utils/sanitize.py), and the backup gate in [`api/v1/endpoints/system_config.py`](../api/v1/endpoints/system_config.py). `log_safe_exception`, bounded diagnostic sanitizers, sensitive configuration metadata, and static exception-log guards provide meaningful coverage, but they do not yet establish a repository-wide guarantee for every provider, trace, and export path.

### Outbound network access

| ID | Level | Requirement |
| --- | --- | --- |
| `NET-01` | MUST | Every user-influenced outbound URL must pass one shared fail-closed policy before a connection is opened. The policy must define allowed schemes, credentials, host syntax, ports, proxies, and destination classes. |
| `NET-02` | MUST | Loopback, private, link-local, reserved, multicast, unspecified, metadata, and other non-public destinations must be blocked by default. DNS results must be checked at connection time, including IPv4 and IPv6 forms. |
| `NET-03` | MUST | Redirect targets must be revalidated, redirect counts and response sizes must be bounded, and DNS rebinding must not bypass destination checks. Credentials must not be forwarded across an unintended origin. |
| `NET-04` | MUST | Search-result content fetching, configurable news or feed sources, custom model and search endpoints, webhooks, and notification tests must use the same policy. A URL parser or `http(s)` scheme check alone is insufficient SSRF protection. |
| `NET-05` | MUST | Outbound requests must have finite timeouts and TLS verification enabled by default. Any opt-out must be explicit, narrowly scoped, documented as risky, and unsuitable for untrusted networks. |
| `NET-06` | SHOULD | Egress denials should emit a stable, redacted security event with the policy reason and correlation identifier, never the credential-bearing URL. |

Current anchors include URL and DNS checks for configurable intelligence feeds in [`src/services/intelligence_service.py`](../src/services/intelligence_service.py), search providers and result fetching in [`src/search_service.py`](../src/search_service.py), and notification senders under [`src/notification_sender/`](../src/notification_sender/). These paths currently apply different validation depths; the required centralized policy is tracked in [#171](https://github.com/SiinXu/stock-pulse-ai/issues/171).

### Auditability and human control

| ID | Level | Requirement |
| --- | --- | --- |
| `AUDIT-01` | MUST | Security-relevant events must record a timestamp, stable event type, actor or execution identity, action, bounded target identifier, outcome, reason code, and correlation identifier. |
| `AUDIT-02` | MUST | Authentication changes, configuration changes, privileged tool calls, analysis execution, export, and protected-data access must be auditable at the boundary where the operation is accepted or rejected. |
| `AUDIT-03` | MUST | Audit records must be append-oriented, access-controlled, redacted, retention-bounded, and distinguish an attempted action from a completed action. Application logs alone are not a durable audit trail. |
| `AUDIT-04` | MUST | High-risk autonomous actions must stop at a defined human approval boundary. Approval, rejection, expiration, and modification decisions must be attributable and auditable. |
| `AUDIT-05` | SHOULD | Analysis evidence should preserve source and model provenance, timestamps, quality or degradation markers, and stable references without exporting raw secrets or unnecessary personal data. |

Current anchors include redacted Agent tool audit records in [`src/agent/tools/execution.py`](../src/agent/tools/execution.py), runtime events under [`src/agent/runtime/`](../src/agent/runtime/), bounded run diagnostics in [`src/services/run_diagnostics.py`](../src/services/run_diagnostics.py), and LLM usage metadata in [`src/llm/usage.py`](../src/llm/usage.py). They are useful operational records, but there is no single durable security-audit contract across every sensitive operation.

### Supply chain and automation

| ID | Level | Requirement |
| --- | --- | --- |
| `SUPPLY-01` | MUST | Production, CI, desktop, and optional dependency sets must have a documented reproducibility and update policy. Direct sources must be immutable; resolved versions must be reviewable; security updates must not depend on unconstrained resolution. |
| `SUPPLY-02` | MUST | Third-party GitHub Actions must be pinned to reviewed immutable commit SHAs. Automated updates must preserve the pin and expose the upstream release identity in review. |
| `SUPPLY-03` | MUST | Every workflow must declare least-privilege top-level permissions and add job-level write permissions only where required. Fork pull requests must not receive repository secrets or a write-capable token. |
| `SUPPLY-04` | MUST | Release and publish jobs must separate build from credentialed publication, validate artifact provenance and expected paths, and require the narrowest practical token scope. |
| `SUPPLY-05` | SHOULD | CI should detect known vulnerable dependencies, stale immutable pins, unexpected lock changes, and permission expansion while providing an explicit exception workflow. |

Current anchors: [`requirements.txt`](../requirements.txt), [`requirements-pydanticai.txt`](../requirements-pydanticai.txt), the npm lockfiles under [`apps/`](../apps/), and [`.github/workflows/`](../.github/workflows/). The optional PydanticAI closure is exactly versioned and npm installs use lockfiles, while the default Python environment and most workflow Action references are not immutable. The remaining reproducibility and least-privilege work is tracked in [#326](https://github.com/SiinXu/stock-pulse-ai/issues/326).

### Financial and privacy compliance

| ID | Level | Requirement |
| --- | --- | --- |
| `COMP-01` | MUST | User-visible analysis must state that AI-generated output is informational or for research support, is not investment advice, involves market and data risk, and does not guarantee an outcome. |
| `COMP-02` | MUST | Equivalent disclosures must remain materially consistent across reports, Web surfaces that present recommendations, notifications, exports, and supported languages. A feature-specific notice does not replace the product-level disclosure. |
| `COMP-03` | MUST | Data-source freshness, missing coverage, model uncertainty, fallback or degradation, and simulated or experimental status must not be presented as verified fact or guaranteed performance. |
| `COMP-04` | MUST | Personal data must have a defined purpose, owner, access boundary, retention period, and deletion or export path before multi-user or long-term-memory features claim privacy compliance. Collect only what the capability requires. |
| `COMP-05` | SHOULD | Material changes to financial terminology or disclosures should receive domain and native-language review; machine checks are supporting evidence, not legal or linguistic approval. |

Current anchors include the project disclaimer in [`README.md`](../README.md), localized report footer text in [`src/report_language.py`](../src/report_language.py), report and notification rendering in [`src/notification.py`](../src/notification.py), and the terminology controls in [`docs/financial-terminology-guide.md`](financial-terminology-guide.md). Disclosure coverage is not yet governed consistently across every report, UI, notification, and language.

## Secure Change Checklist

Every new or materially changed capability must answer these questions in its issue or pull request:

- What untrusted inputs, protected assets, actors, and external trust domains are introduced or changed?
- Which requirement IDs in this baseline apply, and where is each enforced?
- Are authentication, authorization, fresh reauthentication, and human approval boundaries explicit?
- Are sizes, timeouts, redirects, retries, parser depth, and tool capabilities bounded?
- Can any secret or personal data reach logs, traces, errors, reports, notifications, exports, caches, or CI artifacts?
- Does any user-influenced value select an outbound origin, file path, command, model tool, or data scope?
- Are denial, timeout, fallback, rollback, and partial-failure paths tested at the real risk boundary?
- Are dependency, workflow permission, deployment, API/client compatibility, documentation, and changelog effects covered?
- Does user-facing financial language preserve uncertainty, provenance, limitations, and the non-advice disclosure?
- What remains unverified, who owns it, and what is the rollback method?

## Current Gaps

This table is a scope and ownership map, not an exploit guide. Sensitive implementation details must not be added to public issues.

| Gap | Current boundary | Follow-up |
| --- | --- | --- |
| Multi-user identity, role and workspace authorization, consent, data ownership, export, deletion, and privacy audit are not implemented. | `AUTH-05`, `COMP-04` | [#230](https://github.com/SiinXu/stock-pulse-ai/issues/230) |
| Agent tool schema, capability, data-scope, and network enforcement is not yet one complete deny-by-default sandbox. | `INPUT-04`, `NET-04`, `AUDIT-02` | [#191](https://github.com/SiinXu/stock-pulse-ai/issues/191), coordinated with [#137](https://github.com/SiinXu/stock-pulse-ai/issues/137) and [#214](https://github.com/SiinXu/stock-pulse-ai/issues/214) |
| Redaction coverage is not yet systemic across every provider error, Agent trace, webhook diagnostic, and exported artifact. | `SECRET-03` | [#176](https://github.com/SiinXu/stock-pulse-ai/issues/176) |
| Search, news, model endpoints, and notification URLs do not yet share one fail-closed SSRF and egress policy. | `NET-01` through `NET-06` | [#171](https://github.com/SiinXu/stock-pulse-ai/issues/171) |
| Structured Agent observability is not yet a complete queryable cross-stage event and trace foundation. | `AUDIT-01` through `AUDIT-03` | [#222](https://github.com/SiinXu/stock-pulse-ai/issues/222) |
| Analysis reports do not yet provide a complete exportable, redacted evidence chain and audit package. | `AUDIT-05` | [#127](https://github.com/SiinXu/stock-pulse-ai/issues/127) |
| High-risk Agent actions do not yet have configurable, attributable human approval gates. | `AUDIT-04` | [#251](https://github.com/SiinXu/stock-pulse-ai/issues/251) |
| Default Python dependency resolution, third-party Action pinning, and explicit workflow permission coverage do not yet meet the reproducibility and least-privilege baseline. | `SUPPLY-01` through `SUPPLY-05` | [#326](https://github.com/SiinXu/stock-pulse-ai/issues/326) |
| Product-level investment and limitation disclosures are not yet guaranteed consistently across every report, notification, Web surface, and supported language. | `COMP-01` through `COMP-03`, `COMP-05` | [#144](https://github.com/SiinXu/stock-pulse-ai/issues/144) |

## Review Cadence

- Apply the secure change checklist to every security-sensitive pull request.
- Review this baseline and all linked open gaps at least quarterly, and before a release that materially expands network exposure, autonomous capabilities, user identity, data retention, or financial decision presentation.
- Re-review immediately after a security incident, credential disclosure, material dependency advisory, authentication change, new outbound URL surface, or change in applicable product or privacy obligations.
- Record the review date and evidence in the relevant issue or pull request. Update this document only when requirements, observed implementation, ownership, or follow-up links change.
- A passing CI run is necessary evidence, not proof that threat modeling, semantic review, or the linked gaps are complete.
