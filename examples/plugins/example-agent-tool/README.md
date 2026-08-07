# Example Agent Tool (load-and-register)

Registers a deterministic, network-free `example_echo` `ToolDefinition` on the
process `ToolRegistry` through the frozen `agent_tool` extension point.

## Security boundary (#539)

Issue **#539** gates wiring external `agent_tool` plugins into **live agent
runs** until ToolSurface sandbox hardening is complete. This package is
intentionally **load-and-register only**:

- Contract tests load the package, assert the tool appears on the registry, and
  may call the handler **directly**.
- Do not treat this sample as proof of a hardened agent execution path.
- Registration never bypasses ToolSurface policy validation; it also does not
  create a parallel `plugin_manager.get_plugin(name).execute()` path.

Point `PLUGINS_DIR` at this directory's parent (`examples/plugins`):

```bash
export PLUGINS_DIR="$PWD/examples/plugins"
```

`ToolDefinition` / `ToolParameter` / `ToolPolicy` are ToolSurface-owned types
imported from `src.agent.tools.registry` (not re-exported on the plugin author
surface). Review all plugin code before enabling `PLUGINS_DIR`.

See the [Plugin Development Guide](../../../docs/plugin-development-guide.md).
