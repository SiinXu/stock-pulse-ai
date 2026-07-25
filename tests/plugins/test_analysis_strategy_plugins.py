# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Runtime contract tests for plugin-provided declarative analysis strategies."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.agent.runtime_assembly as runtime_assembly
import src.config
from src.agent.protocols import AgentContext
from src.agent.skills.base import Skill
from src.agent.skills.router import SkillRouter
from src.agent.skills.skill_agent import SkillAgent
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.plugins import (
    AnalysisStrategyRegistry,
    Plugin,
    PluginContext,
    PluginManager,
    PluginManifest,
    build_analysis_strategy_extension_contract,
    build_application_extension_registry,
    validate_analysis_strategy_definition,
)


def _manifest(plugin_id: str) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": "1.0.0",
            "description": f"Analysis strategy test plugin {plugin_id}",
            "author": "StockPulse tests",
            "permissions": [],
        }
    )


def _skill(name: str, *, instructions: str | None = None) -> Skill:
    return Skill(
        name=name,
        display_name=f"Display {name}",
        description=f"Description for {name}",
        instructions=instructions or f"Instructions for {name}",
        category="framework",
        core_rules=[1, 7],
        required_tools=["get_daily_history"],
        allowed_tools=["Read"],
        aliases=[f"alias-{name}"],
        enabled=True,
        source="plugin-owned-mutable-source",
        entrypoint="plugin.py",
        bundle_dir="plugin-bundle",
        disable_model_invocation=False,
        user_invocable=True,
        default_active=False,
        default_router=True,
        default_priority=40,
        market_regimes=["sideways"],
        execution_context="fork",
        subagent_type="researcher",
        preferred_model="reviewed-model-hint",
    )


class _StrategyPlugin(Plugin):
    def __init__(
        self,
        plugin_id: str,
        definitions: tuple[Skill, ...],
        *,
        registration_ids: tuple[str, ...] | None = None,
        events: list[str] | None = None,
    ) -> None:
        super().__init__(_manifest(plugin_id))
        self.definitions = definitions
        self.registration_ids = registration_ids or tuple(
            definition.name for definition in definitions
        )
        self.events = events

    def onload(self, context: PluginContext) -> None:
        if self.events is not None:
            self.events.append(f"load:{self.manifest.id}")
        for registration_id, definition in zip(
            self.registration_ids,
            self.definitions,
            strict=True,
        ):
            context.register(
                "analysis_strategy",
                registration_id,
                definition,
                contract_version="1",
            )

    def onunload(self) -> None:
        if self.events is not None:
            self.events.append(f"unload:{self.manifest.id}")


def _config(
    *,
    agent_skill_dir: str | None = None,
    agent_skills: list[str] | None = None,
    agent_skill_routing: str = "auto",
) -> SimpleNamespace:
    return SimpleNamespace(
        agent_skill_dir=agent_skill_dir,
        agent_skills=agent_skills,
        agent_skill_routing=agent_skill_routing,
        kronos_enabled=False,
    )


def _write_yaml_skill(directory, name: str, instructions: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.yaml").write_text(
        "\n".join(
            (
                f"name: {name}",
                f"display_name: Display {name}",
                f"description: Description for {name}",
                f"instructions: {instructions}",
            )
        )
        + "\n",
        encoding="utf-8",
    )


def _write_markdown_skill(directory, name: str, instructions: str) -> None:
    bundle = directory / name
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "SKILL.md").write_text(
        "\n".join(
            (
                "---",
                f"name: {name}",
                f"description: Description for {name}",
                "---",
                instructions,
            )
        )
        + "\n",
        encoding="utf-8",
    )


