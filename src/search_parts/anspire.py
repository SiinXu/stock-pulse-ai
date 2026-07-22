# Provider definition executed by the public src.search_service facade.

if __name__ != "src.search_service":
    from src.search_service import (
        Any,
        BaseSearchProvider,
        Dict,
        List,
        Optional,
        SearchResponse,
        SearchResult,
        Tuple,
        _SEARCH_REQUEST_FAILED,
        _SEARXNG_JSON_DISABLED,
        _get_with_retry,
        _log_search_failure,
        _post_with_retry,
        _safe_search_exception_message,
        _stable_search_failure_message,
        date,
        datetime,
        exception_chain_redaction_values,
        fetch_url_content,
        log_safe_exception,
        logger,
        logging,
        parse_qsl,
        re,
        record_provider_run,
        record_provider_run_started,
        requests,
        safe_get,
        threading,
        time,
        timedelta,
        timezone,
        unquote,
        urlparse,
    )

class AnspireSearchProvider(BaseSearchProvider):
    """
    Anspire Search 搜索引擎
\x20\x20\x20\x20
    特点：
    - 面向AI生态的下一代实时智能搜索引擎
    - 结果精准、响应快速
    - 适用于股票新闻和市场情报搜索
\x20\x20\x20\x20
    文档: https://open.anspire.cn/document/docs/searchApi/
\x20\x20\x20\x20"""

    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "Anspire")

    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7, region_mode: int = 0) -> SearchResponse:
        """执行 Anspire 搜索"""
        try:
            import requests
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="requests 未安装，请运行：pip install requests"
            )

        try:
            # API endpoints
            url = "https://plugin.anspire.cn/api/ntsearch/search"

            # Request headers
            headers = {
                'Authorization': f'Bearer {api_key}'
            }

            # Request parameters
            payload = {
                "query": query,
                "top_k": min(max_results,50),
                "FromTime": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S"),
                "ToTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "region_mode": region_mode
            }

            # Execute search
            response = _get_with_retry(url, headers=headers, params=payload, timeout=10)

            # Check HTTP status code
            if response.status_code != 200:
                error_msg = _stable_search_failure_message(response.status_code)
                _log_search_failure(
                    provider=self.name,
                    http_status=response.status_code,
                    error_code="anspire_http_request_failed",
                )

                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )

            # Parse response
            try:
                data = response.json()
            except ValueError as e:
                error_msg = _safe_search_exception_message(
                    provider=self.name,
                    event="Anspire response JSON parsing failed",
                    error_code="anspire_response_json_invalid",
                    exc=e,
                    public_message="Response JSON parsing failed",
                )
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )

            if 'code' in data and data.get('code') != 200:
                error_msg = _stable_search_failure_message()
                _log_search_failure(
                    provider=self.name,
                    error_code="anspire_api_response_failed",
                )
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )

            if 'results' not in data:
                error_msg = "Invalid search response."
                _log_search_failure(
                    provider=self.name,
                    error_code="anspire_response_format_invalid",
                )
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )

            logger.info(f"[Anspire] 搜索完成，query='{query}'")

            results = []
            value_list = data.get('results', [])

            for item in value_list[:max_results]:
                snippet = item.get('content')
                if snippet and isinstance(snippet, str) and len(snippet) > 500:
                    snippet = snippet[:500] + "..."

                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=snippet,
                    url=item.get('url', ''),
                    source=self._extract_domain(item.get('url', '')),
                    published_date=item.get('date', '')
                ))

            logger.info(f"[Anspire] 成功解析 {len(results)} 条结果")

            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True,
            )

        except requests.exceptions.Timeout:
            error_msg = "请求超时"
            _log_search_failure(
                provider=self.name,
                error_code="anspire_request_timeout",
            )
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except requests.exceptions.RequestException as e:
            error_msg = _safe_search_exception_message(
                provider=self.name,
                event="Anspire network request failed",
                error_code="anspire_network_request_failed",
                exc=e,
                public_message="Network connection failed",
            )
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except Exception as e:  # broad-exception: fallback_recorded - Provider failure becomes a stable search result.
            log_safe_exception(
                logger,
                "Anspire search failed unexpectedly",
                e,
                error_code="anspire_search_failed",
                level=logging.ERROR,
                context={"provider": self.name},
                exception_redaction_values=exception_chain_redaction_values(e),
            )
            error_msg = "Unexpected search error"
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )

    @staticmethod
    def _extract_domain(url: str) -> str:
        """从 URL 提取域名作为来源"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain or '未知来源'
        except Exception:  # broad-exception: optional_metadata - Invalid URLs keep the unknown source label.
            return '未知来源'
