"""Guard methods moved behind the public search-service facade."""

import __future__
import ast
import importlib
import inspect
import subprocess
import sys
from pathlib import Path

from tests.test_search_service_public_surface import (
    _canonical_ast,
    _class_record,
    _digest,
)


EXPECTED_SERVICE_RAW_COUNT = 95
EXPECTED_SERVICE_RAW_SURFACE_SHA256 = (
    "01fa9cc33dafc7c34c2211c64fd7ebcb2a499cabeff3654c88953a7882e7fe94"
)
EXPECTED_SERVICE_REFLECTION_SHA256 = (
    "ca753430115eef646f762dd716bce7854086468b483dc2fe086353498ba7990d"
)

EXPECTED_METHOD_AST_GROUPS = (
    (
        "service_state.py",
        "_ServiceStateMethods",
        (
            "_is_foreign_stock",
            "_contains_chinese_text",
            "_is_us_stock",
            "_should_prefer_chinese_news",
            "_is_chinese_news_result",
            "_prioritize_news_language",
            "_is_better_preferred_news_response",
            "_brave_search_locale",
            "is_index_or_etf",
            "is_available",
            "_cache_key",
            "_get_cached_locked",
            "_get_cached",
            "_get_cached_or_reserve",
            "_release_cache_fill",
            "_wait_for_cached",
            "_put_cache",
            "_effective_news_window_days",
        ),
        "56800ed57640116db8ca983015a0f792d76e2f0ad544a399f453a43315132b79",
        195,
    ),
    (
        "news_processing.py",
        "_NewsProcessingMethods",
        (
            "_provider_request_size",
            "_append_unique",
            "_stock_code_identity_terms",
            "_company_identity_terms",
            "_contains_identity_term",
            "_contains_stock_code_identity_term",
            "_contains_any_news_term",
            "_contains_any_low_quality_news_term",
            "_candidate_hostname",
            "_source_resembles_hostname",
            "_is_trusted_official_news_source",
            "_has_low_quality_news_page_signal",
            "_has_adult_service_spam_news_page_signal",
            "_score_news_relevance",
            "_rank_news_response",
            "_filter_ranked_news_for_context",
            "_news_relevance_stats",
            "_is_better_ranked_news_response",
            "_parse_relative_news_date",
            "_normalize_news_publish_date",
            "_filter_news_response",
            "_normalize_and_limit_response",
            "_limit_search_response",
            "_elapsed_ms",
            "_record_news_search_run",
        ),
        "6ad381bae9f14968e8692c07af1e275f40282a025ba90663e1a869cf436c727a",
        971,
    ),
    (
        "orchestration.py",
        "_OrchestrationMethods",
        (
            "search_stock_news",
            "search_stock_events",
            "search_comprehensive_intel",
            "format_intel_report",
            "batch_search",
            "search_stock_price_fallback",
            "search_stock_with_enhanced_fallback",
            "format_price_search_context",
        ),
        "2576de57ba5268e7c18f394151cedef379dcbb7062d6f50a0e34db97f56a3cfb",
        864,
    ),
)
EXPECTED_MOVED_METHOD_AST_LINES = 2_030
MOVED_METHOD_NAMES = tuple(
    name
    for _, _, expected_names, _, _ in EXPECTED_METHOD_AST_GROUPS
    for name in expected_names
)
PRIVATE_METHOD_MODULES = tuple(
    f"src.search_parts.{filename.removesuffix('.py')}"
    for filename, _, _, _, _ in EXPECTED_METHOD_AST_GROUPS
)


