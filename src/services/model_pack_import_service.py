"""Model Pack import orchestration on the canonical process-local task queue."""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol

from src.model_pack import (
    DEFAULT_OLLAMA_BASE_URL,
    ModelPackError,
    ModelPackRegistry,
    OllamaHttpModelPackExecutor,
    inspect_model_pack,
    normalize_ollama_native_base_url,
)
from src.services.local_model_service import (
    LocalModelError,
    LocalModelService,
    get_ollama_runtime_identity,
)
from src.services.task_queue import AnalysisTaskQueue, TaskInfo
from src.services.system_config_service import ConfigConflictError, ConfigValidationError
from src.task_execution import TaskCommand, TaskRunContext, TaskStatusEnum
from src.utils.sanitize import log_safe_exception


MODEL_PACK_IMPORT_TASK_KIND = "model_pack_import"
_MAX_RETAINED_IMPORT_FAILURES = 256
_PROCESS_IMPORT_FAILURES: Dict[str, Dict[str, str]] = {}
_PROCESS_IMPORT_FAILURE_LOCK = threading.RLock()
logger = logging.getLogger(__name__)


class _ModelPackActivationHandler(Protocol):
    """Activate one validated Model Pack through the shared local-model authority."""

    def __call__(
        self,
        normalized: str,
        *,
        config_version: str,
        values: Mapping[str, str],
        base_url: str,
        metadata: Mapping[str, Any],
        is_cancel_requested: Callable[[], bool],
        commit_final_result: Callable[
            [Callable[[], Any]], tuple[bool, Any]
        ],
        persist_metadata: Callable[[], Any],
    ) -> Optional[Dict[str, Any]]:
        """Return activation metadata after the guarded final commit."""
        ...


