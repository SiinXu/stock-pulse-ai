"""Analysis orchestration and prompt method sources for the analyzer facade."""

from typing import TYPE_CHECKING, Any, Callable, Dict, ForwardRef, List, Optional, Tuple

if TYPE_CHECKING:
    from src.analyzer import (
        AnalysisResult,
        LOCAL_CLI_GENERATION_BACKEND_IDS,
        STOCK_NAME_MAP,
        _AllModelsFailedError,
        _legacy_audit_marker_specs,
        _legacy_market_group,
        _localized_text,
        _phase_aware_quote_labels,
        _safe_float,
        _sanitize_trend_analysis_for_prompt,
        _should_hide_regular_session_ohlc,
        _today_has_realtime_overlay,
        apply_placeholder_fill,
        check_content_integrity,
        format_daily_market_context_prompt_section,
        format_market_phase_prompt_section,
        format_market_structure_prompt_section,
        get_chip_unavailable_text,
        get_no_data_text,
        get_unknown_text,
        localize_confidence_level,
        localize_operation_advice,
        localize_trend_prediction,
        log_safe_exception,
        logger,
        logging,
        math,
        normalize_chip_structure_availability,
        normalize_report_language,
        persist_llm_usage,
        redact_diagnostic_text,
        resolve_news_window_days,
        should_persist_usage_telemetry,
        time,
    )
else:
    AnalysisResult = ForwardRef("AnalysisResult")


