"""Guard the compatibility surface of :mod:`src.agent.runner`."""

import ast
import builtins
import hashlib
import importlib
import inspect
import json
import typing
from pathlib import Path
from types import CodeType, FunctionType

from tests.litellm_stub import ensure_litellm_stub


ensure_litellm_stub()


EXPECTED_PUBLIC_EXPORTS = frozenset(
    """
    Any BoundToolSession Callable DashboardParseResult Dict
    ExecutionFenceRejected FuturesTimeoutError LLMToolAdapter List Optional
    RunLoopResult RuntimeGuardPolicy StageFailureReason StockScope
    ThreadPoolExecutor ToolCall ToolRegistry UsageRecorder annotations
    as_completed bind_runner_tool_completion_guard contextvars dataclass
    execute_runner_tool_call_via_session field get_default_usage_recorder
    has_reserved_explanation_field json log_runtime_guard_event logger logging
    normalize_report_signal_attribution parse_dashboard_json
    parse_dashboard_json_result re replace run_agent_loop
    runtime_guard_fingerprint sanitize_agent_dashboard_payload
    serialize_tool_result stream_event threading time try_parse_json uuid
    """.split()
)

EXPECTED_ALL = (
    "DashboardParseResult",
    "RunLoopResult",
    "parse_dashboard_json",
    "parse_dashboard_json_result",
    "run_agent_loop",
    "serialize_tool_result",
    "try_parse_json",
    "_build_tool_cache_key",
    "_guard_tool_stock_scope",
    "_is_non_retriable_tool_result",
    "_is_stock_scoped_tool",
    "_normalize_guard_stock_code",
    "_normalize_tool_stock_code",
)

EXPECTED_GROUPS = (
    (
        "_runner_parsing",
        "_PARSING_FUNCTION_NAMES",
        (
            "parse_dashboard_json",
            "parse_dashboard_json_result",
            "_finalize_dashboard_parse_result",
        ),
        "d84eca62e7a8af8999c262b963cf89a3ac33467c9580390be6b0ad446fa931ff",
    ),
    (
        "_runner_results",
        "_RESULT_FUNCTION_NAMES",
        (
            "_remaining_timeout_seconds",
            "_build_timeout_result",
            "_build_cancelled_result",
            "_build_budget_guard_result",
            "_build_tool_loop_result",
        ),
        "b688d887bdd0e1f40103adb9cb9cbc76038c8735123370be9993e94b25366e18",
    ),
    (
        "_runner_loop",
        "_LOOP_FUNCTION_NAMES",
        ("run_agent_loop",),
        "5a1347ced8e6f4e39f50634df06f1216ff030c8df9f83ba3dbff29eb4fce8545",
    ),
    (
        "_runner_tools",
        "_TOOL_FUNCTION_NAMES",
        ("_execute_tools",),
        "4c5160138e6335109c26fa28668c38923e7b0a24a4c5b2cebd0903b8894f276b",
    ),
)

EXPECTED_SIGNATURES = {
    "parse_dashboard_json": "(content: 'str') -> 'Optional[Dict[str, Any]]'",
    "parse_dashboard_json_result": (
        "(content: 'str') -> 'Optional[DashboardParseResult]'"
    ),
    "_finalize_dashboard_parse_result": (
        "(payload: 'Dict[str, Any]') -> 'DashboardParseResult'"
    ),
    "try_parse_json": "(text: 'str') -> 'Optional[Dict[str, Any]]'",
    "_try_repair_json": (
        "(text: 'str', repair_fn: 'Callable') -> 'Optional[Dict[str, Any]]'"
    ),
    "_remaining_timeout_seconds": (
        "(start_time: 'float', max_wall_clock_seconds: 'Optional[float]') "
        "-> 'Optional[float]'"
    ),
    "_build_timeout_result": (
        "(*, start_time: 'float', max_wall_clock_seconds: 'float', step: 'int', "
        "tool_calls_log: 'List[Dict[str, Any]]', total_tokens: 'int', "
        "provider_used: 'str', models_used: 'List[str]', "
        "messages: 'List[Dict[str, Any]]') -> 'RunLoopResult'"
    ),
    "_build_cancelled_result": (
        "(*, step: 'int', tool_calls_log: 'List[Dict[str, Any]]', "
        "total_tokens: 'int', provider_used: 'str', models_used: 'List[str]', "
        "messages: 'List[Dict[str, Any]]') -> 'RunLoopResult'"
    ),
    "_build_budget_guard_result": (
        "(*, start_time: 'float', step: 'int', "
        "tool_calls_log: 'List[Dict[str, Any]]', total_tokens: 'int', "
        "provider_used: 'str', models_used: 'List[str]', "
        "messages: 'List[Dict[str, Any]]', remaining_timeout_s: 'float', "
        "min_step_budget_s: 'float') -> 'RunLoopResult'"
    ),
    "_build_tool_loop_result": (
        "(*, step: 'int', tool_name: 'str', repeat_limit: 'int', "
        "tool_calls_log: 'List[Dict[str, Any]]', total_tokens: 'int', "
        "provider_used: 'str', models_used: 'List[str]', "
        "messages: 'List[Dict[str, Any]]') -> 'RunLoopResult'"
    ),
    "run_agent_loop": (
        "(*, messages: 'List[Dict[str, Any]]', tool_registry: 'ToolRegistry', "
        "llm_adapter: 'LLMToolAdapter', max_steps: 'int' = 10, "
        "progress_callback: 'Optional[Callable[[Dict[str, Any]], None]]' = None, "
        "thinking_labels: 'Optional[Dict[str, str]]' = None, "
        "max_wall_clock_seconds: 'Optional[float]' = None, "
        "tool_call_timeout_seconds: 'Optional[float]' = None, "
        "stock_scope: 'Optional[StockScope]' = None, "
        "emit_stage_events: 'bool' = True, "
        "cancelled_check: 'Optional[Callable[[], bool]]' = None, "
        "usage_recorder: 'Optional[UsageRecorder]' = None, "
        "runtime_guard_policy: 'Optional[RuntimeGuardPolicy]' = None) "
        "-> 'RunLoopResult'"
    ),
    "_execute_tools": (
        "(tool_calls: 'List[ToolCall]', tool_session: 'BoundToolSession', "
        "step: 'int', progress_callback: 'Optional[Callable]', "
        "tool_calls_log: 'List[Dict[str, Any]]', "
        "tool_wait_timeout_seconds: 'Optional[float]' = None) "
        "-> 'List[Dict[str, Any]]'"
    ),
}

