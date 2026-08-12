# Competitive Landscape: Local-First Finance AI Peers

- Status: `Living`
- As of: **2026-08-12** (star counts and public peer claims snapshot via GitHub API / public READMEs)
- Scope: honest external positioning vs peers named in [#799](https://github.com/SiinXu/stock-pulse-ai/issues/799) / [#1063](https://github.com/SiinXu/stock-pulse-ai/issues/1063)
- Chinese: [competitive-landscape_CN.md](competitive-landscape_CN.md)

This note helps external users choose deliberately, helps contributors prioritize real gaps, and forbids marketing inflation. It is **not** a continuous competitor-monitoring process and does **not** invent features to “beat” peers.

**Language rule:** prefer *investment research workbench* over tip-service language. Outputs are research-only, not regulated advice.

Related product narrative already on the homepage: [README · Why StockPulse](../README.md#why-stockpulse) (shipped highlights and explicit non-claims). Upstream fork policy: [Foundation Pipeline And Product Layer](foundation-product-architecture.md), [Upstream Parity Checker](upstream-parity.md). Claim hygiene trackers: [#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008), [#1056](https://github.com/SiinXu/stock-pulse-ai/issues/1056).

---

## How To Read This Document

| Label | Meaning |
| --- | --- |
| **Shipped** | Reachable on StockPulse `main` with docs or UI entry points, not Playground-only / wire-only |
| **Default-off** | Shipped but requires explicit config or opt-in; do not market as always-on |
| **Partial** | Backend or partial UI exists; not fully honest as a complete product surface ([#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008), [#1056](https://github.com/SiinXu/stock-pulse-ai/issues/1056)) |
| **Planned / gap** | Tracked by issue; not a current differentiator claim |
| **Peer strength** | Something a peer does well; StockPulse may deliberately not copy it |

Star counts below are **approximate popularity signals only**, as of 2026-08-12. They are not quality rankings.

---

## StockPulse Positioning (One Paragraph)

StockPulse is a **local-first investment research workbench** for multi-market equities (A-share / HK / US / JP / KR / TW and related instruments): multi-provider market data → technical and news context → LLM / multi-agent analysis → **stratified** reports → optional notifications. It is an independently maintained fork of [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) (upstream portions **MIT**; StockPulse additions **AGPL-3.0**). It optimizes for **auditable risk controls**, **deny-by-default Agent tools**, **honest report structure**, and **operator-owned** deployment (CLI, Docker, Web, Desktop, GitHub Actions)—not multi-tenant SaaS and not a black-box stock tip service.

---

## Peer Snapshot (Named In #799)

| Peer | Approx. stars (2026-08-12) | Public home | Core strength (peer) | StockPulse relative note |
| --- | ---: | --- | --- | --- |
| **Upstream `daily_stock_analysis`** | ~62.5k | [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) | Zero-cost GitHub Actions daily push; huge community install path via fork | Shared foundation lineage; StockPulse differentiates on governance, strata, ToolSurface, plugins—see [vs upstream](#vs-upstream-daily_stock_analysis) |
| **go-stock** | ~7.2k | [ArvinLovegood/go-stock](https://github.com/ArvinLovegood/go-stock) | Mature Chinese **desktop-first** packaging; local data retention; multi-LLM; fast Windows-oriented releases | StockPulse has Web + Electron, but **desktop first-run / one-click install still trails** ([#798](https://github.com/SiinXu/stock-pulse-ai/issues/798)) |
| **FinRobot (+ Desktop)** | ~7.8k (platform) | [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot); [Desktop release](https://github.com/AI4Finance-Foundation/FinRobot/releases/tag/desktop-v0.1.0) | Equity-research workflow, multi-agent research pipelines, **code-calculated valuation** + LLM narration, IC-style memos (Desktop v0.1.0 macOS aarch64 as of peer README) | StockPulse valuation / memo depth is thinner; committee and valuation paths exist but are **default-off / scoped**—do not claim FinRobot-depth research memos |
| **TradingAgents (and CN forks)** | ~97.7k core; large CN ecosystem forks | [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | Multi-agent debate, role specialization, trading-framework narrative | StockPulse has optional committee / personas / critic (**default-off**); process visualization and full debate UX still a product gap relative to specialist frameworks ([#545](https://github.com/SiinXu/stock-pulse-ai/issues/545) closed for V1 mode; visualization still limited) |
| **StockAI / OpenCandle-class** | Fragmented; e.g. [Kahtaf/OpenCandle](https://github.com/Kahtaf/OpenCandle) ~10s of stars | Multiple small repos under similar names | Clean local / terminal research UX, visual or multi-analyst focus depending on project | Treat as **category**, not a single product; StockPulse should not over-claim “share cards” or terminal polish without shipped UI |

> **Argus-style** in #799 means *role-debate / committee* multi-agent systems in the same design family as TradingAgents, not a single canonical repo. Claims about that family refer to process UX (roles, debate, veto), not to one named product.

---

## Dimension Matrix

Statuses for StockPulse are honest labels as of 2026-08-12. Peer cells summarize public positioning, not a full audit of peer codebases.

| Dimension | StockPulse | Upstream DSA | go-stock | FinRobot Desktop | TradingAgents-class |
| --- | --- | --- | --- | --- | --- |
| Primary form factor | CLI + FastAPI Web + Electron Desktop | CLI + Actions + WebUI lineage | Desktop-first (Wails) | Native desktop research cockpit (Tauri stack per peer README) | Framework / library / research pipeline |
| Local-first operator control | **Shipped** (local bind, local models, optional local-only mode) | Strong Actions + local options | Strong desktop local retention | Desktop local app | Depends on deployment |
| Multi-market data + fallback | **Shipped** (multi-provider, health/fallback docs) | Strong shared lineage | A/HK/US local focus | Research data providers (US-heavy in Desktop narrative) | Varies by fork |
| Report trust UX (facts / gaps / inference / risks / disclaimer) | **Shipped** stratified reports | Decision dashboard lineage | AI analysis output | Traceable multi-chapter research / IC memos (peer claim) | Agent debate transcripts more than stratified retail reports |
| Deny-by-default Agent tools (ToolSurface) | **Shipped** | Not a StockPulse-style governance highlight | Multi-LLM tools; different threat model | Multi-agent platform; different product boundary | Tool-using agents; framework-specific |
| HITL high-risk gate | **Shipped, default-off** | N/A as product highlight | N/A as product highlight | Research workflow, not the same approval product | Risk agents / veto patterns (framework) |
| Personal investment framework inject | **Shipped** (versioned API + report alignment slot; deeper editor **planned**) | N/A | N/A | Valuation / IC narrative depth stronger | Role prompts, not the same product object |
| Trusted plugin contract (six points) | **Shipped** (not a marketplace) | Limited / different model | App-centric extension | Platform extensibility | Code-level composition |
| Local Model Packs (versioned GGUF) | **Shipped** | Local models possible; pack product is StockPulse | Ollama / LMStudio / etc. | Local/desktop stack per release | Bring-your-own LLM |
| Zero-config / beginner first success | **Shipped** (local Ollama detect + sample path) | Excellent Actions “fork = install” story | Strong installer / green EXE story | DMG first-run (macOS aarch64) | Dev-oriented |
| Desktop packaging maturity | **Partial / gap** vs go-stock / FinRobot Desktop ([#798](https://github.com/SiinXu/stock-pulse-ai/issues/798)) | Secondary | **Peer strength** | **Peer strength** (scoped OS) | N/A |
| Multi-agent debate UX visualization | **Partial** (committee mode default-off; limited process theater) | Optional multi-agent paths in lineage | Lighter AI assist | Strong research pipeline story | **Peer strength** |
| Community / stars | Very small | **Peer strength** | Large CN desktop community | Established AI4Finance brand | Very large |

---

## StockPulse Differentiation (What To Emphasize)

Only claim what is **Shipped** or clearly **Default-off**. Link docs; do not paste marketing adjectives without a product surface.

### 1. Research workbench, not tip oracle — **Shipped**

- Homepage and docs position the product as a workbench with **explicit non-claims** (not multi-tenant SaaS, not regulated advice, free data stability not guaranteed).
- Report strata separate **facts / gaps / inference / risks / framework alignment / disclaimer** so users can audit trust boundaries.
- Docs: [report strata contract](report-strata-contract_EN.md), [README Why StockPulse](../README.md#why-stockpulse).

### 2. Agent and control-plane governance — **Shipped** (often default-off)

| Capability | Status | Docs / issue |
| --- | --- | --- |
| Strict Agent **ToolSurface** (deny-by-default, grants, stock scope, outbound URL policy) | Shipped | [security-baseline](security-baseline.md) |
| HITL approvals for high-risk control paths | Shipped, default-off | [human-approvals](human-approvals_EN.md) |
| Durable security audit on privileged paths | Shipped | [security-audit](security-audit.md) |
| Agent Soul + optional Personas / committee | Shipped, committee default-off | [agent-soul](agent-soul.md), [investment-committee-mode](investment-committee-mode_EN.md) (#545) |
| Bounded Critic before multi-agent decisions | Shipped, default-off | CHANGELOG / Agent docs |

### 3. Extension without pretending to be a plugin store — **Shipped**

- Trusted process plugins (strategies, templates, notification channels, event hooks, data providers).
- Explicit trust model: plugins run with process privileges—**never** load untrusted packages as “apps”.
- Docs: [plugin-extension-contract](plugin-extension-contract.md).

### 4. Local model productization — **Shipped**

- Ollama catalog path plus **versioned Model Pack** GGUF import (Web + Desktop) with integrity checks.
- Docs: [model-packs](model-packs.md), [local-model-catalog](local-model-catalog.md).

### 5. Config and claim hygiene — **Shipped direction + ongoing audit**

- Registry-backed Settings, presets/profiles, zero-config first success paths.
- Active audits against over-claiming merged-but-unreachable surfaces ([#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008), [#1056](https://github.com/SiinXu/stock-pulse-ai/issues/1056)).
- Docs: [zero-config first success](zero-config-first-run_EN.md), [config presets](config-presets-profiles_EN.md).

### 6. Dual license and independent maintenance — **Shipped fact**

- Upstream-originated portions remain **MIT**; StockPulse additions and substantial modifications are **AGPL-3.0**.
- Manual upstream porting with parity tooling—not silent rebrand of upstream.
- Docs: [LICENSE](../LICENSE), [upstream-parity](upstream-parity.md), [foundation-product-architecture](foundation-product-architecture.md).

---

## Vs Upstream `daily_stock_analysis`

This section must **not contradict** the closed differentiator issue [#624](https://github.com/SiinXu/stock-pulse-ai/issues/624): the homepage already answers “why not only upstream?” in plain language. This living note goes deeper for contributors and evaluators.

| Topic | Upstream strength | StockPulse choice |
| --- | --- | --- |
| Adoption path | Fork + GitHub Actions is the viral install | Keep Actions support; also invest in workbench UX, governance, desktop |
| Narrative | Multi-market daily analysis + push | Same foundation lineage + **research workbench / trust UX** emphasis |
| License | MIT | MIT (original) + **AGPL-3.0** (StockPulse additions) |
| Product governance | Community velocity | ToolSurface, HITL, audit, plugin trust model, report strata |
| Sync model | Canonical upstream | **Manual** ports + weekly parity report ([upstream-parity](upstream-parity.md)) |

**Do not claim:** “StockPulse is a strict superset of upstream,” “always better reports,” or “same install friction as Actions-only users.” Star and community size remain upstream’s advantage.

Tracked historical differentiator work: [#624](https://github.com/SiinXu/stock-pulse-ai/issues/624) (closed when homepage differentiators landed).

---

## Honest Gaps (Prioritize These; Do Not Market Around Them)

| Gap | Why it hurts adoption | Tracking |
| --- | --- | --- |
| Desktop first-run / one-click local install vs go-stock & FinRobot Desktop | Many CN users evaluate desktop EXE/DMG before Web | [#798](https://github.com/SiinXu/stock-pulse-ai/issues/798) |
| Research-memo / valuation synthesis depth vs FinRobot Desktop | Equity-research users compare IC memo depth and numeric provenance | Valuation docs are scoped; avoid over-claim; see [valuation-models](valuation-models_EN.md) |
| Multi-agent process visualization vs TradingAgents-class | Users equate “multi-agent” with live debate UX | Committee mode shipped default-off (#545); visualization still limited |
| Community gravity vs upstream | Users default to the 60k+ star repo | Narrative + claim hygiene (#799, #1063); not a code race |
| Reachability honesty after feature trains | README/feature tables can drift ahead of user-reachable UI | [#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008), [#1056](https://github.com/SiinXu/stock-pulse-ai/issues/1056) |

Related onboarding / packaging issues also named from the landscape survey: [#589](https://github.com/SiinXu/stock-pulse-ai/issues/589) (agent-guided onboarding, closed), [#796](https://github.com/SiinXu/stock-pulse-ai/issues/796) (zero-config first success, closed).

---

## What StockPulse Explicitly Does *Not* Claim

Aligned with README non-claims and security docs:

1. **Not** multi-tenant SaaS / post-login RBAC workspace isolation ([security-baseline AUTH-05](security-baseline.md), [#230](https://github.com/SiinXu/stock-pulse-ai/issues/230)).
2. **Plugins are not a sandboxed app store**—they are trusted process code.
3. **Free market data** can run without tokens; **stability is not guaranteed**.
4. **Research only**—not investment advice and not regulated advisory.
5. **Default-off** agent/governance features are not “always-on multi-agent trading.”
6. **Stars / “best AI stock picker”** rankings are not product claims.

---

## Entry Points For Readers

| Audience | Start here |
| --- | --- |
| New user choosing a project | [README · Why StockPulse](../README.md#why-stockpulse) → this page → [FAQ](FAQ_EN.md) |
| Contributor prioritizing gaps | Gap table above + linked issues |
| Operator deploying safely | [security-baseline](security-baseline.md), [DEPLOY_EN](DEPLOY_EN.md) |
| Someone comparing only to upstream | [Vs upstream](#vs-upstream-daily_stock_analysis) + [upstream-parity](upstream-parity.md) |

Documentation index: [INDEX_EN.md](INDEX_EN.md).

---

## Maintenance Rules

1. Update **As of** date when refreshing star counts or peer claims.
2. Prefer linking **issues and docs** over vague adjectives.
3. When a gap closes, move the row from **Honest Gaps** to **Differentiation** only if the surface is user-reachable (not wire-only).
4. Keep EN/CN parity for material claim changes.
5. Root README stays **homepage-level**; deep peer tables live here (AGENTS.md README focus rule). INDEX/FAQ link here instead of expanding the homepage feature matrix.
6. Out of scope: marketing website, continuous competitive monitoring bots, inventing features solely to win a comparison cell.

---

## References

- Issues: [#799](https://github.com/SiinXu/stock-pulse-ai/issues/799), [#1063](https://github.com/SiinXu/stock-pulse-ai/issues/1063), [#624](https://github.com/SiinXu/stock-pulse-ai/issues/624), [#798](https://github.com/SiinXu/stock-pulse-ai/issues/798), [#545](https://github.com/SiinXu/stock-pulse-ai/issues/545), [#796](https://github.com/SiinXu/stock-pulse-ai/issues/796), [#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008), [#1056](https://github.com/SiinXu/stock-pulse-ai/issues/1056)
- Peer repos (as of 2026-08-12): [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis), [go-stock](https://github.com/ArvinLovegood/go-stock), [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot), [TradingAgents](https://github.com/TauricResearch/TradingAgents), [OpenCandle (example of class)](https://github.com/Kahtaf/OpenCandle)
