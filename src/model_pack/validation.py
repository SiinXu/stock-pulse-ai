from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Callable, Dict, Iterator, List, Optional, Tuple
from zipfile import BadZipFile, ZipFile, is_zipfile

from src.model_pack.errors import ModelPackError
from src.model_pack.manifest import (
    MANIFEST_FILENAME,
    MAX_MANIFEST_BYTES,
    MAX_MODEL_PACK_BYTES,
    parse_manifest_bytes,
)
from src.model_pack.models import InspectedModelPack, ModelPackFile, ModelPackManifest
from src.model_pack.modelfile import MAX_MODELFILE_BYTES, parse_modelfile


_HASH_CHUNK_SIZE = 1024 * 1024
_DISK_RESERVE_MIN_BYTES = 64 * 1024 * 1024
_DISK_RESERVE_MAX_BYTES = 512 * 1024 * 1024
MAX_LICENSE_BYTES = 2 * 1024 * 1024
MAX_MODEL_PACK_ENTRIES = 256
DiskUsage = Callable[[Path], object]


def _error(code: str, message: str) -> ModelPackError:
    """Return one stable actionable validation error."""
    return ModelPackError(code, message)


def _sha256(path: Path) -> str:
    """Hash one payload file with bounded memory."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(_HASH_CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError as exc:
        raise _error(
            "file_read_failed",
            f"Could not read {path.name}. Check file permissions and try again.",
        ) from exc
    return digest.hexdigest()


def _same_file_identity(first: os.stat_result, second: os.stat_result) -> bool:
    """Return whether two stat results identify the same filesystem object."""
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


@contextmanager
def _open_regular_payload(path: Path, name: str) -> Iterator[Tuple[BinaryIO, int]]:
    """Open one declared source through a stable verified regular-file handle."""
    file_obj: Optional[BinaryIO] = None
    try:
        path_stat = path.lstat()
        if not stat.S_ISREG(path_stat.st_mode):
            raise _error(
                "unsafe_package_entry",
                (
                    f"{name} must be a regular file inside the Model Pack. "
                    "Build the pack again."
                ),
            )
        file_obj = path.open("rb")
        opened_stat = os.fstat(file_obj.fileno())
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or not _same_file_identity(path_stat, opened_stat)
        ):
            raise _error(
                "unsafe_package_entry",
                (
                    f"{name} changed while it was opened. "
                    "Stop modifying the Model Pack and try again."
                ),
            )
    except ModelPackError:
        if file_obj is not None:
            file_obj.close()
        raise
    except FileNotFoundError as exc:
        if file_obj is not None:
            file_obj.close()
        raise _error(
            "missing_file",
            f"Model Pack is missing {name}. Download or build the pack again.",
        ) from exc
    except OSError as exc:
        if file_obj is not None:
            file_obj.close()
        raise _error(
            "file_read_failed",
            f"Could not read {name}. Check file permissions and try again.",
        ) from exc
    assert file_obj is not None
    try:
        yield file_obj, opened_stat.st_size
    finally:
        file_obj.close()


def _validate_role_size(file_entry: ModelPackFile, size_bytes: int) -> None:
    """Validate one declared or actual size against its role-specific cap."""
    path = file_entry.path
    role = file_entry.role
    if role == "modelfile" and size_bytes > MAX_MODELFILE_BYTES:
        raise _error(
            "unsafe_modelfile",
            (
                f"{path} exceeds the {MAX_MODELFILE_BYTES}-byte limit. "
                "Reduce it and rebuild the pack."
            ),
        )
    if role == "license" and size_bytes > MAX_LICENSE_BYTES:
        raise _error(
            "invalid_license_file",
            (
                f"{path} exceeds the {MAX_LICENSE_BYTES}-byte limit. "
                "Use the plain-text license and rebuild the pack."
            ),
        )


def _validate_declared_size(file_entry: ModelPackFile, actual_size: int) -> None:
    """Validate one actual payload size against its declaration and role cap."""
    if actual_size != file_entry.size_bytes:
        raise _error(
            "size_mismatch",
            (
                f"{file_entry.path} has the wrong size. "
                "Download or build the pack again."
            ),
        )
    _validate_role_size(file_entry, actual_size)


def _validate_manifest_role_sizes(manifest: ModelPackManifest) -> None:
    """Reject role-specific declared sizes before any payload copy or extraction."""
    for file_entry in manifest.files:
        _validate_role_size(file_entry, file_entry.size_bytes)


def _disk_required_bytes(payload_size: int, *, archive: bool) -> int:
    """Return staging, extraction, and reserve bytes for preflight."""
    reserve = min(
        _DISK_RESERVE_MAX_BYTES,
        max(_DISK_RESERVE_MIN_BYTES, payload_size // 20),
    )
    copies = 2 if archive else 1
    return payload_size * copies + reserve


def _check_disk(
    location: Path,
    *,
    payload_size: int,
    archive: bool,
    disk_usage: DiskUsage,
) -> None:
    """Reject an import when the staging disk lacks bounded free space."""
    required = _disk_required_bytes(payload_size, archive=archive)
    try:
        free = int(getattr(disk_usage(location), "free"))
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise _error(
            "disk_check_failed",
            "Could not check free disk space. Check the target disk and try again.",
        ) from exc
    if free < required:
        required_gib = max(1, (required - free + (1024 ** 3) - 1) // (1024 ** 3))
        raise ModelPackError(
            "insufficient_disk_space",
            (
                f"Not enough disk space to import this Model Pack. "
                f"Free at least {required_gib} GiB and try again."
            ),
            details={"additional_bytes_required": required - free},
        )


def _unexpected_file_warning(path: str) -> str:
    """Return the stable warning for one undeclared regular file."""
    return f"Unexpected file is not part of the manifest: {path}"


def _safe_archive_name(name: str) -> bool:
    """Return whether one archive member is a safe root-level filename."""
    path = Path(name)
    return bool(
        name
        and "\\" not in name
        and not name.startswith(("/", "\\"))
        and not path.is_absolute()
        and len(path.parts) == 1
        and path.parts[0] not in {".", ".."}
    )


def _validate_payload_files(
    root: Path,
    manifest: ModelPackManifest,
) -> None:
    """Verify declared sizes, hashes, file types, GGUF magic, and limits."""
    for file_entry in manifest.files:
        path = root / file_entry.path
        if not path.exists():
            raise _error(
                "missing_file",
                (
                    f"Model Pack is missing {file_entry.path}. "
                    "Download or build the pack again."
                ),
            )
        if path.is_symlink() or not path.is_file():
            raise _error(
                "unsafe_package_entry",
                (
                    f"{file_entry.path} must be a regular file inside the Model Pack. "
                    "Build the pack again."
                ),
            )
        try:
            actual_size = path.stat().st_size
        except OSError as exc:
            raise _error(
                "file_read_failed",
                f"Could not read {file_entry.path}. Check file permissions and try again.",
            ) from exc
        _validate_declared_size(file_entry, actual_size)
        if _sha256(path) != file_entry.sha256:
            raise _error(
                "hash_mismatch",
                (
                    f"{file_entry.path} failed SHA-256 verification. "
                    "Download or build the pack again."
                ),
            )
        if file_entry.role == "gguf":
            try:
                with path.open("rb") as file_obj:
                    magic = file_obj.read(4)
            except OSError as exc:
                raise _error(
                    "file_read_failed",
                    f"Could not read {file_entry.path}. Check file permissions and try again.",
                ) from exc
            if magic != b"GGUF":
                raise _error(
                    "invalid_gguf",
                    (
                        f"{file_entry.path} is not a GGUF model. "
                        "Select the correct weights and rebuild the pack."
                    ),
                )


def _build_inspection(
    root: Path,
    manifest: ModelPackManifest,
    warnings: Tuple[str, ...],
) -> InspectedModelPack:
    """Build an executor-ready inspection after all payload checks."""
    _validate_payload_files(root, manifest)
    modelfile_path = root / manifest.modelfile
    try:
        modelfile_payload = modelfile_path.read_bytes()
    except OSError as exc:
        raise _error(
            "file_read_failed",
            f"Could not read {manifest.modelfile}. Check file permissions and try again.",
        ) from exc
    parsed_modelfile = parse_modelfile(
        modelfile_payload,
        expected_gguf_file=manifest.gguf_file,
    )
    license_path = root / manifest.license.file
    try:
        license_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise _error(
            "invalid_license_file",
            "The declared license must be UTF-8 text. Rebuild the Model Pack.",
        ) from exc
    except OSError as exc:
        raise _error(
            "file_read_failed",
            f"Could not read {manifest.license.file}. Check file permissions and try again.",
        ) from exc
    return InspectedModelPack(
        root=root,
        manifest=manifest,
        modelfile=parsed_modelfile,
        gguf_path=root / manifest.gguf_file,
        modelfile_path=modelfile_path,
        license_path=license_path,
        warnings=warnings,
    )


def _read_directory_manifest(root: Path) -> Tuple[ModelPackManifest, bytes]:
    """Read and parse the regular root manifest from a directory."""
    manifest_path = root / MANIFEST_FILENAME
    file_obj: Optional[BinaryIO] = None
    try:
        path_stat = manifest_path.lstat()
        if not stat.S_ISREG(path_stat.st_mode):
            raise _error(
                "unsafe_package_entry",
                "manifest.json must be a regular file. Build the pack again.",
            )
        file_obj = manifest_path.open("rb")
        opened_stat = os.fstat(file_obj.fileno())
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or not _same_file_identity(path_stat, opened_stat)
        ):
            raise _error(
                "unsafe_package_entry",
                (
                    "manifest.json changed while it was opened. "
                    "Stop modifying the Model Pack and try again."
                ),
            )
        payload = file_obj.read(MAX_MANIFEST_BYTES + 1)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise _error(
                "invalid_manifest",
                "manifest.json is too large. Build the pack again with the current tool.",
            )
        return parse_manifest_bytes(payload), payload
    except ModelPackError:
        raise
    except FileNotFoundError as exc:
        raise _error(
            "missing_manifest",
            "Model Pack is missing manifest.json. Download or build the pack again.",
        ) from exc
    except OSError as exc:
        raise _error(
            "file_read_failed",
            "Could not read manifest.json. Check file permissions and try again.",
        ) from exc
    finally:
        if file_obj is not None:
            file_obj.close()


def _directory_inventory(root: Path) -> Tuple[str, ...]:
    """Enumerate a bounded directory tree and return regular filenames."""
    names: List[str] = []
    paths: List[Path] = []
    entry_count = 0
    try:
        for path in root.rglob("*"):
            entry_count += 1
            if entry_count > MAX_MODEL_PACK_ENTRIES:
                raise _error(
                    "invalid_archive",
                    "Model Pack contains too many entries. Rebuild it with only declared data.",
                )
            paths.append(path)
        for path in sorted(paths, key=lambda item: item.as_posix()):
            if path.is_symlink():
                relative = path.relative_to(root).as_posix()
                raise _error(
                    "unsafe_package_entry",
                    f"{relative} is a symbolic link. Build the pack again.",
                )
            if path.is_file():
                names.append(path.relative_to(root).as_posix())
            elif not path.is_dir():
                relative = path.relative_to(root).as_posix()
                raise _error(
                    "unsafe_package_entry",
                    f"{relative} is not a regular file or directory. Build the pack again.",
                )
    except ModelPackError:
        raise
    except OSError as exc:
        raise _error(
            "file_read_failed",
            "Could not inspect the Model Pack directory. Check permissions and try again.",
        ) from exc
    return tuple(names)


def _copy_directory_payload(
    source_root: Path,
    destination: Path,
    manifest: ModelPackManifest,
    manifest_payload: bytes,
) -> None:
    """Copy exact declared bytes into a private snapshot through stable handles."""
    current_name = MANIFEST_FILENAME
    try:
        (destination / MANIFEST_FILENAME).write_bytes(manifest_payload)
        copied_bytes = 0
        for file_entry in manifest.files:
            current_name = file_entry.path
            source = source_root / file_entry.path
            digest = hashlib.sha256()
            with _open_regular_payload(
                source,
                file_entry.path,
            ) as (input_file, opened_size):
                if opened_size != file_entry.size_bytes:
                    raise _error(
                        "size_mismatch",
                        (
                            f"{file_entry.path} changed while it was copied. "
                            "Stop modifying the Model Pack and try again."
                        ),
                    )
                _validate_declared_size(file_entry, opened_size)
                target = destination / file_entry.path
                remaining = file_entry.size_bytes
                with target.open("xb") as output_file:
                    while remaining:
                        chunk = input_file.read(min(_HASH_CHUNK_SIZE, remaining))
                        if not chunk:
                            raise _error(
                                "size_mismatch",
                                (
                                    f"{file_entry.path} changed while it was copied. "
                                    "Stop modifying the Model Pack and try again."
                                ),
                            )
                        output_file.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)
                        copied_bytes += len(chunk)
                        if copied_bytes > MAX_MODEL_PACK_BYTES:
                            raise _error(
                                "model_pack_too_large",
                                (
                                    "This Model Pack exceeds the 64 GiB limit. "
                                    "Build or select a smaller pack."
                                ),
                            )
                    if input_file.read(1):
                        raise _error(
                            "size_mismatch",
                            (
                                f"{file_entry.path} changed while it was copied. "
                                "Stop modifying the Model Pack and try again."
                            ),
                        )
            if digest.hexdigest() != file_entry.sha256:
                raise _error(
                    "hash_mismatch",
                    (
                        f"{file_entry.path} failed SHA-256 verification. "
                        "Download or build the pack again."
                    ),
                )
    except ModelPackError:
        raise
    except FileNotFoundError as exc:
        raise _error(
            "missing_file",
            f"Model Pack is missing {current_name}. Download or build the pack again.",
        ) from exc
    except OSError as exc:
        raise _error(
            "file_read_failed",
            "Could not snapshot the Model Pack directory. Check permissions and try again.",
        ) from exc


def _prevalidate_directory_payloads(
    root: Path,
    manifest: ModelPackManifest,
) -> int:
    """Validate source types and actual sizes before disk admission or copying."""
    total_size = 0
    for file_entry in manifest.files:
        path = root / file_entry.path
        try:
            path_stat = path.lstat()
        except FileNotFoundError as exc:
            raise _error(
                "missing_file",
                (
                    f"Model Pack is missing {file_entry.path}. "
                    "Download or build the pack again."
                ),
            ) from exc
        except OSError as exc:
            raise _error(
                "file_read_failed",
                (
                    f"Could not read {file_entry.path}. "
                    "Check file permissions and try again."
                ),
            ) from exc
        if not stat.S_ISREG(path_stat.st_mode):
            raise _error(
                "unsafe_package_entry",
                (
                    f"{file_entry.path} must be a regular file inside the Model Pack. "
                    "Build the pack again."
                ),
            )
        _validate_declared_size(file_entry, path_stat.st_size)
        total_size += path_stat.st_size
        if total_size > MAX_MODEL_PACK_BYTES:
            raise _error(
                "model_pack_too_large",
                (
                    "This Model Pack exceeds the 64 GiB limit. "
                    "Build or select a smaller pack."
                ),
            )
    return total_size


@contextmanager
def _inspect_directory(
    root: Path,
    *,
    disk_usage: DiskUsage,
) -> Iterator[InspectedModelPack]:
    """Inspect a directory through a private immutable snapshot."""
    manifest, manifest_payload = _read_directory_manifest(root)
    _validate_manifest_role_sizes(manifest)
    expected = {MANIFEST_FILENAME, *(entry.path for entry in manifest.files)}
    inventory = _directory_inventory(root)
    warnings = tuple(
        _unexpected_file_warning(name)
        for name in inventory
        if name not in expected
    )
    payload_size = _prevalidate_directory_payloads(root, manifest)
    temp_root = Path(tempfile.gettempdir())
    _check_disk(
        temp_root,
        payload_size=payload_size,
        archive=True,
        disk_usage=disk_usage,
    )
    with tempfile.TemporaryDirectory(prefix="stockpulse-model-pack-") as temp_dir:
        snapshot_root = Path(temp_dir)
        _copy_directory_payload(
            root,
            snapshot_root,
            manifest,
            manifest_payload,
        )
        yield _build_inspection(snapshot_root, manifest, warnings)


def _zip_inventory(archive: ZipFile) -> Dict[str, object]:
    """Build a bounded safe inventory for one ZIP-compatible archive."""
    inventory: Dict[str, object] = {}
    casefold_names = set()
    for entry in archive.infolist():
        if len(inventory) >= MAX_MODEL_PACK_ENTRIES:
            raise _error(
                "invalid_archive",
                "Model Pack contains too many files. Rebuild it with only declared data.",
            )
        if entry.is_dir() or not _safe_archive_name(entry.filename):
            raise _error(
                "unsafe_archive_entry",
                (
                    f"Archive entry {entry.filename!r} is not a safe root-level file. "
                    "Build the pack again."
                ),
            )
        normalized = entry.filename.casefold()
        if normalized in casefold_names:
            raise _error(
                "unsafe_archive_entry",
                "Archive contains duplicate file names. Build the pack again.",
            )
        casefold_names.add(normalized)
        file_type = (entry.external_attr >> 16) & 0o170000
        if file_type == stat.S_IFLNK:
            raise _error(
                "unsafe_archive_entry",
                f"Archive entry {entry.filename!r} is a symbolic link. Build the pack again.",
            )
        inventory[entry.filename] = entry
    return inventory


def _read_zip_manifest(archive: ZipFile, inventory: Dict[str, object]) -> ModelPackManifest:
    """Read the bounded manifest from an already validated ZIP inventory."""
    manifest_info = inventory.get(MANIFEST_FILENAME)
    if manifest_info is None:
        raise _error(
            "missing_manifest",
            "Model Pack is missing manifest.json. Download or build the pack again.",
        )
    if int(getattr(manifest_info, "file_size", 0)) > MAX_MANIFEST_BYTES:
        raise _error(
            "invalid_manifest",
            "manifest.json is too large. Build the pack again with the current tool.",
        )
    try:
        return parse_manifest_bytes(archive.read(manifest_info))
    except ModelPackError:
        raise
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise _error(
            "invalid_archive",
            "Could not read manifest.json from the archive. Download the pack again.",
        ) from exc


def _extract_declared_files(
    archive: ZipFile,
    inventory: Dict[str, object],
    manifest: ModelPackManifest,
    destination: Path,
) -> None:
    """Extract only declared files after size and inventory validation."""
    declared_names = [MANIFEST_FILENAME, *(entry.path for entry in manifest.files)]
    for name in declared_names:
        info = inventory.get(name)
        if info is None:
            raise _error(
                "missing_file",
                f"Model Pack is missing {name}. Download or build the pack again.",
            )
        manifest_entry = next(
            (entry for entry in manifest.files if entry.path == name),
            None,
        )
        if (
            manifest_entry is not None
            and int(getattr(info, "file_size", -1)) != manifest_entry.size_bytes
        ):
            raise _error(
                "size_mismatch",
                f"{name} has the wrong size. Download or build the pack again.",
            )
        target = destination / name
        try:
            with archive.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=_HASH_CHUNK_SIZE)
        except (BadZipFile, OSError, RuntimeError) as exc:
            raise _error(
                "invalid_archive",
                f"Could not extract {name}. Download the pack again.",
            ) from exc


@contextmanager
def _inspect_archive(
    archive_path: Path,
    *,
    disk_usage: DiskUsage,
) -> Iterator[InspectedModelPack]:
    """Inspect one archive through a private extraction directory."""
    try:
        archive = ZipFile(archive_path, "r")
    except (BadZipFile, OSError) as exc:
        raise _error(
            "invalid_archive",
            "The selected file is not a readable Model Pack archive. Download it again.",
        ) from exc
    with archive:
        inventory = _zip_inventory(archive)
        manifest = _read_zip_manifest(archive, inventory)
        _validate_manifest_role_sizes(manifest)
        expected = {MANIFEST_FILENAME, *(entry.path for entry in manifest.files)}
        warnings = tuple(
            _unexpected_file_warning(name)
            for name in sorted(inventory)
            if name not in expected
        )
        payload_size = sum(entry.size_bytes for entry in manifest.files)
        temp_root = Path(tempfile.gettempdir())
        _check_disk(
            temp_root,
            payload_size=payload_size,
            archive=True,
            disk_usage=disk_usage,
        )
        with tempfile.TemporaryDirectory(prefix="stockpulse-model-pack-") as temp_dir:
            extracted_root = Path(temp_dir)
            _extract_declared_files(
                archive,
                inventory,
                manifest,
                extracted_root,
            )
            yield _build_inspection(extracted_root, manifest, warnings)


@contextmanager
def inspect_model_pack(
    source: Path,
    *,
    disk_usage: DiskUsage = shutil.disk_usage,
) -> Iterator[InspectedModelPack]:
    """Validate a Model Pack directory or ZIP-compatible archive."""

    path = Path(source).expanduser()
    try:
        source_stat = path.lstat()
    except FileNotFoundError as exc:
        raise _error(
            "pack_not_found",
            "The selected Model Pack does not exist. Select it again.",
        ) from exc
    except OSError as exc:
        raise _error(
            "file_read_failed",
            "Could not inspect the selected Model Pack. Check permissions and try again.",
        ) from exc
    if stat.S_ISLNK(source_stat.st_mode):
        raise _error(
            "unsafe_package_entry",
            "The selected Model Pack cannot be a symbolic link. Select the original pack.",
        )
    if stat.S_ISDIR(source_stat.st_mode):
        with _inspect_directory(path, disk_usage=disk_usage) as inspected:
            yield inspected
        return
    if not stat.S_ISREG(source_stat.st_mode):
        raise _error(
            "pack_not_found",
            "The selected Model Pack is not a regular file or directory. Select it again.",
        )
    if source_stat.st_size > MAX_MODEL_PACK_BYTES:
        raise _error(
            "model_pack_too_large",
            "This Model Pack exceeds the 64 GiB limit. Build or select a smaller pack.",
        )
    try:
        zip_compatible = is_zipfile(path)
    except OSError as exc:
        raise _error(
            "file_read_failed",
            "Could not read the selected Model Pack. Check permissions and try again.",
        ) from exc
    if not zip_compatible:
        raise _error(
            "unsupported_archive",
            "Select a Model Pack directory, .modelpack file, or ZIP archive.",
        )
    with _inspect_archive(path, disk_usage=disk_usage) as inspected:
        yield inspected


__all__ = [
    "MAX_LICENSE_BYTES",
    "MAX_MODEL_PACK_BYTES",
    "MAX_MODEL_PACK_ENTRIES",
    "inspect_model_pack",
]
