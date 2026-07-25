# Analysis Strategy Plugin Authoring Guide

This guide covers the version 1 `analysis_strategy` system-plugin boundary.
Most strategy authors should use a declarative YAML or `SKILL.md` package under
`AGENT_SKILL_DIR`: it requires no trusted Python code and preserves the same
`SkillManager` runtime. Use a system plugin only when a reviewed in-process
plugin already needs the shared manifest and lifecycle boundary. The broader
[plugin extension contract](plugin-extension-contract.md) remains authoritative.

## Package And Registration

An external plugin is one direct child of the configured plugin root:

```text
<PLUGINS_DIR>/
  example-analysis-strategy/
    manifest.json
    plugin.py
```

`PLUGINS_DIR` points to the parent directory. Keeping it unset or blank disables
external discovery. The manifest fields, version rules, entrypoint containment,
diagnostics, and trust model are the same as the tested
[Data Provider reference package](data-provider-plugin-authoring.md#manifest-fields).
An Analysis Strategy plugin normally declares no permissions because it only
publishes a definition, but the manifest `permissions` list is descriptive
metadata and is not an enforcement boundary.

The plugin registers a real `Skill` during `onload()`:

```python
from src.agent.skills.base import Skill
from src.plugins import Plugin as BasePlugin


class Plugin(BasePlugin):
    def onload(self, context):
        definition = Skill(
            name="quality-compounder",
            display_name="Quality Compounder",
            description="Evaluate durable quality and compounding evidence.",
            instructions=(
                "Require durable cash generation, defensible returns on capital, "
                "and an explicit valuation and downside-risk check."
            ),
            category="framework",
            required_tools=["get_daily_history"],
            default_active=False,
            default_router=False,
        )
        context.register(
            "analysis_strategy",
            definition.name,
            definition,
            contract_version="1",
        )
```

Do not retain `PluginContext`; it closes after `onload()` returns. The manager
owns the registration handle and removes the exact definition on disable or
root shutdown. `onunload()` is needed only for resources owned by the plugin
itself. A definition-only plugin should not create clients, threads, or another
strategy runtime.

## Definition Contract

Contract version 1 accepts an actual `Skill` whose `name` exactly matches the
registration ID. The name is at most 128 characters and uses ASCII letters,
digits, dots, underscores, or hyphens, beginning with a letter or digit.
Display name, description, instructions, and category must be non-empty.
Boolean fields must be booleans; `default_priority` must be an integer;
`execution_context` is `inline` or `fork`; list fields contain unique values;
and `core_rules` contains unique integers from 1 through 7.

The registry detaches every accepted value. Later mutation of the plugin-owned
`Skill` cannot rename or alter the enabled catalog entry. Disable removes only
the exact accepted object; a later enable validates and snapshots the current
definition again. Runtime clones always force `enabled=False` and pin `source`
to `plugin:<manifest-id>`, so plugin-supplied provenance cannot be mistaken for
a built-in or custom-directory definition.

`required_tools` narrows tools only when Multi-Agent specialist mode constructs
a `SkillAgent`. `allowed_tools` remains imported metadata and is not a runtime
permission grant. The definition cannot execute Python, write consensus, bypass
tool policy, or replace `StrategyEngine`.

## Load And Verify

From the repository root, point `PLUGINS_DIR` at the reviewed parent directory
and install the `ApplicationServices` root before resolving the catalog:

```bash
PLUGINS_DIR="$PWD/my-plugins" python - <<'PY'
from src.agent.factory import get_skill_manager
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)

services = ApplicationServices()
try:
    set_application_services(services)
    print("discovery", services.external_plugin_results)
    print("load", services.plugin_load_results)
    skill = get_skill_manager().get("quality-compounder")
    print("catalog", None if skill is None else (skill.name, skill.source))
    print("disable", services.plugin_manager.disable("your.plugin-id"))
    print("after-disable", get_skill_manager().get("quality-compounder"))
finally:
    reset_application_services()
PY
```

The candidate should be `registered` during discovery, `enabled` after load,
visible with its pinned plugin source, and absent from the next catalog snapshot
after disable. External discovery is startup-only; changing plugin files or
`PLUGINS_DIR` requires a process restart.

The default application root binds Analysis Strategies and Agent Tools into one
`PluginManager` and one unified registry. A composition caller that supplies a
custom `PluginManager` must bind its Analysis Strategy contract to the exact
`AnalysisStrategyRegistry` consumed by that root. `ApplicationServices` derives
that native backend from the supplied manager or rejects a mismatched explicit
pair; it never creates a second, silently disconnected strategy registry.

## Catalog Precedence And Lifecycle

One resolved catalog feeds Single-Agent prompt assembly, Multi-Agent routing,
and `SkillAgent` construction:

1. `SkillManager.load_builtin_skills()` loads the complete built-in catalog.
2. A configured `AGENT_SKILL_DIR` keeps its existing top-level YAML/YML and
   nested `SKILL.md` discovery behavior. A custom name may replace a built-in.
3. An enabled plugin may add only a name not owned by the resolved built-in or
   custom catalog or by another plugin. Registration conflicts fail closed and
   do not change the existing owner.
4. If a runtime custom-directory change introduces a conflict with an already
   enabled plugin, the custom definition remains authoritative and the plugin
   definition is excluded from the published catalog. Removing that conflict
   makes the still-enabled plugin visible on the next rebuilt snapshot.

The cached prototype is keyed by custom-directory value, application-root
identity, and plugin generation. Load, disable, enable, root replacement, and
custom-directory changes therefore rebuild the next catalog while an in-flight
request may safely retain its already cloned snapshot. Editing files in place
without a configuration change is not hot reload.

Multi-Agent specialist selection remains capped at three definitions.
`StrategyEngine` remains the sole authority for opinion validation,
partitioning, aggregation, and synthesis. No plugin registration priority can
change either rule.

## Diagnostics, Testing, And Trust

Inspect `ApplicationServices.external_plugin_results` for discovery failures and
`plugin_load_results` for lifecycle or registration failures. Representative
load codes are `extension_implementation_invalid`,
`extension_registration_conflict`, `native_registration_conflict`, and
`plugin_onload_failed`. One failing plugin is isolated and later candidates
continue loading.

Run the focused contract and cross-path regressions with:

```bash
python -m py_compile src/plugins/analysis_strategies.py \
  tests/plugins/test_analysis_strategy_plugins.py
python -m pytest -q tests/plugins/test_analysis_strategy_plugins.py
python -m pytest -q tests/plugins tests/test_application_services.py \
  tests/agent tests/test_multi_agent.py
```

Setting `PLUGINS_DIR` opts into arbitrary Python running with the StockPulse
process user's privileges. There is no sandbox, subprocess boundary, signature
verification, marketplace, dependency installer, automatic update, or hot
reload. Review the complete plugin and dependencies, restrict directory
ownership and writes, and prefer `AGENT_SKILL_DIR` when declarative content is
sufficient.