EXPECTED_RETAINED_HELPER_AST_HASH = (
    "7e20269836fe2492cbb25356dff13ec293999574892b02e1d486dbac78143009"
)
EXPECTED_RETAINED_CLASS_AST_HASH = (
    "761e946e0551e1fa4a8a44b74be744f0de2f3ec6909730a1c62226e594ecea23"
)


def _canonical_ast(value):
    if isinstance(value, ast.AST):
        return [
            value.__class__.__name__,
            [
                [field, _canonical_ast(child)]
                for field, child in ast.iter_fields(value)
                if field != "type_params"
            ],
        ]
    if isinstance(value, list):
        return [_canonical_ast(item) for item in value]
    return value


def _definition_ast_hash(source, names, kinds) -> str:
    source_path = inspect.getsourcefile(source)
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    nodes = {
        node.name: node
        for node in tree.body
        if isinstance(node, kinds)
    }
    payload = json.dumps(
        [(name, _canonical_ast(nodes[name])) for name in names],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _loaded_globals(code: CodeType):
    import dis

    names = {
        instruction.argval
        for instruction in dis.get_instructions(code)
        if instruction.opname in {"LOAD_GLOBAL", "LOAD_NAME"}
    }
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            names.update(_loaded_globals(constant))
    return names


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


def test_runner_public_exports_match_pre_split_snapshot():
    module = importlib.import_module("src.agent.runner")

    assert {name for name in vars(module) if not name.startswith("_")} == (
        EXPECTED_PUBLIC_EXPORTS
    )
    assert tuple(module.__all__) == EXPECTED_ALL


def test_runner_definition_asts_match_pre_split_snapshot():
    module = importlib.import_module("src.agent.runner")

    for source_name, names_name, expected_names, expected_hash in EXPECTED_GROUPS:
        source_module = getattr(module, source_name)
        assert getattr(module, names_name) == expected_names
        assert _definition_ast_hash(
            source_module,
            expected_names,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ) == expected_hash

    assert _definition_ast_hash(
        module,
        ("try_parse_json", "_try_repair_json"),
        (ast.FunctionDef, ast.AsyncFunctionDef),
    ) == EXPECTED_RETAINED_HELPER_AST_HASH
    assert _definition_ast_hash(
        module,
        ("RunLoopResult", "DashboardParseResult", "_ToolCompletionFence"),
        (ast.ClassDef,),
    ) == EXPECTED_RETAINED_CLASS_AST_HASH


def test_runner_moved_functions_preserve_facade_contract():
    module = importlib.import_module("src.agent.runner")
    facade_globals = vars(module)

    for source_name, _, expected_names, _ in EXPECTED_GROUPS:
        source_module = getattr(module, source_name)
        for name in expected_names:
            function = getattr(module, name)
            source_function = getattr(source_module, name)
            assert function.__globals__ is facade_globals
            assert function.__code__ is source_function.__code__
            assert function.__defaults__ == source_function.__defaults__
            assert function.__kwdefaults__ == source_function.__kwdefaults__
            assert function.__annotations__ == source_function.__annotations__
            assert function.__closure__ == source_function.__closure__
            assert function.__dict__ == source_function.__dict__
            assert function.__doc__ == source_function.__doc__
            assert getattr(function, "__type_params__", ()) == getattr(
                source_function,
                "__type_params__",
                (),
            )
            assert function.__module__ == "src.agent.runner"
            assert function.__name__ == source_function.__name__
            assert function.__qualname__ == name
            for global_name in _loaded_globals(function.__code__):
                assert global_name in facade_globals or hasattr(
                    builtins,
                    global_name,
                )


def test_runner_signatures_annotations_and_alias_match_pre_split():
    module = importlib.import_module("src.agent.runner")

    assert {
        name: str(inspect.signature(getattr(module, name)))
        for name in EXPECTED_SIGNATURES
    } == EXPECTED_SIGNATURES
    assert module._try_parse_json is module.try_parse_json
    assert module.try_parse_json.__globals__ is vars(module)
    assert module._try_repair_json.__globals__ is vars(module)

    for name in EXPECTED_SIGNATURES:
        assert isinstance(typing.get_type_hints(getattr(module, name)), dict)


def test_runner_facade_patch_seams_are_preserved(monkeypatch):
    module = importlib.import_module("src.agent.runner")
    parsed = module.DashboardParseResult(payload={"patched": True})
    monkeypatch.setattr(
        module,
        "parse_dashboard_json_result",
        lambda _content: parsed,
    )

    assert module.parse_dashboard_json("ignored") is parsed.payload

    monkeypatch.setattr(module.time, "time", lambda: 15.0)
    assert module._remaining_timeout_seconds(10.0, 10.0) == 5.0


def test_runner_dataclass_fence_and_reload_ownership_stay_on_facade():
    module = importlib.import_module("src.agent.runner")
    old_result = module.RunLoopResult
    old_parse_result = module.DashboardParseResult
    old_fence = module._ToolCompletionFence
    old_loop = module.run_agent_loop
    old_execute = module._execute_tools
    old_labels = module._THINKING_TOOL_LABELS

    assert old_result.__module__ == "src.agent.runner"
    assert old_result.__init__.__globals__ is vars(module)
    assert inspect.unwrap(old_result.__repr__).__globals__ is vars(module)
    assert old_result.model.fget.__globals__ is vars(module)
    assert tuple(old_result.__dataclass_fields__) == (
        "success",
        "content",
        "tool_calls_log",
        "total_steps",
        "total_tokens",
        "provider",
        "models_used",
        "error",
        "failure_reason",
        "messages",
        "cancelled",
        "timed_out",
    )
    for field_name in ("tool_calls_log", "models_used", "messages"):
        assert (
            old_result.__dataclass_fields__[field_name].default_factory
            is list
        )

    assert old_parse_result.__module__ == "src.agent.runner"
    assert old_parse_result.__init__.__globals__ is vars(module)
    assert inspect.unwrap(old_parse_result.__repr__).__globals__ is vars(module)
    assert tuple(old_parse_result.__dataclass_fields__) == (
        "payload",
        "reserved_field_removed",
    )
    assert old_parse_result.__dataclass_params__.frozen is True

    for name in ("__init__", "mark_timed_out", "timed_out", "claim_completion"):
        function = _descriptor_function(old_fence.__dict__[name])
        assert isinstance(function, FunctionType)
        assert function.__globals__ is vars(module)
        assert function.__module__ == "src.agent.runner"
        assert function.__qualname__ == f"_ToolCompletionFence.{name}"

    old_labels["review-sentinel"] = "unexpected"
    first_reload = importlib.reload(module)
    first_result = first_reload.RunLoopResult
    first_parse_result = first_reload.DashboardParseResult
    first_fence = first_reload._ToolCompletionFence
    first_loop = first_reload.run_agent_loop
    first_execute = first_reload._execute_tools

    assert first_result is not old_result
    assert first_parse_result is not old_parse_result
    assert first_fence is not old_fence
    assert first_loop is not old_loop
    assert first_execute is not old_execute
    assert first_reload._THINKING_TOOL_LABELS is not old_labels
    assert "review-sentinel" not in first_reload._THINKING_TOOL_LABELS
    assert first_reload._try_parse_json is first_reload.try_parse_json
    assert first_loop.__globals__ is vars(first_reload)
    assert first_execute.__globals__ is vars(first_reload)
    assert first_loop.__annotations__["return"] == "RunLoopResult"
    assert (
        typing.get_type_hints(first_loop)["return"]
        is first_reload.RunLoopResult
    )

    second_reload = importlib.reload(first_reload)
    assert second_reload.RunLoopResult is not first_result
    assert second_reload.DashboardParseResult is not first_parse_result
    assert second_reload._ToolCompletionFence is not first_fence
    assert second_reload.run_agent_loop is not first_loop
    assert second_reload._execute_tools is not first_execute
    assert second_reload.run_agent_loop.__globals__ is vars(second_reload)
    assert second_reload.RunLoopResult.__init__.__globals__ is vars(second_reload)
    assert (
        inspect.unwrap(second_reload.DashboardParseResult.__repr__).__globals__
        is vars(second_reload)
    )
    assert (
        typing.get_type_hints(second_reload.parse_dashboard_json_result)[
            "return"
        ]
        == typing.Optional[second_reload.DashboardParseResult]
    )
