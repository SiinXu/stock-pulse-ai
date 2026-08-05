# Import-Cycle Ratchet

- Status: `Living`
- Last verified: 2026-08-05
- Related: [ADR-010](adr/ADR-010-import-cycle-ratchet.md),
  [architecture overview](architecture-overview.md),
  [legacy facade import policy](legacy-facade-import-policy.md),
  `scripts/check_import_layers.py`,
  `scripts/import_layer_baseline.json`

## Purpose

Production packages still contain a finite set of **bidirectional** import pairs
(package A imports B at module level and B imports A). Those cycles make layer
boundaries hard to reason about and allow new back-edges to land silently.

This ratchet:

1. Measures bidirectional pairs from **module-level** imports only.
2. Allows only pairs listed in the checked-in baseline.
3. Fails CI when a **new** pair appears.
4. Treats shrink as free: after you break a cycle, re-run `--write-baseline`.

## Package identity

| Location | Package key |
| --- | --- |
| `src/<name>.py` or `src/<name>/...` | `src.<name>` |
| `data_provider/`, `api/`, `bot/` | `data_provider`, `api`, `bot` |
| `main.py`, `server.py`, `webui.py` | `main`, `server`, `webui` |

Only **module body** imports count. Lazy imports inside functions or methods are
ignored so intentional deferred loads do not create false pairs.

## How to read a failure

```text
[import-layers] ERROR: new-bidirectional-pair: src.foo <-> src.bar: ...
[import-layers] HINT: break the cycle or see docs/import-cycle-ratchet.md ...
```

Meaning: the current tree has a module-level import edge `src.foo → src.bar`
**and** `src.bar → src.foo`, and that undirected pair is not in
`scripts/import_layer_baseline.json`.

Typical fixes:

1. Move a pure helper to a leaf module (for example `src/utils/`) that both sides
   may import one-way.
2. Invert the dependency so only one package owns the shared type or helper.
3. Keep a re-export on the old path if callers/patch targets must stay stable
   (mechanical move only; no silent contract change).

## Commands

```bash
python scripts/check_import_layers.py --self-test
python scripts/check_import_layers.py
python scripts/check_import_layers.py --write-baseline
```

The guard is wired into `./scripts/ci_gate.sh` deterministic checks (self-test
then live check), next to the other AST ratchets.

## Legitimate change path

| Change | Action |
| --- | --- |
| **Shrink** (break an existing cycle) | Merge the code fix, then run `--write-baseline` so the JSON drops the pair. Always allowed. |
| **Growth** (new intentional pair) | **Not** allowed via `--write-baseline` (it refuses). Manually edit the baseline in the same PR, justify the permanent cycle in the PR body, and preferably file follow-up work to remove it. Prefer not to grow. |
| Accidental new pair | Fix the code; do not edit the baseline. |

## Example: config → services edge

Historically `src.config` / `src.config_parts` imported
`src.services.stock_list_parser.split_stock_list`, while services already
depended on config, forming two bidirectional pairs. The pure separator helper
now lives in `src/utils/stock_list.py` (stdlib-only). Configuration imports the
leaf; `src.services.stock_list_parser` re-exports `split_stock_list` so existing
importers and patch targets keep working.
