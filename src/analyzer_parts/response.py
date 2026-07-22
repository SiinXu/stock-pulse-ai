"""Response assembly method sources for the analyzer facade."""

from typing import TYPE_CHECKING, Any, Dict, ForwardRef, List, Tuple

from src.llm.generation_backend import GenerationError, GenerationErrorCode

if TYPE_CHECKING:
    from src.analyzer import (
        AnalysisReportSchema,
        AnalysisResult,
        _localized_text,
        infer_decision_type_from_advice,
        json,
        localize_confidence_level,
        localize_operation_advice,
        localize_trend_prediction,
        log_safe_exception,
        logger,
        logging,
        normalize_report_language,
        normalize_report_signal_attribution,
        populate_decision_action_fields,
        re,
        repair_json,
        time,
    )
else:
    AnalysisResult = ForwardRef("AnalysisResult")


class GeminiAnalyzer:
    """Provide response assembly descriptors for the legacy facade."""

    def _extract_analysis_json_object(self, response_text: str) -> Tuple[str, Dict[str, Any]]:
        """Extract the single allowed JSON object from an LLM response."""

        text = response_text or ""
        stripped = text.strip()
        if not stripped:
            raise ValueError("empty_response")

        fence_pattern = re.compile(
            r"```[ \t]*(?P<lang>[A-Za-z0-9_-]*)[ \t]*\n?(?P<body>.*?)```",
            flags=re.DOTALL,
        )
        fenced_matches = list(fence_pattern.finditer(text))
        if len(fenced_matches) > 1:
            raise ValueError("ambiguous_json")
        if len(fenced_matches) == 1:
            match = fenced_matches[0]
            outside = (text[:match.start()] + text[match.end():]).strip()
            if outside:
                raise ValueError("ambiguous_json")
            fence_lang = (match.group("lang") or "").strip().lower()
            if fence_lang not in {"", "json"}:
                raise ValueError("ambiguous_json")
            json_str = match.group("body").strip()
            data = self._load_analysis_json_candidate(json_str)
            return json_str, data
        if "```" in text:
            raise ValueError("ambiguous_json")

        try:
            data = self._load_analysis_json_candidate(stripped)
        except json.JSONDecodeError as exc:
            if self._contains_embedded_json_object(text):
                raise ValueError("ambiguous_json") from exc
            raise
        return stripped, data

    def _load_analysis_json_candidate(self, json_str: str) -> Dict[str, Any]:
        """Parse one already-selected JSON candidate, repairing common LLM JSON drift."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            stripped = (json_str or "").strip()
            try:
                _obj, end = json.JSONDecoder().raw_decode(stripped)
            except json.JSONDecodeError:
                pass
            else:
                if stripped[end:].strip():
                    raise
            if not (stripped.startswith("{") and stripped.endswith("}")):
                raise
            repaired = self._fix_json_string(stripped)
            data = json.loads(repaired)
        if not isinstance(data, dict):
            raise TypeError("json_root_not_object")
        return data

    @staticmethod
    def _contains_embedded_json_object(text: str) -> bool:
        decoder = json.JSONDecoder()
        count = 0
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                _obj, end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            count += 1
            before = text[:index].strip()
            after = text[index + end:].strip()
            if count > 1 or before or after:
                return True
        return False

    def _validate_analysis_minimal_contract(self, data: Dict[str, Any]) -> None:
        try:
            AnalysisReportSchema.model_validate(data)
        except Exception as exc:  # broad-exception: fallback_recorded - Schema failure is logged before parser fallback continues.
            log_safe_exception(
                logger,
                "Analysis report schema validation failed; continuing with parser fallback",
                exc,
                error_code="analysis_report_schema_validation_failed",
                level=logging.WARNING,
                redaction_values=self.get_generation_log_redaction_values(
                    fallback_error=exc,
                ),
            )
        minimal_keys = {
            "sentiment_score",
            "trend_prediction",
            "operation_advice",
            "analysis_summary",
            "dashboard",
        }
        if not any(key in data for key in minimal_keys):
            raise self._generation_validation_error(
                GenerationErrorCode.SCHEMA_VALIDATION_FAILED,
                reason="minimal_contract_failed",
                message="analysis JSON does not contain any minimal parser field",
            )
        if "sentiment_score" in data:
            try:
                int(data.get("sentiment_score", 50))
            except (TypeError, ValueError) as exc:
                raise self._generation_validation_error(
                    GenerationErrorCode.SCHEMA_VALIDATION_FAILED,
                    reason="parser_contract_failed",
                    message="sentiment_score must be integer-compatible",
                ) from exc

    def _generation_validation_error(
        self,
        error_code: GenerationErrorCode,
        *,
        reason: str,
        message: str,
    ) -> GenerationError:
        try:
            backend_id, _fallback_backend_id = self._resolve_generation_backend_config()
        except GenerationError:
            backend_id = "generation_backend"
        return GenerationError(
            error_code=error_code,
            stage="validation",
            retryable=True,
            fallbackable=True,
            backend=backend_id,
            provider=backend_id,
            details={
                "reason": reason,
                "message": message,
            },
        )

    def _parse_response(
        self,
        response_text: str,
        code: str,
        name: str
    ) -> AnalysisResult:
        """
        Parse Gemini responses (decision dashboard version)