class GeminiAnalyzer:
    """Provide analysis and prompt descriptors for the legacy facade."""

    def analyze(
        self,
        context: Dict[str, Any],
        news_context: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        stream_progress_callback: Optional[Callable[[int], None]] = None,
        analysis_context_pack_summary: Optional[str] = None,
    ) -> AnalysisResult:
        """
        分析单只股票
\x20\x20\x20\x20\x20\x20\x20\x20
        流程：
        1. 格式化输入数据（技术面 + 新闻）
        2. 调用 Gemini API（带重试和模型切换）
        3. 解析 JSON 响应
        4. 返回结构化结果
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            context: 从 storage.get_analysis_context() 获取的上下文数据
            news_context: 预先搜索的新闻内容（可选）

        Returns:
            AnalysisResult 对象
        """
        def _emit_progress(progress: int, message: str) -> None:
            if progress_callback is None:
                return
            try:
                progress_callback(progress, message)
            except Exception as exc:  # broad-exception: optional_metadata - Progress callback failure cannot change the analysis result.
                log_safe_exception(
                    logger,
                    "Analyzer progress callback failed",
                    exc,
                    error_code="analyzer_progress_callback_failed",
                    level=logging.DEBUG,
                    redaction_values=self.get_generation_log_redaction_values(
                        fallback_error=exc,
                    ),
                )

        code = context.get('code', 'Unknown')
        config = self._get_runtime_config()
        report_language = normalize_report_language(getattr(config, "report_language", "zh"))
        system_prompt = self._get_analysis_system_prompt(report_language, stock_code=code)
        skill_instructions, default_skill_policy, use_legacy_default_prompt = self._get_skill_prompt_sections()

        # Add delay before request (to prevent consecutive requests triggering rate limits)
        request_delay = config.gemini_request_delay
        if request_delay > 0:
            logger.debug(f"[LLM] 请求前等待 {request_delay:.1f} 秒...")
            _emit_progress(65, f"{code}：LLM 请求前等待 {request_delay:.1f} 秒")
            time.sleep(request_delay)

        # Prioritize fetching stock name from context (passed in by main.py)
        name = context.get('stock_name')
        if not name or name.startswith('股票'):
            # Fallback: get from realtime
            if 'realtime' in context and context['realtime'].get('name'):
                name = context['realtime']['name']
            else:
                # Retrieve from mapping table
                name = STOCK_NAME_MAP.get(code, f'股票{code}')

        backend_error = self.get_generation_backend_config_error()
        if backend_error is not None and not self._can_use_generation_fallback(backend_error):
            details = backend_error.details or {}
            field = str(details.get("field") or "GENERATION_BACKEND")
            requested_backend = str(details.get("requested_backend") or backend_error.backend)
            reason = str(details.get("reason") or backend_error.error_code.value)
            if report_language == "en":
                summary = (
                    "AI analysis is unavailable because the generation backend "
                    f"cannot start: {backend_error.error_code.value}."
                )
                risk_warning = (
                    f"Check {field}={requested_backend} ({reason}) or set a valid "
                    "backend/fallback before retrying."
                )
            elif report_language == "ko":
                summary = (
                    "생성 백엔드를 시작할 수 없어 AI 분석을 사용할 수 없습니다: "
                    f"{backend_error.error_code.value}."
                )
                risk_warning = (
                    f"{field}={requested_backend} ({reason})를 확인하거나 유효한 "
                    "백엔드/폴백을 설정한 뒤 다시 시도하세요."
                )
            else:
                summary = (
                    "AI 分析功能不可用：生成后端无法启动，"
                    f"{backend_error.error_code.value}。"
                )
                risk_warning = (
                    f"请检查 {field}={requested_backend}（{reason}），"
                    "或配置有效后端/回退后重试。"
                )
            return AnalysisResult(
                code=code,
                name=name,
                sentiment_score=50,
                trend_prediction=localize_trend_prediction('震荡', report_language),
                operation_advice=localize_operation_advice('持有', report_language),
                confidence_level=localize_confidence_level('低', report_language),
                analysis_summary=summary,
                risk_warning=risk_warning,
                success=False,
                error_message=(
                    f"{backend_error.error_code.value}: {field}={requested_backend}"
                ),
                model_used=None,
                report_language=report_language,
            )

        # If the model is unavailable, return the default result
        if not self.is_available():
            return AnalysisResult(
                code=code,
                name=name,
                sentiment_score=50,
                trend_prediction=localize_trend_prediction('震荡', report_language),
                operation_advice=localize_operation_advice('持有', report_language),
                confidence_level=localize_confidence_level('低', report_language),
                analysis_summary=_localized_text(
                    report_language,
                    en='AI analysis is unavailable because no API key is configured.',
                    zh='AI 分析功能未启用（未配置 API Key）',
                    ko='API 키가 설정되지 않아 AI 분석을 사용할 수 없습니다.',
                ),
                risk_warning=_localized_text(
                    report_language,
                    en='Configure an LLM API key (GEMINI_API_KEY/ANTHROPIC_API_KEY/OPENAI_API_KEY) and retry.',
                    zh='请配置 LLM API Key（GEMINI_API_KEY/ANTHROPIC_API_KEY/OPENAI_API_KEY）后重试',
                    ko='LLM API 키(GEMINI_API_KEY/ANTHROPIC_API_KEY/OPENAI_API_KEY)를 설정한 뒤 다시 시도하세요.',
                ),
                success=False,
                error_message=_localized_text(
                    report_language,
                    en='LLM API key is not configured',
                    zh='LLM API Key 未配置',
                    ko='LLM API 키가 설정되지 않았습니다',
                ),
                model_used=None,
                report_language=report_language,
            )

        try:
            # Formatted input (including technical face data and news)
            prompt = self._format_prompt(
                context,
                name,
                news_context,
                report_language=report_language,
                analysis_context_pack_summary=analysis_context_pack_summary,
            )
            legacy_audit_context = {
                "language": report_language,
                "market_group": _legacy_market_group(code),
                "analysis_mode": "stock_analysis",
                "legacy_prompt_mode": "legacy_default" if use_legacy_default_prompt else "skill_aware",
                "skill_config": {
                    "skill_instructions": skill_instructions,
                    "default_skill_policy": default_skill_policy,
                    "use_legacy_default_prompt": use_legacy_default_prompt,
                },
                "transport": "litellm",
                "dynamic_markers": _legacy_audit_marker_specs(
                    context,
                    code=code,
                    stock_name=name,
                    report_language=report_language,
                    news_context=news_context,
                    analysis_context_pack_summary=analysis_context_pack_summary,
                ),
            }

            config = self._get_runtime_config()
            backend_id, _fallback_backend_id = self._resolve_generation_backend_config()
            model_name = config.litellm_model or "unknown"
            if backend_id in LOCAL_CLI_GENERATION_BACKEND_IDS:
                model_name = backend_id
                legacy_audit_context["transport"] = backend_id
            logger.info(f"========== AI 分析 {name}({code}) ==========")
            logger.info(f"[LLM配置] 模型: {model_name}")
            logger.info(f"[LLM配置] Prompt 长度: {len(prompt)} 字符")
            logger.info(f"[LLM配置] 是否包含新闻: {'是' if news_context else '否'}")

            # Local CLI backend is process execution capability, does not record complete prompt.
            if backend_id in LOCAL_CLI_GENERATION_BACKEND_IDS:
                prompt_preview = redact_diagnostic_text(prompt, limit=500)
            else:
                prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
            logger.info(f"[LLM Prompt 预览]\n{prompt_preview}")
            if backend_id not in LOCAL_CLI_GENERATION_BACKEND_IDS:
                logger.debug(f"=== 完整 Prompt ({len(prompt)}字符) ===\n{prompt}\n=== End Prompt ===")

            # Configure generation
            generation_config = {
                "temperature": config.llm_temperature,
                "max_output_tokens": 8192,
            }

            logger.info(f"[LLM调用] 开始调用 {model_name}...")
            _emit_progress(68, f"{name}：LLM 已接收请求，等待响应")

            # Use litellm to call (supports integrity check retry)
            current_prompt = prompt
            retry_count = 0
            max_retries = config.report_integrity_retry if config.report_integrity_enabled else 0

            while True:
                start_time = time.time()
                try:
                    response_text, model_used, llm_usage = self._call_litellm(
                        current_prompt,
                        generation_config,
                        system_prompt=system_prompt,
                        stream=True,
                        stream_progress_callback=stream_progress_callback,
                        response_validator=self._validate_json_response,
                        audit_context=legacy_audit_context,
                    )
                except _AllModelsFailedError as exc:
                    if exc.last_response_text is not None:
                        logger.warning(
                            "[LLM JSON] %s(%s): all models returned invalid JSON, using text fallback",
                            name,
                            code,
                        )
                        response_text = exc.last_response_text
                        model_used = exc.last_model
                        llm_usage = exc.last_usage
                    else:
                        raise
                elapsed = time.time() - start_time

                # Record response information
                logger.info(
                    f"[LLM返回] {model_name} 响应成功, 耗时 {elapsed:.2f}s, 响应长度 {len(response_text)} 字符"
                )
                if backend_id in LOCAL_CLI_GENERATION_BACKEND_IDS:
                    response_preview = redact_diagnostic_text(response_text, limit=300)
                else:
                    response_preview = response_text[:300] + "..." if len(response_text) > 300 else response_text
                logger.info(f"[LLM返回 预览]\n{response_preview}")
                if backend_id not in LOCAL_CLI_GENERATION_BACKEND_IDS:
                    logger.debug(
                        f"=== {model_name} 完整响应 ({len(response_text)}字符) ===\n{response_text}\n=== End Response ==="
                    )
                # Keep parser/retry progress monotonic so task progress/message never "goes backward".
                parse_progress = min(99, 93 + retry_count * 2)
                _emit_progress(parse_progress, f"{name}：LLM 返回完成，正在解析 JSON")

                # Parse response
                result = self._parse_response(response_text, code, name)
                result.raw_response = response_text
                result.search_performed = bool(news_context)
                result.market_snapshot = self._build_market_snapshot(context)
                result.model_used = model_used
                result.report_language = report_language
                normalize_chip_structure_availability(result, context.get("chip"))

                # Content integrity check (optional)
                if not config.report_integrity_enabled:
                    break
                require_phase_decision = isinstance(context.get("market_phase_context"), dict)
                pass_integrity, missing_fields = self._check_content_integrity(
                    result,
                    require_phase_decision=require_phase_decision,
                )
                if pass_integrity:
                    break
                if retry_count < max_retries:
                    current_prompt = self._build_integrity_retry_prompt(
                        prompt,
                        response_text,
                        missing_fields,
                        report_language=report_language,
                    )
                    retry_count += 1
                    logger.info(
                        "[LLM完整性] 必填字段缺失 %s，第 %d 次补全重试",
                        missing_fields,
                        retry_count,
                    )
                    retry_progress = min(99, 92 + retry_count * 2)
                    _emit_progress(
                        retry_progress,
                        f"{name}：报告字段不完整，正在补全重试（{retry_count}/{max_retries}）",
                    )
                else:
                    self._apply_placeholder_fill(result, missing_fields)
                    logger.warning(
                        "[LLM完整性] 必填字段缺失 %s，已占位补全，不阻塞流程",
                        missing_fields,
                    )
                    break

            if should_persist_usage_telemetry(llm_usage):
                persist_llm_usage(llm_usage, model_used, call_type="analysis", stock_code=code)

            logger.info(f"[LLM解析] {name}({code}) 分析完成: {result.trend_prediction}, 评分 {result.sentiment_score}")

            return result

        except Exception as e:  # broad-exception: fallback_recorded - Analysis failure is logged before returning the legacy fallback result.
            safe_error = self.sanitize_generation_diagnostic(e)
            logger.error("AI 分析 %s(%s) 失败: %s", name, code, safe_error)
            return AnalysisResult(
                code=code,
                name=name,
                sentiment_score=50,
                trend_prediction=localize_trend_prediction('震荡', report_language),
                operation_advice=localize_operation_advice('持有', report_language),
                confidence_level=localize_confidence_level('低', report_language),
                analysis_summary=_localized_text(
                    report_language,
                    en=f'Analysis failed: {safe_error[:100]}',
                    zh=f'分析过程出错: {safe_error[:100]}',
                    ko=f'분석 중 오류가 발생했습니다: {safe_error[:100]}',
                ),
                risk_warning=_localized_text(
                    report_language,
                    en='Analysis failed. Please retry later or review manually.',
                    zh='分析失败，请稍后重试或手动分析',
                    ko='분석에 실패했습니다. 잠시 후 다시 시도하거나 수동으로 검토하세요.',
                ),
                success=False,
                error_message=safe_error,
                model_used=None,
                report_language=report_language,
            )

    def _format_prompt(
        self,
        context: Dict[str, Any],
        name: str,
        news_context: Optional[str] = None,
        report_language: str = "zh",
        analysis_context_pack_summary: Optional[str] = None,
    ) -> str:
        """
        格式化分析提示词（决策仪表盘 v2.0）
\x20\x20\x20\x20\x20\x20\x20\x20
        包含：技术指标、实时行情（量比/换手率）、筹码分布、趋势分析、新闻
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            context: 技术面数据上下文（包含增强数据）
            name: 股票名称（默认值，可能被上下文覆盖）
            news_context: 预先搜索的新闻内容
        """
        code = context.get('code', 'Unknown')
        report_language = normalize_report_language(report_language)
        _, _, use_legacy_default_prompt = self._get_skill_prompt_sections()

        # Prioritize using stock name from context (from realtime_quote)
        stock_name = context.get('stock_name', name)
        if not stock_name or stock_name == f'股票{code}':
            stock_name = STOCK_NAME_MAP.get(code, f'股票{code}')

        today = context.get('today', {})
        unknown_text = get_unknown_text(report_language)
        no_data_text = get_no_data_text(report_language)
        quote_section_title, close_price_label = _phase_aware_quote_labels(context)
        hide_regular_session_ohlc = _should_hide_regular_session_ohlc(context)
        realtime_overlay_quote = hide_regular_session_ohlc and _today_has_realtime_overlay(today)
        pct_chg_label = "实时涨跌幅" if realtime_overlay_quote else "涨跌幅"
        volume_label = "实时成交量" if realtime_overlay_quote else "成交量"
        amount_label = "实时成交额" if realtime_overlay_quote else "成交额"
        quote_rows = [
            f"| {close_price_label} | {today.get('close', 'N/A')} 元 |",
        ]
        if not hide_regular_session_ohlc:
            quote_rows.extend(
                [
                    f"| 开盘价 | {today.get('open', 'N/A')} 元 |",
                    f"| 最高价 | {today.get('high', 'N/A')} 元 |",
                    f"| 最低价 | {today.get('low', 'N/A')} 元 |",
                ]
            )
        quote_rows.extend(
            [
                f"| {pct_chg_label} | {today.get('pct_chg', 'N/A')}% |",
                f"| {volume_label} | {self._format_volume(today.get('volume'))} |",
                f"| {amount_label} | {self._format_amount(today.get('amount'))} |",
            ]
        )
        quote_rows_text = "\n".join(quote_rows)

        # ========== Input for Building Decision Dashboard Format ==========
        prompt = f"""# 决策仪表盘分析请求

## 📊 股票基础信息
| 项目 | 数据 |
|------|------|
| 股票代码 | **{code}** |
| 股票名称 | **{stock_name}** |
| 分析日期 | {context.get('date', unknown_text)} |

---
"""
        prompt += format_market_phase_prompt_section(
            context.get("market_phase_context"),
            report_language=report_language,
        )
        daily_market_context_section = format_daily_market_context_prompt_section(
            context.get("daily_market_context"),
            report_language=report_language,
        )
        if daily_market_context_section:
            prompt += daily_market_context_section
        market_structure_section = format_market_structure_prompt_section(
            context.get("market_structure_context"),
            report_language=report_language,
        )
        if market_structure_section:
            prompt += market_structure_section
        if isinstance(analysis_context_pack_summary, str) and analysis_context_pack_summary:
            prompt += analysis_context_pack_summary
        decision_memory_prompt = context.get("decision_memory_reflection_prompt")
        if isinstance(decision_memory_prompt, str) and decision_memory_prompt:
            prompt += decision_memory_prompt
        prompt += f"""

## 📈 技术面数据

### {quote_section_title}
| 指标 | 数值 |
|------|------|
{quote_rows_text}

### 均线系统（关键判断指标）
| 均线 | 数值 | 说明 |
|------|------|------|
| MA5 | {today.get('ma5', 'N/A')} | 短期趋势线 |
| MA10 | {today.get('ma10', 'N/A')} | 中短期趋势线 |
| MA20 | {today.get('ma20', 'N/A')} | 中期趋势线 |
| 均线形态 | {context.get('ma_status', unknown_text)} | 多头/空头/缠绕 |
"""

        # Add real-time market data (volume ratio, turnover rate, etc.)
        if 'realtime' in context:
            rt = context['realtime']
            prompt += f"""
### 实时行情增强数据
| 指标 | 数值 | 解读 |
|------|------|------|
| 当前价格 | {rt.get('price', 'N/A')} 元 | |
| **量比** | **{rt.get('volume_ratio', 'N/A')}** | {rt.get('volume_ratio_desc', '')} |
| **换手率** | **{rt.get('turnover_rate', 'N/A')}%** | |
| 市盈率(动态) | {rt.get('pe_ratio', 'N/A')} | |
| 市净率 | {rt.get('pb_ratio', 'N/A')} | |
| 总市值 | {self._format_amount(rt.get('total_mv'))} | |
| 流通市值 | {self._format_amount(rt.get('circ_mv'))} | |
| 60日涨跌幅 | {rt.get('change_60d', 'N/A')}% | 中期表现 |
"""

        # Add financial reports and dividends (value investment perspective)
        fundamental_context = context.get("fundamental_context") if isinstance(context, dict) else None
        earnings_block = (
            fundamental_context.get("earnings", {})
            if isinstance(fundamental_context, dict)
            else {}
        )
        earnings_data = (
            earnings_block.get("data", {})
            if isinstance(earnings_block, dict)
            else {}
        )
        financial_report = (
            earnings_data.get("financial_report", {})
            if isinstance(earnings_data, dict)
            else {}
        )
        dividend_metrics = (
            earnings_data.get("dividend", {})
            if isinstance(earnings_data, dict)
            else {}
        )
        if isinstance(financial_report, dict) or isinstance(dividend_metrics, dict):
            financial_report = financial_report if isinstance(financial_report, dict) else {}
            dividend_metrics = dividend_metrics if isinstance(dividend_metrics, dict) else {}
            ttm_yield = dividend_metrics.get("ttm_dividend_yield_pct", "N/A")
            ttm_cash = dividend_metrics.get("ttm_cash_dividend_per_share", "N/A")
            ttm_count = dividend_metrics.get("ttm_event_count", "N/A")
            report_date = financial_report.get("report_date", "N/A")
            prompt += f"""
### 财报与分红（价值投资口径）
| 指标 | 数值 | 说明 |
|------|------|------|
| 最近报告期 | {report_date} | 来自结构化财报字段 |
| 营业收入 | {financial_report.get('revenue', 'N/A')} | |
| 归母净利润 | {financial_report.get('net_profit_parent', 'N/A')} | |
| 经营现金流 | {financial_report.get('operating_cash_flow', 'N/A')} | |
| ROE | {financial_report.get('roe', 'N/A')} | |
| 近12个月每股现金分红 | {ttm_cash} | 仅现金分红、税前口径 |
| TTM 股息率 | {ttm_yield} | 公式：近12个月每股现金分红 / 当前价格 × 100% |
| TTM 分红事件数 | {ttm_count} | |

> 若上述字段为 N/A 或缺失，请明确写“数据缺失，无法判断”，禁止编造。
"""

        capital_flow_block = (
            fundamental_context.get("capital_flow", {})
            if isinstance(fundamental_context, dict)
            else {}
        )
        capital_flow_data = (
            capital_flow_block.get("data", {})
            if isinstance(capital_flow_block, dict)
            else {}
        )
        stock_flow = (
            capital_flow_data.get("stock_flow", {})
            if isinstance(capital_flow_data, dict)
            else {}
        )
        sector_flow = (
            capital_flow_data.get("sector_rankings", {})
            if isinstance(capital_flow_data, dict)
            else {}
        )
        has_capital_flow = (
            isinstance(stock_flow, dict)
            and any(v is not None for v in stock_flow.values())
        ) or (
            isinstance(sector_flow, dict)
            and (sector_flow.get("top") or sector_flow.get("bottom"))
        )
        if has_capital_flow:
            top_sectors = sector_flow.get("top", []) if isinstance(sector_flow, dict) else []
            bottom_sectors = sector_flow.get("bottom", []) if isinstance(sector_flow, dict) else []
            top_sector_text = "、".join(
                str(item.get("name", "")).strip()
                for item in top_sectors[:3]
                if isinstance(item, dict) and str(item.get("name", "")).strip()
            ) or "N/A"
            bottom_sector_text = "、".join(
                str(item.get("name", "")).strip()
                for item in bottom_sectors[:3]
                if isinstance(item, dict) and str(item.get("name", "")).strip()
            ) or "N/A"
            prompt += f"""
### 主力资金流向（操作建议过滤器）
| 指标 | 数值 | 决策含义 |
|------|------|----------|
| 主力净流入 | {stock_flow.get('main_net_inflow', 'N/A')} | 正值偏支持，负值偏压制 |
| 5日净流入 | {stock_flow.get('inflow_5d', 'N/A')} | 用于判断资金持续性 |
| 10日净流入 | {stock_flow.get('inflow_10d', 'N/A')} | 用于判断资金持续性 |
| 资金流入靠前板块 | {top_sector_text} | 板块资金共振参考 |
| 资金流出靠前板块 | {bottom_sector_text} | 板块风险参考 |

> 资金流向只能作为价格位置的过滤器：接近压力且主力流出时不得追买；接近支撑且未放量跌破时，优先判断为持有观察、震荡或洗盘观察。
"""

        # Add Taiwan institutional-investor activity as a chip filter only when the institution block is ok
        # and all net-flow values exist. Other markets remain not_supported; this input is strictly additive.
        institution_block = (
            fundamental_context.get("institution", {})
            if isinstance(fundamental_context, dict)
            else {}
        )
        institution_data = (
            institution_block.get("data", {})
            if isinstance(institution_block, dict)
            else {}
        )
        if (
            isinstance(institution_block, dict)
            and institution_block.get("status") == "ok"
            and isinstance(institution_data, dict)
            and all(
                institution_data.get(key) is not None
                for key in ("foreign_net", "trust_net", "dealer_net", "total_net")
            )
        ):
            prompt += f"""
### 三大法人动向（台股筹码过滤器，净买卖超，单位:股）
| 法人 | 净买卖超 | 决策含义 |
|------|------|----------|
| 外资 | {institution_data.get('foreign_net', 'N/A')} | 正值=净买超偏支持，负值=净卖超偏压制 |
| 投信 | {institution_data.get('trust_net', 'N/A')} | 投信持续买超常伴随中线做多 |
| 自营商 | {institution_data.get('dealer_net', 'N/A')} | 短线避险/自营方向参考 |
| 三大法人合计 | {institution_data.get('total_net', 'N/A')} | 台股最受关注的筹码信号 |
| 资料日期 | {institution_data.get('date', 'N/A')} | 来源 {institution_data.get('source', 'N/A')} |

> 三大法人是台股的筹码过滤器（相当于 A 股主力资金/龙虎榜的角色，但口径不同、不可混用）：外资与投信同向净买支持价格、同向净卖压制价格。请据此判断台股筹码结构，不要在有本数据时写“筹码结构：数据缺失”。
"""

        # Add chip-distribution data.
        if 'chip' in context:
            chip = context['chip']
            profit_ratio = chip.get('profit_ratio', 0)
            prompt += f"""
### 筹码分布数据（效率指标）
| 指标 | 数值 | 健康标准 |
|------|------|----------|
| **获利比例** | **{profit_ratio:.1%}** | 70-90%时警惕 |
| 平均成本 | {chip.get('avg_cost', 'N/A')} 元 | 现价应高于5-15% |
| 90%筹码集中度 | {chip.get('concentration_90', 0):.2%} | <15%为集中 |
| 70%筹码集中度 | {chip.get('concentration_70', 0):.2%} | |
| 筹码状态 | {chip.get('chip_status', unknown_text)} | |
"""
        else:
            chip_unavailable_text = get_chip_unavailable_text(report_language)
            chip_instruction = (
                "Do not fabricate profit ratio, average cost, or concentration. Mention chip data "
                "unavailability only once in the report; do not repeat per-field no-data text in `chip_structure`."
                if report_language in ("en", "ko")
                else "请勿编造获利比例、平均成本或集中度；报告中只说明一次筹码数据不可用，不要把“数据缺失，无法判断”逐字段重复写入 `chip_structure`。"
            )
            prompt += f"""
### 筹码分布数据（效率指标）
> {chip_unavailable_text}
> {chip_instruction}
"""

        # Add trend analysis; only the implicit built-in bull_trend fallback preserves the legacy behavior.
        if 'trend_analysis' in context:
            trend = _sanitize_trend_analysis_for_prompt(
                context['trend_analysis'],
                volume_change_ratio=context.get('volume_change_ratio'),
            )
            consistency_notes = trend.get('prompt_consistency_notes', [])
            if use_legacy_default_prompt:
                bias_warning = "🚨 超过5%，严禁追高！" if trend.get('bias_ma5', 0) > 5 else "✅ 安全范围"
                prompt += f"""
### 趋势分析预判（基于交易理念）
| 指标 | 数值 | 判定 |
|------|------|------|
| 趋势状态 | {trend.get('trend_status', unknown_text)} | |
| 均线排列 | {trend.get('ma_alignment', unknown_text)} | MA5>MA10>MA20为多头 |
| 趋势强度 | {trend.get('trend_strength', 0)}/100 | |
| **乖离率(MA5)** | **{trend.get('bias_ma5', 0):+.2f}%** | {bias_warning} |
| 乖离率(MA10) | {trend.get('bias_ma10', 0):+.2f}% | |
| 量能状态 | {trend.get('volume_status', unknown_text)} | {trend.get('volume_trend', '')} |
| 系统信号 | {trend.get('buy_signal', unknown_text)} | |
| 系统评分 | {trend.get('signal_score', 0)}/100 | |

#### 系统分析理由
**买入理由**：
{chr(10).join('- ' + r for r in trend.get('signal_reasons', ['无'])) if trend.get('signal_reasons') else '- 无'}

**风险因素**：
{chr(10).join('- ' + r for r in trend.get('risk_factors', ['无'])) if trend.get('risk_factors') else '- 无'}
"""
                if consistency_notes:
                    prompt += f"""

**一致性约束**：
{chr(10).join('- ' + note for note in consistency_notes)}
"""
            else:
                bias_warning = (
                    "🚨 偏离较大，需谨慎评估追高风险"
                    if trend.get('bias_ma5', 0) > 5
                    else "✅ 位置相对可控"
                )
                prompt += f"""
### 技术与结构分析（供激活技能判断参考）
| 指标 | 数值 | 说明 |
|------|------|------|
| 趋势状态 | {trend.get('trend_status', unknown_text)} | |
| 均线排列 | {trend.get('ma_alignment', unknown_text)} | 结合激活技能判断结构强弱 |
| 趋势强度 | {trend.get('trend_strength', 0)}/100 | |
| **价格位置(MA5)** | **{trend.get('bias_ma5', 0):+.2f}%** | {bias_warning} |
| 价格位置(MA10) | {trend.get('bias_ma10', 0):+.2f}% | |
| 量能状态 | {trend.get('volume_status', unknown_text)} | {trend.get('volume_trend', '')} |
| 系统信号 | {trend.get('buy_signal', unknown_text)} | |
| 系统评分 | {trend.get('signal_score', 0)}/100 | |

#### 系统分析理由
**支持因素**：
{chr(10).join('- ' + r for r in trend.get('signal_reasons', ['无'])) if trend.get('signal_reasons') else '- 无'}

**风险因素**：
{chr(10).join('- ' + r for r in trend.get('risk_factors', ['无'])) if trend.get('risk_factors') else '- 无'}
"""
                if consistency_notes:
                    prompt += f"""

**一致性约束**：
{chr(10).join('- ' + note for note in consistency_notes)}
"""

        # Add yesterday's comparison data
        if 'yesterday' in context:
            volume_change = context.get('volume_change_ratio', 'N/A')
            prompt += f"""
### 量价变化
- 成交量较昨日变化：{volume_change}倍
- 价格较昨日变化：{context.get('price_change_ratio', 'N/A')}%
"""
            parsed_volume_change = _safe_float(volume_change, default=math.nan)
            if math.isfinite(parsed_volume_change) and parsed_volume_change > 10:
                prompt += """
- ⚠️ 量能异常提示：成交量较昨日放大超过10倍，可能受异常数据或一次性冲量影响，必须降权解读，不能机械视为强确认信号
"""

        # Add news search results (key regions)
        news_window_days: Optional[int] = None
        context_window = context.get("news_window_days")
        try:
            if context_window is not None:
                parsed_window = int(context_window)
                if parsed_window > 0:
                    news_window_days = parsed_window
        except (TypeError, ValueError):
            news_window_days = None

        if news_window_days is None:
            prompt_config = self._get_runtime_config()
            news_window_days = resolve_news_window_days(
                news_max_age_days=getattr(prompt_config, "news_max_age_days", 3),
                news_strategy_profile=getattr(prompt_config, "news_strategy_profile", "short"),
            )
        prompt += """
---

## 📰 舆情情报
"""
        if news_context:
            prompt += f"""
以下是 **{stock_name}({code})** 近{news_window_days}日的新闻搜索结果，请重点提取：
1. 🚨 **风险警报**：减持、处罚、利空
2. 🎯 **利好催化**：业绩、合同、政策
3. 📊 **业绩预期**：年报预告、业绩快报
4. 🕒 **时间规则（强制）**：
   - 输出到 `risk_alerts` / `positive_catalysts` / `latest_news` 的每一条都必须带具体日期（YYYY-MM-DD）
   - 超出近{news_window_days}日窗口的新闻一律忽略
   - 时间未知、无法确定发布日期的新闻一律忽略

```
{news_context}
```
"""
        else:
            prompt += """
未搜索到该股票近期的相关新闻。请主要依据技术面数据进行分析。
"""

        # Warning for missing data injection
        if context.get('data_missing'):
            prompt += """
⚠️ **数据缺失警告**
由于接口限制，当前无法获取完整的实时行情和技术指标数据。
请 **忽略上述表格中的 N/A 数据**，重点依据 **【📰 舆情情报】** 中的新闻进行基本面和情绪面分析。
在回答技术面问题（如均线、乖离率）时，请直接说明“数据缺失，无法判断”，**严禁编造数据**。
"""

        # Clear output requirements
        prompt += f"""
---

## ✅ 分析任务

请为 **{stock_name}({code})** 生成【决策仪表盘】，严格按照 JSON 格式输出。
"""
        if context.get('is_index_etf'):
            prompt += """
> ⚠️ **指数/ETF 分析约束**：该标的为指数跟踪型 ETF 或市场指数。
> - 风险分析仅关注：**指数走势、跟踪误差、市场流动性**
> - 严禁将基金公司的诉讼、声誉、高管变动纳入风险警报
> - 业绩预期基于**指数成分股整体表现**，而非基金公司财报
> - `risk_alerts` 中不得出现基金管理人相关的公司经营风险

"""
        prompt += f"""
### ⚠️ 重要：输出正确的股票名称格式
正确的股票名称格式为“股票名称（股票代码）”，例如“贵州茅台（600519）”。
如果上方显示的股票名称为"股票{code}"或不正确，请在分析开头**明确输出该股票的正确中文全称**。
"""
        if use_legacy_default_prompt:
            prompt += f"""

### 重点关注（必须明确回答）：
1. ❓ 是否满足 MA5>MA10>MA20 多头排列？
2. ❓ 当前乖离率是否在安全范围内（<5%）？—— 超过5%必须标注"严禁追高"
3. ❓ 量能是否配合（缩量回调/放量突破）？
4. ❓ 筹码结构是否健康？
5. ❓ 消息面有无重大利空？（减持、处罚、业绩变脸等）
"""
        else:
            prompt += f"""

### 重点关注（必须明确回答）：
1. ❓ 当前结构是否满足激活技能的关键触发条件？
2. ❓ 当前入场位置与风险回报是否合理？若偏离过大，请明确说明等待条件
3. ❓ 量能、波动与筹码结构是否支持当前结论？
4. ❓ 消息面有无重大利空或与技能结论冲突的信息？
5. ❓ 若结论成立，具体触发条件、止损位、观察点分别是什么？
"""
        prompt += f"""

### 决策仪表盘要求：
- **股票名称**：必须输出正确的中文全称（如"贵州茅台"而非"股票600519"）
- **核心结论**：一句话说清该买/该卖/该等
- **持仓分类建议**：空仓者怎么做 vs 持仓者怎么做
- **具体狙击点位**：买入价、止损价、目标价（精确到分）
- **检查清单**：每项用 ✅/⚠️/❌ 标记
- **消息面时间合规**：`latest_news`、`risk_alerts`、`positive_catalysts` 不得包含超出近{news_window_days}日或时间未知的信息
- **技术面一致性**：严禁把“空头排列”和“多头排列”等互斥结论同时当作有效依据；若基本面/事件面与技术面冲突，必须明确写“事件先行、技术待确认”或“基本面偏多，但技术面尚未确认”
\x20
请输出完整的 JSON 格式决策仪表盘。"""

        if report_language == "en":
            prompt += """

### Output language requirements (highest priority)
- Keep every JSON key exactly as defined above; do not translate keys.
- `decision_type` must remain `buy`, `hold`, or `sell`.
- All human-readable JSON values must be in English.
- This includes `stock_name`, `trend_prediction`, `operation_advice`, `confidence_level`, all nested dashboard text, checklist items, and every summary field.
- Use the common English company name when you are confident. If not, keep the listed company name rather than inventing one.
- When data is missing, explain it in English instead of Chinese.
"""
        elif report_language == "ko":
            prompt += """

### Output language requirements (highest priority)
- Keep every JSON key exactly as defined above; do not translate keys.
- `decision_type` must remain `buy`, `hold`, or `sell`.
- All human-readable JSON values must be in Korean (한국어).
- This includes `stock_name`, `trend_prediction`, `operation_advice`, `confidence_level`, all nested dashboard text, checklist items, and every summary field.
- Use the common Korean or original listed company name when you are confident. If not, keep the listed company name rather than inventing one.
- When data is missing, explain it in Korean instead of Chinese.
"""
        else:
            prompt += f"""

### 输出语言要求（最高优先级）
- 所有 JSON 键名必须保持不变，不要翻译键名。
- `decision_type` 必须保持为 `buy`、`hold`、`sell`。
- 所有面向用户的人类可读文本值必须使用中文。
- 当数据缺失时，请使用中文直接说明“{no_data_text}，无法判断”。
"""

        return prompt

    def _format_volume(self, volume: Optional[float]) -> str:
        """格式化成交量显示"""
        if volume is None:
            return 'N/A'
        if volume >= 1e8:
            return f"{volume / 1e8:.2f} 亿股"
        elif volume >= 1e4:
            return f"{volume / 1e4:.2f} 万股"
        else:
            return f"{volume:.0f} 股"

    def _format_amount(self, amount: Optional[float]) -> str:
        """格式化成交额显示"""
        if amount is None:
            return 'N/A'
        if amount >= 1e8:
            return f"{amount / 1e8:.2f} 亿元"
        elif amount >= 1e4:
            return f"{amount / 1e4:.2f} 万元"
        else:
            return f"{amount:.0f} 元"

    def _format_percent(self, value: Optional[float]) -> str:
        """格式化百分比显示"""
        if value is None:
            return 'N/A'
        try:
            return f"{float(value):.2f}%"
        except (TypeError, ValueError):
            return 'N/A'

    def _format_price(self, value: Optional[float]) -> str:
        """格式化价格显示"""
        if value is None:
            return 'N/A'
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return 'N/A'

    def _build_market_snapshot(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """构建当日行情快照（展示用）"""
        today = context.get('today', {}) or {}
        realtime = context.get('realtime', {}) or {}
        yesterday = context.get('yesterday', {}) or {}

        prev_close = yesterday.get('close')
        close = today.get('close')
        high = today.get('high')
        low = today.get('low')

        amplitude = None
        change_amount = None
        if prev_close not in (None, 0) and high is not None and low is not None:
            try:
                amplitude = (float(high) - float(low)) / float(prev_close) * 100
            except (TypeError, ValueError, ZeroDivisionError):
                amplitude = None
        if prev_close is not None and close is not None:
            try:
                change_amount = float(close) - float(prev_close)
            except (TypeError, ValueError):
                change_amount = None

        snapshot = {
            "date": context.get('date', '未知'),
            "close": self._format_price(close),
            "open": self._format_price(today.get('open')),
            "high": self._format_price(high),
            "low": self._format_price(low),
            "prev_close": self._format_price(prev_close),
            "pct_chg": self._format_percent(today.get('pct_chg')),
            "change_amount": self._format_price(change_amount),
            "amplitude": self._format_percent(amplitude),
            "volume": self._format_volume(today.get('volume')),
            "amount": self._format_amount(today.get('amount')),
        }

        if realtime:
            snapshot.update({
                "price": self._format_price(realtime.get('price')),
                "volume_ratio": realtime.get('volume_ratio', 'N/A'),
                "turnover_rate": self._format_percent(realtime.get('turnover_rate')),
                "source": getattr(realtime.get('source'), 'value', realtime.get('source', 'N/A')),
            })

        return snapshot

    def _check_content_integrity(
        self,
        result: AnalysisResult,
        *,
        require_phase_decision: bool = False,
    ) -> Tuple[bool, List[str]]:
        """Delegate to module-level check_content_integrity."""
        return check_content_integrity(result, require_phase_decision=require_phase_decision)

    def _build_integrity_complement_prompt(self, missing_fields: List[str], report_language: str = "zh") -> str:
        """Build complement instruction for missing mandatory fields."""
        report_language = normalize_report_language(report_language)
        if report_language in ("en", "ko"):
            lines = ["### Completion requirements: fill the missing mandatory fields below and output the full JSON again:"]
            for f in missing_fields:
                if f == "sentiment_score":
                    lines.append("- sentiment_score: integer score from 0 to 100")
                elif f == "operation_advice":
                    lines.append("- operation_advice: localized action advice")
                elif f == "analysis_summary":
                    lines.append("- analysis_summary: concise analysis summary")
                elif f == "dashboard.core_conclusion.one_sentence":
                    lines.append("- dashboard.core_conclusion.one_sentence: one-line decision")
                elif f == "dashboard.intelligence.risk_alerts":
                    lines.append("- dashboard.intelligence.risk_alerts: risk alert list (can be empty)")
                elif f == "dashboard.battle_plan.sniper_points.stop_loss":
                    lines.append("- dashboard.battle_plan.sniper_points.stop_loss: stop-loss level")
                elif f == "dashboard.phase_decision.phase_context":
                    lines.append("- dashboard.phase_decision.phase_context: public market phase summary subset")
                elif f == "dashboard.phase_decision.action_window":
                    lines.append("- dashboard.phase_decision.action_window: phase-aware action window")
                elif f == "dashboard.phase_decision.immediate_action":
                    lines.append("- dashboard.phase_decision.immediate_action: act now / wait / watch / no intraday action")
                elif f == "dashboard.phase_decision.watch_conditions":
                    lines.append("- dashboard.phase_decision.watch_conditions: list of watch conditions")
                elif f == "dashboard.phase_decision.next_check_time":
                    lines.append("- dashboard.phase_decision.next_check_time: next check point or market-local time")
                elif f == "dashboard.phase_decision.confidence_reason":
                    lines.append("- dashboard.phase_decision.confidence_reason: confidence rationale and data limits")
                elif f == "dashboard.phase_decision.data_limitations":
                    lines.append("- dashboard.phase_decision.data_limitations: list of phase/data quality limitations")
            return "\n".join(lines)

        lines = ["### 补全要求：请在上方分析基础上补充以下必填内容，并输出完整 JSON："]
        for f in missing_fields:
            if f == "sentiment_score":
                lines.append("- sentiment_score: 0-100 综合评分")
            elif f == "operation_advice":
                lines.append("- operation_advice: 买入/加仓/持有/减仓/卖出/观望")
            elif f == "analysis_summary":
                lines.append("- analysis_summary: 综合分析摘要")
            elif f == "dashboard.core_conclusion.one_sentence":
                lines.append("- dashboard.core_conclusion.one_sentence: 一句话决策")
            elif f == "dashboard.intelligence.risk_alerts":
                lines.append("- dashboard.intelligence.risk_alerts: 风险警报列表（可为空数组）")
            elif f == "dashboard.battle_plan.sniper_points.stop_loss":
                lines.append("- dashboard.battle_plan.sniper_points.stop_loss: 止损价")
            elif f == "dashboard.phase_decision.phase_context":
                lines.append("- dashboard.phase_decision.phase_context: 公开低敏市场阶段摘要子集")
            elif f == "dashboard.phase_decision.action_window":
                lines.append("- dashboard.phase_decision.action_window: 阶段化行动窗口")
            elif f == "dashboard.phase_decision.immediate_action":
                lines.append("- dashboard.phase_decision.immediate_action: 立即行动/等待确认/观察/无盘中动作")
            elif f == "dashboard.phase_decision.watch_conditions":
                lines.append("- dashboard.phase_decision.watch_conditions: 观察条件数组")
            elif f == "dashboard.phase_decision.next_check_time":
                lines.append("- dashboard.phase_decision.next_check_time: 下一次检查点或市场本地时间")
            elif f == "dashboard.phase_decision.confidence_reason":
                lines.append("- dashboard.phase_decision.confidence_reason: 置信度理由与数据限制")
            elif f == "dashboard.phase_decision.data_limitations":
                lines.append("- dashboard.phase_decision.data_limitations: 阶段/数据质量限制数组")
        return "\n".join(lines)

    def _build_integrity_retry_prompt(
        self,
        base_prompt: str,
        previous_response: str,
        missing_fields: List[str],
        report_language: str = "zh",
    ) -> str:
        """Build retry prompt using the previous response as the complement baseline."""
        complement = self._build_integrity_complement_prompt(missing_fields, report_language=report_language)
        previous_output = previous_response.strip()
        if normalize_report_language(report_language) in ("en", "ko"):
            prefix = "### The previous output is below. Complete the missing fields based on that output and return the full JSON again. Do not omit existing fields:"
        else:
            prefix = "### 上一次输出如下，请在该输出基础上补齐缺失字段，并重新输出完整 JSON。不要省略已有字段："
        return "\n\n".join([
            base_prompt,
            prefix,
            previous_output,
            complement,
        ])

    def _apply_placeholder_fill(self, result: AnalysisResult, missing_fields: List[str]) -> None:
        """Delegate to module-level apply_placeholder_fill."""
        apply_placeholder_fill(result, missing_fields)
