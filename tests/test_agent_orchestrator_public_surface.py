"""Guard the compatibility surface of ``src.agent.orchestrator``."""

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
    AGENT_EXECUTION_FAILURE_MESSAGE AGENT_MAX_STEPS_DEFAULT AgentContext
    AgentOrchestrator AgentRunStats AgentRuntimeFacts Any Callable
    DegradationBoundary DegradedEvent Dict ExecutionState FuturesTimeoutError
    LLMToolAdapter List NON_CRITICAL_BASE_STAGES Optional OrchestratorResult
    PipelineTerminationFact RiskOverrideApplication RuntimeGuardPolicy
    StageFailurePolicy StageFailureReason StageResult StageStatus StockScope
    StrategyEngine StrategyResultStatus TYPE_CHECKING ThreadPoolExecutor
    ToolRegistry VALID_MODES annotations build_agent_chat_market_context
    build_agent_chat_tool_registry build_agent_disagreement_summary
    build_agent_runtime_facts build_risk_override_application
    build_risk_override_plan build_visible_chat_history
    classify_result_terminal_state contextvars copy dataclass dataclass_fields
    field get_config inspect json log_runtime_guard_event log_safe_exception
    logger logging normalize_decision_signal normalize_report_language
    normalize_stage_failure_reason parse_dashboard_json re resolve_stock_scope
    run_agent_loop sanitize_agent_dashboard_payload sanitize_agent_diagnostic
    stream_event threading time
    """.split()
)

EXPECTED_EXECUTION_METHODS = (
    "_get_timeout_seconds",
    "_get_sub_agent_timeout_map",
    "_resolve_stage_timeout_seconds",
    "_build_timeout_result",
    "_build_budget_skip_result",
    "_build_cancelled_result",
    "_prepare_agent",
    "_callable_accepts_kwarg",
    "_agent_run_accepts_kwarg",
    "_commit_stage_context",
    "_execute_isolated_stage",
    "_run_stage_agent",
)

EXPECTED_CHAT_METHODS = (
    "run",
    "chat",
    "_build_chat_pipeline_context",
    "_build_multi_symbol_cancelled_result",
    "_execute_multi_symbol_chat",
    "_synthesize_multi_symbol_chat",
    "_build_multi_symbol_limitations",
    "_build_multi_symbol_fallback",
)

EXPECTED_PIPELINE_METHODS = (
    "_execute_pipeline",
    "_tool_registry_for_context",
    "_trim_agent_tool_names",
    "_build_agent_chain",
    "_build_specialist_agents",
    "_build_skill_agents",
    "_build_strategy_agents",
    "_aggregate_skill_opinions",
    "_aggregate_strategy_opinions",
    "_run_strategy_engine",
    "_apply_partition_fallback",
    "_collect_strategy_synthesis",
    "_prepare_decision_context",
    "_record_degraded_stage",
    "_record_degraded_event",
    "_record_pipeline_termination",
    "_is_non_critical_stage",
)

EXPECTED_DASHBOARD_METHODS = (
    "_build_context",
    "_fallback_summary",
    "_resolve_final_output",
    "_resolve_dashboard_payload",
    "_prepare_dashboard_payload",
    "_finalize_dashboard_payload",
    "_collect_key_levels",
    "_build_data_perspective",
    "_collect_risk_alerts",
    "_collect_positive_catalysts",
    "_latest_opinion",
    "_select_base_opinion",
    "_mark_partial_dashboard",
    "_apply_risk_override",
    "_merge_risk_warning",
)

EXPECTED_AST_HASHES = {
    "_ExecutionMethods": "c4fc99490e95e66bbcb79ca2e2196abff1024efd156205cc5898705f49e9f91b",
    "_ChatMethods": "f8365a4cd942e0b0a836c10ca11689ca157cedbd754bd061f059e149f27da3b9",
    "_PipelineMethods": "25b1e8e2031eb4f3519d996018e7eabaa97a86b19bf206f8fedeee58713d89f8",
    "_DashboardMethods": "c049531e3e4398323fa7963293fad0c03542477fa34e4b375e5159ef5c3c46a3",
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


def _container_ast_hash(container) -> str:
    source_path = inspect.getsourcefile(container)
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == container.__name__
    )
    records = [
        (
            node.name,
            ast.dump(node, annotate_fields=True, include_attributes=False),
        )
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    payload = json.dumps(records, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def test_orchestrator_public_exports_match_pre_split_snapshot():
    module = importlib.import_module("src.agent.orchestrator")
    actual = {name for name in vars(module) if not name.startswith("_")}
    assert actual == EXPECTED_PUBLIC_EXPORTS


def test_orchestrator_moved_method_asts_match_pre_split_snapshot():
    module = importlib.import_module("src.agent.orchestrator")
    containers = (
        module._ExecutionMethods,
        module._ChatMethods,
        module._PipelineMethods,
        module._DashboardMethods,
    )
    assert {
        container.__name__: _container_ast_hash(container)
        for container in containers
    } == EXPECTED_AST_HASHES


def test_orchestrator_extracted_descriptors_preserve_facade_contract():
    module = importlib.import_module("src.agent.orchestrator")
    target = module.AgentOrchestrator
    facade_globals = vars(module)
    groups = (
        ("_EXECUTION_METHOD_NAMES", "_ExecutionMethods", EXPECTED_EXECUTION_METHODS),
        ("_CHAT_METHOD_NAMES", "_ChatMethods", EXPECTED_CHAT_METHODS),
        ("_PIPELINE_METHOD_NAMES", "_PipelineMethods", EXPECTED_PIPELINE_METHODS),
        ("_DASHBOARD_METHOD_NAMES", "_DashboardMethods", EXPECTED_DASHBOARD_METHODS),
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
            assert function.__annotations__ == source_function.__annotations__
            assert function.__closure__ == source_function.__closure__
            assert function.__dict__ == source_function.__dict__
            assert function.__doc__ == source_function.__doc__
            assert getattr(function, "__type_params__", ()) == getattr(
                source_function, "__type_params__", ()
            )
            assert function.__module__ == "src.agent.orchestrator"
            assert function.__name__ == source_function.__name__
            assert function.__qualname__ == f"AgentOrchestrator.{name}"
            for global_name in _loaded_globals(function.__code__):
                assert global_name in facade_globals or hasattr(builtins, global_name)


def test_orchestrator_type_hint_resolution_matches_pre_split_contract():
    module = importlib.import_module("src.agent.orchestrator")
    moved_names = (
        EXPECTED_EXECUTION_METHODS
        + EXPECTED_CHAT_METHODS
        + EXPECTED_PIPELINE_METHODS
        + EXPECTED_DASHBOARD_METHODS
    )
    unresolved = set()
    for name in moved_names:
        function = _descriptor_function(module.AgentOrchestrator.__dict__[name])
        try:
            typing.get_type_hints(function)
        except NameError:
            unresolved.add(name)
    assert unresolved == {"run", "chat"}


def test_orchestrator_dataclass_and_reload_ownership_stay_on_facade():
    module = importlib.import_module("src.agent.orchestrator")
    old_class = module.AgentOrchestrator
    old_result = module.OrchestratorResult
    old_method = old_class._execute_pipeline

    assert old_result.__module__ == "src.agent.orchestrator"
    assert old_result.__init__.__globals__ is vars(module)

    reloaded = importlib.reload(module)

    assert reloaded.AgentOrchestrator is not old_class
    assert reloaded.OrchestratorResult is not old_result
    assert reloaded.AgentOrchestrator._execute_pipeline is not old_method
    assert reloaded.AgentOrchestrator._execute_pipeline.__globals__ is vars(reloaded)
    assert reloaded.OrchestratorResult.__module__ == "src.agent.orchestrator"
    assert reloaded.OrchestratorResult.__init__.__globals__ is vars(reloaded)
