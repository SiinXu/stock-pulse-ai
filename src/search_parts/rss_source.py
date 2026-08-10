# Provider definition executed by the public src.search_service facade.
"""RSS/Atom market-news supplement for the on-demand search pipeline.

This is intentionally separate from ``IntelligenceService`` (local intel pool).
Configured feeds join the existing ``SearchService`` provider chain so entries
flow through the same freshness filter, relevance ranking, and diagnostics path
as SearXNG and paid search engines. Empty feed configuration keeps the provider
inert (``is_available`` is false).
"""

if __name__ != "src.search_service":
    from src.search_service import (
        Any,
        BaseSearchProvider,
        Dict,
        List,
        Optional,
        SearchResponse,
        SearchResult,
        _SEARCH_REQUEST_FAILED,
        _log_search_failure,
        datetime,
        exception_chain_redaction_values,
        log_safe_exception,
        logger,
        logging,
        parsedate_to_datetime,
        re,
        record_provider_run,
        requests,
        safe_get,
        time,
        timezone,
        urlparse,
    )


class RssAtomSearchProvider(BaseSearchProvider):
    """RSS/Atom feed adapter that supplements SearXNG and paid search providers.

    Feed URLs are admin-configured egress targets. Fetching goes through the
    fail-closed outbound policy (``safe_get``), matching other user-influenced
    HTTP destinations. Private/loopback feed hosts require an exact
    ``OUTBOUND_HTTP_ALLOWLIST`` entry; metadata and other hard-blocked targets
    remain denied.
    """

    MAX_FEED_BYTES = 2 * 1024 * 1024
    MAX_FEED_REDIRECTS = 5
    DEFAULT_TIMEOUT_SECONDS = 8.0
    DEFAULT_MAX_ITEMS_PER_FEED = 50
    _HTML_TAG_RE = re.compile(r"<[^>]+>")
    _WHITESPACE_RE = re.compile(r"\s+")
    _TOKEN_RE = re.compile(r"[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff]{2,}")
    _STOP_TOKENS = frozenset(
        {
            "stock",
            "stocks",
            "news",
            "latest",
            "market",
            "markets",
            "price",
            "share",
            "shares",
            "company",
            "the",
            "and",
            "for",
            "股票",
            "最新",
            "消息",
            "新闻",
            "行情",
            "公司",
            "市场",
        }
    )

    def __init__(
        self,
        feed_urls: Optional[List[str]] = None,
        *,
        timeout_sec: float = DEFAULT_TIMEOUT_SECONDS,
        max_items_per_feed: int = DEFAULT_MAX_ITEMS_PER_FEED,
    ):
        normalized = self._normalize_feed_urls(feed_urls or [])
        super().__init__(normalized, "RSS/Atom")
        self._feed_urls = normalized
        self._timeout = max(1.0, min(float(timeout_sec or self.DEFAULT_TIMEOUT_SECONDS), 30.0))
        self._max_items_per_feed = max(
            1, min(int(max_items_per_feed or self.DEFAULT_MAX_ITEMS_PER_FEED), 200)
        )

    @property
    def is_available(self) -> bool:
        return bool(self._feed_urls)

    @staticmethod
    def _xml_et():
        """Load XML parser with defusedxml-class care when the package is present."""
        try:
            from defusedxml import ElementTree as ET  # type: ignore
        except ImportError:  # pragma: no cover - exercised when defusedxml is absent
            from xml.etree import ElementTree as ET  # type: ignore
        return ET

    @staticmethod
    def _html_unescape(value: str) -> str:
        from html import unescape

        return unescape(value)

    @classmethod
    def _normalize_feed_urls(cls, raw_urls: List[str]) -> List[str]:
        seen = set()
        normalized: List[str] = []
        for raw in raw_urls:
            url = (raw or "").strip()
            if not url:
                continue
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                logger.warning(
                    "RSS/Atom feed URL ignored (invalid scheme or host) "
                    "error_code=rss_feed_url_invalid"
                )
                continue
            if url in seen:
                continue
            seen.add(url)
            normalized.append(url)
        return normalized

    def _do_search(
        self,
        query: str,
        api_key: str,
        max_results: int,
        days: int = 7,
    ) -> SearchResponse:
        """Single-feed path used only by the base class; prefer ``search``."""
        return self._search_feeds(
            query=query,
            max_results=max_results,
            days=days,
            feed_urls=[api_key] if api_key else [],
        )

    def search(self, query: str, max_results: int = 5, days: int = 7) -> SearchResponse:
        """Fetch all configured feeds and return query-relevant entries."""
        start_time = time.time()
        if not self._feed_urls:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=f"{self.name} 未配置 feed URL",
                search_time=0.0,
            )

        response = self._search_feeds(
            query=query,
            max_results=max_results,
            days=days,
            feed_urls=list(self._feed_urls),
        )
        response.search_time = time.time() - start_time
        if response.success:
            logger.info(
                "[%s] search '%s' returned %s results in %.2fs",
                self.name,
                query,
                len(response.results),
                response.search_time,
            )
        return response

    def _search_feeds(
        self,
        *,
        query: str,
        max_results: int,
        days: int,
        feed_urls: List[str],
    ) -> SearchResponse:
        query_tokens = self._query_tokens(query)
        collected: List[SearchResult] = []
        seen_urls = set()
        feeds_ok = 0
        feeds_failed = 0

        for feed_url in feed_urls:
            started = time.monotonic()
            try:
                entries = self._fetch_and_parse_feed(feed_url)
                feeds_ok += 1
                for entry in entries:
                    result = self._entry_to_result(entry, feed_url=feed_url)
                    if result is None:
                        continue
                    if result.url and result.url in seen_urls:
                        continue
                    if not self._matches_query(result, query_tokens):
                        continue
                    if result.url:
                        seen_urls.add(result.url)
                    collected.append(result)
                record_provider_run(
                    data_type="news_search",
                    provider=self.name,
                    operation="rss_feed_fetch",
                    success=True,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    record_count=len(entries),
                )
            except Exception as exc:  # broad-exception: fallback_recorded - Per-feed failure degrades without aborting the run.
                feeds_failed += 1
                log_safe_exception(
                    logger,
                    "RSS/Atom feed fetch failed; continuing with remaining feeds",
                    exc,
                    error_code="rss_feed_fetch_failed",
                    level=logging.WARNING,
                    context={"provider": self.name, "feed_host": self._feed_host(feed_url)},
                    exception_redaction_values=exception_chain_redaction_values(exc),
                )
                record_provider_run(
                    data_type="news_search",
                    provider=self.name,
                    operation="rss_feed_fetch",
                    success=False,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    error_type=type(exc).__name__,
                    error_message=_SEARCH_REQUEST_FAILED,
                )

        if days > 0:
            collected = self._soft_age_filter(collected, days=days)

        if feeds_ok == 0 and feeds_failed > 0:
            _log_search_failure(
                provider=self.name,
                error_code="rss_all_feeds_failed",
            )
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=_SEARCH_REQUEST_FAILED,
            )

        limited = collected[: max(1, int(max_results))]
        return SearchResponse(
            query=query,
            results=limited,
            provider=self.name,
            success=True,
        )

    def _fetch_and_parse_feed(self, feed_url: str) -> List[Dict[str, Any]]:
        response = None
        try:
            response = safe_get(
                feed_url,
                timeout=self._timeout,
                headers={
                    "User-Agent": "StockPulse-RSS/1.0",
                    "Accept": (
                        "application/rss+xml, application/atom+xml, "
                        "application/xml, text/xml, */*"
                    ),
                },
                max_redirects=self.MAX_FEED_REDIRECTS,
                stream=True,
                transport=requests,
            )
            response.raise_for_status()
            content = self._read_limited_body(response)
            return self._parse_feed_bytes(content, feed_url=feed_url)
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:  # broad-exception: optional_metadata - Best-effort close of stream body.
                    pass

    def _read_limited_body(self, response: Any) -> bytes:
        if hasattr(response, "iter_content") and callable(response.iter_content):
            chunks: List[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.MAX_FEED_BYTES:
                    raise ValueError("feed response exceeds size limit")
                chunks.append(chunk)
            return bytes().join(chunks)
        content = getattr(response, "content", None) or bytes()
        if len(content) > self.MAX_FEED_BYTES:
            raise ValueError("feed response exceeds size limit")
        return content

    def _parse_feed_bytes(self, content: bytes, *, feed_url: str) -> List[Dict[str, Any]]:
        if content is None or len(content) == 0 or len(content.strip()) == 0:
            return []
        ET = self._xml_et()
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ValueError(f"invalid RSS/Atom feed: {exc}") from exc

        tag = self._strip_ns(getattr(root, "tag", "")).lower()
        feed_label = self._feed_label(root, feed_url)
        if tag == "rss":
            nodes = root.findall("./channel/item")
            return [
                entry
                for entry in (
                    self._parse_rss_item(node, feed_label)
                    for node in nodes[: self._max_items_per_feed]
                )
                if entry is not None
            ]
        if tag == "feed":
            nodes = root.findall("./{*}entry") or root.findall("./entry")
            return [
                entry
                for entry in (
                    self._parse_atom_entry(node, feed_label)
                    for node in nodes[: self._max_items_per_feed]
                )
                if entry is not None
            ]
        raise ValueError("unsupported feed format; expected RSS or Atom")

    def _parse_rss_item(self, node: Any, feed_label: str) -> Optional[Dict[str, Any]]:
        return self._build_entry(
            title=self._text(node, "title"),
            summary=self._text(node, "description") or self._text(node, "summary"),
            url=self._text(node, "link"),
            source_label=feed_label,
            published_raw=self._text(node, "pubDate") or self._text(node, "published"),
        )

    def _parse_atom_entry(self, node: Any, feed_label: str) -> Optional[Dict[str, Any]]:
        url = ""
        for link in node.findall("./{*}link") or node.findall("./link"):
            rel = (link.attrib.get("rel") or "alternate").lower()
            href = (link.attrib.get("href") or "").strip()
            if rel == "alternate" and href:
                url = href
                break
            if not url and href:
                url = href
        return self._build_entry(
            title=self._text(node, "title"),
            summary=self._text(node, "summary") or self._text(node, "content"),
            url=url,
            source_label=feed_label,
            published_raw=self._text(node, "published") or self._text(node, "updated"),
        )

    def _build_entry(
        self,
        *,
        title: str,
        summary: str,
        url: str,
        source_label: str,
        published_raw: str,
    ) -> Optional[Dict[str, Any]]:
        clean_title = self._clean_text(title)[:300]
        clean_summary = self._clean_text(summary)[:500]
        clean_url = (url or "").strip()
        if not clean_title and not clean_url:
            return None
        if clean_url:
            parsed = urlparse(clean_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return None
        return {
            "title": clean_title or clean_url,
            "summary": clean_summary,
            "url": clean_url,
            "source": source_label,
            "published_raw": published_raw,
        }

    def _entry_to_result(self, entry: Dict[str, Any], *, feed_url: str) -> Optional[SearchResult]:
        url = str(entry.get("url") or "").strip()
        title = str(entry.get("title") or "").strip()
        if not title and not url:
            return None
        source = str(entry.get("source") or "").strip() or self._feed_label_from_url(feed_url)
        if not source.lower().endswith("(rss)") and "rss" not in source.lower():
            source = f"{source} (RSS)"
        return SearchResult(
            title=title or url,
            snippet=str(entry.get("summary") or "")[:500],
            url=url,
            source=source,
            published_date=self._format_published(entry.get("published_raw")),
        )

    def _soft_age_filter(self, results: List[SearchResult], *, days: int) -> List[SearchResult]:
        cutoff = datetime.now(timezone.utc).date().toordinal() - max(1, int(days))
        kept: List[SearchResult] = []
        for item in results:
            if not item.published_date:
                kept.append(item)
                continue
            try:
                pub = datetime.strptime(item.published_date[:10], "%Y-%m-%d").date()
            except ValueError:
                kept.append(item)
                continue
            if pub.toordinal() >= cutoff:
                kept.append(item)
        return kept

    @classmethod
    def _query_tokens(cls, query: str) -> List[str]:
        tokens: List[str] = []
        for raw in cls._TOKEN_RE.findall(query or ""):
            token = raw.strip().lower()
            if len(token) < 2 or token in cls._STOP_TOKENS:
                continue
            if token not in tokens:
                tokens.append(token)
        return tokens

    @classmethod
    def _matches_query(cls, result: SearchResult, query_tokens: List[str]) -> bool:
        if not query_tokens:
            return True
        haystack = f"{result.title} {result.snippet} {result.url}".lower()
        return any(token in haystack for token in query_tokens)

    @staticmethod
    def _format_published(value: Any) -> Optional[str]:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError):
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return raw[:32]
        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.strftime("%Y-%m-%d")

    @classmethod
    def _feed_label(cls, root: Any, feed_url: str) -> str:
        channel = root.find("./channel")
        if channel is not None:
            title = cls._text(channel, "title")
            if title:
                return title[:80]
        title = cls._text(root, "title")
        if title:
            return title[:80]
        return cls._feed_label_from_url(feed_url)

    @staticmethod
    def _feed_label_from_url(feed_url: str) -> str:
        try:
            host = urlparse(feed_url).netloc.replace("www.", "")
            return host or "RSS"
        except Exception:  # broad-exception: optional_metadata - Invalid URL keeps generic label.
            return "RSS"

    @staticmethod
    def _feed_host(feed_url: str) -> str:
        try:
            return urlparse(feed_url).netloc.replace("www.", "") or "unknown"
        except Exception:  # broad-exception: optional_metadata - Diagnostics use stable host label.
            return "unknown"

    @staticmethod
    def _strip_ns(tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    @classmethod
    def _text(cls, node: Any, name: str) -> str:
        found = node.find(f"./{{*}}{name}")
        if found is None:
            found = node.find(f"./{name}")
        if found is None:
            return ""
        text = found.text if found.text is not None else ""
        if not text and len(list(found)):
            text = "".join(found.itertext())
        return (text or "").strip()

    @classmethod
    def _clean_text(cls, value: str) -> str:
        plain = cls._html_unescape(cls._HTML_TAG_RE.sub(" ", value or ""))
        return cls._WHITESPACE_RE.sub(" ", plain).strip()
