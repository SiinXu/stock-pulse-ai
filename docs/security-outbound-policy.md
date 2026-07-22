# Outbound HTTP Security Policy

StockPulse applies one fail-closed policy to HTTP targets that can be selected by an operator, a caller, or an upstream response. This includes search-result content, configurable search and intelligence sources, explicit model base URLs, HTTP notification targets, notification tests, and platform reply webhooks.

The policy is enabled without configuration. A default installation can reach public HTTP(S) services, while loopback and other non-public destinations are denied.

## Default Policy

| Control | Default behavior |
| --- | --- |
| Schemes | Only `http` and `https` are accepted. |
| URL credentials | User information such as `https://user:password@host/` is rejected. |
| Destination classes | Loopback, private, link-local, reserved, multicast, unspecified, metadata, shared, and other non-public addresses are denied. |
| DNS | Every address returned for the target host is checked when the connection resolves it. A mixed public/private answer is rejected. |
| Redirects | Library redirects are disabled. StockPulse follows at most five redirects itself and checks every target before the next connection. |
| Redirect credentials | Authorization, cookies, common API-key/token headers, request auth, and client certificates are removed when a redirect changes origin. |
| Proxies | Environment HTTP proxies are disabled at this boundary so a proxy cannot bypass destination checks. |
| Timeout | Calls without a narrower caller timeout receive a 15-second timeout. |
| Response size | Non-streaming responses are limited to 8 MiB. Streaming consumers apply their own smaller domain limit. |
| TLS | Certificate verification remains enabled unless an existing, explicit channel option disables it. Disabling verification is unsafe on untrusted networks. |
| Denial logs | A denial records a stable event, correlation ID, reason, scheme class, host type, and allowlist state. It never records the URL, query, credentials, or headers. |

Numeric and alternate IP forms are normalized before classification. Decimal, octal, hexadecimal IPv4 forms and IPv4-mapped IPv6 therefore do not bypass the policy.
Percent encoding in a URL hostname is rejected so policy preflight and the HTTP transport cannot interpret different destinations.

## Allow A Trusted Self-Hosted Service

Set `OUTBOUND_HTTP_ALLOWLIST` only when the process must reach a trusted non-public HTTP service:

```dotenv
OUTBOUND_HTTP_ALLOWLIST=localhost:11434,searxng.internal:8080,10.0.0.20:3000
```

Rules:

- Entries are comma-separated exact hostnames or IP addresses.
- An optional port narrows an entry to that port. An entry without a port permits all ports on that exact host, so prefer `host:port`.
- Do not include a scheme, path, query, fragment, wildcard, username, password, API key, or token.
- Hostname matching is exact after case, trailing-dot, Unicode, IDNA, and IP normalization.
- The allowlist can permit a trusted loopback or private destination. It cannot permit metadata, link-local, reserved, multicast, or unspecified destinations.
- Listing a hostname trusts all of its non-hard-blocked DNS answers. Keep control of that hostname and its DNS records.

Common examples include a local Ollama or Hermes endpoint, a private SearXNG instance, and a self-hosted Gotify, ntfy, or custom webhook service. Public services do not need an allowlist entry.

Restart long-running processes after changing the environment. For Docker, pass the value through the existing `--env-file` or Compose `env_file` path. The repository's default GitHub Actions workflows only inject explicitly mapped variables; a custom workflow must map this variable itself, and its runner must have a valid network route to the self-hosted service.

## Rejection Behavior

A blocked request raises an outbound policy error before the prohibited connection is opened. Existing best-effort paths, such as notifications or optional content enrichment, handle that request failure using their normal channel/provider fallback. The security decision itself is always fail-closed.

Representative log shape:

```text
Outbound request rejected event=outbound_request_rejected correlation_id=<id> reason=private_ip_blocked scheme=http host_type=ip allowlisted=false
```

The log intentionally omits the target host and complete URL. Use the correlation ID, call-site logs, and configuration name to locate the rejected operation without copying a credential-bearing URL into diagnostics.

Typical reasons include:

- `scheme_not_allowed` or `credentials_not_allowed`
- `local_host_blocked`, `private_ip_blocked`, or `metadata_host_blocked`
- `private_dns_address` or `restricted_dns_address`
- `dns_resolution_failed` or `dns_no_usable_address`
- `unexpected_dns_target` for an SDK redirect or proxy outside its configured base URLs
- `redirect_limit_exceeded`, `redirect_missing_location`, or `response_too_large`

## Operational Checks

1. Leave `OUTBOUND_HTTP_ALLOWLIST` empty and confirm public search/model/notification endpoints still work.
2. Test a private target and confirm it fails with an `outbound_request_rejected` event.
3. Add the narrowest required `host:port` entry, restart the process, and retest that one self-hosted service.
4. Confirm `WEBHOOK_VERIFY_SSL` remains enabled. An allowlist entry does not make plaintext HTTP or disabled certificate verification safe.
5. Remove obsolete entries when a self-hosted service is retired or moved.

## Limits

- The policy governs HTTP(S). SMTP, database protocols, and WebSocket connections have separate libraries and are not converted into HTTP policy exceptions.
- Third-party SDKs that use an explicit model base URL are guarded during their DNS activity. Provider SDK traffic with no caller-selected base URL continues to use the provider library's fixed service contract.
- DNS checks protect the destination selected by the application. They do not replace host firewall rules, container/network egress controls, or cloud-level service controls.
- An allowlist is a deliberate trust decision, not a discovery mechanism. Do not add a broad shared hostname merely to silence a rejection.

## Rollback

Clear `OUTBOUND_HTTP_ALLOWLIST` to restore the secure default after testing a self-hosted target. To roll back the code change, revert the outbound-policy change set; no database or stored-data migration is involved.
