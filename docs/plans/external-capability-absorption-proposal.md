# StockPulse External Capability Absorption & Integration Proposal

**Version**: 1.0  
**Date**: 2026-08-08  
**Status**: Proposal / RFC  
**Author**: Maintainer proposal for community discussion

## 1. Goal

Systematically absorb useful capabilities from major open-source financial AI projects (FinRL / FinRL-X, TradingAgents-style multi-agent systems, Qlib, OpenBB, FinGPT, etc.) into the StockPulse ecosystem **without compromising** StockPulse’s core identity:

- Local-first investment research workbench
- Evidence-aware, stratified reporting (facts / gaps / inference / risks / disclaimer)
- Auditable risk controls, Human-in-the-Loop, and ToolSurface security
- Trusted, process-equivalent plugins only (no marketplace, no sandbox illusion)

The result should be a clean **research → signal → external strategy validation → feedback** loop.

## 2. Design Principles (Non-Negotiable)

1. **Role clarity**  
   StockPulse remains a **research and signal workbench**. It is not an automated execution engine and must not embed heavy RL training or full quant pipelines in-process.

2. **Process boundary**  
   Heavy compute (RL training, large-scale factor mining, model fitting) lives in independent processes/services. StockPulse only **calls, aggregates, reports, and notifies** via the plugin surface.

3. **Trust model**  
   All plugins are trusted in-process Python. Setting `PLUGINS_DIR` is an explicit operator trust decision. No remote marketplace, no automatic dependency installation, no untrusted packages.

4. **Use only the frozen V1 extension points**  
   - `data_provider`  
   - `analysis_strategy`  
   - `agent_tool`  
   - `notification_channel`  
   - `report_template`  
   - `event_hook`  

   New points require a new ADR and surface major bump.

5. **Honesty first**  
   Every external signal that enters a report must land in the correct stratum, carry source + model identity + timestamp, and degrade gracefully on low confidence or data gaps.

6. **Default-off & reversible**  
   Every external capability is disabled by default and can be toggled via plugin lifecycle or configuration.

## 3. Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     StockPulse Core                          │
│  Data layer + LLM Agents + Strategy synthesis + Reports +   │
│  Notifications + HITL + Audit                                │
└───────────────┬───────────────────────────────┬─────────────┘
                │ Plugin boundary (6 points)     │
    ┌───────────▼──────────┐         ┌──────────▼──────────┐
    │  Lightweight (in-proc)│         │  Heavy (side services)│
    │  • New data sources   │         │  • FinRL train/infer │
    │  • Skills / Personas  │◄───────►│  • Qlib factors/models│
    │  • Agent Tools        │  HTTP / │  • OpenBB queries    │
    │  • Report templates   │  files  │  • FinGPT specialised│
    │  • Event-hook export  │         │    inference         │
    └──────────────────────┘         └─────────────────────┘