\x20\x20\x20\x20\x20\x20\x20\x20
        Attempt to extract JSON formatted analysis results from the response, including dashboard field
        If parsing fails, attempt intelligent extraction or return default results.
        """
        try:
            report_language = normalize_report_language(
                getattr(self._get_runtime_config(), "report_language", "zh")
            )
            try:
                _json_str, data = self._extract_analysis_json_object(response_text)
                self._validate_analysis_minimal_contract(data)
            except Exception as exc:  # broad-exception: fallback_recorded - JSON extraction failure is logged before text fallback.
                log_safe_exception(
                    logger,
                    "Unique analysis JSON extraction failed; using text fallback",
                    exc,
                    error_code="analysis_json_extraction_failed",
                    level=logging.WARNING,
                    context={"symbol": code},
                    redaction_values=self.get_generation_log_redaction_values(
                        fallback_error=exc,
                    ),
                )
                return self._parse_text_response(response_text, code, name)

            # Extracts dashboard data
            dashboard = data.get('dashboard', None)
            guardrail_reason = data.get("guardrail_reason") or data.get("downgrade_reason")
            if guardrail_reason and isinstance(dashboard, dict):
                score_calibration = dashboard.get("decision_score_calibration")
                if not isinstance(score_calibration, dict):
                    score_calibration = {}
                    dashboard["decision_score_calibration"] = score_calibration
                score_calibration.setdefault("guardrail_reason", str(guardrail_reason).strip())
            # Normalize signal_attribution (LLM may return strings/negative numbers/sums ≠ 100)
            normalize_report_signal_attribution(dashboard)

            # Prioritize using AI-returned stock name (if original name is invalid or contains code)
            ai_stock_name = data.get('stock_name')
            if ai_stock_name and (name.startswith('股票') or name == code or 'Unknown' in name):
                name = ai_stock_name

            # Parse all fields, use default values to prevent missing data
            # Infer decision_type if not present, based on operation_advice
            decision_type = data.get('decision_type', '')
            if not decision_type:
                op = data.get('operation_advice', localize_operation_advice('持有', report_language))
                decision_type = infer_decision_type_from_advice(op, default='hold')

            explicit_action = data.get("action")
            if explicit_action is None and isinstance(dashboard, dict):
                explicit_action = dashboard.get("action")

            result = AnalysisResult(
                code=code,
                name=name,
                # Key Indicators
                sentiment_score=int(data.get('sentiment_score', 50)),
                trend_prediction=data.get('trend_prediction', localize_trend_prediction('震荡', report_language)),
                operation_advice=data.get('operation_advice', localize_operation_advice('持有', report_language)),
                decision_type=decision_type,
                confidence_level=localize_confidence_level(
                    data.get('confidence_level', localize_confidence_level('中', report_language)),
                    report_language,
                ),
                report_language=report_language,
                # Decision dashboard
                dashboard=dashboard,
                # Trend analysis
                trend_analysis=data.get('trend_analysis', ''),
                short_term_outlook=data.get('short_term_outlook', ''),
                medium_term_outlook=data.get('medium_term_outlook', ''),
                # Technical view
                technical_analysis=data.get('technical_analysis', ''),
                ma_analysis=data.get('ma_analysis', ''),
                volume_analysis=data.get('volume_analysis', ''),
                pattern_analysis=data.get('pattern_analysis', ''),
                # Fundamentals
                fundamental_analysis=data.get('fundamental_analysis', ''),
                sector_position=data.get('sector_position', ''),
                company_highlights=data.get('company_highlights', ''),
                # Sentiment/News sentiment
                news_summary=data.get('news_summary', ''),
                market_sentiment=data.get('market_sentiment', ''),
                hot_topics=data.get('hot_topics', ''),
                # Comprehensive
                analysis_summary=data.get('analysis_summary', _localized_text(
                    report_language, en='Analysis completed', zh='分析完成', ko='분석 완료')),
                key_points=data.get('key_points', ''),
                risk_warning=data.get('risk_warning', ''),
                buy_reason=data.get('buy_reason', ''),
                # Metadata
                search_performed=data.get('search_performed', False),
                data_sources=data.get('data_sources', _localized_text(
                    report_language, en='Technical data', zh='技术面数据', ko='기술적 데이터')),
                success=True,
            )
            return populate_decision_action_fields(
                result,
                explicit_action=explicit_action,
                align_with_score=False,
            )

        except json.JSONDecodeError as e:
            log_safe_exception(
                logger,
                "Analysis JSON parsing failed; using text fallback",
                e,
                error_code="analysis_json_parsing_failed",
                level=logging.WARNING,
                context={"symbol": code},
                redaction_values=self.get_generation_log_redaction_values(
                    fallback_error=e,
                ),
            )
            return self._parse_text_response(response_text, code, name)

    def _fix_json_string(self, json_str: str) -> str:
        """Fix common JSON format issues"""
        import re

        # Remove comment
        json_str = re.sub(r'//.*?\n', '\n', json_str)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)

        # Fix trailing comma
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)

        # Ensure boolean values are lowercase
        json_str = json_str.replace('True', 'true').replace('False', 'false')

        # fix by json-repair
        json_str = repair_json(json_str)

        return json_str

    def _validate_json_response(self, text: str) -> None:
        """Validate that *text* contains one parser-compatible JSON object.

        Used as the ``response_validator`` argument to :meth:`_call_litellm` so
        that a JSON-less or unparseable reply from the primary model is treated
        as a model failure and triggers fallback to the next configured model.

        Raises:
            GenerationError: if the response has no unique parser-compatible
                JSON object, the selected JSON candidate cannot be parsed, or
                the parsed object cannot satisfy the minimal parser contract.
        """
        try:
            _json_str, data = self._extract_analysis_json_object(text)
        except ValueError as exc:
            reason = str(exc) or "invalid_json"
            if reason == "ambiguous_json":
                message = "JSON source is ambiguous"
            else:
                message = "No unique JSON object found in LLM response"
            raise self._generation_validation_error(
                GenerationErrorCode.INVALID_JSON,
                reason=reason,
                message=message,
            ) from exc
        except json.JSONDecodeError as exc:
            raise self._generation_validation_error(
                GenerationErrorCode.INVALID_JSON,
                reason="invalid_json",
                message=str(exc)[:200],
            ) from exc
        except Exception as exc:  # broad-exception: cleanup - Unexpected validation failure becomes the existing typed generation error.
            raise self._generation_validation_error(
                GenerationErrorCode.INVALID_JSON,
                reason="invalid_json",
                message=str(exc)[:200],
            ) from exc

        self._validate_analysis_minimal_contract(data)

    def _parse_text_response(
        self,
        response_text: str,
        code: str,
        name: str
    ) -> AnalysisResult:
        """Extract as much analysis information as possible from plain text responses."""
        report_language = normalize_report_language(
            getattr(self._get_runtime_config(), "report_language", "zh")
        )
        # Attempt to recognize keywords to determine sentiment
        sentiment_score = 50
        trend = localize_trend_prediction('震荡', report_language)
        advice = localize_operation_advice('持有', report_language)

        text_lower = response_text.lower()

        # Simple sentiment recognition
        positive_keywords = ['看多', '买入', '上涨', '突破', '强势', '利好', '加仓', 'bullish', 'buy']
        negative_keywords = ['看空', '卖出', '下跌', '跌破', '弱势', '利空', '减仓', 'bearish', 'sell']

        positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in text_lower)

        if positive_count > negative_count + 1:
            sentiment_score = 65
            trend = localize_trend_prediction('看多', report_language)
            advice = localize_operation_advice('买入', report_language)
            decision_type = 'buy'
        elif negative_count > positive_count + 1:
            sentiment_score = 35
            trend = localize_trend_prediction('看空', report_language)
            advice = localize_operation_advice('卖出', report_language)
            decision_type = 'sell'
        else:
            decision_type = 'hold'

        # Truncate top 500 characters as a summary
        summary = response_text[:500] if response_text else _localized_text(
            report_language, en='No analysis result', zh='无分析结果', ko='분석 결과 없음')

        result = AnalysisResult(
            code=code,
            name=name,
            sentiment_score=sentiment_score,
            trend_prediction=trend,
            operation_advice=advice,
            decision_type=decision_type,
            confidence_level=localize_confidence_level('低', report_language),
            analysis_summary=summary,
            key_points=_localized_text(
                report_language,
                en='JSON parsing failed; treat this as best-effort output.',
                zh='JSON解析失败，仅供参考',
                ko='JSON 파싱에 실패했습니다. 참고용으로만 사용하세요.',
            ),
            risk_warning=_localized_text(
                report_language,
                en='The result may be inaccurate. Cross-check with other information.',
                zh='分析结果可能不准确，建议结合其他信息判断',
                ko='결과가 부정확할 수 있습니다. 다른 정보와 교차 확인하세요.',
            ),
            raw_response=response_text,
            success=False,
            error_message='LLM response is not valid JSON; analysis result will not be persisted',
            report_language=report_language,
        )
        return populate_decision_action_fields(result, align_with_score=False)

    def batch_analyze(
        self,
        contexts: List[Dict[str, Any]],
        delay_between: float = 2.0
    ) -> List[AnalysisResult]:
        """
        Bulk analysis of multiple stocks
\x20\x20\x20\x20\x20\x20\x20\x20
        Note: There will be delays between analyses to avoid API rate limits.
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            contexts: context data list
            delay_between: delay between analyses (seconds)
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
        Returns:
            AnalysisResult list
        """
        results = []

        for i, context in enumerate(contexts):
            if i > 0:
                logger.debug(f"等待 {delay_between} 秒后继续...")
                time.sleep(delay_between)

            result = self.analyze(context)
            results.append(result)

        return results
