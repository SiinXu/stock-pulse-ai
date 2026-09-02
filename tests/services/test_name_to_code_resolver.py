# -*- coding: utf-8 -*-
"""Tests for name_to_code_resolver.

Covers:
- Local mapping (STOCK_NAME_MAP reverse)
- Code format boundary (_is_code_like, _normalize_code)
- Pinyin match (when pypinyin available)
- AkShare fallback (mocked)
- Fuzzy match (difflib)
- Ambiguous names return None
"""

from unittest.mock import patch

from src.services.name_to_code_resolver import (
    resolve_name_to_code,
    _is_code_like,
    _normalize_code,
    _normalize_stock_name,
    _normalize_name_to_code_map,
    _build_reverse_map_no_duplicates,
)


# ---------------------------------------------------------------------------
# _is_code_like
# ---------------------------------------------------------------------------

class TestIsCodeLike:
    def test_a_share_5_digits(self):
        assert _is_code_like("60051") is True
        assert _is_code_like("600519") is True

    def test_a_share_6_digits(self):
        assert _is_code_like("300750") is True

    def test_bse_with_exchange_hint(self):
        assert _is_code_like("920493.BJ") is True
        assert _is_code_like("BJ920493") is True

    def test_bj_exchange_hint_rejects_non_bse_code(self):
        assert _is_code_like("600519.BJ") is False
        assert _is_code_like("BJ600519") is False

    def test_hk_5_digits(self):
        assert _is_code_like("00700") is True

    def test_us_stock_letters(self):
        assert _is_code_like("AAPL") is True
        assert _is_code_like("TSLA") is True
        assert _is_code_like("BRK.B") is True

    def test_rejects_non_code(self):
        assert _is_code_like("贵州茅台") is False
        assert _is_code_like("1234567") is False  # too long
        assert _is_code_like("") is False
        assert _is_code_like("   ") is False

    def test_accepts_bare_four_digit_hong_kong_code(self):
        assert _is_code_like("1234") is True


# ---------------------------------------------------------------------------
# _normalize_code
# ---------------------------------------------------------------------------

class TestNormalizeCode:
    def test_preserves_valid_a_share(self):
        assert _normalize_code("600519") == "600519"
        assert _normalize_code("  600519  ") == "600519"

    def test_strips_suffix(self):
        assert _normalize_code("600519.SH") == "600519"
        assert _normalize_code("000001.SZ") == "000001"
        assert _normalize_code("920493.BJ") == "920493"

    def test_strips_bse_prefix(self):
        assert _normalize_code("BJ920493") == "920493"

    def test_bj_exchange_hint_rejects_non_bse_code(self):
        assert _normalize_code("600519.BJ") is None
        assert _normalize_code("BJ600519") is None

    def test_preserves_us_stock(self):
        assert _normalize_code("AAPL") == "AAPL"
        assert _normalize_code("brk.b") == "BRK.B"

    def test_returns_none_for_invalid(self):
        assert _normalize_code("") is None
        assert _normalize_code("贵州茅台") is None

    def test_normalizes_bare_four_digit_hong_kong_code(self):
        assert _normalize_code("1234") == "01234"


# ---------------------------------------------------------------------------
# _build_reverse_map_no_duplicates
# ---------------------------------------------------------------------------

class TestBuildReverseMapNoDuplicates:
    def test_excludes_ambiguous_names(self):
        # "阿里巴巴" maps to both BABA and 09988
        code_to_name = {"BABA": "阿里巴巴", "09988": "阿里巴巴", "600519": "贵州茅台"}
        result = _build_reverse_map_no_duplicates(code_to_name)
        assert "阿里巴巴" not in result
        assert result.get("贵州茅台") == "600519"

    def test_includes_unique_names(self):
        code_to_name = {"600519": "贵州茅台", "00700": "腾讯控股"}
        result = _build_reverse_map_no_duplicates(code_to_name)
        assert result["贵州茅台"] == "600519"
        assert result["腾讯控股"] == "00700"

    def test_normalizes_width_and_embedded_whitespace(self):
        result = _build_reverse_map_no_duplicates(
            {"000001": " 浦 发 银 行 ", "000002": "京东方Ａ"}
        )
        assert result == {"浦发银行": "000001", "京东方A": "000002"}

    def test_normalized_alias_collision_remains_ambiguous(self):
        result = _build_reverse_map_no_duplicates(
            {"000001": "京东方Ａ", "000002": "京东方 A"}
        )
        assert "京东方A" not in result

    def test_normalized_cache_aliases_preserve_unique_code(self):
        result = _normalize_name_to_code_map(
            {"京东方Ａ": "000725", "京东方 A": "000725"}
        )
        assert result == {"京东方A": "000725"}

    def test_normalized_cache_alias_conflict_is_excluded(self):
        result = _normalize_name_to_code_map(
            {"京东方Ａ": "000725", "京东方 A": "000001"}
        )
        assert "京东方A" not in result


