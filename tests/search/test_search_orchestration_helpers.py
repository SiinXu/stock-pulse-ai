"""Behavior coverage for public search orchestration and cache helpers."""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta, timezone

import pytest

import src.search_service as search_module
from src.search_service import SearchResponse, SearchResult, SearchService


def _response(
    *,
    query: str = "query",
    provider: str = "stub",
    success: bool = True,
    results: list[SearchResult] | None = None,
    error_message: str | None = None,
) -> SearchResponse:
    return SearchResponse(
        query=query,
        results=list(results or []),
        provider=provider,
        success=success,
        error_message=error_message,
    )


def _result(
    title: str,
    *,
    url: str,
    snippet: str = "Detailed company update with enough context.",
    published_date: str | None = None,
) -> SearchResult:
    return SearchResult(
        title=title,
        snippet=snippet,
        url=url,
        source="Example News",
        published_date=published_date,
        relevance_score=91,
        relevance_category="direct_company_news",
        relevance_reasons=["title identity match"],
    )


def _service(providers=()) -> SearchService:
    service = object.__new__(SearchService)
    service._providers = list(providers)
    service.news_max_age_days = 3
    service.news_strategy_profile = "short"
    service._cache = {}
    service._cache_ttl = 60
    service._cache_lock = threading.Lock()
    service._cache_inflight = {}
    return service


class _Provider:
    def __init__(self, name: str, outcomes, *, available: bool = True):
        self.name = name
        self.is_available = available
        self._outcomes = list(outcomes)
        self.calls = []

    def search(self, query, max_results=5, **kwargs):
        self.calls.append((query, max_results, kwargs))
        index = min(len(self.calls) - 1, len(self._outcomes) - 1)
        outcome = self._outcomes[index]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_public_format_batch_and_combined_helpers(monkeypatch):
    service = _service()
    rich_result = _result(
        "Apple publishes quarterly results",
        url="https://example.com/apple",
        published_date="2026-08-04",
    )
    short_result = _result(
        "Apple update",
        url="https://example.com/apple-short",
        snippet="Short update",
    )
    rich_response = _response(results=[rich_result, short_result])
    empty_response = _response(provider="empty", success=False)

    report = service.format_intel_report(
        {"latest_news": rich_response, "risk_check": empty_response},
        "Apple",
    )
    assert "Apple 情报搜索结果" in report
    assert "score=91" in report
    assert "未找到相关信息" in report

    sleeps = []
    monkeypatch.setattr(search_module.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        service,
        "search_stock_news",
        lambda code, name, max_results: _response(query=f"{code}:{name}:{max_results}"),
    )
    batched = service.batch_search(
        [{"code": "AAPL", "name": "Apple"}, {"code": "MSFT", "name": "Microsoft"}],
        max_results_per_stock=2,
        delay_between=0.25,
    )
    assert list(batched) == ["AAPL", "MSFT"]
    assert sleeps == [0.25]

    monkeypatch.setattr(service, "search_stock_news", lambda *args, **kwargs: rich_response)
    monkeypatch.setattr(
        service,
        "search_stock_price_fallback",
        lambda *args, **kwargs: empty_response,
    )
    combined = service.search_stock_with_enhanced_fallback(
        "AAPL",
        "Apple",
        include_news=True,
        include_price=True,
        max_results=2,
    )
    assert combined == {"news": rich_response, "price": empty_response}

    assert "未找到相关信息" in service.format_price_search_context(empty_response)
    price_context = service.format_price_search_context(rich_response)
    assert "Example News" in price_context
    assert "2026-08-04" in price_context


def test_enhanced_price_fallback_aggregates_and_deduplicates(monkeypatch):
    duplicate = _result("Duplicate", url="https://example.com/duplicate")
    first = _result("First", url="https://example.com/first")
    second = _result("Second", url="https://example.com/second")
    unavailable = _Provider("unavailable", [], available=False)
    raising = _Provider("raising", [RuntimeError("provider failed")])
    empty = _Provider("empty", [_response(success=False)])
    success = _Provider(
        "success",
        [
            _response(results=[first, duplicate]),
            _response(results=[duplicate, second]),
            _response(results=[duplicate]),
        ],
    )
    service = _service([unavailable, raising, empty, success])
    logged = []
    sleeps = []
    monkeypatch.setattr(search_module, "log_safe_exception", lambda *a, **k: logged.append(k))
    monkeypatch.setattr(search_module, "exception_chain_redaction_values", lambda exc: ())
    monkeypatch.setattr(search_module.time, "sleep", sleeps.append)

    response = service.search_stock_price_fallback(
        "AAPL",
        "Apple",
        max_attempts=3,
        max_results=3,
    )

    assert response.success is True
    assert [item.url for item in response.results] == [
        "https://example.com/first",
        "https://example.com/duplicate",
        "https://example.com/second",
    ]
    assert response.provider == "success"
    assert len(logged) == 3
    assert sleeps == [0.5, 0.5]
    assert "stock price today" in success.calls[0][0]


