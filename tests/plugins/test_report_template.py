# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Runtime wiring regressions for the ``report_template`` extension point."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.application_services as application_services
from src.analyzer import AnalysisResult
from src.config import Config
from src.notification import NotificationService
from src.plugins import (
    ExternalPluginLoader,
    Plugin,
    PLUGIN_APPLICATION_VERSION,
    PluginContext,
    PluginManager,
    PluginManifest,
    ReportRenderRequest,
)
from src.services.report_renderer import render_plugin_template


def _manifest(plugin_id: str) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": "1.0.0",
            "description": "Report template test plugin.",
            "author": "StockPulse Tests",
            "permissions": [],
        }
    )


class _Template:
    def __init__(
        self,
        template_id: str,
        platforms: frozenset[str],
        response: object,
        *,
        error: Exception | None = None,
    ) -> None:
        self.template_id = template_id
        self.platforms = platforms
        self.response = response
        self.error = error
        self.requests: list[ReportRenderRequest] = []

    def render(self, request: ReportRenderRequest) -> str | None:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if callable(self.response):
            return self.response(request)
        return self.response  # type: ignore[return-value]


class _ExplodingString(str):
    def __eq__(self, other: object) -> bool:
        raise AssertionError("string subclass comparison must not run")


class _TemplatePlugin(Plugin):
    def __init__(
        self,
        plugin_id: str,
        registrations: tuple[tuple[_Template, int], ...],
    ) -> None:
        super().__init__(_manifest(plugin_id))
        self.registrations = registrations
        self.unload_count = 0

    def onload(self, context: PluginContext) -> None:
        for template, priority in self.registrations:
            context.register(
                "report_template",
                template.template_id,
                template,
                priority=priority,
            )

    def onunload(self) -> None:
        self.unload_count += 1


def _load(
    manager: PluginManager,
    plugin_id: str,
    *registrations: tuple[_Template, int],
) -> _TemplatePlugin:
    plugin = _TemplatePlugin(plugin_id, tuple(registrations))
    assert manager.register(plugin, source="builtin").success is True
    assert manager.load(plugin_id).success is True
    return plugin


def _result() -> AnalysisResult:
    return AnalysisResult(
        code="600519",
        name="Kweichow Moutai",
        sentiment_score=72,
        trend_prediction="Bullish",
        operation_advice="Hold",
        analysis_summary="Stable outlook.",
        report_language="en",
    )


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> PluginManager:
    plugin_manager = PluginManager(application_version=PLUGIN_APPLICATION_VERSION)
    root = SimpleNamespace(plugin_manager=plugin_manager)
    monkeypatch.setattr(
        application_services,
        "get_application_services",
        lambda: root,
    )
    return plugin_manager


def test_default_contract_accepts_valid_template_and_rejects_invalid_shape(
    manager: PluginManager,
) -> None:
    valid = _Template("valid-template", frozenset({"markdown"}), "valid")
    _load(manager, "valid-plugin", (valid, 100))

    invalid = _Template("invalid-template", frozenset({"markdown"}), "invalid")
    invalid.platforms = {"markdown"}  # type: ignore[assignment]
    plugin = _TemplatePlugin("invalid-plugin", ((invalid, 100),))
    assert manager.register(plugin, source="builtin").success is True

    failed = manager.load("invalid-plugin")

    assert failed.success is False
    assert failed.error_code == "extension_implementation_invalid"
    assert [item.registration_id for item in manager.registrations("report_template")] == [
        "valid-template"
    ]


def test_duplicate_template_id_fails_closed_without_replacing_owner(
    manager: PluginManager,
) -> None:
    original = _Template("shared-template", frozenset({"markdown"}), "original")
    duplicate = _Template("shared-template", frozenset({"markdown"}), "duplicate")
    _load(manager, "original-plugin", (original, 100))
    plugin = _TemplatePlugin("duplicate-plugin", ((duplicate, 50),))
    assert manager.register(plugin, source="builtin").success is True

    failed = manager.load("duplicate-plugin")

    assert failed.success is False
    assert failed.error_code == "extension_registration_conflict"
    assert render_plugin_template("markdown", [_result()]) == "original"


def test_selection_filters_platform_and_uses_priority_then_registration_order(
    manager: PluginManager,
) -> None:
    mismatch = _Template("mismatch", frozenset({"brief"}), "not selected")
    empty = _Template("empty", frozenset({"markdown"}), "")
    winner = _Template("winner", frozenset({"markdown"}), "selected")
    declined = _Template("declined", frozenset({"markdown"}), None)
    later = _Template("later", frozenset({"markdown"}), "too late")
    _load(
        manager,
        "ordered-plugin",
        (mismatch, 0),
        (empty, 20),
        (winner, 20),
        (declined, 10),
        (later, 30),
    )

    rendered = render_plugin_template("markdown", [_result()])

    assert rendered == "selected"
    assert mismatch.requests == []
    assert len(declined.requests) == 1
    assert len(empty.requests) == 1
    assert len(winner.requests) == 1
    assert later.requests == []


