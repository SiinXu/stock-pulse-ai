# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API contract tests for GET /api/v1/stocks/{code}/trust (Issue #1129)."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.data_provider.base import DataFetcherManager
from src.data_provider.realtime_types import RealtimeSource
from src.storage import DatabaseManager
from tests.data_provider.test_field_trust import _DummyFetcher, _make_quote, _mock_config


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


class StockFieldTrustApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "field_trust_api_test.db"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    "DATA_VALIDATION_ENABLED=true",
                    "DATA_VALIDATION_STRICT=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        os.environ["DATA_VALIDATION_ENABLED"] = "true"
        Config.reset_instance()
        DatabaseManager.reset_instance()
        app = create_app(static_dir=self.data_dir / "empty-static")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("DATA_VALIDATION_ENABLED", None)
        self.temp_dir.cleanup()

    def _get_trust(self, manager: DataFetcherManager, code: str = "600519"):
        with patch(
            "src.services.stock_service.StockService._resolve_data_fetcher_manager",
            return_value=manager,
        ), patch("src.config.get_config", return_value=_mock_config()):
            return self.client.get(f"/api/v1/stocks/{code}/trust")

    def test_stale_and_conflict_fixture_returns_visible_degradation(self) -> None:
        stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        primary = _make_quote(source=RealtimeSource.EFINANCE, provider_timestamp=stale_ts)
        conflicting = _make_quote(source=RealtimeSource.AKSHARE_EM, volume_ratio=1.5)
        conflicting.price = 2100.0
        manager = DataFetcherManager(
            fetchers=[
                _DummyFetcher("EfinanceFetcher", 0, result=primary),
                _DummyFetcher("AkshareFetcher", 1, result=conflicting),
            ]
        )

        resp = self._get_trust(manager)
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["schema_version"], "field_trust_view/1.0")
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["metadata_present"])
        self.assertEqual(payload["quote_source"], "efinance")
        self.assertTrue(payload["is_stale"])
        self.assertGreater(payload["stale_seconds"], 600)
        price = next(entry for entry in payload["fields"] if entry["field"] == "price")
        self.assertEqual(price["source"], "efinance")
        self.assertEqual(price["staleness"], "stale")
        self.assertTrue(price["conflict"])
        self.assertEqual(price["value"], 1688.0)
        conflict_fields = {entry["field"] for entry in payload["conflicts"]}
        self.assertIn("price", conflict_fields)
        providers = {
            item["provider"]: item["value"]
            for entry in payload["conflicts"]
            if entry["field"] == "price"
            for item in entry["values"]
        }
        self.assertEqual(providers["efinance"], 1688.0)
        self.assertEqual(providers["akshare_em"], 2100.0)
        health_providers = {row["provider"] for row in payload["provider_health"]}
        self.assertIn("efinance", health_providers)
        self.assertEqual(payload["analysis_input"]["confidence"], "low")
        gap_codes = {gap["code"] for gap in payload["analysis_input"]["gaps"]}
        self.assertIn("conflict", gap_codes)
        self.assertIn("stale", gap_codes)

    def test_provider_failure_then_fallback_exposes_health(self) -> None:
        fresh_ts = datetime.now(timezone.utc).isoformat()
        fallback = _make_quote(
            source=RealtimeSource.AKSHARE_EM,
            provider_timestamp=fresh_ts,
            volume_ratio=1.1,
            turnover_rate=0.5,
            pe_ratio=20.0,
            pb_ratio=5.0,
            total_mv=1.0,
            circ_mv=1.0,
            amplitude=1.0,
            iopv=1.0,
            nav=1.0,
        )
        manager = DataFetcherManager(
            fetchers=[
                _DummyFetcher("EfinanceFetcher", 0, error=RuntimeError("efinance down")),
                _DummyFetcher("AkshareFetcher", 1, result=fallback),
            ]
        )

        resp = self._get_trust(manager)
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["fallback_from"], "efinance")
        statuses = {(row["provider"], row["status"]) for row in payload["provider_health"]}
        self.assertIn(("efinance", "failed"), statuses)
        self.assertIn(("akshare_em", "ok"), statuses)
        self.assertEqual(payload["analysis_input"]["confidence"], "low")
        self.assertTrue(
            any(gap["code"] == "provider_failed" for gap in payload["analysis_input"]["gaps"])
        )

    def test_post_primary_failure_degrades_health_view(self) -> None:
        fresh_ts = datetime.now(timezone.utc).isoformat()
        primary = _make_quote(
            source=RealtimeSource.EFINANCE,
            provider_timestamp=fresh_ts,
        )
        manager = DataFetcherManager(
            fetchers=[
                _DummyFetcher("EfinanceFetcher", 0, result=primary),
                _DummyFetcher("AkshareFetcher", 1, error=RuntimeError("akshare down")),
            ]
        )

        resp = self._get_trust(manager)
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "degraded")
        statuses = {(row["provider"], row["status"]) for row in payload["provider_health"]}
        self.assertIn(("efinance", "ok"), statuses)
        self.assertIn(("akshare_em", "failed"), statuses)
        self.assertEqual(payload["analysis_input"]["confidence"], "low")

    def test_comparison_exception_does_not_read_as_trusted(self) -> None:
        fresh_ts = datetime.now(timezone.utc).isoformat()
        primary = _make_quote(
            source=RealtimeSource.EFINANCE,
            provider_timestamp=fresh_ts,
        )
        secondary = _make_quote(source=RealtimeSource.AKSHARE_EM, pe_ratio=25.5)
        secondary.price = 200.0
        manager = DataFetcherManager(
            fetchers=[
                _DummyFetcher("EfinanceFetcher", 0, result=primary),
                _DummyFetcher("AkshareFetcher", 1, result=secondary),
            ]
        )

        with patch(
            "src.data_provider.data_validation.compare_cross_source_quotes",
            side_effect=RuntimeError("comparison exploded"),
        ):
            resp = self._get_trust(manager)
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertNotEqual(payload["analysis_input"]["confidence"], "high")
        self.assertTrue(
            any(
                check.get("reason") == "comparison_failed"
                for check in payload["conflict_checks"]
            )
        )

    def test_unavailable_when_every_provider_fails(self) -> None:
        manager = DataFetcherManager(
            fetchers=[
                _DummyFetcher("EfinanceFetcher", 0, error=RuntimeError("down")),
                _DummyFetcher("AkshareFetcher", 1, error=RuntimeError("down")),
            ]
        )

        resp = self._get_trust(manager)
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "unavailable")
        self.assertFalse(payload["metadata_present"])
        self.assertEqual(payload["fields"], [])
        self.assertEqual(payload["analysis_input"]["confidence"], "low")
        self.assertEqual(payload["analysis_input"]["gaps"][0]["code"], "quote_unavailable")

    def test_invalid_stock_code_is_400(self) -> None:
        resp = self.client.get("/api/v1/stocks/!!!/trust")
        self.assertEqual(resp.status_code, 400, resp.text)
