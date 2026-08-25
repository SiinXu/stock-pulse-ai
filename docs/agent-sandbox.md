# Agent / Strategy Simulation Sandbox

In-process simulation environment for trusted agent and strategy experiments (Issues #247, #202, #442).

This runner is a repository-level simulation boundary, not an OS/container or
ToolSurface security boundary. A `variant_callable` and `live_reader` must be
trusted application code. The sandbox fences the authoritative production
write paths listed below; it cannot prevent arbitrary Python code from opening
files, sockets, or ungoverned third-party clients.

## Division of labor

| Surface | Owns | Does not own |
| --- | --- | --- |
| **Sandbox** (`src/agent/sandbox/`) | Simulation context and repository-level safety: isolated config, fake clock, read-only live or snapshot data, `SIMULATION` labels, hard fences against known production DecisionSignal / analysis-history / notification / portfolio writes, agent-variant comparison traces, promotion **receipts** | Historical scoring methodology; untrusted-code isolation |
| **Backtest** (V30 / `BacktestService`, Web backtest) | Historical validation methodology: forward windows, engine versioning, resolution notes, performance metrics over analysis history | Live safety envelope for experimental agent configs |
| **ToolSurface sandbox** (#630) | Tool-execution security boundary | Research simulation environment |
| **Paper portfolios** (#370) | Forward paper ledger on portfolio accounts | Multi-variant agent isolation |
| **What-if chat** (#130) | Collaborative preview isolation in chat | Full sandbox runner / promotion receipt |

Passing a sandbox or backtest run **never** becomes automatic execution authority. Promotion produces a reviewable receipt only.

## Current scope

1. **Sandbox execution environment**
   - `SandboxContext`: isolated config overlay, `FakeClock`, `readonly_live` or `snapshot` data mode
   - Always labeled `SIMULATION` / mode=`sandbox`
   - Isolation policy fail-closed (`persist_decision_signal=false`, `send_real_notifications=false`, `write_production_portfolio=false`, …)
   - Public context and result payloads reject NaN / ±Inf, non-JSON values, and payloads over the sandbox budget
   - Variant failures return a generic labeled error; raw exception diagnostics are sanitized logs only
2. **Agent variants**
   - `SandboxRunner` / `run_agent_variant_in_sandbox` / `compare_variants`
   - Production-comparable traces (`sandbox-trace-v1`) project to strict `agent-trajectory-input-v1` via `trajectory_compatible_runs()` (no extra keys; simulation metadata stays on the `SandboxTrace` / `trajectory_projection()` side-car)
3. **Hard no-write fence**
   - Active sandbox refuses production DecisionSignal writes, decision-memory flag upserts, analysis-history persistence (authoritative `save_analysis_history` boundary), real notification dispatch, and every production portfolio repository mutation
   - Blocked effects are recorded for promotion receipts
   - Counterexample tests in `tests/agent/test_agent_sandbox.py`

### Non-goals and absent write surfaces

- **Process-wide wall clock**: `FakeClock` is used only when the sandbox runner / variant code reads `SandboxContext.clock`. It does not monkey-patch `datetime.now` or `utc_naive_now` globally.
- **Arbitrary Python isolation**: trusted callables run in-process. Use ToolSurface or an OS/container boundary for untrusted tools or code.
- **Real brokerage orders**: the current repository has no live order-placement adapter. `place_real_orders=false` is therefore reported as `not_applicable_no_write_surface`; any future adapter must add an authoritative `EFFECT_REAL_ORDER` fence before exposure.
- **Agent-memory writes**: the current `AgentMemory` API is read-only. `persist_agent_memory=false` is reported as `not_applicable_no_write_surface`; any future write API must add an authoritative `EFFECT_AGENT_MEMORY` fence.
- **Paper-ledger persistence during a sandbox run**: all `PortfolioRepository` mutations are refused, including paper-account writes. Simulated actions stay in the sandbox result and receipt rather than a shared persistent ledger.
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

Issue #1115 example `EVOLUTION_AUTO_PROMOTE_SKILLS` is **not** an environment key and is not an alias of this receipt field. Auto-promote stays hard off in the [prediction verification safe rollout](prediction-verification-rollout_EN.md). The #1093 dry-run CLI embeds this receipt in a sidecar; `approve` cannot set `auto_promote` or `auto_promote_to_production`. See the [agent promotion checklist](agent-promotion.md).

Caller-supplied `risk_boundary` or `production_authority_scope` values cannot
broaden these defaults. Conflicting values are rejected rather than copied into
a receipt that could misleadingly imply production authority.

## Safety fences (production write paths)

| Path | Fence |
| --- | --- |
| `DecisionSignalService.create_signal*` | `EFFECT_DECISION_SIGNAL` |
| `DecisionSignalMemoryFlagRepository.upsert` | `EFFECT_DECISION_MEMORY` |
| `DatabaseManager.save_analysis_history` (all callers) | `EFFECT_ANALYSIS_HISTORY` |
| `NotificationService.send_with_results` | `EFFECT_NOTIFICATION` |
| All `PortfolioRepository` mutators (accounts, events, FX, caches, snapshots) | `EFFECT_PRODUCTION_PORTFOLIO` |

Fences raise `SandboxExternalEffectBlocked` only while a `SandboxContext` is active via `active_sandbox_context`. Outside sandbox, production paths are unchanged. Pipeline history stage logs `sandbox_analysis_history_write_blocked` when the authoritative fence refuses a write (does not mislabel it as generic storage failure). Failed runs project `completed=false` into the production-compatible trajectory schema.

## Related

- Issue #247 (parent safe sandbox)
- Issue #202 (research sandbox)
- Issue #442 (sandbox enhancement / multi-scenario)
- Issue #1093 dry-run promotion CLI: `docs/agent-promotion.md` (sidecar review only; `auto_promote=false`)
- `docs/agent-observability.md` (production L0 events; sandbox traces stay field-comparable)
- Backtest UI manual: `docs/ui-manual/09-backtest.md`
