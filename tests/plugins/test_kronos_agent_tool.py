"""Registration and ToolSurface tests for the built-in Kronos plugin."""

from __future__ import annotations

import json
import logging
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agent.agents.technical_agent import TechnicalAgent
from src.agent.executor import AgentExecutor
from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.stock_scope import StockScope
from src.agent.tool_surface import ToolSurface
from src.agent.tools.kronos_tools import (
    KRONOS_FORECAST_TOOL_NAME,
    build_kronos_tool,
)
from src.agent.tools.execution import ToolAccessContext
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)
from src.application_services import ApplicationServices
from src.plugins import (
    PluginManager,
    PluginRegistryError,
    build_agent_tool_extension_registry,
)
from src.plugins.builtin import get_configured_builtin_plugins
from src.plugins.builtin.kronos import KronosAgentToolPlugin
from src.services.kronos_forecast_service import (
    KRONOS_FORECAST_DISCLAIMER,
    KRONOS_MODEL_SPECS,
)


def _config(weights_dir, *, enabled=True, size="mini"):
    return SimpleNamespace(
        kronos_enabled=enabled,
        kronos_model_size=size,
        kronos_weights_dir=str(weights_dir) if weights_dir is not None else None,
    )


def _write_ready_weights(root, *, size="mini"):
    spec = KRONOS_MODEL_SPECS[size]
    tensor_header = json.dumps(
        {
            "readiness_probe": {
                "dtype": "F32",
                "shape": [1],
                "data_offsets": [0, 4],
            }
        },
        separators=(",", ":"),
    ).encode("utf-8")
    tensor_header += b" " * (-len(tensor_header) % 8)
    safetensors_payload = (
        len(tensor_header).to_bytes(8, "little")
        + tensor_header
        + b"\x00\x00\x00\x00"
    )
    for directory, config in (
        (spec.model_directory, spec.model_config),
        (spec.tokenizer_directory, spec.tokenizer_config),
    ):
        target = root / directory
        target.mkdir(parents=True, exist_ok=True)
        (target / "config.json").write_text(
            json.dumps(dict(config), sort_keys=True),
            encoding="utf-8",
        )
        (target / "model.safetensors").write_bytes(safetensors_payload)
    return root


class _FakeService:
    def __init__(self) -> None:
        self.calls = []

    def forecast(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "schema_version": "kronos-forecast-v1",
            "status": "ok",
            "stock_code": kwargs["stock_code"],
            "disclaimer": KRONOS_FORECAST_DISCLAIMER,
        }


def test_disabled_configuration_is_absent_from_builtin_catalog() -> None:
    assert get_configured_builtin_plugins(_config(None, enabled=False)) == ()


def test_technical_agent_omits_unregistered_optional_tool_without_warning(
    caplog,
) -> None:
    agent = TechnicalAgent.__new__(TechnicalAgent)
    agent.tool_registry = ToolRegistry()

    caplog.set_level(logging.WARNING)
    filtered = agent._filtered_registry()

    assert filtered.get(KRONOS_FORECAST_TOOL_NAME) is None
    assert KRONOS_FORECAST_TOOL_NAME not in "\n".join(
        record.getMessage() for record in caplog.records
    )


def test_technical_agent_includes_registered_optional_tool(tmp_path) -> None:
    tool = build_kronos_tool(
        _config(_write_ready_weights(tmp_path)),
        dependency_probe=lambda _module: True,
        service_factory=lambda _availability: _FakeService(),
    )
    assert tool is not None
    source_registry = ToolRegistry()
    source_registry.register(tool)
    agent = TechnicalAgent.__new__(TechnicalAgent)
    agent.tool_registry = source_registry

    filtered = agent._filtered_registry()

    assert filtered.get(KRONOS_FORECAST_TOOL_NAME) is tool
    assert filtered.get(KRONOS_FORECAST_TOOL_NAME).enforce_contract is True


