# -*- coding: utf-8 -*-
"""Unit tests for report language helpers."""

import unittest

from src.report_language import (
    SUPPORTED_REPORT_LANGUAGES,
    format_strategy_skill_items,
    get_bias_status_emoji,
    get_localized_stock_name,
    get_report_labels,
    get_sentiment_label,
    get_signal_level,
    infer_decision_type_from_advice,
    is_supported_report_language_value,
    localize_conflict_severity,
    localize_consensus_level,
    localize_operation_advice,
    localize_strategy_conflict_description,
    localize_strategy_signal,
    localize_strategy_skill,
    localize_strategy_synthesis_summary,
    localize_trend_prediction,
    localize_bias_status,
    normalize_report_language,
    normalize_strategy_synthesis_payload,
    strategy_invalid_opinion_count,
)


class ReportLanguageTestCase(unittest.TestCase):
    def test_supported_language_predicate_rejects_integer(self) -> None:
        self.assertFalse(is_supported_report_language_value(123))

    def test_supported_language_predicate_rejects_list(self) -> None:
        self.assertFalse(is_supported_report_language_value(["en"]))

    def test_supported_language_predicate_rejects_object(self) -> None:
        self.assertFalse(is_supported_report_language_value({"language": "en"}))

    def test_get_signal_level_handles_compound_sell_advice(self) -> None:
        signal_text, emoji, signal_tag = get_signal_level("卖出/观望", 60, "zh")

        self.assertEqual(signal_text, "卖出")
        self.assertEqual(emoji, "🔴")
        self.assertEqual(signal_tag, "sell")

    def test_get_signal_level_handles_compound_buy_advice_in_english(self) -> None:
        signal_text, emoji, signal_tag = get_signal_level("Buy / Watch", 40, "en")

        self.assertEqual(signal_text, "Buy")
        self.assertEqual(emoji, "🟢")
        self.assertEqual(signal_tag, "buy")

    def test_get_signal_level_score_fallback_uses_canonical_scale(self) -> None:
        self.assertEqual(get_signal_level("", 28, "zh"), ("减仓", "🟠", "reduce"))
        self.assertEqual(get_signal_level("", 38, "zh"), ("减仓", "🟠", "reduce"))
        self.assertEqual(get_signal_level("", 42, "zh"), ("观望", "⚪", "watch"))
        self.assertEqual(get_signal_level("", 55, "zh"), ("观望", "⚪", "watch"))
        self.assertEqual(get_signal_level("", 60, "zh"), ("买入", "🟢", "buy"))
        self.assertEqual(get_signal_level("", 66, "zh"), ("买入", "🟢", "buy"))
        self.assertEqual(get_signal_level("", 72, "zh"), ("买入", "🟢", "buy"))

    def test_get_localized_stock_name_replaces_placeholder_for_english(self) -> None:
        self.assertEqual(
            get_localized_stock_name("股票AAPL", "AAPL", "en"),
            "Unnamed Stock",
        )

    def test_get_sentiment_label_preserves_higher_band_thresholds(self) -> None:
        self.assertEqual(get_sentiment_label(80, "en"), "Very Bullish")
        self.assertEqual(get_sentiment_label(60, "en"), "Bullish")
        self.assertEqual(get_sentiment_label(40, "zh"), "中性")
        self.assertEqual(get_sentiment_label(20, "zh"), "悲观")

    def test_localize_trend_prediction_preserves_fine_grain_zh_states(self) -> None:
        self.assertEqual(localize_trend_prediction("多头排列", "zh"), "多头排列")
        self.assertEqual(localize_trend_prediction("弱势空头", "zh"), "弱势空头")

    def test_localize_trend_prediction_still_translates_english_input_for_zh(self) -> None:
        self.assertEqual(localize_trend_prediction("bullish", "zh"), "看多")
        self.assertEqual(localize_trend_prediction("very bearish", "zh"), "强烈看空")

    def test_bias_status_helpers_support_english_values(self) -> None:
        self.assertEqual(localize_bias_status("Safe", "en"), "Safe")
        self.assertEqual(localize_bias_status("警戒", "en"), "Caution")
        self.assertEqual(get_bias_status_emoji("Safe"), "✅")
        self.assertEqual(get_bias_status_emoji("Caution"), "⚠️")

    def test_infer_decision_type_from_advice_matches_chinese_phrases(self) -> None:
        self.assertEqual(infer_decision_type_from_advice("建议买入"), "buy")
        self.assertEqual(infer_decision_type_from_advice("建议持有"), "hold")
        self.assertEqual(infer_decision_type_from_advice("建议减仓"), "sell")
        self.assertEqual(infer_decision_type_from_advice("继续持有"), "hold")
        self.assertEqual(infer_decision_type_from_advice("建议洗盘观察"), "hold")
        self.assertEqual(infer_decision_type_from_advice("洗盘观察", default=""), "hold")
        self.assertEqual(infer_decision_type_from_advice("观察", default=""), "hold")
        self.assertEqual(infer_decision_type_from_advice("不建议买入"), "hold")
        self.assertEqual(
            infer_decision_type_from_advice("当前不跌破支撑位继续持有"),
            "hold",
        )
        self.assertEqual(
            infer_decision_type_from_advice("不破支撑后仍可持有"),
            "hold",
        )


