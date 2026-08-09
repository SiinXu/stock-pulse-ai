# Risk Manager final-action authority

The Risk Manager is the mandatory, deterministic authority immediately before a
buy, hold, or sell recommendation is published. It extends
`src/agent/risk_override.py`; it does not add a second risk engine and never
calls an LLM.

## Covered exits

- Multi-Agent and Investment Committee dashboard finalization
- Single-Agent dashboard conversion
- Multi-strategy deliberation projection, after later guardrails
- Agent Chat, before response and conversation-history publication

Each exit projects real dashboard and bounded runtime risk evidence into the
same evaluator. The final action returned by that evaluator is then reused by
the dashboard, `AnalysisResult`, report, notification, API payload, persisted
raw report, DecisionSignal metadata, and chat history.

## Verdicts and profiles

The canonical verdict set is `pass`, `downgrade`, and `reject`. Every result uses
the bounded `risk-manager-result/v1` shape and includes the original action,
final action, reason/evidence codes, profile, exit ID, evaluation ID, timestamp,
and optional authorized-bypass ID. Raw prompts and model reasoning are never
stored in this shape.

Set `RISK_GATE_PROFILE` to one of:

| Profile | Policy |
| --- | --- |
| `conservative` | Intervenes on any supported elevated-risk evidence and rejects explicit vetoes. |
| `balanced` | Default. Downgrades directional conflicts, vetoes, high-severity flags, and explicit downgrade adjustments. |
| `aggressive` | Intervenes only on explicit blocking evidence or an enabled legacy override transition. |

Invalid values stop configuration loading. The gate cannot be disabled. The
legacy `AGENT_RISK_OVERRIDE` flag still controls legacy override planning, but
turning it off cannot bypass the mandatory final-action authority.

Missing evidence by itself produces `pass`; it is not fabricated. Evidence with
an invalid bounded field or malformed timestamp is marked invalid and blocks a
new bullish publication. Timestamped evidence older than 24 hours is retained
with its provenance, marked stale, and also blocks a new bullish publication.

## Failure and approval semantics

An internal evaluation failure is fail-closed. A buy becomes hold and the
structured result records `reject`, `gate_internal_failure`, and
`fail_closed=true`; the original buy is never published accidentally.

For operational recovery, inspect the stable `exception_type`, `exit_id`, and
`evaluation_id` diagnostics in the structured result, correct the invalid
configuration/evidence or runtime fault, and rerun the analysis. Recovery must
not disable or bypass the gate; a one-shot approval is the only authorized way
to retain an action that the working gate recommends changing.

`/approvals` remains an optional, one-shot bypass. A consumed approval preserves
the original action, stores the approval ID in the structured result, and uses
wording that says the original action was authorized. It must not claim that a
downgrade was applied.

## Rollback

Revert the change. There is no schema migration: new persisted fields are
additive JSON metadata. Do not add a disable switch as a rollback mechanism.