def test_missing_dependencies_prevent_registration_with_actionable_log(
    tmp_path,
    caplog,
) -> None:
    weights = _write_ready_weights(tmp_path)
    registry = ToolRegistry()
    manager = PluginManager(
        application_version="3.26.3",
        registry=build_agent_tool_extension_registry(registry),
    )
    plugin = KronosAgentToolPlugin(
        _config(weights),
        dependency_probe=lambda module: module != "torch",
    )
    assert manager.register(plugin, source="builtin").success is True

    caplog.set_level(logging.WARNING, logger="src.agent.tools.kronos_tools")
    result = manager.load(plugin.manifest.id)

    assert result.success is True
    assert registry.get(KRONOS_FORECAST_TOOL_NAME) is None
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "dependencies_missing" in rendered
    assert "requirements-kronos.txt" in rendered


def test_missing_weights_prevent_registration_without_network_access(
    tmp_path,
    caplog,
) -> None:
    registry = ToolRegistry()
    manager = PluginManager(
        application_version="3.26.3",
        registry=build_agent_tool_extension_registry(registry),
    )
    plugin = KronosAgentToolPlugin(
        _config(tmp_path / "absent"),
        dependency_probe=lambda _module: True,
    )
    manager.register(plugin, source="builtin")

    caplog.set_level(logging.WARNING, logger="src.agent.tools.kronos_tools")
    result = manager.load(plugin.manifest.id)

    assert result.success is True
    assert registry.get(KRONOS_FORECAST_TOOL_NAME) is None
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "weights_dir_missing" in rendered
    assert "No automatic download" not in rendered
    assert "Download the official Hugging Face artifacts elsewhere" in rendered


@pytest.mark.parametrize("config_payload", ["not-json", "{}"])
def test_invalid_local_weight_config_prevents_registration(
    tmp_path,
    caplog,
    config_payload,
) -> None:
    weights = _write_ready_weights(tmp_path)
    (weights / "Kronos-mini" / "config.json").write_text(
        config_payload,
        encoding="utf-8",
    )
    registry = ToolRegistry()
    manager = PluginManager(
        application_version="3.26.3",
        registry=build_agent_tool_extension_registry(registry),
    )
    plugin = KronosAgentToolPlugin(
        _config(weights),
        dependency_probe=lambda _module: True,
    )
    manager.register(plugin, source="builtin")

    caplog.set_level(logging.WARNING, logger="src.agent.tools.kronos_tools")
    result = manager.load(plugin.manifest.id)

    assert result.success is True
    assert registry.get(KRONOS_FORECAST_TOOL_NAME) is None
    assert "weights_invalid" in "\n".join(
        record.getMessage() for record in caplog.records
    )


def test_invalid_safetensors_container_prevents_registration(tmp_path, caplog) -> None:
    weights = _write_ready_weights(tmp_path)
    (weights / "Kronos-mini" / "model.safetensors").write_bytes(b"not-safetensors")

    caplog.set_level(logging.WARNING, logger="src.agent.tools.kronos_tools")
    tool = build_kronos_tool(
        _config(weights),
        dependency_probe=lambda _module: True,
        service_factory=lambda _availability: _FakeService(),
    )

    assert tool is None
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "weights_invalid" in rendered
    assert "Kronos-mini/model.safetensors" in rendered


def test_default_service_factory_prepares_local_model_before_registration(
    tmp_path,
    monkeypatch,
) -> None:
    calls = []

    class _PreparingBackend:
        def __init__(self, **kwargs) -> None:
            calls.append(("init", kwargs))

        def prepare(self) -> None:
            calls.append(("prepare", None))

        def predict_paths(self, *_args, **_kwargs):
            raise AssertionError("inference is not part of registration")

    monkeypatch.setattr(
        "src.agent.tools.kronos_tools.OfficialKronosInferenceBackend",
        _PreparingBackend,
    )

    tool = build_kronos_tool(
        _config(_write_ready_weights(tmp_path)),
        dependency_probe=lambda _module: True,
    )

    assert tool is not None
    assert [event for event, _payload in calls] == ["init", "prepare"]


