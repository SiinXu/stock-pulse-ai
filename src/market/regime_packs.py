# -*- coding: utf-8 -*-
"""Cross-market trading-regime packs (Issue #1141).

Versioned, data-defined per-market microstructure facts (sessions, halts /
price limits, short-selling norms) loaded from YAML files under
``src/market/regime_pack_data/``. The rendered prompt section is attached to
market guidelines on market detection so risk language matches each market's
rules instead of silently assuming another market's regime.

Contract:
- Packs are schema-validated on load; a malformed pack raises
  :class:`RegimePackError` naming the file and field. No silent fallback.
- A market without a pack renders an explicit "no pack" section that forbids
  assuming another market's rules; it never fails open to US or A-share
  semantics.
- Pack content is a versioned static reference and never claims live legal
  or regulatory authority; the rendered section says so.
- Authoritative session/holiday/timezone *computation* stays in
  ``src/core/trading_calendar.py`` (used by prediction ``resolve_after``).
  Packs only carry descriptive constraint language and reuse the same
  timezone identifiers so the two layers compose without drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional

__all__ = [
    "REGIME_PACK_SCHEMA_VERSION",
    "RegimePackError",
    "TradingRegimePack",
    "format_trading_regime_section",
    "get_trading_regime_pack",
    "get_trading_regime_pack_version",
    "list_trading_regime_pack_versions",
    "load_trading_regime_packs",
    "reset_trading_regime_pack_cache",
]

REGIME_PACK_SCHEMA_VERSION = 1

_PACK_DIR = Path(__file__).resolve().parent / "regime_pack_data"

_REQUIRED_LOCALIZED_FIELDS = ("halts", "shorting")
_OPTIONAL_LOCALIZED_FIELDS = ("settlement",)
_ALLOWED_TOP_LEVEL_KEYS = frozenset(
    ("schema_version", "market", "pack_version", "sessions")
    + _REQUIRED_LOCALIZED_FIELDS
    + _OPTIONAL_LOCALIZED_FIELDS
)
_LANG_KEYS = ("zh", "en")


class RegimePackError(ValueError):
    """Raised when a trading-regime pack file is missing or malformed."""


@dataclass(frozen=True)
class TradingRegimePack:
    """Validated per-market trading-regime facts."""

    market: str
    pack_version: str
    timezone: str
    sessions: Mapping[str, str]
    halts: Mapping[str, str]
    shorting: Mapping[str, str]
    settlement: Optional[Mapping[str, str]] = None


def _require_non_empty_str(value: object, *, file_name: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegimePackError(
            f"Trading-regime pack {file_name}: field '{field}' must be a "
            f"non-empty string, got {value!r}"
        )
    return value.strip()


def _parse_localized_block(
    value: object, *, file_name: str, field: str, extra_keys: tuple = ()
) -> Dict[str, str]:
    if not isinstance(value, Mapping):
        raise RegimePackError(
            f"Trading-regime pack {file_name}: field '{field}' must be a "
            f"mapping with '{_LANG_KEYS[0]}' and '{_LANG_KEYS[1]}' texts, "
            f"got {type(value).__name__}"
        )
    allowed = set(_LANG_KEYS) | set(extra_keys)
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise RegimePackError(
            f"Trading-regime pack {file_name}: field '{field}' has unknown "
            f"keys {unknown}; allowed keys are {sorted(allowed)}"
        )
    parsed: Dict[str, str] = {}
    for lang in _LANG_KEYS + tuple(extra_keys):
        parsed[lang] = _require_non_empty_str(
            value.get(lang), file_name=file_name, field=f"{field}.{lang}"
        )
    return parsed


def _load_pack_file(path: Path) -> TradingRegimePack:
    import yaml

    file_name = path.name
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise RegimePackError(
            f"Trading-regime pack {file_name}: invalid YAML: {exc}"
        ) from exc

    if not isinstance(data, Mapping):
        raise RegimePackError(
            f"Trading-regime pack {file_name}: top level must be a YAML "
            f"mapping, got {type(data).__name__}"
        )

    unknown = sorted(set(data) - _ALLOWED_TOP_LEVEL_KEYS)
    if unknown:
        raise RegimePackError(
            f"Trading-regime pack {file_name}: unknown top-level keys "
            f"{unknown}; allowed keys are {sorted(_ALLOWED_TOP_LEVEL_KEYS)}"
        )

    schema_version = data.get("schema_version")
    if schema_version != REGIME_PACK_SCHEMA_VERSION:
        raise RegimePackError(
            f"Trading-regime pack {file_name}: field 'schema_version' must "
            f"be {REGIME_PACK_SCHEMA_VERSION}, got {schema_version!r}"
        )

    market = _require_non_empty_str(
        data.get("market"), file_name=file_name, field="market"
    ).lower()
    if market != path.stem:
        raise RegimePackError(
            f"Trading-regime pack {file_name}: field 'market' is "
            f"'{market}' but must match the file stem '{path.stem}'"
        )

    pack_version = _require_non_empty_str(
        data.get("pack_version"), file_name=file_name, field="pack_version"
    )

    sessions = _parse_localized_block(
        data.get("sessions"),
        file_name=file_name,
        field="sessions",
        extra_keys=("timezone",),
    )
    timezone = sessions.pop("timezone")

    localized: Dict[str, Dict[str, str]] = {}
    for field in _REQUIRED_LOCALIZED_FIELDS:
        localized[field] = _parse_localized_block(
            data.get(field), file_name=file_name, field=field
        )
    for field in _OPTIONAL_LOCALIZED_FIELDS:
        if data.get(field) is not None:
            localized[field] = _parse_localized_block(
                data.get(field), file_name=file_name, field=field
            )

    return TradingRegimePack(
        market=market,
        pack_version=pack_version,
        timezone=timezone,
        sessions=sessions,
        halts=localized["halts"],
        shorting=localized["shorting"],
        settlement=localized.get("settlement"),
    )


_pack_cache: Optional[Dict[str, TradingRegimePack]] = None


def load_trading_regime_packs(
    directory: Optional[Path] = None,
) -> Dict[str, TradingRegimePack]:
    """Load and validate every ``*.yaml`` pack in *directory*.

    Raises :class:`RegimePackError` on the first malformed pack. When
    *directory* is omitted, results for the packaged directory are cached.
    """
    global _pack_cache
    if directory is None:
        if _pack_cache is not None:
            return _pack_cache
        directory = _PACK_DIR
        cache_result = True
    else:
        cache_result = False

    directory = Path(directory)
    if not directory.is_dir():
        raise RegimePackError(
            f"Trading-regime pack directory not found: {directory}"
        )

    packs: Dict[str, TradingRegimePack] = {}
    for path in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
        pack = _load_pack_file(path)
        if pack.market in packs:
            raise RegimePackError(
                f"Trading-regime pack {path.name}: duplicate pack for "
                f"market '{pack.market}'"
            )
        packs[pack.market] = pack

    if cache_result:
        _pack_cache = packs
    return packs


def reset_trading_regime_pack_cache() -> None:
    """Drop the cached packaged packs (test hook)."""
    global _pack_cache
    _pack_cache = None


def get_trading_regime_pack(market: str) -> Optional[TradingRegimePack]:
    """Return the validated pack for *market*, or ``None`` if none exists."""
    if not market:
        return None
    return load_trading_regime_packs().get(market.strip().lower())


def get_trading_regime_pack_version(market: str) -> Optional[str]:
    """Return the pack version id for *market*, or ``None`` without a pack."""
    pack = get_trading_regime_pack(market)
    return pack.pack_version if pack else None


def list_trading_regime_pack_versions() -> Dict[str, str]:
    """Return ``{market: pack_version}`` for every shipped pack."""
    return {
        market: pack.pack_version
        for market, pack in sorted(load_trading_regime_packs().items())
    }


_SECTION_LABELS = {
    "zh": {
        "header": "【交易制度参考 | 市场 {market} | 制度包版本 {version}】",
        "sessions": "- 交易时段（{timezone}）：{text}",
        "halts": "- 停牌与涨跌停：{text}",
        "shorting": "- 卖空与回转交易：{text}",
        "settlement": "- 结算：{text}",
        "disclaimer": (
            "- 说明：以上为版本化静态参考信息，不构成对现行法律法规或交易所"
            "规则的实时权威表述；具体以交易所现行规则为准。"
        ),
        "missing": (
            "【交易制度参考 | 市场 {market} | 无对应制度包】\n"
            "- 该市场暂无版本化交易制度包：请勿假设美股、A 股或其他市场的交易"
            "时段、停牌/涨跌停或卖空规则同样适用；如需给出交易制度约束，"
            "必须注明其未经核实。"
        ),
    },
    "en": {
        "header": "[Trading-regime reference | market: {market} | pack version: {version}]",
        "sessions": "- Sessions ({timezone}): {text}",
        "halts": "- Halts and price limits: {text}",
        "shorting": "- Short selling and same-day trading: {text}",
        "settlement": "- Settlement: {text}",
        "disclaimer": (
            "- Note: this is versioned static reference material, not a live "
            "authoritative statement of current laws, regulations, or "
            "exchange rules; defer to the exchange's current rules."
        ),
        "missing": (
            "[Trading-regime reference | market: {market} | no pack]\n"
            "- No versioned trading-regime pack exists for this market. Do "
            "not assume that US, China A-share, or any other market's "
            "session, halt/price-limit, or short-selling rules apply; flag "
            "any regime constraint you state as unverified."
        ),
    },
}


def format_trading_regime_section(market: str, lang: str = "zh") -> str:
    """Render the per-market trading-regime prompt section.

    Always returns non-empty text: either the versioned pack content or an
    explicit "no pack" section that forbids borrowing another market's rules.
    Raises :class:`RegimePackError` if the packaged pack data is malformed.
    """
    lang_key = "en" if lang in ("en", "ko") else "zh"
    labels = _SECTION_LABELS[lang_key]
    market_key = (market or "").strip().lower() or "unknown"
    pack = get_trading_regime_pack(market_key)
    if pack is None:
        return labels["missing"].format(market=market_key)

    lines = [
        labels["header"].format(market=pack.market, version=pack.pack_version),
        labels["sessions"].format(
            timezone=pack.timezone, text=pack.sessions[lang_key]
        ),
        labels["halts"].format(text=pack.halts[lang_key]),
        labels["shorting"].format(text=pack.shorting[lang_key]),
    ]
    if pack.settlement is not None:
        lines.append(labels["settlement"].format(text=pack.settlement[lang_key]))
    lines.append(labels["disclaimer"])
    return "\n".join(lines)
