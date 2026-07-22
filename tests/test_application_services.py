"""Tests for the ApplicationServices composition root."""

import json
import threading
from pathlib import Path

import pytest

import src.config
import src.search_service
import src.services.task_queue as task_queue_mod
import src.storage
from src.application_services import (
    ApplicationServices,
    PLUGIN_APPLICATION_VERSION,
    get_application_services,
    reset_application_services,
    set_application_services,
)
from src.plugins import ExternalPluginLoader, Plugin, PluginContext, PluginManifest


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


def _plugin_manifest(plugin_id: str) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": "1.0.0",
            "description": f"Test plugin {plugin_id}",
            "author": "StockPulse tests",
            "permissions": [],
        }
    )


class _RecordingPlugin(Plugin):
    def __init__(
        self,
        plugin_id: str,
        events: list[str],
        *,
        fail_on_load: bool = False,
    ) -> None:
        super().__init__(_plugin_manifest(plugin_id))
        self._events = events
        self._fail_on_load = fail_on_load

    def onload(self, context: PluginContext) -> None:
        self._events.append(f"load:{self.manifest.id}")
        if self._fail_on_load:
            raise RuntimeError("test plugin load failure")

    def onunload(self) -> None:
        self._events.append(f"unload:{self.manifest.id}")


def _write_external_plugin(
    root: Path,
    directory_name: str,
    plugin_id: str,
    *,
    fail_on_load: bool = False,
) -> None:
    candidate = root / directory_name
    candidate.mkdir()
    (candidate / "manifest.json").write_text(
        json.dumps(
            {
                "id": plugin_id,
                "name": plugin_id,
                "version": "1.0.0",
                "minAppVersion": "1.0.0",
                "description": f"External test plugin {plugin_id}",
                "author": "StockPulse tests",
                "permissions": [],
                "entrypoint": "plugin.py:Plugin",
            }
        ),
        encoding="utf-8",
    )
    failure_line = "        raise RuntimeError('external load failure')\n" if fail_on_load else ""
    onload_body = failure_line or "        pass\n"
    (candidate / "plugin.py").write_text(
        "from src.plugins import Plugin as BasePlugin\n\n"
        "class Plugin(BasePlugin):\n"
        "    def onload(self, context):\n"
        f"{onload_body}",
        encoding="utf-8",
    )


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


def test_plugin_composition_registers_builtins_and_isolates_load_failure():
    events: list[str] = []
    failing = _RecordingPlugin("test.failing", events, fail_on_load=True)
    healthy = _RecordingPlugin("test.healthy", events)

    services = ApplicationServices(
        builtin_plugins=(failing, healthy),
        plugins_dir="",
    )
    services.start_plugins()

    assert PLUGIN_APPLICATION_VERSION == "3.26.3"
    assert [result.success for result in services.builtin_plugin_results] == [
        True,
        True,
    ]
    assert [result.success for result in services.plugin_load_results] == [
        False,
        True,
    ]
    assert services.plugin_manager.snapshot("test.failing").state == "failed"
    assert services.plugin_manager.snapshot("test.healthy").state == "enabled"
    assert events == ["load:test.failing", "load:test.healthy"]

    services.close()
    assert services.plugin_manager.snapshot("test.failing").state == "disabled"
    assert services.plugin_manager.snapshot("test.healthy").state == "disabled"
    assert events == [
        "load:test.failing",
        "load:test.healthy",
        "unload:test.healthy",
    ]


def test_blank_plugins_dir_does_not_invoke_external_loader(monkeypatch):
    monkeypatch.delenv("PLUGINS_DIR", raising=False)

    def fail_if_called(_loader, _plugins_dir):
        raise AssertionError("external loader must remain opt-in")

    monkeypatch.setattr(
        ExternalPluginLoader,
        "register_from_directory",
        fail_if_called,
    )

    services = ApplicationServices()
    services.start_plugins()
    assert services.external_plugin_results == ()
    services.close()


def test_plugins_dir_registers_and_loads_external_plugins_in_order(
    tmp_path,
    monkeypatch,
):
    _write_external_plugin(
        tmp_path,
        "01-failing",
        "external.failing",
        fail_on_load=True,
    )
    _write_external_plugin(tmp_path, "02-healthy", "external.healthy")
    monkeypatch.setenv("PLUGINS_DIR", str(tmp_path))

    services = ApplicationServices()
    services.start_plugins()

    assert [result.plugin_id for result in services.external_plugin_results] == [
        "external.failing",
        "external.healthy",
    ]
    assert [result.success for result in services.external_plugin_results] == [
        True,
        True,
    ]
    assert [result.plugin_id for result in services.plugin_load_results] == [
        "external.failing",
        "external.healthy",
    ]
    assert [result.success for result in services.plugin_load_results] == [
        False,
        True,
    ]
    assert services.plugin_manager.snapshot("external.failing").state == "failed"
    assert services.plugin_manager.snapshot("external.healthy").state == "enabled"
    services.close()


def test_explicit_blank_plugins_dir_overrides_environment(tmp_path, monkeypatch):
    _write_external_plugin(tmp_path, "external", "external.disabled")
    monkeypatch.setenv("PLUGINS_DIR", str(tmp_path))

    services = ApplicationServices(plugins_dir="")
    services.start_plugins()

    assert services.external_plugin_results == ()
    assert services.plugin_manager.plugin_ids() == ()
    services.close()


