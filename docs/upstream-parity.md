# Upstream Parity Checker

- Status: `Living`
- Last verified: 2026-08-05
- Scope: drift reporting for `ZhuLinsen/daily_stock_analysis`, whitelist semantics, and triage

StockPulse ports upstream foundation fixes **manually**. There is no automatic
merge or sync from upstream. This document describes the weekly parity checker
that reports drift so maintainers can triage ports deliberately.

Chinese version: [upstream-parity_CN.md](upstream-parity_CN.md).

Related policy: [Foundation Pipeline And Product Layer](foundation-product-architecture.md#upstream-porting-policy).

## What The Checker Does

Script: `scripts/check_upstream_parity.py`  
Whitelist: `scripts/upstream_parity_whitelist.json`  
Workflow: `.github/workflows/upstream-parity.yml`

On each weekly (or manual) run the workflow:

1. Fetches `https://github.com/ZhuLinsen/daily_stock_analysis.git` as `upstream`.
2. Computes the merge-base (fork point) between StockPulse `main` and `upstream/main`.
3. Lists **upstream-only** commits since that fork point.
4. Classifies each commit by changed paths against the whitelist.
5. Cross-references local `Ported-from:` trailers so already-ported commits are marked.
6. Uploads a Markdown report artifact and **updates one** tracking issue in place.

The offline CI gate does **not** fetch upstream. Use `--self-test` for fixture
repos, or run the script locally with remotes when you need a live report.

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
- Do **not** whitelist shared foundation paths such as `data_provider/`, `src/core/`, or shared analysis services merely to silence the report.
- Expanding the whitelist is a product decision: update the JSON, this document (EN + CN), and the changelog.

Empty path lists (for example some merge commits) are treated as informational.

## Triage Flow

1. Open the tracking issue labeled `upstream-parity` (title: `Upstream parity drift report`), or download the workflow artifact `upstream-parity-report-*.md`.
2. Work **Attention** commits first. For each candidate:
   - Confirm it is a foundation-compatible fix (see foundation porting policy).
   - Port in a focused StockPulse PR; adapt to current contracts and licenses.
   - Include `Ported-from: ZhuLinsen/daily_stock_analysis@<sha>` on the commit.
3. Leave **Informational** commits unported unless paths later become shared.
4. Re-run locally after ports:

```bash
python scripts/check_upstream_parity.py --self-test
python scripts/check_upstream_parity.py --fetch \
  --local-ref origin/main \
  --upstream-ref upstream/main \
  --output /tmp/upstream-parity-report.md
```

5. Do not open extra tracking issues. The workflow updates the single open issue with label `upstream-parity` and HTML marker `<!-- upstream-parity-tracking-issue -->`. Duplicates are closed automatically.

## Local Commands

```bash
python scripts/check_upstream_parity.py --self-test
python -m pytest tests/scripts/test_upstream_parity.py -q
python scripts/check_upstream_parity.py --fetch \
  --local-ref origin/main \
  --upstream-ref upstream/main
```

## Workflow Notes

- Schedule: Mondays 04:00 UTC, plus `workflow_dispatch`.
- Actions are SHA-pinned (enforced by `scripts/check_workflow_supply_chain.py`).
- Permissions: `contents: read`, `issues: write` only on the parity job.
- The workflow never pushes code, opens PRs, or merges upstream.

## Keeping This Current

Update this document and `upstream-parity_CN.md` together when whitelist
semantics, trailer format, or triage flow change. Update
`foundation-product-architecture.md` when the porting policy itself changes.
