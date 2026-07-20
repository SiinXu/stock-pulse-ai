"""Tests for the ApplicationServices composition root."""

import pytest

import src.config
import src.search_service
import src.services.task_queue as task_queue_mod
import src.storage
from src.application_services import (
    ApplicationServices,
    get_application_services,
    reset_application_services,
    set_application_services,
)


@pytest.fixture(autouse=True)
def _clean_root():
    """Guarantee no installed composition root leaks across tests."""
    reset_application_services()
    yield
    reset_application_services()


def _install_singleton_stubs(monkeypatch):
    """Replace each underlying accessor with a distinct sentinel object."""
    config_stub = object()
    db_stub = object()
    search_stub = object()
    queue_stub = object()
    monkeypatch.setattr(src.config.Config, "get_instance", staticmethod(lambda: config_stub))
    monkeypatch.setattr(
        src.storage.DatabaseManager, "get_instance", staticmethod(lambda: db_stub)
    )
    monkeypatch.setattr(src.search_service, "get_search_service", lambda: search_stub)
    monkeypatch.setattr(task_queue_mod, "get_task_queue", lambda: queue_stub)
    return config_stub, db_stub, search_stub, queue_stub


def test_default_root_delegates_to_underlying_singletons(monkeypatch):
    config_stub, db_stub, search_stub, queue_stub = _install_singleton_stubs(monkeypatch)
    services = ApplicationServices()
    assert services.config is config_stub
    assert services.database is db_stub
    assert services.search is search_stub
    assert services.task_queue is queue_stub


def test_injected_instances_are_returned(monkeypatch):
    _install_singleton_stubs(monkeypatch)
    injected_config = object()
    injected_db = object()
    injected_search = object()
    injected_queue = object()
    services = ApplicationServices(
        config=injected_config,
        database=injected_db,
        search=injected_search,
        task_queue=injected_queue,
    )
    assert services.config is injected_config
    assert services.database is injected_db
    assert services.search is injected_search
    assert services.task_queue is injected_queue


def test_partial_injection_falls_back_per_field(monkeypatch):
    _config, db_stub, search_stub, queue_stub = _install_singleton_stubs(monkeypatch)
    injected_config = object()
    services = ApplicationServices(config=injected_config)
    assert services.config is injected_config
    assert services.database is db_stub
    assert services.search is search_stub
    assert services.task_queue is queue_stub


def test_construction_is_lazy(monkeypatch):
    built = []
    monkeypatch.setattr(
        src.config.Config, "get_instance", staticmethod(lambda: built.append("config") or object())
    )
    monkeypatch.setattr(
        src.storage.DatabaseManager,
        "get_instance",
        staticmethod(lambda: built.append("db") or object()),
    )
    monkeypatch.setattr(
        src.search_service, "get_search_service", lambda: built.append("search") or object()
    )
    monkeypatch.setattr(
        task_queue_mod, "get_task_queue", lambda: built.append("queue") or object()
    )
    services = ApplicationServices()
    assert built == []
    _ = services.config
    assert built == ["config"]


def test_get_application_services_is_stable_until_reset():
    first = get_application_services()
    second = get_application_services()
    assert first is second
    reset_application_services()
    assert get_application_services() is not first


def test_set_and_reset_isolated_root(monkeypatch):
    config_stub, _db, _search, _queue = _install_singleton_stubs(monkeypatch)
    injected_config = object()
    isolated = ApplicationServices(config=injected_config)
    set_application_services(isolated)
    assert get_application_services() is isolated
    assert get_application_services().config is injected_config
    reset_application_services()
    assert get_application_services() is not isolated
    assert get_application_services().config is config_stub


def test_get_db_delegates_to_composition_root(monkeypatch):
    db_stub = object()
    monkeypatch.setattr(
        src.storage.DatabaseManager, "get_instance", staticmethod(lambda: db_stub)
    )
    from src.storage import get_db

    # get_db() routes through the composition root to the underlying singleton.
    assert get_db() is db_stub
    assert get_db() is get_application_services().database
    # Injecting an isolated DatabaseManager makes get_db() return it.
    injected_db = object()
    set_application_services(ApplicationServices(database=injected_db))
    assert get_db() is injected_db
    # Reset restores default delegation to the underlying singleton.
    reset_application_services()
    assert get_db() is db_stub


def test_startup_install_then_get_db(monkeypatch):
    # Mirrors what server.py / main.py do at the startup layer.
    db_stub = object()
    monkeypatch.setattr(
        src.storage.DatabaseManager, "get_instance", staticmethod(lambda: db_stub)
    )
    from src.storage import get_db

    set_application_services(ApplicationServices())
    assert get_db() is db_stub
