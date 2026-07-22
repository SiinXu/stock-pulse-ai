# -*- coding: utf-8 -*-
"""EastMoney hotspot provider methods extracted from the AlphaSift facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.alphasift_service import (
        Any,
        Dict,
        List,
        Optional,
        Tuple,
        _ensure_hotspot_detail_compat_fields,
        _env_text,
        _get_dsa_fetcher_manager,
        _list_text_values,
        _safe_float,
        _topic_log_context,
        datetime,
        log_safe_exception,
        logger,
        logging,
        re,
        threading,
        time,
    )


class DsaEastMoneyHotspotProvider:
    """Minimal EastMoney board provider for AlphaSift hotspot scoring."""

    _BASE_URL = "https://push2.eastmoney.com/api/qt/clist/get"
    _HTTP_TIMEOUT_SECONDS = 8
    _COMMON_PARAMS = {
        "pn": "1",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f12",
        "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
    }
    _BROAD_BOARD_KEYWORDS = (
        "融资融券",
        "深股通",
        "沪股通",
        "创业板",
        "昨日",
        "机构重仓",
        "富时罗素",
        "MSCI",
        "标普",
        "上证",
        "深证",
        "中证",
        "HS300",
        "证金",
        "QFII",
        "基金",
        "转融券",
        "预增",
        "预盈",
        "亏损",
        "低价",
        "小盘股",
        "中盘股",
        "百元股",
        "破发",
        "破增发",
        "趋势股",
        "广东板块",
        "江苏板块",
        "浙江板块",
        "上海板块",
        "深圳特区",
        "央国企",
        "国企改革",
        "专精特新",
        "其他",
        "Ⅱ",
        "Ⅲ",
    )
    _CHANGE_EVENT_LABELS = {
        4: "快速拉升",
        8: "快速回落",
        16: "大幅上涨",
        32: "大幅下跌",
        64: "有大笔买入",
        128: "有大笔卖出",
        8193: "火箭发射",
        8194: "高台跳水",
        8201: "大笔买入",
        8202: "大笔卖出",
        8203: "封涨停板",
        8204: "打开涨停板",
        8207: "有打开跌停板",
        8208: "封跌停板",
        8209: "向上缺口",
        8210: "向下缺口",
        8211: "60日新高",
        8212: "60日新低",
        8213: "60日大幅上涨",
        8214: "60日大幅下跌",
        8215: "竞价上涨",
        8216: "竞价下跌",
        8217: "高开",
        8218: "低开",
        8219: "放量",
        8220: "缩量",
        8221: "向上突破",
        8222: "向下破位",
    }
    _METAL_TOPIC_GROUPS = {
        "钼": "小金属",
        "钨": "小金属",
        "钴": "小金属",
        "镍": "小金属",
        "锑": "小金属",
        "铟": "小金属",
        "锗": "小金属",
        "铅锌": "工业金属",
        "铜": "工业金属",
        "铝": "工业金属",
        "锡": "工业金属",
        "黄金": "贵金属",
        "白银": "贵金属",
        "贵金属": "贵金属",
    }
    def __init__(self) -> None:
        import requests

        self._board_changes_raw_cache: Any = None
        self._board_changes_frame_cache: Any = None
        self._constituent_cache: Dict[Tuple[str, str], Any] = {}
        self._session = requests.Session()
        self._request_lock = threading.RLock()
        self._last_request_ts = 0.0
        self._min_request_interval = 0.25

    def _eastmoney_get_once(self, url: str, **kwargs: Any) -> Any:
        with self._request_lock:
            elapsed = time.monotonic() - self._last_request_ts
            if elapsed < self._min_request_interval:
                time.sleep(self._min_request_interval - elapsed)
            try:
                return self._session.get(url, **kwargs)
            finally:
                self._last_request_ts = time.monotonic()

    def _eastmoney_get(self, url: str, **kwargs: Any) -> Any:
        import requests

        retryable_errors = (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        )
        delays = (0.3, 0.8)
        last_error: Optional[BaseException] = None
        for attempt in range(len(delays) + 1):
            try:
                return self._eastmoney_get_once(url, **kwargs)
            except retryable_errors as exc:
                last_error = exc
                if attempt >= len(delays):
                    break
                log_safe_exception(
                    logger,
                    "AlphaSift EastMoney hotspot request failed; retrying",
                    exc,
                    error_code="alphasift_eastmoney_request_failed",
                    level=logging.WARNING,
                    context={"attempt": attempt + 1},
                )
                time.sleep(delays[attempt])
        assert last_error is not None
        raise last_error

    def stock_board_concept_name_em(self) -> Any:
        frame = self._fetch_board_changes_with_fallback()
        if frame is not None and not frame.empty:
            return frame
        frame = self._fetch_rankings_with_fallback("concept")
        if frame is not None and not frame.empty:
            return frame
        return self._fetch_board_names(source_fs="m:90 t:3 f:!50")

    def stock_board_industry_name_em(self) -> Any:
        concept_frame = self._fetch_board_changes_with_fallback()
        if concept_frame is not None and not concept_frame.empty:
            import pandas as pd

            return pd.DataFrame()
        frame = self._fetch_rankings_with_fallback("industry")
        if frame is not None and not frame.empty:
            return frame
        return self._fetch_board_names(source_fs="m:90 t:2 f:!50")

    def hotspot_rows(self, *, top: int = 12) -> List[Dict[str, Any]]:
        import pandas as pd

        frame = self.stock_board_concept_name_em()
        df = pd.DataFrame(frame)
        if df.empty:
            return []
        rows: List[Dict[str, Any]] = []
        for index, row in df.head(max(1, min(top, 50))).iterrows():
            name = _env_text(row.get("name") or row.get("板块名称") or row.get("行业名称") or row.get("名称"))
            if not name:
                continue
            change_pct = _safe_float(row.get("change_pct") or row.get("涨跌幅"))
            event_count = int(_safe_float(row.get("event_count") or row.get("observations")) or 0)
            leader = _env_text(row.get("leader"))
            leaders_raw = row.get("leaders")
            leaders = _list_text_values(leaders_raw) or ([leader] if leader else [])
            heat_score = _safe_float(row.get("heat_score"))
            if heat_score is None:
                heat_score = min(99.0, max(1.0, max(change_pct or 0.0, 0.0) * 9.0 + event_count / 120.0))
            trend_score = _safe_float(row.get("trend_score"))
            if trend_score is None:
                trend_score = self._derive_trend_score(change_pct=change_pct, event_count=event_count)
            persistence_score = _safe_float(row.get("persistence_score"))
            if persistence_score is None:
                persistence_score = self._derive_persistence_score(event_count=event_count)
            stage = _env_text(row.get("stage") or row.get("state")) or self._derive_hotspot_stage(
                change_pct=change_pct,
                event_count=event_count,
            )
            display_name = self._display_hotspot_name(name)
            rows.append({
                "topic": name,
                "name": display_name,
                "theme_group": self._hotspot_group(name),
                "source": "dsa_eastmoney_board_change",
                "rank": len(rows) + 1,
                "change_pct": change_pct,
                "heat_score": round(float(heat_score), 2),
                "trend_score": trend_score,
                "persistence_score": persistence_score,
                "observations": event_count,
                "state": stage,
                "stage": stage,
                "sample_stock_count": int(_safe_float(row.get("sample_stock_count")) or len(leaders)),
                "leaders": leaders,
            })
        return rows

    def stock_board_concept_cons_em(self, symbol: str = "") -> Any:
        cached = self._get_constituent_cache("concept", symbol)
        if cached is not None:
            return cached
        frames = [self._fetch_eastmoney_constituents(symbol, source="concept")]
        try:
            frames.append(self._fetch_ths_constituents(symbol))
        except Exception as exc:  # broad-exception: fallback_recorded - THS constituent failure is logged before alternative sources continue.
            log_safe_exception(
                logger,
                "AlphaSift THS constituent fetch failed; falling back to alternative sources",
                exc,
                error_code="alphasift_ths_constituent_fetch_failed",
                level=logging.WARNING,
                context={"symbol": symbol},
            )
        frames.append(self._fallback_constituents(symbol))
        frames.append(self._related_hotspot_constituents(symbol))
        frame = self._merge_constituent_frames(frames)
        self._set_constituent_cache("concept", symbol, frame)
        return frame

    def stock_board_industry_cons_em(self, symbol: str = "") -> Any:
        cached = self._get_constituent_cache("industry", symbol)
        if cached is not None:
            return cached
        frame = self._merge_constituent_frames([
            self._fetch_eastmoney_constituents(symbol, source="industry"),
            self._fallback_constituents(symbol),
        ])
        self._set_constituent_cache("industry", symbol, frame)
        return frame

    def hotspot_detail(self, topic: str) -> Dict[str, Any]:
        try:
            summary = self._find_board_change(topic)
        except Exception as exc:  # broad-exception: fallback_recorded - Board-summary failure is logged before detail fallback continues.
            log_safe_exception(
                logger,
                "AlphaSift board-change summary fetch failed; continuing without summary",
                exc,
                error_code="alphasift_board_change_summary_failed",
                level=logging.WARNING,
                context=_topic_log_context(topic, provider="eastmoney"),
            )
            summary = {}
        if self._is_industry_hotspot(topic):
            stocks = self._normalize_constituent_records(self.stock_board_industry_cons_em(topic))
        else:
            stocks = self._normalize_constituent_records(self.stock_board_concept_cons_em(topic))
        stocks = self._enrich_constituent_quotes(stocks)
        route = self._build_hotspot_route(topic, summary)
        info = self._fetch_ths_info(topic)
        if info:
            route.append({
                "title": "同花顺板块概况",
                "description": "；".join(f"{key} {value}" for key, value in list(info.items())[:4]),
                "source": "ths_info",
            })
        if not stocks and summary:
            stock_code = _env_text(summary.get("板块异动最频繁个股及所属类型-股票代码"))
            stock_name = _env_text(summary.get("板块异动最频繁个股及所属类型-股票名称"))
            if stock_code or stock_name:
                stocks.append({
                    "code": stock_code,
                    "name": stock_name,
                    "role": "异动核心",
                    "change_pct": None,
                    "hot_stock_score": 60.0,
                })
        return _ensure_hotspot_detail_compat_fields({
            "topic": topic,
            "name": self._display_hotspot_name(topic),
            "canonical_topic": topic,
            "summary": self._build_hotspot_summary(topic, summary),
            "route": route,
            "stocks": stocks[:30],
            "leader_stocks": stocks[:30],
            "stock_count": len(stocks),
            "source_errors": [],
        })

    def _fetch_board_changes(self) -> Any:
        import pandas as pd

        if self._board_changes_frame_cache is not None:
            return self._board_changes_frame_cache.copy()

        df = self._fetch_board_changes_raw()
        if df is None or df.empty:
            return pd.DataFrame()
        rows = []
        for index, row in df.iterrows():
            topic = _env_text(row.get("板块名称"))
            if not topic or self._is_broad_board(topic):
                continue
            change_pct = _safe_float(row.get("涨跌幅"))
            event_count = int(_safe_float(row.get("板块异动总次数")) or 0)
            leader = _env_text(row.get("板块异动最频繁个股及所属类型-股票名称"))
            heat_score = min(99.0, max(1.0, event_count / 120.0 + max(change_pct or 0.0, 0.0) * 9.0))
            trend_score = self._derive_trend_score(change_pct=change_pct, event_count=event_count)
            persistence_score = self._derive_persistence_score(event_count=event_count)
            leaders = [leader] if leader else []
            stage = self._derive_hotspot_stage(change_pct=change_pct, event_count=event_count)
            rows.append({
                "name": topic,
                "change_pct": change_pct,
                "rank": index + 1,
                "heat_score": heat_score,
                "trend_score": trend_score,
                "persistence_score": persistence_score,
                "observations": event_count,
                "state": stage,
                "stage": stage,
                "sample_stock_count": len(leaders),
                "leaders": leaders,
                "leader": leader,
                "event_count": event_count,
            })
        rows.sort(key=lambda item: (item.get("heat_score") or 0, item.get("event_count") or 0), reverse=True)
        frame = pd.DataFrame(rows)
        self._board_changes_frame_cache = frame
        return frame.copy()

    def _fetch_board_changes_raw(self) -> Any:
        import akshare as ak

        if self._board_changes_raw_cache is not None:
            return self._board_changes_raw_cache.copy()
        df = ak.stock_board_change_em()
        self._board_changes_raw_cache = df
        return df.copy() if df is not None else df

    def _fetch_board_changes_with_fallback(self) -> Any:
        import pandas as pd

        try:
            return self._fetch_board_changes()
        except Exception as exc:  # broad-exception: fallback_recorded - Board-change failure is logged before ranking fallback.
            log_safe_exception(
                logger,
                "AlphaSift hotspot board-change fetch failed; falling back to ranking/board names",
                exc,
                error_code="alphasift_board_change_fetch_failed",
                level=logging.WARNING,
            )
            return pd.DataFrame()

    def _is_broad_board(self, name: str) -> bool:
        return any(keyword in name for keyword in self._BROAD_BOARD_KEYWORDS)

    def _fetch_rankings(self, source: str) -> Any:
        import pandas as pd

        manager = _get_dsa_fetcher_manager()
        fetch = manager.get_concept_rankings if source == "concept" else manager.get_sector_rankings
        top, _bottom = fetch(100)
        rows = []
        for index, item in enumerate(top or []):
            name = _env_text((item or {}).get("name"))
            if not name:
                continue
            rows.append({
                "name": name,
                "change_pct": (item or {}).get("change_pct"),
                "rank": index + 1,
            })
        return pd.DataFrame(rows)

    def _fetch_rankings_with_fallback(self, source: str) -> Any:
        import pandas as pd

        try:
            return self._fetch_rankings(source)
        except Exception as exc:  # broad-exception: fallback_recorded - Ranking failure is logged before board-name fallback.
            log_safe_exception(
                logger,
                "AlphaSift hotspot ranking fetch failed; falling back to board names",
                exc,
                error_code="alphasift_ranking_fetch_failed",
                level=logging.WARNING,
                context={"source": source},
            )
            return pd.DataFrame()

    def _fetch_board_names(self, *, source_fs: str) -> Any:
        import pandas as pd

        params = dict(self._COMMON_PARAMS)
        params.update({"pz": "100", "fs": source_fs})
        response = self._eastmoney_get(
            self._BASE_URL,
            params=params,
            timeout=self._HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"},
        )
        response.raise_for_status()
        payload = response.json()
        rows = ((payload.get("data") or {}).get("diff") or []) if isinstance(payload, dict) else []
        normalized = [
            {
                "板块名称": str(row.get("f14") or "").strip(),
                "涨跌幅": row.get("f3"),
                "序号": index + 1,
                "name": str(row.get("f14") or "").strip(),
                "change_pct": row.get("f3"),
                "rank": index + 1,
                "leader": str(row.get("f140") or row.get("f128") or "").strip(),
                "up_count": row.get("f104"),
                "down_count": row.get("f105"),
                "source": "eastmoney_push2_board_spot",
            }
            for index, row in enumerate(rows)
            if str(row.get("f14") or "").strip()
        ]
        return pd.DataFrame(normalized)

    def _find_board_change(self, topic: str) -> Dict[str, Any]:
        df = self._fetch_board_changes_raw()
        if df is None or df.empty:
            return {}
        rows = df[df["板块名称"].astype(str) == topic]
        if rows.empty:
            rows = df[df["板块名称"].astype(str).str.contains(re.escape(topic), case=False, na=False)]
        if rows.empty:
            return {}
        return rows.iloc[0].to_dict()

    def _is_industry_hotspot(self, topic: str) -> bool:
        # EastMoney board-change rows are concept-like hot boards; if the topic is
        # already in that live change set, avoid an extra industry request.
        try:
            concept_frame = self._fetch_board_changes_with_fallback()
            if self._board_frame_contains_topic(concept_frame, topic):
                return False
        except Exception:  # broad-exception: optional_metadata - Concept-source classification may be skipped before industry fallback.
            pass
        try:
            frame = self.stock_board_industry_name_em()
        except Exception as exc:  # broad-exception: fallback_recorded - Industry-source failure is logged before concept fallback.
            log_safe_exception(
                logger,
                "AlphaSift industry hotspot source check failed; using concept constituents",
                exc,
                error_code="alphasift_industry_source_check_failed",
                level=logging.WARNING,
                context=_topic_log_context(topic, provider="eastmoney"),
            )
            return False
        return self._board_frame_contains_topic(frame, topic)

    def _derive_trend_score(self, *, change_pct: Optional[float], event_count: int) -> float:
        change_component = max(change_pct or 0.0, 0.0) * 12.0
        event_component = min(event_count / 8.0, 45.0)
        return round(min(99.0, max(1.0, change_component + event_component)), 1)

    def _derive_persistence_score(self, *, event_count: int) -> float:
        return round(min(99.0, max(1.0, event_count / 3.0)), 1)

    def _derive_hotspot_stage(self, *, change_pct: Optional[float], event_count: int) -> str:
        positive_change = max(change_pct or 0.0, 0.0)
        if event_count >= 180 and positive_change >= 3.0:
            return "加速发酵"
        if event_count >= 90:
            return "持续发酵"
        if positive_change >= 5.0:
            return "快速拉升"
        return "初次异动"

    def _hotspot_group(self, topic: str) -> str:
        topic_text = _env_text(topic)
        for keyword, group in self._METAL_TOPIC_GROUPS.items():
            if keyword and keyword in topic_text:
                return group
        return ""

    def _display_hotspot_name(self, topic: str) -> str:
        topic_text = _env_text(topic)
        group = self._hotspot_group(topic_text)
        if group and topic_text != group:
            return f"{group} · {topic_text}"
        return topic_text

    def _board_frame_contains_topic(self, frame: Any, topic: str) -> bool:
        import pandas as pd

        topic_text = _env_text(topic)
        if not topic_text:
            return False
        df = pd.DataFrame(frame)
        if df.empty:
            return False
        for column in ("name", "板块名称", "行业名称", "名称"):
            if column not in df.columns:
                continue
            values = df[column].map(_env_text)
            if bool((values == topic_text).any()):
                return True
        return False

    def _build_hotspot_summary(self, topic: str, summary: Dict[str, Any]) -> str:
        if not summary:
            return f"{topic} 当前暂无可用的板块异动摘要。"
        change_pct = _safe_float(summary.get("涨跌幅"))
        event_count = int(_safe_float(summary.get("板块异动总次数")) or 0)
        leader = _env_text(summary.get("板块异动最频繁个股及所属类型-股票名称"))
        action = _env_text(summary.get("板块异动最频繁个股及所属类型-买卖方向"))
        parts = [f"{topic} 当前涨跌幅 {change_pct:.2f}%" if change_pct is not None else f"{topic} 当前有异动记录"]
        if event_count:
            parts.append(f"盘中异动 {event_count} 次")
        if leader:
            parts.append(f"高频异动个股为 {leader}{f'（{action}）' if action else ''}")
        return "，".join(parts) + "。"

    def _build_hotspot_route(self, topic: str, summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        route_by_date: Dict[str, Dict[str, Any]] = {}
        today = datetime.now().date().isoformat()

        def put_daily_item(*, date: str, title: str, description: str, source: str) -> None:
            day = date or today
            existing = route_by_date.get(day)
            if existing:
                existing["description"] = f"{existing['description']}；{description}"
                if source and source not in str(existing.get("source") or ""):
                    existing["source"] = f"{existing.get('source')},{source}"
                return
            route_by_date[day] = {
                "title": title,
                "description": description,
                "source": source,
                "date": day,
                "published_at": day,
            }

        ths_event = self._fetch_ths_summary_event(topic)
        if ths_event:
            event_date = self._extract_route_date(ths_event) or today
            put_daily_item(
                date=event_date,
                title="题材驱动",
                description=ths_event,
                source="ths_summary",
            )
        if summary:
            change_events = self._parse_change_events(summary.get("板块具体异动类型列表及出现次数"))[:5]
            event_text = "；".join(f"{item['label']}出现 {item['count']} 次" for item in change_events)
            description = self._build_hotspot_summary(topic, summary)
            if event_text:
                description = f"{description} 当日结构：{event_text}。"
            put_daily_item(
                date=today,
                title="当日发酵",
                description=description,
                source="eastmoney_board_change",
            )
        route = [
            route_by_date[date]
            for date in sorted(route_by_date.keys(), reverse=True)
        ]
        if not route:
            route.append({
                "title": "等待发酵",
                "description": "暂未获取到明确催化事件，可继续观察涨跌幅、成交额和核心个股联动。",
                "source": "fallback",
                "date": today,
                "published_at": today,
            })
        return route

    def _extract_route_date(self, text: str) -> str:
        match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text or "")
        if not match:
            return ""
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"

    def _parse_change_events(self, raw: Any) -> List[Dict[str, Any]]:
        if isinstance(raw, str):
            try:
                import ast

                raw = ast.literal_eval(raw)
            except Exception:  # broad-exception: optional_metadata - Malformed optional event metadata falls back to an empty event list.
                raw = []
        events = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            event_type = int(_safe_float(item.get("t")) or 0)
            count = int(_safe_float(item.get("ct")) or 0)
            if not count:
                continue
            events.append({
                "type": event_type,
                "label": self._CHANGE_EVENT_LABELS.get(event_type, f"异动类型 {event_type}"),
                "count": count,
            })
        return sorted(events, key=lambda item: item["count"], reverse=True)

    def _fetch_ths_summary_event(self, topic: str) -> str:
        import akshare as ak

        try:
            df = ak.stock_board_concept_summary_ths()
        except Exception:  # broad-exception: optional_metadata - Optional THS summary failure yields no summary enrichment.
            return ""
        if df is None or df.empty:
            return ""
        if "概念名称" not in df.columns:
            logger.warning(
                "AlphaSift THS summary is missing the required concept-name column; skipping enrichment.",
            )
            return ""
        rows = df[df["概念名称"].astype(str) == topic]
        if rows.empty:
            rows = df[df["概念名称"].astype(str).str.contains(re.escape(topic), case=False, na=False)]
        if rows.empty:
            return ""
        row = rows.iloc[0]
        date = _env_text(row.get("日期"))
        event = _env_text(row.get("驱动事件"))
        return f"{date}：{event}" if date and event else event

    def _fetch_ths_info(self, topic: str) -> Dict[str, str]:
        import akshare as ak

        try:
            df = ak.stock_board_concept_info_ths(symbol=topic)
        except Exception:  # broad-exception: optional_metadata - Optional THS topic metadata failure yields no metadata.
            return {}
        if df is None or df.empty or "项目" not in df.columns or "值" not in df.columns:
            return {}
        return {
            _env_text(row.get("项目")): _env_text(row.get("值"))
            for _, row in df.iterrows()
            if _env_text(row.get("项目"))
        }

    def _fetch_eastmoney_constituents(self, topic: str, *, source: str) -> Any:
        import akshare as ak

        try:
            if source == "industry":
                return ak.stock_board_industry_cons_em(symbol=topic)
            return ak.stock_board_concept_cons_em(symbol=topic)
        except Exception:  # broad-exception: optional_metadata - Optional EastMoney constituent lookup falls through to other sources.
            return None

    def _fetch_ths_constituents(self, topic: str) -> Any:
        import pandas as pd
        from src.security.outbound_policy import safe_get

        code = self._resolve_ths_concept_code(topic)
        if not code:
            return pd.DataFrame()
        url = f"http://q.10jqka.com.cn/gn/detail/code/{code}/"
        response = safe_get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "http://q.10jqka.com.cn/gn/"},
            timeout=self._HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        html = response.content.decode("gbk", "ignore")
        rows = []
        seen = set()
        for match in re.finditer(r">(\d{6})<.*?>([^<>\n]{2,12})<", html, re.S):
            code_text = match.group(1)
            name_text = re.sub(r"\s+", "", match.group(2))
            if code_text in seen or not name_text or re.search(r"\d", name_text):
                continue
            seen.add(code_text)
            rows.append({"code": code_text, "name": name_text})
            if len(rows) >= 80:
                break
        return pd.DataFrame(rows)

    def _resolve_ths_concept_code(self, topic: str) -> str:
        import akshare as ak

        try:
            df = ak.stock_board_concept_name_ths()
        except Exception:  # broad-exception: optional_metadata - Optional THS concept-code lookup may yield no code.
            return ""
        if df is None or df.empty:
            return ""
        rows = df[df["name"].astype(str) == topic]
        if rows.empty:
            rows = df[df["name"].astype(str).str.contains(re.escape(topic), case=False, na=False)]
        if rows.empty and topic.endswith("概念"):
            base = topic[:-2]
            rows = df[df["name"].astype(str).str.contains(re.escape(base), case=False, na=False)]
        if rows.empty:
            return ""
        return _env_text(rows.iloc[0].get("code"))

    def _fallback_constituents(self, topic: str) -> Any:
        import pandas as pd

        try:
            summary = self._find_board_change(topic)
        except Exception as exc:  # broad-exception: fallback_recorded - Constituent fallback failure is logged before other sources continue.
            log_safe_exception(
                logger,
                "AlphaSift board-change constituent fallback failed; trying other sources",
                exc,
                error_code="alphasift_constituent_fallback_failed",
                level=logging.WARNING,
                context=_topic_log_context(topic, provider="eastmoney"),
            )
            return pd.DataFrame()
        code = _env_text(summary.get("板块异动最频繁个股及所属类型-股票代码"))
        name = _env_text(summary.get("板块异动最频繁个股及所属类型-股票名称"))
        if not code and not name:
            return pd.DataFrame()
        return pd.DataFrame([{
            "code": code,
            "name": name,
            "change_pct": None,
            "hot_stock_score": 60.0,
        }])

    def _related_hotspot_constituents(self, topic: str) -> Any:
        import pandas as pd

        group = self._hotspot_group(topic)
        if not group:
            return pd.DataFrame()
        try:
            raw = self._fetch_board_changes_raw()
        except Exception:  # broad-exception: optional_metadata - Related-board enrichment may be omitted when board changes are unavailable.
            return pd.DataFrame()
        df = pd.DataFrame(raw)
        if df.empty:
            return pd.DataFrame()
        rows: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for _, row in df.iterrows():
            board_name = _env_text(row.get("板块名称"))
            if not board_name or self._hotspot_group(board_name) != group:
                continue
            code = _env_text(row.get("板块异动最频繁个股及所属类型-股票代码"))
            name = _env_text(row.get("板块异动最频繁个股及所属类型-股票名称"))
            if not code and not name:
                continue
            key = code or name
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "code": code,
                "name": name,
                "change_pct": _safe_float(row.get("涨跌幅")),
                "role": f"{group}活跃股",
                "hot_stock_score": 35.0,
                "source": "eastmoney_board_change.related_group",
            })
            if len(rows) >= 12:
                break
        return pd.DataFrame(rows)

    def _get_constituent_cache(self, source: str, topic: str) -> Any:
        import pandas as pd

        if not hasattr(self, "_constituent_cache"):
            self._constituent_cache = {}
        frame = self._constituent_cache.get((source, _env_text(topic)))
        if frame is None:
            return None
        return pd.DataFrame(frame).copy()

    def _set_constituent_cache(self, source: str, topic: str, frame: Any) -> None:
        import pandas as pd

        if not hasattr(self, "_constituent_cache"):
            self._constituent_cache = {}
        self._constituent_cache[(source, _env_text(topic))] = pd.DataFrame(frame).copy()

    def _merge_constituent_frames(self, frames: List[Any]) -> Any:
        import pandas as pd

        merged: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for frame in frames:
            df = pd.DataFrame(frame)
            if df.empty:
                continue
            for _, row in df.iterrows():
                code = _env_text(row.get("code") or row.get("代码") or row.get("证券代码"))
                name = _env_text(row.get("name") or row.get("名称") or row.get("股票名称"))
                if not code and not name:
                    continue
                key = code or name
                if key in seen:
                    continue
                seen.add(key)
                record = row.to_dict()
                record.setdefault("code", code)
                record.setdefault("name", name)
                merged.append(record)
        return pd.DataFrame(merged)

    def _enrich_constituent_quotes(self, stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        codes = [str(item.get("code") or "").strip() for item in stocks if item.get("code")]
        codes = [code for code in codes if code][:12]
        if len(codes) < 4:
            return stocks
        try:
            manager = _get_dsa_fetcher_manager()
            manager.prefetch_realtime_quotes(codes)
        except Exception as exc:  # broad-exception: fallback_recorded - Quote-prefetch failure is logged before preserving source constituents.
            log_safe_exception(
                logger,
                "AlphaSift hotspot quote prefetch skipped",
                exc,
                error_code="alphasift_quote_prefetch_failed",
                level=logging.DEBUG,
            )
            return stocks
        quote_by_code: Dict[str, Any] = {}
        for code in codes:
            try:
                quote = manager.get_realtime_quote(code, log_final_failure=False)
            except Exception:  # broad-exception: optional_metadata - One optional quote failure omits enrichment for that symbol.
                quote = None
            if quote is not None:
                quote_by_code[code] = quote
        if not quote_by_code:
            return stocks
        enriched: List[Dict[str, Any]] = []
        for item in stocks:
            next_item = dict(item)
            code = str(next_item.get("code") or "").strip()
            quote = quote_by_code.get(code)
            if quote is not None:
                if next_item.get("change_pct") is None:
                    next_item["change_pct"] = _safe_float(getattr(quote, "change_pct", None))
                if next_item.get("amount") is None:
                    next_item["amount"] = _safe_float(getattr(quote, "amount", None))
                if next_item.get("turnover_rate") is None:
                    next_item["turnover_rate"] = _safe_float(getattr(quote, "turnover_rate", None))
                if next_item.get("volume_ratio") is None:
                    next_item["volume_ratio"] = _safe_float(getattr(quote, "volume_ratio", None))
                if next_item.get("hot_stock_score") in (None, 0.0):
                    next_item["hot_stock_score"] = min(99.0, max(1.0, abs(next_item.get("change_pct") or 0.0) * 8.0))
            enriched.append(next_item)
        return enriched

    def _normalize_constituent_records(self, frame: Any) -> List[Dict[str, Any]]:
        import pandas as pd

        df = pd.DataFrame(frame)
        if df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            code = _env_text(row.get("code") or row.get("代码") or row.get("证券代码"))
            name = _env_text(row.get("name") or row.get("名称") or row.get("股票名称"))
            if not code and not name:
                continue
            records.append({
                "code": code,
                "name": name,
                "change_pct": _safe_float(row.get("change_pct") or row.get("涨跌幅") or row.get("涨幅")),
                "amount": _safe_float(row.get("amount") or row.get("成交额") or row.get("成交金额")),
                "turnover_rate": _safe_float(row.get("turnover_rate") or row.get("换手率")),
                "volume_ratio": _safe_float(row.get("volume_ratio") or row.get("量比")),
                "role": _env_text(row.get("role")) or "概念股",
                "hot_stock_score": _safe_float(row.get("hot_stock_score")) or 0.0,
            })
        return records
