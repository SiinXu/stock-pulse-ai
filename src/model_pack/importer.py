from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from src.model_pack.errors import ModelPackError
from src.model_pack.models import (
    InspectedModelPack,
    ModelPackImportResult,
)
from src.model_pack.validation import inspect_model_pack


class ModelPackExecutor(Protocol):
    """Execution port for creating one already inspected Model Pack."""

    def create(
        self,
        inspected: InspectedModelPack,
        *,
        on_progress: Optional[Callable[[int, str], None]] = None,
        is_cancel_requested: Optional[Callable[[], bool]] = None,
    ) -> Optional[bool]:
        """Create the validated model unless cancellation wins first."""
        ...


class ModelPackImporter:
    """Validate, create, and activate one local model in that order."""

    def __init__(
        self,
        *,
        executor: ModelPackExecutor,
        register_model: Callable[[str], Any],
        disk_usage: Callable[[Path], object] = shutil.disk_usage,
    ) -> None:
        """Bind the create executor, registration callback, and disk probe."""
        self._executor = executor
        self._register_model = register_model
        self._disk_usage = disk_usage

    def import_pack(
        self,
        source: Path,
        *,
        on_progress: Optional[Callable[[int, str], None]] = None,
    ) -> ModelPackImportResult:
        """Validate, create, register, and return detached manifest metadata."""
        with inspect_model_pack(source, disk_usage=self._disk_usage) as inspected:
            try:
                self._executor.create(inspected, on_progress=on_progress)
            except ModelPackError:
                raise
            except Exception as exc:  # broad-exception: cleanup - Translate executor failures to the typed import boundary.
                raise ModelPackError(
                    "ollama_create_failed",
                    (
                        "Ollama could not create this model. "
                        "Check that Ollama is running and that the pack is compatible, then try again."
                    ),
                ) from exc
            try:
                registration = self._register_model(inspected.manifest.model_id)
            except ModelPackError:
                raise
            except Exception as exc:  # broad-exception: cleanup - Translate activation failures to the typed import boundary.
                raise ModelPackError(
                    "registration_failed",
                    (
                        "The model was created, but StockPulse could not activate it. "
                        "Open Local Models and register the model manually."
                    ),
                ) from exc
            return ModelPackImportResult(
                model_id=inspected.manifest.model_id,
                display_name=inspected.manifest.display_name,
                minimum_memory_gb=inspected.manifest.minimum_memory_gb,
                license_id=inspected.manifest.license.id,
                warnings=inspected.warnings,
                activated=bool(
                    registration is not None
                    and (
                        not isinstance(registration, dict)
                        or registration.get("activated", True)
                    )
                ),
                selected_primary=bool(
                    isinstance(registration, dict)
                    and registration.get("selected_primary")
                ),
            )


__all__ = ["ModelPackExecutor", "ModelPackImporter"]
