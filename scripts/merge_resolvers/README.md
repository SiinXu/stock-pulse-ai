# Derived-file merge resolvers

These resolvers handle conflicts where neither Git side is the merged truth.
They plan every output before writing anything, reject unknown conflict shapes,
refuse all-zero write batches, replace all files as one batch, and stage
them with one Git index update.

## When a coordinator runs this

After `git merge` (or rebase) leaves unmerged derived files:

```bash
python scripts/merge_resolvers/resolve.py --list
python scripts/merge_resolvers/resolve.py $(git diff --name-only --diff-filter=U)
```

On a clean tree the second command is a no-op and exits `0`. Do not pass
`--ours` / `--theirs` for these files: the correct value is recomputed or
union-merged from the merged tree.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Every requested conflict was resolved and staged, or there were no paths (clean-tree no-op) |
| `2` | Deliberate refusal. stderr is `REFUSE <path>: <reason>`. **Nothing was written.** |
| `1` | Internal error (bad git state, unreadable file, resolver bug). **Nothing was staged.** |

**Refusal is the safe outcome.** Merging a semantic conflict as if it were
additive silently drops one side and is far worse than bumping the PR out of
the merge train. If any file is refused, the whole batch is refused and the
working tree is left untouched. Fail-open is the dangerous failure mode here.

If the tool refuses, leave the conflict in place and let the pull request bump
out.

## Why choosing a side is wrong

- `bundle-size-budget.json` is a complete budget registry. The resolver performs
  a three-way merge by rule ID only when each side changed distinct rules. It
  refuses overlapping rule changes, rule removal/reordering, unexplained numeric
  changes, and top-level metadata changed differently on both sides; those cases
  require a combined production-build measurement.
- Public-surface tests snapshot exports, facade method lists, and implementation
  AST hashes. The resolver recomputes those values from the merged Python modules.
  It refuses conflicts outside an `EXPECTED_*` assignment or any failed import.
- `docs/INDEX.md` and `docs/INDEX_EN.md` are complete bilingual indexes. Their
  conflict rows are combined by link target and sorted within each insertion
  point. The resolver requires the pair, matching per-side row counts, and refuses
  duplicate targets or non-row conflict content.
- The playground catalog test stores the full catalog's derived count. The
  resolver recounts `PLAYGROUND_CATALOG` from the merged catalog and refuses any
  conflict that is not exactly one length assertion per side.
- `openapi.json` and `api.generated.ts` are generated artifacts. The resolver
  calls the repository's deterministic OpenAPI exporter and `openapi-typescript`
  against temporary files, then writes both generated artifacts together. Run
  `npm ci` in `apps/dsa-web` first when Web dependencies are absent.
- Existing additive i18n and config-registry hash resolvers are included in the
  same atomic entry point because real public-surface PRs conflict in those
  snapshots too. I18n accepts only one-line array/map additions with disjoint
  keys; registry hashes are recomputed by importing the merged registry.
- `settingsHelp.<lang>.ts` files are the Settings-page help catalogue. The
  resolver unions complete, brace-balanced entry blocks by settings key,
  including one-line empty `key: {}` entries. Complete and mid-block (open)
  forms share that key table: the same key with different bodies is refused,
  and equivalent open/complete copies are kept once. It also refuses empty
  sides, unexpected hunk lines, and hunks where only one side ends mid-block.

Rollback is ordinary Git merge rollback: run `git merge --abort`. The resolver
does not commit, push, raise budgets, or resolve semantic source conflicts.
