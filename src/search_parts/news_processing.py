"""News identity, ranking, filtering, and normalization methods."""

if not globals().get("_SEARCH_FACADE_LOADING", False):
    from src.search_service import (
        re,
        time,
        date,
        datetime,
        timedelta,
        timezone,
        parsedate_to_datetime,
        List,
        Dict,
        Any,
        Optional,
        Tuple,
        unquote,
        urlparse,
        record_provider_run,
        logger,
        SearchResult,
        SearchResponse,
    )


class _NewsProcessingMethods:
    """Source container rebound onto ``SearchService`` by the facade."""

    @classmethod
    def _provider_request_size(cls, max_results: int) -> int:
        """Apply light overfetch before time filtering to avoid sparse outputs."""
        target = max(1, int(max_results))
        return max(target, min(target * cls.NEWS_OVERSAMPLE_FACTOR, cls.NEWS_OVERSAMPLE_MAX))

    @staticmethod
    def _append_unique(values: List[str], value: Optional[str]) -> None:
        cleaned = (value or "").strip()
        if cleaned and cleaned not in values:
            values.append(cleaned)

    @classmethod
    def _stock_code_identity_terms(cls, stock_code: str) -> List[str]:
        """Return code/ticker variants that should count as strong identity hits."""
        raw = (stock_code or "").strip()
        if not raw:
            return []

        terms: List[str] = []
        upper = raw.upper()
        code_for_variants = upper
        if "." in upper:
            base, suffix = upper.rsplit(".", 1)
            if suffix == "HK" and base.isdigit() and 1 <= len(base) <= 5:
                code_for_variants = f"HK{base.zfill(5)}"
            elif suffix in {"SH", "SZ", "SS", "BJ"} and base.isdigit() and len(base) == 6:
                code_for_variants = base
            elif suffix == "US" and re.fullmatch(r"[A-Z]{1,5}", base):
                code_for_variants = base

        is_us_ticker = bool(cls._US_STOCK_RE.match(code_for_variants))
        if not is_us_ticker:
            cls._append_unique(terms, raw)
            cls._append_unique(terms, upper)
            if code_for_variants != upper:
                cls._append_unique(terms, code_for_variants)

        lower = code_for_variants.lower()
        hk_digits = ""
        if lower.startswith("hk"):
            hk_digits = re.sub(r"\D", "", code_for_variants)
        elif code_for_variants.isdigit() and len(code_for_variants) == 5:
            hk_digits = code_for_variants

        if hk_digits:
            padded = hk_digits.zfill(5)
            short = str(int(hk_digits)) if hk_digits.isdigit() else hk_digits.lstrip("0")
            cls._append_unique(terms, padded)
            cls._append_unique(terms, f"HK{padded}")
            cls._append_unique(terms, f"{padded}.HK")
            cls._append_unique(terms, f"{short}.HK")
            cls._append_unique(terms, f"HKEX:{short}")
            return terms

        if code_for_variants.isdigit() and len(code_for_variants) == 6:
            suffix = ".SH" if code_for_variants.startswith(("5", "6", "9")) else ".SZ"
            cls._append_unique(terms, f"{code_for_variants}{suffix}")
            return terms

        if cls._US_STOCK_RE.match(code_for_variants):
            cls._append_unique(terms, f"${code_for_variants}")
            cls._append_unique(terms, f"NASDAQ:{code_for_variants}")
            cls._append_unique(terms, f"NYSE:{code_for_variants}")
            if len(code_for_variants) > 1:
                cls._append_unique(terms, code_for_variants)
            return terms

        return terms

    @classmethod
    def _company_identity_terms(cls, stock_name: str) -> List[str]:
        """Return conservative company-name variants for relevance matching."""
        raw = (stock_name or "").strip()
        if not raw:
            return []

        terms: List[str] = []
        cls._append_unique(terms, raw)

        without_market_suffix = re.sub(r"[-－（(].*$", "", raw).strip()
        cls._append_unique(terms, without_market_suffix)

        if cls._contains_chinese_text(raw):
            cleaned = re.sub(
                r"(股份有限公司|有限责任公司|有限公司|控股集团|控股|集团|股份|公司)$",
                "",
                without_market_suffix,
            ).strip()
            if len(cleaned) >= 4:
                cls._append_unique(terms, cleaned)
        else:
            cleaned = re.sub(
                r"\b(incorporated|inc|corporation|corp|company|co|plc|ltd|limited|holdings?)\.?$",
                "",
                without_market_suffix,
                flags=re.IGNORECASE,
            ).strip()
            if len(cleaned) >= 3:
                cls._append_unique(terms, cleaned)

        return terms

    @classmethod
    def _contains_identity_term(cls, text: str, term: str) -> bool:
        if not text or not term:
            return False

        if cls._contains_chinese_text(term):
            start = 0
            while True:
                index = text.find(term, start)
                if index < 0:
                    return False
                next_char = text[index + len(term):index + len(term) + 1]
                if next_char not in {"镇", "村", "县"}:
                    return True
                start = index + len(term)

        lower_text = text.lower()
        lower_term = term.lower()
        if lower_term.startswith("$"):
            return lower_term in lower_text

        pattern = r"(?<![A-Za-z0-9])" + re.escape(lower_term) + r"(?![A-Za-z0-9])"
        return bool(re.search(pattern, lower_text))

    @classmethod
    def _contains_stock_code_identity_term(cls, text: str, term: str) -> bool:
        if not text or not term:
            return False

        if cls._US_STOCK_RE.match(term) and term.upper() == term and not term.startswith("$"):
            ticker_pattern = f"(?:{re.escape(term)}|{re.escape(term.lower())})"
            pattern = (
                r"(?<![A-Za-z0-9$:.])"
                + ticker_pattern
                + r"(?=$|[^A-Za-z0-9.]|\.(?:US|us|O|o|N|n|NYSE|nyse|NASDAQ|nasdaq|AMEX|amex)\b)"
            )
            return bool(re.search(pattern, text))

        return cls._contains_identity_term(text, term)

    @classmethod
    def _contains_any_news_term(cls, text: str, terms: Tuple[str, ...]) -> bool:
        lower = (text or "").lower()
        return any(term.lower() in lower for term in terms)

    @classmethod
    def _contains_any_low_quality_news_term(cls, text: str, terms: Tuple[str, ...]) -> bool:
        lower = (text or "").lower()
        if not lower:
            return False

        for term in terms:
            normalized_term = term.lower()
            if not normalized_term:
                continue
            if normalized_term.isascii() and re.search(r"[a-z0-9]", normalized_term):
                pattern = r"(?<![A-Za-z0-9])" + re.escape(normalized_term) + r"(?![A-Za-z0-9])"
                if re.search(pattern, lower):
                    return True
                continue
            if normalized_term in lower:
                return True
        return False

    @staticmethod
    def _candidate_hostname(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if not raw or re.search(r"\s", raw):
            return ""

        parse_value = (
            raw
            if re.match(r"^[a-z][a-z0-9+.-]*://", raw) or raw.startswith("//")
            else f"//{raw}"
        )
        return (urlparse(parse_value).hostname or "").rstrip(".")

    @staticmethod
    def _source_resembles_hostname(value: Any) -> bool:
        raw = str(value or "").strip().lower()
        if not raw or re.search(r"\s", raw):
            return False
        if re.match(r"^[a-z][a-z0-9+.-]*://", raw) or raw.startswith("//"):
            return True
        return bool(re.search(r"\.[a-z0-9-]{2,}(?::\d+)?/?$", raw))

    @classmethod
    def _is_trusted_official_news_source(cls, item: SearchResult) -> bool:
        """Only trust official exemptions from trusted hosts; fallback to labels only when URL host is absent."""
        url_host = cls._candidate_hostname(item.url)
        source_label = str(item.source or "").strip().lower()
        source_host = (
            cls._candidate_hostname(item.source)
            if cls._source_resembles_hostname(item.source)
            else ""
        )

        if url_host:
            # Use the hostname when a URL is present, avoid misleading official approvals with source label/host.
            return any(
                url_host == official_host or url_host.endswith(f".{official_host}")
                for official_host in cls._OFFICIAL_SOURCE_HOSTS
            )

        if source_host:
            return any(
                source_host == official_host or source_host.endswith(f".{official_host}")
                for official_host in cls._OFFICIAL_SOURCE_HOSTS
            )

        return source_label in cls._OFFICIAL_SOURCE_LABELS

    @classmethod
    def _has_low_quality_news_page_signal(cls, item: SearchResult) -> bool:
        """Detect app/download/listing pages without relying on a domain blocklist."""
        content_text = " ".join(filter(None, [item.title, item.snippet])).lower()
        parsed_url = urlparse(item.url or "")
        url_surface = unquote(
            " ".join(filter(None, [parsed_url.netloc, parsed_url.path, parsed_url.query]))
        ).lower()

        has_app_context = cls._contains_any_low_quality_news_term(
            content_text,
            cls._LOW_QUALITY_APP_CONTEXT_TERMS,
        )
        has_app_metadata = cls._contains_any_low_quality_news_term(
            content_text,
            cls._LOW_QUALITY_APP_METADATA_TERMS,
        )
        has_download_action = cls._contains_any_low_quality_news_term(
            content_text,
            cls._LOW_QUALITY_DOWNLOAD_ACTION_TERMS,
        )
        has_download_intent = cls._contains_any_low_quality_news_term(
            content_text,
            cls._LOW_QUALITY_DOWNLOAD_INTENT_TERMS,
        )
        has_app_page_detail = cls._contains_any_low_quality_news_term(
            content_text,
            cls._LOW_QUALITY_APP_PAGE_DETAIL_TERMS,
        )
        has_file_size = bool(cls._LOW_QUALITY_FILE_SIZE_RE.search(content_text))
        has_rating = bool(cls._LOW_QUALITY_RATING_RE.search(content_text))
        has_url_signal = bool(cls._LOW_QUALITY_URL_RE.search(url_surface))
        has_business_app_metric = bool(cls._BUSINESS_APP_METRIC_RE.search(content_text))
        has_app_listing_detail = (
            has_file_size
            or has_rating
            or cls._contains_any_low_quality_news_term(
                content_text,
                (
                    "版本", "适用年龄", "开发者", "应用商店", "安卓版",
                    "苹果版", "官方版", "最新版", "version", "developer",
                    "package",
                ),
            )
        )
        has_strong_app_page_evidence = (
            has_app_listing_detail
            and (
                has_url_signal
                or has_download_intent
                or (has_download_action and has_app_metadata)
            )
        )
        has_business_app_metric_only = (
            has_business_app_metric
            and not has_strong_app_page_evidence
        )
        has_app_listing_context = (
            not has_business_app_metric_only
            and has_app_context
            and has_app_metadata
            and (has_download_action or has_download_intent)
            and (has_file_size or has_rating)
        )
        has_content_download_page = (
            not has_business_app_metric_only
            and (
                (has_download_intent and (has_app_page_detail or has_file_size or has_rating))
                or (has_download_action and (has_app_metadata or has_file_size))
            )
        )
        has_url_backed_download_page = (
            not has_business_app_metric_only
            and has_url_signal
            and (
                has_file_size
                or has_download_intent
                or (has_download_action and has_app_metadata)
                or (has_app_metadata and has_rating)
            )
        )

        return (
            has_content_download_page
            or has_app_listing_context
            or has_url_backed_download_page
        )

    @classmethod
    def _has_adult_service_spam_news_page_signal(cls, item: SearchResult) -> bool:
        """Detect adult-service spam by content signals instead of domain names."""
        combined_text = " ".join(
            filter(None, [item.title, item.snippet, item.source, item.url])
        ).lower()

        if cls._contains_any_news_term(
            combined_text,
            cls._ADULT_SERVICE_SPAM_STRONG_TERMS,
        ):
            return True
        has_contact_signal = bool(cls._ADULT_SERVICE_SPAM_CONTACT_RE.search(combined_text))
        has_remediation_context = cls._contains_any_news_term(
            combined_text,
            cls._ADULT_SERVICE_REMEDIATION_TERMS,
        )
        if has_remediation_context and not has_contact_signal:
            return False

        if (
            "外围" in combined_text
            and cls._contains_any_news_term(
                combined_text,
                ("上门", "同城", "约炮", "援交", "包夜", "大保健", "推油", "小姐", "技师"),
            )
        ):
            return True

        context_hits = sum(
            1
            for term in cls._ADULT_SERVICE_SPAM_CONTEXT_TERMS
            if term.lower() in combined_text
        )
        has_service_anchor = cls._contains_any_news_term(
            combined_text,
            ("小姐", "按摩", "足浴", "桑拿", "会所", "技师"),
        )
        has_adult_specific_anchor = cls._contains_any_news_term(
            combined_text,
            (
                "小姐", "约炮", "援交", "楼凤", "外围", "包夜",
                "大保健", "莞式", "推油", "成人", "色情",
            ),
        )
        if has_contact_signal:
            return has_adult_specific_anchor and cls._contains_any_news_term(
                combined_text,
                cls._ADULT_SERVICE_SPAM_CONTACT_CONTEXT_TERMS,
            )
        has_solicitation_signal = cls._contains_any_news_term(
            combined_text,
            cls._ADULT_SERVICE_SOLICITATION_TERMS,
        )
        has_ambiguous_adult_phrase = cls._contains_any_news_term(
            combined_text,
            cls._ADULT_SERVICE_SPAM_AMBIGUOUS_TERMS,
        )
        if has_ambiguous_adult_phrase:
            return has_service_anchor and has_solicitation_signal

        return (
            has_adult_specific_anchor
            and has_service_anchor
            and has_solicitation_signal
            and context_hits >= 3
        )

    @classmethod
    def _score_news_relevance(
        cls,
        item: SearchResult,
        *,
        stock_code: str,
        stock_name: str,
    ) -> SearchResult:
        """Attach conservative, explainable relevance metadata to one news item."""
        title = item.title or ""
        snippet = item.snippet or ""
        url = item.url or ""
        source = item.source or ""
        full_text = " ".join([title, snippet, url, source])

        score = 0
        direct_signal = 0
        reasons: List[str] = []
        has_stock_code_signal = False
        has_unambiguous_company_signal = False
        has_ambiguous_company_signal = False

        def add_reason(reason: str) -> None:
            if reason not in reasons and len(reasons) < 5:
                reasons.append(reason)

        for term in cls._stock_code_identity_terms(stock_code):
            if cls._contains_stock_code_identity_term(title, term):
                score += 55
                direct_signal += 55
                has_stock_code_signal = True
                add_reason(f"标题命中股票代码 {term}")
                break
        else:
            for term in cls._stock_code_identity_terms(stock_code):
                if cls._contains_stock_code_identity_term(snippet, term):
                    score += 34
                    direct_signal += 34
                    has_stock_code_signal = True
                    add_reason(f"摘要命中股票代码 {term}")
                    break
            else:
                for term in cls._stock_code_identity_terms(stock_code):
                    if cls._contains_stock_code_identity_term(url, term):
                        score += 18
                        direct_signal += 18
                        has_stock_code_signal = True
                        add_reason(f"链接命中股票代码 {term}")
                        break

        for term in cls._company_identity_terms(stock_name):
            ambiguous_en = (
                not cls._contains_chinese_text(term)
                and term.lower() in cls._AMBIGUOUS_EN_COMPANY_NAMES
            )
            title_score = 26 if ambiguous_en else 45
            snippet_score = 16 if ambiguous_en else 28
            if cls._contains_identity_term(title, term):
                score += title_score
                direct_signal += title_score
                if ambiguous_en:
                    has_ambiguous_company_signal = True
                else:
                    has_unambiguous_company_signal = True
                add_reason(f"标题命中公司名 {term}")
                break
            if cls._contains_identity_term(snippet, term):
                score += snippet_score
                direct_signal += snippet_score
                if ambiguous_en:
                    has_ambiguous_company_signal = True
                else:
                    has_unambiguous_company_signal = True
                add_reason(f"摘要命中公司名 {term}")
                break

        has_company_event = cls._contains_any_news_term(full_text, cls._COMPANY_EVENT_TERMS)
        if has_company_event and direct_signal > 0:
            score += 12
            ambiguous_name_only = (
                has_ambiguous_company_signal
                and not has_stock_code_signal
                and not has_unambiguous_company_signal
            )
            has_confirming_event = cls._contains_any_news_term(
                full_text,
                cls._AMBIGUOUS_EN_CONFIRMING_EVENT_TERMS,
            )
            if not ambiguous_name_only or has_confirming_event:
                direct_signal += 12
            add_reason("命中公告/财报/交易等公司事件词")

        if cls._is_trusted_official_news_source(item):
            score += 8
            add_reason("来源接近公告或交易所渠道")

        has_sector_signal = cls._contains_any_news_term(full_text, cls._SECTOR_NEWS_TERMS)
        has_macro_signal = cls._contains_any_news_term(full_text, cls._MACRO_NEWS_TERMS)

        if direct_signal >= 38:
            category = cls._DIRECT_NEWS_CATEGORY
        elif has_macro_signal and not direct_signal:
            category = cls._MACRO_NEWS_CATEGORY
            score = max(0, score - 12)
            add_reason("未命中目标公司身份，归为宏观/市场新闻")
        else:
            category = cls._SECTOR_NEWS_CATEGORY
            if has_sector_signal:
                score += 6
                add_reason("仅命中行业或板块背景")
            else:
                add_reason("未命中股票代码或公司全称，降级为背景新闻")

        score = max(0, min(100, score))
        return SearchResult(
            title=item.title,
            snippet=item.snippet,
            url=item.url,
            source=item.source,
            published_date=item.published_date,
            relevance_score=score,
            relevance_category=category,
            relevance_reasons=reasons,
        )

    @classmethod
    def _rank_news_response(
        cls,
        response: SearchResponse,
        *,
        stock_code: str,
        stock_name: str,
        prefer_chinese: bool,
        max_results: int,
        log_scope: str,
    ) -> SearchResponse:
        """Score and sort news so direct company items are not crowded out."""
        if not response.success or not response.results:
            return response

        scored_results = [
            cls._score_news_relevance(item, stock_code=stock_code, stock_name=stock_name)
            for item in response.results
        ]

        indexed_results = list(enumerate(scored_results))

        def sort_key(entry: Tuple[int, SearchResult]) -> Tuple[int, int, int, int]:
            index, result = entry
            category = result.relevance_category or cls._SECTOR_NEWS_CATEGORY
            category_rank = cls._NEWS_CATEGORY_PRIORITY.get(category, 9)
            language_rank = 0 if prefer_chinese and cls._is_chinese_news_result(result) else 1
            if not prefer_chinese:
                language_rank = 0
            score = result.relevance_score or 0
            return (category_rank, language_rank, -score, index)

        ranked_results = [result for _, result in sorted(indexed_results, key=sort_key)]
        limited_results = ranked_results[:max_results]
        category_counts = {
            cls._DIRECT_NEWS_CATEGORY: 0,
            cls._SECTOR_NEWS_CATEGORY: 0,
            cls._MACRO_NEWS_CATEGORY: 0,
        }
        for result in limited_results:
            if result.relevance_category in category_counts:
                category_counts[result.relevance_category] += 1
        if limited_results:
            top = limited_results[0]
            logger.info(
                "[新闻相关度] %s: direct=%s, sector=%s, macro=%s, top_score=%s, top_category=%s, reasons=%s",
                log_scope,
                category_counts[cls._DIRECT_NEWS_CATEGORY],
                category_counts[cls._SECTOR_NEWS_CATEGORY],
                category_counts[cls._MACRO_NEWS_CATEGORY],
                top.relevance_score,
                top.relevance_category,
                "；".join(top.relevance_reasons or []),
            )

        return SearchResponse(
            query=response.query,
            results=limited_results,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )

    @classmethod
    def _filter_ranked_news_for_context(
        cls,
        response: SearchResponse,
        *,
        log_scope: str,
    ) -> SearchResponse:
        """Drop obvious non-news pages and zero-relevance fillers from ranked results."""
        if not response.success or not response.results:
            return response

        candidates: List[SearchResult] = []
        dropped_low_quality = 0
        dropped_adult_spam = 0
        dropped_zero_relevance = 0

        for item in response.results:
            is_official_source = cls._is_trusted_official_news_source(item)
            if (
                not is_official_source
                and cls._has_low_quality_news_page_signal(item)
            ):
                dropped_low_quality += 1
                continue
            if (
                not is_official_source
                and cls._has_adult_service_spam_news_page_signal(item)
            ):
                dropped_adult_spam += 1
                continue
            candidates.append(item)

        meaningful_candidates = [
            item
            for item in candidates
            if item.relevance_category == cls._DIRECT_NEWS_CATEGORY
            or (item.relevance_score or 0) > 0
        ]
        if meaningful_candidates:
            dropped_zero_relevance = len(candidates) - len(meaningful_candidates)
            filtered_results = meaningful_candidates
        else:
            filtered_results = candidates

        if dropped_low_quality or dropped_adult_spam or dropped_zero_relevance:
            logger.info(
                "[新闻准入] %s: provider=%s, total=%s, kept=%s, "
                "drop_low_quality=%s, drop_adult_spam=%s, drop_zero_relevance=%s",
                log_scope,
                response.provider,
                len(response.results),
                len(filtered_results),
                dropped_low_quality,
                dropped_adult_spam,
                dropped_zero_relevance,
            )

        return SearchResponse(
            query=response.query,
            results=filtered_results,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )

    @classmethod
    def _news_relevance_stats(
        cls,
        response: SearchResponse,
        *,
        prefer_chinese: bool,
    ) -> Dict[str, int]:
        results = response.results if response and response.results else []
        return {
            "direct_count": sum(
                1 for item in results if item.relevance_category == cls._DIRECT_NEWS_CATEGORY
            ),
            "preferred_direct_count": sum(
                1
                for item in results
                if (
                    prefer_chinese
                    and item.relevance_category == cls._DIRECT_NEWS_CATEGORY
                    and cls._is_chinese_news_result(item)
                )
            ),
            "preferred_count": sum(
                1 for item in results if prefer_chinese and cls._is_chinese_news_result(item)
            ),
            "max_score": max((item.relevance_score or 0 for item in results), default=0),
            "result_count": len(results),
        }

    @classmethod
    def _is_better_ranked_news_response(
        cls,
        candidate: SearchResponse,
        *,
        candidate_stats: Dict[str, int],
        best_response: Optional[SearchResponse],
        best_stats: Optional[Dict[str, int]],
        prefer_chinese: bool,
    ) -> bool:
        if best_response is None or best_stats is None:
            return True
        if candidate_stats["direct_count"] != best_stats["direct_count"]:
            return candidate_stats["direct_count"] > best_stats["direct_count"]
        if (
            prefer_chinese
            and candidate_stats["preferred_direct_count"] != best_stats["preferred_direct_count"]
        ):
            return candidate_stats["preferred_direct_count"] > best_stats["preferred_direct_count"]
        if prefer_chinese and candidate_stats["preferred_count"] != best_stats["preferred_count"]:
            return candidate_stats["preferred_count"] > best_stats["preferred_count"]
        if candidate_stats["max_score"] != best_stats["max_score"]:
            return candidate_stats["max_score"] > best_stats["max_score"]
        return candidate_stats["result_count"] > best_stats["result_count"]

    @staticmethod
    def _parse_relative_news_date(text: str, now: datetime) -> Optional[date]:
        """Parse common Chinese/English relative-time strings."""
        raw = (text or "").strip()
        if not raw:
            return None

        lower = raw.lower()
        if raw in {"今天", "今日", "刚刚"} or lower in {"today", "just now", "now"}:
            return now.date()
        if raw == "昨天" or lower == "yesterday":
            return (now - timedelta(days=1)).date()
        if raw == "前天":
            return (now - timedelta(days=2)).date()

        zh = re.match(r"^\s*(\d+)\s*(分钟|小时|天|周|个月|月|年)\s*前\s*$", raw)
        if zh:
            amount = int(zh.group(1))
            unit = zh.group(2)
            if unit == "分钟":
                return (now - timedelta(minutes=amount)).date()
            if unit == "小时":
                return (now - timedelta(hours=amount)).date()
            if unit == "天":
                return (now - timedelta(days=amount)).date()
            if unit == "周":
                return (now - timedelta(weeks=amount)).date()
            if unit in {"个月", "月"}:
                return (now - timedelta(days=amount * 30)).date()
            if unit == "年":
                return (now - timedelta(days=amount * 365)).date()

        en = re.match(
            r"^\s*(\d+)\s*(minute|minutes|min|mins|hour|hours|day|days|week|weeks|month|months|year|years)\s*ago\s*$",
            lower,
        )
        if en:
            amount = int(en.group(1))
            unit = en.group(2)
            if unit in {"minute", "minutes", "min", "mins"}:
                return (now - timedelta(minutes=amount)).date()
            if unit in {"hour", "hours"}:
                return (now - timedelta(hours=amount)).date()
            if unit in {"day", "days"}:
                return (now - timedelta(days=amount)).date()
            if unit in {"week", "weeks"}:
                return (now - timedelta(weeks=amount)).date()
            if unit in {"month", "months"}:
                return (now - timedelta(days=amount * 30)).date()
            if unit in {"year", "years"}:
                return (now - timedelta(days=amount * 365)).date()

        return None

    @classmethod
    def _normalize_news_publish_date(cls, value: Any) -> Optional[date]:
        """Normalize provider date value into a date object."""
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                local_tz = datetime.now().astimezone().tzinfo or timezone.utc
                return value.astimezone(local_tz).date()
            return value.date()
        if isinstance(value, date):
            return value

        text = str(value).strip()
        if not text:
            return None
        now = datetime.now()
        local_tz = now.astimezone().tzinfo or timezone.utc

        relative_date = cls._parse_relative_news_date(text, now)
        if relative_date:
            return relative_date

        # Unix timestamp fallback
        if text.isdigit() and len(text) in (10, 13):
            try:
                ts = int(text[:10]) if len(text) == 13 else int(text)
                # Provider timestamps are typically UTC epoch seconds.
                # Normalize to local date to keep window checks aligned with local "today".
                return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(local_tz).date()
            except (OSError, OverflowError, ValueError):
                pass

        iso_candidate = text.replace("Z", "+00:00")
        try:
            parsed_iso = datetime.fromisoformat(iso_candidate)
            if parsed_iso.tzinfo is not None:
                return parsed_iso.astimezone(local_tz).date()
            return parsed_iso.date()
        except ValueError:
            pass

        normalized = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text, flags=re.IGNORECASE)

        try:
            parsed_rfc = parsedate_to_datetime(normalized)
            if parsed_rfc:
                if parsed_rfc.tzinfo is not None:
                    return parsed_rfc.astimezone(local_tz).date()
                return parsed_rfc.date()
        except (TypeError, ValueError):
            pass

        zh_match = re.search(r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?", text)
        if zh_match:
            try:
                return date(int(zh_match.group(1)), int(zh_match.group(2)), int(zh_match.group(3)))
            except ValueError:
                pass

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y.%m.%d",
            "%Y%m%d",
            "%b %d, %Y",
            "%B %d, %Y",
            "%d %b %Y",
            "%d %B %Y",
            "%a, %d %b %Y %H:%M:%S %z",
        ):
            try:
                parsed_dt = datetime.strptime(normalized, fmt)
                if parsed_dt.tzinfo is not None:
                    return parsed_dt.astimezone(local_tz).date()
                return parsed_dt.date()
            except ValueError:
                continue

        return None

    def _filter_news_response(
        self,
        response: SearchResponse,
        *,
        search_days: int,
        max_results: int,
        log_scope: str,
        keep_unknown: bool = False,
    ) -> SearchResponse:
        """Hard-filter results by published_date recency and normalize date strings."""
        if not response.success or not response.results:
            return response

        today = datetime.now().date()
        earliest = today - timedelta(days=max(0, int(search_days) - 1))
        latest = today + timedelta(days=self.FUTURE_TOLERANCE_DAYS)

        filtered: List[SearchResult] = []
        dropped_unknown = 0
        dropped_old = 0
        dropped_future = 0

        for item in response.results:
            published = self._normalize_news_publish_date(item.published_date)
            if published is None:
                if keep_unknown:
                    filtered.append(
                        SearchResult(
                            title=item.title,
                            snippet=item.snippet,
                            url=item.url,
                            source=item.source,
                            published_date=item.published_date,
                            relevance_score=item.relevance_score,
                            relevance_category=item.relevance_category,
                            relevance_reasons=item.relevance_reasons,
                        )
                    )
                    if len(filtered) >= max_results:
                        break
                    continue
                dropped_unknown += 1
                continue
            if published < earliest:
                dropped_old += 1
                continue
            if published > latest:
                dropped_future += 1
                continue

            filtered.append(
                SearchResult(
                    title=item.title,
                    snippet=item.snippet,
                    url=item.url,
                    source=item.source,
                    published_date=published.isoformat(),
                    relevance_score=item.relevance_score,
                    relevance_category=item.relevance_category,
                    relevance_reasons=item.relevance_reasons,
                )
            )
            if len(filtered) >= max_results:
                break

        if dropped_unknown or dropped_old or dropped_future:
            logger.info(
                "[新闻过滤] %s: provider=%s, total=%s, kept=%s, drop_unknown=%s, drop_old=%s, drop_future=%s, window=[%s,%s]",
                log_scope,
                response.provider,
                len(response.results),
                len(filtered),
                dropped_unknown,
                dropped_old,
                dropped_future,
                earliest.isoformat(),
                latest.isoformat(),
            )

        return SearchResponse(
            query=response.query,
            results=filtered,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )

    def _normalize_and_limit_response(
        self,
        response: SearchResponse,
        *,
        max_results: int,
    ) -> SearchResponse:
        """Normalize parseable dates without enforcing freshness filtering."""
        if not response.success or not response.results:
            return response

        normalized_results: List[SearchResult] = []
        for item in response.results[:max_results]:
            normalized_date = self._normalize_news_publish_date(item.published_date)
            normalized_results.append(
                SearchResult(
                    title=item.title,
                    snippet=item.snippet,
                    url=item.url,
                    source=item.source,
                    published_date=(
                        normalized_date.isoformat() if normalized_date is not None else item.published_date
                    ),
                    relevance_score=item.relevance_score,
                    relevance_category=item.relevance_category,
                    relevance_reasons=item.relevance_reasons,
                )
            )

        return SearchResponse(
            query=response.query,
            results=normalized_results,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )

    @staticmethod
    def _limit_search_response(
        response: SearchResponse,
        *,
        max_results: int,
    ) -> SearchResponse:
        """Trim response results without changing the rest of the metadata."""
        if not response.success or not response.results:
            return response

        limited_results = response.results[:max_results]
        if len(limited_results) == len(response.results):
            return response

        return SearchResponse(
            query=response.query,
            results=limited_results,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, int((time.monotonic() - started_at) * 1000))

    @staticmethod
    def _record_news_search_run(
        *,
        provider: str,
        operation: str,
        success: bool,
        latency_ms: Optional[int] = None,
        record_count: Optional[int] = None,
        cache_hit: Optional[bool] = None,
        error_type: Optional[str] = None,
        error_message: Optional[Any] = None,
    ) -> None:
        record_provider_run(
            data_type="news_search",
            provider=provider,
            operation=operation,
            success=success,
            latency_ms=latency_ms,
            error_type=error_type,
            error_message=error_message,
            cache_hit=cache_hit,
            record_count=record_count,
        )