def test_local_model_prepare_failure_keeps_tool_absent(
    tmp_path,
    monkeypatch,
    caplog,
) -> None:
    class _BrokenBackend:
        def __init__(self, **_kwargs) -> None:
            pass

        def prepare(self) -> None:
            raise RuntimeError("local artifact rejected")

    monkeypatch.setattr(
        "src.agent.tools.kronos_tools.OfficialKronosInferenceBackend",
        _BrokenBackend,
    )
    caplog.set_level(logging.WARNING, logger="src.agent.tools.kronos_tools")

    tool = build_kronos_tool(
        _config(_write_ready_weights(tmp_path)),
        dependency_probe=lambda _module: True,
    )

    assert tool is None
    assert "reason=model_load_failed" in "\n".join(
        record.getMessage() for record in caplog.records
    )


def test_incomplete_state_dict_is_strictly_rejected_before_registration(
    tmp_path,
    monkeypatch,
    caplog,
) -> None:
    calls = []

    class _LoadedTokenizer:
        def eval(self) -> None:
            calls.append(("tokenizer_eval", None, None))

    class _TokenizerLoader:
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            calls.append(("tokenizer_load", path, kwargs))
            return _LoadedTokenizer()

    class _ModelLoader:
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            calls.append(("model_load", path, kwargs))
            if kwargs.get("strict") is True:
                raise RuntimeError("missing state-dict keys")
            raise AssertionError("incomplete state dict was loaded non-strictly")

    class _Predictor:
        def __init__(self, *_args, **_kwargs) -> None:
            raise AssertionError("predictor must not be built from incomplete weights")

    vendor_module = ModuleType("src.services._kronos_vendor")
    vendor_module.Kronos = _ModelLoader
    vendor_module.KronosPredictor = _Predictor
    vendor_module.KronosTokenizer = _TokenizerLoader
    monkeypatch.setitem(sys.modules, "src.services._kronos_vendor", vendor_module)
    caplog.set_level(logging.WARNING, logger="src.agent.tools.kronos_tools")

    tool = build_kronos_tool(
        _config(_write_ready_weights(tmp_path)),
        dependency_probe=lambda _module: True,
    )

    assert tool is None
    load_calls = [call for call in calls if call[0].endswith("_load")]
    assert [call[0] for call in load_calls] == ["tokenizer_load", "model_load"]
    assert all(
        call[2] == {"local_files_only": True, "strict": True}
        for call in load_calls
    )
    assert "reason=model_load_failed" in "\n".join(
        record.getMessage() for record in caplog.records
    )


def test_ready_plugin_registers_through_native_registry_and_unloads_exact_owner(
    tmp_path,
) -> None:
    weights = _write_ready_weights(tmp_path)
    fake_service = _FakeService()
    registry = ToolRegistry()
    manager = PluginManager(
        application_version="3.26.3",
        registry=build_agent_tool_extension_registry(registry),
    )
    plugin = KronosAgentToolPlugin(
        _config(weights),
        dependency_probe=lambda _module: True,
        service_factory=lambda _availability: fake_service,
    )

    assert manager.register(plugin, source="builtin").success is True
    assert manager.load(plugin.manifest.id).success is True
    registered = registry.get(KRONOS_FORECAST_TOOL_NAME)
    assert registered is not None
    assert manager.registrations("agent_tool")[0].implementation is registered
    declarations = registry.to_openai_tools()
    assert declarations[0]["function"]["name"] == KRONOS_FORECAST_TOOL_NAME

    assert manager.disable(plugin.manifest.id).success is True
    assert registry.get(KRONOS_FORECAST_TOOL_NAME) is None


def test_unload_uses_the_exact_registry_resolved_during_registration(
    tmp_path,
) -> None:
    weights = _write_ready_weights(tmp_path)
    first_registry = ToolRegistry()
    second_registry = ToolRegistry()
    current_registry = [first_registry]
    manager = PluginManager(
        application_version="3.26.3",
        registry=build_agent_tool_extension_registry(
            lambda: current_registry[0],
        ),
    )
    plugin = KronosAgentToolPlugin(
        _config(weights),
        dependency_probe=lambda _module: True,
        service_factory=lambda _availability: _FakeService(),
    )

    assert manager.register(plugin, source="builtin").success is True
    assert manager.load(plugin.manifest.id).success is True
    assert first_registry.get(KRONOS_FORECAST_TOOL_NAME) is not None

    current_registry[0] = second_registry
    assert manager.disable(plugin.manifest.id).success is True

    assert first_registry.get(KRONOS_FORECAST_TOOL_NAME) is None
    assert second_registry.get(KRONOS_FORECAST_TOOL_NAME) is None


