"""Tests for the ApplicationServices composition root."""

import json
import subprocess
import sys
import textwrap
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


def test_concurrent_replacement_request_does_not_deadlock_unload_callback():
    events: list[str] = []
    final_root_holder: list[ApplicationServices] = []
    worker_returned = threading.Event()
    workers: list[threading.Thread] = []

    class _WorkerReplacingUnloadPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("old-unload-begin")

            def request_final_root() -> None:
                set_application_services(final_root_holder[0])
                worker_returned.set()

            worker = threading.Thread(target=request_final_root)
            workers.append(worker)
            worker.start()
            if not worker_returned.wait(timeout=5):
                raise AssertionError("replacement worker deadlocked during unload")
            worker.join(timeout=5)
            events.append("old-unload-end")

    first = ApplicationServices(
        builtin_plugins=(_WorkerReplacingUnloadPlugin("test.old", events),),
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

    assert worker_returned.is_set()
    assert all(not worker.is_alive() for worker in workers)
    assert get_application_services() is final
    assert superseded.plugin_manager.plugin_ids() == ()
    assert events == [
        "load:test.old",
        "old-unload-begin",
        "old-unload-end",
        "load:test.final",
    ]


def test_concurrent_replacement_request_does_not_deadlock_load_callback():
    events: list[str] = []
    final_root_holder: list[ApplicationServices] = []
    worker_returned = threading.Event()
    workers: list[threading.Thread] = []

    class _WorkerReplacingLoadPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("intermediate-load-begin")

            def request_final_root() -> None:
                set_application_services(final_root_holder[0])
                worker_returned.set()

            worker = threading.Thread(target=request_final_root)
            workers.append(worker)
            worker.start()
            if not worker_returned.wait(timeout=5):
                raise AssertionError("replacement worker deadlocked during load")
            worker.join(timeout=5)
            events.append("intermediate-load-end")

    intermediate = ApplicationServices(
        builtin_plugins=(_WorkerReplacingLoadPlugin("test.intermediate", events),),
        plugins_dir="",
    )
    final = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.final", events),),
        plugins_dir="",
    )
    final_root_holder.append(final)

    set_application_services(intermediate)

    assert worker_returned.is_set()
    assert all(not worker.is_alive() for worker in workers)
    assert get_application_services() is final
    assert events == [
        "intermediate-load-begin",
        "intermediate-load-end",
        "unload:test.intermediate",
        "load:test.final",
    ]


def test_latest_reentrant_request_can_retain_the_current_root():
    events: list[str] = []
    current_root_holder: list[ApplicationServices] = []
    superseded_root = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.superseded", events),),
        plugins_dir="",
    )

    class _RetainingLoadPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("current-load-begin")
            set_application_services(superseded_root)
            set_application_services(current_root_holder[0])
            events.append("current-load-end")

    current_root = ApplicationServices(
        builtin_plugins=(_RetainingLoadPlugin("test.current", events),),
        plugins_dir="",
    )
    current_root_holder.append(current_root)

    set_application_services(current_root)

    assert get_application_services() is current_root
    assert superseded_root.plugin_manager.plugin_ids() == ()
    assert current_root.plugin_manager.snapshot("test.current").state == "enabled"
    assert events == ["current-load-begin", "current-load-end"]