def test_enhanced_price_fallback_unavailable_and_empty_paths(monkeypatch):
    unavailable = _service()
    response = unavailable.search_stock_price_fallback("600519", "贵州茅台")
    assert response.success is False
    assert response.error_message == "未配置搜索能力"

    empty_provider = _Provider("empty", [_response(success=False)])
    configured = _service([empty_provider])
    monkeypatch.setattr(search_module.time, "sleep", lambda _seconds: None)
    response = configured.search_stock_price_fallback(
        "600519",
        "贵州茅台",
        max_attempts=1,
    )
    assert response.success is False
    assert response.error_message == "增强搜索未找到相关信息"
    assert "今日 股价" in empty_provider.calls[0][0]


def test_event_search_uses_alias_and_provider_fallback():
    failed = _Provider("failed", [_response(success=False)])
    success_response = _response(query="provider-result")
    success = _Provider("success", [success_response])
    service = _service([_Provider("off", [], available=False), failed, success])

    response = service.search_stock_events("AAPL.US", "苹果", event_types=None)

    assert response is success_response
    assert failed.calls[0][0].startswith("Apple Inc. (")
    assert "earnings report" in failed.calls[0][0]


def test_search_stock_news_cache_and_terminal_fallback_paths(monkeypatch):
    cached = _response(provider="cache", results=[_result("Cached", url="https://cache")])
    diagnostics = []

    direct = _service()
    monkeypatch.setattr(direct, "_get_cached_or_reserve", lambda _key: (cached, False, None))
    monkeypatch.setattr(direct, "_record_news_search_run", lambda **kwargs: diagnostics.append(kwargs))
    assert direct.search_stock_news("AAPL", "Apple") is cached
    assert diagnostics[-1]["cache_hit"] is True

    waited = _service()
    wait_event = threading.Event()
    monkeypatch.setattr(
        waited,
        "_get_cached_or_reserve",
        lambda _key: (None, False, wait_event),
    )
    monkeypatch.setattr(waited, "_wait_for_cached", lambda _key, _event: cached)
    monkeypatch.setattr(waited, "_record_news_search_run", lambda **_kwargs: None)
    assert waited.search_stock_news("AAPL", "Apple") is cached

    retried = _service()
    calls = iter([(None, False, wait_event), (cached, False, None)])
    monkeypatch.setattr(retried, "_get_cached_or_reserve", lambda _key: next(calls))
    monkeypatch.setattr(retried, "_wait_for_cached", lambda _key, _event: None)
    monkeypatch.setattr(retried, "_record_news_search_run", lambda **_kwargs: None)
    assert retried.search_stock_news("AAPL", "Apple") is cached

    no_provider = _service([_Provider("off", [], available=False)])
    response = no_provider.search_stock_news(
        "600519",
        "贵州茅台",
        focus_keywords=["茅台", "公告"],
    )
    assert response.success is False
    assert response.provider == "None"

    provider_failed = _service([_Provider("failed", [_response(success=False)])])
    monkeypatch.setattr(provider_failed, "_filter_news_response", lambda response, **_kwargs: response)
    monkeypatch.setattr(provider_failed, "_record_news_search_run", lambda **_kwargs: None)
    response = provider_failed.search_stock_news("UNKNOWN", "Unknown")
    assert response.success is False
    assert response.provider == "None"

    filtered = _service([_Provider("empty", [_response(success=True)])])
    monkeypatch.setattr(filtered, "_filter_news_response", lambda response, **_kwargs: response)
    monkeypatch.setattr(filtered, "_record_news_search_run", lambda **_kwargs: None)
    response = filtered.search_stock_news("UNKNOWN", "Unknown")
    assert response.success is True
    assert response.provider == "Filtered"


