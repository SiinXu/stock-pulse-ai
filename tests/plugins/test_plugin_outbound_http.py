# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Local Only plugin HTTP contract: sanctioned wrapper, guard, isolation."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import src.application_services as application_services
from src.core.pipeline import StockAnalysisPipeline
from src.enums import ReportType
from src.plugins import (
    EventHookRegistration,
    OutboundPolicyError,
    Plugin,
    PluginContext,
    PluginManifest,
    plugin_safe_get,
    plugin_safe_post,
    plugin_safe_request,
)
from src.plugins.http import (
    find_unsanctioned_plugin_http,
    scan_bundled_plugin_http,
)
from src.security.outbound_policy import (
    LOCAL_ONLY_MODE_ENV,
    clear_outbound_activity_for_tests,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _clean_plugin_http_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(LOCAL_ONLY_MODE_ENV, raising=False)
    monkeypatch.delenv("OUTBOUND_HTTP_ALLOWLIST", raising=False)
    clear_outbound_activity_for_tests()
    application_services.reset_application_services()
    yield
    application_services.reset_application_services()
    clear_outbound_activity_for_tests()
    monkeypatch.delenv(LOCAL_ONLY_MODE_ENV, raising=False)


def _manifest(plugin_id: str) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": "1.0.0",
            "description": "Plugin outbound HTTP test.",
            "author": "StockPulse Tests",
            "permissions": [],
        }
    )


class _HookPlugin(Plugin):
    def __init__(
        self,
        plugin_id: str,
        hook_id: str,
        event_names: frozenset[str],
        callback,
        *,
        priority: int = 100,
    ) -> None:
        super().__init__(_manifest(plugin_id))
        self.registration = EventHookRegistration(
            hook_id=hook_id,
            event_names=event_names,
            callback=callback,
        )
        self.priority = priority

    def onload(self, context: PluginContext) -> None:
        context.register(
            "event_hook",
            self.registration.hook_id,
            self.registration,
            priority=self.priority,
        )


def _install_plugins(*plugins: Plugin):
    services = application_services.ApplicationServices(
        builtin_plugins=plugins,
        plugins_dir="",
    )
    application_services.set_application_services(services)
    return services


def _pipeline(result: object) -> StockAnalysisPipeline:
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.query_id = "analysis-task"
    pipeline.trace_id = "analysis-trace"
    pipeline.query_source = "api"
    pipeline._emit_progress = MagicMock()
    pipeline._resolve_resume_target_date = MagicMock(return_value=date(2026, 7, 24))
    pipeline.fetch_and_save_stock_data = MagicMock(return_value=(True, None))
    pipeline.analyze_stock = MagicMock(return_value=result)
    pipeline._refresh_saved_diagnostic_snapshot = MagicMock()
    return pipeline


def test_plugin_safe_helpers_are_author_exports() -> None:
    from src.plugins import PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
    import src.plugins as plugins_pkg

    for name in (
        "OutboundPolicyError",
        "plugin_safe_get",
        "plugin_safe_post",
        "plugin_safe_request",
    ):
        assert name in PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS
        assert getattr(plugins_pkg, name) is not None


def test_plugin_safe_get_blocks_non_loopback_under_local_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    with patch("src.security.outbound_policy.requests.get") as transport:
        with pytest.raises(OutboundPolicyError, match="local_only_mode_blocked") as exc_info:
            plugin_safe_get("https://api.example.com/plugin-egress")
    assert exc_info.value.reason == "local_only_mode_blocked"
    assert "LOCAL_ONLY_MODE" in str(exc_info.value)
    transport.assert_not_called()


def test_plugin_safe_request_and_post_block_non_loopback_under_local_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    with patch("src.security.outbound_policy.requests.post") as transport:
        with pytest.raises(OutboundPolicyError) as exc_info:
            plugin_safe_post("https://hooks.example.com/notify")
        assert exc_info.value.reason == "local_only_mode_blocked"
        transport.assert_not_called()
    with patch("src.security.outbound_policy.requests.request") as transport:
        with pytest.raises(OutboundPolicyError) as exc_info:
            plugin_safe_request("PUT", "https://api.tushare.pro")
        assert exc_info.value.reason == "local_only_mode_blocked"
        transport.assert_not_called()


def test_direct_requests_usage_is_detected() -> None:
    source = (
        "import requests\n"
        "\n"
        "def fetch():\n"
        "    return requests.get('https://api.example.com/feed')\n"
    )
    findings = find_unsanctioned_plugin_http(source, filename="plugin.py")
    assert findings
    assert any("unsanctioned HTTP client requests" in item for item in findings)


