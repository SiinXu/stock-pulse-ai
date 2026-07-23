# -*- coding: utf-8 -*-
"""AlphaSift hotspot cache, event, and normalization helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.alphasift_service import (
        Any,
        Config,
        DSA_ALPHASIFT_DATA_DIR,
        DSA_ALPHASIFT_HOTSPOT_CACHE_PATH,
        DSA_ALPHASIFT_HOTSPOT_CONNECTIVITY_ERROR_MARKERS,
        DSA_ALPHASIFT_HOTSPOT_DETAIL_CACHE_TTL_SECONDS,
        DSA_ALPHASIFT_HOTSPOT_DETAIL_FALLBACK_CODE,
        DSA_ALPHASIFT_HOTSPOT_DETAIL_SOURCE_ERROR_CODE,
        DSA_ALPHASIFT_HOTSPOT_EVENT_SUMMARY_MAX_CHARS,
        DSA_ALPHASIFT_HOTSPOT_HISTORY_PATH,
        DSA_ALPHASIFT_HOTSPOT_PREFETCH_DETAIL_COUNT,
        DSA_ALPHASIFT_HOTSPOT_SOURCE_ERROR_CODE,
        DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE,
        DSA_ALPHASIFT_MIN_HOTSPOT_CACHE_COUNT,
        Dict,
        DsaEastMoneyHotspotProvider,
        List,
        Optional,
        Path,
        _ALPHASIFT_PUBLIC_DIAGNOSTIC_CODES,
        _ALPHASIFT_PUBLIC_LIST_DIAGNOSTIC_FIELD_CODES,
        _ALPHASIFT_PUBLIC_SCALAR_DIAGNOSTIC_FIELD_CODES,
        _alphasift_litellm_headers,
        _env_text,
        _remove_non_finite_json_values,
        _resolve_alphasift_data_dir,
        _resolve_alphasift_llm_models,
        _to_plain,
        datetime,
        hashlib,
        json,
        log_safe_exception,
        logger,
        logging,
        math,
        os,
        re,
        redact_sensitive_data,
        sanitize_sensitive_text,
        timezone,
    )


def _topic_log_context(topic: Any, **identifiers: Any) -> Dict[str, Any]:
    """Return non-content metadata for a user-provided AlphaSift topic."""
    context = dict(identifiers)
    context["topic_length"] = len(topic.strip()) if isinstance(topic, str) else 0
    return context


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _alphasift_hotspot_cache_path() -> Path:
    if _env_text(os.getenv("ALPHASIFT_DATA_DIR")):
        return _resolve_alphasift_data_dir() / "hotspots.json"
    return DSA_ALPHASIFT_HOTSPOT_CACHE_PATH


def _alphasift_hotspot_history_path() -> Path:
    if _env_text(os.getenv("ALPHASIFT_DATA_DIR")):
        return _resolve_alphasift_data_dir() / "hotspot.history.jsonl"
    return DSA_ALPHASIFT_HOTSPOT_HISTORY_PATH


def _alphasift_hotspot_detail_cache_dir() -> Path:
    return _resolve_alphasift_data_dir() / "hotspot_details"


def _alphasift_hotspot_detail_cache_path(*, provider: str, topic: str) -> Path:
    provider_text = re.sub(r"[^A-Za-z0-9_.-]+", "_", _env_text(provider) or "akshare")
    digest = hashlib.sha1(f"{provider_text}\0{_env_text(topic)}".encode("utf-8")).hexdigest()
    return _alphasift_hotspot_detail_cache_dir() / f"{provider_text}.{digest}.json"


def _parse_cache_datetime(value: Any) -> Optional[datetime]:
    text = _env_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_alphasift_hotspot_detail_cache(
    *,
    provider: str,
    topic: str,
    allow_stale: bool = False,
) -> Optional[Dict[str, Any]]:
    cache_path = _alphasift_hotspot_detail_cache_path(provider=provider, topic=topic)
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:  # broad-exception: fallback_recorded - Treat an unreadable optional cache as a miss.
        log_safe_exception(
            logger,
            "Failed to read AlphaSift hotspot detail cache",
            exc,
            error_code="alphasift_hotspot_detail_cache_read_failed",
            level=logging.WARNING,
            context={"cache_path": cache_path},
        )
        return None

    payload = raw.get("payload") if isinstance(raw, dict) else None
    if not isinstance(payload, dict):
        return None
    cached_at = raw.get("cached_at") or payload.get("cached_at")
    cached_dt = _parse_cache_datetime(cached_at)
    if cached_dt is None:
        return None
    age_seconds = max(0.0, (datetime.now(timezone.utc) - cached_dt).total_seconds())
    stale = age_seconds > DSA_ALPHASIFT_HOTSPOT_DETAIL_CACHE_TTL_SECONDS
    if stale and not allow_stale:
        return None

    cached = _ensure_hotspot_detail_compat_fields(dict(payload))
    cached.update({
        "enabled": True,
        "provider": provider or cached.get("provider") or "akshare",
        "cache_used": True,
        "cached_at": cached_at,
        "stale": bool(cached.get("stale") or stale),
    })
    if stale:
        cached["fallback_used"] = True
        cached["stale_age_seconds"] = round(age_seconds, 1)
    cached["source_errors"] = _public_diagnostic_codes(
        cached.get("source_errors"),
        fallback_code=DSA_ALPHASIFT_HOTSPOT_DETAIL_SOURCE_ERROR_CODE,
    )
    return _sanitize_public_alphasift_diagnostics(_remove_non_finite_json_values(cached))


def _write_alphasift_hotspot_detail_cache(*, provider: str, topic: str, payload: Dict[str, Any]) -> None:
    cache_path = _alphasift_hotspot_detail_cache_path(provider=provider, topic=topic)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned = _sanitize_public_alphasift_diagnostics(
            _remove_non_finite_json_values(_ensure_hotspot_detail_compat_fields(dict(payload)))
        )
        cached_at = _utc_now_iso()
        cache_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "provider": provider or cleaned.get("provider") or "akshare",
                    "topic": topic,
                    "cached_at": cached_at,
                    "payload": cleaned,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # broad-exception: fallback_recorded - Cache persistence must not fail the request.
        log_safe_exception(
            logger,
            "Failed to write AlphaSift hotspot detail cache",
            exc,
            error_code="alphasift_hotspot_detail_cache_write_failed",
            level=logging.WARNING,
            context=_topic_log_context(topic, provider=provider or "unknown"),
        )


def _ensure_hotspot_detail_compat_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Keep old and new AlphaSift hotspot detail consumers on the same shape."""
    stocks = payload.get("stocks")
    leader_stocks = payload.get("leader_stocks")
    if not isinstance(stocks, list):
        stocks = []
    if not isinstance(leader_stocks, list) or not leader_stocks:
        nested_leader_stocks = _extract_nested_hotspot_leader_stocks(payload)
        leader_stocks = nested_leader_stocks or (leader_stocks if isinstance(leader_stocks, list) else [])
    if not stocks and leader_stocks:
        stocks = leader_stocks
    if not leader_stocks and stocks:
        leader_stocks = stocks
    payload["stocks"] = stocks
    payload["leader_stocks"] = leader_stocks
    payload["stock_count"] = len(stocks)
    return payload


