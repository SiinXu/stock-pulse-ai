"""Base configuration field definitions."""

from typing import Any, Dict

BASE_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "STOCK_LIST": {
        "title": "Stock List",
        "description": "Watchlist stock codes. English commas are recommended; common pasted separators are normalized on save.",
        "category": "base",
        "data_type": "array",
        "ui_control": "textarea",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "600519,300750,002594",
        "options": [],
        "validation": {"min_items": 1},
        "display_order": 10,
        "help_key": "settings.base.STOCK_LIST",
        "examples": [
            "STOCK_LIST=600519,300750,002594",
            "STOCK_LIST=600519,hk00700,AAPL",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
            {
                "label": "Tushare 股票列表指南",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/TUSHARE_STOCK_LIST_GUIDE.md",
            },
        ],
        "warning_codes": [],
    },
}