def test_cache_locale_and_preference_helpers(monkeypatch):
    service = _service([_Provider("available", [_response()])])
    assert service.is_available is True
    assert service._should_prefer_chinese_news("AAPL", "Apple", ["公告"]) is True
    assert service._brave_search_locale("UNKNOWN", prefer_chinese=False) == {}
    assert service.is_index_or_etf("", "") is False
    assert service.is_index_or_etf("SPX", "S&P 500") is True

    one = _response(results=[_result("One", url="https://one")])
    two = _response(
        results=[_result("One", url="https://one"), _result("Two", url="https://two")]
    )
    assert service._is_better_preferred_news_response(
        one,
        candidate_preferred_count=1,
        best_response=None,
        best_preferred_count=0,
    )
    assert service._is_better_preferred_news_response(
        one,
        candidate_preferred_count=2,
        best_response=two,
        best_preferred_count=1,
    )
    assert service._is_better_preferred_news_response(
        two,
        candidate_preferred_count=1,
        best_response=one,
        best_preferred_count=1,
    )

    service._cache["fresh"] = (time.time(), one)
    assert service._get_cached("fresh") is one
    assert service._get_cached_or_reserve("fresh") == (one, False, None)
    service._cache["expired"] = (0, one)
    assert service._get_cached("expired") is None

    cached, owner, event = service._get_cached_or_reserve("reserved")
    assert (cached, owner) == (None, True)
    assert service._get_cached_or_reserve("reserved") == (None, False, event)
    service._put_cache("reserved", two)
    service._release_cache_fill("reserved", event)
    assert event.is_set()
    assert service._wait_for_cached("reserved", event) is two

    now = time.time()
    service._cache = {f"key-{index}": (now + index, one) for index in range(500)}
    service._put_cache("newest", two)
    assert len(service._cache) == 500
    assert "key-0" not in service._cache

    service._cache = {f"key-{index}": (now, one) for index in range(499)}
    service._cache["expired"] = (0, one)
    service._put_cache("replacement", two)
    assert "expired" not in service._cache
    assert service._cache["replacement"][1] is two


@pytest.mark.parametrize(
    ("value", "expected_days"),
    [
        ("today", 0),
        ("yesterday", 1),
        ("前天", 2),
        ("2 分钟前", 0),
        ("2 小时前", 0),
        ("2 天前", 2),
        ("2 周前", 14),
        ("2 个月前", 60),
        ("2 年前", 730),
        ("2 mins ago", 0),
        ("2 hours ago", 0),
        ("2 days ago", 2),
        ("2 weeks ago", 14),
        ("2 months ago", 60),
        ("2 years ago", 730),
    ],
)
def test_relative_news_date_variants(value, expected_days):
    now = datetime(2026, 8, 4, 12, 0, 0)
    parsed = SearchService._parse_relative_news_date(value, now)
    assert parsed == (now - timedelta(days=expected_days)).date()


def test_news_date_normalization_and_filter_edge_paths():
    service = _service()
    today = date.today()
    assert service._parse_relative_news_date("", datetime.now()) is None
    assert service._parse_relative_news_date("not a date", datetime.now()) is None
    assert service._normalize_news_publish_date(None) is None
    assert service._normalize_news_publish_date("") is None
    assert service._normalize_news_publish_date(today) == today
    assert service._normalize_news_publish_date(datetime(2026, 8, 4)) == date(2026, 8, 4)
    assert service._normalize_news_publish_date(
        datetime(2026, 8, 4, tzinfo=timezone.utc)
    ) == date(2026, 8, 4)
    assert service._normalize_news_publish_date("2026-08-04T10:00:00+00:00") == date(2026, 8, 4)
    assert service._normalize_news_publish_date("2026年8月4日") == date(2026, 8, 4)
    assert service._normalize_news_publish_date("Aug 4th, 2026") == date(2026, 8, 4)
    assert service._normalize_news_publish_date("20260804") == date(2026, 8, 4)
    assert service._normalize_news_publish_date("not a date") is None

    empty = _response()
    assert service._filter_news_response(
        empty,
        search_days=3,
        max_results=1,
        log_scope="empty",
    ) is empty
    assert service._normalize_and_limit_response(empty, max_results=1) is empty

    unknown = _response(
        results=[
            _result("Unknown", url="https://unknown", published_date=None),
            _result("Ignored", url="https://ignored", published_date=None),
        ]
    )
    kept = service._filter_news_response(
        unknown,
        search_days=3,
        max_results=1,
        log_scope="unknown",
        keep_unknown=True,
    )
    assert [item.title for item in kept.results] == ["Unknown"]


def test_ranked_response_final_tiebreakers():
    response = _response()
    best = {"direct_count": 1, "preferred_direct_count": 1, "preferred_count": 1, "max_score": 5, "result_count": 1}
    higher_score = dict(best, max_score=6)
    more_results = dict(best, result_count=2)
    assert SearchService._is_better_ranked_news_response(
        response,
        candidate_stats=higher_score,
        best_response=response,
        best_stats=best,
        prefer_chinese=False,
    )
    assert SearchService._is_better_ranked_news_response(
        response,
        candidate_stats=more_results,
        best_response=response,
        best_stats=best,
        prefer_chinese=False,
    )