def _extract_nested_hotspot_leader_stocks(payload: Dict[str, Any]) -> List[Any]:
    for key in ("summary_detail", "summary"):
        summary = payload.get(key)
        if not isinstance(summary, dict):
            continue
        leader_stocks = summary.get("leader_stocks")
        if isinstance(leader_stocks, list) and leader_stocks:
            return leader_stocks
    return []


def _load_alphasift_hotspot_cache(*, provider: str, top: int) -> Optional[Dict[str, Any]]:
    cache_path = _alphasift_hotspot_cache_path()
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:  # broad-exception: fallback_recorded - Treat an unreadable optional cache as a miss.
        log_safe_exception(
            logger,
            "Failed to read AlphaSift hotspot cache",
            exc,
            error_code="alphasift_hotspot_cache_read_failed",
            level=logging.WARNING,
            context={"cache_path": cache_path},
        )
        return None

    payload = _normalize_alphasift_hotspot_cache_payload(raw)
    if not isinstance(payload, dict):
        return None
    hotspots = payload.get("hotspots")
    if not isinstance(hotspots, list) or not hotspots:
        return None

    top_count = max(1, min(int(top or 12), 50))
    if len(hotspots) < min(DSA_ALPHASIFT_MIN_HOTSPOT_CACHE_COUNT, top_count):
        logger.info(
            "Ignoring AlphaSift hotspot cache with too few rows: %s < %s",
            len(hotspots),
            min(DSA_ALPHASIFT_MIN_HOTSPOT_CACHE_COUNT, top_count),
        )
        return None

    selected = hotspots[:top_count]
    cached = dict(payload)
    cached.update({
        "enabled": True,
        "provider": provider or payload.get("provider") or "akshare",
        "hotspots": selected,
        "hotspot_count": len(selected),
        "cache_used": True,
        "cached_at": raw.get("cached_at") or payload.get("cached_at"),
    })
    cached["source_errors"] = _classify_hotspot_source_errors(
        cached.get("source_errors"),
        eastmoney=provider in {"", "akshare"},
    )
    return _sanitize_public_alphasift_diagnostics(_remove_non_finite_json_values(cached))


