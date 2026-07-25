# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Runtime wiring regressions for the ``report_template`` extension point."""

from __future__ import annotations

import concurrent.futures
import logging
import threading
from collections.abc import Iterator
from pathlib import Path
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


class _ExplodingPlatforms:
    def __contains__(self, platform: object) -> bool:
        raise RuntimeError("token=platform-secret")


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
def manager() -> PluginManager:
    plugin_manager = PluginManager(application_version=PLUGIN_APPLICATION_VERSION)
    application_services.set_application_services(
        application_services.ApplicationServices(
            plugin_manager=plugin_manager,
            plugins_dir="",
        )
    )
    return plugin_manager


@pytest.fixture(autouse=True)
def _clean_application_services() -> Iterator[None]:
    application_services.reset_application_services()
    yield
    application_services.reset_application_services()


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


def test_fallback_only_render_does_not_install_or_start_application_services() -> None:
    config = Config(stock_list=[], report_renderer_enabled=False)

    assert application_services.get_installed_application_services() is None
    with patch("src.notification.get_config", return_value=config):
        rendered = NotificationService().generate_brief_report(
            [_result()],
            report_date="2026-07-24",
        )

    assert "Kweichow Moutai" in rendered
    assert application_services.get_installed_application_services() is None


def test_fallback_only_markdown_does_not_build_history_context() -> None:
    config = Config(stock_list=[], report_renderer_enabled=False)
    service = NotificationService()

    with patch("src.notification.get_config", return_value=config), patch.object(
        service,
        "_get_history_compare_context",
        side_effect=AssertionError("history context must remain lazy"),
    ):
        rendered = service.generate_dashboard_report(
            [_result()],
            report_date="2026-07-24",
        )

    assert "Kweichow Moutai" in rendered
    assert application_services.get_installed_application_services() is None


@pytest.mark.parametrize("register_nonmatching_template", (False, True))
def test_installed_root_skips_history_without_matching_markdown_candidate(
    manager: PluginManager,
    register_nonmatching_template: bool,
) -> None:
    template = _Template("brief-only", frozenset({"brief"}), "not selected")
    if register_nonmatching_template:
        _load(manager, "brief-only-plugin", (template, 100))
    config = Config(stock_list=[], report_renderer_enabled=False)
    service = NotificationService()

    with patch("src.notification.get_config", return_value=config), patch.object(
        service,
        "_get_history_compare_context",
        side_effect=AssertionError("history context must remain lazy"),
    ):
        rendered = service.generate_dashboard_report(
            [_result()],
            report_date="2026-07-24",
        )

    assert "Kweichow Moutai" in rendered
    assert template.requests == []


def test_installed_root_report_template_is_selected() -> None:
    plugin_manager = PluginManager(application_version=PLUGIN_APPLICATION_VERSION)
    root = application_services.ApplicationServices(
        plugin_manager=plugin_manager,
        plugins_dir="",
    )
    application_services.set_application_services(root)
    template = _Template("installed-template", frozenset({"brief"}), "installed")
    _load(plugin_manager, "installed-plugin", (template, 100))

    assert application_services.get_installed_application_services() is root
    assert render_plugin_template("brief", [_result()]) == "installed"


def test_root_shutdown_excludes_template_while_onunload_is_running() -> None:
    unload_started = threading.Event()
    release_unload = threading.Event()

    class BlockingUnloadPlugin(_TemplatePlugin):
        def onunload(self) -> None:
            self.unload_count += 1
            unload_started.set()
            assert release_unload.wait(timeout=2)

    template = _Template("closing-template", frozenset({"brief"}), "closing")
    plugin = BlockingUnloadPlugin("closing-plugin", ((template, 100),))
    root = application_services.ApplicationServices(
        builtin_plugins=(plugin,),
        plugins_dir="",
    )
    application_services.set_application_services(root)
    assert root.plugin_load_results[0].success is True

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        reset_future = executor.submit(application_services.reset_application_services)
        assert unload_started.wait(timeout=2)
        assert application_services.get_installed_application_services() is root
        render_future = executor.submit(render_plugin_template, "brief", [_result()])
        try:
            assert render_future.done() is False
            assert template.requests == []
        finally:
            release_unload.set()

        reset_future.result(timeout=2)
        assert render_future.result(timeout=2) is None

    assert template.requests == []
    assert application_services.get_installed_application_services() is None


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


def test_platform_check_failure_does_not_block_later_candidate(
    manager: PluginManager,
    caplog: pytest.LogCaptureFixture,
) -> None:
    invalid = _Template(
        "invalid-platforms",
        frozenset({"markdown"}),
        "not selected",
    )
    winner = _Template("winner", frozenset({"markdown"}), "safe report")
    _load(
        manager,
        "platform-isolation-plugin",
        (invalid, 1),
        (winner, 2),
    )
    invalid.platforms = _ExplodingPlatforms()  # type: ignore[assignment]
    caplog.set_level(logging.WARNING)

    rendered = render_plugin_template("markdown", [_result()])

    assert rendered == "safe report"
    assert invalid.requests == []
    assert len(winner.requests) == 1
    assert "platform-secret" not in caplog.text
    assert "report_template_platform_check_failed" in caplog.text


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

    service = NotificationService()
    history_context = {"history_by_code": {"600519": []}}
    with patch("src.notification.get_config", return_value=config), patch(
        "src.services.report_renderer.render"
    ) as jinja_render, patch.object(
        service,
        "_get_history_compare_context",
        return_value=history_context,
    ) as build_history:
        rendered = getattr(service, method_name)([_result()])

    assert rendered == f"plugin:{platform}"
    jinja_render.assert_not_called()
    assert build_history.call_count == (1 if platform == "markdown" else 0)
    if platform == "markdown":
        assert template.requests[0].extra_context["history_by_code"] == {
            "600519": ()
        }


def test_declined_markdown_template_builds_history_once_for_jinja_fallback(
    manager: PluginManager,
) -> None:
    declined = _Template("declined-markdown", frozenset({"markdown"}), None)
    _load(manager, "declined-markdown-plugin", (declined, 100))
    config = Config(stock_list=[], report_renderer_enabled=True)
    service = NotificationService()
    history_context = {"history_by_code": {"600519": []}}

    with patch("src.notification.get_config", return_value=config), patch(
        "src.services.report_renderer.render",
        return_value="jinja fallback",
    ) as jinja_render, patch.object(
        service,
        "_get_history_compare_context",
        return_value=history_context,
    ) as build_history:
        rendered = service.generate_dashboard_report(
            [_result()],
            report_date="2026-07-24",
        )

    assert rendered == "jinja fallback"
    build_history.assert_called_once()
    jinja_render.assert_called_once()
    assert declined.requests[0].extra_context["history_by_code"] == {
        "600519": ()
    }
    jinja_context = jinja_render.call_args.kwargs["extra_context"]
    assert jinja_context["history_by_code"] is history_context["history_by_code"]
    assert jinja_context["report_language"] == "en"


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
