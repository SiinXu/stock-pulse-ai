from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from src.model_pack.registry import ModelPackRegistry
from src.services.local_model_service import (
    LocalModelService,
    get_ollama_runtime_identity,
)
from src.services.model_pack_import_service import (
    MODEL_PACK_IMPORT_TASK_KIND,
    ModelPackImportService,
)
from src.services.task_queue import AnalysisTaskQueue
from src.task_execution import TaskCommand, TaskStatusEnum


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_pack(root: Path, *, tampered: bool = False) -> Path:
    root.mkdir(parents=True)
    gguf = root / "weights.gguf"
    modelfile = root / "Modelfile"
    license_file = root / "LICENSE"
    gguf.write_bytes(b"GGUF-service-test")
    modelfile.write_text("FROM ./weights.gguf\n", encoding="utf-8")
    license_file.write_text("Test license\n", encoding="utf-8")
    manifest = {
        "format_version": 1,
        "model_id": "stockpulse/service-test:q4",
        "display_name": "Service Test",
        "gguf_file": gguf.name,
        "modelfile": modelfile.name,
        "license": {"id": "LicenseRef-Test", "file": license_file.name},
        "minimum_memory_gb": 8,
        "files": [
            {
                "path": gguf.name,
                "role": "gguf",
                "sha256": _sha256(gguf),
                "size_bytes": gguf.stat().st_size,
            },
            {
                "path": modelfile.name,
                "role": "modelfile",
                "sha256": _sha256(modelfile),
                "size_bytes": modelfile.stat().st_size,
            },
            {
                "path": license_file.name,
                "role": "license",
                "sha256": _sha256(license_file),
                "size_bytes": license_file.stat().st_size,
            },
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if tampered:
        gguf.write_bytes(b"GGUF-tampered----")
    return root


class _ConfigService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.version = "before"
        self.values = {
            "LLM_CHANNELS": "primary",
            "LLM_OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            "LLM_OLLAMA_MODELS": "",
        }
        self.updates: list[Dict[str, Any]] = []
        self.update_started: Optional[threading.Event] = None
        self.release_update: Optional[threading.Event] = None

    def get_config(self, include_schema: bool):
        assert include_schema is False
        with self._lock:
            return {
                "config_version": self.version,
                "items": [
                    {"key": key, "value": value}
                    for key, value in self.values.items()
                ],
            }

    def update(self, **kwargs):
        if self.update_started is not None:
            self.update_started.set()
        if self.release_update is not None:
            assert self.release_update.wait(timeout=5)
        with self._lock:
            assert kwargs["config_version"] == self.version
            self.updates.append(kwargs)
            for item in kwargs["items"]:
                self.values[item["key"]] = item["value"]
            self.version = "after"
            return {
                "config_version": self.version,
                "updated_keys": [item["key"] for item in kwargs["items"]],
                "warnings": [],
                "applied_count": len(kwargs["items"]),
                "skipped_masked_count": 0,
                "reload_triggered": True,
            }


class _RecordingExecutor:
    def __init__(self, events: list[tuple[str, str]]) -> None:
        self.events = events

    def create(self, inspected, *, on_progress=None):
        self.events.append(("create", inspected.manifest.model_id))
        if on_progress is not None:
            on_progress(75, "Creating the Ollama model")


class _DeferredExecutor:
    def __init__(self) -> None:
        self.calls = []

    def submit(self, function, *args, **kwargs):
        future = Future()
        self.calls.append((function, args, kwargs, future))
        return future

    def shutdown(self, wait=True, cancel_futures=False) -> None:
        del wait
        if cancel_futures:
            for _function, _args, _kwargs, future in self.calls:
                future.cancel()


class _FailingExecutor:
    def submit(self, _function, *_args, **_kwargs):
        raise RuntimeError("submission failed")

    def shutdown(self, wait=True, cancel_futures=False) -> None:
        del wait, cancel_futures


@pytest.fixture
def task_queue():
    original = AnalysisTaskQueue._instance
    AnalysisTaskQueue._instance = None
    queue = AnalysisTaskQueue(max_workers=1)
    try:
        yield queue
    finally:
        queue.shutdown()
        AnalysisTaskQueue._instance = original


def _services(
    tmp_path: Path,
    queue: AnalysisTaskQueue,
    *,
    config: Optional[_ConfigService] = None,
    events: Optional[list[tuple[str, str]]] = None,
) -> tuple[ModelPackImportService, _ConfigService, ModelPackRegistry]:
    config = config or _ConfigService()
    events = events if events is not None else []
    registry = ModelPackRegistry(tmp_path / "model-packs.json")
    local_models = LocalModelService(
        system_config_service=config,
        task_queue=queue,
        pullable_model_ids=lambda: {"qwen3:4b"},
        client_factory=lambda _base_url: None,
        imported_model_metadata=registry.list_for_runtime,
    )
    service = ModelPackImportService(
        system_config_service=config,
        task_queue=queue,
        registry=registry,
        executor_factory=lambda base_url_provider: (
            events.append(("base_url", base_url_provider()))
            or _RecordingExecutor(events)
        ),
        activation_handler=lambda normalized, **kwargs: (
            local_models._activate_completed_import(normalized, **kwargs)
        ),
    )
    return service, config, registry


def test_import_service_uses_atomic_task_commit_and_cleans_staging(
    tmp_path: Path,
    task_queue: AnalysisTaskQueue,
) -> None:
    staging = tmp_path / "staging"
    pack = _write_pack(staging / "pack")
    events: list[tuple[str, str]] = []
    service, config, registry = _services(tmp_path, task_queue, events=events)

    task = service.start_import(pack, cleanup_root=staging)
    task_queue._futures[task.task_id].result(timeout=5)
    status = service.get_import(task.task_id)

    assert status is not None
    assert status["status"] == "completed"
    assert status["result"] == {
        "model_id": "stockpulse/service-test:q4",
        "display_name": "Service Test",
        "minimum_memory_gb": 8,
        "license_id": "LicenseRef-Test",
        "warnings": [],
        "activated": True,
        "selected_primary": True,
    }
    assert events == [
        ("base_url", "http://127.0.0.1:11434"),
        ("create", "stockpulse/service-test:q4"),
    ]
    assert config.values["LLM_OLLAMA_MODELS"] == "stockpulse/service-test:q4"
    assert registry.list_for_runtime(
        get_ollama_runtime_identity("http://127.0.0.1:11434")
    )[0]["display_name"] == "Service Test"
    assert not staging.exists()


def test_import_service_preserves_actionable_validation_failure(
    tmp_path: Path,
    task_queue: AnalysisTaskQueue,
) -> None:
    staging = tmp_path / "staging"
    pack = _write_pack(staging / "pack", tampered=True)
    calls: list[tuple[str, str]] = []
    service, config, _registry = _services(tmp_path, task_queue, events=calls)

    task = service.start_import(pack, cleanup_root=staging)
    task_queue._futures[task.task_id].result(timeout=5)
    status = service.get_import(task.task_id)

    assert status is not None
    assert status["status"] == "failed"
    assert status["error"] == "hash_mismatch"
    assert "Download or build the pack again" in status["message"]
    assert status["result"] is None
    assert calls == [("base_url", "http://127.0.0.1:11434")]
    assert config.updates == []
    assert not staging.exists()


@pytest.mark.parametrize("terminalizer", ["cancel", "shutdown"])
def test_prestart_terminalization_cleans_staged_upload(
    tmp_path: Path,
    task_queue: AnalysisTaskQueue,
    terminalizer: str,
) -> None:
    staging = tmp_path / "staging"
    pack = _write_pack(staging / "pack")
    executor = _DeferredExecutor()
    task_queue._executor = executor
    service, _config, _registry = _services(tmp_path, task_queue)

    task = service.start_import(pack, cleanup_root=staging)
    assert staging.exists()

    if terminalizer == "cancel":
        assert task_queue.cancel(task.task_id).status == TaskStatusEnum.CANCELLED
    else:
        task_queue.shutdown()

    assert not staging.exists()
    assert executor.calls[0][3].cancelled()


def test_queue_submission_failure_cleans_staged_upload(
    tmp_path: Path,
    task_queue: AnalysisTaskQueue,
) -> None:
    staging = tmp_path / "staging"
    pack = _write_pack(staging / "pack")
    task_queue._executor = _FailingExecutor()
    service, _config, _registry = _services(tmp_path, task_queue)

    with pytest.raises(RuntimeError, match="submission failed"):
        service.start_import(pack, cleanup_root=staging)

    assert not staging.exists()


def test_failure_code_survives_import_service_lifespan_replacement(
    tmp_path: Path,
    task_queue: AnalysisTaskQueue,
) -> None:
    pack = _write_pack(tmp_path / "pack", tampered=True)
    service, config, _registry = _services(tmp_path, task_queue)
    task = service.start_import(pack)
    task_queue._futures[task.task_id].result(timeout=5)

    replacement, _config, _replacement_registry = _services(
        tmp_path / "replacement",
        task_queue,
        config=config,
    )
    status = replacement.get_import(task.task_id)

    assert status is not None
    assert status["error"] == "hash_mismatch"
    assert "Download or build the pack again" in status["message"]


@pytest.mark.parametrize(
    ("winner", "expected_status"),
    [
        ("cancel", TaskStatusEnum.CANCELLED),
        ("shutdown", TaskStatusEnum.INTERRUPTED),
    ],
)
def test_final_registration_rejects_cancel_and_shutdown_winners(
    tmp_path: Path,
    task_queue: AnalysisTaskQueue,
    winner: str,
    expected_status: TaskStatusEnum,
) -> None:
    pack = _write_pack(tmp_path / "pack")
    service, config, registry = _services(tmp_path, task_queue)
    commit_reached = threading.Event()
    release_commit = threading.Event()
    original_commit = task_queue._commit_final_result

    def delay_commit(task_id, operation):
        commit_reached.set()
        assert release_commit.wait(timeout=5)
        return original_commit(task_id, operation)

    task_queue._commit_final_result = delay_commit
    task = service.start_import(pack)
    future = task_queue._futures[task.task_id]
    assert commit_reached.wait(timeout=5)

    if winner == "cancel":
        assert task_queue.cancel(task.task_id).status == TaskStatusEnum.CANCEL_REQUESTED
    else:
        task_queue.shutdown()
    release_commit.set()
    future.result(timeout=5)

    assert task_queue.get(task.task_id).status == expected_status
    assert config.updates == []
    assert config.values["LLM_OLLAMA_MODELS"] == ""
    runtime_identity = "0" * 64
    assert registry.list_for_runtime(runtime_identity) == ()


def test_import_status_does_not_project_other_task_kinds(
    tmp_path: Path,
    task_queue: AnalysisTaskQueue,
) -> None:
    service, _config, _registry = _services(tmp_path, task_queue)
    other_id = task_queue.submit(
        TaskCommand(
            kind="stock_analysis",
            run=lambda _context: {"ok": True},
            metadata={"stock_code": "AAPL", "report_type": "stock_analysis"},
        )
    )
    task_queue._futures[other_id].result(timeout=5)

    assert service.get_import(other_id) is None
    assert service.get_import("missing") is None
    assert MODEL_PACK_IMPORT_TASK_KIND == "model_pack_import"
