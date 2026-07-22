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

class TavilySearchProvider(BaseSearchProvider):
    """
    Tavily 搜索引擎
\x20\x20\x20\x20
    特点：
    - 专为 AI/LLM 优化的搜索 API
    - 免费版每月 1000 次请求
    - 返回结构化的搜索结果
\x20\x20\x20\x20
    文档：https://docs.tavily.com/
\x20\x20\x20\x20"""

    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "Tavily")

    def _do_search(
        self,
        query: str,
        api_key: str,
        max_results: int,
        days: int = 7,
        topic: Optional[str] = None,
    ) -> SearchResponse:
        """执行 Tavily 搜索"""
        try:
            from tavily import TavilyClient
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="tavily-python 未安装，请运行: pip install tavily-python"
            )

        try:
            client = TavilyClient(api_key=api_key)

            # Execute search (optimization: use advanced depth, limit to recent days)
            search_kwargs: Dict[str, Any] = {
                "query": query,
                "search_depth": "advanced",  # Advanced retrieval for more results
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False,
                "days": days,  # Search for content from the last N days.
            }
            if topic is not None:
                search_kwargs["topic"] = topic

            response = client.search(
                **search_kwargs,
            )

            if isinstance(response, dict) and "error" in response:
                _log_search_failure(
                    provider=self.name,
                    error_code="tavily_api_response_failed",
                )
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=_SEARCH_REQUEST_FAILED,
                )

            # Parse results
            results = []
            for item in response.get('results', []):
                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=item.get('content', '')[:500],  # Keep the first 500 characters
                    url=item.get('url', ''),
                    source=self._extract_domain(item.get('url', '')),
                    published_date=item.get('published_date') or item.get('publishedDate'),
                ))

            logger.info(
                "Search provider response parsed provider=%s result_count=%s",
                self.name,
                len(results),
            )

            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True,
            )

        except Exception as exc:  # broad-exception: optional_metadata - An optional provider failure returns a stable result to the fallback chain.
            error_msg = _safe_search_exception_message(
                provider=self.name,
                event="Tavily search failed unexpectedly",
                error_code="tavily_search_failed",
                exc=exc,
                public_message=_SEARCH_REQUEST_FAILED,
            )
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )

    def search(
        self,
        query: str,
        max_results: int = 5,
        days: int = 7,
        topic: Optional[str] = None,
    ) -> SearchResponse:
        """执行 Tavily 搜索，可按调用方选择是否启用新闻 topic。"""
        if topic is None:
            return super().search(query, max_results=max_results, days=days)

        api_key = self._get_next_key()
        if not api_key:
            return SearchResponse(
                query=query,
                results=[],
                provider=self._name,
                success=False,
                error_message=f"{self._name} 未配置 API Key"
            )

        start_time = time.time()
        try:
            response = self._do_search(query, api_key, max_results, days=days, topic=topic)
            response.search_time = time.time() - start_time

            if response.success:
                self._record_success(api_key)
                logger.info(f"[{self._name}] 搜索 '{query}' 成功，返回 {len(response.results)} 条结果，耗时 {response.search_time:.2f}s")
            else:
                self._record_error(api_key)

            return response

        except Exception as exc:  # broad-exception: optional_metadata - Optional topic search failure returns a stable result to the fallback chain.
            self._record_error(api_key)
            elapsed = time.time() - start_time
            error_msg = _safe_search_exception_message(
                provider=self._name,
                event="Tavily topic search failed",
                error_code="tavily_topic_search_failed",
                exc=exc,
                public_message=_SEARCH_REQUEST_FAILED,
            )
            return SearchResponse(
                query=query,
                results=[],
                provider=self._name,
                success=False,
                error_message=error_msg,
                search_time=elapsed
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
