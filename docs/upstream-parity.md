# Upstream Parity Checker

- Status: `Living`
- Last verified: 2026-08-12
- Scope: drift reporting for `ZhuLinsen/daily_stock_analysis`, whitelist semantics, triage, and maintainer cadence

StockPulse ports upstream foundation fixes **manually**. There is no automatic
merge or sync from upstream. This document describes the weekly parity checker
that reports drift so maintainers can triage ports deliberately.

Chinese version: [upstream-parity_CN.md](upstream-parity_CN.md).

Related policy: [Foundation Pipeline And Product Layer](foundation-product-architecture.md#upstream-porting-policy).
Cadence owner issue: [#1061](https://github.com/SiinXu/stock-pulse-ai/issues/1061).
Machine tracking issue: [#1002](https://github.com/SiinXu/stock-pulse-ai/issues/1002).

## What The Checker Does

Script: `scripts/check_upstream_parity.py`  
Inventory (path presence + suggested actions): `scripts/inventory_upstream_drift.py`
Whitelist: `scripts/upstream_parity_whitelist.json`  
Workflow: `.github/workflows/upstream-parity.yml`

On each weekly (or manual) run the workflow:

1. Fetches `https://github.com/ZhuLinsen/daily_stock_analysis.git` as `upstream`.
2. Computes the merge-base (fork point) between StockPulse `main` and `upstream/main`.
3. Lists **upstream-only** commits since that fork point.
4. Classifies each commit by changed paths against the whitelist.
5. Cross-references local `Ported-from:` trailers so already-ported commits are marked.
6. Uploads a Markdown report artifact and **updates one** tracking issue in place.

After the machine report refreshes, maintainers should run the **inventory**
script to turn Attention commits into an actionable gap list (local path
presence, suggested Port / Design / Record-trailer / Skip-docs actions). Path
presence is a heuristic, not semantic equivalence.

The offline CI gate does **not** fetch upstream. Use `--self-test` for fixture
repos, or run the scripts locally with remotes when you need a live report.

## Ported-from Trailer Convention

When a StockPulse commit ports behavior from upstream, record provenance:

```text
Ported-from: ZhuLinsen/daily_stock_analysis@<sha>
```

- Use the upstream commit SHA (7-40 hex characters).
- Multiple trailers are allowed when one StockPulse change combines several upstream commits.
- The checker matches trailer SHAs as prefixes against full upstream SHAs.

## Whitelist Semantics

The whitelist lists **deliberately diverged path prefixes**. Classification:

| Commit paths | Ported-from match? | Status |
| --- | --- | --- |
| Any path outside the whitelist (shared foundation / shared product surface) | No | **Attention** — review for a deliberate port |
| Any shared path | Yes | **Already ported** |
| All paths match whitelist prefixes only | No | **Informational** — expected product/governance divergence |
| All paths whitelist-only | Yes | **Already ported** (still recorded) |

Rules of thumb:

- Prefer a **small** whitelist. Only add prefixes StockPulse will not mirror on purpose (desktop packaging, AI governance assets, parity tooling itself, etc.).
- Do **not** whitelist shared foundation paths such as `src/data_provider/`, `src/core/`, or shared analysis services merely to silence the report.
- Expanding the whitelist is a product decision: update the JSON, this document (EN + CN), and the changelog.

Empty path lists (for example some merge commits) are treated as informational.

## Triage Flow

1. Open the tracking issue labeled `upstream-parity` (title: `Upstream parity drift report`, currently #1002), or download the workflow artifact `upstream-parity-report-*.md`.
2. Generate the maintainer inventory (path presence + suggested actions):

```bash
python scripts/inventory_upstream_drift.py \
  --local-ref origin/main \
  --upstream-ref upstream/main \
  --output /tmp/upstream-drift-inventory.md
```

3. Work **Attention** commits first. For each candidate, classify per #1061:
   - **Port now** — foundation fix; small, test-backed PR with `Ported-from: ZhuLinsen/daily_stock_analysis@<sha>`
   - **DESIGN-NEEDED** — entangled with local Agent/strategy/report contracts; one design issue before code (example: #805 multi-strategy cluster)
   - **Record trailer** — fork already absorbed the intent under a different layout; spot-check, then add `Ported-from` so #1002 stops listing it as Attention
   - **Skip / whitelist** — product-only, docs/changelog-only, or governance paths StockPulse will not mirror; expand whitelist only deliberately
4. **Never half-port** entangled clusters across orchestrator/pipeline/report schema without a design note.
5. Open or update **child issues** for concrete residual gaps. Do not leave actionable gaps only inside the weekly report body.
6. Leave **Informational** commits unported unless paths later become shared.
7. Re-run locally after ports:

```bash
python scripts/check_upstream_parity.py --self-test
python scripts/inventory_upstream_drift.py --self-test
python scripts/check_upstream_parity.py --fetch \
  --local-ref origin/main \
  --upstream-ref upstream/main \
  --output /tmp/upstream-parity-report.md
python scripts/inventory_upstream_drift.py \
  --local-ref origin/main \
  --upstream-ref upstream/main \
  --output /tmp/upstream-drift-inventory.md
```

8. Do not open extra **tracking** issues for the machine report. The workflow updates the single open issue with label `upstream-parity` and HTML marker `<!-- upstream-parity-tracking-issue -->`. Duplicates are closed automatically. Child port/design issues are expected and should reference #1002 / #1061.

## Governance Cadence (Who / When)

| Cadence | Owner | Action |
| --- | --- | --- |
| Weekly Mon 04:00 UTC (or `workflow_dispatch`) | GitHub Actions `upstream-parity` | Refresh #1002 commit classification + artifact |
| Within a few days of each refresh | Maintainers / #1061 cadence owners | Run `inventory_upstream_drift.py`, triage Attention, open/update child issues |
| After each port PR merges | Port author | Confirm `Ported-from` trailer; re-run inventory so Attention shrinks |
| Whitelist changes | Maintainer product decision | Update JSON + this doc (EN/CN) + changelog |

**Consumers of the inventory:** #1002 triage comments, #1061 checklist owners, and authors planning the next port wave.

## Local Commands

```bash
python scripts/check_upstream_parity.py --self-test
python scripts/inventory_upstream_drift.py --self-test
python -m pytest tests/scripts/test_upstream_parity.py tests/scripts/test_inventory_upstream_drift.py -q
python scripts/check_upstream_parity.py --fetch \
  --local-ref origin/main \
  --upstream-ref upstream/main
python scripts/inventory_upstream_drift.py --fetch \
  --local-ref origin/main \
  --upstream-ref upstream/main \
  --output /tmp/upstream-drift-inventory.md
```

## Workflow Notes

- Schedule: Mondays 04:00 UTC, plus `workflow_dispatch`.
- Actions are SHA-pinned (enforced by `scripts/check_workflow_supply_chain.py`).
- Permissions: `contents: read`, `issues: write` only on the parity job.
- The workflow never pushes code, opens PRs, or merges upstream.

## Keeping This Current

Update this document and `upstream-parity_CN.md` together when whitelist
semantics, trailer format, triage flow, or cadence change. Update
`foundation-product-architecture.md` when the porting policy itself changes.
