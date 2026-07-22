# Architecture Decision Records

This directory is the canonical index and process for StockPulse Architecture
Decision Records (ADRs). ADRs explain why a durable boundary or constraint was
chosen. Living contracts and implementation guides describe the current
mechanics; runnable code remains authoritative when documentation drifts.

## Location And Numbering

- ADR numbers are repository-wide, three digits, monotonic, and never reused.
- New files use `ADR-NNN-short-kebab-title.md` and live in `docs/adr/`.
- `ADR-001` and `ADR-002` predate this directory. They remain at their stable
  `docs/architecture/` paths and reserve those numbers globally.
- Accepted records are not renumbered or rewritten to hide history. A material
  change uses a new ADR and reciprocal amendment or supersession links.
- Use [the template](template.md) for new records.

## Statuses

| Status | Meaning |
| --- | --- |
| `Proposed` | Open for review; not yet an architectural commitment. |
| `Accepted` | Approved and expected to govern new work. |
| `Amended` | Still active, with a later ADR changing part of the decision. |
| `Superseded` | Replaced by a later ADR; retained as history. |
| `Rejected` | Considered and declined; retained to prevent repeated debate. |

Retrospective records use `Accepted (retrospective)` and cite the merged PRs or
commits that established the decision. They must not invent alternatives or
rationale that the historical evidence does not support.

## When A Pull Request Needs ADR Consideration

A pull request must consider an ADR when it changes one or more of these areas:

- component ownership, dependency direction, or composition boundaries;
- a cross-module source of truth, lifecycle, state machine, or public contract;
- runtime, persistence, deployment, scheduling, security, or failure policy;
- an extension mechanism or dependency that creates a durable maintenance cost;
- a large structural migration whose compatibility method should be reused.

The PR should either link a new or existing ADR, or explain why the change stays
within an accepted decision and does not require a new record. Local bug fixes,
documentation corrections, and mechanical changes normally do not need an ADR
unless they alter one of the boundaries above.

## Process

1. Search the registry before proposing a new decision.
2. Copy `template.md`, allocate the next unused number, and set `Proposed`.
3. Link concrete issue, code, contract, benchmark, or PR evidence in `References`.
4. Review the ADR with the implementation PR or in a preceding docs PR.
5. On acceptance, record the decision date and update this registry.
6. If the decision changes later, create a new ADR and link both records. Keep
   detailed operational mechanics in the relevant living contract.

## Registry

| ADR | Status | Decision | Primary evidence |
| --- | --- | --- | --- |
| [ADR-001](../architecture/ADR-001-agent-runtime.md) | Accepted / Amended by ADR-002 | Native-only production Agent assembly behind a vendor-neutral runtime contract | Runtime decision history through 2026-07-19 |
| [ADR-002](../architecture/ADR-002-pydanticai-runtime-reinstatement.md) | Accepted | Optional PydanticAI Single RUN test/evidence POC with no product selector or fallback | PR #60 and subsequent reconciliation |
| [ADR-003](ADR-003-application-services-composition-root.md) | Accepted (retrospective) | Lightweight process composition root with lazy compatibility accessors | [PR #83](https://github.com/SiinXu/stock-pulse-ai/pull/83) |
| [ADR-004](ADR-004-process-local-task-execution-authority.md) | Accepted (retrospective) | One process-local task execution lifecycle and status authority | [PR #90](https://github.com/SiinXu/stock-pulse-ai/pull/90), [PR #103](https://github.com/SiinXu/stock-pulse-ai/pull/103) |
| [ADR-005](ADR-005-provider-fallback-and-circuit-control.md) | Accepted (retrospective) | Priority-based provider fallback with market-scoped health and circuit control | [PR #290](https://github.com/SiinXu/stock-pulse-ai/pull/290), compatible evolution in [PR #312](https://github.com/SiinXu/stock-pulse-ai/pull/312) |
| [ADR-006](ADR-006-behavior-preserving-module-decomposition.md) | Accepted (retrospective) | Staged oversized-module extraction behind compatibility facades | [PR #291](https://github.com/SiinXu/stock-pulse-ai/pull/291), [PR #293](https://github.com/SiinXu/stock-pulse-ai/pull/293), [PR #296](https://github.com/SiinXu/stock-pulse-ai/pull/296), [PR #297](https://github.com/SiinXu/stock-pulse-ai/pull/297) |
| [ADR-007](ADR-007-versioned-plugin-extension-boundary.md) | Accepted | Versioned plugin lifecycle and six policy-preserving extension points | [PR #339](https://github.com/SiinXu/stock-pulse-ai/pull/339) |
