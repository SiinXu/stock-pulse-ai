from __future__ import annotations

import shutil
import threading
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Mapping, Optional

from src.model_pack import (
    DEFAULT_OLLAMA_BASE_URL,
    ModelPackError,
    ModelPackImporter,
    OllamaHttpModelPackExecutor,
)
from src.services.local_model_activation import LocalModelActivationService
from src.services.task_queue import AnalysisTaskQueue, TaskInfo, TaskStatus

if TYPE_CHECKING:
    from src.services.system_config_service import SystemConfigService


MODEL_PACK_IMPORT_TASK_KIND = "model_pack_import"
_MAX_RETAINED_IMPORT_FAILURES = 256


class ModelPackImportService:
    """Run Model Pack imports through the shared process-local task queue."""

    def __init__(
        self,
        *,
        system_config_service: "SystemConfigService",
        task_queue: AnalysisTaskQueue,
        executor_factory: Optional[Callable[[Callable[[], str]], Any]] = None,
    ) -> None:
        self._system_config_service = system_config_service
        self._task_queue = task_queue
        self._executor_factory = executor_factory or (
            lambda base_url_provider: OllamaHttpModelPackExecutor(
                base_url_provider=base_url_provider
            )
        )
        self._failures: Dict[str, Dict[str, str]] = {}
        self._failure_lock = threading.RLock()

    def _config_values(self) -> Mapping[str, str]:
        payload = self._system_config_service.get_config(include_schema=False)
        return {
            str(item.get("key") or "").upper(): str(item.get("value") or "")
            for item in payload.get("items", [])
            if isinstance(item, dict)
        }

    def _base_url(self) -> str:
        return self._config_values().get("LLM_OLLAMA_BASE_URL", "") or DEFAULT_OLLAMA_BASE_URL

    def _record_failure(self, task_id: str, error: ModelPackError) -> None:
        with self._failure_lock:
            while len(self._failures) >= _MAX_RETAINED_IMPORT_FAILURES:
                self._failures.pop(next(iter(self._failures)))
            self._failures[task_id] = {
                "error": error.code,
                "message": error.user_message,
            }

    def _clear_failure(self, task_id: str) -> None:
        with self._failure_lock:
            self._failures.pop(task_id, None)

    def start_import(
        self,
        source: Path,
        *,
        cleanup_root: Optional[Path] = None,
    ) -> TaskInfo:
        """Submit one staged archive or directory for validation and import."""

        source_path = Path(source)
        cleanup_path = Path(cleanup_root) if cleanup_root is not None else None
        task_id = uuid.uuid4().hex
        executor = self._executor_factory(self._base_url)
        activation = LocalModelActivationService(self._system_config_service)
        importer = ModelPackImporter(
            executor=executor,
            register_model=activation.activate,
        )

        def run_import() -> Dict[str, Any]:
            try:
                result = importer.import_pack(
                    source_path,
                    on_progress=lambda progress, message: self._task_queue.update_task_progress(
                        task_id,
                        progress,
                        message,
                        message_code="local_model.import.progress",
                        message_params={},
                    ),
                )
                self._clear_failure(task_id)
                return asdict(result)
            except ModelPackError as exc:
                self._record_failure(task_id, exc)
                raise
            finally:
                if cleanup_path is not None:
                    shutil.rmtree(cleanup_path, ignore_errors=True)

        return self._task_queue.submit_background_task(
            run_import,
            stock_code="model_pack",
            stock_name="Local Model Pack",
            report_type=MODEL_PACK_IMPORT_TASK_KIND,
            message="Model Pack import queued",
            task_id=task_id,
            trace_id=task_id,
            failure_error_code="model_pack_import_failed",
        )

    def get_import(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self._task_queue.get_task(str(task_id or ""))
        if task is None or task.report_type != MODEL_PACK_IMPORT_TASK_KIND:
            return None
        status = task.status.value if isinstance(task.status, TaskStatus) else str(task.status)
        result = (
            task.result
            if task.status == TaskStatus.COMPLETED and isinstance(task.result, dict)
            else None
        )
        with self._failure_lock:
            failure = dict(self._failures.get(task.task_id) or {})
        return {
            "task_id": task.task_id,
            "status": status,
            "progress": task.progress,
            "error": failure.get("error") or task.public_error(),
            "message": failure.get("message") or task.public_message(),
            "result": result,
        }


__all__ = ["MODEL_PACK_IMPORT_TASK_KIND", "ModelPackImportService"]
