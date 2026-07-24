from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from src.services.model_pack_import_service import (
    MODEL_PACK_IMPORT_TASK_KIND,
    ModelPackImportService,
)
from src.services.task_queue import TaskStatus


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


class _Task:
    def __init__(self, *, task_id: str, report_type: str) -> None:
        self.task_id = task_id
        self.report_type = report_type
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.result = None
        self._error = None
        self._message = "Model Pack import queued"

    def public_error(self):
        return self._error

    def public_message(self):
        return self._message


class _SynchronousTaskQueue:
    def __init__(self) -> None:
        self.tasks = {}
        self.progress = []

    def submit_background_task(self, run_task, **kwargs):
        task = _Task(task_id=kwargs["task_id"], report_type=kwargs["report_type"])
        self.tasks[task.task_id] = task
        task.status = TaskStatus.PROCESSING
        try:
            task.result = run_task()
        except Exception:
            task.status = TaskStatus.FAILED
            task._error = kwargs["failure_error_code"]
            task._message = "Task failed"
        else:
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            task._message = "Task completed"
        return task

    def update_task_progress(
        self,
        task_id,
        progress,
        message,
        *,
        message_code,
        message_params,
    ):
        task = self.tasks[task_id]
        task.progress = progress
        task._message = message
        self.progress.append(
            (task_id, progress, message, message_code, message_params)
        )

    def get_task(self, task_id):
        return self.tasks.get(task_id)


class _ConfigService:
    def __init__(self) -> None:
        self.updates = []
        self.values = {
            "LLM_CHANNELS": "primary",
            "LLM_OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            "LLM_OLLAMA_MODELS": "",
        }

    def get_config(self, include_schema: bool):
        assert include_schema is False
        return {
            "config_version": "before",
            "items": [
                {"key": key, "value": value}
                for key, value in self.values.items()
            ],
        }

    def update(self, **kwargs):
        self.updates.append(kwargs)
        for item in kwargs["items"]:
            self.values[item["key"]] = item["value"]
        return {"config_version": "after", "reload_triggered": True}


class _RecordingExecutor:
    def __init__(self, events) -> None:
        self.events = events

    def create(self, inspected, *, on_progress=None):
        self.events.append(("create", inspected.manifest.model_id))
        if on_progress is not None:
            on_progress(75, "Creating the Ollama model")


def test_import_service_uses_shared_task_lifecycle_and_cleans_staging(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    pack = _write_pack(staging / "pack")
    queue = _SynchronousTaskQueue()
    config = _ConfigService()
    executor_events = []
    service = ModelPackImportService(
        system_config_service=config,
        task_queue=queue,
        executor_factory=lambda base_url_provider: (
            executor_events.append(("base_url", base_url_provider()))
            or _RecordingExecutor(executor_events)
        ),
    )

    task = service.start_import(pack, cleanup_root=staging)
    status = service.get_import(task.task_id)

    assert status == {
        "task_id": task.task_id,
        "status": "completed",
        "progress": 100,
        "error": None,
        "message": "Task completed",
        "result": {
            "model_id": "stockpulse/service-test:q4",
            "display_name": "Service Test",
            "minimum_memory_gb": 8,
            "license_id": "LicenseRef-Test",
            "warnings": (),
            "registration": {
                "channels": "primary,ollama",
                "models": "stockpulse/service-test:q4",
                "config_version": "after",
                "reload_triggered": True,
            },
        },
    }
    assert executor_events == [
        ("base_url", "http://127.0.0.1:11434"),
        ("create", "stockpulse/service-test:q4"),
    ]
    assert queue.progress[0][1:] == (
        75,
        "Creating the Ollama model",
        "local_model.import.progress",
        {},
    )
    assert config.values["LLM_OLLAMA_MODELS"] == "stockpulse/service-test:q4"
    assert not staging.exists()


def test_import_service_preserves_actionable_validation_failure(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    pack = _write_pack(staging / "pack", tampered=True)
    queue = _SynchronousTaskQueue()
    calls = []
    service = ModelPackImportService(
        system_config_service=_ConfigService(),
        task_queue=queue,
        executor_factory=lambda _base_url_provider: SimpleNamespace(
            create=lambda *_args, **_kwargs: calls.append("create")
        ),
    )

    task = service.start_import(pack, cleanup_root=staging)
    status = service.get_import(task.task_id)

    assert status["status"] == "failed"
    assert status["error"] == "hash_mismatch"
    assert "Download or build the pack again" in status["message"]
    assert status["result"] is None
    assert calls == []
    assert not staging.exists()


def test_import_status_does_not_project_other_task_kinds() -> None:
    queue = _SynchronousTaskQueue()
    queue.tasks["other"] = _Task(task_id="other", report_type="stock_analysis")
    service = ModelPackImportService(
        system_config_service=_ConfigService(),
        task_queue=queue,
    )

    assert service.get_import("other") is None
    assert service.get_import("missing") is None
