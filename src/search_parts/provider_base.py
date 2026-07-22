# Shared provider definitions executed by the public src.search_service facade.

if __name__ != "src.search_service":
    from src.search_service import (
        ABC,
        Any,
        Article,
        Config,
        Dict,
        List,
        Optional,
        Tuple,
        _SEARCH_REQUEST_FAILED,
        abstractmethod,
        cycle,
        dataclass,
        exception_chain_redaction_values,
        log_safe_exception,
        logger,
        logging,
        requests,
        retry,
        retry_if_exception_type,
        safe_before_sleep_log,
        safe_get,
        safe_post,
        stop_after_attempt,
        threading,
        time,
        wait_exponential,
    )

def _stable_search_failure_message(http_status: Any = None) -> str:
    """Return a bounded public failure without provider response diagnostics."""
    if isinstance(http_status, int) and not isinstance(http_status, bool):
        return f"Search request failed (HTTP {http_status})."
    return _SEARCH_REQUEST_FAILED


def _log_search_failure(
    *,
    provider: str,
    error_code: str,
    http_status: Optional[int] = None,
) -> None:
    """Log only the stable fields allowed at search-provider failure boundaries."""
    if isinstance(http_status, int) and not isinstance(http_status, bool):
        logger.warning(
            "Search provider request failed provider=%s http_status=%s error_code=%s",
            provider,
            http_status,
            error_code,
        )
        return
    logger.warning(
        "Search provider request failed provider=%s error_code=%s",
        provider,
        error_code,
    )


def _safe_search_exception_message(
    *,
    provider: str,
    event: str,
    error_code: str,
    exc: BaseException,
    public_message: str,
) -> str:
    """Log a provider exception safely and return a stable public diagnostic."""

    log_safe_exception(
        logger,
        event,
        exc,
        error_code=error_code,
        level=logging.ERROR,
        context={"provider": provider},
        exception_redaction_values=exception_chain_redaction_values(exc),
    )
    return public_message

# Transient network errors (retryable)
_SEARCH_TRANSIENT_EXCEPTIONS = (
    requests.exceptions.SSLError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_SEARCH_TRANSIENT_EXCEPTIONS),
    before_sleep=safe_before_sleep_log(
        logger,
        logging.WARNING,
        event="Search POST request retry scheduled",
        error_code="search_post_request_retry",
    ),
)
def _post_with_retry(url: str, *, headers: Dict[str, str], json: Dict[str, Any], timeout: int) -> requests.Response:
    """POST with retry on transient SSL/network errors."""
    return safe_post(
        url,
        headers=headers,
        json=json,
        timeout=timeout,
        transport=requests,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_SEARCH_TRANSIENT_EXCEPTIONS),
    before_sleep=safe_before_sleep_log(
        logger,
        logging.WARNING,
        event="Search GET request retry scheduled",
        error_code="search_get_request_retry",
    ),
    reraise=True,
)
def _get_with_retry(
    url: str, *, headers: Dict[str, str], params: Dict[str, Any], timeout: int
) -> requests.Response:
    """GET with retry on transient SSL/network errors."""
    return safe_get(
        url,
        headers=headers,
        params=params,
        timeout=timeout,
        transport=requests,
    )


def fetch_url_content(url: str, timeout: int = 5) -> str:
    """
    获取 URL 网页正文内容 (使用 newspaper3k)
    """
    try:
        # Configure newspaper3k
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        config.request_timeout = timeout
        config.fetch_images = False  # Do not download images
        config.memoize_articles = False # Not cached

        response = safe_get(
            url,
            headers={"User-Agent": config.browser_user_agent},
            timeout=timeout,
            transport=requests,
        )
        response.raise_for_status()

        article = Article(url, config=config, language='zh')  # Chinese is the default, but other languages remain supported.
        article.download(input_html=response.text)
        article.parse()

        # Get the main text
        text = article.text.strip()

        # Simple post-processing: remove empty lines
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)

        return text[:1500]  # Allow slightly more than bs4 because newspaper produces cleaner text.
    except Exception as exc:  # broad-exception: fallback_recorded - Optional content enrichment logs and returns empty.
        log_safe_exception(
            logger,
            "Search result content fetch failed",
            exc,
            error_code="search_result_content_fetch_failed",
            level=logging.DEBUG,
            exception_redaction_values=exception_chain_redaction_values(exc),
        )

    return ""


@dataclass
class SearchResult:
    """搜索结果数据类"""
    title: str
    snippet: str  # Summary
    url: str
    source: str  # Source website
    published_date: Optional[str] = None
    relevance_score: Optional[int] = None
    relevance_category: Optional[str] = None
    relevance_reasons: Optional[List[str]] = None

    def to_text(self) -> str:
        """转换为文本格式"""
        date_str = f" ({self.published_date})" if self.published_date else ""
        relevance_parts: List[str] = []
        if self.relevance_category:
            relevance_parts.append(self.relevance_category)
        if self.relevance_score is not None:
            relevance_parts.append(f"score={self.relevance_score}")
        if self.relevance_reasons:
            relevance_parts.append(f"依据: {'；'.join(self.relevance_reasons[:3])}")
        relevance_str = f"\n关联度: {'; '.join(relevance_parts)}" if relevance_parts else ""
        return f"【{self.source}】{self.title}{date_str}\n{self.snippet}{relevance_str}"