def _normalize_alphasift_hotspot_cache_payload(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    payload = raw.get("payload")
    if isinstance(payload, dict):
        return payload
    hotspots = raw.get("hotspots")
    if not isinstance(hotspots, list):
        return None
    metadata_raw = raw.get("metadata")
    metadata: Dict[str, Any] = metadata_raw if isinstance(metadata_raw, dict) else {}
    cached_at = raw.get("cached_at") or raw.get("generated_at") or metadata.get("generated_at")
    return {
        "enabled": True,
        "provider": _env_text(metadata.get("provider")) or "akshare",
        "provider_used": _env_text(metadata.get("provider_used")),
        "fallback_used": False,
        "cache_used": False,
        "cached_at": cached_at,
        "schema_version": raw.get("schema_version") or metadata.get("schema_version"),
        "source_errors": _list_text_values(raw.get("source_errors") or metadata.get("source_errors")),
        "stale": bool(raw.get("stale") or metadata.get("stale") or False),
        "stale_age_hours": raw.get("stale_age_hours") or metadata.get("stale_age_hours"),
        "hotspots": hotspots,
        "hotspot_count": len(hotspots),
    }


def _hotspot_route_has_external_event(route: Any) -> bool:
    if not isinstance(route, list):
        return False
    generated_sources = {"", "eastmoney_board_change", "fallback", "dsa_topic_catalyst", "ths_info"}
    for item in route:
        if not isinstance(item, dict):
            continue
        source = _env_text(item.get("source"))
        if source and source not in generated_sources:
            return True
    return False


def _has_configured_hotspot_news_source(config: Config) -> bool:
    fields = (
        "bocha_api_keys",
        "tavily_api_keys",
        "anspire_api_keys",
        "brave_api_keys",
        "serpapi_api_keys",
        "minimax_api_keys",
        "searxng_base_urls",
    )
    return any(bool(getattr(config, field, None)) for field in fields)


def _build_hotspot_event_routes_from_search(topic: str, config: Config) -> List[Dict[str, Any]]:
    topic_text = _env_text(topic)
    if not topic_text or not _has_configured_hotspot_news_source(config):
        return []
    try:
        from src.search_service import SearchService

        service = SearchService(
            bocha_keys=getattr(config, "bocha_api_keys", None),
            tavily_keys=getattr(config, "tavily_api_keys", None),
            anspire_keys=getattr(config, "anspire_api_keys", None),
            brave_keys=getattr(config, "brave_api_keys", None),
            serpapi_keys=getattr(config, "serpapi_api_keys", None),
            minimax_keys=getattr(config, "minimax_api_keys", None),
            searxng_base_urls=getattr(config, "searxng_base_urls", None),
            searxng_public_instances_enabled=False,
            news_max_age_days=int(getattr(config, "news_max_age_days", 3) or 3),
            news_strategy_profile=getattr(config, "news_strategy_profile", "short"),
        )
        response = service.search_stock_news(
            topic_text,
            topic_text,
            max_results=3,
            focus_keywords=[topic_text, "A股", "题材", "催化", "涨价"],
        )
    except Exception as exc:  # broad-exception: fallback_recorded - Omit optional event routes when search fails.
        log_safe_exception(
            logger,
            "AlphaSift hotspot event search skipped",
            exc,
            error_code="alphasift_hotspot_event_search_failed",
            level=logging.INFO,
            context=_topic_log_context(topic_text, source="configured_search"),
        )
        return []

    if not bool(getattr(response, "success", False)):
        return []
    today = datetime.now().date().isoformat()
    event_parts: List[str] = []
    sources: List[str] = []
    first_url = ""
    first_date = ""
    first_published = ""
    for result in list(getattr(response, "results", []) or [])[:2]:
        title = _env_text(getattr(result, "title", ""))
        snippet = _env_text(getattr(result, "snippet", ""))
        if not title and not snippet:
            continue
        event_text = _compact_hotspot_news_text(title=title, snippet=snippet)
        if event_text:
            event_parts.append(event_text)
        published = _env_text(getattr(result, "published_date", ""))
        source = _env_text(getattr(result, "source", "")) or _env_text(getattr(response, "provider", "")) or "news_search"
        if source and source not in sources:
            sources.append(source)
        if not first_url:
            first_url = _env_text(getattr(result, "url", ""))
        if not first_date:
            first_date = _extract_date_text(published) or _extract_date_text(event_text)
        if not first_published:
            first_published = published
    if not event_parts:
        return []
    description = _summarize_hotspot_news_event(
        topic=topic_text,
        title="",
        snippet="；".join(event_parts),
        config=config,
    )
    date = first_date or _extract_date_text(description) or today
    return [{
        "title": "消息催化",
        "description": description,
        "source": ",".join(sources) if sources else "news_search",
        "date": date,
        "published_at": first_published or date,
        "url": first_url,
    }]


def _summarize_hotspot_news_event(*, topic: str, title: str, snippet: str, config: Config) -> str:
    compact_text = _compact_hotspot_news_text(title=title, snippet=snippet)
    llm_summary = _summarize_hotspot_news_event_with_llm(topic=topic, text=compact_text, config=config)
    if llm_summary:
        return _truncate_text(llm_summary, DSA_ALPHASIFT_HOTSPOT_EVENT_SUMMARY_MAX_CHARS)
    return _summarize_hotspot_news_event_locally(topic=topic, text=compact_text)


def _summarize_hotspot_news_event_locally(*, topic: str, text: str) -> str:
    cleaned = _strip_hotspot_news_noise(text)
    if not cleaned:
        return ""
    catalyst = _extract_hotspot_catalyst_phrase(cleaned)
    impacts = _extract_hotspot_impact_phrases(cleaned)
    if catalyst and impacts:
        summary = f"{catalyst}，带动{impacts}发酵。"
    elif catalyst:
        summary = f"{catalyst}，市场关注{topic}相关产业链机会。"
    else:
        summary = _first_meaningful_hotspot_sentence(cleaned)
    summary = _truncate_text(summary, DSA_ALPHASIFT_HOTSPOT_EVENT_SUMMARY_MAX_CHARS).rstrip(".。…")
    return _truncate_text(f"{summary}。", DSA_ALPHASIFT_HOTSPOT_EVENT_SUMMARY_MAX_CHARS)


def _strip_hotspot_news_noise(text: str) -> str:
    cleaned = _normalize_inline_text(text)
    cleaned = re.sub(r"【[^】]{1,24}】", " ", cleaned)
    cleaned = re.sub(r"\[[^\]]{1,24}\]", " ", cleaned)
    cleaned = re.sub(r"\b20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}[日号]?\b", " ", cleaned)
    cleaned = re.sub(r"\b\d{1,2}:\d{2}\b", " ", cleaned)
    cleaned = re.sub(r"\([^)]{0,18}\d+\.\d+[^)]{0,18}\)", " ", cleaned)
    cleaned = re.sub(r"（[^）]{0,18}\d+\.\d+[^）]{0,18}）", " ", cleaned)
    cleaned = re.sub(r"截至[^。；;]*", " ", cleaned)
    cleaned = re.sub(r"(建议关注|后续建议|风险提示|投资建议)[^。；;]*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ，,；;。.")


def _extract_hotspot_catalyst_phrase(text: str) -> str:
    patterns = (
        r"以[^，。；;]{1,12}代[^，。；;]{1,12}",
        r"[^，。；;]{1,18}(涨价|价格上行|供需偏紧|供应紧张|资源增储|订单增长|政策催化|出口管制|减产|并购重组|技术突破)[^，。；;]{0,24}",
        r"[^，。；;]{1,18}(替代|国产替代|需求增长|景气上行)[^，。；;]{0,24}",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _normalize_inline_text(match.group(0)).strip(" ，,；;。.")
    return ""


def _extract_hotspot_impact_phrases(text: str) -> str:
    impacts: List[str] = []
    keyword_groups = (
        ("小金属", ("小金属", "钼", "钨", "锑", "锗", "铟")),
        ("有色金属", ("有色", "铜", "铝", "锌", "铅")),
        ("相关个股", ("涨停", "异动", "走强", "大涨", "拉升")),
        ("产业链", ("产业链", "上游", "下游", "材料", "资源")),
    )
    for label, keywords in keyword_groups:
        if any(keyword in text for keyword in keywords) and label not in impacts:
            impacts.append(label)
    return "、".join(impacts[:3])


def _first_meaningful_hotspot_sentence(text: str) -> str:
    sentences = [
        _normalize_inline_text(item).strip(" ，,；;。.")
        for item in re.split(r"[。！？!?；;]", text)
        if _normalize_inline_text(item)
    ]
    for sentence in sentences:
        if len(sentence) >= 8 and not re.search(r"(现价|成交额|涨跌幅|换手率|建议关注|截至)", sentence):
            return sentence
    return sentences[0] if sentences else text


def _compact_hotspot_news_text(*, title: str, snippet: str) -> str:
    title_text = _normalize_inline_text(title)
    snippet_text = _normalize_inline_text(snippet)
    if title_text and snippet_text.startswith(title_text):
        snippet_text = snippet_text[len(title_text):].lstrip(" ：:，,。;；")
    if title_text and snippet_text == title_text:
        snippet_text = ""
    text = "。".join(part for part in (title_text, snippet_text) if part)
    text = re.sub(r"(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}[日号]?)\s+\d{1,2}:\d{2}", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_inline_text(value: Any) -> str:
    text = _env_text(value)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _truncate_text(text: str, max_chars: int) -> str:
    text = _normalize_inline_text(text)
    if len(text) <= max_chars:
        return text
    sentence_parts = re.split(r"(?<=[。！？!?；;])", text)
    summary = ""
    for part in sentence_parts:
        if not part:
            continue
        if len(summary) + len(part) > max_chars:
            break
        summary += part
    if summary:
        return summary.rstrip("，,；;：: ")[:max_chars].rstrip("，,；;：: ") + "..."
    return text[: max(0, max_chars - 3)].rstrip("，,；;：: ") + "..."


def _summarize_hotspot_news_event_with_llm(*, topic: str, text: str, config: Config) -> str:
    model, _fallback_models = _resolve_alphasift_llm_models(config)
    if not _env_text(model) or not text:
        return ""
    try:
        import litellm

        prompt = (
            "请把下面新闻压缩成一句 A 股热点题材催化摘要。"
            "要求：不超过 70 个中文字符，只保留事件、影响方向和相关链条；"
            "不要输出完整报道、股票价格流水、免责声明或投资建议。\n\n"
            f"题材：{topic}\n新闻：{text}"
        )
        with _alphasift_litellm_headers(config):
            response = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": "你是A股题材事件摘要助手，只输出一句短摘要。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=120,
                timeout=8,
            )
        return _clean_hotspot_llm_summary(_extract_litellm_message_content(response))
    except Exception as exc:  # broad-exception: optional_metadata - Fall back to the local event summary.
        log_safe_exception(
            logger,
            "AlphaSift hotspot LLM event summary skipped",
            exc,
            error_code="alphasift_hotspot_summary_failed",
            level=logging.INFO,
            context=_topic_log_context(topic, stage="llm_summary"),
        )
        return ""


def _extract_litellm_message_content(response: Any) -> str:
    try:
        choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
        if choices:
            choice = choices[0]
            message = choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
            if isinstance(message, dict):
                return _env_text(message.get("content"))
            return _env_text(getattr(message, "content", ""))
    except Exception:  # broad-exception: optional_metadata - Ignore malformed optional provider response metadata.
        return ""
    return ""


def _clean_hotspot_llm_summary(text: str) -> str:
    summary = _normalize_inline_text(text).strip(" 　\"'“”‘’")
    summary = re.sub(r"^(摘要|总结|消息催化|事件催化)\s*[:：]\s*", "", summary)
    return summary


def _extract_date_text(text: str) -> str:
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text or "")
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _hotspot_rows_are_thin(rows: List[Any], *, top: int) -> bool:
    if len(rows) < min(DSA_ALPHASIFT_MIN_HOTSPOT_CACHE_COUNT, max(1, top)):
        return True
    rich_count = 0
    metric_count = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        if item.get("change_pct") is not None or item.get("changePct") is not None:
            rich_count += 1
        if (
            item.get("trend_score") is not None
            or item.get("trendScore") is not None
            or item.get("persistence_score") is not None
            or item.get("persistenceScore") is not None
        ):
            metric_count += 1
    return rich_count == 0 or metric_count == 0


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _enrich_hotspot_rows_from_provider(rows: List[Any], provider: Any, *, top: int) -> List[Dict[str, Any]]:
    try:
        provider_rows = provider.hotspot_rows(top=max(top, len(rows), 30))
    except Exception as exc:  # broad-exception: fallback_recorded - Keep contract rows when optional enrichment fails.
        log_safe_exception(
            logger,
            "AlphaSift hotspot metric enrichment failed",
            exc,
            error_code="alphasift_hotspot_metric_enrichment_failed",
            level=logging.WARNING,
        )
        return [dict(item) if isinstance(item, dict) else item for item in rows]
    by_topic: Dict[str, Dict[str, Any]] = {}
    for item in provider_rows or []:
        if not isinstance(item, dict):
            continue
        topic = _env_text(item.get("topic") or item.get("name"))
        if topic:
            by_topic[topic] = item
        name = _env_text(item.get("name"))
        if name and "·" in name:
            by_topic[name.split("·")[-1].strip()] = item
    enriched: List[Dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            enriched.append(raw)
            continue
        item = dict(raw)
        topic = _env_text(item.get("topic") or item.get("name"))
        provider_item = by_topic.get(topic)
        if not provider_item:
            enriched.append(item)
            continue
        for key in (
            "change_pct",
            "heat_score",
            "trend_score",
            "persistence_score",
            "observations",
            "stage",
            "state",
            "sample_stock_count",
            "leaders",
            "theme_group",
        ):
            camel_key = _snake_to_camel(key)
            if item.get(key) in (None, "", [], {}) and item.get(camel_key) in (None, "", [], {}):
                value = provider_item.get(key)
                if value not in (None, "", [], {}):
                    item[key] = value
        if item.get("name") in (None, "", topic):
            item["name"] = provider_item.get("name") or topic
        enriched.append(item)
    return enriched


def _write_alphasift_hotspot_cache(payload: Dict[str, Any]) -> None:
    cache_path = _alphasift_hotspot_cache_path()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cached_at = _utc_now_iso()
        cache_payload = _sanitize_public_alphasift_diagnostics(dict(payload))
        cache_payload["cache_used"] = False
        cache_payload["cached_at"] = cached_at
        cache_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "generated_at": cached_at,
                    "cached_at": cached_at,
                    "metadata": {
                        "schema_version": 2,
                        "asset_type": "hotspot_cache",
                        "provider": cache_payload.get("provider"),
                        "provider_used": cache_payload.get("provider_used"),
                        "row_count": len(cache_payload.get("hotspots") or []),
                        "source_errors": _list_text_values(cache_payload.get("source_errors")),
                    },
                    "hotspots": cache_payload.get("hotspots") or [],
                    "payload": cache_payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # broad-exception: fallback_recorded - Cache persistence must not fail the request.
        log_safe_exception(
            logger,
            "Failed to write AlphaSift hotspot cache",
            exc,
            error_code="alphasift_hotspot_cache_write_failed",
            level=logging.WARNING,
            context={"cache_path": cache_path},
        )


def _hotspot_topic_from_row(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    return _env_text(row.get("topic") or row.get("name") or row.get("canonical_topic"))


def _attach_cached_hotspot_details(
    payload: Dict[str, Any],
    *,
    provider: str,
    top: int,
) -> Dict[str, Any]:
    rows = payload.get("hotspots")
    if not isinstance(rows, list) or not rows:
        return payload
    details = dict(payload.get("details") if isinstance(payload.get("details"), dict) else {})
    for row in rows[:max(0, min(int(top or 0), DSA_ALPHASIFT_HOTSPOT_PREFETCH_DETAIL_COUNT))]:
        topic = _hotspot_topic_from_row(row)
        if not topic or topic in details:
            continue
        cached = _load_alphasift_hotspot_detail_cache(provider=provider, topic=topic)
        if cached is not None:
            details[topic] = cached
    if details:
        attached = dict(payload)
        attached["details"] = _remove_non_finite_json_values(details)
        return attached
    return payload


def _empty_alphasift_hotspot_payload(
    *,
    provider: str,
    provider_used: str = "",
    source_errors: Optional[List[str]] = None,
    message: str = "",
) -> Dict[str, Any]:
    return {
        "enabled": True,
        "provider": provider,
        "provider_used": provider_used,
        "fallback_used": False,
        "cache_used": False,
        "cached_at": None,
        "source_errors": list(source_errors or []),
        "stale": False,
        "stale_age_hours": None,
        "hotspots": [],
        "hotspot_count": 0,
        "message": message,
    }


def _is_known_eastmoney_hotspot_connectivity_error(exc: BaseException) -> bool:
    retryable_types: List[Any] = [ConnectionError, TimeoutError]
    try:
        import requests

        retryable_types.extend(
            [
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ]
        )
    except Exception:  # broad-exception: optional_metadata - Requests is an optional transport classifier.
        pass
    try:
        import http.client

        retryable_types.extend([http.client.RemoteDisconnected, http.client.IncompleteRead])
    except Exception:  # broad-exception: optional_metadata - HTTP client details are optional classifiers.
        pass
    try:
        import urllib3.exceptions

        retryable_types.extend(
            [
                urllib3.exceptions.ProtocolError,
                urllib3.exceptions.MaxRetryError,
                urllib3.exceptions.ReadTimeoutError,
                urllib3.exceptions.ConnectTimeoutError,
            ]
        )
    except Exception:  # broad-exception: optional_metadata - urllib3 details are optional classifiers.
        pass

    retryable_tuple = tuple(retryable_types)
    pending: List[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)
        if isinstance(current, retryable_tuple):
            return True
        message = f"{current.__class__.__name__}: {current}".lower()
        if any(marker in message for marker in DSA_ALPHASIFT_HOTSPOT_CONNECTIVITY_ERROR_MARKERS):
            return True
        cause = getattr(current, "__cause__", None)
        context = getattr(current, "__context__", None)
        if isinstance(cause, BaseException):
            pending.append(cause)
        if isinstance(context, BaseException):
            pending.append(context)
    return False


def _should_return_eastmoney_hotspot_unavailable(provider_arg: Any, exc: BaseException) -> bool:
    return isinstance(provider_arg, DsaEastMoneyHotspotProvider) and _is_known_eastmoney_hotspot_connectivity_error(exc)


def _has_degraded_eastmoney_hotspot_failure(provider_arg: Any, source_errors: List[str]) -> bool:
    if not isinstance(provider_arg, DsaEastMoneyHotspotProvider):
        return False
    for source_error in source_errors:
        if source_error == DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE:
            return True
        if _is_known_eastmoney_hotspot_connectivity_error(RuntimeError(source_error)):
            return True
    return False


def _normalize_alphasift_hotspot_detail(detail: Any, *, provider: str, requested_topic: str) -> Dict[str, Any]:
    raw_value = _remove_non_finite_json_values(_to_plain(detail))
    raw: Dict[str, Any] = raw_value if isinstance(raw_value, dict) else {}
    summary_value = raw.get("summary")
    summary: Dict[str, Any] = summary_value if isinstance(summary_value, dict) else {}
    stocks_value = raw.get("stocks")
    leader_stocks_value = raw.get("leader_stocks")
    stocks: List[Any] = stocks_value if isinstance(stocks_value, list) else []
    leader_stocks: List[Any] = leader_stocks_value if isinstance(leader_stocks_value, list) else []
    timeline_value = raw.get("timeline")
    timeline: List[Any] = timeline_value if isinstance(timeline_value, list) else []
    route_value = raw.get("route")
    route: List[Any] = route_value if isinstance(route_value, list) and route_value else _hotspot_timeline_to_route(timeline)
    source_errors = _list_text_values(raw.get("source_errors") or summary.get("source_errors"))
    topic = _env_text(summary.get("topic") or raw.get("topic") or requested_topic)
    canonical_topic = _env_text(summary.get("canonical_topic") or raw.get("canonical_topic"))
    name = _env_text(summary.get("name") or raw.get("name") or canonical_topic or topic)
    quality_status = _env_text(summary.get("quality_status") or raw.get("quality_status"))
    missing_fields = _list_text_values(summary.get("missing_fields") or raw.get("missing_fields"))
    summary_text_value = raw.get("summary")
    summary_text = (
        summary_text_value
        if isinstance(summary_text_value, str)
        else _build_alphasift_hotspot_summary_text(summary, topic=topic, canonical_topic=canonical_topic)
    )
    return _ensure_hotspot_detail_compat_fields({
        "enabled": True,
        "provider": provider,
        "topic": topic,
        "name": name,
        "canonical_topic": canonical_topic,
        "aliases": _list_text_values(summary.get("aliases") or raw.get("aliases")),
        "summary": summary_text,
        "summary_detail": summary,
        "route": route,
        "timeline": timeline,
        "stocks": stocks,
        "leader_stocks": leader_stocks,
        "source_errors": source_errors,
        "quality_status": quality_status,
        "missing_fields": missing_fields,
        "fallback_used": bool(summary.get("fallback_used") or raw.get("fallback_used") or False),
        "stale": bool(summary.get("stale") or raw.get("stale") or False),
        "stale_age_hours": summary.get("stale_age_hours") or raw.get("stale_age_hours"),
        "resolver_candidates": _list_dict_values(summary.get("resolver_candidates") or raw.get("resolver_candidates")),
    })


def _list_text_values(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = _env_text(value)
        return [text] if text else []
    if not isinstance(value, list):
        text = _env_text(value)
        return [text] if text else []
    return [text for item in value if (text := _env_text(item))]


def _public_diagnostic_codes(value: Any, *, fallback_code: str) -> List[str]:
    """Map adapter-owned diagnostic text to a small, documented public code set."""
    codes: List[str] = []
    for diagnostic in _list_text_values(value):
        code = diagnostic if diagnostic in _ALPHASIFT_PUBLIC_DIAGNOSTIC_CODES else fallback_code
        if code not in codes:
            codes.append(code)
    return codes


def _public_diagnostic_code(value: Any, *, fallback_code: str) -> Any:
    """Return one stable code for scalar diagnostic fields while preserving empty values."""
    if value is None or value is False:
        return value
    if isinstance(value, str):
        diagnostic = _env_text(value)
        if not diagnostic:
            return value
        return diagnostic if diagnostic in _ALPHASIFT_PUBLIC_DIAGNOSTIC_CODES else fallback_code
    if isinstance(value, (list, tuple, dict, set)) and not value:
        return value
    return fallback_code


def _normalize_diagnostic_field_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _classify_hotspot_source_errors(value: Any, *, eastmoney: bool) -> List[str]:
    codes: List[str] = []
    for diagnostic in _list_text_values(value):
        if diagnostic in _ALPHASIFT_PUBLIC_DIAGNOSTIC_CODES:
            code = diagnostic
        elif eastmoney and _is_known_eastmoney_hotspot_connectivity_error(RuntimeError(diagnostic)):
            code = DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE
        else:
            code = DSA_ALPHASIFT_HOTSPOT_SOURCE_ERROR_CODE
        if code not in codes:
            codes.append(code)
    return codes


def _sanitize_public_alphasift_diagnostics(value: Any) -> Any:
    """Code known diagnostics and redact secrets in nested string keys and values."""
    if isinstance(value, list):
        return [_sanitize_public_alphasift_diagnostics(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_public_alphasift_diagnostics(item) for item in value]
    if isinstance(value, str):
        return sanitize_sensitive_text(value)
    if not isinstance(value, dict):
        return value

    sanitized: Dict[Any, Any] = {}
    for key, item in value.items():
        normalized_key = _normalize_diagnostic_field_name(key)
        public_key = key
        if isinstance(key, str):
            redacted_key = sanitize_sensitive_text(key)
            if "[REDACTED" in redacted_key:
                public_key = redacted_key
        list_fallback_code = _ALPHASIFT_PUBLIC_LIST_DIAGNOSTIC_FIELD_CODES.get(normalized_key)
        scalar_fallback_code = _ALPHASIFT_PUBLIC_SCALAR_DIAGNOSTIC_FIELD_CODES.get(normalized_key)
        if list_fallback_code is not None:
            sanitized[public_key] = _public_diagnostic_codes(item, fallback_code=list_fallback_code)
        elif scalar_fallback_code is not None:
            sanitized[public_key] = _public_diagnostic_code(item, fallback_code=scalar_fallback_code)
        else:
            sanitized[public_key] = _sanitize_public_alphasift_diagnostics(item)
    redacted = redact_sensitive_data(sanitized)
    return redacted if isinstance(redacted, dict) else {}


def _list_dict_values(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _hotspot_timeline_to_route(timeline: List[Any]) -> List[Dict[str, Any]]:
    route: List[Dict[str, Any]] = []
    for item in timeline:
        if not isinstance(item, dict):
            continue
        title = _env_text(item.get("title"))
        if not title:
            continue
        date = _env_text(item.get("date") or item.get("published_at"))
        source = _env_text(item.get("source")) or "alphasift_timeline"
        route.append({
            "title": title,
            "description": f"{date}：{title}" if date else title,
            "source": source,
            "url": _env_text(item.get("url")),
            "published_at": date,
        })
    if route:
        return route
    return [{
        "title": "等待发酵",
        "description": "暂未获取到明确催化事件，可继续观察涨跌幅、成交额和核心个股联动。",
        "source": "fallback",
    }]


def _merge_provider_hotspot_route_fallback(
    normalized: Dict[str, Any],
    *,
    provider: "DsaEastMoneyHotspotProvider",
    topic: str,
) -> Dict[str, Any]:
    if _has_meaningful_hotspot_route(normalized.get("route")):
        return normalized
    try:
        provider_detail = provider.hotspot_detail(topic)
    except Exception as exc:  # broad-exception: fallback_recorded - Keep the normalized contract route on provider failure.
        log_safe_exception(
            logger,
            "AlphaSift provider route fallback failed; keeping contract detail route",
            exc,
            error_code=DSA_ALPHASIFT_HOTSPOT_DETAIL_FALLBACK_CODE,
            level=logging.WARNING,
            context=_topic_log_context(
                topic,
                provider_type=type(provider).__name__,
            ),
        )
        return normalized

    raw_value = _remove_non_finite_json_values(_to_plain(provider_detail))
    raw: Dict[str, Any] = raw_value if isinstance(raw_value, dict) else {}
    provider_route = raw.get("route")
    if _has_meaningful_hotspot_route(provider_route):
        normalized["route"] = provider_route
        provider_timeline = raw.get("timeline")
        if not normalized.get("timeline") and isinstance(provider_timeline, list):
            normalized["timeline"] = provider_timeline
        return normalized

    provider_timeline = raw.get("timeline")
    if isinstance(provider_timeline, list) and provider_timeline:
        provider_timeline_route = _hotspot_timeline_to_route(provider_timeline)
        if _has_meaningful_hotspot_route(provider_timeline_route):
            normalized["route"] = provider_timeline_route
            normalized["timeline"] = provider_timeline
    return normalized


def _has_meaningful_hotspot_route(route: Any) -> bool:
    if not isinstance(route, list):
        return False
    for item in route:
        if not isinstance(item, dict):
            continue
        title = _env_text(item.get("title"))
        description = _env_text(item.get("description"))
        source = _env_text(item.get("source"))
        if not title and not description:
            continue
        if source == "fallback" and title == "等待发酵":
            continue
        return True
    return False


def _build_alphasift_hotspot_summary_text(summary: Dict[str, Any], *, topic: str, canonical_topic: str) -> str:
    display_topic = canonical_topic or topic
    quality = _env_text(summary.get("quality_status"))
    heat = _safe_float(summary.get("heat_score"))
    stage = _env_text(summary.get("stage"))
    leaders = summary.get("leaders") if isinstance(summary.get("leaders"), list) else []
    parts = [f"{display_topic} 当前热点详情"]
    if heat is not None:
        parts.append(f"热度 {heat:.1f}")
    if stage:
        parts.append(f"阶段 {stage}")
    if leaders:
        parts.append("核心股 " + "、".join(_env_text(item) for item in leaders[:3] if _env_text(item)))
    if quality:
        parts.append(f"质量状态 {quality}")
    return "，".join(part for part in parts if part) + "。"
