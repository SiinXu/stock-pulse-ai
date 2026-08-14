# Derived-file merge resolvers

A small number of files in this repository record **whole-repository state**:
snapshot digests of the configuration registry, the flat i18n tables, the
production bundle-size budgets, the documentation index, the Playground
catalogue size, and the public-export surface guards. Every pull request that
touches the corresponding subsystem rewrites them, and a single slot cannot hold
two values, so any two such pull requests conflict.

The important property of this class of conflict is that **neither side is
correct**. `--ours` silently drops the incoming contribution, `--theirs`
silently drops what main gained since the branch point, and a line-level union
either duplicates a constant or produces invalid JSON/TypeScript. The correct
value is *recomputed from* or *merged over* the merged tree.

These resolvers implement exactly that, and refuse everything else.

## Usage

```bash
python scripts/merge_resolvers/resolve.py --list

git merge --no-commit --no-ff <pull request head>
python scripts/merge_resolvers/resolve.py $(git diff --name-only --diff-filter=U)
git diff --name-only --diff-filter=U      # empty when everything was resolved
```

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | every requested file was resolved, written, and staged |
| `2` | at least one file was refused; **nothing was written** |
| `1` | internal error (bad git state, unreadable file, resolver bug) |

Options:

| Option | Effect |
| --- | --- |
| `--list` | list the supported files and exit |
| `--dry-run` | compute every resolution, report, write nothing |
| `--no-stage` | write the resolved files but do not `git add` them |
| `--remeasure` | let the bundle-budget resolver run a real production build of the merged tree instead of refusing an ambiguous chunk |
| `--rebaseline-collateral` | with `--remeasure`, also record the measured size of chunks that neither side changed but that the merged build pushed over budget |

## Atomicity

The batch is atomic on purpose. An earlier ad-hoc i18n resolver validated and
wrote in a single pass, so refusing the last file left a half-resolved working
tree that *looked* resolved.

Here:

1. every resolver computes its result in memory and writes nothing;
2. the first refusal aborts the whole batch and reports which files *would*
   have resolved;
3. only then are the files written, and only after that are they `git add`ed;
4. the expensive steps (production build, code generators) run last, and if one
   of them refuses, every file written in step 3 is restored with
   `git checkout --merge` — which still works, because nothing has been staged
   yet and the index therefore still holds all three merge stages.

## Fail-closed by design

The dangerous failure mode for this tool is **fail-open**: merging something
that should not have been merged. Refusing a legitimate input costs one pull
request a slot in the merge train; silently flattening a semantic conflict costs
a production regression that no review will catch, because the diff looks like
a routine snapshot refresh.

Every resolver therefore refuses on anything it does not fully recognise. The
per-file refusal conditions are listed below and repeated in each module's
docstring.

## The files

### `apps/dsa-web/scripts/bundle-size-budget.json` — `bundle_budget.py`

*Why neither side is correct.* Each rule records the gzip size of one production
chunk. Two pull requests that both grow the same chunk write two different
numbers, and the post-merge size is neither of them — it is roughly
`base + (ours - base) + (theirs - base)`. A line union would also break the JSON
syntax. The file's own `description` says: *do not raise budgets to hide
regressions without justification*, so the resolver never picks the larger
number and calls it a day.

*What it does.* Three-way merges the `rules` array by `id`, preserving the
first-match ordering that `check-bundle-size.mjs` depends on. Rules changed on
only one side merge unambiguously.

*Refuses when:*

* an index stage is missing (add/add, delete/modify);
* a stage is not valid JSON, or `rules` is not a list of objects with unique
  string `id`s;
* a rule id was removed on one side and kept or changed on the other;
* a rule's `match` glob differs on both sides;
* a rule's `maxGzipBytes` / `measuredGzipBytes` were changed on **both** sides,
  unless `--remeasure` is given;
* a top-level key other than `baselineNote` / `measuredAt` was changed on both
  sides to different values;
* an incoming-only rule cannot be anchored into the merged ordering;
* under `--remeasure`, the merged build exceeds a budget that neither side
  changed, unless `--rebaseline-collateral` is also given.

With `--remeasure` the resolver runs `npm run build` on the merged tree and
measures each chunk with the same glob matching and gzip level that
`check-bundle-size.mjs` uses, then records `measured` plus the rule's existing
headroom and writes a note in the established format (the `IntelligenceSourcesPanel`
and `vendor-icons` notes are the precedent).

### `tests/**/*_public_surface.py` and friends — `public_surface.py`

Covers `tests/agent/test_agent_orchestrator_public_surface.py`,
`tests/agent/test_agent_executor_public_surface.py`,
`tests/core/test_pipeline_public_surface.py`,
`tests/notification/test_notification_public_surface.py`, and
`tests/test_analysis_stage_facade.py` — dispatched by content
(`EXPECTED_PUBLIC_EXPORTS`), not by filename.

*Why neither side is correct.* These files pin the whole public surface of a
module: the set of public names and SHA-256 digests over the canonical AST of
the extracted method containers. A digest of main's tree and a digest of the
branch's tree are both digests of trees that no longer exist after the merge.

