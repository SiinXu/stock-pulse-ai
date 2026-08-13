"""Recompute public-surface test snapshots from the merged implementation."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .common import ConflictContext, RefusalError, parse_conflict_hunks


SUPPORTED_PATHS = frozenset(
    {
        Path("tests/agent/test_agent_orchestrator_public_surface.py"),
        Path("tests/agent/test_agent_executor_public_surface.py"),
        Path("tests/core/test_pipeline_public_surface.py"),
        Path("tests/notification/test_notification_public_surface.py"),
        Path("tests/test_analysis_stage_facade.py"),
    }
)

_SNAPSHOT_LINE = __import__("re").compile(
    r'^\s*(?:[(){}\[\],]|"[^"]*"(?:\s*:\s*"[0-9a-f]{64}")?,?|'
    r"(?:[A-Za-z_][A-Za-z0-9_]*\s+)+[A-Za-z_][A-Za-z0-9_]*|"
    r'[A-Za-z_][A-Za-z0-9_]*|#.*|""".*|.*\.split\(\))\s*$'
)


def _resolve_snapshot_hunks(context: ConflictContext) -> str:
    parts, hunk_count = parse_conflict_hunks(context.path, context.current)
    if hunk_count == 0:
        raise RefusalError(context.path, "file has no conflict hunks")

    rendered: list[str] = []
    stage_cursors = {"ours": 0, "theirs": 0}

    def locate_assignment(
        stage_name: str,
        stage_text: str,
        lines: tuple[str, ...],
    ) -> str:
        if not lines:
            raise RefusalError(context.path, f"{stage_name} snapshot side is empty")
        try:
            tree = ast.parse(stage_text)
        except SyntaxError as exc:
            raise RefusalError(context.path, f"{stage_name} snapshot file is invalid: {exc}") from exc
        spans = {
            node.targets[0].id: (node.lineno - 1, node.end_lineno or node.lineno)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.startswith("EXPECTED_")
        }
        stage_lines = stage_text.splitlines(keepends=True)
        start_at = stage_cursors[stage_name]
        matches = [
            index
            for index in range(start_at, len(stage_lines) - len(lines) + 1)
            if tuple(stage_lines[index : index + len(lines)]) == lines
        ]
        if len(matches) != 1:
            raise RefusalError(
                context.path,
                f"{stage_name} conflict side is not uniquely located in its index stage",
            )
        start = matches[0]
        end = start + len(lines)
        owners = [name for name, span in spans.items() if span[0] <= start and end <= span[1]]
        if len(owners) != 1:
            raise RefusalError(
                context.path,
                f"{stage_name} conflict side is not inside one EXPECTED_* assignment",
            )
        stage_cursors[stage_name] = end
        return owners[0]

    for part in parts:
        if isinstance(part, str):
            rendered.append(part)
            continue

        our_assignment = locate_assignment("ours", context.ours, part.ours)
        their_assignment = locate_assignment("theirs", context.theirs, part.theirs)
        if our_assignment != their_assignment:
            raise RefusalError(
                context.path,
                f"conflict crosses snapshot assignments: {our_assignment} vs {their_assignment}",
            )
        if part.ours == part.theirs:
            raise RefusalError(
                context.path,
                f"both sides changed the same {our_assignment} entry",
            )
        candidate_lines = [*part.ours, *part.theirs]
        if not candidate_lines or not all(
            not line.strip() or _SNAPSHOT_LINE.match(line.rstrip("\n"))
            for line in candidate_lines
        ):
            raise RefusalError(
                context.path,
                f"conflict in {our_assignment} contains non-snapshot code",
            )
        rendered.extend(part.ours)

    text = "".join(rendered)
    try:
        ast.parse(text)
    except SyntaxError as exc:
        raise RefusalError(context.path, f"snapshot structure cannot be recovered: {exc}") from exc
    return text