@pytest.mark.parametrize(
    ("parameters", "handler"),
    [
        (
            [ToolParameter(name="value", type="integer", description="Value")],
            lambda value, **extra: (value, extra),
        ),
        (
            [
                ToolParameter(
                    name="value",
                    type="integer",
                    description="Value",
                    required=False,
                    default=1,
                )
            ],
            lambda value=2: value,
        ),
        (
            [ToolParameter(name="value", type="integer", description="Value")],
            lambda value, hidden=None: (value, hidden),
        ),
    ],
)
def test_registration_rejects_handler_schema_drift(parameters, handler) -> None:
    native_registry = ToolRegistry()
    extension_registry = build_agent_tool_extension_registry(native_registry)
    tool = ToolDefinition(
        name="schema_drift",
        description="Invalid plugin tool",
        parameters=parameters,
        handler=handler,
        policy=ToolPolicy.declared(read_only=True),
        enforce_contract=True,
    )

    with pytest.raises(
        PluginRegistryError,
        match="extension_implementation_invalid",
    ):
        extension_registry.register(
            plugin_id="test.schema-drift",
            extension_point="agent_tool",
            registration_id=tool.name,
            implementation=tool,
        )

    assert native_registry.get(tool.name) is None


@pytest.mark.parametrize("tool_name", ["provider.tool", "x" * 65])
def test_registration_rejects_nonportable_provider_tool_names(tool_name) -> None:
    native_registry = ToolRegistry()
    extension_registry = build_agent_tool_extension_registry(native_registry)
    tool = ToolDefinition(
        name=tool_name,
        description="Nonportable plugin tool name",
        parameters=[],
        handler=lambda: None,
        policy=ToolPolicy.declared(read_only=True),
        enforce_contract=True,
    )

    with pytest.raises(
        PluginRegistryError,
        match="extension_implementation_invalid",
    ):
        extension_registry.register(
            plugin_id="test.nonportable-name",
            extension_point="agent_tool",
            registration_id=tool.name,
            implementation=tool,
        )

    assert native_registry.to_openai_tools() == []


@pytest.mark.parametrize(
    ("parameter", "handler"),
    [
        (
            ToolParameter(
                name="value",
                type="integer",
                description="Value",
                required=False,
                default=2,
                maximum=1,
            ),
            lambda value=2: value,
        ),
        (
            ToolParameter(
                name="value",
                type="integer",
                description="Value",
                required=False,
                default="2",
            ),
            lambda value="2": value,
        ),
        (
            ToolParameter(
                name="value",
                type="string",
                description="Value",
                required=False,
                default="base",
                enum=["mini"],
            ),
            lambda value="base": value,
        ),
        (
            ToolParameter(
                name="value",
                type="integer",
                description="Value",
                enum=["1"],
            ),
            lambda value: value,
        ),
        (
            ToolParameter(
                name="value",
                type="object",
                description="Value",
                required=False,
                default={1: "silently-stringified-key"},
            ),
            lambda value={1: "silently-stringified-key"}: value,
        ),
        (
            ToolParameter(
                name="value",
                type="array",
                description="Value",
                required=False,
                default=[{"nested": ("tuple",)}],
            ),
            lambda value=[{"nested": ("tuple",)}]: value,
        ),
    ],
)
def test_registration_rejects_defaults_and_enum_values_outside_schema(
    parameter,
    handler,
) -> None:
    native_registry = ToolRegistry()
    extension_registry = build_agent_tool_extension_registry(native_registry)
    tool = ToolDefinition(
        name="invalid_parameter_value",
        description="Invalid plugin parameter value",
        parameters=[parameter],
        handler=handler,
        policy=ToolPolicy.declared(read_only=True),
        enforce_contract=True,
    )

    with pytest.raises(
        PluginRegistryError,
        match="extension_implementation_invalid",
    ):
        extension_registry.register(
            plugin_id="test.invalid-parameter-value",
            extension_point="agent_tool",
            registration_id=tool.name,
            implementation=tool,
        )

    assert native_registry.get(tool.name) is None


