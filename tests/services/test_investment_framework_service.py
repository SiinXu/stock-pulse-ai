"""Service, history, concurrency, and context contracts for frameworks."""

import json

import pytest
from pydantic import ValidationError

from src.config import Config
from src.repositories.investment_framework_repo import (
    InvestmentFrameworkRepository,
    InvestmentFrameworkRepositoryError,
)
from src.schemas.investment_framework import (
    InvestmentFrameworkContent,
    InvestmentFrameworkEvaluationDimension,
)
from src.services.investment_framework_context import InvestmentFrameworkContextReader
from src.services.investment_framework_service import (
    InvestmentFrameworkDataError,
    InvestmentFrameworkNotFoundError,
    InvestmentFrameworkRevisionConflictError,
    InvestmentFrameworkService,
    InvestmentFrameworkServiceError,
)
from src.storage import (
    DatabaseManager,
    InvestmentFrameworkRecord,
    InvestmentFrameworkVersionRecord,
)


@pytest.fixture
def database():
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    yield manager
    DatabaseManager.reset_instance()
    Config.reset_instance()


def _content(title: str, rule: str) -> InvestmentFrameworkContent:
    return InvestmentFrameworkContent(
        title=title,
        evaluation_dimensions=[
            {
                "name": "Business quality",
                "weight": 60,
                "criteria": ["Use primary financial evidence"],
            }
        ],
        risk_rules=[rule],
        tracking_criteria=["Review material changes"],
    )


def _storage_snapshot(database: DatabaseManager) -> tuple:
    with database._engine.connect() as connection:
        aggregates = tuple(
            connection.exec_driver_sql(
                "SELECT id, scope_key, latest_version, active_version, revision, "
                "created_at, updated_at FROM investment_frameworks ORDER BY id"
            ).fetchall()
        )
        versions = tuple(
            connection.exec_driver_sql(
                "SELECT id, framework_id, version, content_json, change_summary, "
                "created_at FROM investment_framework_versions "
                "ORDER BY framework_id, version, id"
            ).fetchall()
        )
    return aggregates, versions


def test_no_data_is_an_explicit_context_no_op(database) -> None:
    service = InvestmentFrameworkService(database)
    reader = InvestmentFrameworkContextReader(database)

    assert reader.read() is None
    with pytest.raises(InvestmentFrameworkNotFoundError):
        service.get()


def test_crud_history_active_version_and_reactivation(database) -> None:
    service = InvestmentFrameworkService(database)
    reader = InvestmentFrameworkContextReader(database)

    created = service.create(
        content=_content("Version one", "Maximum position size is 5%"),
        change_summary="Initial framework",
    )
    assert (created["version"], created["active_version"], created["revision"]) == (
        1,
        1,
        1,
    )
    assert reader.read().framework_version == 1

    updated = service.update(
        expected_revision=1,
        content=_content("Version two", "Maximum position size is 4%"),
        change_summary="Tighten position risk",
    )
    assert (updated["version"], updated["active_version"], updated["revision"]) == (
        2,
        2,
        2,
    )
    history = service.list_history()
    assert [item["version"] for item in history["items"]] == [2, 1]
    assert [item["is_active"] for item in history["items"]] == [True, False]

    inactive = service.deactivate(expected_revision=2)
    assert inactive["active_version"] is None
    assert inactive["is_active"] is False
    assert inactive["revision"] == 3
    assert reader.read() is None
    with pytest.raises(InvestmentFrameworkRevisionConflictError) as stale_retry:
        service.deactivate(expected_revision=2)
    assert stale_retry.value.current_revision == 3
    repeated = service.deactivate(expected_revision=3)
    assert repeated["revision"] == 3
    assert service.list_history()["total"] == 2

    reactivated = service.update(
        expected_revision=3,
        content=_content("Version three", "Maximum position size is 3%"),
        change_summary="Reactivate with a new version",
    )
    assert (reactivated["version"], reactivated["active_version"]) == (3, 3)
    context = reader.read()
    assert context is not None
    assert context.schema_version == "investment-framework-context-v1"
    assert context.framework_version == 3
    assert context.content.title == "Version three"


