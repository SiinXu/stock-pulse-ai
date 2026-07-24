"""Registration and ToolSurface tests for the built-in Kronos plugin."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from src.agent.agents.technical_agent import TechnicalAgent
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
from src.plugins import PluginManager, build_agent_tool_extension_registry
from src.plugins.builtin import get_configured_builtin_plugins
from src.plugins.builtin.kronos import KronosAgentToolPlugin
from src.services.kronos_forecast_service import KRONOS_FORECAST_DISCLAIMER


def _config(weights_dir, *, enabled=True, size="mini"):
    return SimpleNamespace(
        kronos_enabled=enabled,
        kronos_model_size=size,
        kronos_weights_dir=str(weights_dir) if weights_dir is not None else None,
    )


def _write_ready_weights(root, *, size="mini"):
    tokenizer = "Kronos-Tokenizer-2k" if size == "mini" else "Kronos-Tokenizer-base"
    for directory in (f"Kronos-{size}", tokenizer):
        target = root / directory
        target.mkdir(parents=True, exist_ok=True)
        (target / "config.json").write_text("{}", encoding="utf-8")
        (target / "model.safetensors").write_bytes(b"test")
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


def test_invalid_local_weight_config_prevents_registration(tmp_path, caplog) -> None:
    weights = _write_ready_weights(tmp_path)
    (weights / "Kronos-mini" / "config.json").write_text(
        "not-json",
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

    assert manager.disable(plugin.manifest.id).success is True
    assert registry.get(KRONOS_FORECAST_TOOL_NAME) is None


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
