# -*- coding: utf-8 -*-
"""Cross-market trading-regime pack contract tests (Issue #1141)."""

from pathlib import Path

import pytest

from src.core.trading_calendar import MARKET_TIMEZONE
from src.market.context import get_market_guidelines
from src.market.regime_packs import (
    REGIME_PACK_SCHEMA_VERSION,
    RegimePackError,
    format_trading_regime_section,
    get_trading_regime_pack,
    get_trading_regime_pack_version,
    list_trading_regime_pack_versions,
    load_trading_regime_packs,
    reset_trading_regime_pack_cache,
)


@pytest.fixture(autouse=True)
def _fresh_pack_cache():
    reset_trading_regime_pack_cache()
    yield
    reset_trading_regime_pack_cache()


VALID_PACK_YAML = """\
schema_version: 1
market: zz
pack_version: v9
sessions:
  timezone: UTC
  zh: 时段说明
  en: session text
halts:
  zh: 停牌说明
  en: halt text
shorting:
  zh: 卖空说明
  en: shorting text
"""


def _write_pack(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


# -- Shipped pack loading and version query --


def test_shipped_packs_load_and_cover_issue_markets() -> None:
    packs = load_trading_regime_packs()
    assert {"cn", "hk", "us", "crypto"} <= set(packs)
    for market, pack in packs.items():
        assert pack.market == market
        assert pack.pack_version


def test_pack_version_is_queryable_per_market() -> None:
    versions = list_trading_regime_pack_versions()
    assert versions
    for market, version in versions.items():
        assert get_trading_regime_pack_version(market) == version
    assert get_trading_regime_pack_version("jp") is None
    assert get_trading_regime_pack_version("") is None
    assert get_trading_regime_pack("no-such-market") is None


def test_pack_timezones_compose_with_trading_calendar() -> None:
    packs = load_trading_regime_packs()
    for market in ("cn", "hk", "us"):
        assert packs[market].timezone == MARKET_TIMEZONE[market]
    # trading_calendar treats crypto as UTC (24x7); packs must agree.
    assert packs["crypto"].timezone == "UTC"


# -- Distinct constraint language per market --


def test_distinct_markets_produce_distinct_constraint_language() -> None:
    for lang in ("zh", "en"):
        sections = {
            market: format_trading_regime_section(market, lang)
            for market in ("cn", "hk", "us", "crypto")
        }
        assert len(set(sections.values())) == 4

    cn_zh = format_trading_regime_section("cn", "zh")
    assert "±10%" in cn_zh
    assert "T+1" in cn_zh
    assert "融资融券" in cn_zh

    hk_zh = format_trading_regime_section("hk", "zh")
    assert "无每日涨跌停" in hk_zh
    assert "可卖空证券名单" in hk_zh

    us_en = format_trading_regime_section("us", "en")
    assert "circuit breakers" in us_en
    assert "Limit Up-Limit Down" in us_en
    assert "Short Sale Restriction" in us_en

    crypto_en = format_trading_regime_section("crypto", "en")
    assert "24x7" in crypto_en
    assert "No market-wide price limits" in crypto_en


def test_sections_carry_version_id_and_disclaimer() -> None:
    zh = format_trading_regime_section("cn", "zh")
    assert "制度包版本 v1" in zh
    assert "不构成对现行法律法规或交易所规则的实时权威表述" in zh

    en = format_trading_regime_section("us", "en")
    assert "pack version: v1" in en
    assert "not a live authoritative statement" in en


# -- Explicit default for markets without a pack --


def test_market_without_pack_gets_explicit_default_not_us_rules() -> None:
    for market in ("jp", "kr", "tw", "xx"):
        zh = format_trading_regime_section(market, "zh")
        en = format_trading_regime_section(market, "en")
        assert f"市场 {market}" in zh
        assert "无对应制度包" in zh
        assert "请勿假设" in zh
        assert f"market: {market}" in en
        assert "no pack" in en
        assert "Do not assume" in en
        # Never silently borrows another market's constraint content.
        for text in (zh, en):
            assert "circuit breakers" not in text
            assert "±10%" not in text


def test_empty_market_renders_unknown_default() -> None:
    section = format_trading_regime_section("", "en")
    assert "market: unknown" in section
    assert "no pack" in section


# -- Auto-attach on market detection --


def test_market_guidelines_attach_regime_pack_on_market_detect() -> None:
    cn = get_market_guidelines("600519", "zh")
    hk = get_market_guidelines("HK00700", "zh")
    us = get_market_guidelines("AAPL", "en")
    crypto = get_market_guidelines("crypto:BTC", "en")

    assert "【交易制度参考 | 市场 cn | 制度包版本 v1】" in cn
    assert "【交易制度参考 | 市场 hk | 制度包版本 v1】" in hk
    assert "[Trading-regime reference | market: us | pack version: v1]" in us
    assert "[Trading-regime reference | market: crypto | pack version: v1]" in crypto
    assert len({cn, hk, us, crypto}) == 4

    # Existing hand-written guidance stays in place (append-only attach).
    assert "T+1" in cn
    assert "港股无涨跌停限制" in hk


def test_market_guidelines_for_packless_market_flag_missing_pack() -> None:
    jp = get_market_guidelines("7203.T", "zh")
    assert "市场 jp" in jp
    assert "无对应制度包" in jp
    # The pre-existing JP guidance still leads the section.
    assert "日股" in jp


# -- Schema validation: malformed packs fail loudly, naming file and field --


def test_valid_custom_pack_loads_from_directory(tmp_path: Path) -> None:
    _write_pack(tmp_path, "zz.yaml", VALID_PACK_YAML)
    packs = load_trading_regime_packs(tmp_path)
    assert packs["zz"].pack_version == "v9"
    assert packs["zz"].settlement is None


def test_missing_required_field_names_file_and_field(tmp_path: Path) -> None:
    content = VALID_PACK_YAML.replace("shorting:\n  zh: 卖空说明\n  en: shorting text\n", "")
    _write_pack(tmp_path, "zz.yaml", content)
    with pytest.raises(RegimePackError, match=r"zz\.yaml.*'shorting'"):
        load_trading_regime_packs(tmp_path)


def test_missing_language_variant_names_file_and_field(tmp_path: Path) -> None:
    content = VALID_PACK_YAML.replace("  en: halt text\n", "")
    _write_pack(tmp_path, "zz.yaml", content)
    with pytest.raises(RegimePackError, match=r"zz\.yaml.*'halts\.en'"):
        load_trading_regime_packs(tmp_path)


def test_missing_session_timezone_names_file_and_field(tmp_path: Path) -> None:
    content = VALID_PACK_YAML.replace("  timezone: UTC\n", "")
    _write_pack(tmp_path, "zz.yaml", content)
    with pytest.raises(RegimePackError, match=r"zz\.yaml.*'sessions\.timezone'"):
        load_trading_regime_packs(tmp_path)


def test_unknown_top_level_key_fails_loudly(tmp_path: Path) -> None:
    _write_pack(tmp_path, "zz.yaml", VALID_PACK_YAML + "surprise: true\n")
    with pytest.raises(RegimePackError, match=r"zz\.yaml.*surprise"):
        load_trading_regime_packs(tmp_path)


def test_wrong_schema_version_fails_loudly(tmp_path: Path) -> None:
    content = VALID_PACK_YAML.replace("schema_version: 1", "schema_version: 2")
    _write_pack(tmp_path, "zz.yaml", content)
    with pytest.raises(RegimePackError, match=r"zz\.yaml.*'schema_version'"):
        load_trading_regime_packs(tmp_path)
    assert REGIME_PACK_SCHEMA_VERSION == 1


def test_market_must_match_file_stem(tmp_path: Path) -> None:
    _write_pack(tmp_path, "aa.yaml", VALID_PACK_YAML)
    with pytest.raises(RegimePackError, match=r"aa\.yaml.*'market'"):
        load_trading_regime_packs(tmp_path)


def test_non_mapping_pack_fails_loudly(tmp_path: Path) -> None:
    _write_pack(tmp_path, "zz.yaml", "- just\n- a list\n")
    with pytest.raises(RegimePackError, match=r"zz\.yaml.*mapping"):
        load_trading_regime_packs(tmp_path)


def test_invalid_yaml_fails_loudly(tmp_path: Path) -> None:
    _write_pack(tmp_path, "zz.yaml", "market: [unclosed\n")
    with pytest.raises(RegimePackError, match=r"zz\.yaml.*invalid YAML"):
        load_trading_regime_packs(tmp_path)


def test_missing_directory_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(RegimePackError, match="directory not found"):
        load_trading_regime_packs(tmp_path / "nope")
