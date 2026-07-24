"""Service, history, concurrency, and context contracts for frameworks."""

import pytest

from src.config import Config
from src.schemas.investment_framework import InvestmentFrameworkContent
from src.services.investment_framework_context import InvestmentFrameworkContextReader
from src.services.investment_framework_service import (
    InvestmentFrameworkDataError,
    InvestmentFrameworkNotFoundError,
    InvestmentFrameworkRevisionConflictError,
    InvestmentFrameworkService,
)
from src.storage import DatabaseManager, InvestmentFrameworkVersionRecord


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
        row.content_json = "{}"
        session.commit()

    with pytest.raises(InvestmentFrameworkDataError):
        InvestmentFrameworkContextReader(database).read()
