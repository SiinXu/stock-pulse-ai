"""Known legacy marker created by the pre-runner initialization flow."""

from sqlalchemy.engine import Connection

from src.migrations.types import Migration


MIGRATION_ID = "2026-06-05-create-all-baseline"
DESCRIPTION = "Baseline schema created through SQLAlchemy metadata.create_all"


def upgrade(_connection: Connection) -> None:
    """The legacy marker is verified and stamped, never newly applied."""


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
    is_legacy_baseline=True,
)