def test_replacing_composition_root_unloads_previous_plugins():
    events: list[str] = []
    plugin = _RecordingPlugin("test.replaced", events)
    first = ApplicationServices(builtin_plugins=(plugin,), plugins_dir="")
    second = ApplicationServices(plugins_dir="")

    set_application_services(first)
    set_application_services(second)

    assert events == ["load:test.replaced", "unload:test.replaced"]
    assert first.plugin_manager.snapshot("test.replaced").state == "disabled"
    assert first.close() == first.plugin_shutdown_results


def test_close_requested_during_plugin_start_converges_to_disabled():
    events: list[str] = []
    services_holder: list[ApplicationServices] = []

    class _ClosingPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            super().onload(context)
            services_holder[0].close()

    plugin = _ClosingPlugin("test.self-closing", events)
    services = ApplicationServices(builtin_plugins=(plugin,), plugins_dir="")
    services_holder.append(services)

    services.start_plugins()

    assert services.plugin_load_results[0].success is True
    assert services.plugin_shutdown_results[0].success is True
    assert services.plugin_manager.snapshot("test.self-closing").state == "disabled"
    assert events == ["load:test.self-closing", "unload:test.self-closing"]


def test_plugin_load_can_resolve_the_already_installed_root():
    observed_roots: list[ApplicationServices] = []

    class _RootAwarePlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            super().onload(context)
            observed_roots.append(get_application_services())

    events: list[str] = []
    plugin = _RootAwarePlugin("test.root-aware", events)
    services = ApplicationServices(builtin_plugins=(plugin,), plugins_dir="")

    set_application_services(services)

    assert observed_roots == [services]
    assert events == ["load:test.root-aware"]


def test_reset_does_not_recreate_root_from_unload_lookup():
    observed_roots: list[ApplicationServices] = []
    events: list[str] = []

    class _UnloadLookupPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("unload-begin")
            observed_roots.append(get_application_services())
            events.append("unload-end")

    services = ApplicationServices(
        builtin_plugins=(_UnloadLookupPlugin("test.reset-lookup", events),),
        plugins_dir="",
    )
    set_application_services(services)

    reset_application_services()

    assert observed_roots == [services]
    assert events == ["load:test.reset-lookup", "unload-begin", "unload-end"]
    assert get_application_services() is not services


def test_replacement_finishes_old_unload_before_new_root_load():
    observed_roots: list[ApplicationServices] = []
    events: list[str] = []

    class _UnloadLookupPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("old-unload-begin")
            observed_roots.append(get_application_services())
            events.append("old-unload-end")

    first = ApplicationServices(
        builtin_plugins=(_UnloadLookupPlugin("test.old", events),),
        plugins_dir="",
    )
    second = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.new", events),),
        plugins_dir="",
    )

    set_application_services(first)
    set_application_services(second)

    assert observed_roots == [first]
    assert events == [
        "load:test.old",
        "old-unload-begin",
        "old-unload-end",
        "load:test.new",
    ]


def test_concurrent_get_during_replacement_keeps_old_root_until_unload_finishes():
    unload_started = threading.Event()
    release_unload = threading.Event()
    observed_roots: list[ApplicationServices] = []
    events: list[str] = []

    class _BlockingUnloadPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("old-unload-begin")
            unload_started.set()
            if not release_unload.wait(timeout=5):
                raise AssertionError("test did not release the unload callback")
            events.append("old-unload-end")

    first = ApplicationServices(
        builtin_plugins=(_BlockingUnloadPlugin("test.old", events),),
        plugins_dir="",
    )
    second = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.new", events),),
        plugins_dir="",
    )
    set_application_services(first)

    replacement = threading.Thread(
        target=set_application_services,
        args=(second,),
    )
    lookup = threading.Thread(
        target=lambda: observed_roots.append(get_application_services()),
    )
    replacement.start()
    assert unload_started.wait(timeout=5)

    try:
        lookup.start()
        lookup.join(timeout=5)
        assert not lookup.is_alive()
        assert observed_roots == [first]
        assert "load:test.new" not in events
    finally:
        release_unload.set()
        replacement.join(timeout=5)
        lookup.join(timeout=5)

    assert not replacement.is_alive()
    assert not lookup.is_alive()
    assert events == [
        "load:test.old",
        "old-unload-begin",
        "old-unload-end",
        "load:test.new",
    ]


def test_reentrant_replacement_is_deferred_until_old_unload_finishes():
    events: list[str] = []
    final_root_holder: list[ApplicationServices] = []

    class _ReplacingUnloadPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("old-unload-begin")
            set_application_services(final_root_holder[0])
            events.append("old-unload-end")

    first = ApplicationServices(
        builtin_plugins=(_ReplacingUnloadPlugin("test.old", events),),
        plugins_dir="",
    )
    superseded = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.superseded", events),),
        plugins_dir="",
    )
    final = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.final", events),),
        plugins_dir="",
    )
    final_root_holder.append(final)

    set_application_services(first)
    set_application_services(superseded)

    assert get_application_services() is final
    assert superseded.plugin_manager.plugin_ids() == ()
    assert events == [
        "load:test.old",
        "old-unload-begin",
        "old-unload-end",
        "load:test.final",
    ]