def _method_definitions(path: Path, container_name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    container = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == container_name
    )
    return [
        node
        for node in container.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _definition_line_count(node):
    first_line = min(
        [node.lineno, *(decorator.lineno for decorator in node.decorator_list)]
    )
    return node.end_lineno - first_line + 1


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    if inspect.isfunction(descriptor):
        return descriptor
    return None


def _search_service_reflection_snapshot(module):
    record = _class_record(module, module.SearchService)
    record["regexes"] = [
        [
            "_CHINESE_TEXT_RE",
            module.SearchService._CHINESE_TEXT_RE.pattern,
            module.SearchService._CHINESE_TEXT_RE.flags,
        ],
        [
            "_US_STOCK_RE",
            module.SearchService._US_STOCK_RE.pattern,
            module.SearchService._US_STOCK_RE.flags,
        ],
    ]
    record["code_contract"] = []
    for name, descriptor in vars(module.SearchService).items():
        function = _descriptor_function(descriptor)
        if function is None:
            continue
        record["code_contract"].append(
            [
                name,
                bool(
                    function.__code__.co_flags
                    & __future__.annotations.compiler_flag
                ),
                list(function.__code__.co_freevars),
                function.__closure__ is None,
            ]
        )
    return record


def test_search_service_method_asts_match_pre_split_snapshot():
    parts = Path(__file__).parents[1] / "src" / "search_parts"
    moved_lines = 0

    for (
        filename,
        container_name,
        expected_names,
        expected_hash,
        expected_lines,
    ) in EXPECTED_METHOD_AST_GROUPS:
        definitions = _method_definitions(parts / filename, container_name)
        assert tuple(node.name for node in definitions) == expected_names
        assert _digest(
            [(node.name, _canonical_ast(node)) for node in definitions]
        ) == expected_hash
        actual_lines = sum(_definition_line_count(node) for node in definitions)
        assert actual_lines == expected_lines
        moved_lines += actual_lines

    assert moved_lines == EXPECTED_MOVED_METHOD_AST_LINES


def test_search_service_class_reflection_matches_pre_split_snapshot():
    script = r'''
import src.search_service as module
from tests.test_search_service_method_surface import (
    _digest,
    _search_service_reflection_snapshot,
)

print(len(vars(module.SearchService)))
print(_digest(tuple(vars(module.SearchService))))
print(_digest(_search_service_reflection_snapshot(module)))
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        str(EXPECTED_SERVICE_RAW_COUNT),
        EXPECTED_SERVICE_RAW_SURFACE_SHA256,
        EXPECTED_SERVICE_REFLECTION_SHA256,
    ]


def test_search_service_moved_methods_use_facade_patch_seams(monkeypatch):
    module = importlib.import_module("src.search_service")
    service = object.__new__(module.SearchService)
    service.news_max_age_days = 3
    service.news_strategy_profile = "short"
    service._providers = []

    resolver_calls = []
    monkeypatch.setattr(
        module,
        "resolve_news_window_days",
        lambda **kwargs: resolver_calls.append(kwargs) or 41,
    )
    assert service._effective_news_window_days() == 41
    assert resolver_calls == [
        {"news_max_age_days": 3, "news_strategy_profile": "short"}
    ]

    diagnostics = []
    monkeypatch.setattr(
        module,
        "record_provider_run",
        lambda **kwargs: diagnostics.append(kwargs),
    )
    service._record_news_search_run(
        provider="patched",
        operation="surface_guard",
        success=True,
        record_count=2,
    )
    assert diagnostics == [
        {
            "data_type": "news_search",
            "provider": "patched",
            "operation": "surface_guard",
            "success": True,
            "latency_ms": None,
            "error_type": None,
            "error_message": None,
            "cache_hit": None,
            "record_count": 2,
        }
    ]

    sentinel = object()
    response_calls = []
    monkeypatch.setattr(
        module,
        "SearchResponse",
        lambda **kwargs: response_calls.append(kwargs) or sentinel,
    )
    assert service.search_stock_events("AAPL", "Apple", ["earnings"]) is sentinel
    assert response_calls == [
        {
            "query": "Apple (earnings)",
            "results": [],
            "provider": "None",
            "success": False,
            "error_message": "事件搜索失败",
        }
    ]


def test_search_method_private_modules_do_not_replace_facade_methods():
    script = r'''
import importlib

private_first = importlib.import_module("src.search_parts.orchestration")
module = importlib.import_module("src.search_service")
from tests.test_search_service_method_surface import (
    EXPECTED_METHOD_AST_GROUPS,
    MOVED_METHOD_NAMES,
    PRIVATE_METHOD_MODULES,
)

facade_descriptors = {
    name: vars(module.SearchService)[name]
    for name in MOVED_METHOD_NAMES
}
for private_name, (_, container_name, method_names, _, _) in zip(
    PRIVATE_METHOD_MODULES,
    EXPECTED_METHOD_AST_GROUPS,
):
    private_module = importlib.import_module(private_name)
    container = getattr(private_module, container_name)
    for name in method_names:
        private_descriptor = vars(container)[name]
        assert private_descriptor is not facade_descriptors[name]
        function = (
            private_descriptor.__func__
            if isinstance(private_descriptor, (staticmethod, classmethod))
            else private_descriptor.fget
            if isinstance(private_descriptor, property)
            else private_descriptor
        )
        assert function.__module__ == private_name

assert private_first._OrchestrationMethods.__module__ == private_first.__name__
assert {
    name: vars(module.SearchService)[name]
    for name in MOVED_METHOD_NAMES
} == facade_descriptors
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_search_reload_recreates_moved_methods_and_singleton():
    script = r'''
import importlib
import src.search_parts.service_state as private_state
import src.search_service as module

old_class = module.SearchService
old_method = module.SearchService._cache_key
private_state._ServiceStateMethods._cache_key = lambda *_args: "stale"
module._search_service = object()

first = importlib.reload(module)
first_class = first.SearchService
first_method = first.SearchService._cache_key
service = object.__new__(first.SearchService)

assert first_class is not old_class
assert first_method is not old_method
assert first_method.__globals__ is vars(first)
assert first_method.__module__ == first.__name__
assert first_method.__qualname__ == "SearchService._cache_key"
assert first_method(service, "query", 2, 3) == "query|2|3"
assert private_state._ServiceStateMethods._cache_key() == "stale"
assert first._search_service is None

first._search_service = object()
second = importlib.reload(first)
assert second.SearchService is not first_class
assert second.SearchService._cache_key is not first_method
assert second.SearchService._cache_key.__globals__ is vars(second)
assert second.SearchService._is_foreign_stock("AAPL") is True
assert second._search_service is None
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
