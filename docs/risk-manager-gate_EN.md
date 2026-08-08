# Risk Manager Gate

Mandatory decision-exit risk evaluation for Issue #120. This upgrades the existing
`src/agent/risk_override.py` module — it does **not** introduce a parallel risk
engine or change the final report JSON schema.

## Call-path map (current)

```
Single Agent (AgentExecutor dashboard)
  → analysis_results._agent_result_to_analysis_result
  → apply_risk_manager_gate(exit=single_agent)

Multi-Agent / Investment Committee
  → orchestrator dashboard finalization
  → _apply_risk_override
  → apply_risk_manager_gate(exit=orchestrator_multi_agent|committee_mode)
  → existing AGENT_RISK_OVERRIDE plan + optional HITL bypass

Deliberation projection
  → analysis_agent (when multi-strategy deliberation is on)
  → apply_risk_manager_gate(exit=deliberation_projection)
  → build_pipeline_final_explanation (explanation only)

Agent Chat
  → orchestrator_parts.chat.chat
  → apply_risk_manager_gate(exit=agent_chat)
```

Every exit **must** call the gate. Skipping an exit is considered incomplete.

## Outcomes

| Outcome | Signal | User-visible effect |
| --- | --- | --- |
| `pass` | unchanged | no mandatory note |
| `attach_warning` | unchanged | appends `[Risk Manager] ...` to `risk_warning` |
| `downgrade` | more conservative | signal change + mandatory note |

Rules are **deterministic** (risk flags, veto, signal_adjustment, evidence/conclusion
conflict, confidence mismatch). The gate never calls an LLM.

## Configuration

| Env | Default | Meaning |
| --- | --- | --- |
| `RISK_GATE_ENABLED` | `true` | Run the gate at every exit |
| `RISK_GATE_STRICT` | `false` | Force-downgrade on risk evidence even when `AGENT_RISK_OVERRIDE=false` |
| `AGENT_RISK_OVERRIDE` | `true` | Existing force-downgrade authority when its plan `will_apply` |

**Default mode choice:** warn-first. Changing every existing buy to a forced
downgrade would be a breaking user-visible change. Strict mode is opt-in.

## Trace / fail-safe

- Each evaluation stores `ctx.meta["risk_gate_result"]` and
  `ctx.data["risk_gate_applied"]` (low-sensitivity dict for T03-style traces).
- If the gate itself throws, analysis continues with the original signal and a
  `fail_safe=true` pass result (`gate_internal_failure`).

## Compatibility

- Does not remove or replace `AGENT_RISK_OVERRIDE` / HITL approval bypass.
- Does not alter `runner.py` log format or report schema fields.
- Optional Web Settings registry entries are intentionally deferred (config
  registry ownership is outside this change); env defaults work without Web UI.

## Rollback

Set `RISK_GATE_ENABLED=false`, or revert the PR. No data migration.
