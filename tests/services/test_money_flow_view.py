# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for build_money_flow_view (Issue #989)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from data_provider.money_flow_types import MoneyFlowOutcome, MoneyFlowSnapshot, MoneyFlowStatus
from src.services.smartmoney_flow_service import build_money_flow_view


def _partial_outcome() -> MoneyFlowOutcome:
    snapshot = MoneyFlowSnapshot(
        code="600519",
        date="2026-08-08",
        source="akshare:stock_individual_fund_flow",
        main_net_inflow_ratio=1.5,
        bucket_definition="eastmoney_v1;amount_unit=unknown",
        as_of=datetime(2026, 8, 8, 8, 0, tzinfo=timezone.utc).isoformat(),
        requested_days=5,
        observed_days=5,
        completeness="complete",
    )
    return MoneyFlowOutcome(
        status=MoneyFlowStatus.PARTIAL,
        code="600519",
        market="cn",
        requested_days=5,
        fetched_at=datetime(2026, 8, 8, 8, 1, tzinfo=timezone.utc).isoformat(),
        snapshot=snapshot,
        provider_date="2026-08-08",
        age_days=0,
        warnings=["money_flow_amount_scale_is_not_authoritatively_calibrated"],
    )


def test_view_disabled_zero_io():
    class _Boom:
        def get_money_flow(self, *args, **kwargs):
            raise AssertionError("must not call manager when disabled")

        def close(self):
            return None

    view = build_money_flow_view(
        "600519",
        manager=_Boom(),
        config=SimpleNamespace(smartmoney_enabled=False),
    )
    assert view["enabled"] is False
    assert view["status"] == "disabled"
    assert view["snapshot"] is None
    assert "SMARTMONEY_ENABLED" in (view["message"] or "")


def test_view_projects_partial_snapshot_with_provenance():
    class _Manager:
        def get_money_flow(self, stock_code: str, days: int = 5):
            assert stock_code == "600519"
            assert days == 5
            return _partial_outcome()

        def close(self):
            return None

    view = build_money_flow_view(
        "600519",
        manager=_Manager(),
        config=SimpleNamespace(smartmoney_enabled=True),
    )
    assert view["enabled"] is True
    assert view["status"] == "partial"
    assert view["source"] == "akshare:stock_individual_fund_flow"
    assert view["as_of"] == "2026-08-08T08:00:00+00:00"
    assert view["provider_date"] == "2026-08-08"
    assert view["snapshot"]["main_net_inflow_ratio"] == 1.5
    assert view["snapshot"]["attitude"] == "inflow"
    assert "degraded" in (view["message"] or "").lower()


def test_view_not_supported_is_honest():
    class _Manager:
        def get_money_flow(self, stock_code: str, days: int = 5):
            return MoneyFlowOutcome(
                status=MoneyFlowStatus.NOT_SUPPORTED,
                code="AAPL",
                market="us",
                requested_days=5,
                fetched_at=datetime.now(timezone.utc).isoformat(),
                error_code="money_flow_market_not_supported",
            )

        def close(self):
            return None

    view = build_money_flow_view(
        "AAPL",
        manager=_Manager(),
        config=SimpleNamespace(smartmoney_enabled=True),
    )
    assert view["status"] == "not_supported"
    assert view["snapshot"] is None
    assert view["error_code"] == "money_flow_market_not_supported"
    assert "unavailable" in (view["message"] or "").lower()


def test_view_rejects_empty_stock_code():
    with pytest.raises(ValueError, match="stock_code"):
        build_money_flow_view("", config=SimpleNamespace(smartmoney_enabled=False))


def test_view_bounds_public_provider_diagnostics_and_warnings():
    outcome = _partial_outcome()
    outcome.source_chain = [
        {
            "provider": "akshare",
            "status": "success",
            "latency_ms": 12,
            "provider_date": "2026-08-08",
            "private_debug_metric": float("nan"),
        }
    ]
    outcome.warnings = [f"warning_{index}" for index in range(20)]

    class _Manager:
        def get_money_flow(self, stock_code: str, days: int = 5):
            return outcome

        def close(self):
            return None

    view = build_money_flow_view(
        "600519",
        manager=_Manager(),
        config=SimpleNamespace(smartmoney_enabled=True),
    )
    assert view["source_chain"] == [
        {
            "provider": "akshare",
            "status": "success",
            "latency_ms": 12,
            "provider_date": "2026-08-08",
        }
    ]
    assert len(view["warnings"]) == 16
    assert view["warnings"][-1] == "money_flow_warnings_truncated"
    assert "raw_field_map" not in view["snapshot"]