def test_two_writers_reject_the_stale_optimistic_revision(database) -> None:
    first_writer = InvestmentFrameworkService(database)
    second_writer = InvestmentFrameworkService(database)
    first_writer.create(content=_content("Initial", "Initial risk rule"))

    winner = first_writer.update(
        expected_revision=1,
        content=_content("Winner", "Winning risk rule"),
    )
    assert winner["revision"] == 2

    with pytest.raises(InvestmentFrameworkRevisionConflictError) as conflict:
        second_writer.update(
            expected_revision=1,
            content=_content("Stale", "Stale risk rule"),
        )
    assert conflict.value.current_revision == 2
    history = first_writer.list_history()
    assert [item["content"].title for item in history["items"]] == [
        "Winner",
        "Initial",
    ]


def test_mutated_model_instances_are_revalidated_before_persistence(database) -> None:
    service = InvestmentFrameworkService(database)
    invalid_create = _content("Invalid create", "Initial risk rule")
    invalid_create.evaluation_dimensions[0].weight = "60"

    with pytest.raises(ValidationError):
        service.create(content=invalid_create)

    invalid_nested_create = InvestmentFrameworkEvaluationDimension(
        name="Business quality",
        weight=60,
        criteria=["Use primary financial evidence"],
    )
    invalid_nested_create.weight = "60"
    with pytest.raises(ValidationError):
        service.create(
            content={
                "title": "Invalid nested create",
                "evaluation_dimensions": [invalid_nested_create],
            }
        )
    with pytest.raises(InvestmentFrameworkNotFoundError):
        service.get()

    service.create(content=_content("Initial", "Initial risk rule"))
    invalid_update = InvestmentFrameworkEvaluationDimension(
        name="Business quality",
        weight=55,
        criteria=["Use primary financial evidence"],
    )
    invalid_update.weight = "55"
    with pytest.raises(ValidationError):
        service.update(
            expected_revision=1,
            content={
                "title": "Invalid nested update",
                "evaluation_dimensions": [invalid_update],
            },
        )
    assert service.get()["revision"] == 1


def test_history_integrity_error_is_not_misreported_as_revision_conflict(
    database,
) -> None:
    service = InvestmentFrameworkService(database)
    service.create(content=_content("Initial", "Initial risk rule"))
    with database.get_session() as session:
        first = session.query(InvestmentFrameworkVersionRecord).one()
        session.add(
            InvestmentFrameworkVersionRecord(
                framework_id=first.framework_id,
                version=2,
                content_json=first.content_json,
                change_summary="Injected inconsistent future version",
                created_at=first.created_at,
            )
        )
        session.commit()
    before = _storage_snapshot(database)

    with pytest.raises(InvestmentFrameworkDataError):
        service.update(
            expected_revision=1,
            content=_content("Would conflict with orphan", "Updated risk rule"),
        )
    with pytest.raises(InvestmentFrameworkDataError):
        service.get()
    assert _storage_snapshot(database) == before


def test_orphan_history_is_not_misreported_as_existing_framework(database) -> None:
    with database._engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql(
            "INSERT INTO investment_framework_versions "
            "(framework_id, version, content_json, change_summary, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                1,
                1,
                "{}",
                "Injected orphan history",
                "2026-07-25 00:00:00",
            ),
        )
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")

    service = InvestmentFrameworkService(database)
    with pytest.raises(InvestmentFrameworkDataError):
        service.create(content=_content("Initial", "Initial risk rule"))
    with pytest.raises(InvestmentFrameworkDataError):
        service.get()