class KoreanReportLanguageTestCase(unittest.TestCase):
    def test_korean_is_supported(self) -> None:
        self.assertIn("ko", SUPPORTED_REPORT_LANGUAGES)

    def test_normalize_korean_aliases(self) -> None:
        self.assertEqual(normalize_report_language("ko"), "ko")
        self.assertEqual(normalize_report_language("korean"), "ko")
        self.assertEqual(normalize_report_language("ko-KR"), "ko")
        self.assertEqual(normalize_report_language("kr"), "ko")

    def test_unknown_language_falls_back_to_default(self) -> None:
        self.assertEqual(normalize_report_language("fr"), "zh")
        self.assertEqual(normalize_report_language(None), "zh")

    def test_korean_labels_cover_full_english_key_set(self) -> None:
        ko_labels = get_report_labels("ko")
        en_labels = get_report_labels("en")
        self.assertEqual(set(ko_labels.keys()), set(en_labels.keys()))
        self.assertEqual(ko_labels["dashboard_title"], "결정 대시보드")
        self.assertEqual(ko_labels["risk_alerts_label"], "리스크 경보")

    def test_korean_sentiment_label_bands(self) -> None:
        self.assertEqual(get_sentiment_label(80, "ko"), "매우 낙관")
        self.assertEqual(get_sentiment_label(40, "ko"), "중립")
        self.assertEqual(get_sentiment_label(0, "ko"), "매우 비관")

    def test_korean_operation_advice_and_trend(self) -> None:
        self.assertEqual(localize_operation_advice("买入", "ko"), "매수")
        self.assertEqual(localize_operation_advice("strong sell", "ko"), "적극 매도")
        self.assertEqual(localize_trend_prediction("bullish", "ko"), "상승")

    def test_korean_localized_stock_name_placeholder(self) -> None:
        self.assertEqual(
            get_localized_stock_name("股票AAPL", "AAPL", "ko"),
            "미확인 종목",
        )

    def test_existing_languages_unchanged(self) -> None:
        self.assertEqual(get_sentiment_label(80, "en"), "Very Bullish")
        self.assertEqual(get_sentiment_label(40, "zh"), "中性")

    def test_korean_advice_canonicalizes_to_decision_type(self) -> None:
        self.assertEqual(infer_decision_type_from_advice("매수"), "buy")
        self.assertEqual(infer_decision_type_from_advice("매도"), "sell")
        self.assertEqual(infer_decision_type_from_advice("보유"), "hold")
        self.assertEqual(infer_decision_type_from_advice("관망"), "hold")

    def test_korean_advice_resolves_signal_level(self) -> None:
        self.assertEqual(get_signal_level("매수", 72, "ko"), ("매수", "🟢", "buy"))
        self.assertEqual(get_signal_level("매도", 30, "ko"), ("매도", "🔴", "sell"))

    def test_korean_values_canonicalize_back_for_other_languages(self) -> None:
        self.assertEqual(localize_trend_prediction("상승", "en"), "Bullish")
        self.assertEqual(localize_operation_advice("적극 매도", "zh"), "强烈卖出")