def test_registration_requires_stock_scoped_identity_parameter() -> None:
    native_registry = ToolRegistry()
    extension_registry = build_agent_tool_extension_registry(native_registry)
    tool = ToolDefinition(
        name="optional_stock_identity",
        description="Invalid optional stock identity",
        parameters=[
            ToolParameter(
                name="stock_code",
                type="string",
                description="Stock code",
                required=False,
                default="AAPL",
            )
        ],
        handler=lambda stock_code="AAPL": {"stock_code": stock_code},
        policy=ToolPolicy.declared(
            read_only=True,
            scope_dimensions=["stock"],
        ),
        enforce_contract=True,
    )

    with pytest.raises(
        PluginRegistryError,
        match="extension_implementation_invalid",
    ):
        extension_registry.register(
            plugin_id="test.optional-stock-identity",
            extension_point="agent_tool",
            registration_id=tool.name,
            implementation=tool,
        )

    assert native_registry.get(tool.name) is None


def test_registration_requires_native_contract_enforcement() -> None:
    native_registry = ToolRegistry()
    extension_registry = build_agent_tool_extension_registry(native_registry)
    tool = ToolDefinition(
        name="permissive_tool",
        description="Permissive plugin tool",
        parameters=[
            ToolParameter(name="value", type="integer", description="Value")
        ],
        handler=lambda value: value,
        policy=ToolPolicy.declared(read_only=True),
    )

    with pytest.raises(
        PluginRegistryError,
        match="extension_implementation_invalid",
    ):
        extension_registry.register(
            plugin_id="test.permissive",
            extension_point="agent_tool",
            registration_id=tool.name,
            implementation=tool,
        )

    assert native_registry.get(tool.name) is None


def test_application_services_uses_the_same_native_registry_for_builtin_tool(
    tmp_path,
    monkeypatch,
) -> None:
    weights = _write_ready_weights(tmp_path)
    fake_service = _FakeService()
    registry = ToolRegistry()
    plugin = KronosAgentToolPlugin(
        _config(weights),
        dependency_probe=lambda _module: True,
        service_factory=lambda _availability: fake_service,
    )
    monkeypatch.setattr(
        "src.agent.runtime_assembly.get_tool_registry",
        lambda: registry,
    )
    services = ApplicationServices(
        config=_config(weights),
        builtin_plugins=(plugin,),
        plugins_dir="",
    )

    results = services.start_plugins()

    assert results[0].success is True
    assert registry.get(KRONOS_FORECAST_TOOL_NAME) is not None
    services.close()
    assert registry.get(KRONOS_FORECAST_TOOL_NAME) is None


def test_plugin_cannot_overwrite_an_existing_builtin_tool(tmp_path) -> None:
    weights = _write_ready_weights(tmp_path)
    registry = ToolRegistry()
    existing = ToolDefinition(
        name=KRONOS_FORECAST_TOOL_NAME,
        description="Existing core tool",
        parameters=[
            ToolParameter(
                name="stock_code",
                type="string",
                description="Stock code",
            )
        ],
        handler=lambda stock_code: {"stock_code": stock_code},
        policy=ToolPolicy.declared(
            read_only=True,
            permissions=["market_data:read"],
            scope_dimensions=["stock"],
        ),
    )
    registry.register(existing)
    manager = PluginManager(
        application_version="3.26.3",
        registry=build_agent_tool_extension_registry(registry),
    )
    plugin = KronosAgentToolPlugin(
        _config(weights),
        dependency_probe=lambda _module: True,
        service_factory=lambda _availability: _FakeService(),
    )
    manager.register(plugin, source="builtin")

    result = manager.load(plugin.manifest.id)

    assert result.success is False
    assert result.error_code == "native_registration_conflict"
    assert registry.get(KRONOS_FORECAST_TOOL_NAME) is existing