def test_foreign_owner_orphan_history_blocks_create_and_all_reads(database) -> None:
    with database._engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql(
            "INSERT INTO investment_framework_versions "
            "(framework_id, version, content_json, change_summary, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                999,
                1,
                "{}",
                "Injected foreign-owner history",
                "2026-07-25 00:00:00",
            ),
        )
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")

    service = InvestmentFrameworkService(database)
    reader = InvestmentFrameworkContextReader(database)
    before = _storage_snapshot(database)

    for operation in (
        service.get,
        service.list_history,
        reader.read,
        lambda: service.create(content=_content("Initial", "Initial risk rule")),
    ):
        with pytest.raises(InvestmentFrameworkDataError):
            operation()
        assert _storage_snapshot(database) == before


@pytest.mark.parametrize(
    "changes",
    (
        pytest.param({"revision": 0}, id="zero-revision"),
        pytest.param({"active_version": 99}, id="missing-active-version"),
        pytest.param(
            {"revision": 999, "active_version": 1},
            id="active-revision-above-legal-bound",
        ),
        pytest.param(
            {"revision": 1, "active_version": None},
            id="inactive-revision-below-legal-bound",
        ),
        pytest.param(
            {"revision": 2, "active_version": 1},
            id="active-revision-after-impossible-deactivation",
        ),
        pytest.param(
            {
                "latest_version": 9223372036854775807,
                "active_version": 9223372036854775807,
                "revision": 9223372036854775807,
            },
            id="unbounded-latest-version",
        ),
    ),
)
def test_corrupt_aggregate_invariants_fail_every_path_without_mutation(
    database,
    changes: dict[str, object],
) -> None:
    service = InvestmentFrameworkService(database)
    reader = InvestmentFrameworkContextReader(database)
    service.create(content=_content("Initial", "Initial risk rule"))
    with database.get_session() as session:
        aggregate = session.query(InvestmentFrameworkRecord).one()
        for field, value in changes.items():
            setattr(aggregate, field, value)
        session.commit()
    before = _storage_snapshot(database)

    service_operations = (
        service.get,
        service.list_history,
        reader.read,
        lambda: service.update(
            expected_revision=1,
            content=_content("Blocked update", "Blocked update risk rule"),
        ),
        lambda: service.deactivate(expected_revision=1),
        lambda: service.delete(expected_revision=1),
        lambda: service.create(
            content=_content("Blocked create", "Blocked create risk rule")
        ),
    )
    for operation in service_operations:
        with pytest.raises(InvestmentFrameworkDataError):
            operation()
        assert _storage_snapshot(database) == before

    repository = InvestmentFrameworkRepository(database)
    repository_operations = (
        repository.get_current,
        repository.get_active,
        repository.list_history,
        lambda: repository.update(
            expected_revision=1,
            content_json="{}",
            change_summary=None,
        ),
        lambda: repository.deactivate(expected_revision=1),
        lambda: repository.delete(expected_revision=1),
        lambda: repository.create(
            content_json="{}",
            change_summary=None,
        ),
    )
    for operation in repository_operations:
        with pytest.raises(InvestmentFrameworkRepositoryError):
            operation()
        assert _storage_snapshot(database) == before


def test_revision_boundaries_follow_every_legal_transition(database) -> None:
    service = InvestmentFrameworkService(database)

    created = service.create(content=_content("One", "One risk rule"))
    assert (created["version"], created["revision"], created["is_active"]) == (
        1,
        1,
        True,
    )
    inactive_one = service.deactivate(expected_revision=1)
    assert (inactive_one["version"], inactive_one["revision"]) == (1, 2)
    active_two = service.update(
        expected_revision=2,
        content=_content("Two", "Two risk rule"),
    )
    assert (active_two["version"], active_two["revision"]) == (2, 3)
    inactive_two = service.deactivate(expected_revision=3)
    assert (inactive_two["version"], inactive_two["revision"]) == (2, 4)
    active_three = service.update(
        expected_revision=4,
        content=_content("Three", "Three risk rule"),
    )
    assert (active_three["version"], active_three["revision"]) == (3, 5)
    assert service.get()["content"].title == "Three"


