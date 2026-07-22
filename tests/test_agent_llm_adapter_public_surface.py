"""Guard the compatibility surface of ``src.agent.llm_adapter``."""

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
    AGENT_LLM_FAILURE_MESSAGE AUTO_AGENT_BACKEND_ID AgentLiteLLMRouteResolution
    Any Dict GENERATION_ONLY_BACKEND_IDS GenerationError GenerationErrorCode
    Iterable LITELLM_BACKEND_ID LLMResponse LLMToolAdapter List Optional Router
    TRACE_MODEL_KEY TRACE_PROVIDER_KEY ToolCall Tuple
    apply_litellm_generation_params attach_message_hmacs
    build_provider_cache_route_context call_litellm_with_param_recovery dataclass
    extra_litellm_params extract_usage_payload field filter_prompt_cache_telemetry
    get_api_keys_for_model get_config get_configured_llm_models
    get_effective_agent_primary_model get_thinking_extra_body json litellm
    log_safe_exception logger logging normalize_litellm_usage
    normalize_prompt_cache_diagnostics_level register_fallback_model_pricing
    resolve_agent_generation_backend_id resolve_agent_litellm_route
    resolve_fallback_litellm_wire_models resolve_litellm_wire_model
    resolve_provider_cache_caps resolved_model_provider_identity
    resolved_provider_namespace sanitize_agent_diagnostic time trace_model_matches uuid
    """.split()
)

EXPECTED_SETUP_METHODS = (
    "_register_custom_model_pricing",
    "_has_channel_config",
    "_init_litellm",
    "is_available",
    "primary_provider",
)

EXPECTED_CALL_METHODS = (
    "call_with_tools",
    "call_text",
)

EXPECTED_TRANSPORT_METHODS = (
    "_get_model_provider",
    "_call_litellm_model",
    "_get_temperature",
)

EXPECTED_MESSAGE_METHODS = (
    "_convert_messages",
    "_trace_provider_for_target",
    "_parse_litellm_response",
)

EXPECTED_AST_HASHES = {
    "_SetupMethods": "02b29d573435c4d96b4e8219f7d9ebd1a58a3a962cd75cbe323ea46391a568a7",
    "_CallMethods": "9580907bc57d105dfa06ecdeab55f6e25bb3712319b3e981a8d06b462acab386",
    "_TransportMethods": "b34c0ce96c0009f96cbb5495fbfec72b5b687c816d0e6c6fc28bd4f1a32c5aba",
    "_MessageMethods": "73d1ca4581569a97f57673013b2a370d9c108760caa55c0be5057856a215e5ee",
}
EXPECTED_RETAINED_COMPLETION_AST_HASH = (
    "0e0d8a63aa6de926b3fc1f6ada43cd2ec51c74077f8651eaed62d0e07660ed66"
)

EXPECTED_SIGNATURES = {
    "_register_custom_model_pricing": "() -> None",
    "_has_channel_config": "(self) -> bool",
    "_init_litellm": "(self) -> None",
    "is_available": "(self) -> bool",
    "primary_provider": "(self) -> str",
    "call_with_tools": (
        "(self, messages: List[Dict[str, Any]], tools: List[dict], "
        "provider: Optional[str] = None, timeout: Optional[float] = None) -> "
        "src.agent.llm_adapter.LLMResponse"
    ),
    "call_text": (
        "(self, messages: List[Dict[str, Any]], *, provider: Optional[str] = None, "
        "temperature: Optional[float] = None, max_tokens: Optional[int] = None, "
        "timeout: Optional[float] = None) -> src.agent.llm_adapter.LLMResponse"
    ),
    "call_completion": (
        "(self, messages: List[Dict[str, Any]], *, tools: Optional[List[dict]] = None, "
        "provider: Optional[str] = None, temperature: Optional[float] = None, "
        "max_tokens: Optional[int] = None, timeout: Optional[float] = None) -> "
        "src.agent.llm_adapter.LLMResponse"
    ),
    "_get_model_provider": "(model: str) -> str",
    "_call_litellm_model": (
        "(self, messages: List[Dict[str, Any]], tools: List[dict], model: str, *, "
        "temperature: Optional[float] = None, max_tokens: Optional[int] = None, "
        "timeout: Optional[float] = None) -> src.agent.llm_adapter.LLMResponse"
    ),
    "_get_temperature": "(self) -> float",
    "_convert_messages": (
        "(self, messages: List[Dict[str, Any]], *, target_model: Optional[str] = None) "
        "-> List[Dict[str, Any]]"
    ),
    "_trace_provider_for_target": "(self, target_model: Optional[str]) -> str",
    "_parse_litellm_response": (
        "(self, response: Any, model: str, messages: Optional[List[Dict[str, Any]]] = None, "
        "*, model_list: Optional[List[Dict[str, Any]]] = None) -> "
        "src.agent.llm_adapter.LLMResponse"
    ),
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


def _container_ast_hash(container, method_names=None) -> str:
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
        and (method_names is None or node.name in method_names)
    ]
    payload = json.dumps(records, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _method_groups(module):
    return (
        ("_SETUP_METHOD_NAMES", "_SetupMethods", EXPECTED_SETUP_METHODS),
        ("_CALL_METHOD_NAMES", "_CallMethods", EXPECTED_CALL_METHODS),
        ("_TRANSPORT_METHOD_NAMES", "_TransportMethods", EXPECTED_TRANSPORT_METHODS),
        ("_MESSAGE_METHOD_NAMES", "_MessageMethods", EXPECTED_MESSAGE_METHODS),
    )


def test_llm_adapter_public_exports_match_pre_split_snapshot():
    module = importlib.import_module("src.agent.llm_adapter")
    actual = {name for name in vars(module) if not name.startswith("_")}
    assert actual == EXPECTED_PUBLIC_EXPORTS


def test_llm_adapter_moved_method_asts_match_pre_split_snapshot():
    module = importlib.import_module("src.agent.llm_adapter")
    containers = (
        module._SetupMethods,
        module._CallMethods,
        module._TransportMethods,
        module._MessageMethods,
    )
    assert {
        container.__name__: _container_ast_hash(container)
        for container in containers
    } == EXPECTED_AST_HASHES
    assert _container_ast_hash(
        module.LLMToolAdapter,
        method_names={"call_completion"},
    ) == EXPECTED_RETAINED_COMPLETION_AST_HASH


def test_llm_adapter_extracted_descriptors_preserve_facade_contract():
    module = importlib.import_module("src.agent.llm_adapter")
    target = module.LLMToolAdapter
    facade_globals = vars(module)

    for names_attribute, container_attribute, expected_names in _method_groups(module):
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
            assert function.__module__ == "src.agent.llm_adapter"
            assert function.__name__ == source_function.__name__
            assert function.__qualname__ == f"LLMToolAdapter.{name}"
            for global_name in _loaded_globals(function.__code__):
                assert global_name in facade_globals or hasattr(builtins, global_name)


def test_llm_adapter_signatures_type_hints_and_method_order_match_pre_split():
    module = importlib.import_module("src.agent.llm_adapter")
    expected_names = (
        EXPECTED_SETUP_METHODS
        + EXPECTED_CALL_METHODS
        + ("call_completion",)
        + EXPECTED_TRANSPORT_METHODS
        + EXPECTED_MESSAGE_METHODS
    )
    actual_names = tuple(
        name for name in vars(module.LLMToolAdapter) if name in expected_names
    )
    assert actual_names == expected_names

    functions = {
        name: _descriptor_function(module.LLMToolAdapter.__dict__[name])
        for name in expected_names
    }
    assert {
        name: str(inspect.signature(function))
        for name, function in functions.items()
    } == EXPECTED_SIGNATURES
    assert module.LLMToolAdapter.call_completion.__globals__ is vars(module)
    for function in functions.values():
        assert isinstance(typing.get_type_hints(function), dict)


def test_llm_adapter_facade_patch_seam_is_preserved(monkeypatch):
    module = importlib.import_module("src.agent.llm_adapter")
    adapter = module.LLMToolAdapter.__new__(module.LLMToolAdapter)
    adapter._config = object()
    monkeypatch.setattr(
        module,
        "get_effective_agent_primary_model",
        lambda _config: "patched-provider/test-model",
    )

    assert adapter.primary_provider == "patched-provider"


def test_llm_adapter_dataclass_registry_and_reload_ownership_stay_on_facade():
    module = importlib.import_module("src.agent.llm_adapter")
    old_adapter = module.LLMToolAdapter
    old_tool_call = module.ToolCall
    old_response = module.LLMResponse
    old_registry = module._FALLBACK_MODEL_PRICING_REGISTERED
    old_method = old_adapter.call_completion

    assert old_adapter.__module__ == "src.agent.llm_adapter"
    assert old_adapter.__init__.__globals__ is vars(module)
    assert old_tool_call.__module__ == "src.agent.llm_adapter"
    assert old_tool_call.__init__.__globals__ is vars(module)
    assert inspect.unwrap(old_tool_call.__repr__).__globals__ is vars(module)
    assert old_response.__module__ == "src.agent.llm_adapter"
    assert old_response.__init__.__globals__ is vars(module)
    assert inspect.unwrap(old_response.__repr__).__globals__ is vars(module)
    assert old_tool_call.__dataclass_fields__["provider_specific_fields"].default_factory is dict
    assert old_response.__dataclass_fields__["tool_calls"].default_factory is list
    assert old_response.__dataclass_fields__["provider_blocks"].default_factory is list
    assert old_response.__dataclass_fields__["usage"].default_factory is dict

    old_registry.add("review-sentinel")
    reloaded = importlib.reload(module)

    assert reloaded.LLMToolAdapter is not old_adapter
    assert reloaded.ToolCall is not old_tool_call
    assert reloaded.LLMResponse is not old_response
    assert reloaded._FALLBACK_MODEL_PRICING_REGISTERED is not old_registry
    assert "review-sentinel" not in reloaded._FALLBACK_MODEL_PRICING_REGISTERED
    assert reloaded.LLMToolAdapter.call_completion is not old_method
    assert reloaded.LLMToolAdapter.call_completion.__globals__ is vars(reloaded)
    assert (
        reloaded.LLMToolAdapter.call_completion.__annotations__["return"]
        is reloaded.LLMResponse
    )
    assert (
        reloaded.LLMToolAdapter.call_completion.__annotations__["return"]
        is not old_response
    )
    assert reloaded.LLMResponse.__init__.__globals__ is vars(reloaded)