def test_real_tool_surface_rejects_bad_code_and_window_before_handler(
    tmp_path,
) -> None:
    weights = _write_ready_weights(tmp_path)
    fake_service = _FakeService()
    tool = build_kronos_tool(
        _config(weights),
        dependency_probe=lambda _module: True,
        service_factory=lambda _availability: fake_service,
    )
    assert tool is not None
    registry = ToolRegistry()
    registry.register(tool)
    surface = ToolSurface(registry)
    context = ToolAccessContext(
        stock_scope=StockScope(
            expected_stock_code="600519",
            allowed_stock_codes={"600519"},
        )
    )

    invalid_code = surface.execute_tool(
        KRONOS_FORECAST_TOOL_NAME,
        {"stock_code": "../600519", "lookback_days": 30, "horizon_days": 5},
        context,
    )
    oversized = surface.execute_tool(
        KRONOS_FORECAST_TOOL_NAME,
        {"stock_code": "600519", "lookback_days": 513, "horizon_days": 5},
        context,
    )

    assert invalid_code["error"]["code"] == "invalid_arguments"
    assert "required format" in invalid_code["error"]["message"]
    assert oversized["error"]["code"] == "invalid_arguments"
    assert "<= 512" in oversized["error"]["message"]
    assert fake_service.calls == []


def test_ready_tool_executes_with_structured_disclaimer_and_bounded_schema(
    tmp_path,
) -> None:
    weights = _write_ready_weights(tmp_path)
    fake_service = _FakeService()
    tool = build_kronos_tool(
        _config(weights),
        dependency_probe=lambda _module: True,
        service_factory=lambda _availability: fake_service,
    )
    assert tool is not None
    registry = ToolRegistry()
    registry.register(tool)
    surface = ToolSurface(registry)

    descriptor = surface.list_tools("public")[0]
    properties = descriptor["parameters"]["properties"]
    assert properties["stock_code"]["pattern"]
    assert properties["lookback_days"]["minimum"] == 30
    assert properties["lookback_days"]["maximum"] == 512
    assert properties["horizon_days"]["minimum"] == 1
    assert properties["horizon_days"]["maximum"] == 30
    assert descriptor["parameters"]["additionalProperties"] is False

    result = surface.execute_tool(
        KRONOS_FORECAST_TOOL_NAME,
        {"stock_code": "600519", "lookback_days": 30, "horizon_days": 5},
        ToolAccessContext(
            stock_scope=StockScope(
                expected_stock_code="600519",
                allowed_stock_codes={"600519"},
            )
        ),
    )

    assert result["ok"] is True
    assert result["result"]["schema_version"] == "kronos-forecast-v1"
    assert result["result"]["disclaimer"] == KRONOS_FORECAST_DISCLAIMER
    assert fake_service.calls == [
        {
            "stock_code": "600519",
            "lookback_days": 30,
            "horizon_days": 5,
        }
    ]


def test_single_agent_run_executes_kronos_with_frozen_context_scope(tmp_path) -> None:
    fake_service = _FakeService()
    tool = build_kronos_tool(
        _config(_write_ready_weights(tmp_path)),
        dependency_probe=lambda _module: True,
        service_factory=lambda _availability: fake_service,
    )
    assert tool is not None
    registry = ToolRegistry()
    registry.register(tool)
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="kronos-1",
                    name=KRONOS_FORECAST_TOOL_NAME,
                    arguments={
                        "stock_code": "600519",
                        "lookback_days": 30,
                        "horizon_days": 5,
                    },
                )
            ],
            usage={"total_tokens": 3},
            provider="openai",
        ),
        LLMResponse(
            content=json.dumps({"decision_type": "hold", "stock_name": "test"}),
            tool_calls=[],
            usage={"total_tokens": 3},
            provider="openai",
        ),
    ]

    result = AgentExecutor(registry, adapter, max_steps=3).run(
        "Analyze stock 600519",
        context={"stock_code": "600519"},
    )

    assert result.success is True
    assert result.tool_calls_log[0]["success"] is True
    assert fake_service.calls == [
        {
            "stock_code": "600519",
            "lookback_days": 30,
            "horizon_days": 5,
        }
    ]
