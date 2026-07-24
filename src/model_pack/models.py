from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ModelPackFile:
    path: str
    role: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ModelPackLicense:
    id: str
    file: str


@dataclass(frozen=True)
class ModelPackManifest:
    format_version: int
    model_id: str
    display_name: str
    gguf_file: str
    modelfile: str
    license: ModelPackLicense
    minimum_memory_gb: int
    files: Tuple[ModelPackFile, ...]

    def file_for_role(self, role: str) -> ModelPackFile:
        return next(file_entry for file_entry in self.files if file_entry.role == role)


@dataclass(frozen=True)
class ParsedModelfile:
    from_file: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    template: Optional[str] = None
    system: Optional[str] = None


@dataclass(frozen=True)
class InspectedModelPack:
    root: Path
    manifest: ModelPackManifest
    modelfile: ParsedModelfile
    gguf_path: Path
    modelfile_path: Path
    license_path: Path
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelPackImportResult:
    model_id: str
    display_name: str
    minimum_memory_gb: int
    license_id: str
    warnings: Tuple[str, ...]
    registration: Any = None


__all__ = [
    "InspectedModelPack",
    "ModelPackFile",
    "ModelPackImportResult",
    "ModelPackLicense",
    "ModelPackManifest",
    "ParsedModelfile",
]
