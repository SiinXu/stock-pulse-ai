# Agent / Strategy Simulation Sandbox

Safe simulation environment for agent and strategy experiments (Issues #247, #202, #442).

## Division of labor

| Surface | Owns | Does not own |
| --- | --- | --- |
| **Sandbox** (`src/agent/sandbox/`) | Environment isolation and safety: isolated config, fake clock, read-only live or snapshot data, `SIMULATION` labels, hard fences against production DecisionSignal / analysis-history / notification / order writes, agent-variant comparison traces, promotion **receipts** | Historical scoring methodology |
| **Backtest** (V30 / `BacktestService`, Web backtest) | Historical validation methodology: forward windows, engine versioning, resolution notes, performance metrics over analysis history | Live safety envelope for experimental agent configs |
| **ToolSurface sandbox** (#630) | Tool-execution security boundary | Research simulation environment |
| **Paper portfolios** (#370) | Forward paper ledger on portfolio accounts | Multi-variant agent isolation |
| **What-if chat** (#130) | Collaborative preview isolation in chat | Full sandbox runner / promotion receipt |

Passing a sandbox or backtest run **never** becomes automatic execution authority. Promotion produces a reviewable receipt only.

## Batch-1 scope (this document)

1. **Sandbox execution environment**
   - `SandboxContext`: isolated config overlay, `FakeClock`, `readonly_live` or `snapshot` data mode
   - Always labeled `SIMULATION` / mode=`sandbox`
   - Isolation policy fail-closed (`persist_decision_signal=false`, `send_real_notifications=false`, …)
2. **Agent variants**
   - `SandboxRunner` / `run_agent_variant_in_sandbox` / `compare_variants`
   - Production-comparable traces (`sandbox-trace-v1`) project to strict `agent-trajectory-input-v1` via `trajectory_compatible_runs()` (no extra keys; simulation metadata stays on the `SandboxTrace` / `trajectory_projection()` side-car)
3. **Hard no-write fence**
   - Active sandbox refuses production DecisionSignal writes, decision-memory flag upserts, analysis-history persistence (authoritative `save_analysis_history` boundary), and real notification dispatch
   - Blocked effects are recorded for promotion receipts
   - Counterexample tests in `tests/agent/test_agent_sandbox.py`

### Batch-1 non-goals (declared, not silently enforced)

- **Process-wide wall clock**: `FakeClock` is used only when the sandbox runner / variant code reads `SandboxContext.clock`. It does not monkey-patch `datetime.now` or `utc_naive_now` globally.
- **Real order / portfolio writes**: policy constants document intent; trade paths are not yet fenced in batch-1 (paper portfolio remains a separate surface).
- **Agent memory vector writes**: policy documents intent; memory `add` paths are not yet fenced in batch-1.
- Live `AgentExecutor` / ToolSurface integration and Web multi-scenario UI are later batches.

## Usage (library)

```python
from src.agent.sandbox import (
    FakeClock,
    SandboxContext,
    SandboxRunRequest,
    SandboxRunner,
    active_sandbox_context,
    run_agent_variant_in_sandbox,
)

ctx = SandboxContext.create(
    fixed_now="2026-08-01T12:00:00Z",
    data_mode="snapshot",
    snapshot={"quote:AAPL": {"close": 190.5}},
    agent_variant_id="conservative",
    config_overlay={"risk": "low"},
    source_data_window={"from": "2026-01-01", "to": "2026-06-30"},
)

result = run_agent_variant_in_sandbox(
    SandboxRunRequest(prompt="Stress rates +50bp", agent_variant_id="conservative"),
    context=ctx,
)
assert result.to_dict()["simulation"] is True
assert result.promotion_receipt.auto_promote is False
assert result.promotion_receipt.review_required is True

# Side-by-side variants
runner = SandboxRunner()
pair = runner.compare_variants(
    SandboxRunRequest(prompt="Stress rates +50bp"),
    variants=[
        {"id": "conservative", "config": {"risk": "low"}},
        {"id": "aggressive", "config": {"risk": "high"}},
    ],
    base_context=ctx,
)
```

## Promotion receipt

Schema: `sandbox-promotion-receipt-v1`. Required fields include:

- `sandbox_run_id`, `source_data_window`, `config_digest`
- `simulated_actions`, `blocked_external_effects`, `rejected_actions`
- `assumptions` classified as `observed` / `inferred` / `not_checked`
- `risk_boundary` (default forces paper-only)
- `production_authority_scope`
- `first_live_run_guard` (`notification_only` | `small_scope` | `human_approval_required`)
- `rollback_condition`
- `review_required=true`, `auto_promote=false` (hard)

## Safety fences (production write paths)

| Path | Fence |
| --- | --- |
| `DecisionSignalService.create_signal*` | `EFFECT_DECISION_SIGNAL` |
| `DecisionSignalMemoryFlagRepository.upsert` | `EFFECT_DECISION_MEMORY` |
| `DatabaseManager.save_analysis_history` (all callers) | `EFFECT_ANALYSIS_HISTORY` |
| `NotificationService.send_with_results` | `EFFECT_NOTIFICATION` |

Fences raise `SandboxExternalEffectBlocked` only while a `SandboxContext` is active via `active_sandbox_context`. Outside sandbox, production paths are unchanged. Pipeline history stage logs `sandbox_analysis_history_write_blocked` when the authoritative fence refuses a write (does not mislabel it as generic storage failure).

## Related

- Issue #247 (parent safe sandbox)
- Issue #202 (research sandbox)
- Issue #442 (sandbox enhancement / multi-scenario)
- `docs/agent-observability.md` (production L0 events; sandbox traces stay field-comparable)
- Backtest UI manual: `docs/ui-manual/09-backtest.md`
