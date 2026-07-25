from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ModelPackFile:
    """One declared payload file and its integrity metadata."""

    path: str
    role: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ModelPackLicense:
    """License identifier and root-level text filename."""

    id: str
    file: str


@dataclass(frozen=True)
class ModelPackManifest:
    """Strict immutable format-v1 Model Pack manifest."""

    format_version: int
    model_id: str
    display_name: str
    gguf_file: str
    modelfile: str
    license: ModelPackLicense
    minimum_memory_gb: int
    files: Tuple[ModelPackFile, ...]

    def file_for_role(self, role: str) -> ModelPackFile:
        """Return the unique declared file for one required role."""
        return next(file_entry for file_entry in self.files if file_entry.role == role)


@dataclass(frozen=True)
class ParsedModelfile:
    """Validated data-only Modelfile projection."""

    from_file: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    template: Optional[str] = None
    system: Optional[str] = None


@dataclass(frozen=True)
class InspectedModelPack:
    """Private validated snapshot passed to the Ollama executor."""

    root: Path
    manifest: ModelPackManifest
    modelfile: ParsedModelfile
    gguf_path: Path
    modelfile_path: Path
    license_path: Path
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelPackImportResult:
    """Detached successful import metadata and activation state."""

    model_id: str
    display_name: str
    minimum_memory_gb: int
    license_id: str
    warnings: Tuple[str, ...]
    activated: bool
    selected_primary: bool = False


__all__ = [
    "InspectedModelPack",
    "ModelPackFile",
    "ModelPackImportResult",
    "ModelPackLicense",
    "ModelPackManifest",
    "ParsedModelfile",
]
