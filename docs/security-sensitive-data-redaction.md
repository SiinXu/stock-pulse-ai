# Sensitive-Data Redaction

StockPulse applies one central redaction rule set before operational data crosses a log, error, trace, audit, or diagnostic boundary. Redaction is enabled unconditionally; debug mode changes verbosity, not the secret-handling policy.

## Covered Boundaries

- Application logs written to the console, regular log files, and debug log files.
- Structured exception summaries and retry diagnostics.
- Version-one API error envelopes, including nested `params`, `details`, and the legacy `detail` alias.
- Approved HTTP error compatibility headers (`Retry-After` and `WWW-Authenticate`); arbitrary exception headers are dropped.
- Run Diagnostic snapshots, Run Flow metadata, historical diagnostic summaries, and copyable diagnostic text.
- Agent progress/SSE metadata, Tool Surface audit previews, and execution-trace arguments.
- Provider errors from model discovery, channel capability tests, Hermes, local CLI backends, and AlphaSift public diagnostics.
- Single-agent provider protocol traces before persistence.

The central implementation is `src/utils/sanitize.py`. Callers that already have the exact runtime credential can also pass it as an exact redaction value; this closes gaps for provider-specific tokens that do not have a recognizable prefix.

## What Is Redacted

The shared rules cover:

- Mapping keys that denote API keys, tokens, passwords, credentials, secrets, cookies, authorization, webhooks, complete header/prompt/proxy fields, or raw responses. Safe usage counters such as `prompt_tokens` remain intact.
- `Authorization` and `Proxy-Authorization` values, including Bearer, Basic, Token, and Digest forms.
- Bearer values and labelled assignments such as `OPENAI_API_KEY=...`, `access_token: ...`, or JSON secret fields.
- Common prefixed credentials, including OpenAI/Anthropic-style `sk-` keys, Stripe secret keys, GitHub tokens, Slack tokens, Google API keys, AWS access-key IDs, and SendGrid keys.
- Userinfo credentials in HTTP URLs and non-HTTP connection strings such as PostgreSQL, MySQL, Redis, MongoDB, and AMQP DSNs.
- Known webhook capability URLs and URLs whose query or fragment contains a sensitive key or token.

Public payload redaction preserves ordinary text, normal public URLs, numeric values, and collection structure. Credential-bearing HTTP(S) URLs are redacted completely by default; the established Run Diagnostics display keeps only the host after removing userinfo, as do non-HTTP DSNs, so operators can identify the failing service. Logs use the stricter diagnostic formatter and redact every HTTP(S) URL.

The canonical markers are `[REDACTED]` and `[REDACTED_URL]`. Existing Run Diagnostics responses retain their compatible `<redacted>` and `<redacted-url>` display markers.

## Agent Trace Behavior

Tool audit and execution-trace fields are recursively redacted before they are exposed. SSE progress metadata is redacted at the public downgrade boundary.

Provider protocol traces are different: provider reasoning and tool-call signatures must remain byte-faithful to be replayable. StockPulse therefore applies the central detector before persistence and drops the complete trace with reason `sensitive_data_redacted` if any field would require masking. It never persists a partially modified signed trace. The visible conversation and current run still complete normally; only future protocol-trace replay is unavailable for that turn.

## Failure And Debug Behavior

- HTTP 5xx responses remain generic and discard private server payloads.
- HTTP 4xx responses preserve their public error semantics after recursive redaction.
- A malformed or unrenderable redaction input fails closed to a fixed marker instead of returning the original value.
- Debug logs use the same formatter as other handlers. There is no setting that enables raw secrets in debug output.
- Redaction is stateless and does not rewrite saved configuration or rotate credentials.

## Limits

Pattern redaction cannot prove that an arbitrary, unlabelled string is a secret. New integrations must place credentials under clearly sensitive keys, pass known exact values to the central redactor, and avoid including credentials in exception text in the first place. Local CLI diagnostics additionally mask long opaque token-like values because those subprocesses may emit credential material without labels.

This boundary does not rewrite normal report/chat content or authenticated System Configuration backup exports. A configuration backup is intentionally credential-bearing and must be stored as a secret. Redaction is also not a substitute for access control, encrypted transport, log retention, credential rotation, or removing historical log files created before this policy was deployed.

If a secret may have appeared in an output, rotate or revoke it, restrict access to the affected artifact, and remove the artifact according to the deployment's retention policy. Do not paste real credentials into issues or redaction tests.

## Verification And Rollback

Deterministic coverage is in `tests/security/test_sensitive_redaction.py`; it exercises logs, API errors, Agent traces/SSE, diagnostics exports, provider errors, and tool audits without network access.

Rollback is a revert of the redaction change. No database or configuration migration is required. Reverting restores the prior, less complete leak boundary and should not be used as a workaround for an integration that emits secrets.