def _run_snapshot_probe(root: Path, path: Path) -> dict[str, Any]:
    probe = r'''
import ast, hashlib, importlib, inspect, json, sys
from pathlib import Path
from types import CodeType
from tests.litellm_stub import ensure_litellm_stub
ensure_litellm_stub()

target = sys.argv[1]
module_names = {
    "tests/agent/test_agent_orchestrator_public_surface.py": "src.agent.orchestrator",
    "tests/agent/test_agent_executor_public_surface.py": "src.agent.executor",
    "tests/core/test_pipeline_public_surface.py": "src.core.pipeline",
    "tests/notification/test_notification_public_surface.py": "src.notification",
    "tests/test_analysis_stage_facade.py": "src.core.stages.analysis",
}
module = importlib.import_module(module_names[target])

def canonical(value):
    if isinstance(value, ast.AST):
        fields = [
            [field, canonical(child)]
            for field, child in ast.iter_fields(value)
            if field != "type_params"
        ]
        return [value.__class__.__name__, fields]
    if isinstance(value, list):
        return [canonical(item) for item in value]
    if value is Ellipsis:
        return {"constant": "Ellipsis"}
    return value

def container_hash(container, sort_keys=False):
    source_path = inspect.getsourcefile(container)
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    class_node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == container.__name__)
    records = [
        (node.name, canonical(node))
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    payload = json.dumps(records, ensure_ascii=True, separators=(",", ":"), sort_keys=sort_keys)
    return hashlib.sha256(payload.encode()).hexdigest()

data = {"EXPECTED_PUBLIC_EXPORTS": sorted(name for name in vars(module) if not name.startswith("_"))}
if target.endswith("test_agent_orchestrator_public_surface.py"):
    groups = {
        "EXPECTED_EXECUTION_METHODS": ("_EXECUTION_METHOD_NAMES", "_ExecutionMethods"),
        "EXPECTED_CHAT_METHODS": ("_CHAT_METHOD_NAMES", "_ChatMethods"),
        "EXPECTED_PIPELINE_METHODS": ("_PIPELINE_METHOD_NAMES", "_PipelineMethods"),
        "EXPECTED_DASHBOARD_METHODS": ("_DASHBOARD_METHOD_NAMES", "_DashboardMethods"),
    }
    data["EXPECTED_AST_HASHES"] = {}
    for expected, (names, container) in groups.items():
        data[expected] = list(getattr(module, names))
        value = getattr(module, container)
        data["EXPECTED_AST_HASHES"][value.__name__] = container_hash(value)
elif target.endswith("test_agent_executor_public_surface.py"):
    groups = {
        "EXPECTED_RUN_METHODS": ("_RUN_METHOD_NAMES", "_RunMethods"),
        "EXPECTED_CHAT_METHODS": ("_CHAT_METHOD_NAMES", "_ChatMethods"),
        "EXPECTED_LOOP_METHODS": ("_LOOP_METHOD_NAMES", "_LoopMethods"),
    }
    data["EXPECTED_AST_HASHES"] = {}
    for expected, (names, container) in groups.items():
        data[expected] = list(getattr(module, names))
        value = getattr(module, container)
        data["EXPECTED_AST_HASHES"][value.__name__] = container_hash(value)
elif target.endswith("test_pipeline_public_surface.py"):
    for expected, actual in {
        "EXPECTED_DELIVERY_METHODS": "_DELIVERY_STAGE_METHOD_NAMES",
        "EXPECTED_ANALYSIS_METHODS": "_ANALYSIS_STAGE_METHOD_NAMES",
        "EXPECTED_PERSISTENCE_METHODS": "_PERSISTENCE_STAGE_METHOD_NAMES",
        "EXPECTED_ORCHESTRATION_METHODS": "_ORCHESTRATION_STAGE_METHOD_NAMES",
    }.items():
        data[expected] = list(getattr(module, actual))
elif target.endswith("test_analysis_stage_facade.py"):
    data["EXPECTED_ANALYSIS_METHODS"] = list(module._ANALYSIS_STAGE_METHOD_NAMES)
else:
    target_class = module.NotificationService
    data["EXPECTED_BASES"] = [base.__name__ for base in target_class.__bases__]
    groups = []
    for container_name, names_name in (
        ("_ReportSetupMethods", "_REPORT_SETUP_METHOD_NAMES"),
        ("_RoutingMethods", "_ROUTING_METHOD_NAMES"),
        ("_RenderingMethods", "_RENDERING_METHOD_NAMES"),
        ("_DispatchMethods", "_DISPATCH_METHOD_NAMES"),
    ):
        container = getattr(module, container_name)
        groups.append([
            container_name,
            names_name,
            list(getattr(module, names_name)),
            container_hash(container, sort_keys=True),
        ])
    data["EXPECTED_GROUPS"] = groups
print(json.dumps(data, sort_keys=True))
'''
    result = subprocess.run(
        [sys.executable, "-c", probe, path.as_posix()],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip()[-1200:] or result.stdout.strip()[-1200:]
        raise RefusalError(path, f"merged implementation snapshot probe failed: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"snapshot probe returned invalid JSON: {result.stdout[-500:]}") from exc


def _render_words(words: list[str]) -> str:
    lines: list[str] = []
    current = "    "
    for word in sorted(words):
        if len(current) + len(word) + 1 > 88:
            lines.append(current.rstrip())
            current = "    "
        current += word + " "
    if current.strip():
        lines.append(current.rstrip())
    body = "\n".join(lines)
    return f'frozenset(\n    """\n{body}\n    """.split()\n)'


def _render_tuple(values: list[str], indent: int = 0) -> str:
    prefix = " " * indent
    inner = "".join(f'{prefix}    {value!r},\n' for value in values)
    return f"(\n{inner}{prefix})"


def _render_value(name: str, value: Any) -> str:
    if name == "EXPECTED_PUBLIC_EXPORTS":
        return _render_words(value)
    if name == "EXPECTED_GROUPS":
        groups = []
        for container, names, methods, digest in value:
            groups.append(
                "    (\n"
                f"        {container!r},\n"
                f"        {names!r},\n"
                + "        "
                + _render_tuple(methods, indent=8).lstrip()
                + ",\n"
                f"        {digest!r},\n"
                "    ),\n"
            )
        return "(\n" + "".join(groups) + ")"
    if isinstance(value, list):
        return _render_tuple(value)
    if isinstance(value, dict):
        body = "".join(f"    {key!r}: {value[key]!r},\n" for key in sorted(value))
        return "{\n" + body + "}"
    raise TypeError(f"unsupported snapshot value for {name}: {type(value).__name__}")


def apply_snapshot_values(path: Path, text: str, values: dict[str, Any]) -> str:
    tree = ast.parse(text)
    assignments: dict[str, ast.Assign] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            assignments[node.targets[0].id] = node

    lines = text.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []
    for name, value in values.items():
        node = assignments.get(name)
        if node is None or node.end_lineno is None:
            raise RefusalError(path, f"required snapshot assignment {name} is missing")
        replacement = f"{name} = {_render_value(name, value)}\n"
        replacements.append((node.lineno - 1, node.end_lineno, replacement))
    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start:end] = [replacement]
    output = "".join(lines)
    ast.parse(output)
    return output


def resolve(
    context: ConflictContext,
    root: Path,
    snapshot_provider: Callable[[Path, Path], dict[str, Any]] = _run_snapshot_probe,
) -> str:
    if context.path not in SUPPORTED_PATHS:
        raise RefusalError(context.path, "unsupported public-surface snapshot")
    recovered = _resolve_snapshot_hunks(context)
    values = snapshot_provider(root, context.path)
    return apply_snapshot_values(context.path, recovered, values)
