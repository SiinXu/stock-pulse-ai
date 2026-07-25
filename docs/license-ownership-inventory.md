# MIT vs AGPL-3.0 File Ownership Inventory Process

**Status**: Process (progressive coverage)  
**Last updated**: 2026-07-26  
**Authority**: Root [LICENSE](../LICENSE) and [LICENSE.AGPL](../LICENSE.AGPL)

This document defines a **repeatable maintainer process** for classifying and
recording file-level license ownership between:

1. **Upstream / original** code from `ZhuLinsen/daily_stock_analysis` — **MIT**
2. **New or substantially modified StockPulse contributions** — **AGPL-3.0-only**

It is **not** a completed full-repository legal audit and is **not** legal
advice. Redistributors and SaaS/network operators must still read the root
license notice and obtain their own counsel where required.

Related architectural provenance rules:
[Foundation Pipeline And Product Layer](foundation-product-architecture.md#license-and-provenance-boundary).

---

## Why this process exists

`LICENSE` correctly states dual licensing for the combined work. Some files
already carry `SPDX-License-Identifier` headers, but without a published
process:

- contributors lack a default SPDX convention for new StockPulse files
- maintainers cannot measure SPDX / ownership coverage over time
- redistributors cannot see how file ownership is classified or updated

Network use of the combined work (web service, API, or hosted agent) is
subject to the AGPL-3.0 terms described in `LICENSE`. This process does not
change those terms; it only makes file-level provenance reviewable.

---

## Classification rules

| Class | When to use | Default SPDX | Notes |
| --- | --- | --- | --- |
| **MIT-inherited** | File is substantially unchanged from upstream `ZhuLinsen/daily_stock_analysis`, or is a faithful port that retains upstream copyright | `MIT` | Keep upstream copyright notice; record upstream path/commit when known |
| **AGPL-new** | File was created for StockPulse, or is substantially rewritten StockPulse work with independent authorship | `AGPL-3.0-only` | Default for new StockPulse-authored source |
| **Mixed / dual-notice** | File contains clearly separable upstream and StockPulse sections, or a StockPulse-substantial edit of an MIT-origin file where both notices must remain | Prefer dual notice in file header **or** inventory row `Mixed` with notes | Do not invent a third product license |
| **Third-party vendored** | Vendored upstream library, model code, or copied third-party material | SPDX of **that** component | Inventory must record origin URL and upstream license; do not relabel as StockPulse AGPL |
| **Non-code / docs / config** | Markdown, config, assets without executable provenance | Usually not SPDX-tagged | Inventory when redistribution-sensitive; otherwise leave unmarked |

### What “substantially modified” means (operational)

Treat a file as **AGPL-new** (or **Mixed** with notes) when StockPulse changes
alter the file’s dominant authorship or control flow—for example new modules,
rewritten public contracts, or large feature additions. Prefer **MIT-inherited**
when the file remains a thin adaptation of identifiable upstream content.

When provenance is uncertain: **do not guess**. Record `Unknown` in the
inventory, block merge of redistribution-sensitive packaging, and resolve
before release notes claim a completed audit.

Architectural track (foundation vs product) **does not** determine license.
See [foundation-product-architecture.md](foundation-product-architecture.md).

---

## Default SPDX convention for new StockPulse source

For new StockPulse-authored Python (and other source) files under this
repository’s copyright, use:

```text
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
```

For clearly MIT-inherited files that already carry upstream notices, preserve
those notices and use:

```text
# SPDX-License-Identifier: MIT
```

only when the file remains MIT-owned per the table above.

Do not add AGPL headers to third-party vendored trees. Example of a vendored
MIT path already in-tree: `src/services/_kronos_vendor/`.

---

## Inventory template

Maintain a progressive table (in this file’s “Working inventory samples”
section, or a maintainer-owned spreadsheet linked from a PR). Columns:

| Column | Meaning |
| --- | --- |
| `path` | Repository-relative path or glob |
| `origin` | `upstream-mit` / `stockpulse-agpl` / `third-party` / `mixed` / `unknown` |
| `license` | SPDX id or dual notice reference |
| `last_reviewed` | ISO date (`YYYY-MM-DD`) of the last human review |
| `notes` | Upstream commit/PR, vendor URL, dual-notice rationale, open questions |

Template row:

```markdown
| path | origin | license | last_reviewed | notes |
| --- | --- | --- | --- | --- |
| `src/example/module.py` | stockpulse-agpl | AGPL-3.0-only | 2026-07-26 | New StockPulse module |
```

### Working inventory samples (not exhaustive)

These rows illustrate the process. They are **examples**, not a claim that the
repository has been fully inventoried.

| path | origin | license | last_reviewed | notes |
| --- | --- | --- | --- | --- |
| `LICENSE` | mixed | MIT + AGPL-3.0-only notice | 2026-07-26 | Dual-license notice for the combined work |
| `LICENSE.AGPL` | stockpulse-agpl | AGPL-3.0-only | 2026-07-26 | Full AGPL text |
| `src/services/_kronos_vendor/` | third-party | MIT | 2026-07-26 | Vendored; keep upstream MIT SPDX |
| `src/schemas/investment_framework.py` | stockpulse-agpl | AGPL-3.0-only | 2026-07-26 | Example of existing AGPL SPDX header |
| `src/services/kronos_forecast_service.py` | stockpulse-agpl | AGPL-3.0-only | 2026-07-26 | Example of existing AGPL SPDX header |

---

## When a PR must update the inventory

Update the inventory (or add/adjust SPDX headers per this process) when the PR:

1. Adds a **new top-level package or major tree** (`src/<new>/`, `api/<new>/`, vendored directory, etc.)
2. **Vendors** third-party code or model weights metadata that ships in the repo
3. **Ports** a substantial upstream MIT file into StockPulse
4. Changes **license notices**, dual-license messaging, or redistribution packaging
5. Resolves a previous `unknown` provenance row

Routine product bugfixes inside an already-classified StockPulse module do
**not** require inventory churn beyond keeping SPDX headers consistent on new
files.

This process is **not** an automatic CI merge blocker for unrelated PRs unless
maintainers later adopt an explicit enforcement policy.

---

## Coverage report (maintainer checklist)

Progressive coverage is expected. **100% SPDX is not required on day one.**

### 1) List files with SPDX headers

From the repository root:

```bash
git grep -n "SPDX-License-Identifier" -- \
  '*.py' '*.ts' '*.tsx' '*.js' '*.mjs' '*.cjs' '*.go' '*.rs' || true
```

### 2) Count SPDX-tagged paths vs Python sources (rough signal)

```bash
echo "SPDX-tagged paths:"
git grep -l "SPDX-License-Identifier" -- '*.py' | wc -l
echo "Tracked Python files:"
git ls-files '*.py' | wc -l
```

Interpret the ratio as a **progress metric only**. Untagged files may be
MIT-inherited, docs-adjacent, generated, or simply not yet reviewed.

### 3) Sample dual-license / vendor hotspots

```bash
git grep -n "SPDX-License-Identifier: MIT" -- '*.py' || true
git grep -n "SPDX-License-Identifier: AGPL-3.0-only" -- '*.py' | head
```

### 4) Record the review

In the PR that touches provenance:

- paste command outputs (or summarize counts)
- update inventory rows for paths you actually reviewed
- do **not** claim “full-repo audit complete” unless a dedicated review covered
  every in-scope path and is linked from the PR

Optional helper (non-enforcing):

```bash
python scripts/report_spdx_coverage.py
```

---

## High-level network-use note (not legal advice)

When StockPulse (or a modified version) is made available to users over a
network—including as a web UI, API, or hosted agent—the dual-license notice in
`LICENSE` states that **AGPL-3.0 terms apply to the combined work**. Operators
must retain copyright and license texts and consult `LICENSE` / `LICENSE.AGPL`.
This inventory process does not grant additional permissions and does not
replace compliance review for SaaS deployment.

---

## Contributor quick start

1. New StockPulse source file → AGPL SPDX header (see default convention above).
2. Porting upstream MIT code → preserve MIT notice; inventory the path; prefer
   faithful attribution over silent relicense.
3. Vendoring third-party code → keep upstream license; inventory origin URL.
4. Unsure → open a maintainer question; mark inventory `unknown` rather than
   guessing.

Also see [Contributing Guide](CONTRIBUTING_EN.md) and the Chinese
[贡献指南](CONTRIBUTING.md).

---

## Change control

Update this document when classification rules, SPDX defaults, or inventory
triggers change. Product release notes should not claim a completed full-repo
license audit unless that audit actually happened and is linked here.