```

**Primary signal flow**

1. StockPulse daily / on-demand analysis produces stratified reports + DecisionSignals.
2. An `event_hook` exports high-quality signals / features for external training.
3. FinRL / Qlib (or similar) train independently.
4. Trained policies are exposed back to StockPulse via `agent_tool`.
5. Results enter StrategyEngine synthesis and reports; high-risk items can trigger HITL.

## 4. Capability Absorption Matrix

| External Project       | Absorbable Capabilities                          | Recommended Landing                  | Plugin Point(s)              | Priority |
|------------------------|--------------------------------------------------|--------------------------------------|------------------------------|----------|
| **FinRL / FinRL-X**    | RL policy learning, backtest envs, multi-algo    | Independent inference service + tool | `agent_tool` + `event_hook`  | P0       |
| **TradingAgents-style**| Multi-role debate, risk veto, committee structure| Personas + Skills + optional aggregator | `analysis_strategy` + `agent_tool` | P0 |
| **Qlib**               | Factor engineering, model predictions, quant pipeline | Independent service + query tool | `agent_tool` (+ optional `data_provider`) | P1 |
| **OpenBB**             | Rich financial data & research interfaces        | Data-source adapter                  | `data_provider`              | P1       |
| **FinGPT**             | Domain LLM / sentiment & event extraction        | LLM backend or specialised tool      | Config + `agent_tool`        | P1       |
| Others                 | Sentiment, alternative data, execution sim, etc. | Tool-ise as needed                   | `agent_tool` / `data_provider` | P2     |

## 5. Phased Implementation Roadmap

### Phase 0 – Preparation (1–2 weeks)

- Document safe `PLUGINS_DIR` usage and review checklist.
- Agree on inter-process communication convention (preferred: internal HTTP + JSON, or shared export directory).
- Freeze a **unified external signal contract** (see §6).
- Publish two official example plugin skeletons:
  - `example-rl-signal-tool`
  - `example-external-data-provider`

### Phase 1 – Lightweight Absorption (2–4 weeks) — Quick Wins

**Goal**: Dramatically improve analytical perspectives with zero heavy dependencies.

1. **TradingAgents-style roles**  
   - Author a set of YAML `analysis_strategy` / Personas (Fundamental, Sentiment, Technical, Bull/Bear Researcher, Risk Manager).  
   - Enable Multi-Agent + investment-committee mode (already supported).  
   - Optional: one `agent_tool` for committee vote aggregation.

2. **FinGPT**  
   - Configure FinGPT-compatible models as normal LLM connections (OpenAI-compatible or Ollama).  
   - Optional specialised `agent_tool` e.g. `fin_sentiment_extract(text)`.

3. **Event-hook export**  
   - Implement `analysis.completed` / `analysis.failed` hooks that write standardised DecisionSignals + key metrics to a well-known directory for FinRL/Qlib consumption.

### Phase 2 – Core External Strategy Integration (4–8 weeks)

**Goal**: Bring real FinRL / Qlib **inference results** into the StockPulse decision chain.

1. **FinRL inference service** (separate process)  
   - Minimal API: `POST /predict` → `{stock_code, action, confidence, model_id, as_of, ...}`  
   - StockPulse side: `agent_tool` named `get_rl_policy_signal(stock_code, model_id?)`  
   - Must pass ToolSurface (capabilities, schema, outbound policy, audit).

2. **Qlib factor / prediction service**  
   - Similar tool: `get_qlib_alpha(stock_code, factor_set)`.

3. **Synthesis integration**  
   - Treat external signals as a special class of Skill opinion inside StrategyEngine / DecisionAgent.  
   - Force them into the **inference** stratum; always annotate source + model version.

4. **Reporting & notifications**  
   - New `report_template` block for “External Strategy Signals”.  
   - High-risk external signals can flow through existing HITL approvals.

### Phase 3 – Data-layer Enhancement (parallel, 2–4 weeks)

1. OpenBB (or other) `data_provider` plugins declaring supported markets and capabilities (`daily_data`, `realtime_quote`, etc.).  
2. Strict adherence to existing routing, cache, circuit-breaker and outbound HTTP policy.  
3. Optional read-only wrapping of FinRL-Meta environment data.

### Phase 4 – Closed Loop & Governance (ongoing)

- External signals participate in back-testing and skill-opinion-outcome evaluation.
- Plugin lifecycle monitoring (enable / disable / reload).
- Periodic audit of model drift and signal efficacy.
- Official documentation and example plugins land in-repo.

## 6. Unified External Signal Contract (Proposed Mandatory Shape)

Every external strategy tool **must** return (at minimum):

```json
{
  "source": "finrl|qlib|custom",
  "model_id": "ppo_dow30_v2026q2",
  "stock_code": "AAPL",
  "as_of": "2026-08-07T15:30:00+08:00",
  "signal": "buy|hold|sell",
  "confidence": 0.0,
  "horizon_days": 5,
  "raw_action": null,
  "features_used": ["close", "rsi", "macd"],
  "disclaimer": "Model output only. Not investment advice.",
  "evidence_ref": "optional internal id"
}
```

Reporting rules:

- Always land in the **inference** stratum.
- Always display `source + model_id + as_of`.
- Automatically degrade to “observe / watch” on low confidence or missing data.

## 7. Concrete Plugin Sketches

### 7.1 RL Policy Tool (`agent_tool`)

- Manifest declares id, descriptive permissions, `minAppVersion`.
- `onload` registers a `ToolDefinition`:
  - name: `get_rl_policy_signal`
  - required `stock_code`, optional `model_id`
  - handler calls the local/remote FinRL inference service (timeout + outbound policy)
  - explicit `ToolPolicy` capabilities

### 7.2 Analysis-completed Export Hook (`event_hook`)

- Listens to `analysis.completed`.
- Writes standardised signals under e.g. `~/.stockpulse/exports/signals/YYYY-MM-DD/`.
- Failures are isolated; they never abort the main analysis pipeline.

### 7.3 OpenBB Data Provider (`data_provider`)

- Implements the `DataProvider` interface.
- Declares markets + capabilities.
- Factory returns an instance; `DataFetcherManager` remains the sole routing authority.

### 7.4 Committee-style Strategies (`analysis_strategy`)

- Prefer pure YAML Skills (lightest path).
- Escalate to a Python plugin only when complex registration logic is required.

## 8. Security & Operational Requirements

- Every external plugin undergoes code review + dependency review.
- Production: absolute `PLUGINS_DIR`, preferably read-only for the process user.
- All outbound HTTP must obey StockPulse outbound policy (allow-list, timeouts, no credential leakage).
- High-impact external signals default into HITL.
- Audit log must record: plugin id, tool name, model version, result summary.
- Forbidden inside plugins: arbitrary code execution, core config mutation, ToolSurface bypass, silent overwrite of built-in strategies.

## 9. Success Metrics

| Metric | Target |
|--------|--------|
| External signals appear in reports with correct stratification | 100% |
| Plugin load/unload never compromises core availability | Fault isolation |
| Time from “have a FinRL model” to “daily signal visible in report” | ≤ 1 day of operator configuration |
| External signals evaluable in back-test / outcome tracking | Supported |
| Time to onboard a new similar external strategy (with templates) | ≤ 1 week |

**Explicit non-goals**

- Running full RL training inside the StockPulse process
- Automatic live order execution
- Remote plugin marketplace
- Embedding full Qlib / FinRL UIs

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| External model over-fitting / silent decay | Mandatory source annotation + confidence + periodic outcome evaluation |
| Plugin introduces security vulnerability | Strict review + least privilege + outbound policy |
| Dependency hell | Keep heavy capabilities completely external; StockPulse only ships thin clients |
| Conflicting signals | Existing StrategyEngine conflict detection & synthesis |
| Rising maintenance cost | Core maintains only the contract + official examples; community plugins are best-effort |

## 11. Immediate Next Steps (Actionable)

1. **This week**: Finish Phase 0 + two example plugin skeletons + freeze the signal contract.  
2. **Next week**: Ship TradingAgents-style Persona YAMLs + Event-hook export.  
3. **Within a month**: Land the first real `get_rl_policy_signal` tool (even with a mock backend).  
4. **Ongoing**: Extend the same pattern to Qlib / OpenBB.

## 12. References (StockPulse)

- Plugin Extension Contract: `docs/plugin-extension-contract.md`
- Analysis Strategy Plugin Authoring: `docs/analysis-strategy-plugin-authoring.md`
- Data Provider Plugin Authoring: `docs/data-provider-plugin-authoring.md`
- Security Baseline & ToolSurface: `docs/security-baseline.md`
- Human Approvals (HITL): `docs/human-approvals_EN.md`
- Report Strata Contract: `docs/report-strata-contract_EN.md`

---

*This proposal is intentionally aligned with the frozen V1 plugin surface and the existing security / honesty philosophy of StockPulse. Feedback, alternative designs, and concrete plugin PRs are welcome.*