@dataclass
class SearchResponse:
    """搜索响应"""
    query: str
    results: List[SearchResult]
    provider: str  # Used search engine
    success: bool = True
    error_message: Optional[str] = None
    search_time: float = 0.0  # Search duration (seconds).

    def to_context(self, max_results: int = 5) -> str:
        """将搜索结果转换为可用于 AI 分析的上下文"""
        if not self.success or not self.results:
            return f"搜索 '{self.query}' 未找到相关结果。"

        lines = [f"【{self.query} 搜索结果】（来源：{self.provider}）"]
        for i, result in enumerate(self.results[:max_results], 1):
            lines.append(f"\n{i}. {result.to_text()}")

        return "\n".join(lines)


def _stabilize_failed_search_response(response: SearchResponse) -> SearchResponse:
    """Replace provider-owned failure details before a service boundary uses them."""
    if not response.success:
        response.error_message = _SEARCH_REQUEST_FAILED
    return response


class BaseSearchProvider(ABC):
    """搜索引擎基类"""

    def __init__(self, api_keys: List[str], name: str):
        """
        初始化搜索引擎
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            api_keys: API Key 列表（支持多个 key 负载均衡）
            name: 搜索引擎名称
\x20\x20\x20\x20\x20\x20\x20\x20"""
        self._api_keys = api_keys
        self._name = name
        self._key_cycle = cycle(api_keys) if api_keys else None
        self._key_usage: Dict[str, int] = {key: 0 for key in api_keys}
        self._key_errors: Dict[str, int] = {key: 0 for key in api_keys}
        self._state_lock = threading.RLock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_available(self) -> bool:
        """检查是否有可用的 API Key"""
        return bool(self._api_keys)

    def _get_next_key(self) -> Optional[str]:
        """
        获取下一个可用的 API Key（负载均衡）
\x20\x20\x20\x20\x20\x20\x20\x20
        策略：轮询 + 跳过错误过多的 key
\x20\x20\x20\x20\x20\x20\x20\x20"""
        with self._state_lock:
            if not self._key_cycle:
                return None

            # Try all keys maximum
            for _ in range(len(self._api_keys)):
                key = next(self._key_cycle)
                # Skip keys with excessive errors (more than 3 times)
                if self._key_errors.get(key, 0) < 3:
                    return key

            # All keys have problems, reset error count and return the first one
            logger.warning(f"[{self._name}] 所有 API Key 都有错误记录，重置错误计数")
            self._key_errors = {key: 0 for key in self._api_keys}
            return self._api_keys[0] if self._api_keys else None

    def _record_success(self, key: str) -> None:
        """记录成功使用"""
        with self._state_lock:
            self._key_usage[key] = self._key_usage.get(key, 0) + 1
            # Reduce error count on success
            if key in self._key_errors and self._key_errors[key] > 0:
                self._key_errors[key] -= 1

    def _record_error(self, key: str) -> None:
        """记录错误"""
        with self._state_lock:
            self._key_errors[key] = self._key_errors.get(key, 0) + 1
            error_count = self._key_errors[key]
        logger.warning(
            "Search provider key failure provider=%s error_count=%s "
            "error_code=search_provider_key_failure",
            self._name,
            error_count,
        )

    @abstractmethod
    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """执行搜索（子类实现）"""
        pass

    def _execute_search(
        self,
        query: str,
        *,
        max_results: int = 5,
        days: int = 7,
        api_key: Optional[str] = None,
        **search_kwargs: Any,
    ) -> SearchResponse:
        """Run the shared search flow with an optional preselected API key."""
        api_key = api_key or self._get_next_key()
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
            response = self._do_search(query, api_key, max_results, days=days, **search_kwargs)
            response.search_time = time.time() - start_time

            if response.success:
                self._record_success(api_key)
                logger.info(f"[{self._name}] 搜索 '{query}' 成功，返回 {len(response.results)} 条结果，耗时 {response.search_time:.2f}s")
            else:
                self._record_error(api_key)

            return response

        except Exception as exc:  # broad-exception: optional_metadata - An optional provider failure returns a stable result to the fallback chain.
            self._record_error(api_key)
            elapsed = time.time() - start_time
            error_msg = _safe_search_exception_message(
                provider=self._name,
                event="Search provider request failed",
                error_code="search_provider_request_failed",
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

    def search(self, query: str, max_results: int = 5, days: int = 7) -> SearchResponse:
        """
        执行搜索
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            days: 搜索最近几天的时间范围（默认7天）
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
        Returns:
            SearchResponse 对象
\x20\x20\x20\x20\x20\x20\x20\x20"""
        return self._execute_search(query, max_results=max_results, days=days)