def test_candidate_failures_and_invalid_results_continue_safely(
    manager: PluginManager,
    caplog: pytest.LogCaptureFixture,
) -> None:
    failing = _Template(
        "failing",
        frozenset({"markdown"}),
        None,
        error=RuntimeError("token=renderer-secret"),
    )
    invalid = _Template("invalid-result", frozenset({"markdown"}), 42)
    invalid_string = _Template(
        "invalid-string-subclass",
        frozenset({"markdown"}),
        _ExplodingString("unsafe"),
    )
    winner = _Template("winner", frozenset({"markdown"}), "safe report")
    _load(
        manager,
        "isolated-plugin",
        (failing, 1),
        (invalid, 2),
        (invalid_string, 3),
        (winner, 4),
    )
    caplog.set_level(logging.WARNING)

    rendered = render_plugin_template("markdown", [_result()])

    assert rendered == "safe report"
    assert (
        len(failing.requests)
        == len(invalid.requests)
        == len(invalid_string.requests)
        == len(winner.requests)
        == 1
    )
    assert "renderer-secret" not in caplog.text
    assert "report_template_rendering_failed" in caplog.text
    assert "report_template_result_invalid" in caplog.text


def test_request_is_normalized_and_context_is_deeply_immutable(
    manager: PluginManager,
) -> None:
    captured: list[ReportRenderRequest] = []

    def render_request(request: ReportRenderRequest) -> str:
        captured.append(request)
        with pytest.raises(TypeError):
            request.extra_context["new"] = "value"  # type: ignore[index]
        with pytest.raises(TypeError):
            request.extra_context["nested"]["new"] = "value"  # type: ignore[index]
        return "normalized"

    template = _Template(
        "request-template",
        frozenset({"markdown"}),
        render_request,
    )
    _load(manager, "request-plugin", (template, 100))
    result = _result()

    rendered = render_plugin_template(
        " MARKDOWN ",
        [result],
        report_date="2026-07-24",
        summary_only=True,
        extra_context={
            "report_language": "en",
            "source": "test",
            "nested": {"values": [1, 2]},
        },
    )

    assert rendered == "normalized"
    assert captured == template.requests
    request = captured[0]
    assert request.platform == "markdown"
    assert request.results == (result,)
    assert request.report_date == "2026-07-24"
    assert request.summary_only is True
    assert request.report_language == "en"
    assert request.extra_context["report_language"] == "en"
    assert request.extra_context["source"] == "test"
    assert request.extra_context["nested"]["values"] == (1, 2)  # type: ignore[index]


def test_disable_unloads_only_owned_template_and_updates_next_snapshot(
    manager: PluginManager,
) -> None:
    first = _Template("first-template", frozenset({"markdown"}), "first")
    second = _Template("second-template", frozenset({"markdown"}), "second")
    first_plugin = _load(manager, "first-plugin", (first, 10))
    second_plugin = _load(manager, "second-plugin", (second, 20))

    assert render_plugin_template("markdown", [_result()]) == "first"
    assert manager.disable("first-plugin").success is True
    assert render_plugin_template("markdown", [_result()]) == "second"
    assert manager.disable("second-plugin").success is True
    assert render_plugin_template("markdown", [_result()]) is None
    assert first_plugin.unload_count == second_plugin.unload_count == 1


@pytest.mark.parametrize(
    ("method_name", "platform"),
    (
        ("generate_dashboard_report", "markdown"),
        ("generate_wechat_dashboard", "wechat"),
        ("generate_brief_report", "brief"),
    ),
)
def test_aggregate_report_paths_select_plugins_before_jinja(
    manager: PluginManager,
    method_name: str,
    platform: str,
) -> None:
    template = _Template(
        "all-platforms",
        frozenset({"markdown", "wechat", "brief"}),
        lambda request: f"plugin:{request.platform}",
    )
    _load(manager, "all-platform-plugin", (template, 100))
    config = Config(stock_list=[], report_renderer_enabled=False)

    with patch("src.notification.get_config", return_value=config), patch(
        "src.services.report_renderer.render"
    ) as jinja_render:
        service = NotificationService()
        rendered = getattr(service, method_name)([_result()])

    assert rendered == f"plugin:{platform}"
    jinja_render.assert_not_called()


def test_all_declined_templates_continue_to_jinja_fallback(
    manager: PluginManager,
) -> None:
    declined = _Template("declined", frozenset({"brief"}), None)
    _load(manager, "declined-plugin", (declined, 100))
    config = Config(stock_list=[], report_renderer_enabled=True)

    with patch("src.notification.get_config", return_value=config), patch(
        "src.services.report_renderer.render",
        return_value="jinja fallback",
    ) as jinja_render:
        service = NotificationService()
        rendered = service.generate_brief_report([_result()], report_date="2026-07-24")

    assert rendered == "jinja fallback"
    jinja_render.assert_called_once()


def test_all_declined_templates_continue_to_hard_coded_fallback_when_jinja_disabled(
    manager: PluginManager,
) -> None:
    declined = _Template("declined", frozenset({"brief"}), None)
    _load(manager, "declined-plugin", (declined, 100))
    config = Config(stock_list=[], report_renderer_enabled=False)

    with patch("src.notification.get_config", return_value=config), patch(
        "src.services.report_renderer.render"
    ) as jinja_render:
        service = NotificationService()
        rendered = service.generate_brief_report([_result()], report_date="2026-07-24")

    assert "Kweichow Moutai" in rendered
    assert "600519" in rendered
    jinja_render.assert_not_called()


def test_documented_external_example_loads_and_renders(
    manager: PluginManager,
) -> None:
    examples_root = Path(__file__).resolve().parents[2] / "docs" / "examples"
    results = ExternalPluginLoader(manager).register_from_directory(examples_root)
    example = next(
        result for result in results if result.candidate == "report-template-plugin"
    )

    assert example.success is True
    assert example.plugin_id == "example-report-template"
    assert manager.load("example-report-template").success is True

    rendered = render_plugin_template(
        "markdown",
        [_result()],
        report_date="2026-07-24",
    )

    assert rendered == (
        "# Plugin report for 2026-07-24\n\n"
        "- Kweichow Moutai (600519): Hold"
    )
