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

class BochaSearchProvider(BaseSearchProvider):
    """
    博查搜索引擎
\x20\x20\x20\x20
    特点：
    - 专为AI优化的中文搜索API
    - 结果准确、摘要完整
    - 支持时间范围过滤和AI摘要
    - 兼容Bing Search API格式
\x20\x20\x20\x20
    文档：https://bocha-ai.feishu.cn/wiki/RXEOw02rFiwzGSkd9mUcqoeAnNK
\x20\x20\x20\x20"""

    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "Bocha")

    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """执行博查搜索"""
        try:
            import requests
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="requests 未安装，请运行: pip install requests"
            )

        try:
            # API endpoints
            url = "https://api.bocha.cn/v1/web-search"

            # Request headers
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }

            # Determine time range
            freshness = "oneWeek"
            if days <= 1:
                freshness = "oneDay"
            elif days <= 7:
                freshness = "oneWeek"
            elif days <= 30:
                freshness = "oneMonth"
            else:
                freshness = "oneYear"

            # Request parameters (strictly according to the API documentation)
            payload = {
                "query": query,
                "freshness": freshness,  # Dynamic time range
                "summary": True,  # Enable AI summarization
                "count": min(max_results, 50)  # Maximum 50 items
            }

            # Execute search with retries for transient SSL/network errors
            response = _post_with_retry(url, headers=headers, json=payload, timeout=10)

            # Check HTTP status code
            if response.status_code != 200:
                error_msg = _stable_search_failure_message(response.status_code)
                _log_search_failure(
                    provider=self.name,
                    http_status=response.status_code,
                    error_code="bocha_http_request_failed",
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
                    event="Bocha response JSON parsing failed",
                    error_code="bocha_response_json_invalid",
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

            # Check the response code
            if data.get('code') != 200:
                error_msg = _stable_search_failure_message()
                _log_search_failure(
                    provider=self.name,
                    error_code="bocha_api_response_failed",
                )
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )

            logger.info(f"[Bocha] 搜索完成，query='{query}'")

            # Parse search results
            results = []
            web_pages = data.get('data', {}).get('webPages', {})
            value_list = web_pages.get('value', [])

            for item in value_list[:max_results]:
                # Prioritize using summary (AI summary), fallback to snippet
                snippet = item.get('summary') or item.get('snippet', '')

                # Truncate summary length
                if snippet:
                    snippet = snippet[:500]

                results.append(SearchResult(
                    title=item.get('name', ''),
                    snippet=snippet,
                    url=item.get('url', ''),
                    source=item.get('siteName') or self._extract_domain(item.get('url', '')),
                    published_date=item.get('datePublished'),  # UTC+8 format, no conversion needed
                ))

            logger.info(f"[Bocha] 成功解析 {len(results)} 条结果")

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
                error_code="bocha_request_timeout",
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
                event="Bocha network request failed",
                error_code="bocha_network_request_failed",
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
                "Bocha search failed unexpectedly",
                e,
                error_code="bocha_search_failed",
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