@pytest.mark.parametrize(
    "corruption",
    (
        pytest.param("future", id="future-version"),
        pytest.param("gap", id="missing-intermediate-version"),
        pytest.param("foreign-owner", id="foreign-owner-version"),
    ),
)
def test_noncanonical_history_set_fails_closed_without_mutation(
    database,
    corruption: str,
) -> None:
    service = InvestmentFrameworkService(database)
    service.create(content=_content("Initial", "Initial risk rule"))
    if corruption == "gap":
        service.update(
            expected_revision=1,
            content=_content("Second", "Second risk rule"),
        )
        service.update(
            expected_revision=2,
            content=_content("Third", "Third risk rule"),
        )

    with database._engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        if corruption == "gap":
            connection.exec_driver_sql(
                "DELETE FROM investment_framework_versions WHERE version = 2"
            )
        else:
            owner = 999 if corruption == "foreign-owner" else 1
            version = 1 if corruption == "foreign-owner" else 2
            connection.exec_driver_sql(
                "INSERT INTO investment_framework_versions "
                "(framework_id, version, content_json, change_summary, created_at) "
                "SELECT ?, ?, content_json, ?, created_at "
                "FROM investment_framework_versions WHERE version = 1",
                (owner, version, f"Injected {corruption} history"),
            )
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")

    before = _storage_snapshot(database)
    for operation in (
        service.get,
        service.list_history,
        InvestmentFrameworkContextReader(database).read,
        lambda: service.update(
            expected_revision=(
                3 if corruption == "gap" else 1
            ),
            content=_content("Blocked update", "Blocked update risk rule"),
        ),
        lambda: service.deactivate(
            expected_revision=3 if corruption == "gap" else 1
        ),
        lambda: service.delete(
            expected_revision=3 if corruption == "gap" else 1
        ),
    ):
        with pytest.raises(InvestmentFrameworkDataError):
            operation()
        assert _storage_snapshot(database) == before


@pytest.mark.parametrize("invalid_revision", (True, 1.0))
def test_service_rejects_non_integer_expected_revision(
    database,
    invalid_revision,
) -> None:
    service = InvestmentFrameworkService(database)
    service.create(content=_content("Initial", "Initial risk rule"))
    before = _storage_snapshot(database)

    for operation in (
        lambda: service.update(
            expected_revision=invalid_revision,
            content=_content("Blocked update", "Blocked update risk rule"),
        ),
        lambda: service.deactivate(expected_revision=invalid_revision),
        lambda: service.delete(expected_revision=invalid_revision),
    ):
        with pytest.raises(InvestmentFrameworkServiceError):
            operation()
        assert _storage_snapshot(database) == before


def test_delete_removes_history_and_allows_a_fresh_create(database) -> None:
    service = InvestmentFrameworkService(database)
    reader = InvestmentFrameworkContextReader(database)
    service.create(content=_content("Initial", "Initial risk rule"))
    service.update(
        expected_revision=1,
        content=_content("Second", "Second risk rule"),
    )

    with pytest.raises(InvestmentFrameworkRevisionConflictError):
        service.delete(expected_revision=1)
    deleted = service.delete(expected_revision=2)
    assert deleted["deleted"] is True
    assert deleted["deleted_through_version"] == 2
    assert reader.read() is None
    with pytest.raises(InvestmentFrameworkNotFoundError):
        service.list_history()

    recreated = service.create(content=_content("Fresh", "Fresh risk rule"))
    assert (recreated["version"], recreated["revision"]) == (1, 1)


