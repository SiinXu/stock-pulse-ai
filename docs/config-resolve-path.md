# Single Config Resolve Path (value + source)

- Status: `Living`
- Last verified: 2026-08-12
- Related: Issue [#1070](https://github.com/SiinXu/stock-pulse-ai/issues/1070),
  [config-access ratchet](config-access-ratchet.md),
  [config registry guard](../tests/core/test_env_example_config_registry_guard.py)

## Purpose

Runtime configuration is still loaded into the typed `Config` singleton, and
Settings still read/write the persisted `.env` through `SystemConfigService`.
What this package adds is a **single raw-key resolve path** that returns both:

| Field | Meaning |
| --- | --- |
| `value` | Effective raw string (or `None` / caller default) |
| `source` | `default` · `env` · `persisted` |

New features must not invent a fourth ad-hoc channel (direct `os.getenv` mixed
with a one-off dotenv read). Prefer this path for raw string lookup; keep typed
`Config` attributes for runtime behavior that already goes through
`_load_from_env`.

## Package layout

```text
src/core/config/
  resolve.py     # resolve / resolve_config_value / dump_resolved
  sources.py     # ConfigSource, env + .env adapters, WebUI priority keys
  registry.py    # re-export of src.core.config_registry (no second catalog)
```

Registration metadata remains owned by `src/core/config_registry` and its
partitioned parts (344 registered keys at verification time). The temporary
unregistered `.env.example` debt allowlist (shrink-only, max 161) is **not** a
resolve channel and must not grow via this path.

## Precedence (value-preserving)

Matches historical `Config._resolve_env_value`:

1. WebUI file-priority keys (or `prefer_env_file=True`) when the file has a value:
   - process env wins only when bootstrap capture proves an explicit override;
   - otherwise the persisted `.env` wins (`source=persisted`).
2. Else process env when present (`source=env`).
3. Else persisted file when present (`source=persisted`).
4. Else caller default (`source=default`).

Registry `default_value` is applied only by `resolve_registered` for keys that
are already registered. Unregistered keys never invent defaults here.

## Compatibility facades

| Surface | Role |
| --- | --- |
| `Config._resolve_env_value` | Thin wrapper; returns `.value` only |
| `Config.resolve_with_source` | Same inputs; returns `ResolvedConfigValue` |
| `src.core.config.resolve` | Public package entry for new code |
| `src.core.config.registry` | Re-export; does not replace `config_registry` |

Bootstrap override capture and class attributes used by runtime reliability
tests remain on `Config`.

## Diagnostics

```python
from src.core.config import dump_resolved, resolve

row = resolve("STOCK_LIST", prefer_env_file=True)
# ResolvedConfigValue(key=..., value=..., source=ConfigSource.PERSISTED|ENV|DEFAULT)

for item in dump_resolved():  # all registered keys
    print(item.as_dict())
```

## Hard rules

- Do not change effective config values in the same PR as this path unless the
  PR is an explicit feature that documents the semantic change.
- Do not expand the unregistered-key debt baseline to green a new key; register
  the key in `config_registry_parts/*` instead.
- Do not add a parallel key list under `src/core/config/`.
