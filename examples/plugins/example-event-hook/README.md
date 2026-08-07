# Example Event Hook

Trusted in-process plugin that registers an **observational** analysis lifecycle
hook (`analysis.started` / `completed` / `failed`). Callbacks log non-sensitive
task metadata only. They must not mutate analysis outcomes, open network
connections, or block the analysis path.

Point `PLUGINS_DIR` at this directory's parent (`examples/plugins`):

```bash
export PLUGINS_DIR="$PWD/examples/plugins"
python - <<'PY'
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.config import Config
from src.plugins import dispatch_analysis_event

reset_application_services()
services = ApplicationServices(
    config=Config(stock_list=[]),
    plugins_dir="examples/plugins",
)
set_application_services(services)
assert services.plugin_manager.load  # plugins already started on root install
dispatch_analysis_event(
    "analysis.started",
    task_id="demo-task",
    trace_id="demo-trace",
    stock_code="600519",
    trigger_source="example",
)
services.close()
reset_application_services()
PY
```

External plugins execute with the same OS privileges as StockPulse. Review all
code before opting in. See the
[Plugin Development Guide](../../../docs/plugin-development-guide.md).