def test_corrupt_persisted_content_fails_closed_instead_of_looking_absent(database) -> None:
    service = InvestmentFrameworkService(database)
    service.create(content=_content("Initial", "Initial risk rule"))
    with database.get_session() as session:
        row = session.query(InvestmentFrameworkVersionRecord).one()
        legacy_payload = json.loads(row.content_json)
        legacy_payload.pop("schema_version")
        row.content_json = json.dumps(legacy_payload)
        session.commit()

    assert service.get()["content"].schema_version == (
        "investment-framework-content-v1"
    )
    assert service.list_history()["items"][0]["content"].schema_version == (
        "investment-framework-content-v1"
    )
    assert InvestmentFrameworkContextReader(
        database
    ).read().content.schema_version == "investment-framework-content-v1"

    invalid_payloads = (
        {
            "schema_version": "investment-framework-content-v1",
            "title": "Legacy coerced scalar",
            "evaluation_dimensions": [
                {
                    "name": "Business quality",
                    "weight": "60",
                    "criteria": ["Use primary financial evidence"],
                }
            ],
        },
        {
            "schema_version": "investment-framework-content-v999",
            "title": "Unknown content version",
            "risk_rules": ["Do not reinterpret unknown criteria"],
        },
    )
    persisted_reads = (
        service.get,
        service.list_history,
        InvestmentFrameworkContextReader(database).read,
    )
    for payload in invalid_payloads:
        with database.get_session() as session:
            row = session.query(InvestmentFrameworkVersionRecord).one()
            row.content_json = json.dumps(payload)
            session.commit()

        for read in persisted_reads:
            with pytest.raises(InvestmentFrameworkDataError):
                read()


@pytest.mark.parametrize("invalid_summary", ("", "x" * 501))
def test_invalid_persisted_change_summary_fails_every_path_without_mutation(
    database,
    invalid_summary: str,
) -> None:
    service = InvestmentFrameworkService(database)
    service.create(
        content=_content("Initial", "Initial risk rule"),
        change_summary="Valid summary",
    )
    with database.get_session() as session:
        row = session.query(InvestmentFrameworkVersionRecord).one()
        row.change_summary = invalid_summary
        session.commit()
    before = _storage_snapshot(database)

    for operation in (
        service.get,
        service.list_history,
        InvestmentFrameworkContextReader(database).read,
        lambda: service.update(
            expected_revision=1,
            content=_content("Blocked update", "Blocked update risk rule"),
        ),
        lambda: service.deactivate(expected_revision=1),
        lambda: service.delete(expected_revision=1),
    ):
        with pytest.raises(InvestmentFrameworkDataError):
            operation()
        assert _storage_snapshot(database) == before


def test_create_rejects_valid_trigger_tampering_and_rolls_back(database) -> None:
    service = InvestmentFrameworkService(database)
    tampered_json = service._encode_content(
        _content("Tampered create", "Tampered create risk rule")
    ).replace("'", "''")
    with database._engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER tamper_framework_create "
            "AFTER INSERT ON investment_framework_versions BEGIN "
            "UPDATE investment_framework_versions "
            f"SET content_json = '{tampered_json}' WHERE id = NEW.id; END"
        )

    with pytest.raises(InvestmentFrameworkDataError):
        service.create(
            content=_content("Requested create", "Requested create risk rule"),
            change_summary="Requested summary",
        )

    assert _storage_snapshot(database) == ((), ())


def test_update_rejects_valid_trigger_tampering_of_immutable_history(
    database,
) -> None:
    service = InvestmentFrameworkService(database)
    service.create(
        content=_content("Initial", "Initial risk rule"),
        change_summary="Initial summary",
    )
    before = _storage_snapshot(database)
    tampered_json = service._encode_content(
        _content("Tampered history", "Tampered history risk rule")
    ).replace("'", "''")
    with database._engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER tamper_framework_history "
            "AFTER INSERT ON investment_framework_versions "
            "WHEN NEW.version > 1 BEGIN "
            "UPDATE investment_framework_versions "
            f"SET content_json = '{tampered_json}' "
            "WHERE framework_id = NEW.framework_id AND version = 1; END"
        )

    with pytest.raises(InvestmentFrameworkDataError):
        service.update(
            expected_revision=1,
            content=_content("Requested update", "Requested update risk rule"),
            change_summary="Requested update summary",
        )

    assert _storage_snapshot(database) == before


