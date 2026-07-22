# ADR-006: Decompose Oversized Modules Behind Compatibility Facades

- Status: `Accepted (retrospective)`
- Decision date: 2026-07-21
- Recorded: 2026-07-21
- Decision owners: StockPulse maintainers
- References: [PR #291](https://github.com/SiinXu/stock-pulse-ai/pull/291), [PR #293](https://github.com/SiinXu/stock-pulse-ai/pull/293), [PR #296](https://github.com/SiinXu/stock-pulse-ai/pull/296), [PR #297](https://github.com/SiinXu/stock-pulse-ai/pull/297)

## Context

`src/core/pipeline.py`, `src/config.py`, and the configuration registry had grown
large enough to mix unrelated responsibilities. Directly moving definitions was
risky because repository callers and tests relied on stable import paths, patch
targets, class identity, reflection, reload behavior, generated dataclass
methods, field ordering, and broad-exception fingerprints.

The goal of the initial decomposition was structural only. Combining the move
with behavior or API changes would make compatibility evidence ambiguous and
rollback harder.

## Decision

Split oversized modules in sequential, review-sized, behavior-preserving slices:

1. Inventory production imports and relevant test, patch, reflection, and reload
   seams before moving code.
2. Extract one coherent responsibility into a private focused module.
3. Keep the original module or class as the caller-facing compatibility facade;
   do not migrate callers in the same structural slice.
4. Preserve executable bodies and every observed public or patchable contract.
   For extracted pipeline descriptors, bind the complete legacy facade globals
   rather than a selected dependency allowlist.
5. Verify moved ASTs, complete exports, signatures and metadata, facade patching,
   entrypoint imports, targeted behavior, and frozen replay contracts appropriate
   to the module.
6. Classify relocated broad exceptions and regenerate stale fingerprints through
   the repository tooling instead of editing the baseline manually.

A later PR may intentionally simplify a facade or change behavior, but it must
state that contract change separately. This ADR does not require preservation of
unobserved low-level source metadata such as a moved callable's `co_filename`.

## Consequences

- Existing imports, patches, payloads, and entrypoints remain stable while
  implementation ownership becomes more focused.
- Small structural slices are independently reviewable and revertible without a
  data or configuration migration.
- Compatibility facades, global rebinding, reload assembly, and deep regression
  guards add temporary complexity.
- The evidence bar is deliberately deeper than an import smoke test; shallow
  export-only shims are insufficient when runtime patching or reflection is part
  of the observed contract.
- Future cleanup can remove compatibility machinery only through an explicit,
  separately verified contract change.