*What it does.* Recomputes both snapshots from the merged tree, reusing the test
file's own `_container_ast_hash` helper rather than a re-implementation that
could drift from it.

*Refuses when:*

* either side of a hunk does not parse as Python;
* the sides differ anywhere outside a top-level `EXPECTED_*` assignment;
* an `EXPECTED_*` constant exists on only one side;
* a conflicting constant is neither `EXPECTED_PUBLIC_EXPORTS` nor a constant
  whose two sides become identical once the 64-hex digest literals are blanked
  (i.e. a hand-maintained method-name tuple changed on both sides);
* `EXPECTED_PUBLIC_EXPORTS` is not the expected
  `frozenset("""...""".split())` shape;
* the guarded module cannot be determined from the file's
  `importlib.import_module(...)` calls;
* the guarded module fails to import from the merged tree, or the recompute
  subprocess fails for any reason. A failed recompute is a refusal, never a
  fallback to one side.

### `tests/core/test_config_registry_public_exports.py` — `config_registry.py`

*Why neither side is correct.* Same reasoning, with its own recipes: the public
and private export sets of `src.core.config_registry`, its module annotations,
and digests over `get_registered_field_keys()` and `build_schema_response()`.

*Refuses when:* the sides differ outside the `EXPECTED_*` constants, a constant
exists on only one side, a conflicting constant has no recompute recipe, or
importing the registry from the merged tree fails.

### `docs/INDEX.md` + `docs/INDEX_EN.md` — `docs_index.py`

*Why neither side is correct.* Both files are the repository-wide table of
contents, appended to by every pull request that adds a document. Keeping one
side loses the other's entry and leaves the bilingual pair out of sync.

*Refuses when:*

* any non-blank line in a hunk is not a markdown table row;
* a hunk touches the table separator row;
* both sides carry a row for the same document link with different text;
* both index files are in the batch and the merge adds a different number of
  rows to each — the bilingual documentation rule requires them to move
  together.

### `apps/dsa-web/src/playground/__tests__/catalog.test.ts` — `playground_catalog.py`

*Why neither side is correct.* The test pins the catalogue size with
`toHaveLength(N)`. `catalog.ts` itself merges cleanly, but `N` cannot hold both
results: main's `N` fails by the branch's additions and the branch's `N` fails
by main's.

*What it does.* Bundles the merged `catalog.ts` with esbuild and counts the
entries — ground truth from the merged tree. Without `node_modules` it falls
back to the three-way arithmetic `ours + theirs - base`, which is only valid
when both sides added entries.

*Refuses when:* a hunk carries anything other than `toHaveLength(<int>)`
differences, the two sides carry a different number of count assertions, a side
lowered a count relative to the base, or the count can be neither recomputed nor
derived (no esbuild *and* no base stage).

### `apps/dsa-web/src/i18n/**/*.ts` — `i18n_locales.py`

*Why neither side is correct.* Each locale file is one flat, sorted table of
every translation key in the product. Losing a side means the UI falls back to
raw key names at runtime.

*Refuses when:* a hunk line is not a single flat entry (`"key",` or
`"key": "value",`) — nested objects, spreads, comments and type annotations all
refuse — or the same key appears on both sides with different values.

### `apps/dsa-web/src/locales/settingsHelp.<lang>.ts` — `settings_help.py`

*Why neither side is correct.* The whole-repository settings help catalogue, one
nested block per configuration key. Losing a side means the Settings page shows
a bare key name.

*Refuses when:* a hunk contains anything other than complete, brace-balanced
entry blocks (or, on **both** sides, exactly one trailing block closed by the
shared brace that follows the hunk); the same settings key appears on both sides
with different bodies; or only one side ends mid-block, in which case the shared
closing brace cannot serve both.

### `apps/dsa-web/openapi.json`, `apps/dsa-web/src/types/api.generated.ts` — `generated_artifacts.py`

*Why neither side is correct.* These are build outputs. `openapi-types-gate`
regenerates them and fails on any drift, so the only value that can pass CI is
the one produced from the merged tree. This resolver never merges their text; it
runs the same commands the CI job runs:

```bash
python scripts/export_openapi.py --output apps/dsa-web/openapi.json
cd apps/dsa-web && npm run generate:api-types
```

*Refuses when:* a generator is missing or fails on the merged tree,
`node_modules` is absent when the TypeScript generator is needed, or the
regenerated output still contains conflict markers.

## Adding a resolver

A resolver module exposes:

```python
NAME: str
DESCRIPTION: str
def matches(rel_path: str) -> bool: ...
def resolve(ctx: Context, rel_path: str) -> Resolution: ...      # raises Refusal
def validate_batch(ctx, resolutions) -> None: ...                # optional
def finalize(ctx, rel_path) -> list[str]: ...                    # optional, deferred
```

Register it in `RESOLVERS` in `resolve.py`. Exact-path resolvers must come
before content-dispatching ones. Add unit tests to
`tests/scripts/test_merge_resolvers.py` covering, at minimum: a normal additive
merge, both sides changing the same entry (must refuse), a marker-free file
(no-op), and an unexpected hunk shape (must refuse).