# ---------------------------------------------------------------------------
# resolve_name_to_code
# ---------------------------------------------------------------------------

class TestResolveNameToCode:
    def test_code_like_input_returned_normalized(self):
        assert resolve_name_to_code("600519") == "600519"
        assert resolve_name_to_code("600519.SH") == "600519"
        assert resolve_name_to_code("920493.BJ") == "920493"
        assert resolve_name_to_code("  AAPL  ") == "AAPL"

    def test_local_map_exact_match(self):
        assert resolve_name_to_code("贵州茅台") == "600519"
        assert resolve_name_to_code("腾讯控股") == "00700"

    def test_query_normalizes_full_width_latin_and_embedded_whitespace(self):
        assert resolve_name_to_code("腾 讯 控 股") == "00700"
        assert resolve_name_to_code("ＡＡＰＬ") == "AAPL"

    def test_normalization_removes_unicode_whitespace(self):
        assert _normalize_stock_name("京\u3000东 方Ａ") == "京东方A"

    def test_returns_none_for_empty_or_invalid_input(self):
        assert resolve_name_to_code("") is None
        assert resolve_name_to_code("   ") is None
        assert resolve_name_to_code(None) is None  # type: ignore

    def test_ambiguous_name_returns_none(self):
        # "阿里巴巴" maps to both BABA and 09988 in STOCK_NAME_MAP
        assert resolve_name_to_code("阿里巴巴") is None

    @patch("src.services.name_to_code_resolver._get_akshare_name_to_code")
    def test_akshare_fallback_when_not_in_local(self, mock_akshare):
        mock_akshare.return_value = {"平安银行": "000001"}
        # `000001` is locally mapped to `平安银行`, so use the AkShare-only `浦发银行` fixture below.
        # Use a name not in STOCK_NAME_MAP - e.g. some A-share only in AkShare
        mock_akshare.return_value = {"浦发银行": "600000"}
        result = resolve_name_to_code("浦发银行")
        assert result == "600000"
        mock_akshare.assert_called()

    @patch("src.services.name_to_code_resolver._get_akshare_name_to_code")
    def test_akshare_map_is_normalized_at_merge_boundary(self, mock_akshare):
        mock_akshare.return_value = {"浦 发 银 行Ａ": "600000"}
        assert resolve_name_to_code("浦发银行Ａ") == "600000"

    @patch("src.services.name_to_code_resolver.time.time", return_value=101.0)
    def test_cached_akshare_names_are_normalized(self, _mock_time):
        from src.services import name_to_code_resolver as resolver

        with patch.object(
            resolver,
            "_akshare_cache",
            (100.0, {"浦 发 银 行Ａ": "600000"}),
        ):
            assert resolve_name_to_code("浦发银行A") == "600000"

    @patch("src.services.name_to_code_resolver._get_akshare_name_to_code")
    def test_fuzzy_match_fallback(self, mock_akshare):
        mock_akshare.return_value = {"贵州茅台": "600519"}
        # The typo `贵州茅苔` should fuzzy-match `贵州茅台`.
        result = resolve_name_to_code("贵州茅苔")
        assert result == "600519"

    @patch("src.services.name_to_code_resolver._get_akshare_name_to_code")
    def test_returns_none_when_no_match(self, mock_akshare):
        mock_akshare.return_value = {}
        result = resolve_name_to_code("不存在的股票名称xyz")
        assert result is None

    @patch("src.services.name_to_code_resolver._get_akshare_name_to_code")
    def test_skips_akshare_for_non_cjk_garbage_input(self, mock_akshare):
        result = resolve_name_to_code("aaaaaaa")
        assert result is None
        mock_akshare.assert_not_called()
