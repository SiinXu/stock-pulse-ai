# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API contract tests for GET /api/v1/stocks/{code}/money-flow (Issue #989)."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import src.auth as auth
from src.api.app import create_app
from src.data_provider.money_flow_types import MoneyFlowOutcome, MoneyFlowSnapshot, MoneyFlowStatus
from src.config import Config
from src.storage import DatabaseManager


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


def _partial_outcome() -> MoneyFlowOutcome:
    snapshot = MoneyFlowSnapshot(
        code="600519",
        date="2026-08-08",
        source="akshare:stock_individual_fund_flow",
        main_net_inflow_ratio=1.5,
        super_large_net_inflow_ratio=0.8,
        large_net_inflow_ratio=0.7,
        bucket_definition="eastmoney_em_order_size_buckets_v1;amount_unit=unknown",
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
        source_chain=[{"provider": "akshare", "status": "partial"}],
        warnings=["money_flow_amount_scale_is_not_authoritatively_calibrated"],
    )


class StockMoneyFlowApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "money_flow_api_test.db"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    "SMARTMONEY_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        os.environ["SMARTMONEY_ENABLED"] = "false"
        Config.reset_instance()
        DatabaseManager.reset_instance()
        app = create_app(static_dir=self.data_dir / "empty-static")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("SMARTMONEY_ENABLED", None)
        self.temp_dir.cleanup()

    def test_disabled_gate_returns_zero_io_payload(self) -> None:
        with patch(
            "src.services.smartmoney_flow_service.fetch_money_flow",
            side_effect=AssertionError("must not fetch when disabled"),
        ):
            resp = self.client.get("/api/v1/stocks/600519/money-flow")
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["schema_version"], "money_flow_view/1.0")
        self.assertEqual(payload["stock_code"], "600519")
        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["status"], "disabled")
        self.assertIsNone(payload["snapshot"])
        self.assertIn("SMARTMONEY_ENABLED", payload["message"] or "")
        self.assertTrue(payload["disclaimer"])

    def test_enabled_partial_outcome_preserves_as_of_and_source(self) -> None:
        config = SimpleNamespace(smartmoney_enabled=True)
        services = SimpleNamespace(config=config)
        with patch(
            "src.api.v1.endpoints.stocks.get_application_services",
            return_value=services,
        ), patch(
            "src.services.smartmoney_flow_service.fetch_money_flow",
            return_value=_partial_outcome(),
        ):
            resp = self.client.get("/api/v1/stocks/600519/money-flow?days=5")
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["source"], "akshare:stock_individual_fund_flow")
        self.assertEqual(payload["provider_date"], "2026-08-08")
        self.assertEqual(payload["as_of"], "2026-08-08T08:00:00Z")
        self.assertIsNotNone(payload["snapshot"])
        self.assertEqual(payload["snapshot"]["main_net_inflow_ratio"], 1.5)
        self.assertEqual(payload["snapshot"]["attitude"], "inflow")
        self.assertIn(
            "money_flow_amount_scale_is_not_authoritatively_calibrated",
            payload["warnings"],
        )

    def test_invalid_days_returns_validation_error(self) -> None:
        resp = self.client.get("/api/v1/stocks/600519/money-flow?days=99")
        self.assertEqual(resp.status_code, 422)

    def test_invalid_stock_code_returns_400(self) -> None:
        resp = self.client.get("/api/v1/stocks/!!!/money-flow")
        self.assertEqual(resp.status_code, 400)

    def test_invalid_internal_payload_is_sanitized_500_not_input_error(self) -> None:
        config = SimpleNamespace(smartmoney_enabled=True)
        services = SimpleNamespace(config=config)
        invalid_payload = {
            "schema_version": "money_flow_view/1.0",
            "stock_code": "600519",
            "enabled": True,
            "status": "partial",
            "requested_days": 5,
            "fetched_at": "2026-08-08T08:01:00+00:00",
            "as_of": "2026-08-08T08:00:00+00:00",
            "provider_date": "2026-08-08",
            "age_days": 0,
            "source": "test",
            "source_chain": [],
            "market": "cn",
            "error_code": None,
            "warnings": [],
            "cache_state": "miss",
            "fallback_from": None,
            "snapshot": {"main_net_inflow_ratio": float("nan")},
            "message": "degraded",
            "disclaimer": "Research evidence only.",
        }
        with patch(
            "src.api.v1.endpoints.stocks.get_application_services",
            return_value=services,
        ), patch(
            "src.api.v1.endpoints.stocks.build_money_flow_view",
            return_value=invalid_payload,
        ):
            resp = self.client.get("/api/v1/stocks/600519/money-flow")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["error"], "internal_error")
        self.assertNotIn("nan", resp.text.lower())
        self.assertNotIn("validation", resp.text.lower())