def test_terminal_atexit_shutdown_blocks_late_root_recreation():
    script = textwrap.dedent(
        """
        import atexit
        import os

        os.environ.pop("PLUGINS_DIR", None)

        def late_callback():
            from src.application_services import get_application_services

            try:
                get_application_services()
            except RuntimeError:
                print("LATE_ROOT_BLOCKED")
            else:
                print("LATE_ROOT_RECREATED")

        atexit.register(late_callback)

        from src.application_services import get_application_services

        get_application_services()
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "LATE_ROOT_BLOCKED" in result.stdout
    assert "LATE_ROOT_RECREATED" not in result.stdout


def test_unload_request_cannot_republish_the_closing_root():
    events: list[str] = []
    old_root_holder: list[ApplicationServices] = []

    class _RetainingUnloadPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("old-unload-begin")
            set_application_services(old_root_holder[0])
            events.append("old-unload-end")

    old_root = ApplicationServices(
        builtin_plugins=(_RetainingUnloadPlugin("test.old", events),),
        plugins_dir="",
    )
    new_root = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.new", events),),
        plugins_dir="",
    )
    old_root_holder.append(old_root)

    set_application_services(old_root)
    set_application_services(new_root)

    assert old_root.is_closed is True
    assert get_application_services() is new_root
    assert events == [
        "load:test.old",
        "old-unload-begin",
        "old-unload-end",
        "load:test.new",
    ]


def test_latest_installable_unload_request_wins_after_closing_root_request():
    events: list[str] = []
    roots: dict[str, ApplicationServices] = {}

    class _MultipleRequestUnloadPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("old-unload-begin")
            set_application_services(roots["final"])
            set_application_services(roots["old"])
            events.append("old-unload-end")

    roots["old"] = ApplicationServices(
        builtin_plugins=(_MultipleRequestUnloadPlugin("test.old", events),),
        plugins_dir="",
    )
    superseded = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.superseded", events),),
        plugins_dir="",
    )
    roots["final"] = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.final", events),),
        plugins_dir="",
    )

    set_application_services(roots["old"])
    set_application_services(superseded)

    assert get_application_services() is roots["final"]
    assert superseded.plugin_manager.plugin_ids() == ()
    assert events == [
        "load:test.old",
        "old-unload-begin",
        "old-unload-end",
        "load:test.final",
    ]


def test_closed_root_cannot_be_installed_again():
    services = ApplicationServices(plugins_dir="")
    set_application_services(services)
    reset_application_services()

    assert services.is_closed is True
    with pytest.raises(RuntimeError, match="Cannot install closed"):
        set_application_services(services)


def test_plugin_manager_cannot_be_shared_between_application_roots():
    first = ApplicationServices(plugins_dir="")

    with pytest.raises(RuntimeError, match="already belongs"):
        ApplicationServices(
            plugin_manager=first.plugin_manager,
            plugins_dir="",
        )


def test_closed_root_manager_rejects_activation_but_allows_disable():
    events: list[str] = []
    services = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.closed-owner", events),),
        plugins_dir="",
    )
    set_application_services(services)
    services.close()
    late_plugin = _RecordingPlugin("test.late", events)
    assert services.plugin_manager.register(late_plugin, source="builtin").success

    enable_result = services.plugin_manager.enable("test.closed-owner")
    load_result = services.plugin_manager.load("test.late")
    load_all_results = services.plugin_manager.load_all()
    disable_result = services.plugin_manager.disable("test.closed-owner")

    assert enable_result.success is False
    assert enable_result.error_code == "plugin_owner_closed"
    assert load_result.success is False
    assert load_result.error_code == "plugin_owner_closed"
    assert [result.error_code for result in load_all_results] == [
        "plugin_owner_closed",
        "plugin_owner_closed",
    ]
    assert disable_result.success is True
    assert services.plugin_manager.snapshot("test.closed-owner").state == "disabled"
    assert services.plugin_manager.snapshot("test.late").state == "registered"
    assert events == ["load:test.closed-owner", "unload:test.closed-owner"]


def test_local_root_close_disables_plugin_loaded_directly_through_manager():
    events: list[str] = []
    services = ApplicationServices(plugins_dir="")
    plugin = _RecordingPlugin("test.local-direct", events)
    assert services.plugin_manager.register(plugin, source="builtin").success
    assert services.plugin_manager.load("test.local-direct").success

    results = services.close()

    assert [result.success for result in results] == [True]
    assert services.is_closed is True
    assert services.plugin_manager.snapshot("test.local-direct").state == "disabled"
    assert events == ["load:test.local-direct", "unload:test.local-direct"]


def test_local_manager_callback_worker_can_defer_root_close_without_deadlock():
    events: list[str] = []
    root_holder: list[ApplicationServices] = []
    worker_returned = threading.Event()
    workers: list[threading.Thread] = []

    class _WorkerClosingLoadPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("local-load-begin")

            def close_root() -> None:
                root_holder[0].close()
                worker_returned.set()

            worker = threading.Thread(target=close_root)
            workers.append(worker)
            worker.start()
            if not worker_returned.wait(timeout=5):
                raise AssertionError("local manager close worker deadlocked")
            worker.join(timeout=5)
            events.append("local-load-end")

    services = ApplicationServices(plugins_dir="")
    root_holder.append(services)
    plugin = _WorkerClosingLoadPlugin("test.local-worker-close", events)
    assert services.plugin_manager.register(plugin, source="builtin").success

    result = services.plugin_manager.load("test.local-worker-close")

    assert result.success is True
    assert worker_returned.is_set()
    assert all(not worker.is_alive() for worker in workers)
    assert services.is_closed is True
    assert services.plugin_manager.snapshot("test.local-worker-close").state == "disabled"
    assert events == [
        "local-load-begin",
        "local-load-end",
        "unload:test.local-worker-close",
    ]


def test_local_close_request_rejects_queued_plugin_activation():
    events: list[str] = []
    root_holder: list[ApplicationServices] = []
    close_requested = threading.Event()
    release_first_load = threading.Event()
    first_results: list = []
    late_results: list = []

    class _ClosingLoadPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("first-load-begin")
            root_holder[0].close()
            close_requested.set()
            if not release_first_load.wait(timeout=5):
                raise AssertionError("test did not release the first local load")
            events.append("first-load-end")

    services = ApplicationServices(plugins_dir="")
    root_holder.append(services)
    assert services.plugin_manager.register(
        _ClosingLoadPlugin("test.first", events),
        source="builtin",
    ).success
    assert services.plugin_manager.register(
        _RecordingPlugin("test.late", events),
        source="builtin",
    ).success

    first_load = threading.Thread(
        target=lambda: first_results.append(
            services.plugin_manager.load("test.first")
        ),
    )
    first_load.start()
    assert close_requested.wait(timeout=5)
    late_load = threading.Thread(
        target=lambda: late_results.append(
            services.plugin_manager.load("test.late")
        ),
    )
    late_load.start()
    try:
        for _ in range(500):
            if services._local_lifecycle_ops == 2:
                break
            late_load.join(timeout=0.01)
        assert services._local_lifecycle_ops == 2
    finally:
        release_first_load.set()
        first_load.join(timeout=5)
        late_load.join(timeout=5)

    assert not first_load.is_alive()
    assert not late_load.is_alive()
    assert first_results and first_results[0].success is True
    assert late_results and late_results[0].success is False
    assert late_results[0].error_code == "plugin_owner_closed"
    assert services.is_closed is True
    assert services.plugin_manager.snapshot("test.first").state == "disabled"
    assert services.plugin_manager.snapshot("test.late").state == "registered"
    assert events == [
        "first-load-begin",
        "first-load-end",
        "unload:test.first",
    ]


def test_installer_drain_stays_active_through_deferred_local_cleanup():
    events: list[str] = []
    root_holder: list[ApplicationServices] = []
    load_callback_ready = threading.Event()
    release_load_callback = threading.Event()
    unload_started = threading.Event()
    release_unload = threading.Event()
    load_results: list = []

    class _DeferredClosePlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("local-load-begin")
            root_holder[0].close()
            load_callback_ready.set()
            if not release_load_callback.wait(timeout=5):
                raise AssertionError("test did not release the local load callback")
            events.append("local-load-end")

        def onunload(self) -> None:
            events.append("local-unload-begin")
            unload_started.set()
            if not release_unload.wait(timeout=5):
                raise AssertionError("test did not release the deferred unload")
            events.append("local-unload-end")

    services = ApplicationServices(plugins_dir="")
    root_holder.append(services)
    plugin = _DeferredClosePlugin("test.deferred-local-close", events)
    assert services.plugin_manager.register(plugin, source="builtin").success
    local_load = threading.Thread(
        target=lambda: load_results.append(
            services.plugin_manager.load("test.deferred-local-close")
        ),
    )
    local_load.start()
    assert load_callback_ready.wait(timeout=5)

    installer = threading.Thread(target=lambda: set_application_services(services))
    installer.start()
    installer.join(timeout=0.5)
    assert installer.is_alive()
    release_load_callback.set()
    assert unload_started.wait(timeout=5)

    unrelated_root = ApplicationServices(plugins_dir="")
    unrelated_root.plugin_manager.load("missing")
    installer.join(timeout=0.5)
    assert installer.is_alive()

    release_unload.set()
    local_load.join(timeout=5)
    installer.join(timeout=5)
    assert not local_load.is_alive()
    assert not installer.is_alive()
    successor = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.successor", events),),
        plugins_dir="",
    )
    set_application_services(successor)

    assert load_results and load_results[0].success is True
    assert services.is_closed is True
    assert services.plugin_manager.snapshot("test.deferred-local-close").state == "disabled"
    assert events == [
        "local-load-begin",
        "local-load-end",
        "local-unload-begin",
        "local-unload-end",
        "load:test.successor",
    ]


def test_get_replaces_a_directly_closed_installed_root():
    services = ApplicationServices(plugins_dir="")
    set_application_services(services)
    services.close()

    replacement = get_application_services()

    assert services.is_closed is True
    assert replacement is not services
    assert replacement.is_closed is False


def test_direct_close_keeps_installed_root_visible_during_unload():
    observed_roots: list[ApplicationServices] = []
    events: list[str] = []

    class _UnloadLookupPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("unload-begin")
            observed_roots.append(get_application_services())
            events.append("unload-end")

    services = ApplicationServices(
        builtin_plugins=(_UnloadLookupPlugin("test.direct-close", events),),
        plugins_dir="",
    )
    set_application_services(services)

    services.close()

    assert observed_roots == [services]
    assert events == ["load:test.direct-close", "unload-begin", "unload-end"]
    assert get_application_services() is not services


def test_direct_close_defers_reentrant_replacement_until_reverse_unload_finishes():
    events: list[str] = []
    replacement_holder: list[ApplicationServices] = []

    class _ReplacingUnloadPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("replacer-unload-begin")
            set_application_services(replacement_holder[0])
            events.append("replacer-unload-end")

    services = ApplicationServices(
        builtin_plugins=(
            _RecordingPlugin("test.first", events),
            _ReplacingUnloadPlugin("test.replacer", events),
        ),
        plugins_dir="",
    )
    replacement = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.new", events),),
        plugins_dir="",
    )
    replacement_holder.append(replacement)
    set_application_services(services)

    services.close()

    assert get_application_services() is replacement
    assert events == [
        "load:test.first",
        "load:test.replacer",
        "replacer-unload-begin",
        "replacer-unload-end",
        "unload:test.first",
        "load:test.new",
    ]


def test_direct_close_callback_worker_can_lookup_and_replace_without_deadlock():
    events: list[str] = []
    observed_roots: list[ApplicationServices] = []
    replacement_holder: list[ApplicationServices] = []
    worker_returned = threading.Event()
    workers: list[threading.Thread] = []

    class _WorkerReplacingUnloadPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("replacer-unload-begin")

            def request_replacement() -> None:
                observed_roots.append(get_application_services())
                set_application_services(replacement_holder[0])
                worker_returned.set()

            worker = threading.Thread(target=request_replacement)
            workers.append(worker)
            worker.start()
            if not worker_returned.wait(timeout=5):
                raise AssertionError("replacement worker deadlocked during direct close")
            worker.join(timeout=5)
            events.append("replacer-unload-end")

    services = ApplicationServices(
        builtin_plugins=(
            _RecordingPlugin("test.first", events),
            _WorkerReplacingUnloadPlugin("test.replacer", events),
        ),
        plugins_dir="",
    )
    replacement = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.new", events),),
        plugins_dir="",
    )
    replacement_holder.append(replacement)
    set_application_services(services)

    services.close()

    assert worker_returned.is_set()
    assert all(not worker.is_alive() for worker in workers)
    assert observed_roots == [services]
    assert get_application_services() is replacement
    assert events == [
        "load:test.first",
        "load:test.replacer",
        "replacer-unload-begin",
        "replacer-unload-end",
        "unload:test.first",
        "load:test.new",
    ]


def test_load_callback_worker_can_close_installed_root_without_deadlock():
    events: list[str] = []
    root_holder: list[ApplicationServices] = []
    worker_returned = threading.Event()
    workers: list[threading.Thread] = []

    class _WorkerClosingLoadPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("load-begin")

            def close_root() -> None:
                root_holder[0].close()
                worker_returned.set()

            worker = threading.Thread(target=close_root)
            workers.append(worker)
            worker.start()
            if not worker_returned.wait(timeout=5):
                raise AssertionError("close worker deadlocked during load")
            worker.join(timeout=5)
            events.append("load-end")

    services = ApplicationServices(
        builtin_plugins=(_WorkerClosingLoadPlugin("test.worker-close", events),),
        plugins_dir="",
    )
    root_holder.append(services)

    set_application_services(services)

    assert worker_returned.is_set()
    assert all(not worker.is_alive() for worker in workers)
    assert services.is_closed is True
    assert get_application_services() is not services
    assert events == ["load-begin", "load-end", "unload:test.worker-close"]


def test_unload_callback_worker_can_close_installed_root_without_deadlock():
    events: list[str] = []
    root_holder: list[ApplicationServices] = []
    worker_returned = threading.Event()
    workers: list[threading.Thread] = []

    class _WorkerClosingUnloadPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("unload-begin")

            def close_root() -> None:
                root_holder[0].close()
                worker_returned.set()

            worker = threading.Thread(target=close_root)
            workers.append(worker)
            worker.start()
            if not worker_returned.wait(timeout=5):
                raise AssertionError("close worker deadlocked during unload")
            worker.join(timeout=5)
            events.append("unload-end")

    services = ApplicationServices(
        builtin_plugins=(
            _WorkerClosingUnloadPlugin("test.worker-close", events),
        ),
        plugins_dir="",
    )
    root_holder.append(services)
    set_application_services(services)

    services.close()

    assert worker_returned.is_set()
    assert all(not worker.is_alive() for worker in workers)
    assert services.is_closed is True
    assert get_application_services() is not services
    assert events == ["load:test.worker-close", "unload-begin", "unload-end"]


def test_overlapping_direct_close_returns_current_snapshot_without_waiting():
    events: list[str] = []
    unload_started = threading.Event()
    release_unload = threading.Event()
    first_results: list[tuple] = []

    class _BlockingUnloadPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("unload-begin")
            unload_started.set()
            if not release_unload.wait(timeout=5):
                raise AssertionError("test did not release direct close")
            events.append("unload-end")

    services = ApplicationServices(
        builtin_plugins=(_BlockingUnloadPlugin("test.blocking-close", events),),
        plugins_dir="",
    )
    set_application_services(services)
    first_close = threading.Thread(
        target=lambda: first_results.append(services.close()),
    )
    first_close.start()
    assert unload_started.wait(timeout=5)

    try:
        queued_result = services.close()
        assert queued_result == ()
        assert services.plugin_shutdown_results == ()
        assert first_close.is_alive()
    finally:
        release_unload.set()
        first_close.join(timeout=5)

    assert not first_close.is_alive()
    assert first_results == [services.plugin_shutdown_results]
    assert [result.success for result in first_results[0]] == [True]
    assert events == [
        "load:test.blocking-close",
        "unload-begin",
        "unload-end",
    ]


def test_root_closed_during_plugin_start_is_not_left_installed():
    events: list[str] = []
    root_holder: list[ApplicationServices] = []

    class _ClosingLoadPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("load-begin")
            root_holder[0].close()
            events.append("load-end")

    services = ApplicationServices(
        builtin_plugins=(_ClosingLoadPlugin("test.closing", events),),
        plugins_dir="",
    )
    root_holder.append(services)

    set_application_services(services)
    replacement = get_application_services()

    assert services.is_closed is True
    assert replacement is not services
    assert events == ["load-begin", "load-end", "unload:test.closing"]


def test_close_request_cannot_be_superseded_by_reinstalling_the_same_root():
    events: list[str] = []
    root_holder: list[ApplicationServices] = []

    class _ClosingAndRetainingLoadPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("closing-load-begin")
            root_holder[0].close()
            set_application_services(root_holder[0])
            events.append("closing-load-end")

    services = ApplicationServices(
        builtin_plugins=(
            _ClosingAndRetainingLoadPlugin("test.closing", events),
            _RecordingPlugin("test.late", events),
        ),
        plugins_dir="",
    )
    root_holder.append(services)

    set_application_services(services)
    replacement = get_application_services()

    assert services.is_closed is True
    assert replacement is not services
    assert [result.error_code for result in services.plugin_load_results] == [
        None,
        "plugin_owner_closed",
    ]
    assert services.plugin_manager.snapshot("test.closing").state == "disabled"
    assert services.plugin_manager.snapshot("test.late").state == "registered"
    assert events == [
        "closing-load-begin",
        "closing-load-end",
        "unload:test.closing",
    ]


def test_local_root_load_callback_worker_can_resolve_root_without_deadlock():
    events: list[str] = []
    worker_returned = threading.Event()
    workers: list[threading.Thread] = []
    observed_roots: list[ApplicationServices] = []

    class _WorkerResolvingLoadPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("local-load-begin")

            def resolve_root() -> None:
                observed_roots.append(get_application_services())
                worker_returned.set()

            worker = threading.Thread(target=resolve_root)
            workers.append(worker)
            worker.start()
            if not worker_returned.wait(timeout=5):
                raise AssertionError("lookup worker deadlocked during local load")
            worker.join(timeout=5)
            events.append("local-load-end")

    services = ApplicationServices(
        builtin_plugins=(
            _WorkerResolvingLoadPlugin("test.local-worker", events),
        ),
        plugins_dir="",
    )

    results = services.start_plugins()

    assert worker_returned.is_set()
    assert all(not worker.is_alive() for worker in workers)
    assert [result.success for result in results] == [True]
    assert observed_roots and observed_roots[0] is not services
    assert events == ["local-load-begin", "local-load-end"]


def test_public_manager_load_defers_callback_requested_replacement():
    events: list[str] = []
    replacement_holder: list[ApplicationServices] = []
    observed_roots: list[ApplicationServices] = []

    class _ReplacingLoadPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("late-load-begin")
            set_application_services(replacement_holder[0])
            observed_roots.append(get_application_services())
            events.append("late-load-end")

    services = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.first", events),),
        plugins_dir="",
    )
    replacement = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.new", events),),
        plugins_dir="",
    )
    replacement_holder.append(replacement)
    set_application_services(services)

    register_result = services.plugin_manager.register(
        _ReplacingLoadPlugin("test.late", events),
        source="builtin",
    )
    assert register_result.success is True

    load_result = services.plugin_manager.load("test.late")

    assert load_result.success is True
    assert observed_roots == [services]
    assert services.is_closed is True
    assert get_application_services() is replacement
    assert events == [
        "load:test.first",
        "late-load-begin",
        "late-load-end",
        "unload:test.late",
        "unload:test.first",
        "load:test.new",
    ]


def test_public_manager_disable_defers_callback_requested_replacement():
    events: list[str] = []
    observed_roots: list[ApplicationServices] = []
    replacement_holder: list[ApplicationServices] = []

    class _ReplacingUnloadPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("replacer-unload-begin")
            set_application_services(replacement_holder[0])
            observed_roots.append(get_application_services())
            events.append("replacer-unload-end")

    services = ApplicationServices(
        builtin_plugins=(
            _RecordingPlugin("test.first", events),
            _ReplacingUnloadPlugin("test.replacer", events),
        ),
        plugins_dir="",
    )
    replacement = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.new", events),),
        plugins_dir="",
    )
    replacement_holder.append(replacement)
    set_application_services(services)

    result = services.plugin_manager.disable("test.replacer")

    assert result.success is True
    assert observed_roots == [services]
    assert services.is_closed is True
    assert get_application_services() is replacement
    assert events == [
        "load:test.first",
        "load:test.replacer",
        "replacer-unload-begin",
        "replacer-unload-end",
        "unload:test.first",
        "load:test.new",
    ]


def test_public_manager_enable_defers_callback_requested_replacement():
    events: list[str] = []
    observed_roots: list[ApplicationServices] = []
    replacement_holder: list[ApplicationServices] = []

    class _ReplacingEnablePlugin(_RecordingPlugin):
        def __init__(self, plugin_id: str, plugin_events: list[str]) -> None:
            super().__init__(plugin_id, plugin_events)
            self.replace_on_load = False

        def onload(self, context: PluginContext) -> None:
            if not self.replace_on_load:
                events.append("initial-load")
                return
            events.append("enable-begin")
            set_application_services(replacement_holder[0])
            observed_roots.append(get_application_services())
            events.append("enable-end")

    plugin = _ReplacingEnablePlugin("test.reenabled", events)
    services = ApplicationServices(
        builtin_plugins=(
            _RecordingPlugin("test.first", events),
            plugin,
        ),
        plugins_dir="",
    )
    replacement = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.new", events),),
        plugins_dir="",
    )
    replacement_holder.append(replacement)
    set_application_services(services)
    assert services.plugin_manager.disable("test.reenabled").success is True
    events.clear()
    plugin.replace_on_load = True

    result = services.plugin_manager.enable("test.reenabled")

    assert result.success is True
    assert observed_roots == [services]
    assert services.is_closed is True
    assert services.plugin_manager.snapshot("test.reenabled").state == "disabled"
    assert get_application_services() is replacement
    assert events == [
        "enable-begin",
        "enable-end",
        "unload:test.reenabled",
        "unload:test.first",
        "load:test.new",
    ]


def test_installer_waits_for_in_flight_local_lifecycle_operation():
    events: list[str] = []
    load_started = threading.Event()
    release_load = threading.Event()
    start_results: list[tuple] = []

    class _BlockingLoadPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("local-load-begin")
            load_started.set()
            if not release_load.wait(timeout=5):
                raise AssertionError("test did not release the local load")
            events.append("local-load-end")

    services = ApplicationServices(
        builtin_plugins=(_BlockingLoadPlugin("test.blocking-local", events),),
        plugins_dir="",
    )
    local_start = threading.Thread(
        target=lambda: start_results.append(services.start_plugins()),
    )
    local_start.start()
    assert load_started.wait(timeout=5)

    installer = threading.Thread(
        target=lambda: set_application_services(services),
    )
    installer.start()
    try:
        installer.join(timeout=0.5)
        assert installer.is_alive()
        events.append("release-local-load")
    finally:
        release_load.set()
        local_start.join(timeout=5)
        installer.join(timeout=5)

    assert not local_start.is_alive()
    assert not installer.is_alive()
    assert get_application_services() is services
    assert [result.success for result in start_results[0]] == [True]
    assert events == [
        "local-load-begin",
        "release-local-load",
        "local-load-end",
    ]


def test_local_root_close_during_installer_drain_does_not_deadlock():
    events: list[str] = []
    load_started = threading.Event()
    release_load = threading.Event()
    side_close_results: list[tuple] = []

    class _SideClosingPlugin(_RecordingPlugin):
        def onload(self, context: PluginContext) -> None:
            events.append("local-load-begin")
            load_started.set()
            if not release_load.wait(timeout=5):
                raise AssertionError("test did not release the local load")
            side_close_results.append(side_root.close())
            events.append("local-load-end")

    side_root = ApplicationServices(
        builtin_plugins=(_RecordingPlugin("test.side", events),),
        plugins_dir="",
    )
    side_root.start_plugins()

    services = ApplicationServices(
        builtin_plugins=(_SideClosingPlugin("test.blocking-local", events),),
        plugins_dir="",
    )
    local_start = threading.Thread(target=services.start_plugins)
    local_start.start()
    assert load_started.wait(timeout=5)

    installer = threading.Thread(
        target=lambda: set_application_services(services),
    )
    installer.start()
    try:
        installer.join(timeout=0.5)
        assert installer.is_alive()
    finally:
        release_load.set()
        local_start.join(timeout=5)
        installer.join(timeout=5)

    assert not local_start.is_alive()
    assert not installer.is_alive()
    assert side_root.is_closed is True
    assert get_application_services() is services
    assert [result.success for result in side_close_results[0]] == [True]
    assert events == [
        "load:test.side",
        "local-load-begin",
        "unload:test.side",
        "local-load-end",
    ]


def test_local_close_rechecks_boundary_after_concurrent_install(monkeypatch):
    events: list[str] = []
    observed_roots: list[ApplicationServices] = []
    close_ready = threading.Event()
    release_close = threading.Event()
    close_results: list[tuple] = []

    class _LookupUnloadPlugin(_RecordingPlugin):
        def onunload(self) -> None:
            events.append("local-unload-begin")
            observed_roots.append(get_application_services())
            events.append("local-unload-end")

    services = ApplicationServices(
        builtin_plugins=(
            _LookupUnloadPlugin("test.concurrent-local-close", events),
        ),
        plugins_dir="",
    )
    services.start_plugins()
    original_close_plugins = services._close_plugins

    def delayed_close_plugins():
        close_ready.set()
        if not release_close.wait(timeout=5):
            raise AssertionError("test did not release the local close")
        return original_close_plugins()

    monkeypatch.setattr(services, "_close_plugins", delayed_close_plugins)
    local_close = threading.Thread(
        target=lambda: close_results.append(services.close()),
    )
    local_close.start()
    assert close_ready.wait(timeout=5)

    installer = threading.Thread(
        target=lambda: set_application_services(services),
    )
    installer.start()
    try:
        installer.join(timeout=5)
        assert not installer.is_alive()
        assert get_application_services() is services
    finally:
        release_close.set()
        local_close.join(timeout=5)
        installer.join(timeout=5)

    assert not local_close.is_alive()
    assert not installer.is_alive()
    assert services.is_closed is True
    assert observed_roots == [services]
    assert get_application_services() is not services
    assert [result.success for result in close_results[0]] == [True]
    assert events == [
        "load:test.concurrent-local-close",
        "local-unload-begin",
        "local-unload-end",
    ]
