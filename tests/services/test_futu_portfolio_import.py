# -*- coding: utf-8 -*-
"""Portfolio import service seam for Futu live positions."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from data_provider.futu_position_fetcher import FutuPosition, FutuPositionFetchError
from src.config import Config
from src.services.portfolio_import_service import PortfolioImportService
from src.services.portfolio_service import PortfolioService
from src.storage import DatabaseManager


class FutuPortfolioImportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.db_path = self.data_dir / "futu_import.db"
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.service = PortfolioService()
        self.importer = PortfolioImportService(portfolio_service=self.service)
        account = self.service.create_account(
            name="Futu Import",
            broker="Futu",
            market="us",
            base_currency="USD",
        )
        self.account_id = int(account["id"])

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def _sample_positions(self):
        return [
            FutuPosition(
                futu_acc_id=101,
                futu_code="US.AAPL",
                symbol="AAPL",
                market="US",
                quantity=5.0,
                cost_price=190.0,
                currency="USD",
            ),
            FutuPosition(
                futu_acc_id=101,
                futu_code="US.MSFT",
                symbol="MSFT",
                market="US",
                quantity=2.0,
                cost_price=420.0,
                currency="USD",
            ),
        ]

    def test_import_mapping_and_idempotent_reimport(self) -> None:
        with patch(
            "src.services.portfolio_import_service.fetch_futu_positions",
            return_value=self._sample_positions(),
        ):
            first = self.importer.import_futu_positions(
                account_id=self.account_id,
                as_of=date(2026, 8, 6),
            )
            second = self.importer.import_futu_positions(
                account_id=self.account_id,
                as_of=date(2026, 8, 6),
            )

        self.assertEqual(first["inserted_count"], 2)
        self.assertEqual(first["duplicate_count"], 0)
        self.assertEqual(first["failed_count"], 0)
        self.assertEqual(second["inserted_count"], 0)
        self.assertEqual(second["duplicate_count"], 2)
        self.assertEqual(second["failed_count"], 0)

        snapshot = self.service.get_portfolio_snapshot(
            account_id=self.account_id,
            as_of=date(2026, 8, 6),
            cost_method="fifo",
        )
        accounts = snapshot.get("accounts") or []
        self.assertTrue(accounts)
        symbols = {item["symbol"]: item for item in accounts[0].get("positions") or []}
        self.assertIn("AAPL", symbols)
        self.assertEqual(float(symbols["AAPL"]["quantity"]), 5.0)

    def test_unreachable_gateway_does_not_write(self) -> None:
        with patch(
            "src.services.portfolio_import_service.fetch_futu_positions",
            side_effect=FutuPositionFetchError(
                "Futu OpenD is unreachable or rejected the account query"
            ),
        ):
            with self.assertRaises(FutuPositionFetchError):
                self.importer.import_futu_positions(account_id=self.account_id)

        snapshot = self.service.get_portfolio_snapshot(
            account_id=self.account_id,
            as_of=date(2026, 8, 6),
            cost_method="fifo",
        )
        self.assertEqual(snapshot.get("positions") or [], [])


if __name__ == "__main__":
    unittest.main()
