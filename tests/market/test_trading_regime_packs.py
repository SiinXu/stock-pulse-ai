# -*- coding: utf-8 -*-
"""Cross-market trading-regime pack contract tests (Issue #1141)."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.core.trading_calendar import MARKET_TIMEZONE
from src.market.context import (
    get_market_guidelines,
    get_trading_regime_context_metadata,
)
from src.market.regime_packs import (
    LEGAL_AUTHORITY,
    REGIME_PACK_SCHEMA_VERSION,
    REQUIRED_SHIPPED_MARKETS,
    RegimePackError,
    build_trading_regime_context_metadata,
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
    assert REQUIRED_SHIPPED_MARKETS <= set(packs)
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
    assert packs["crypto"].timezone == "UTC"


def test_loaded_packs_are_immutable() -> None:
    pack = get_trading_regime_pack("cn")
    assert pack is not None
    with pytest.raises(FrozenInstanceError):
        pack.pack_version = "hacked"  # type: ignore[misc]
    with pytest.raises(TypeError):
        pack.halts["zh"] = "mutated"  # type: ignore[index]
    with pytest.raises(TypeError):
        pack.sessions["en"] = "mutated"  # type: ignore[index]


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
    assert "±10%" not in hk_zh

    us_en = format_trading_regime_section("us", "en")
    assert "circuit breakers" in us_en
    assert "Limit Up-Limit Down" in us_en
    assert "Short Sale Restriction" in us_en
    assert "T+1 settlement" in us_en.lower() or "Stock settlement is T+1" in us_en

    crypto_en = format_trading_regime_section("crypto", "en")
    assert "24x7" in crypto_en
    assert "No market-wide price limits" in crypto_en
    assert "circuit breakers" in crypto_en
    assert "Limit Up-Limit Down" not in crypto_en


def test_sections_carry_version_id_and_disclaimer() -> None:
    zh = format_trading_regime_section("cn", "zh")
    cn_version = get_trading_regime_pack_version("cn")
    assert cn_version
    assert f"制度包版本 {cn_version}" in zh
    assert "不构成对现行法律法规或交易所规则的实时权威表述" in zh
    assert "不是实时法律意见" in zh

    en = format_trading_regime_section("us", "en")
    us_version = get_trading_regime_pack_version("us")
    assert us_version
    assert f"pack version: {us_version}" in en
    assert "not a live authoritative statement" in en
    assert "not live legal advice" in en


# -- Version metadata for run/context consumers --


def test_context_metadata_exposes_queryable_pack_version() -> None:
    cn = get_trading_regime_context_metadata("600519")
    hk = get_trading_regime_context_metadata("HK00700")
    us = get_trading_regime_context_metadata("AAPL")
    crypto = get_trading_regime_context_metadata("crypto:BTC")
    jp = get_trading_regime_context_metadata("7203.T")

    assert cn["market"] == "cn"
    assert hk["market"] == "hk"
    assert us["market"] == "us"
    assert crypto["market"] == "crypto"
    assert {cn["pack_version"], hk["pack_version"], us["pack_version"], crypto["pack_version"]}
    assert cn["has_pack"] is True
    assert cn["schema_version"] == REGIME_PACK_SCHEMA_VERSION
    assert cn["legal_authority"] == LEGAL_AUTHORITY
    assert cn["legal_authority"] == "static_reference_not_live_legal_advice"
    assert jp["has_pack"] is False
    assert jp["pack_version"] is None
    assert jp["market"] == "jp"
    assert build_trading_regime_context_metadata("cn")["pack_version"] == cn["pack_version"]


# -- Explicit default for markets without a pack --


def test_market_without_pack_gets_explicit_default_not_us_rules() -> None:
    for market in ("jp", "kr", "tw", "xx"):
        zh = format_trading_regime_section(market, "zh")
        en = format_trading_regime_section(market, "en")
        assert f"市场 {market}" in zh
        assert "无对应制度包" in zh
        assert "请勿假设" in zh
        assert "不是实时法律意见" in zh
        assert f"market: {market}" in en
        assert "no pack" in en
        assert "Do not assume" in en
        assert "not live legal advice" in en
        for text in (zh, en):
            assert "Limit Up-Limit Down" not in text
            assert "±10%" not in text
            assert "融资融券" not in text


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

    cn_version = get_trading_regime_pack_version("cn")
    hk_version = get_trading_regime_pack_version("hk")
    us_version = get_trading_regime_pack_version("us")
    crypto_version = get_trading_regime_pack_version("crypto")
    assert f"【交易制度参考 | 市场 cn | 制度包版本 {cn_version}】" in cn
    assert f"【交易制度参考 | 市场 hk | 制度包版本 {hk_version}】" in hk
    assert f"[Trading-regime reference | market: us | pack version: {us_version}]" in us
    assert (
        f"[Trading-regime reference | market: crypto | pack version: {crypto_version}]"
        in crypto
    )
    assert len({cn, hk, us, crypto}) == 4
    assert "T+1" in cn
    assert "港股无涨跌停限制" in hk
    assert "not live legal advice" in us


def test_market_guidelines_for_packless_market_flag_missing_pack() -> None:
    jp = get_market_guidelines("7203.T", "zh")
    assert "市场 jp" in jp
    assert "无对应制度包" in jp
    assert "日股" in jp
    assert "不是实时法律意见" in jp


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


def test_unreadable_pack_file_is_regime_pack_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_pack(tmp_path, "zz.yaml", VALID_PACK_YAML)
    real_open = open

    def fake_open(file, *args, **kwargs):
        if Path(file).name == "zz.yaml":
            raise PermissionError("denied")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    with pytest.raises(RegimePackError, match=r"zz\.yaml.*cannot read file"):
        load_trading_regime_packs(tmp_path)


def test_undecodable_pack_file_is_regime_pack_error(tmp_path: Path) -> None:
    (tmp_path / "zz.yaml").write_bytes(b"\xff\xfe not utf-8")
    with pytest.raises(RegimePackError, match=r"zz\.yaml.*cannot read file"):
        load_trading_regime_packs(tmp_path)


def test_missing_directory_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(RegimePackError, match="directory not found"):
        load_trading_regime_packs(tmp_path / "nope")


def test_packaged_directory_requires_shipped_markets(tmp_path: Path, monkeypatch) -> None:
    _write_pack(tmp_path, "cn.yaml", VALID_PACK_YAML.replace("market: zz", "market: cn"))
    monkeypatch.setattr("src.market.regime_packs._PACK_DIR", tmp_path)
    reset_trading_regime_pack_cache()
    with pytest.raises(RegimePackError, match="missing required packs"):
        load_trading_regime_packs()


def test_duplicate_market_files_fail_loudly(tmp_path: Path) -> None:
    _write_pack(tmp_path, "zz.yaml", VALID_PACK_YAML)
    _write_pack(tmp_path, "zz.yml", VALID_PACK_YAML)
    with pytest.raises(RegimePackError, match=r"duplicate pack"):
        load_trading_regime_packs(tmp_path)


def test_empty_localized_field_fails_loudly(tmp_path: Path) -> None:
    content = VALID_PACK_YAML.replace("  en: halt text\n", "  en: '   '\n")
    _write_pack(tmp_path, "zz.yaml", content)
    with pytest.raises(RegimePackError, match=r"zz\.yaml.*'halts\.en'"):
        load_trading_regime_packs(tmp_path)
