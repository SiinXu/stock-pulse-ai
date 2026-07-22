"""Search orchestration, fallback, batching, and formatting methods."""

if not globals().get("_SEARCH_FACADE_LOADING", False):
    from src.search_service import (
        logging,
        time,
        List,
        Dict,
        Any,
        Optional,
        record_provider_run_started,
        exception_chain_redaction_values,
        log_safe_exception,
        logger,
        _SEARCH_REQUEST_FAILED,
        _log_search_failure,
        SearchResponse,
        _stabilize_failed_search_response,
        TavilySearchProvider,
        BraveSearchProvider,
    )


class _OrchestrationMethods:
    """Source container rebound onto ``SearchService`` by the facade."""

    def search_stock_news(
        self,
        stock_code: str,
        stock_name: str,
        max_results: int = 5,
        focus_keywords: Optional[List[str]] = None
    ) -> SearchResponse:
        """
        搜索股票相关新闻
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            max_results: 最大返回结果数
            focus_keywords: 重点关注的关键词列表
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
        Returns:
            SearchResponse 对象
        """
        # Strategy window priority: ultra_short/short/medium/long = 1/3/7/30 Day,
        # Will unify the constraint imposed by NEWS_MAX_AGE_DAYS.
        search_days = self._effective_news_window_days()
        provider_max_results = self._provider_request_size(max_results)
        prefer_chinese = self._should_prefer_chinese_news(
            stock_code,
            stock_name,
            focus_keywords=focus_keywords,
        )

        # Build search query (optimize search effect)
        is_foreign = self._is_foreign_stock(stock_code)
        if focus_keywords:
            # If keywords are provided, use them directly as queries.
            query = " ".join(focus_keywords)
        elif prefer_chinese:
            query = f"{stock_name} {stock_code} 股票 最新消息"
        elif is_foreign:
            # Use English search keywords for Hong Kong/U.S. stocks
            query = f"{stock_name} {stock_code} stock latest news"
        else:
            # Default main query: Stock Name + Core Keywords
            query = f"{stock_name} {stock_code} 股票 最新消息"

        logger.info(
            (
                "搜索股票新闻: %s(%s), query='%s', 时间范围: 近%s天 "
                "(profile=%s, NEWS_MAX_AGE_DAYS=%s, prefer_chinese=%s), 目标条数=%s, provider请求条数=%s"
            ),
            stock_name,
            stock_code,
            query,
            search_days,
            self.news_strategy_profile,
            self.news_max_age_days,
            prefer_chinese,
            max_results,
            provider_max_results,
        )

        cache_key = self._cache_key(
            (
                f"{query}|target={stock_code}:{stock_name}|"
                f"news_pref={'zh' if prefer_chinese else 'default'}"
            ),
            max_results,
            search_days,
        )
        cached, cache_owner, cache_event = self._get_cached_or_reserve(cache_key)
        if cached is not None:
            cached = _stabilize_failed_search_response(cached)
            logger.info(f"使用缓存搜索结果: {stock_name}({stock_code})")
            self._record_news_search_run(
                provider=cached.provider or "SearchCache",
                operation="search_stock_news_cache",
                success=bool(cached.success),
                latency_ms=0,
                record_count=len(cached.results or []),
                cache_hit=True,
                error_message=cached.error_message,
            )
            return cached

        if not cache_owner and cache_event is not None:
            cached = self._wait_for_cached(cache_key, cache_event)
            if cached is not None:
                cached = _stabilize_failed_search_response(cached)
                logger.info(f"使用并发填充后的缓存搜索结果: {stock_name}({stock_code})")
                self._record_news_search_run(
                    provider=cached.provider or "SearchCache",
                    operation="search_stock_news_cache_wait",
                    success=bool(cached.success),
                    latency_ms=0,
                    record_count=len(cached.results or []),
                    cache_hit=True,
                    error_message=cached.error_message,
                )
                return cached
            cached, cache_owner, cache_event = self._get_cached_or_reserve(cache_key)
            if cached is not None:
                cached = _stabilize_failed_search_response(cached)
                logger.info(f"使用等待后命中的缓存搜索结果: {stock_name}({stock_code})")
                self._record_news_search_run(
                    provider=cached.provider or "SearchCache",
                    operation="search_stock_news_cache_retry",
                    success=bool(cached.success),
                    latency_ms=0,
                    record_count=len(cached.results or []),
                    cache_hit=True,
                    error_message=cached.error_message,
                )
                return cached

        try:
            # Try each search engine sequentially (if empty after filtering, try the next engine)
            had_provider_success = False
            best_ranked_response: Optional[SearchResponse] = None
            best_ranked_stats: Optional[Dict[str, int]] = None
            for provider in self._providers:
                if not provider.is_available:
                    continue

                search_kwargs: Dict[str, Any] = {}
                if isinstance(provider, TavilySearchProvider):
                    search_kwargs["topic"] = "news"
                elif isinstance(provider, BraveSearchProvider):
                    search_kwargs.update(
                        self._brave_search_locale(
                            stock_code,
                            prefer_chinese=prefer_chinese,
                        )
                    )

                started_at = time.monotonic()
                try:
                    record_provider_run_started(
                        data_type="news_search",
                        provider=provider.name,
                        operation="search_stock_news",
                    )
                    response = provider.search(query, provider_max_results, days=search_days, **search_kwargs)
                    response = _stabilize_failed_search_response(response)
                except Exception as exc:
                    self._record_news_search_run(
                        provider=provider.name,
                        operation="search_stock_news",
                        success=False,
                        latency_ms=self._elapsed_ms(started_at),
                        error_type=type(exc).__name__,
                        error_message=_SEARCH_REQUEST_FAILED,
                    )
                    raise
                filtered_response = self._filter_news_response(
                    response,
                    search_days=search_days,
                    max_results=provider_max_results,
                    log_scope=f"{stock_code}:{provider.name}:stock_news",
                )
                had_provider_success = had_provider_success or bool(response.success)

                if filtered_response.success and filtered_response.results:
                    language_response, _preferred_count = self._prioritize_news_language(
                        filtered_response,
                        prefer_chinese=prefer_chinese,
                    )
                    ranked_response = self._rank_news_response(
                        language_response,
                        stock_code=stock_code,
                        stock_name=stock_name,
                        prefer_chinese=prefer_chinese,
                        max_results=provider_max_results,
                        log_scope=f"{stock_code}:{provider.name}:stock_news",
                    )
                    admitted_response = self._filter_ranked_news_for_context(
                        ranked_response,
                        log_scope=f"{stock_code}:{provider.name}:stock_news",
                    )
                    limited_response = self._limit_search_response(
                        admitted_response,
                        max_results=max_results,
                    )
                    admitted_count = len(limited_response.results or [])
                    self._record_news_search_run(
                        provider=provider.name,
                        operation="search_stock_news",
                        success=bool(limited_response.success and limited_response.results),
                        latency_ms=self._elapsed_ms(started_at),
                        record_count=admitted_count,
                        error_type=None if admitted_count else "NoUsableNews",
                        error_message=None if admitted_count else (
                            response.error_message or "过滤后无有效新闻"
                        ),
                    )
                    if not admitted_count:
                        logger.info(
                            "%s 搜索成功但准入过滤后无有效新闻，继续尝试下一引擎",
                            provider.name,
                        )
                        continue

                    stats = self._news_relevance_stats(
                        limited_response,
                        prefer_chinese=prefer_chinese,
                    )
                    if self._is_better_ranked_news_response(
                        limited_response,
                        candidate_stats=stats,
                        best_response=best_ranked_response,
                        best_stats=best_ranked_stats,
                        prefer_chinese=prefer_chinese,
                    ):
                        best_ranked_response = limited_response
                        best_ranked_stats = stats

                    if stats["direct_count"] > 0 and (
                        not prefer_chinese or stats["preferred_direct_count"] > 0
                    ):
                        logger.info(
                            "%s 搜索成功，识别到 %s 条直接个股新闻，优先返回",
                            provider.name,
                            stats["direct_count"],
                        )
                        self._put_cache(cache_key, limited_response)
                        return limited_response

                    if prefer_chinese and stats["direct_count"] > 0:
                        logger.info(
                            "%s 搜索成功，识别到 %s 条直接个股新闻但缺少中文直接命中，继续尝试下一引擎",
                            provider.name,
                            stats["direct_count"],
                        )
                        continue

                    if prefer_chinese and stats["preferred_count"] >= max_results:
                        logger.info(
                            "%s 搜索成功，中文结果已满足目标条数但缺少直接个股命中，继续尝试下一引擎",
                            provider.name,
                        )
                        continue

                    if prefer_chinese and stats["preferred_count"] > 0:
                        logger.info(
                            "%s 搜索成功，识别到 %s/%s 条中文新闻但缺少直接个股命中，继续尝试下一引擎",
                            provider.name,
                            stats["preferred_count"],
                            len(limited_response.results),
                        )
                    else:
                        logger.info(
                            "%s 搜索成功但未识别直接个股新闻，继续尝试下一引擎",
                            provider.name,
                        )
                else:
                    filtered_count = len(filtered_response.results or []) if filtered_response.success else 0
                    self._record_news_search_run(
                        provider=provider.name,
                        operation="search_stock_news",
                        success=bool(filtered_response.success and filtered_response.results),
                        latency_ms=self._elapsed_ms(started_at),
                        record_count=filtered_count,
                        error_type=None if filtered_count else "NoUsableNews",
                        error_message=None if filtered_count else (
                            response.error_message or "过滤后无有效新闻"
                        ),
                    )
                    if response.success and not filtered_response.results:
                        logger.info(
                            "%s 搜索成功但过滤后无有效新闻，继续尝试下一引擎",
                            provider.name,
                        )
                    else:
                        _log_search_failure(
                            provider=provider.name,
                            error_code="stock_news_provider_failed",
                        )

            if best_ranked_response is not None:
                self._put_cache(cache_key, best_ranked_response)
                return best_ranked_response

            if had_provider_success:
                return SearchResponse(
                    query=query,
                    results=[],
                    provider="Filtered",
                    success=True,
                    error_message=None,
                )

            # All engines failed
            return SearchResponse(
                query=query,
                results=[],
                provider="None",
                success=False,
                error_message="所有搜索引擎都不可用或搜索失败"
            )
        finally:
            if cache_owner and cache_event is not None:
                self._release_cache_fill(cache_key, cache_event)

    def search_stock_events(
        self,
        stock_code: str,
        stock_name: str,
        event_types: Optional[List[str]] = None
    ) -> SearchResponse:
        """
        搜索股票特定事件（年报预告、减持等）
\x20\x20\x20\x20\x20\x20\x20\x20
        专门针对交易决策相关的重要事件进行搜索
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            event_types: 事件类型列表
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
        Returns:
            SearchResponse 对象
        """
        if event_types is None:
            if self._is_foreign_stock(stock_code):
                event_types = ["earnings report", "insider selling", "quarterly results"]
            else:
                event_types = ["年报预告", "减持公告", "业绩快报"]

        # Build targeted query
        event_query = " OR ".join(event_types)
        query = f"{stock_name} ({event_query})"

        logger.info(f"搜索股票事件: {stock_name}({stock_code}) - {event_types}")

        # Try various search engines sequentially
        for provider in self._providers:
            if not provider.is_available:
                continue

            response = provider.search(query, max_results=5)

            if response.success:
                return response

        return SearchResponse(
            query=query,
            results=[],
            provider="None",
            success=False,
            error_message="事件搜索失败"
        )

    def search_comprehensive_intel(
        self,
        stock_code: str,
        stock_name: str,
        max_searches: int = 3
    ) -> Dict[str, SearchResponse]:
        """
        多维度情报搜索（同时使用多个引擎、多个维度）
\x20\x20\x20\x20\x20\x20\x20\x20
        搜索维度：
        1. 最新消息 - 近期新闻动态
        2. 风险排查 - 减持、处罚、利空
        3. 业绩预期 - 年报预告、业绩快报
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            max_searches: 最大搜索次数
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
        Returns:
            {维度名称: SearchResponse} 字典
        """
        results = {}
        search_count = 0

        is_foreign = self._is_foreign_stock(stock_code)
        is_index_etf = self.is_index_or_etf(stock_code, stock_name)

        if is_foreign:
            search_dimensions = [
                {
                    'name': 'latest_news',
                    'query': f"{stock_name} {stock_code} latest news events",
                    'desc': '最新消息',
                    'tavily_topic': 'news',
                    'strict_freshness': True,
                },
                {
                    'name': 'market_analysis',
                    'query': f"{stock_name} analyst rating target price report",
                    'desc': '机构分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'risk_check',
                    'query': (
                        f"{stock_name} {stock_code} index performance outlook tracking error"
                        if is_index_etf else f"{stock_name} risk insider selling lawsuit litigation"
                    ),
                    'desc': '风险排查',
                    'tavily_topic': None if is_index_etf else 'news',
                    'strict_freshness': not is_index_etf,
                },
                {
                    'name': 'earnings',
                    'query': (
                        f"{stock_name} {stock_code} index performance composition outlook"
                        if is_index_etf else f"{stock_name} earnings revenue profit growth forecast"
                    ),
                    'desc': '业绩预期',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'industry',
                    'query': (
                        f"{stock_name} {stock_code} index sector allocation holdings"
                        if is_index_etf else f"{stock_name} industry competitors market share outlook"
                    ),
                    'desc': '行业分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
            ]
        else:
            search_dimensions = [
                {
                    'name': 'latest_news',
                    'query': f"{stock_name} {stock_code} 最新 新闻 重大 事件",
                    'desc': '最新消息',
                    'tavily_topic': 'news',
                    'strict_freshness': True,
                },
                {
                    'name': 'market_analysis',
                    'query': f"{stock_name} 研报 目标价 评级 深度分析",
                    'desc': '机构分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'risk_check',
                    'query': (
                        f"{stock_name} 指数走势 跟踪误差 净值 表现"
                        if is_index_etf else f"{stock_name} 减持 处罚 违规 诉讼 利空 风险"
                    ),
                    'desc': '风险排查',
                    'tavily_topic': None if is_index_etf else 'news',
                    'strict_freshness': not is_index_etf,
                },
                {
                    'name': 'announcements',
                    'query': (
                        f"{stock_name} {stock_code} 公告 指数调整 成分变化"
                        if is_index_etf else f"{stock_name} {stock_code} 公司公告 重要公告 上交所 深交所 cninfo"
                    ),
                    'desc': '公司公告',
                    'tavily_topic': 'news',
                    'strict_freshness': True,
                },
                {
                    'name': 'earnings',
                    'query': (
                        f"{stock_name} 指数成分 净值 跟踪表现"
                        if is_index_etf else f"{stock_name} 业绩预告 财报 营收 净利润 同比增长"
                    ),
                    'desc': '业绩预期',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'industry',
                    'query': (
                        f"{stock_name} 指数成分股 行业配置 权重"
                        if is_index_etf else f"{stock_name} 所在行业 竞争对手 市场份额 行业前景"
                    ),
                    'desc': '行业分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
            ]

        search_days = self._effective_news_window_days()
        target_per_dimension = 3
        provider_max_results = self._provider_request_size(target_per_dimension)

        logger.info(
            (
                "开始多维度情报搜索: %s(%s), 时间范围: 近%s天 "
                "(profile=%s, NEWS_MAX_AGE_DAYS=%s), 目标条数=%s, provider请求条数=%s"
            ),
            stock_name,
            stock_code,
            search_days,
            self.news_strategy_profile,
            self.news_max_age_days,
            target_per_dimension,
            provider_max_results,
        )

        # Rotate between different search engines
        provider_index = 0

        for dim in search_dimensions:
            if search_count >= max_searches:
                break

            # Select search engine (rotate usage).
            available_providers = [p for p in self._providers if p.is_available]
            if not available_providers:
                break

            provider = available_providers[provider_index % len(available_providers)]
            provider_index += 1

            request_days = (
                self.ANALYTICAL_INTEL_LOOKBACK_DAYS
                if dim['name'] in self.ANALYTICAL_INTEL_DIMENSIONS
                else search_days
            )

            logger.info(
                "[情报搜索] %s: 使用 %s，请求窗口: 近%s天",
                dim['desc'],
                provider.name,
                request_days,
            )

            if isinstance(provider, TavilySearchProvider) and dim.get('tavily_topic'):
                response = provider.search(
                    dim['query'],
                    max_results=provider_max_results,
                    days=request_days,
                    topic=dim['tavily_topic'],
                )
            else:
                response = provider.search(
                    dim['query'],
                    max_results=provider_max_results,
                    days=request_days,
                )
            response = _stabilize_failed_search_response(response)
            if dim['strict_freshness']:
                filtered_response = self._filter_news_response(
                    response,
                    search_days=search_days,
                    max_results=provider_max_results,
                    log_scope=f"{stock_code}:{provider.name}:{dim['name']}",
                )
            elif dim['name'] in self.ANALYTICAL_INTEL_DIMENSIONS:
                filtered_response = self._filter_news_response(
                    response,
                    search_days=self.ANALYTICAL_INTEL_LOOKBACK_DAYS,
                    max_results=provider_max_results,
                    keep_unknown=True,
                    log_scope=f"{stock_code}:{provider.name}:{dim['name']}",
                )
            else:
                filtered_response = self._normalize_and_limit_response(
                    response,
                    max_results=provider_max_results,
                )
            filtered_response = self._rank_news_response(
                filtered_response,
                stock_code=stock_code,
                stock_name=stock_name,
                prefer_chinese=self._should_prefer_chinese_news(stock_code, stock_name),
                max_results=provider_max_results,
                log_scope=f"{stock_code}:{provider.name}:{dim['name']}:rank",
            )
            filtered_response = self._filter_ranked_news_for_context(
                filtered_response,
                log_scope=f"{stock_code}:{provider.name}:{dim['name']}:admission",
            )
            filtered_response = self._limit_search_response(
                filtered_response,
                max_results=target_per_dimension,
            )
            results[dim['name']] = filtered_response
            search_count += 1

            if response.success:
                logger.info(
                    "[情报搜索] %s: 原始=%s条, 过滤后=%s条",
                    dim['desc'],
                    len(response.results),
                    len(filtered_response.results),
                )
            else:
                filtered_response.error_message = response.error_message
                _log_search_failure(
                    provider=provider.name,
                    error_code="search_dimension_failed",
                )

            # Avoid excessive requests due to short delays
            time.sleep(0.5)

        return results

    def format_intel_report(self, intel_results: Dict[str, SearchResponse], stock_name: str) -> str:
        """
        格式化情报搜索结果为报告
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            intel_results: 多维度搜索结果
            stock_name: 股票名称
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
        Returns:
            格式化的情报报告文本
        """
        lines = [f"【{stock_name} 情报搜索结果】"]

        # Dimension display order
        display_order = ['latest_news', 'announcements', 'market_analysis', 'risk_check', 'earnings', 'industry']

        dim_labels = {
            'latest_news': '📰 最新消息',
            'announcements': '📋 公司公告',
            'market_analysis': '📈 机构分析',
            'risk_check': '⚠️ 风险排查',
            'earnings': '📊 业绩预期',
            'industry': '🏭 行业分析',
        }

        for dim_name in display_order:
            if dim_name not in intel_results:
                continue

            resp = intel_results[dim_name]

            # Get dimension description
            dim_desc = dim_labels.get(dim_name, dim_name)

            lines.append(f"\n{dim_desc} (来源: {resp.provider}):")
            if resp.success and resp.results:
                # Increase display count
                for i, r in enumerate(resp.results[:4], 1):
                    date_str = f" [{r.published_date}]" if r.published_date else ""
                    lines.append(f"  {i}. {r.title}{date_str}")
                    # If the summary is too short, the information may be insufficient.
                    snippet = r.snippet[:150] if len(r.snippet) > 20 else r.snippet
                    lines.append(f"     {snippet}...")
                    if r.relevance_category or r.relevance_reasons:
                        relevance_parts = []
                        if r.relevance_category:
                            relevance_parts.append(r.relevance_category)
                        if r.relevance_score is not None:
                            relevance_parts.append(f"score={r.relevance_score}")
                        if r.relevance_reasons:
                            relevance_parts.append(f"依据: {'；'.join(r.relevance_reasons[:3])}")
                        lines.append(f"     关联度: {'; '.join(relevance_parts)}")
            else:
                lines.append("  未找到相关信息")

        return "\n".join(lines)

    def batch_search(
        self,
        stocks: List[Dict[str, str]],
        max_results_per_stock: int = 3,
        delay_between: float = 1.0
    ) -> Dict[str, SearchResponse]:
        """
        Batch search news for multiple stocks.
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            stocks: List of stocks
            max_results_per_stock: Max results per stock
            delay_between: Delay between searches (seconds)
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
        Returns:
            Dict of results
        """
        results = {}

        for i, stock in enumerate(stocks):
            if i > 0:
                time.sleep(delay_between)

            code = stock.get('code', '')
            name = stock.get('name', '')

            response = self.search_stock_news(code, name, max_results_per_stock)
            results[code] = response

        return results

    def search_stock_price_fallback(
        self,
        stock_code: str,
        stock_name: str,
        max_attempts: int = 3,
        max_results: int = 5
    ) -> SearchResponse:
        """
        Enhance search when data sources fail.
\x20\x20\x20\x20\x20\x20\x20\x20
        When all data sources (efinance, akshare, tushare, baostock, etc.) fail to get
        stock data, use search engines to find stock trends and price info as supplemental data for AI analysis.
\x20\x20\x20\x20\x20\x20\x20\x20
        Strategy:
        1. Search using multiple keyword templates
        2. Try all available search engines for each keyword
        3. Aggregate and deduplicate results
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            stock_code: Stock Code
            stock_name: Stock Name
            max_attempts: Max search attempts (using different keywords)
            max_results: Max results to return
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
        Returns:
            SearchResponse object with aggregated results
        """

        if not self.is_available:
            return SearchResponse(
                query=f"{stock_name} 股价走势",
                results=[],
                provider="None",
                success=False,
                error_message="未配置搜索能力"
            )

        logger.info(f"[增强搜索] 数据源失败，启动增强搜索: {stock_name}({stock_code})")

        all_results = []
        seen_urls = set()
        successful_providers = []

        # Use multiple keyword templates to search
        is_foreign = self._is_foreign_stock(stock_code)
        keywords = self.ENHANCED_SEARCH_KEYWORDS_EN if is_foreign else self.ENHANCED_SEARCH_KEYWORDS
        for i, keyword_template in enumerate(keywords[:max_attempts]):
            query = keyword_template.format(name=stock_name, code=stock_code)

            logger.info(f"[增强搜索] 第 {i+1}/{max_attempts} 次搜索: {query}")

            # Try various search engines sequentially
            for provider in self._providers:
                if not provider.is_available:
                    continue

                try:
                    response = provider.search(query, max_results=3)

                    if response.success and response.results:
                        # Deduplicate and add results
                        for result in response.results:
                            if result.url not in seen_urls:
                                seen_urls.add(result.url)
                                all_results.append(result)

                        if provider.name not in successful_providers:
                            successful_providers.append(provider.name)

                        logger.info(f"[增强搜索] {provider.name} 返回 {len(response.results)} 条结果")
                        break  # Continue with the next keyword after a successful search
                    else:
                        logger.debug(f"[增强搜索] {provider.name} 无结果或失败")

                except Exception as exc:  # broad-exception: fallback_recorded - One provider failure is safely logged before trying the remaining fallback chain.
                    log_safe_exception(
                        logger,
                        "Enhanced search provider request failed",
                        exc,
                        error_code="enhanced_search_provider_request_failed",
                        level=logging.WARNING,
                        context={"provider": provider.name},
                        exception_redaction_values=exception_chain_redaction_values(exc),
                    )
                    continue

            # Avoid excessive requests due to short delays
            if i < max_attempts - 1:
                time.sleep(0.5)

        # Summary results
        if all_results:
            # Truncate top max_results items
            final_results = all_results[:max_results]
            provider_str = ", ".join(successful_providers) if successful_providers else "None"

            logger.info(f"[增强搜索] 完成，共获取 {len(final_results)} 条结果（来源: {provider_str}）")

            return SearchResponse(
                query=f"{stock_name}({stock_code}) 股价走势",
                results=final_results,
                provider=provider_str,
                success=True,
            )
        else:
            logger.warning(f"[增强搜索] 所有搜索均未返回结果")
            return SearchResponse(
                query=f"{stock_name}({stock_code}) 股价走势",
                results=[],
                provider="None",
                success=False,
                error_message="增强搜索未找到相关信息"
            )

    def search_stock_with_enhanced_fallback(
        self,
        stock_code: str,
        stock_name: str,
        include_news: bool = True,
        include_price: bool = False,
        max_results: int = 5
    ) -> Dict[str, SearchResponse]:
        """
        综合搜索接口（支持新闻和股价信息）
\x20\x20\x20\x20\x20\x20\x20\x20
        当 include_price=True 时，会同时搜索新闻和股价信息。
        主要用于数据源完全失败时的兜底方案。
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            include_news: 是否搜索新闻
            include_price: 是否搜索股价/走势信息
            max_results: 每类搜索的最大结果数
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
        Returns:
            {'news': SearchResponse, 'price': SearchResponse} 字典
        """
        results = {}

        if include_news:
            results['news'] = self.search_stock_news(
                stock_code,
                stock_name,
                max_results=max_results
            )

        if include_price:
            results['price'] = self.search_stock_price_fallback(
                stock_code,
                stock_name,
                max_attempts=3,
                max_results=max_results
            )

        return results

    def format_price_search_context(self, response: SearchResponse) -> str:
        """
        将股价搜索结果格式化为 AI 分析上下文
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            response: 搜索响应对象
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
        Returns:
            格式化的文本，可直接用于 AI 分析
        """
        if not response.success or not response.results:
            return "【股价走势搜索】未找到相关信息，请以其他渠道数据为准。"

        lines = [
            f"【股价走势搜索结果】（来源: {response.provider}）",
            "⚠️ 注意：以下信息来自网络搜索，仅供参考，可能存在延迟或不准确。",
            ""
        ]

        for i, result in enumerate(response.results, 1):
            date_str = f" [{result.published_date}]" if result.published_date else ""
            lines.append(f"{i}. 【{result.source}】{result.title}{date_str}")
            lines.append(f"   {result.snippet[:200]}...")
            lines.append("")

        return "\n".join(lines)
