# Example Alternative Data (corporate events)

Default-off reference plugin for the **alternative-data contract** under
ToolSurface (Issues #139 / #1144).

## What it registers

| Item | Value |
| --- | --- |
| Manifest ID | `stockpulse.example-alternative-data` |
| Extension point | `agent_tool` |
| Tool name | `get_corporate_events_brief` |
| Capability | `alt_data:read` (declared in manifest **and** `ToolPolicy`) |
| Authority | `non_authoritative` / `supporting_only` |
| Network | None (deterministic fixture) |

## Security and trust

- Setting `PLUGINS_DIR` runs arbitrary Python with process privileges.
- Manifest `permissions` are **declaration** (#944), not a sandbox.
- ToolSurface still **denies** calls when the session lacks `alt_data:read`.
- Live agent hardening for external tools remains issue **#539**; treat this
  package as load + contract proof, not a production feed.

## Enable (explicit opt-in)

```bash
export PLUGINS_DIR="$PWD/examples/plugins"
```

`PLUGINS_DIR` must point at the **parent** of this directory. Unset / blank
keeps the plugin undiscovered (safe default).

## Governance

Host helpers in `src/services/alternative_data_governance.py`:

- project tool results into AnalysisContext as a non-quality-weighted block;
- project evidence as supporting-only strata (never `verified_fact` / `decision`);
- map invalid / missing payloads to gaps without inventing events or confidence.

## Related

- [Alternative data plugin contract](../../../docs/alternative-data-plugin-contract.md)
- [Plugin development guide](../../../docs/plugin-development-guide.md)
- [External framework adapter guide](../../../docs/external-framework-adapter-guide.md) (OpenBB thin-adapter discipline)