@pytest.mark.parametrize(
    "source",
    [
        "from urllib.request import urlopen\n\nurlopen('https://example.com')\n",
        "import urllib.request as web\n\nweb.urlopen('https://example.com')\n",
        "import httpx\n\nhttpx.get('https://example.com')\n",
        "import aiohttp\n",
        "import urllib3\n",
        "from requests import get\n\nget('https://example.com')\n",
    ],
)
def test_guard_fires_on_direct_http_clients(source: str) -> None:
    findings = find_unsanctioned_plugin_http(source, filename="bad_plugin.py")
    assert findings, source


@pytest.mark.parametrize(
    "source",
    [
        "from urllib.parse import urlparse\n\nurlparse('https://example.com')\n",
        "from src.plugins import plugin_safe_get\n\nplugin_safe_get('http://127.0.0.1:11434')\n",
        "from src.security.outbound_policy import safe_get\n",
    ],
)
def test_guard_allows_sanctioned_and_parse_only_usage(source: str) -> None:
    assert find_unsanctioned_plugin_http(source, filename="ok_plugin.py") == ()


def test_guard_fail_closed_on_syntax_error() -> None:
    findings = find_unsanctioned_plugin_http("def broken(\n", filename="broken.py")
    assert findings == ("broken.py: syntax_error",)


def test_bundled_and_example_plugins_have_no_direct_http() -> None:
    findings = scan_bundled_plugin_http(_REPOSITORY_ROOT)
    assert findings == (), findings


def test_scan_detects_direct_http_in_plugin_tree(tmp_path: Path) -> None:
    plugin = tmp_path / "examples" / "plugins" / "sneaky" / "plugin.py"
    plugin.parent.mkdir(parents=True)
    plugin.write_text(
        "import requests\n\ndef ping():\n    return requests.get('https://example.com')\n",
        encoding="utf-8",
    )
    findings = scan_bundled_plugin_http(tmp_path)
    assert any("unsanctioned HTTP client requests" in item for item in findings)


def test_blocked_plugin_http_does_not_abort_later_hooks(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    calls: list[str] = []

    def blocked_http(event) -> None:
        plugin_safe_get("https://api.example.com/plugin-egress")
        calls.append("after-http")
        del event

    def later(event) -> None:
        calls.append(event.name)

    _install_plugins(
        _HookPlugin(
            "event.http",
            "http-hook",
            frozenset({"analysis.started"}),
            blocked_http,
            priority=10,
        ),
        _HookPlugin(
            "event.later",
            "later-hook",
            frozenset({"analysis.started"}),
            later,
            priority=100,
        ),
    )

    from src.plugins.event_hooks import dispatch_analysis_event

    with patch("src.security.outbound_policy.requests.get") as transport:
        dispatch_analysis_event(
            "analysis.started",
            task_id="task-1",
            trace_id="trace-1",
            stock_code="AAPL",
            trigger_source="api",
        )
    transport.assert_not_called()
    assert calls == ["analysis.started"]
    assert "plugin_event_hook_callback_failed" in caplog.text


def test_blocked_plugin_http_does_not_abort_host_analysis(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    calls: list[str] = []

    def blocked_http(event) -> None:
        plugin_safe_get("https://api.example.com/plugin-egress")
        calls.append("after-http")
        del event

    def later(event) -> None:
        calls.append(event.name)

    _install_plugins(
        _HookPlugin(
            "event.http",
            "http-hook",
            frozenset({"analysis.started", "analysis.completed"}),
            blocked_http,
            priority=10,
        ),
        _HookPlugin(
            "event.later",
            "later-hook",
            frozenset({"analysis.started", "analysis.completed"}),
            later,
            priority=100,
        ),
    )

    succeeded = SimpleNamespace(
        code="AAPL",
        query_id="analysis-success",
        success=True,
        sentiment_score=70,
    )
    with patch("src.security.outbound_policy.requests.get") as transport:
        result = _pipeline(succeeded).process_single_stock(
            "AAPL",
            report_type=ReportType.SIMPLE,
            analysis_query_id="analysis-success",
        )
    transport.assert_not_called()
    assert result is succeeded
    assert "after-http" not in calls
    assert "analysis.started" in calls
    assert "analysis.completed" in calls
    assert "plugin_event_hook_callback_failed" in caplog.text