class StrategyLocalizationTestCase(unittest.TestCase):
    def test_strategy_signal_translates_three_languages(self) -> None:
        self.assertEqual(localize_strategy_signal("buy", "zh"), "买入")
        self.assertEqual(localize_strategy_signal("buy", "en"), "Buy")
        self.assertEqual(localize_strategy_signal("buy", "ko"), "매수")
        # canonicalizes case/space aliases before translating
        self.assertEqual(localize_strategy_signal("STRONG BUY", "en"), "Strong Buy")
        self.assertEqual(localize_strategy_signal("强烈卖出", "en"), "Strong Sell")

    def test_strategy_signal_passes_through_unknown(self) -> None:
        self.assertEqual(localize_strategy_signal("moon", "en"), "moon")
        self.assertEqual(localize_strategy_signal("", "en"), "")
        self.assertEqual(localize_strategy_signal(None, "en"), "")

    def test_consensus_level_translates_three_languages(self) -> None:
        self.assertEqual(localize_consensus_level("insufficient", "zh"), "证据不足")
        self.assertEqual(localize_consensus_level("insufficient", "en"), "Insufficient")
        self.assertEqual(localize_consensus_level("insufficient", "ko"), "증거 부족")
        self.assertEqual(localize_consensus_level("high", "en"), "High")

    def test_consensus_level_passes_through_unknown(self) -> None:
        self.assertEqual(localize_consensus_level("weird", "en"), "weird")

    def test_conflict_severity_translates_three_languages(self) -> None:
        self.assertEqual(localize_conflict_severity("none", "zh"), "无")
        self.assertEqual(localize_conflict_severity("none", "en"), "None")
        self.assertEqual(localize_conflict_severity("none", "ko"), "없음")
        self.assertEqual(localize_conflict_severity("high", "en"), "High")

    def test_conflict_severity_passes_through_unknown(self) -> None:
        self.assertEqual(localize_conflict_severity("extreme", "en"), "extreme")

    def test_strategy_skill_translates_three_languages(self) -> None:
        self.assertEqual(localize_strategy_skill("bull_trend", "zh"), "默认多头趋势")
        self.assertEqual(localize_strategy_skill("bull_trend", "en"), "Bull Trend")
        self.assertEqual(localize_strategy_skill("bull_trend", "ko"), "기본 상승 추세")
        self.assertEqual(localize_strategy_skill("热点题材", "en"), "Hot Theme")

    def test_strategy_skill_passes_through_unknown(self) -> None:
        self.assertEqual(localize_strategy_skill("nonexistent_skill", "en"), "nonexistent_skill")

    def test_strategy_conflict_description_translates_three_languages(self) -> None:
        conflict_type = "directional_opposition"
        self.assertIn("策略方向出现对立", localize_strategy_conflict_description(conflict_type, "zh"))
        self.assertIn("Strategy directions diverge", localize_strategy_conflict_description(conflict_type, "en"))
        self.assertIn("전략 방향이 엇갈립니다", localize_strategy_conflict_description(conflict_type, "ko"))

    def test_strategy_conflict_description_passes_through_unknown(self) -> None:
        self.assertEqual(localize_strategy_conflict_description("new_conflict", "en"), "new_conflict")

    def test_strategy_empty_labels_translate_three_languages(self) -> None:
        self.assertEqual(get_report_labels("zh")["none_label"], "无")
        self.assertEqual(get_report_labels("en")["none_label"], "None")
        self.assertEqual(get_report_labels("ko")["none_label"], "없음")

    def test_strategy_skill_items_share_localized_formatting(self) -> None:
        items = [{"skill_id": "bull_trend", "signal": "buy", "confidence": 0.8}]

        self.assertEqual(format_strategy_skill_items(items, "en"), "Bull Trend/Buy/80%")
        self.assertEqual(
            format_strategy_skill_items(items, "en", include_details=False),
            "Bull Trend",
        )
        self.assertEqual(format_strategy_skill_items(["bad", {}], "ko"), "없음")

    def test_normalize_payload_returns_empty_for_non_dict(self) -> None:
        self.assertEqual(normalize_strategy_synthesis_payload("bad"), {})
        self.assertEqual(normalize_strategy_synthesis_payload(None), {})
        self.assertEqual(normalize_strategy_synthesis_payload([1, 2]), {})
        self.assertEqual(normalize_strategy_synthesis_payload(42), {})
        self.assertEqual(normalize_strategy_synthesis_payload({}), {})

    def test_normalize_payload_drops_malformed_list_items(self) -> None:
        payload = normalize_strategy_synthesis_payload(
            {
                "final_signal": "hold",
                "supporting_skills": [{"skill_id": "a"}, "bad", 3, None],
                "opposing_skills": "not-a-list",
                "conflicts": [
                    {
                        "conflict_type": "x",
                        "participants": [" bull_trend ", "", 7, None],
                    },
                    ["bad"],
                ],
            }
        )
        self.assertEqual(payload["supporting_skills"], [{"skill_id": "a"}])
        self.assertEqual(payload["opposing_skills"], [])
        self.assertEqual(
            payload["conflicts"],
            [{"conflict_type": "x", "participants": ["bull_trend"]}],
        )

    def test_normalize_payload_rejects_non_list_conflict_participants(self) -> None:
        payload = normalize_strategy_synthesis_payload(
            {"conflicts": [{"conflict_type": "x", "participants": 7}]}
        )

        self.assertEqual(payload["conflicts"][0]["participants"], [])

    def test_invalid_opinion_count_guards_bad_values(self) -> None:
        self.assertEqual(strategy_invalid_opinion_count({"summary_params": {"invalid_opinion_count": 2}}), 2)
        # summary_params missing or not a dict
        self.assertEqual(strategy_invalid_opinion_count({}), 0)
        self.assertEqual(strategy_invalid_opinion_count({"summary_params": "legacy"}), 0)
        self.assertEqual(strategy_invalid_opinion_count({"summary_params": ["x"]}), 0)
        # negative and zero collapse to 0
        self.assertEqual(strategy_invalid_opinion_count({"summary_params": {"invalid_opinion_count": -3}}), 0)
        self.assertEqual(strategy_invalid_opinion_count({"summary_params": {"invalid_opinion_count": 0}}), 0)
        # bool is not counted as int
        self.assertEqual(strategy_invalid_opinion_count({"summary_params": {"invalid_opinion_count": True}}), 0)
        # decimal string is narrowly parsed; other strings collapse to 0
        self.assertEqual(strategy_invalid_opinion_count({"summary_params": {"invalid_opinion_count": "5"}}), 5)
        self.assertEqual(strategy_invalid_opinion_count({"summary_params": {"invalid_opinion_count": "5abc"}}), 0)
        # non-dict top level
        self.assertEqual(strategy_invalid_opinion_count("bad"), 0)

    def test_synthesis_summary_no_conflict_three_languages(self) -> None:
        payload = {
            "final_signal": "buy",
            "consensus_level": "high",
            "conflict_severity": "none",
            "conflict_count": 0,
            "summary_params": {"opinion_count": 2},
        }
        self.assertIn("买入", localize_strategy_synthesis_summary(payload, "zh"))
        self.assertIn("未检测到策略冲突", localize_strategy_synthesis_summary(payload, "zh"))
        en = localize_strategy_synthesis_summary(payload, "en")
        self.assertIn("Buy", en)
        self.assertIn("no detected conflicts", en)
        ko = localize_strategy_synthesis_summary(payload, "ko")
        self.assertIn("매수", ko)
        self.assertIn("감지된 전략 충돌은 없습니다", ko)

    def test_synthesis_summary_with_conflict_three_languages(self) -> None:
        payload = {
            "final_signal": "sell",
            "consensus_level": "low",
            "conflict_severity": "high",
            "conflict_count": 2,
            "summary_params": {"opinion_count": 3},
        }
        zh = localize_strategy_synthesis_summary(payload, "zh")
        self.assertIn("冲突强度为高", zh)
        en = localize_strategy_synthesis_summary(payload, "en")
        self.assertIn("conflict severity is High", en)
        ko = localize_strategy_synthesis_summary(payload, "ko")
        self.assertIn("충돌 강도는 높음", ko)

    def test_synthesis_summary_empty_for_malformed(self) -> None:
        self.assertEqual(localize_strategy_synthesis_summary("bad", "en"), "")
        self.assertEqual(localize_strategy_synthesis_summary({}, "en"), "")

    def test_synthesis_summary_counts_skills_when_opinion_count_absent(self) -> None:
        payload = {
            "final_signal": "hold",
            "consensus_level": "medium",
            "conflict_severity": "none",
            "conflict_count": 0,
            "supporting_skills": [{"skill_id": "a"}, {"skill_id": "b"}],
            "opposing_skills": [{"skill_id": "c"}],
        }
        en = localize_strategy_synthesis_summary(payload, "en")
        self.assertIn("from 3 strategies", en)


if __name__ == "__main__":
    unittest.main()