class ModelPackImportService:
    """Validate, create, and register Model Packs without bypassing lifecycle authority."""

    def __init__(
        self,
        *,
        system_config_service: Any,
        task_queue: AnalysisTaskQueue,
        activation_handler: _ModelPackActivationHandler,
        registry: Optional[ModelPackRegistry] = None,
        executor_factory: Optional[Callable[[Callable[[], str]], Any]] = None,
    ) -> None:
        """Bind import orchestration to the current config and task authorities."""
        self._system_config_service = system_config_service
        self._task_queue = task_queue
        self._activation_handler = activation_handler
        self._registry = registry or ModelPackRegistry()
        self._executor_factory = executor_factory or (
            lambda base_url_provider: OllamaHttpModelPackExecutor(
                base_url_provider=base_url_provider
            )
        )
        self._failures = _PROCESS_IMPORT_FAILURES
        self._failure_lock = _PROCESS_IMPORT_FAILURE_LOCK

    def _config_snapshot(self) -> tuple[str, Dict[str, str], str]:
        """Return the immutable config version, values, and normalized runtime URL."""
        payload = self._system_config_service.get_config(include_schema=False)
        values = {
            str(item.get("key") or "").upper(): str(item.get("value") or "")
            for item in payload.get("items", [])
            if isinstance(item, dict)
        }
        base_url = normalize_ollama_native_base_url(
            values.get("LLM_OLLAMA_BASE_URL", "") or DEFAULT_OLLAMA_BASE_URL
        )
        return str(payload.get("config_version") or ""), values, base_url

    def _record_failure(self, task_id: str, error: ModelPackError) -> None:
        """Retain one bounded public failure projection for import polling."""
        with self._failure_lock:
            while len(self._failures) >= _MAX_RETAINED_IMPORT_FAILURES:
                self._failures.pop(next(iter(self._failures)))
            self._failures[task_id] = {
                "error": error.code,
                "message": error.user_message,
            }

    def _clear_failure(self, task_id: str) -> None:
        """Remove a retained failure after the same task succeeds."""
        with self._failure_lock:
            self._failures.pop(task_id, None)

    def _persist_metadata(
        self,
        *,
        runtime_identity: str,
        metadata: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Register validated metadata under the selected Ollama runtime identity."""
        return self._registry.register(
            runtime_identity=runtime_identity,
            model_id=str(metadata["model_id"]),
            display_name=str(metadata["display_name"]),
            minimum_memory_gb=int(metadata["minimum_memory_gb"]),
            license_id=str(metadata["license_id"]),
        )

    def start_import(
        self,
        source: Path,
        *,
        cleanup_root: Optional[Path] = None,
    ) -> TaskInfo:
        """Submit one staged archive or directory for validation and import."""
        source_path = Path(source)
        cleanup_path = Path(cleanup_root) if cleanup_root is not None else None
        config_version, values, base_url = self._config_snapshot()
        runtime_identity = get_ollama_runtime_identity(base_url)
        executor = self._executor_factory(lambda: base_url)

        def cleanup_import_source() -> None:
            """Remove the endpoint-owned staging directory idempotently."""
            if cleanup_path is not None:
                shutil.rmtree(cleanup_path, ignore_errors=True)

        def run_import(context: TaskRunContext) -> Dict[str, Any]:
            """Validate, create, and activate one staged pack in the worker."""
            try:
                with inspect_model_pack(source_path) as inspected:
                    context.update_progress(20, "Validated Model Pack")
                    metadata = {
                        "model_id": inspected.manifest.model_id,
                        "display_name": inspected.manifest.display_name,
                        "minimum_memory_gb": inspected.manifest.minimum_memory_gb,
                        "license_id": inspected.manifest.license.id,
                        "warnings": list(inspected.warnings),
                    }
                    if context.is_cancel_requested():
                        return {
                            **metadata,
                            "activated": False,
                            "selected_primary": False,
                        }
                    try:
                        created = executor.create(
                            inspected,
                            on_progress=context.update_progress,
                            is_cancel_requested=context.is_cancel_requested,
                        )
                    except ModelPackError:
                        raise
                    except Exception as exc:  # broad-exception: fallback_recorded - normalize executor failures
                        log_safe_exception(
                            logger,
                            "Model Pack Ollama create failed",
                            exc,
                            error_code="model_pack_ollama_create_failed",
                            level=logging.WARNING,
                            context={"task_id": context.task_id},
                        )
                        raise ModelPackError(
                            "ollama_create_failed",
                            (
                                "Ollama could not create this model. Check that Ollama is "
                                "running and that the pack is compatible, then try again."
                            ),
                        ) from exc

                    if created is False or context.is_cancel_requested():
                        return {
                            **metadata,
                            "activated": False,
                            "selected_primary": False,
                        }
                    try:
                        activation = self._activation_handler(
                            inspected.manifest.model_id,
                            config_version=config_version,
                            values=values,
                            base_url=base_url,
                            metadata=metadata,
                            is_cancel_requested=context.is_cancel_requested,
                            commit_final_result=context.commit_final_result,
                            persist_metadata=lambda: self._persist_metadata(
                                runtime_identity=runtime_identity,
                                metadata=metadata,
                            ),
                        )
                    except ModelPackError:
                        raise
                    except Exception as exc:  # broad-exception: fallback_recorded - stable post-create boundary
                        log_safe_exception(
                            logger,
                            "Model Pack activation failed after Ollama create",
                            exc,
                            error_code="model_pack_activation_failed",
                            level=logging.WARNING,
                            context={"task_id": context.task_id},
                        )
                        raise ModelPackError(
                            "registration_failed",
                            (
                                "The model was created, but StockPulse could not activate it. "
                                "Open Local Models, refresh, and try to register it again."
                            ),
                        ) from exc
                    self._clear_failure(context.task_id)
                    return activation or {
                        **metadata,
                        "activated": False,
                        "selected_primary": False,
                    }
            except ModelPackError as exc:
                self._record_failure(context.task_id, exc)
                raise
            finally:
                cleanup_import_source()

        command = TaskCommand(
            kind=MODEL_PACK_IMPORT_TASK_KIND,
            run=run_import,
            metadata={
                "stock_code": "model_pack",
                "stock_name": "Local Model Pack",
                "report_type": MODEL_PACK_IMPORT_TASK_KIND,
                "message": "Model Pack import queued",
            },
            failure_error_code="model_pack_import_failed",
            on_done=cleanup_import_source,
        )
        try:
            task_id = self._task_queue.submit(command)
        except BaseException:  # broad-exception: cleanup - release staging when queue admission fails
            cleanup_import_source()
            raise
        task = self._task_queue.get_task(task_id)
        if task is None:  # pragma: no cover - queue adapter invariant
            raise RuntimeError("Accepted Model Pack import task is unavailable")
        return task

    def activate_desktop_import(
        self,
        local_model_service: LocalModelService,
        *,
        model_id: str,
        display_name: str,
        minimum_memory_gb: int,
        license_id: str,
        expected_config_version: str,
        expected_runtime_identity: str,
    ) -> Dict[str, Any]:
        """Persist Desktop-validated manifest metadata with shared activation semantics."""
        metadata = {
            "model_id": model_id,
            "display_name": display_name,
            "minimum_memory_gb": minimum_memory_gb,
            "license_id": license_id,
        }
        try:
            return local_model_service.activate_desktop_imported_model(
                model_id,
                expected_config_version=expected_config_version,
                expected_runtime_identity=expected_runtime_identity,
                persist_metadata=lambda: self._persist_metadata(
                    runtime_identity=expected_runtime_identity,
                    metadata=metadata,
                ),
            )
        except (LocalModelError, ConfigValidationError, ConfigConflictError):
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - stable Desktop activation boundary
            log_safe_exception(
                logger,
                "Desktop Model Pack activation failed after Ollama create",
                exc,
                error_code="desktop_model_pack_activation_failed",
                level=logging.WARNING,
            )
            raise ModelPackError(
                "registration_failed",
                (
                    "The model was created, but StockPulse could not register it. "
                    "Refresh Local Models and try again."
                ),
            ) from exc

    def get_import(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Return the public polling projection for one Model Pack import."""
        task = self._task_queue.get_task(str(task_id or ""))
        if task is None or task.report_type != MODEL_PACK_IMPORT_TASK_KIND:
            return None
        result = (
            task.result
            if task.status == TaskStatusEnum.COMPLETED and isinstance(task.result, dict)
            else None
        )
        with self._failure_lock:
            failure = dict(self._failures.get(task.task_id) or {})
        return {
            "task_id": task.task_id,
            "status": (
                task.status.value
                if isinstance(task.status, TaskStatusEnum)
                else str(task.status)
            ),
            "progress": task.progress,
            "error": failure.get("error") or task.public_error(),
            "message": failure.get("message") or task.public_message(),
            "result": result,
        }


__all__ = ["MODEL_PACK_IMPORT_TASK_KIND", "ModelPackImportService"]
