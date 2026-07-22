# ADR-005: Preserve Priority Fallback With Market-Scoped Circuit Control

- Status: `Accepted (retrospective)`
- Decision date: 2026-07-21
- Recorded: 2026-07-21
- Decision owners: StockPulse maintainers
- References: [PR #290](https://github.com/SiinXu/stock-pulse-ai/pull/290), merge `7b3f80f1cfb4f7337853559656bc26e05b9ff22c`, [PR #312](https://github.com/SiinXu/stock-pulse-ai/pull/312), [`docs/data-source-stability.md`](../data-source-stability.md), [ADR-007](ADR-007-versioned-plugin-extension-boundary.md)

## Context

Daily market data already tried another provider when one provider failed, but
the circuit policy was fixed, health meant only consecutive exceptions, and an
open-circuit skip was absent from persisted provider-run diagnostics. Operators
could not inspect recent success, error, latency, cooldown, or recovery state.

The change had to preserve market capability boundaries, configured static
priority, empty-result behavior, and the rule that one provider failure should
not abort an analysis when an eligible fallback exists.

## Decision

Keep provider selection priority-based and fail-open. Market capability filtering
runs before health policy, and fallback chooses the next configured,
capability-valid provider that can currently be attempted. Health and circuit
state are isolated by data type, market, and provider so one market cannot poison
another.

Circuit admission, the provider call, provider-only timing, outcome
classification, and health mutation are serialized at the per-provider boundary.
The state machine is `closed`, `open`, and `half_open`:

- exceptions advance the circuit failure streak;
- an open provider is skipped until its cooldown permits one probe;
- only a usable half-open result restores normal traffic;
- an empty or `None` result is a health-quality failure, not a successful
  recovery, while its closed-state behavior remains compatible with later retry.

Health observations are bounded and process-local. Optional configuration keeps
the historical failure threshold and cooldown as defaults; disabling circuit
skips restores static retry behavior while retaining observations. This decision
does not introduce adaptive provider reordering or persisted cluster-wide health.

Provider failures, circuit skips, actual fallback target, and final success are
written to existing diagnostics through centralized sanitization. Raw provider
exceptions and credentials do not enter public diagnostics.

## Consequences

- A temporarily failing provider stops delaying every request while eligible
  alternatives continue the analysis.
- Serialized final admission prevents queued calls from bypassing a circuit that
  just opened, at the cost of per-provider concurrency.
- Operators can inspect redacted health and fallback metadata without changing
  the public data-return contract.
- Health resets on process restart and does not coordinate across workers.
- Real provider rate limits and unusual live latency distributions remain an
  operational risk beyond deterministic failure-path tests.

## Later Compatible Evolution

PR #312 later added bounded health-based ordering only among contiguous,
sufficiently sampled, closed providers at the same static numeric priority.
Static priority changes, sparse providers, and open or half-open providers stay
uncrossable anchors. This evolution remains inside this ADR's capability-first,
static-priority, and process-local health boundaries; it does not amend the
historical statement that ADR-005 itself did not introduce adaptive ordering.
ADR-007 requires plugin-supplied providers to preserve both contracts.
