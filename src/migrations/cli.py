"""Command-line status and verification for the configured database."""

from __future__ import annotations

import argparse
import json
from typing import Optional, Sequence

from src.config import get_config
from src.migrations.engine import read_only_migration_connection
from src.migrations.registry import TARGET_VERSION
from src.migrations.runner import status, verify
from src.migrations.types import MigrationError, MigrationStatus


def _failure_payload(error: MigrationError) -> dict:
    state = error.state
    if state is not None:
        return MigrationStatus(
            current_version=state.current_version,
            target_version=state.target_version,
            applied_ids=state.applied_ids,
            pending_ids=state.pending_ids,
            unknown_ids=state.unknown_ids,
            checksum_mismatches=state.checksum_mismatches,
            description_mismatches=state.description_mismatches,
            success=False,
            failure_code=error.failure_code,
            failed_migration_id=error.migration_id,
        ).to_dict()
    return MigrationStatus(
        target_version=TARGET_VERSION,
        success=False,
        failure_code=error.failure_code,
        failed_migration_id=error.migration_id,
    ).to_dict()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect StockPulse database migrations")
    parser.add_argument("command", choices=("status", "verify"))
    args = parser.parse_args(argv)

    try:
        config = get_config()
        db_url = config.get_db_url(create_parent=False)
        with read_only_migration_connection(
            db_url,
            sqlite_busy_timeout_ms=config.sqlite_busy_timeout_ms,
        ) as connection:
            result = status(connection) if args.command == "status" else verify(connection)
        payload = result.to_dict()
    except MigrationError as exc:
        payload = _failure_payload(exc)
    except Exception:
        payload = MigrationStatus(
            target_version=TARGET_VERSION,
            success=False,
            failure_code="database_inspection_failed",
        ).to_dict()

    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