def _write_external_strategy_plugin(directory, plugin_id: str, skill_name: str) -> None:
    candidate = directory / "external-analysis-strategy"
    candidate.mkdir(parents=True)
    (candidate / "manifest.json").write_text(
        json.dumps(
            {
                "id": plugin_id,
                "name": "External Analysis Strategy",
                "version": "1.0.0",
                "minAppVersion": "1.0.0",
                "description": "Registers one declarative analysis strategy",
                "author": "StockPulse tests",
                "permissions": [],
                "apiVersion": "1",
                "entrypoint": "plugin.py:Plugin",
            }
        ),
        encoding="utf-8",
    )
    (candidate / "plugin.py").write_text(
        "from src.agent.skills.base import Skill\n"
        "from src.plugins import Plugin as BasePlugin\n\n"
        "class Plugin(BasePlugin):\n"
        "    def onload(self, context):\n"
        "        definition = Skill(\n"
        f"            name={skill_name!r},\n"
        "            display_name='External Skill',\n"
        "            description='External description',\n"
        "            instructions='External instructions',\n"
        "        )\n"
        "        context.register(\n"
        "            'analysis_strategy',\n"
        f"            {skill_name!r},\n"
        "            definition,\n"
        "            contract_version='1',\n"
        "        )\n",
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _isolated_application_root_and_skill_cache():
    reset_application_services()
    cache_state = (
        runtime_assembly._SKILL_MANAGER_PROTOTYPE,
        runtime_assembly._SKILL_MANAGER_CUSTOM_DIR,
        runtime_assembly._SKILL_MANAGER_CATALOG_TOKEN,
        runtime_assembly._SKILL_MANAGER_CATALOG_GENERATION,
    )
    runtime_assembly._SKILL_MANAGER_PROTOTYPE = None
    runtime_assembly._SKILL_MANAGER_CUSTOM_DIR = runtime_assembly._SENTINEL
    runtime_assembly._SKILL_MANAGER_CATALOG_TOKEN = runtime_assembly._SENTINEL
    runtime_assembly._SKILL_MANAGER_CATALOG_GENERATION = -1
    yield
    reset_application_services()
    (
        runtime_assembly._SKILL_MANAGER_PROTOTYPE,
        runtime_assembly._SKILL_MANAGER_CUSTOM_DIR,
        runtime_assembly._SKILL_MANAGER_CATALOG_TOKEN,
        runtime_assembly._SKILL_MANAGER_CATALOG_GENERATION,
    ) = cache_state


def test_analysis_strategy_validator_accepts_only_complete_detachable_skills():
    valid = _skill("plugin-valid")
    assert validate_analysis_strategy_definition(valid) is True

    invalid_values = (
        object(),
        _skill("plugin-invalid-name"),
        _skill("plugin-empty-instructions"),
        _skill("plugin-invalid-context"),
        _skill("plugin-duplicate-tools"),
    )
    invalid_values[1].name = "not a canonical name"
    invalid_values[2].instructions = "  "
    invalid_values[3].execution_context = "host"
    invalid_values[4].required_tools = ["same", "same"]

    assert all(
        validate_analysis_strategy_definition(value) is False
        for value in invalid_values
    )


def test_plugin_skill_lifecycle_uses_detached_snapshots_and_invalidates_cache():
    events: list[str] = []
    mutable_definition = _skill(
        "plugin-lifecycle",
        instructions="Original immutable runtime instructions",
    )
    plugin = _StrategyPlugin(
        "test.analysis-lifecycle",
        (mutable_definition,),
        events=events,
    )
    services = ApplicationServices(
        config=_config(),
        builtin_plugins=(plugin,),
        plugins_dir="",
    )
    set_application_services(services)

    assert services.plugin_load_results[0].success is True
    assert services.analysis_strategy_registry is not None
    assert services.analysis_strategy_registry.generation == 1
    first = runtime_assembly.get_skill_manager()
    first_prototype = runtime_assembly._SKILL_MANAGER_PROTOTYPE
    published = first.get("plugin-lifecycle")
    assert published is not None
    assert published.instructions == "Original immutable runtime instructions"
    assert published.source == "plugin:test.analysis-lifecycle"
    assert published.enabled is False

    mutable_definition.instructions = "Mutated after registration"
    mutable_definition.required_tools.append("post_registration_mutation")
    detached = runtime_assembly.get_skill_manager().get("plugin-lifecycle")
    assert detached is not None
    assert detached.instructions == "Original immutable runtime instructions"
    assert detached.required_tools == ["get_daily_history"]

    disable_result = services.plugin_manager.disable("test.analysis-lifecycle")
    assert disable_result.success is True
    assert services.analysis_strategy_registry.generation == 2
    assert runtime_assembly.get_skill_manager().get("plugin-lifecycle") is None
    assert runtime_assembly._SKILL_MANAGER_PROTOTYPE is not first_prototype

    enable_result = services.plugin_manager.enable("test.analysis-lifecycle")
    assert enable_result.success is True
    assert services.analysis_strategy_registry.generation == 3
    reenabled = runtime_assembly.get_skill_manager().get("plugin-lifecycle")
    assert reenabled is not None
    assert reenabled.instructions == "Mutated after registration"
    assert events == [
        "load:test.analysis-lifecycle",
        "unload:test.analysis-lifecycle",
        "load:test.analysis-lifecycle",
    ]


def test_disable_removes_exact_registration_after_plugin_mutates_its_name():
    mutable_definition = _skill("plugin-exact-owner")
    plugin = _StrategyPlugin("test.analysis-exact-owner", (mutable_definition,))
    services = ApplicationServices(
        config=_config(),
        builtin_plugins=(plugin,),
        plugins_dir="",
    )
    set_application_services(services)
    assert services.plugin_load_results[0].success is True

    mutable_definition.name = "mutated-owner-name"
    result = services.plugin_manager.disable("test.analysis-exact-owner")

    assert result.success is True
    assert services.plugin_manager.registrations("analysis_strategy") == ()
    assert services.analysis_strategy_snapshot().registrations == ()


def test_duplicate_invalid_and_declarative_collisions_fail_closed(tmp_path):
    custom_dir = tmp_path / "custom"
    _write_yaml_skill(custom_dir, "custom-reserved", "Custom directory wins")
    first = _StrategyPlugin(
        "test.analysis-first",
        (_skill("plugin-duplicate"),),
    )
    duplicate = _StrategyPlugin(
        "test.analysis-duplicate",
        (_skill("plugin-duplicate"),),
    )
    builtin_collision = _StrategyPlugin(
        "test.analysis-builtin-collision",
        (_skill("bull_trend"),),
    )
    persona_collision = _StrategyPlugin(
        "test.analysis-persona-collision",
        (_skill("persona_contrarian_deep_value"),),
    )
    custom_collision = _StrategyPlugin(
        "test.analysis-custom-collision",
        (_skill("custom-reserved"),),
    )
    invalid = _StrategyPlugin(
        "test.analysis-invalid",
        (_skill("invalid-definition"),),
    )
    invalid.definitions[0].instructions = ""
    healthy = _StrategyPlugin(
        "test.analysis-healthy",
        (_skill("plugin-healthy"),),
    )
    services = ApplicationServices(
        config=_config(agent_skill_dir=str(custom_dir)),
        builtin_plugins=(
            first,
            duplicate,
            builtin_collision,
            persona_collision,
            custom_collision,
            invalid,
            healthy,
        ),
        plugins_dir="",
    )
    set_application_services(services)

    results = {
        result.plugin_id: result
        for result in services.plugin_load_results
    }
    assert results["test.analysis-first"].success is True
    assert results["test.analysis-duplicate"].error_code == (
        "extension_registration_conflict"
    )
    assert results["test.analysis-builtin-collision"].error_code == (
        "native_registration_conflict"
    )
    assert results["test.analysis-persona-collision"].error_code == (
        "native_registration_conflict"
    )
    assert results["test.analysis-custom-collision"].error_code == (
        "native_registration_conflict"
    )
    assert results["test.analysis-invalid"].error_code == (
        "extension_implementation_invalid"
    )
    assert results["test.analysis-healthy"].success is True
    catalog = runtime_assembly.get_skill_manager()
    assert catalog.get("plugin-duplicate").source == "plugin:test.analysis-first"
    assert catalog.get("plugin-healthy").source == "plugin:test.analysis-healthy"
    assert catalog.get("bull_trend").source == "builtin"
    assert catalog.get("persona_contrarian_deep_value").source == "builtin"
    assert catalog.get("custom-reserved").instructions == "Custom directory wins"


def test_custom_directory_keeps_yaml_markdown_and_builtin_override_semantics(tmp_path):
    custom_dir = tmp_path / "custom"
    _write_yaml_skill(custom_dir, "bull_trend", "Custom bull trend instructions")
    _write_markdown_skill(
        custom_dir,
        "nested-bundle",
        "Nested bundle instructions",
    )
    services = ApplicationServices(
        config=_config(agent_skill_dir=str(custom_dir)),
        plugins_dir="",
    )
    set_application_services(services)

    catalog = runtime_assembly.get_skill_manager()

    assert catalog.get("bull_trend").instructions == "Custom bull trend instructions"
    assert catalog.get("bull_trend").source != "builtin"
    assert catalog.get("nested-bundle").instructions == "Nested bundle instructions"


def test_external_directory_load_and_root_close_remove_strategy(tmp_path):
    _write_external_strategy_plugin(
        tmp_path,
        "test.external-analysis-strategy",
        "external-analysis-strategy",
    )
    services = ApplicationServices(
        config=_config(),
        plugins_dir=tmp_path,
    )
    set_application_services(services)

    assert len(services.external_plugin_results) == 1
    assert services.external_plugin_results[0].success is True
    assert len(services.plugin_load_results) == 1
    assert services.plugin_load_results[0].success is True
    assert runtime_assembly.get_skill_manager().get(
        "external-analysis-strategy"
    ).source == "plugin:test.external-analysis-strategy"

    shutdown_results = services.close()

    assert len(shutdown_results) == 1
    assert shutdown_results[0].success is True
    assert services.plugin_manager.registrations("analysis_strategy") == ()
    assert services.analysis_strategy_snapshot().registrations == ()


def test_runtime_custom_collision_excludes_plugin_until_config_path_changes(tmp_path):
    config = _config()
    services = ApplicationServices(
        config=config,
        builtin_plugins=(
            _StrategyPlugin(
                "test.analysis-dynamic-collision",
                (_skill("dynamic-collision", instructions="Plugin instructions"),),
            ),
        ),
        plugins_dir="",
    )
    set_application_services(services)
    assert runtime_assembly.get_skill_manager().get(
        "dynamic-collision"
    ).instructions == "Plugin instructions"

    custom_dir = tmp_path / "custom"
    _write_yaml_skill(custom_dir, "dynamic-collision", "Custom instructions")
    config.agent_skill_dir = str(custom_dir)
    custom_catalog = runtime_assembly.get_skill_manager()

    assert custom_catalog.get("dynamic-collision").instructions == (
        "Custom instructions"
    )
    assert len(services.plugin_manager.registrations("analysis_strategy")) == 1

    config.agent_skill_dir = None
    restored_catalog = runtime_assembly.get_skill_manager()
    assert restored_catalog.get("dynamic-collision").instructions == (
        "Plugin instructions"
    )


def test_no_argument_catalog_and_router_use_installed_root_config(monkeypatch, tmp_path):
    root_dir = tmp_path / "root-skills"
    global_dir = tmp_path / "global-skills"
    _write_yaml_skill(root_dir, "root-only", "Root-owned instructions")
    _write_yaml_skill(global_dir, "global-only", "Divergent global instructions")
    root_config = _config(
        agent_skill_dir=str(root_dir),
        agent_skills=["root-only"],
        agent_skill_routing="manual",
    )
    global_config = _config(
        agent_skill_dir=str(global_dir),
        agent_skills=["global-only"],
        agent_skill_routing="auto",
    )
    monkeypatch.setattr(src.config, "get_config", lambda: global_config)
    services = ApplicationServices(
        config=root_config,
        builtin_plugins=(
            _StrategyPlugin(
                "test.analysis-global-name",
                (_skill("global-only"),),
            ),
            _StrategyPlugin(
                "test.analysis-root-collision",
                (_skill("root-only"),),
            ),
        ),
        plugins_dir="",
    )
    set_application_services(services)

    results = {
        result.plugin_id: result
        for result in services.plugin_load_results
    }
    assert results["test.analysis-global-name"].success is True
    assert results["test.analysis-root-collision"].error_code == (
        "native_registration_conflict"
    )

    single_catalog = runtime_assembly.get_skill_manager()
    multi_catalog = SkillRouter._get_available_skills()
    specialist_skill = SkillAgent._load_skill("global-only")
    prompt_state = runtime_assembly.resolve_skill_prompt_state()
    plugin_prompt_state = runtime_assembly.resolve_skill_prompt_state(
        skills=["global-only"]
    )

    assert single_catalog.get("root-only").instructions == "Root-owned instructions"
    assert single_catalog.get("global-only").source == (
        "plugin:test.analysis-global-name"
    )
    assert {skill.name for skill in multi_catalog} == {
        skill.name for skill in single_catalog.list_skills()
    }
    assert specialist_skill is not None
    assert specialist_skill.source == "plugin:test.analysis-global-name"
    assert prompt_state.skills_to_activate == ["root-only"]
    assert "Root-owned instructions" in prompt_state.skill_instructions
    assert plugin_prompt_state.skills_to_activate == ["global-only"]
    assert "Instructions for global-only" in plugin_prompt_state.skill_instructions
    assert plugin_prompt_state.skill_manager.get("global-only").source == (
        "plugin:test.analysis-global-name"
    )
    assert SkillRouter._get_routing_mode() == "manual"
    assert SkillRouter._get_manual_skills(max_count=3) == ["root-only"]

    explicit_config = _config(
        agent_skill_dir=str(global_dir),
        agent_skills=["global-only"],
        agent_skill_routing="manual",
    )
    explicit_catalog = runtime_assembly.get_skill_manager(explicit_config)
    explicit_router = SkillRouter(
        skill_manager=explicit_catalog,
        config=explicit_config,
    )
    explicit_agent = SkillAgent(
        skill_id="global-only",
        skill_manager=explicit_catalog,
        tool_registry=object(),
        llm_adapter=object(),
    )

    assert explicit_catalog.get("root-only") is None
    assert explicit_catalog.get("global-only").instructions == (
        "Divergent global instructions"
    )
    assert explicit_catalog.get("global-only").source != (
        "plugin:test.analysis-global-name"
    )
    assert explicit_router.select_skills(AgentContext()) == ["global-only"]
    assert explicit_agent._skill is not None
    assert explicit_agent._skill.instructions == "Divergent global instructions"


def test_root_token_invalidates_equal_generation_catalogs():
    first = ApplicationServices(
        config=_config(),
        builtin_plugins=(
            _StrategyPlugin(
                "test.analysis-first-root",
                (_skill("same-generation", instructions="First root"),),
            ),
        ),
        plugins_dir="",
    )
    set_application_services(first)
    assert first.analysis_strategy_registry.generation == 1
    first_catalog = runtime_assembly.get_skill_manager()
    first_prototype = runtime_assembly._SKILL_MANAGER_PROTOTYPE
    assert first_catalog.get("same-generation").instructions == "First root"

    second = ApplicationServices(
        config=_config(),
        builtin_plugins=(
            _StrategyPlugin(
                "test.analysis-second-root",
                (_skill("same-generation", instructions="Second root"),),
            ),
        ),
        plugins_dir="",
    )
    set_application_services(second)
    assert second.analysis_strategy_registry.generation == 1
    second_catalog = runtime_assembly.get_skill_manager()

    assert second_catalog.get("same-generation").instructions == "Second root"
    assert runtime_assembly._SKILL_MANAGER_PROTOTYPE is not first_prototype


def test_supplied_plugin_manager_derives_or_rejects_analysis_registry_pair():
    native_registry = AnalysisStrategyRegistry(lambda: ())
    extension_registry = build_application_extension_registry(
        lambda: object(),
        additional_contracts={
            "analysis_strategy": build_analysis_strategy_extension_contract(
                native_registry
            )
        },
    )
    manager = PluginManager(
        application_version="3.26.3",
        registry=extension_registry,
    )

    services = ApplicationServices(
        config=_config(),
        plugin_manager=manager,
        plugins_dir="",
    )
    assert services.analysis_strategy_registry is native_registry

    mismatched_registry = AnalysisStrategyRegistry(lambda: ())
    other_manager = PluginManager(
        application_version="3.26.3",
        registry=build_application_extension_registry(
            lambda: object(),
            additional_contracts={
                "analysis_strategy": build_analysis_strategy_extension_contract(
                    native_registry
                )
            },
        ),
    )
    with pytest.raises(ValueError, match="must be paired"):
        ApplicationServices(
            config=_config(),
            plugin_manager=other_manager,
            analysis_strategy_registry=mismatched_registry,
            plugins_dir="",
        )

    manager_without_native_pair = PluginManager(
        application_version="3.26.3",
        registry=build_application_extension_registry(lambda: object()),
    )
    with pytest.raises(ValueError, match="must be paired"):
        ApplicationServices(
            config=_config(),
            plugin_manager=manager_without_native_pair,
            analysis_strategy_registry=mismatched_registry,
            plugins_dir="",
        )


def test_application_registry_preserves_report_template_validation():
    class _Template:
        template_id = "analysis-strategy-rebase-check"
        platforms = frozenset({"markdown"})

        def render(self, request):
            del request
            return "rendered"

    registry = build_application_extension_registry(lambda: object())
    template = _Template()

    handle = registry.register(
        plugin_id="test.report-template-preserved",
        extension_point="report_template",
        registration_id=template.template_id,
        implementation=template,
    )

    assert registry.get("report_template", template.template_id) is not None
    handle.unregister()
    assert registry.get("report_template", template.template_id) is None


def test_requested_plugin_skills_keep_router_maximum_of_three():
    services = ApplicationServices(
        config=_config(),
        builtin_plugins=(
            _StrategyPlugin(
                "test.analysis-router-cap",
                tuple(_skill(f"plugin-cap-{index}") for index in range(4)),
            ),
        ),
        plugins_dir="",
    )
    set_application_services(services)
    ctx = AgentContext()
    ctx.meta["skills_requested"] = [
        "plugin-cap-0",
        "plugin-cap-1",
        "plugin-cap-2",
        "plugin-cap-3",
    ]

    assert SkillRouter().select_skills(ctx) == [
        "plugin-cap-0",
        "plugin-cap-1",
        "plugin-cap-2",
    ]


def test_analysis_strategy_documentation_matches_runtime_ownership_contract():
    repository_root = Path(__file__).resolve().parents[2]
    contract = (repository_root / "docs/plugin-extension-contract.md").read_text(
        encoding="utf-8"
    )
    author_guide = (
        repository_root / "docs/analysis-strategy-plugin-authoring.md"
    ).read_text(encoding="utf-8")
    architecture = (repository_root / "docs/architecture-overview.md").read_text(
        encoding="utf-8"
    )
    strategy_readme = (repository_root / "strategies/README.md").read_text(
        encoding="utf-8"
    )

    assert "Default process definition adapter wired" in contract
    assert "must bind the exact" in contract
    assert "Contract only in this batch" not in next(
        line for line in contract.splitlines() if "| Analysis Strategies |" in line
    )
    assert "most strategy authors should use" in author_guide.lower()
    assert "it never creates a second, silently disconnected" in author_guide
    assert "custom-directory value, application-root" in author_guide
    assert "strategies/personas/" in author_guide
    assert "Enabled analysis_strategy plugins" in architecture
    assert "Analysis Strategy 插件作者指南" in strategy_readme