def test_deactivate_rejects_valid_trigger_reactivation_and_rolls_back(
    database,
) -> None:
    service = InvestmentFrameworkService(database)
    service.create(content=_content("Initial", "Initial risk rule"))
    service.update(
        expected_revision=1,
        content=_content("Second", "Second risk rule"),
    )
    before = _storage_snapshot(database)
    with database._engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TRIGGER tamper_framework_deactivate "
            "AFTER UPDATE OF active_version ON investment_frameworks "
            "WHEN NEW.active_version IS NULL BEGIN "
            "UPDATE investment_frameworks "
            "SET active_version = latest_version WHERE id = NEW.id; END"
        )

    with pytest.raises(InvestmentFrameworkDataError):
        service.deactivate(expected_revision=2)

    assert _storage_snapshot(database) == before


@pytest.mark.parametrize(
    ("table_name", "row_filter"),
    (
        pytest.param("investment_frameworks", "id = 1", id="aggregate-created-at"),
        pytest.param(
            "investment_framework_versions",
            "framework_id = 1 AND version = 1",
            id="version-created-at",
        ),
    ),
)
def test_malformed_persisted_datetime_uses_stable_data_error_without_mutation(
    database,
    table_name: str,
    row_filter: str,
) -> None:
    service = InvestmentFrameworkService(database)
    service.create(content=_content("Initial", "Initial risk rule"))
    with database._engine.begin() as connection:
        connection.exec_driver_sql(
            f"UPDATE {table_name} SET created_at = 'not-a-datetime' "
            f"WHERE {row_filter}"
        )
    before = _storage_snapshot(database)

    for operation in (
        service.get,
        service.list_history,
        InvestmentFrameworkContextReader(database).read,
        lambda: service.update(
            expected_revision=1,
            content=_content("Blocked update", "Blocked update risk rule"),
        ),
        lambda: service.deactivate(expected_revision=1),
        lambda: service.delete(expected_revision=1),
    ):
        with pytest.raises(InvestmentFrameworkDataError):
            operation()
        assert _storage_snapshot(database) == before


def test_deeply_nested_persisted_json_uses_stable_errors_without_mutation(
    database,
) -> None:
    service = InvestmentFrameworkService(database)
    repository = InvestmentFrameworkRepository(database)
    service.create(content=_content("Initial", "Initial risk rule"))
    deeply_nested_json = "[" * 2000 + "0" + "]" * 2000
    with database._engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE investment_framework_versions SET content_json = ?",
            (deeply_nested_json,),
        )
    before = _storage_snapshot(database)

    for operation in (
        service.get,
        service.list_history,
        InvestmentFrameworkContextReader(database).read,
        lambda: service.update(
            expected_revision=1,
            content=_content("Blocked update", "Blocked update risk rule"),
        ),
        lambda: service.deactivate(expected_revision=1),
        lambda: service.delete(expected_revision=1),
        lambda: service.create(
            content=_content("Blocked create", "Blocked create risk rule")
        ),
    ):
        with pytest.raises(InvestmentFrameworkDataError):
            operation()
        assert _storage_snapshot(database) == before

    for operation in (
        repository.get_current,
        repository.get_active,
        repository.list_history,
        lambda: repository.update(
            expected_revision=1,
            content_json="{}",
            change_summary=None,
        ),
        lambda: repository.deactivate(expected_revision=1),
        lambda: repository.delete(expected_revision=1),
        lambda: repository.create(content_json="{}", change_summary=None),
    ):
        with pytest.raises(InvestmentFrameworkRepositoryError):
            operation()
        assert _storage_snapshot(database) == before
