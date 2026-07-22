# -*- coding: utf-8 -*-
"""Market review generation, rendering, and payload contracts."""

from tests.market_analyzer_generate_text_support import (
    MagicMock,
    RotatingGenerationError,
    SimpleNamespace,
    _llm_usage_hmac_env,
    patch,
    pytest,
)


# MarketAnalyzer public generation and rendering contracts

class TestMarketAnalyzerBypassFix:
    def _make_market_analyzer_with_mock_generate_text(self, return_value="复盘报告"):
        """Return a MarketAnalyzer whose embedded Analyzer.generate_text is mocked."""
        from src.core.market_profile import CN_PROFILE
        from src.core.market_strategy import get_market_strategy_blueprint

        with patch("src.analyzer.get_config") as mock_cfg, \
             patch("src.market_analyzer.get_config") as mock_cfg2:
            cfg = MagicMock()
            cfg.litellm_model = "gemini/gemini-2.0-flash"
            cfg.litellm_fallback_models = []
            cfg.gemini_api_keys = ["sk-gemini-testkey-1234"]
            cfg.anthropic_api_keys = []
            cfg.openai_api_keys = []
            cfg.deepseek_api_keys = []
            cfg.llm_model_list = []
            cfg.openai_base_url = None
            cfg.market_review_region = "cn"
            cfg.market_review_color_scheme = "green_up"
            cfg.report_language = "zh"
            cfg.generation_backend = "litellm"
            cfg.generation_fallback_backend = "litellm"
            mock_cfg.return_value = cfg
            mock_cfg2.return_value = cfg

            from src.analyzer import GeminiAnalyzer
            from src.market_analyzer import MarketAnalyzer

            analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
            analyzer._router = None
            analyzer._litellm_available = True
            analyzer._config_override = cfg
            analyzer.generate_text = MagicMock(return_value=return_value)

            ma = MarketAnalyzer.__new__(MarketAnalyzer)
            ma.analyzer = analyzer
            ma.config = cfg
            ma.profile = CN_PROFILE
            ma.strategy = get_market_strategy_blueprint("cn")
            ma.region = "cn"
            return ma

    def test_no_access_to_private_model_attribute(self):
        """generate_text() must be called; _model must never be accessed."""
        ma = self._make_market_analyzer_with_mock_generate_text("复盘结果")
        # Ensure _model attribute does not exist (simulates PR #494 state)
        assert not hasattr(ma.analyzer, "_model") or ma.analyzer._model is None, (
            "_model should not be set on the LiteLLM-based analyzer"
        )
        # generate_text is a MagicMock, so calling it won't crash
        result = ma.analyzer.generate_text("prompt")
        assert isinstance(result, str) and len(result) > 0
        ma.analyzer.generate_text.assert_called_once()

    def test_generate_text_none_falls_back_to_template(self):
        """generate_market_review() falls back to template when generate_text returns None."""
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="000001",
                    name="上证指数",
                    current=3300.0,
                    change=5.0,
                    change_pct=0.15,
                )
            ],
        )
        result = ma.generate_market_review(overview, [])
        assert isinstance(result, str) and len(result) > 0
        ma.analyzer.generate_text.assert_called_once()

    def test_generation_backend_config_error_does_not_template_fallback(self):
        from src.llm.generation_backend import GenerationError
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.analyzer._config_override.generation_backend = "codex"
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="000001",
                    name="上证指数",
                    current=3300.0,
                    change=5.0,
                    change_pct=0.15,
                )
            ],
        )

        with patch.object(ma, "_generate_template_review", wraps=ma._generate_template_review) as template_review, \
             patch("src.market_analyzer.record_llm_run") as mock_record_llm_run:
            with pytest.raises(GenerationError) as exc_info:
                ma.generate_market_review(overview, [])

        assert exc_info.value.details["field"] == "GENERATION_BACKEND"
        assert exc_info.value.details["requested_backend"] == "codex"
        template_review.assert_not_called()
        ma.analyzer.generate_text.assert_not_called()
        mock_record_llm_run.assert_called_once()
        diagnostic = mock_record_llm_run.call_args.kwargs
        assert diagnostic["success"] is False
        assert diagnostic["call_type"] == "market_review"
        assert diagnostic["error_type"] == "GenerationError"
        assert "backend_not_configured" in str(diagnostic["error_message"])

    def test_local_backend_execution_error_does_not_template_fallback(self):
        from src.llm.generation_backend import GenerationError, GenerationErrorCode
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.analyzer.generate_text.side_effect = GenerationError(
            error_code=GenerationErrorCode.COMMAND_NOT_FOUND,
            stage="configuration",
            retryable=False,
            fallbackable=True,
            backend="codex_cli",
            provider="codex_cli",
            details={"reason": "executable_not_found"},
        )
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="000001",
                    name="上证指数",
                    current=3300.0,
                    change=5.0,
                    change_pct=0.15,
                )
            ],
        )

        with patch.object(ma, "_generate_template_review", wraps=ma._generate_template_review) as template_review:
            with pytest.raises(GenerationError) as exc_info:
                ma.generate_market_review(overview, [])

        assert exc_info.value.error_code is GenerationErrorCode.COMMAND_NOT_FOUND
        template_review.assert_not_called()

    def test_market_review_sanitizes_generation_failure_diagnostic(self):
        from src.market_analyzer import MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        secret = ma.config.gemini_api_keys[0]
        ma.analyzer.generate_text.side_effect = RuntimeError(
            f"upstream saw {secret}"
        )
        overview = MarketOverview(date="2026-03-05")

        with patch("src.market_analyzer.record_llm_run") as mock_record_llm_run:
            with pytest.raises(RuntimeError):
                ma.generate_market_review(overview, [])

        diagnostic = mock_record_llm_run.call_args.kwargs["error_message"]
        assert secret not in diagnostic
        assert "[REDACTED]" in diagnostic

    def test_market_review_fails_closed_when_analyzer_sanitizers_raise(self):
        from src.market_analyzer import MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        opaque_secret = "opaque configured value 8kT3"
        ma.analyzer.generate_text.side_effect = RuntimeError(
            f"upstream echoed {opaque_secret}"
        )
        overview = MarketOverview(date="2026-03-05")

        with patch.object(
            ma.analyzer,
            "get_generation_log_redaction_values",
            side_effect=RuntimeError("redaction lookup unavailable"),
        ), patch.object(
            ma.analyzer,
            "sanitize_generation_diagnostic",
            side_effect=RuntimeError("sanitizer unavailable"),
        ), patch("src.market_analyzer.record_llm_run") as mock_record_llm_run:
            with pytest.raises(RuntimeError):
                ma.generate_market_review(overview, [])

        diagnostic = mock_record_llm_run.call_args.kwargs["error_message"]
        assert opaque_secret not in diagnostic
        assert "[REDACTED]" in diagnostic

    def test_market_review_preserves_single_render_exception_snapshot(self):
        from src.utils.sanitize import exception_chain_redaction_values

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        error = RotatingGenerationError()
        snapshot = exception_chain_redaction_values(error)

        with patch.object(
            ma.analyzer,
            "get_generation_log_redaction_values",
            return_value=snapshot,
        ), patch.object(
            ma.analyzer,
            "sanitize_generation_diagnostic",
            side_effect=lambda value, **_kwargs: str(value),
        ) as analyzer_sanitizer:
            diagnostic = ma._sanitize_generation_diagnostic(error)

        assert error.render_count == 1
        analyzer_sanitizer.assert_not_called()
        assert RotatingGenerationError.secret not in diagnostic
        assert diagnostic == "RotatingGenerationError: [REDACTED]"

    def test_backend_error_reuses_single_exception_snapshot(self):
        from src.market_analyzer import MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        error = RotatingGenerationError()
        overview = MarketOverview(date="2026-03-05")

        with patch.object(
            ma,
            "_get_analyzer_generation_backend_config_error",
            return_value=error,
        ), patch.object(
            ma.analyzer,
            "get_generation_log_redaction_values",
            side_effect=RuntimeError("redaction lookup unavailable"),
        ) as redaction_lookup, patch.object(
            ma.analyzer,
            "sanitize_generation_diagnostic",
            side_effect=lambda value, **_kwargs: str(value),
        ) as analyzer_sanitizer, patch(
            "src.market_analyzer.record_llm_run"
        ) as mock_record_llm_run:
            with pytest.raises(RotatingGenerationError):
                ma.generate_market_review(overview, [])

        assert error.render_count == 1
        redaction_lookup.assert_called_once()
        analyzer_sanitizer.assert_not_called()
        diagnostic = mock_record_llm_run.call_args.kwargs["error_message"]
        assert RotatingGenerationError.secret not in diagnostic
        assert diagnostic == "RotatingGenerationError: [REDACTED]"

    def test_backend_error_adds_snapshot_to_normal_redaction_lookup(self):
        from src.market_analyzer import MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        error = RotatingGenerationError()
        overview = MarketOverview(date="2026-03-05")

        with patch.object(
            ma,
            "_get_analyzer_generation_backend_config_error",
            return_value=error,
        ), patch.object(
            ma.analyzer,
            "get_generation_log_redaction_values",
            return_value=set(),
        ) as redaction_lookup, patch.object(
            ma.analyzer,
            "sanitize_generation_diagnostic",
            side_effect=lambda value, **_kwargs: str(value),
        ) as analyzer_sanitizer, patch(
            "src.market_analyzer.record_llm_run"
        ) as mock_record_llm_run:
            with pytest.raises(RotatingGenerationError):
                ma.generate_market_review(overview, [])

        assert error.render_count == 1
        redaction_lookup.assert_called_once()
        analyzer_sanitizer.assert_not_called()
        diagnostic = mock_record_llm_run.call_args.kwargs["error_message"]
        assert RotatingGenerationError.secret not in diagnostic
        assert diagnostic == "RotatingGenerationError: [REDACTED]"

    def test_generation_backend_config_error_without_analyzer_does_not_template_fallback(self):
        from src.llm.generation_backend import GenerationError
        from src.market_analyzer import MarketOverview, MarketIndex

        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="000001",
                    name="上证指数",
                    current=3300.0,
                    change=5.0,
                    change_pct=0.15,
                )
            ],
        )
        cases = [
            ("generation_backend", "GENERATION_BACKEND"),
            ("generation_fallback_backend", "GENERATION_FALLBACK_BACKEND"),
        ]

        for attr_name, expected_field in cases:
            ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
            ma.analyzer = None
            ma.config.generation_backend = "litellm"
            ma.config.generation_fallback_backend = "litellm"
            setattr(ma.config, attr_name, "codex")

            with patch.object(ma, "_generate_template_review", wraps=ma._generate_template_review) as template_review, \
                 patch("src.market_analyzer.record_llm_run") as mock_record_llm_run:
                with pytest.raises(GenerationError) as exc_info:
                    ma.generate_market_review(overview, [])

            assert exc_info.value.details["field"] == expected_field
            assert exc_info.value.details["requested_backend"] == "codex"
            template_review.assert_not_called()
            mock_record_llm_run.assert_called_once()

    def test_market_review_uses_8192_max_tokens(self):
        """generate_market_review() should request a larger output budget to avoid truncation."""
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="复盘结果")
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="000001",
                    name="上证指数",
                    current=3300.0,
                    change=5.0,
                    change_pct=0.15,
                )
            ],
        )

        result = ma.generate_market_review(overview, [])

        assert isinstance(result, str) and len(result) > 0
        ma.analyzer.generate_text.assert_called_once()
        _, kwargs = ma.analyzer.generate_text.call_args
        assert kwargs["max_tokens"] == 8192
        assert kwargs["temperature"] == 0.7

    def test_generate_template_review_uses_english_shell_for_cn_when_report_language_is_en(self):
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.config.report_language = "en"
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="000001",
                    name="上证指数",
                    current=3300.0,
                    change=12.0,
                    change_pct=0.36,
                )
            ],
            up_count=3200,
            down_count=1800,
            limit_up_count=88,
            limit_down_count=5,
            total_amount=14567.0,
            top_sectors=[{"name": "AI算力", "change_pct": 3.25}],
            bottom_sectors=[{"name": "煤炭", "change_pct": -1.12}],
        )

        result = ma.generate_market_review(overview, [])

        assert "A-share Market Recap" in result
        assert "### 1. Market Summary" in result
        assert "### 3. Breadth & Liquidity" in result
        assert "Turnover (CNY 100m)" in result
        assert "### 4. Sector / Theme Highlights" in result
        assert "### 6. Strategy Framework" in result
        assert "### 一、市场总结" not in result

    def test_generate_template_review_uses_jp_title_for_english_fallback(self):
        from src.core.market_profile import JP_PROFILE
        from src.core.market_strategy import get_market_strategy_blueprint
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.region = "jp"
        ma.profile = JP_PROFILE
        ma.strategy = get_market_strategy_blueprint("jp")
        ma.config.report_language = "en"
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="N225",
                    name="Nikkei 225",
                    current=39000.0,
                    change=120.0,
                    change_pct=0.31,
                )
            ],
        )

        result = ma.generate_market_review(overview, [])

        assert "Japan Market Recap" in result
        assert "Today's Japan market showed" in result
        assert "A-share Market Recap" not in result

    def test_generate_template_review_keeps_chinese_shell_for_us_when_report_language_is_default(self):
        from src.core.market_profile import US_PROFILE
        from src.core.market_strategy import get_market_strategy_blueprint
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.region = "us"
        ma.profile = US_PROFILE
        ma.strategy = get_market_strategy_blueprint("us")
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="SPX",
                    name="标普500",
                    current=5200.0,
                    change=-18.0,
                    change_pct=-0.35,
                )
            ],
        )

        result = ma.generate_market_review(overview, [])

        assert "## 2026-03-05 大盘复盘" in result
        assert "### 一、盘面总览" in result
        assert "今日美股市场整体呈现**小幅下跌**态势" in result
        assert "### 6. Strategy Framework" not in result
        assert "### 六、策略框架" in result
        assert "### 1. Market Summary" not in result
        assert "US Market Recap" not in result

    @pytest.mark.parametrize(
        ("region", "profile_name", "index_code", "index_name", "english_title", "zh_label"),
        [
            ("jp", "JP_PROFILE", "N225", "Nikkei 225", "Japan Market Recap", "今日日股市场整体呈现"),
            ("kr", "KR_PROFILE", "KS11", "KOSPI", "Korea Market Recap", "今日韩股市场整体呈现"),
        ],
    )
    def test_generate_template_review_uses_jp_kr_labels_for_no_llm_fallback(
        self, region, profile_name, index_code, index_name, english_title, zh_label
    ):
        import src.core.market_profile as market_profile
        from src.core.market_strategy import get_market_strategy_blueprint
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.region = region
        ma.profile = getattr(market_profile, profile_name)
        ma.strategy = get_market_strategy_blueprint(region)
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code=index_code,
                    name=index_name,
                    current=30000.0,
                    change=120.0,
                    change_pct=0.4,
                )
            ],
        )

        ma.config.report_language = "en"
        english_result = ma.generate_market_review(overview, [])
        assert f"## 2026-03-05 {english_title}" in english_result
        assert "A-share Market Recap" not in english_result

        ma.config.report_language = "zh"
        zh_result = ma.generate_market_review(overview, [])
        assert zh_label in zh_result
        assert "今日A股市场整体呈现" not in zh_result

    def test_inject_data_into_review_matches_english_headings(self):
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        ma.config.report_language = "en"
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="000001",
                    name="上证指数",
                    current=3300.0,
                    change=12.0,
                    change_pct=0.36,
                    amount=145000000000.0,
                )
            ],
            up_count=3200,
            down_count=1800,
            flat_count=100,
            limit_up_count=88,
            limit_down_count=5,
            total_amount=14567.0,
            top_sectors=[{"name": "AI算力", "change_pct": 3.25}],
            bottom_sectors=[{"name": "煤炭", "change_pct": -1.12}],
        )
        review = """## 2026-03-05 A-share Market Recap

### 1. Market Summary
Summary text.

### 2. Index Commentary
Index text.

### 4. Sector Highlights
Sector text.
"""

        result = ma._inject_data_into_review(review, overview)

        assert "- **Market Signal**: 66/100 (constructive, risk-on)" in result
        assert "- **Breadth**: Advancers 3200 / Decliners 1800 / Flat 100;" in result
        assert "Turnover 14567 (CNY 100m)" in result
        assert "| Index | Last | Change % | Open | High | Low | Amplitude | Turnover (CNY 100m) |" in result
        assert "#### Leading Industry Sectors" in result
        assert "| 1 | AI算力 | +3.25% |" in result
        assert "#### Lagging Industry Sectors" in result
        assert "| 1 | 煤炭 | -1.12% |" in result

    def test_inject_data_into_review_matches_reference_style_chinese_headings(self):
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="000001",
                    name="上证指数",
                    current=3300.0,
                    change=12.0,
                    change_pct=0.36,
                    open=3288.0,
                    high=3312.0,
                    low=3276.0,
                    amount=145000000000.0,
                    amplitude=1.1,
                )
            ],
            up_count=3200,
            down_count=1800,
            flat_count=100,
            limit_up_count=88,
            limit_down_count=5,
            total_amount=14567.0,
            top_sectors=[{"name": "AI算力", "change_pct": 3.25}],
            bottom_sectors=[{"name": "煤炭", "change_pct": -1.12}],
        )
        news = [{"title": "AI算力板块走强", "snippet": "算力产业链延续活跃，成交额放大"}]
        review = """## 2026-03-05 大盘复盘

### 一、盘面总览
总结。

### 二、指数结构
指数。

### 三、板块主线
板块。

### 五、消息催化
新闻。
"""

        result = ma._inject_data_into_review(review, overview, news)

        assert "盘面信号" in result
        assert "66/100（偏暖，可进攻）" in result
        assert "绿灯（可进攻）" not in result
        assert "大盘红绿灯" not in result
        assert "green（可进攻）" not in result
        assert "信号依据" in result
        signal_line = next(line for line in result.splitlines() if "**盘面信号**" in line)
        drivers_line = next(line for line in result.splitlines() if "**信号依据**" in line)
        assert signal_line.startswith("- ")
        assert "66/100" in signal_line
        assert "█" not in result
        assert "░" not in result
        assert "盘面温度" not in drivers_line
        assert "操作建议" in result
        assert "盘面温度" not in result
        assert "| 上涨/下跌/平盘 | 3200 / 1800 / 100 |" in result
        assert "| 指数 | 最新 | 涨跌幅 | 开盘 | 最高 | 最低 | 振幅 | 成交额(亿) |" in result
        assert "| 上证指数 | 3300.00 | 🟢 +0.36% | 3288.00 | 3312.00 | 3276.00 | 1.10% | 1450 |" in result
        assert "#### 行业板块领涨 Top 5" in result
        assert "| 1 | AI算力 | +3.25% |" in result
        assert "#### 近三日市场线索" not in result
        assert "AI算力板块走强" not in result
        assert "新闻。" in result
        assert "算力产业链延续活跃" not in result

    def test_inject_data_into_review_appends_sector_block_when_heading_drifts(self):
        from src.market_analyzer import MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        overview = MarketOverview(
            date="2026-03-05",
            top_sectors=[{"name": "AI算力", "change_pct": 3.25}],
            bottom_sectors=[{"name": "煤炭", "change_pct": -1.12}],
        )
        review = """## 2026-03-05 大盘复盘

### 今日主线观察
正文。
"""

        result = ma._inject_data_into_review(review, overview)

        assert "### 三、板块主线" in result
        assert "#### 行业板块领涨 Top 5" in result
        assert "| 1 | AI算力 | +3.25% |" in result
        assert "#### 行业板块领跌 Top 5" in result
        assert "| 1 | 煤炭 | -1.12% |" in result

    def test_market_review_payload_sections_skip_top_report_title(self):
        from src.market_analyzer import MarketAnalyzer

        ma = MarketAnalyzer.__new__(MarketAnalyzer)
        sections = ma._split_report_sections("""## 2026-06-03 大盘复盘

> 今日指数分化。

### 一、盘面总览
正文
""")

        assert sections[0]["key"] == "overview"
        assert "今日指数分化" in sections[0]["markdown"]
        assert all(section["title"] != "2026-06-03 大盘复盘" for section in sections)

    def test_news_block_renders_title_source_and_link_only(self):
        from src.market_analyzer import MarketAnalyzer

        ma = MarketAnalyzer.__new__(MarketAnalyzer)
        ma.config = SimpleNamespace(report_language="zh")
        ma.region = "cn"
        long_snippet = (
            "复盘必读 2026-05-06 复盘的意义在于更清晰地把握市场脉搏，"
            "综合描述 A 股三大指数今日集体反弹，成交额放大，科技成长方向领涨。"
        )

        result = ma._build_news_block([
            {
                "title": "A股收评：科创50指数放量反弹涨5.47% 两市成交额重回3万亿元",
                "snippet": long_snippet,
                "source": "东方财富",
                "published_date": "2026-05-06",
                "url": "https://example.com/news/1",
            }
        ])

        assert "#### 近三日市场线索" in result
        assert "| 序号 |" not in result
        assert "摘要/线索片段" not in result
        assert "关注点" not in result
        assert "成交额放大" not in result
        assert (
            "- 1. [A股收评：科创50指数放量反弹涨5.47% 两市成交额重回3万亿元]"
            "(https://example.com/news/1)（东方财富 / 2026-05-06）"
        ) in result

    def test_news_block_uses_dash_when_source_metadata_missing(self):
        from src.market_analyzer import MarketAnalyzer

        ma = MarketAnalyzer.__new__(MarketAnalyzer)
        ma.config = SimpleNamespace(report_language="zh")
        ma.region = "cn"

        result = ma._build_news_block([
            {
                "title": "政策利好带动板块活跃",
                "snippet": "相关主题成交放大",
            }
        ])

        assert "- 1. 政策利好带动板块活跃" in result
        assert "相关主题成交放大" not in result
        assert "| 1 | 政策利好带动板块活跃 |" not in result

    def test_news_block_uses_english_metadata_punctuation(self):
        from src.market_analyzer import MarketAnalyzer

        ma = MarketAnalyzer.__new__(MarketAnalyzer)
        ma.config = SimpleNamespace(report_language="en")
        ma.region = "us"

        result = ma._build_news_block([
            {
                "title": "Chip stocks rally as AI demand improves",
                "source": "Reuters",
                "published_date": "2026-05-06",
                "url": "https://example.com/news/2",
            }
        ])

        assert "#### News Catalysts" in result
        assert (
            "- 1. [Chip stocks rally as AI demand improves](https://example.com/news/2)"
            " (Reuters / 2026-05-06)"
        ) in result
        assert "（Reuters" not in result

    def test_review_prompt_caps_news_url_context(self):
        from src.market_analyzer import MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        long_url = "https://example.com/redirect?" + "utm_campaign=" + ("x" * 420)

        prompt = ma._build_review_prompt(
            MarketOverview(date="2026-05-06"),
            [
                {
                    "title": "A股收评：指数放量反弹",
                    "snippet": "科技成长方向领涨",
                    "source": "测试来源",
                    "published_date": "2026-05-06",
                    "url": long_url,
                }
            ],
        )

        assert long_url not in prompt
        assert "URL: https://example.com/redirect?" in prompt
        assert ("x" * 220) not in prompt

    def test_market_light_snapshot_marks_defensive_market_red(self):
        from src.market_analyzer import MarketIndex, MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        overview = MarketOverview(
            date="2026-03-06",
            indices=[
                MarketIndex(code="000001", name="上证指数", current=3200, change_pct=-1.8),
                MarketIndex(code="399001", name="深证成指", current=9800, change_pct=-2.4),
            ],
            up_count=900,
            down_count=4100,
            limit_up_count=10,
            limit_down_count=80,
            total_amount=9800.0,
        )

        snapshot = ma.build_market_light_snapshot(overview)

        assert snapshot["status"] == "red"
        assert snapshot["label"] == "偏防守"
        assert snapshot["score"] < 40
        assert snapshot["region"] == "cn"
        assert snapshot["trade_date"] == "2026-03-06"
        assert snapshot["data_quality"] == "ok"
        assert snapshot["dimensions"]["breadth"]["available"] is True
        assert snapshot["dimensions"]["index"]["available"] is True
        assert snapshot["dimensions"]["limit"]["available"] is True
        assert any("亏钱效应" in reason for reason in snapshot["reasons"])

    def test_market_light_snapshot_uses_english_labels_and_reasons(self):
        from src.market_analyzer import MarketIndex, MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        ma.config.report_language = "en"
        overview = MarketOverview(
            date="2026-03-06",
            indices=[
                MarketIndex(code="000001", name="SSE Composite", current=3200, change_pct=-1.8),
                MarketIndex(code="399001", name="SZSE Component", current=9800, change_pct=-2.4),
            ],
            up_count=900,
            down_count=4100,
            limit_up_count=10,
            limit_down_count=80,
            total_amount=9800.0,
        )

        snapshot = ma.build_market_light_snapshot(overview)

        assert snapshot["status"] == "red"
        assert snapshot["label"] == "risk-off"
        assert snapshot["guidance"] == (
            "Risk is elevated; prioritize drawdown control and avoid chasing weak rebounds."
        )
        assert not any(reason.startswith("market temperature ") for reason in snapshot["reasons"])
        assert any(
            reason.startswith("advancers ratio ") and "downside pressure dominates" in reason
            for reason in snapshot["reasons"]
        )

    def test_market_light_snapshot_marks_us_without_breadth_as_partial(self):
        from src.core.market_profile import US_PROFILE
        from src.market_analyzer import MarketIndex, MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        ma.region = "us"
        ma.profile = US_PROFILE
        ma.config.report_language = "en"
        overview = MarketOverview(
            date="2026-03-06",
            indices=[MarketIndex(code="SPX", name="S&P 500", current=5000, change_pct=0.5)],
        )

        snapshot = ma.build_market_light_snapshot(overview)

        assert snapshot["region"] == "us"
        assert snapshot["data_quality"] == "partial"
        assert snapshot["dimensions"]["breadth"] == {"score": 50, "available": False}
        assert snapshot["dimensions"]["index"]["available"] is True
        assert snapshot["dimensions"]["limit"] == {"score": 50, "available": False}

    @pytest.mark.parametrize(
        ("region", "profile_name", "index_code", "index_name"),
        [
            ("jp", "JP_PROFILE", "N225", "Nikkei 225"),
            ("kr", "KR_PROFILE", "KS11", "KOSPI"),
        ],
    )
    def test_market_light_snapshot_accepts_jp_kr_regions(
        self, region, profile_name, index_code, index_name
    ):
        import src.core.market_profile as market_profile
        from src.market_analyzer import MarketIndex, MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="review")
        ma.region = region
        ma.profile = getattr(market_profile, profile_name)
        overview = MarketOverview(
            date="2026-03-06",
            indices=[MarketIndex(code=index_code, name=index_name, current=30000, change_pct=0.5)],
        )

        snapshot = ma.build_market_light_snapshot(overview)

        assert snapshot["region"] == region
        assert snapshot["trade_date"] == "2026-03-06"
        assert snapshot["data_quality"] == "partial"
        assert snapshot["dimensions"]["breadth"] == {"score": 50, "available": False}
        assert snapshot["dimensions"]["index"]["available"] is True
        assert snapshot["dimensions"]["limit"] == {"score": 50, "available": False}

    def test_market_review_payload_omits_breadth_for_markets_without_stats(self):
        from src.core.market_profile import US_PROFILE
        from src.market_analyzer import MarketIndex, MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="复盘结果")
        ma.region = "us"
        ma.profile = US_PROFILE

        payload = ma.build_market_review_payload(
            MarketOverview(
                date="2026-03-18",
                indices=[
                    MarketIndex(code="SPX", name="S&P 500", current=5200.0, change_pct=0.6),
                ],
                up_count=1000,
                down_count=400,
                limit_up_count=10,
                limit_down_count=0,
                total_amount=9800.0,
            ),
            [],
            "美股复盘报告",
            market_light_snapshot={"dimensions": {"breadth": {"score": 60, "available": True}}},
        )

        assert "breadth" not in payload
        assert payload["indices"][0]["code"] == "SPX"

    def test_market_review_payload_omits_breadth_for_cn_market_without_available_stats(self):
        from src.market_analyzer import MarketIndex, MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="复盘结果")
        payload = ma.build_market_review_payload(
            MarketOverview(
                date="2026-03-18",
                indices=[
                    MarketIndex(code="000001", name="上证指数", current=3200.0, change_pct=0.6),
                ],
                up_count=0,
                down_count=0,
                flat_count=0,
                limit_up_count=0,
                limit_down_count=0,
                total_amount=0.0,
            ),
            [],
            "A股复盘报告",
            market_light_snapshot={"dimensions": {"breadth": {"score": 55, "available": False}}},
        )

        assert "breadth" not in payload
        assert payload["indices"][0]["name"] == "上证指数"

    def test_market_review_payload_includes_breadth_only_when_stats_available(self):
        from src.market_analyzer import MarketIndex, MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="复盘结果")
        payload = ma.build_market_review_payload(
            MarketOverview(
                date="2026-03-18",
                indices=[
                    MarketIndex(code="000001", name="上证指数", current=3200.0, change_pct=0.6),
                ],
                up_count=1200,
                down_count=900,
                flat_count=60,
                limit_up_count=12,
                limit_down_count=4,
                total_amount=12345.0,
            ),
            [],
            "A股复盘报告",
            market_light_snapshot={"dimensions": {"breadth": {"score": 62, "available": True}}},
        )

        assert payload["breadth"] is not None
        assert payload["breadth"]["up_count"] == 1200
        assert payload["breadth"]["down_count"] == 900
        assert payload["breadth"]["limit_up_count"] == 12
        assert payload["breadth"]["total_amount"] == 12345.0

    def test_market_review_includes_concept_rankings_in_prompt_payload_and_tables(self):
        from src.market_analyzer import MarketIndex, MarketOverview

        ma = self._make_market_analyzer_with_mock_generate_text(return_value="复盘结果")
        overview = MarketOverview(
            date="2026-03-18",
            indices=[
                MarketIndex(code="000001", name="上证指数", current=3200.0, change_pct=0.6),
            ],
            top_sectors=[{"name": "半导体", "change_pct": 2.35}],
            bottom_sectors=[{"name": "煤炭", "change_pct": -1.1}],
            top_concepts=[{"name": "机器人概念", "change_pct": 4.2}],
            bottom_concepts=[{"name": "转基因", "change_pct": -2.05}],
        )

        prompt = ma._build_review_prompt(overview, [])
        table_block = ma._build_sector_block(overview)
        payload = ma.build_market_review_payload(
            overview,
            [],
            "A股复盘报告",
            market_light_snapshot={"dimensions": {"breadth": {"score": 55, "available": False}}},
        )

        assert "行业领涨: 半导体(+2.35%)" in prompt
        assert "概念领涨: 机器人概念(+4.20%)" in prompt
        assert "#### 概念板块领涨 Top 5" in table_block
        assert "| 1 | 机器人概念 | +4.20% |" in table_block
        assert payload["sectors"]["top"][0]["name"] == "半导体"
        assert payload["concepts"]["top"][0]["name"] == "机器人概念"

    def test_us_english_indices_do_not_label_turnover_as_cny(self):
        from src.core.market_profile import US_PROFILE
        from src.core.market_strategy import get_market_strategy_blueprint
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.config.report_language = "en"
        ma.region = "us"
        ma.profile = US_PROFILE
        ma.strategy = get_market_strategy_blueprint("us")
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(
                    code="SPX",
                    name="S&P 500",
                    current=5200.0,
                    change=35.0,
                    change_pct=0.68,
                    amount=9876543210.0,
                )
            ],
        )

        result = ma._build_indices_block(overview)

        assert "CNY 100m" not in result
        assert "Turnover (USD bn)" in result
        assert "| S&P 500 | 5200.00 |" in result

    def test_indices_block_uses_configured_red_up_color_scheme(self):
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        ma.config.market_review_color_scheme = "red_up"
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(code="000001", name="上证指数", current=3200.0, change_pct=0.68),
                MarketIndex(code="399001", name="深证成指", current=9800.0, change_pct=-0.42),
                MarketIndex(code="399006", name="创业板指", current=2100.0, change_pct=0.0),
            ],
        )

        result = ma._build_indices_block(overview)

        assert "| 上证指数 | 3200.00 | 🔴 +0.68% |" in result
        assert "| 深证成指 | 9800.00 | 🟢 -0.42% |" in result
        assert "| 创业板指 | 2100.00 | ⚪ +0.00% |" in result

    def test_indices_block_keeps_green_up_default_color_scheme(self):
        from src.market_analyzer import MarketOverview, MarketIndex

        ma = self._make_market_analyzer_with_mock_generate_text(return_value=None)
        overview = MarketOverview(
            date="2026-03-05",
            indices=[
                MarketIndex(code="000001", name="上证指数", current=3200.0, change_pct=0.68),
                MarketIndex(code="399001", name="深证成指", current=9800.0, change_pct=-0.42),
            ],
        )

        result = ma._build_indices_block(overview)

        assert "| 上证指数 | 3200.00 | 🟢 +0.68% |" in result
        assert "| 深证成指 | 9800.00 | 🔴 -0.42% |" in result

    def test_no_private_attribute_access_in_market_analyzer_source(self):
        """Static guard: market_analyzer.py must not access private analyzer attrs."""
        import ast
        import pathlib

        src = pathlib.Path("src/market_analyzer.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = {
            "_model", "_router", "_use_openai", "_use_anthropic",  # historical
            "_call_litellm",      # use generate_text() instead
            "_litellm_available", # use is_available() instead
        }

        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in forbidden:
                    violations.append(node.attr)

        assert violations == [], (
            f"market_analyzer.py still accesses private Analyzer attributes: {violations}"
        )
