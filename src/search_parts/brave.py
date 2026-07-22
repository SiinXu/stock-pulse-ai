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

class BraveSearchProvider(BaseSearchProvider):
    """
    Brave Search 搜索引擎

    特点：
    - 隐私优先的独立搜索引擎
    - 索引超过300亿页面
    - 免费层可用
    - 支持时间范围过滤

    文档：https://brave.com/search/api/
    """

    API_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "Brave")

    def _do_search(
        self,
        query: str,
        api_key: str,
        max_results: int,
        days: int = 7,
        search_lang: Optional[str] = None,
        country: Optional[str] = None,
    ) -> SearchResponse:
        """执行 Brave 搜索"""
        try:
            # Request headers
            headers = {
                'X-Subscription-Token': api_key,
                'Accept': 'application/json'
            }

            # Determine time range (freshness parameter)
            if days <= 1:
                freshness = "pd"  # Past day (24 hours)
            elif days <= 7:
                freshness = "pw"  # Past week
            elif days <= 30:
                freshness = "pm"  # Past month
            else:
                freshness = "py"  # Past year

            # Request parameters
            params = {
                "q": query,
                "count": min(max_results, 20),  # Brave supports a maximum of 20 items
                "freshness": freshness,
                "safesearch": "moderate"
            }
            if search_lang:
                params["search_lang"] = search_lang
            if country:
                params["country"] = country

            # Execute the GET search through the outbound safety policy.
            response = safe_get(
                self.API_ENDPOINT,
                headers=headers,
                params=params,
                timeout=10,
                transport=requests,
            )

            # Check HTTP status code
            if response.status_code != 200:
                error_msg = self._parse_error(response)
                _log_search_failure(
                    provider=self.name,
                    http_status=response.status_code,
                    error_code="brave_http_request_failed",
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
                    event="Brave response JSON parsing failed",
                    error_code="brave_response_json_invalid",
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

            logger.info(f"[Brave] 搜索完成，query='{query}'")

            # Parse search results
            results = []
            web_data = data.get('web', {})
            web_results = web_data.get('results', [])

            for item in web_results[:max_results]:
                # Parse the publication date (ISO 8601 format)
                published_date = None
                age = item.get('age') or item.get('page_age')
                if age:
                    try:
                        # Convert ISO format to simple date string
                        dt = datetime.fromisoformat(age.replace('Z', '+00:00'))
                        published_date = dt.strftime('%Y-%m-%d')
                    except (ValueError, AttributeError):
                        published_date = age  # Use original value when parsing fails

                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=item.get('description', '')[:500],  # Truncate to 500 characters
                    url=item.get('url', ''),
                    source=self._extract_domain(item.get('url', '')),
                    published_date=published_date
                ))

            logger.info(f"[Brave] 成功解析 {len(results)} 条结果")

            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True
            )

        except requests.exceptions.Timeout:
            error_msg = "请求超时"
            _log_search_failure(
                provider=self.name,
                error_code="brave_request_timeout",
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
                event="Brave network request failed",
                error_code="brave_network_request_failed",
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
                "Brave search failed unexpectedly",
                e,
                error_code="brave_search_failed",
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

    def _parse_error(self, response) -> str:
        """Return a stable HTTP failure without inspecting the response body."""
        return _stable_search_failure_message(getattr(response, "status_code", None))

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

    def search(
        self,
        query: str,
        max_results: int = 5,
        days: int = 7,
        search_lang: Optional[str] = None,
        country: Optional[str] = None,
    ) -> SearchResponse:
        """执行 Brave 搜索，可按调用方传入区域与语言偏好。"""
        if search_lang is None and country is None:
            return super().search(query, max_results=max_results, days=days)

        return self._execute_search(
            query,
            max_results=max_results,
            days=days,
            search_lang=search_lang,
            country=country,
        )
