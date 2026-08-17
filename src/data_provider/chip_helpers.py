# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Pure chip-distribution metric helpers.

Extracted from :mod:`data_provider.base` behind an ADR-006 compatibility facade.
Public imports and patch targets remain on ``data_provider.base``.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np


def _coerce_chip_metric(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        numeric = float(value)
        if np.isnan(numeric):
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _is_meaningful_chip_distribution(chip: Any) -> bool:
    """Validate that a provider returned usable core chip metrics."""
    if chip is None:
        return False
    avg_cost = _coerce_chip_metric(getattr(chip, "avg_cost", None))
    concentration_90 = _coerce_chip_metric(getattr(chip, "concentration_90", None))
    concentration_70 = _coerce_chip_metric(getattr(chip, "concentration_70", None))
    return (
        avg_cost is not None
        and avg_cost > 0
        and (
            (concentration_90 is not None and concentration_90 >= 0)
            or (concentration_70 is not None and concentration_70 >= 0)
        )
    )
