# Example Analysis Strategy

Registers the declarative Skill `example-quality-compounder` through the
`analysis_strategy` extension point. Most authors should prefer YAML or
`SKILL.md` under `AGENT_SKILL_DIR` instead of a trusted Python plugin.

Point `PLUGINS_DIR` at this directory's parent (`examples/plugins`):

```bash
export PLUGINS_DIR="$PWD/examples/plugins"
```

The definition does not execute Python at analysis time, write consensus, or
bypass tool policy. Runtime clones force `enabled=False` and pin
`source=plugin:<manifest-id>`.

See the
[Analysis Strategy Plugin Authoring Guide](../../../docs/analysis-strategy-plugin-authoring.md)
and the [Plugin Development Guide](../../../docs/plugin-development-guide.md).

External plugins run with the same OS privileges as StockPulse and are not
sandboxed.
