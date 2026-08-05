# -*- coding: utf-8 -*-
"""Leaf helpers for parsing user-facing STOCK_LIST separator forms.

This module is intentionally stdlib-only so configuration and other low-level
packages can depend on it without pulling in the service layer.
"""

from __future__ import annotations

import re
from typing import List

_STOCK_LIST_SEPARATOR_RE = re.compile(r"[\s,;\uFF0C\u3001\uFF1B]+")


def split_stock_list(value: str) -> List[str]:
    """Split STOCK_LIST values on common copy/paste separators."""
    return [
        item.strip()
        for item in _STOCK_LIST_SEPARATOR_RE.split(value or "")
        if item.strip()
    ]
