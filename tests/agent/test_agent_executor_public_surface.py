"""Guard the compatibility surface of ``src.agent.executor``."""

import ast
import builtins
import hashlib
import importlib
import inspect
import json
import typing
from pathlib import Path
from types import CodeType

from tests.litellm_stub import ensure_litellm_stub


ensure_litellm_stub()


EXPECTED_PUBLIC_EXPORTS = frozenset(
    """
    AGENT_CHAT_FAILURE_HISTORY_SENTINEL AGENT_CHAT_FAILURE_MESSAGE
    AGENT_SYSTEM_PROMPT AgentExecutor AgentResult AgentRuntimeFacts Any
    CHAT_SYSTEM_PROMPT Callable ContextVar Dict ExecutionState
    LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT LEGACY_DEFAULT_CHAT_SYSTEM_PROMPT
    LLMToolAdapter List Optional StockScope ToolRegistry Tuple
    build_agent_chat_chip_instruction build_agent_chat_context_bundle
    build_agent_chat_market_context build_agent_chat_tool_registry
    classify_result_terminal_state dataclass extract_provider_trace_turns field
    format_daily_market_context_prompt_section format_market_phase_prompt_section
    format_market_structure_prompt_section get_config get_db
    get_market_guidelines get_market_role json log_safe_exception logger logging
    normalize_report_language parse_dashboard_json_result resolve_stock_scope
    run_agent_loop sanitize_agent_diagnostic uuid
    """.split()
)

EXPECTED_RUN_METHODS = (
    "run",
    "build_run_messages",
)

EXPECTED_CHAT_METHODS = (
    "chat",
    "_persist_provider_trace",
)

EXPECTED_LOOP_METHODS = (
    "_run_loop",
    "_build_user_message",
)

EXPECTED_AST_HASHES = {
    "_RunMethods": "f2ef3d21bd9464b3610e89b76297db046cae2cdaef6b139db8a4469aaff4f512",
    "_ChatMethods": "ad177677bf7da12c49c59ac61b187a2b05651870d60e043ccf75ee089618153b",
    "_LoopMethods": "a7762e27d59da99d7cf482b3da73b78244dd3b8c61084f84c2fee7477b9d4720",
}


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


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


