# -*- coding: utf-8 -*-
"""Pure Tencent realtime field parsers for the AkShare provider.

No network I/O. Extracted from ``data_provider.akshare_fetcher`` (Issue #1068).
"""

from __future__ import annotations

from typing import List, Optional

from src.data_provider.realtime_types import safe_float, safe_int


def _normalize_tencent_volume(fields: List[str]) -> Optional[int]:
    """
    将腾讯实时行情成交量归一为股。

    腾讯返回内容对字段 6 的公开说明和实际返回不完全一致。优先使用
    换手率、价格、流通市值交叉校验，在原值和旧的“手转股”结果中选择
    更接近的一方。若无法交叉校验，则保留旧的“手转股”兜底逻辑，避免
    传统腾讯返回内容回归为原成交量的 1/100。
    """
    if len(fields) <= 6 or not fields[6]:
        return None

    raw_volume = safe_int(fields[6])
    if raw_volume is None:
        return None

    price = safe_float(fields[3]) if len(fields) > 3 else None
    turnover_rate = safe_float(fields[38]) if len(fields) > 38 else None
    circ_mv_yi = safe_float(fields[44]) if len(fields) > 44 and fields[44] else None
    circ_mv = circ_mv_yi * 100000000 if circ_mv_yi is not None else None

    if price and price > 0 and turnover_rate and turnover_rate > 0 and circ_mv and circ_mv > 0:
        expected_volume = (circ_mv / price) * (turnover_rate / 100)
        if expected_volume > 0:
            raw_delta = abs(raw_volume - expected_volume)
            hand_to_share_volume = raw_volume * 100
            hand_delta = abs(hand_to_share_volume - expected_volume)
            return raw_volume if raw_delta <= hand_delta else hand_to_share_volume

    return raw_volume * 100


def _parse_tencent_amount(fields: List[str]) -> Optional[float]:
    """
    解析腾讯实时行情成交额，单位为元。

    观测到的返回内容中，字段 35 包含更精确的“价格/成交量/成交额”
    三元组。字段 37 是旧的“万元”口径兜底字段。
    """
    if len(fields) > 35 and fields[35]:
        parts = fields[35].split("/")
        if len(parts) >= 3:
            precise_amount = safe_float(parts[2])
            if precise_amount is not None:
                return precise_amount

    amount_wan = safe_float(fields[37]) if len(fields) > 37 and fields[37] else None
    return amount_wan * 10000 if amount_wan is not None else None

