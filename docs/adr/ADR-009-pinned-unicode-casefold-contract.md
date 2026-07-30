# ADR-009: Pin Unicode Case Folding for Investment Framework Names

- Status: `Accepted`
- Decision date: 2026-07-30
- Decision owners: StockPulse maintainers
- References: [PR #687](https://github.com/SiinXu/stock-pulse-ai/pull/687), [Unicode 15.0.0 CaseFolding data](https://www.unicode.org/Public/15.0.0/ucd/CaseFolding.txt), `src/schemas/investment_framework.py`, `apps/dsa-web/src/components/settings/investmentFrameworkEditorModel.ts`

## Context

Investment-framework evaluation-dimension names are unique without regard to
case. Python, browser, Node, and ICU releases do not necessarily implement the
same Unicode version or the same full case-fold behavior. Delegating this
persisted validation rule to each runtime therefore allowed the API and Web
editor to disagree. Simple lowercasing also misses multi-code-point mappings
such as `Straße` and `STRASSE`.

This is a cross-runtime validation and persistence contract. It must remain
deterministic for every supported runtime instead of changing when a host
upgrades its Unicode database.

## Decision

Use the Unicode 15.0.0 default full case-fold mapping (`C` plus `F` statuses) as
the single versioned contract for investment-framework evaluation-dimension
name uniqueness.

- Backend and Web implementations embed compact generated mappings from the
  same official `CaseFolding-15.0.0.txt` source and publish the same version
  constant.
- Unlisted code points remain unchanged. Locale-specific Turkic mappings are
  outside this default case-fold contract.
- Cross-runtime tests compare every Unicode code point and retain named
  regressions on both sides of the pinned version boundary.
- The Unicode source, digest, and license remain recorded with the generated
  data and in `THIRD_PARTY_NOTICES`.
- Upgrading Unicode is an explicit contract change. It must update both tables,
  constants, provenance, documentation, and regressions in one reviewed change.

This decision applies only to investment-framework dimension-name uniqueness.
It does not establish a repository-wide normalization policy for search,
symbols, user content, or display text.

## Consequences

- API and Web validation remain identical regardless of Python, Node, browser,
  ICU, or operating-system Unicode versions.
- Multi-code-point folds and version-boundary behavior are testable and stable.
- The repository carries two generated representations and must update them
  together. The all-code-point equivalence test makes drift blocking.
- Characters first assigned a fold after Unicode 15.0.0 remain distinct until a
  deliberate contract upgrade.
- No data migration is required for this adoption. Existing stored frameworks
  retain their versions; create/update validation applies the pinned rule.