def _container_ast_hash(container) -> str:
    source_path = inspect.getsourcefile(container)
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == container.__name__
    )
    records = [
        (node.name, _canonical_ast(node))
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    payload = json.dumps(records, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def test_executor_public_exports_match_pre_split_snapshot():
    module = importlib.import_module("src.agent.executor")
    actual = {name for name in vars(module) if not name.startswith("_")}
    assert actual == EXPECTED_PUBLIC_EXPORTS


def test_executor_moved_method_asts_match_pre_split_snapshot():
    module = importlib.import_module("src.agent.executor")
    containers = (
        module._RunMethods,
        module._ChatMethods,
        module._LoopMethods,
    )
    assert {
        container.__name__: _container_ast_hash(container)
        for container in containers
    } == EXPECTED_AST_HASHES


def test_executor_extracted_descriptors_preserve_facade_contract():
    module = importlib.import_module("src.agent.executor")
    target = module.AgentExecutor
    facade_globals = vars(module)
    groups = (
        ("_RUN_METHOD_NAMES", "_RunMethods", EXPECTED_RUN_METHODS),
        ("_CHAT_METHOD_NAMES", "_ChatMethods", EXPECTED_CHAT_METHODS),
        ("_LOOP_METHOD_NAMES", "_LoopMethods", EXPECTED_LOOP_METHODS),
    )

    for names_attribute, container_attribute, expected_names in groups:
        assert getattr(module, names_attribute) == expected_names
        container = getattr(module, container_attribute)
        for name in expected_names:
            descriptor = target.__dict__[name]
            source_descriptor = container.__dict__[name]
            assert descriptor.__class__ is source_descriptor.__class__
            function = _descriptor_function(descriptor)
            source_function = _descriptor_function(source_descriptor)
            assert function.__globals__ is facade_globals
            assert function.__code__ is source_function.__code__
            assert function.__defaults__ == source_function.__defaults__
            assert function.__kwdefaults__ == source_function.__kwdefaults__
            assert function.__annotations__ == inspect.get_annotations(
                source_function,
                globals=facade_globals,
                locals=facade_globals,
                eval_str=True,
            )
            assert function.__closure__ == source_function.__closure__
            assert function.__dict__ == source_function.__dict__
            assert function.__doc__ == source_function.__doc__
            assert getattr(function, "__type_params__", ()) == getattr(
                source_function, "__type_params__", ()
            )
            assert function.__module__ == "src.agent.executor"
            assert function.__name__ == source_function.__name__
            assert function.__qualname__ == f"AgentExecutor.{name}"
            for global_name in _loaded_globals(function.__code__):
                assert global_name in facade_globals or hasattr(builtins, global_name)


def test_executor_type_hints_and_method_order_match_pre_split_contract():
    module = importlib.import_module("src.agent.executor")
    expected_names = (
        EXPECTED_RUN_METHODS + EXPECTED_CHAT_METHODS + EXPECTED_LOOP_METHODS
    )
    actual_names = tuple(
        name for name in vars(module.AgentExecutor) if name in expected_names
    )
    assert actual_names == expected_names
    for name in expected_names:
        function = _descriptor_function(module.AgentExecutor.__dict__[name])
        assert isinstance(typing.get_type_hints(function), dict)


def test_executor_runtime_annotations_match_pre_split_contract():
    module = importlib.import_module("src.agent.executor")
    expected = {
        "run": {
            "task": str,
            "context": typing.Optional[typing.Dict[str, typing.Any]],
            "cancelled_check": typing.Optional[typing.Callable[[], bool]],
            "return": module.AgentResult,
        },
        "build_run_messages": {
            "task": str,
            "context": typing.Optional[typing.Dict[str, typing.Any]],
            "return": typing.Tuple[
                str,
                str,
                typing.List[typing.Dict[str, typing.Any]],
            ],
        },
        "chat": {
            "message": str,
            "session_id": str,
            "progress_callback": typing.Optional[typing.Callable],
            "context": typing.Optional[typing.Dict[str, typing.Any]],
            "cancelled_check": typing.Optional[typing.Callable[[], bool]],
            "return": module.AgentResult,
        },
        "_persist_provider_trace": {
            "session_id": str,
            "run_id": str,
            "messages": typing.List[typing.Dict[str, typing.Any]],
            "baseline_len": int,
            "user_message_id": int,
            "assistant_message_id": int,
            "return": None,
        },
        "_run_loop": {
            "messages": typing.List[typing.Dict[str, typing.Any]],
            "tool_decls": typing.List[typing.Dict[str, typing.Any]],
            "parse_dashboard": bool,
            "progress_callback": typing.Optional[typing.Callable],
            "stock_scope": typing.Optional[module.StockScope],
            "cancelled_check": typing.Optional[typing.Callable[[], bool]],
            "return": module.AgentResult,
        },
        "_build_user_message": {
            "task": str,
            "context": typing.Optional[typing.Dict[str, typing.Any]],
            "return": str,
        },
    }

    assert {
        name: _descriptor_function(module.AgentExecutor.__dict__[name]).__annotations__
        for name in expected
    } == expected


def test_executor_dataclass_contextvar_and_reload_ownership_stay_on_facade():
    module = importlib.import_module("src.agent.executor")
    old_class = module.AgentExecutor
    old_result = module.AgentResult
    old_registry = module._CHAT_TOOL_REGISTRY
    old_method = old_class.chat

    assert old_class.__module__ == "src.agent.executor"
    assert old_class.__qualname__ == "AgentExecutor"
    assert old_class.__init__.__globals__ is vars(module)
    assert old_result.__module__ == "src.agent.executor"
    assert old_result.__init__.__globals__ is vars(module)

    reloaded = importlib.reload(module)

    assert reloaded.AgentExecutor is not old_class
    assert reloaded.AgentResult is not old_result
    assert reloaded._CHAT_TOOL_REGISTRY is not old_registry
    assert reloaded.AgentExecutor.chat is not old_method
    assert reloaded.AgentExecutor.chat.__globals__ is vars(reloaded)
    assert reloaded.AgentExecutor.chat.__annotations__["return"] is reloaded.AgentResult
    assert reloaded.AgentExecutor.chat.__annotations__["return"] is not old_result
    assert reloaded.AgentResult.__module__ == "src.agent.executor"
    assert reloaded.AgentResult.__init__.__globals__ is vars(reloaded)
