# -*- coding: utf-8 -*-
"""Security contracts for provider failure responses and logs."""

import json
import logging
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

from src.search_service import (
    AnspireSearchProvider,
    BochaSearchProvider,
    BraveSearchProvider,
    MiniMaxSearchProvider,
    SearchResponse,
    SearchService,
    SearXNGSearchProvider,
    SerpAPISearchProvider,
    TavilySearchProvider,
    _post_with_retry,
    fetch_url_content,
)
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)


def _http_failure(*, status_code: int, body: str, json_payload=None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = body
    response.headers = {"content-type": "application/json"}
    response.json.return_value = json_payload if json_payload is not None else {"message": body}
    return response


def test_bocha_http_failure_does_not_return_or_log_response_body(caplog) -> None:
    canary = "BOCHA_HTTP_BODY_CANARY"
    private_url = "https://private.example.invalid/internal/search?token=secret"
    response = _http_failure(
        status_code=500,
        body=f"provider body {canary} {private_url}",
        json_payload={"message": f"provider body {canary} {private_url}"},
    )
    caplog.set_level(logging.WARNING, logger="src.search_service")

    with patch("src.search_service._post_with_retry", return_value=response):
        result = BochaSearchProvider(["test-key"]).search("query", max_results=3)

    assert result.success is False
    assert result.error_message == "Search request failed (HTTP 500)."
    visible = json.dumps(result.__dict__, ensure_ascii=False) + "\n" + "\n".join(
        record.getMessage() for record in caplog.records
    )
    assert canary not in visible
    assert private_url not in visible
    assert "provider body" not in visible
    assert "test-key" not in visible
    assert "provider=Bocha" in visible
    assert "http_status=500" in visible
    assert "error_code=bocha_http_request_failed" in visible
    assert "error_count=1" in visible


def test_transient_retry_does_not_log_raw_exception_diagnostic(caplog) -> None:
    canary = "SEARCH_RETRY_EXCEPTION_CANARY"
    raw_path = "/Users/private-user/.config/stockpulse/retry-provider.json"
    private_url = "https://private.example.invalid/internal/search?token=secret"
    transient_error = requests.exceptions.ConnectionError(
        f"provider failed {canary} at {raw_path} via {private_url}"
    )
    response = _http_failure(status_code=500, body="bounded provider failure")
    caplog.set_level(logging.WARNING, logger="src.search_service")

    with (
        patch("src.search_service.requests.post", side_effect=[transient_error, response]),
        patch.object(_post_with_retry.retry, "sleep", return_value=None),
    ):
        result = BochaSearchProvider(["test-key"]).search("query", max_results=3)

    assert result.success is False
    visible = json.dumps(result.__dict__, ensure_ascii=False) + "\n" + "\n".join(
        record.getMessage() for record in caplog.records
    )
    assert canary not in visible
    assert raw_path not in visible
    assert private_url not in visible
    assert "provider failed" not in visible
    assert "error_code=search_post_request_retry" in visible
    assert "error_code=bocha_http_request_failed" in visible


def test_content_fetch_auxiliary_log_redacts_raw_exception_diagnostic(caplog) -> None:
    canary = "SEARCH_CONTENT_FETCH_EXCEPTION_CANARY"
    raw_path = "/Users/private-user/.config/stockpulse/content-fetch.json"
    article = MagicMock()
    article.download.side_effect = OSError(5, f"provider failed {canary}", raw_path)
    caplog.set_level(logging.DEBUG, logger="src.search_service")

    with (
        patch("src.search_service.Config", return_value=MagicMock()),
        patch("src.search_service.Article", return_value=article),
    ):
        result = fetch_url_content("https://example.com/article")

    assert result == ""
    visible = "\n".join(record.getMessage() for record in caplog.records)
    assert canary not in visible
    assert raw_path not in visible
    assert "provider failed" not in visible
    assert "error_code=search_result_content_fetch_failed" in visible


def test_other_provider_http_failures_do_not_return_or_log_response_body(caplog) -> None:
    canary = "SEARCH_HTTP_BODY_CANARY"
    private_url = "https://private.example.invalid/internal/search?token=secret"
    cases = [
        (
            AnspireSearchProvider(["anspire-key"]),
            "src.search_service._get_with_retry",
            "Anspire",
            "anspire_http_request_failed",
        ),
        (
            MiniMaxSearchProvider(["minimax-key"]),
            "src.search_service._post_with_retry",
            "MiniMax",
            "minimax_http_request_failed",
        ),
        (
            BraveSearchProvider(["brave-key"]),
            "src.search_service.requests.get",
            "Brave",
            "brave_http_request_failed",
        ),
    ]
    caplog.set_level(logging.WARNING, logger="src.search_service")

    for provider, request_target, provider_name, expected_error_code in cases:
        caplog.clear()
        response = _http_failure(
            status_code=500,
            body=f"provider body {canary} {private_url}",
            json_payload={"message": f"provider body {canary} {private_url}"},
        )
        with patch(request_target, return_value=response):
            result = provider.search("query", max_results=3)

        assert result.success is False
        assert result.error_message == "Search request failed (HTTP 500)."
        visible = json.dumps(result.__dict__, ensure_ascii=False) + "\n" + "\n".join(
            record.getMessage() for record in caplog.records
        )
        assert canary not in visible
        assert private_url not in visible
        assert "provider body" not in visible
        assert f"provider={provider_name}" in visible
        assert "http_status=500" in visible
        assert f"error_code={expected_error_code}" in visible


def test_searxng_failure_does_not_return_or_log_private_instance_details(caplog) -> None:
    canary = "SEARXNG_HTTP_BODY_CANARY"
    private_url = "https://user:password@private.example.invalid/internal"
    response = _http_failure(
        status_code=500,
        body=f"provider body {canary}",
    )
    caplog.set_level(logging.WARNING, logger="src.search_service")

    with patch("src.search_service._get_with_retry", return_value=response):
        result = SearXNGSearchProvider(base_urls=[private_url]).search(
            "query",
            max_results=3,
        )

    assert result.success is False
    assert result.error_message == "Search request failed (HTTP 500)."
    visible = json.dumps(result.__dict__, ensure_ascii=False) + "\n" + "\n".join(
        record.getMessage() for record in caplog.records
    )
    assert canary not in visible
    assert private_url not in visible
    assert "private.example.invalid" not in visible
    assert "provider body" not in visible
    assert "provider=SearXNG" in visible
    assert "http_status=500" in visible
    assert "error_code=searxng_http_request_failed" in visible


def test_sdk_provider_exceptions_are_stabilized_at_the_real_catch_boundary(caplog) -> None:
    canary = "SEARCH_SDK_EXCEPTION_CANARY"
    raw_path = "/Users/private-user/.config/stockpulse/sdk-provider.json"
    caplog.set_level(logging.ERROR, logger="src.search_service")

    tavily_client = MagicMock()
    tavily_client.search.side_effect = OSError(5, f"provider failed {canary}", raw_path)
    tavily_module = SimpleNamespace(TavilyClient=MagicMock(return_value=tavily_client))

    serpapi_search = MagicMock()
    serpapi_search.get_dict.side_effect = OSError(5, f"provider failed {canary}", raw_path)
    serpapi_module = SimpleNamespace(GoogleSearch=MagicMock(return_value=serpapi_search))

    cases = [
        (TavilySearchProvider(["tavily-key"]), "tavily", tavily_module, "tavily_search_failed"),
        (SerpAPISearchProvider(["serpapi-key"]), "serpapi", serpapi_module, "serpapi_search_failed"),
    ]

    for provider, module_name, module, expected_error_code in cases:
        caplog.clear()
        with patch.dict(sys.modules, {module_name: module}):
            result = provider.search("query", max_results=3)

        assert result.success is False
        assert result.error_message == "Search request failed."
        visible = json.dumps(result.__dict__, ensure_ascii=False) + "\n" + "\n".join(
            record.getMessage() for record in caplog.records
        )
        assert canary not in visible
        assert raw_path not in visible
        assert "provider failed" not in visible
        assert f"error_code={expected_error_code}" in visible


def test_comprehensive_intel_normalizes_provider_error_before_result_and_log(caplog) -> None:
    canary = "FINAL_AGGREGATE_ERROR_CANARY"
    private_url = "https://private.example.invalid/internal/provider"
    provider = SimpleNamespace(
        name="PrivateProvider",
        is_available=True,
        search=MagicMock(
            return_value=SearchResponse(
                query="query",
                results=[],
                provider="PrivateProvider",
                success=False,
                error_message=f"provider failed {canary} at {private_url}",
            )
        ),
    )
    service = SearchService(searxng_public_instances_enabled=False)
    service._providers = [provider]
    caplog.set_level(logging.WARNING, logger="src.search_service")

    with patch("src.search_service.time.sleep"):
        result = service.search_comprehensive_intel(
            stock_code="600519",
            stock_name="贵州茅台",
            max_searches=1,
        )

    failure = result["latest_news"]
    assert failure.success is False
    assert failure.error_message == "Search request failed."
    visible = json.dumps(failure.__dict__, ensure_ascii=False) + "\n" + "\n".join(
        record.getMessage() for record in caplog.records
    )
    assert canary not in visible
    assert private_url not in visible
    assert "provider failed" not in visible
    assert "provider=PrivateProvider" in visible
    assert "error_code=search_dimension_failed" in visible


def test_stock_news_normalizes_provider_error_before_diagnostics_and_log(caplog) -> None:
    canary = "STOCK_NEWS_PROVIDER_ERROR_CANARY"
    private_url = "https://private.example.invalid/internal/provider"
    provider = SimpleNamespace(
        name="PrivateProvider",
        is_available=True,
        search=MagicMock(
            return_value=SearchResponse(
                query="query",
                results=[],
                provider="PrivateProvider",
                success=False,
                error_message=f"provider failed {canary} at {private_url}",
            )
        ),
    )
    service = SearchService(searxng_public_instances_enabled=False)
    service._providers = [provider]
    caplog.set_level(logging.WARNING, logger="src.search_service")
    token = activate_run_diagnostic_context(
        trace_id="trace-search-error-safety",
        task_id="task-search-error-safety",
        query_id="query-search-error-safety",
        stock_code="600519",
        trigger_source="test",
    )
    try:
        result = service.search_stock_news("600519", "贵州茅台", max_results=3)
        diagnostics = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    visible = json.dumps(result.__dict__, ensure_ascii=False) + "\n" + json.dumps(
        diagnostics,
        ensure_ascii=False,
    ) + "\n" + "\n".join(record.getMessage() for record in caplog.records)
    assert canary not in visible
    assert private_url not in visible
    assert "provider failed" not in visible
    assert diagnostics["provider_runs"][0]["error_message_sanitized"] == "Search request failed."
    assert "provider=PrivateProvider" in visible
    assert "error_code=stock_news_provider_failed" in visible


def test_stock_news_records_stable_diagnostic_when_provider_raises() -> None:
    canary = "STOCK_NEWS_PROVIDER_EXCEPTION_CANARY"
    raw_path = "/Users/private-user/.config/stockpulse/search-provider.json"
    provider = SimpleNamespace(
        name="PrivateProvider",
        is_available=True,
        search=MagicMock(side_effect=OSError(5, f"provider failed {canary}", raw_path)),
    )
    service = SearchService(searxng_public_instances_enabled=False)
    service._providers = [provider]
    token = activate_run_diagnostic_context(
        trace_id="trace-search-exception-safety",
        task_id="task-search-exception-safety",
        query_id="query-search-exception-safety",
        stock_code="600519",
        trigger_source="test",
    )
    try:
        try:
            service.search_stock_news("600519", "贵州茅台", max_results=3)
        except OSError:
            pass
        else:  # pragma: no cover - preserves the existing re-raise contract
            raise AssertionError("provider exception should be re-raised")
        diagnostics = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    visible = json.dumps(diagnostics, ensure_ascii=False)
    assert canary not in visible
    assert raw_path not in visible
    assert "provider failed" not in visible
    assert diagnostics["provider_runs"][0]["error_message_sanitized"] == "Search request failed."


def test_shared_and_tavily_topic_exception_boundaries_return_stable_failure(caplog) -> None:
    canary = "SEARCH_EXCEPTION_BOUNDARY_CANARY"
    raw_path = "/Users/private-user/.config/stockpulse/search-provider.json"
    cases = [
        (
            BochaSearchProvider(["base-key"]),
            {},
            "search_provider_request_failed",
        ),
        (
            TavilySearchProvider(["topic-key"]),
            {"topic": "news"},
            "tavily_topic_search_failed",
        ),
    ]
    caplog.set_level(logging.WARNING, logger="src.search_service")

    for provider, search_kwargs, expected_error_code in cases:
        caplog.clear()
        with patch.object(
            provider,
            "_do_search",
            side_effect=OSError(5, f"provider failed {canary}", raw_path),
        ):
            result = provider.search("query", max_results=3, **search_kwargs)

        assert result.success is False
        assert result.error_message == "Search request failed."
        visible = json.dumps(result.__dict__, ensure_ascii=False) + "\n" + "\n".join(
            record.getMessage() for record in caplog.records
        )
        assert canary not in visible
        assert raw_path not in visible
        assert "provider failed" not in visible
        assert f"error_code={expected_error_code}" in visible
