"""Technical indicator period configuration field definitions (Issue #172)."""

from typing import Any, Dict

from src.utils.indicator_periods import (
    DEFAULT_MACD_FAST,
    DEFAULT_MACD_SIGNAL,
    DEFAULT_MACD_SLOW,
    DEFAULT_MA_PERIODS,
    DEFAULT_RSI_PERIODS,
    MAX_MACD_PERIOD,
    MAX_MA_PERIOD,
    MAX_RSI_PERIOD,
    MIN_PERIOD,
)

_DOC_INDICATOR_PERIODS = [
    {
        "label": "Indicator periods guide (EN)",
        "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/indicator-periods_EN.md",
    },
    {
        "label": "技术指标周期配置",
        "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/indicator-periods.md",
    },
]

_DEFAULT_MA = ",".join(str(p) for p in DEFAULT_MA_PERIODS)
_DEFAULT_RSI = ",".join(str(p) for p in DEFAULT_RSI_PERIODS)

INDICATOR_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "INDICATOR_MA_PERIODS": {
        "title": "Moving Average Periods",
        "description": (
            "Comma-separated moving-average periods in trading days "
            f"(default {_DEFAULT_MA}). Supports longer horizons such as 120/250. "
            "The first four values map to the legacy ma5/ma10/ma20/ma60 slots; "
            "additional periods appear in ma_by_period. When a period exceeds "
            "available bars the value is omitted and annotated as insufficient data "
            "(no silent shorter-period substitution)."
        ),
        "category": "indicators",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": _DEFAULT_MA,
        "options": [],
        "validation": {},
        "display_order": 10,
        "help_key": "settings.indicators.INDICATOR_MA_PERIODS",
        "examples": [
            f"INDICATOR_MA_PERIODS={_DEFAULT_MA}",
            "INDICATOR_MA_PERIODS=5,10,20,60,120,250",
            "INDICATOR_MA_PERIODS=30,60,120",
        ],
        "docs": _DOC_INDICATOR_PERIODS,
        "warning_codes": [],
    },
    "INDICATOR_MACD_FAST": {
        "title": "MACD Fast Period",
        "description": (
            f"MACD fast EMA period (default {DEFAULT_MACD_FAST}). "
            "Must be less than INDICATOR_MACD_SLOW."
        ),
        "category": "indicators",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": str(DEFAULT_MACD_FAST),
        "options": [],
        "validation": {"min": MIN_PERIOD, "max": MAX_MACD_PERIOD},
        "display_order": 20,
        "help_key": "settings.indicators.macd_params",
        "examples": [
            f"INDICATOR_MACD_FAST={DEFAULT_MACD_FAST}",
            f"INDICATOR_MACD_SLOW={DEFAULT_MACD_SLOW}",
            f"INDICATOR_MACD_SIGNAL={DEFAULT_MACD_SIGNAL}",
        ],
        "docs": _DOC_INDICATOR_PERIODS,
        "warning_codes": [],
    },
    "INDICATOR_MACD_SLOW": {
        "title": "MACD Slow Period",
        "description": (
            f"MACD slow EMA period (default {DEFAULT_MACD_SLOW}). "
            "Must be greater than INDICATOR_MACD_FAST."
        ),
        "category": "indicators",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": str(DEFAULT_MACD_SLOW),
        "options": [],
        "validation": {"min": MIN_PERIOD, "max": MAX_MACD_PERIOD},
        "display_order": 30,
        "help_key": "settings.indicators.macd_params",
        "examples": [
            f"INDICATOR_MACD_SLOW={DEFAULT_MACD_SLOW}",
            f"INDICATOR_MACD_FAST={DEFAULT_MACD_FAST}",
        ],
        "docs": _DOC_INDICATOR_PERIODS,
        "warning_codes": [],
    },
    "INDICATOR_MACD_SIGNAL": {
        "title": "MACD Signal Period",
        "description": f"MACD signal-line EMA period (default {DEFAULT_MACD_SIGNAL}).",
        "category": "indicators",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": str(DEFAULT_MACD_SIGNAL),
        "options": [],
        "validation": {"min": MIN_PERIOD, "max": MAX_MACD_PERIOD},
        "display_order": 40,
        "help_key": "settings.indicators.macd_params",
        "examples": [
            f"INDICATOR_MACD_SIGNAL={DEFAULT_MACD_SIGNAL}",
        ],
        "docs": _DOC_INDICATOR_PERIODS,
        "warning_codes": [],
    },
    "INDICATOR_RSI_PERIODS": {
        "title": "RSI Periods",
        "description": (
            "Comma-separated RSI periods (default "
            f"{_DEFAULT_RSI}). The first three values map to rsi_6/rsi_12/rsi_24 "
            "legacy slots for report compatibility."
        ),
        "category": "indicators",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": _DEFAULT_RSI,
        "options": [],
        "validation": {},
        "display_order": 50,
        "help_key": "settings.indicators.INDICATOR_RSI_PERIODS",
        "examples": [
            f"INDICATOR_RSI_PERIODS={_DEFAULT_RSI}",
            "INDICATOR_RSI_PERIODS=7,14,21",
        ],
        "docs": _DOC_INDICATOR_PERIODS,
        "warning_codes": [],
    },
}
