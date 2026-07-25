#!/usr/bin/env python3
"""Build a deterministic StockPulse Model Pack and release checksum."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.model_pack import (  # noqa: E402
    MAX_LICENSE_BYTES,
    MAX_MODEL_PACK_BYTES,
    MODEL_PACK_FORMAT_VERSION,
    ModelPackError,
    parse_manifest,
    parse_modelfile,
)
from src.model_pack.modelfile import MAX_MODELFILE_BYTES  # noqa: E402


_COPY_CHUNK_SIZE = 1024 * 1024
_ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_OUTPUT_NAME_PATTERN = re.compile(r"[^a-z0-9._-]+")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for one file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(_COPY_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_regular_file(path: Path, *, label: str) -> Path:
    """Resolve one required source while rejecting links and non-files."""
    candidate = path.expanduser()
    try:
        source_stat = candidate.lstat()
    except FileNotFoundError as exc:
        raise ModelPackError(
            "missing_source_file",
            f"{label} does not exist. Select the correct file and try again.",
        ) from exc
    except OSError as exc:
        raise ModelPackError(
            "invalid_source_file",
            f"{label} could not be inspected. Check permissions and try again.",
        ) from exc
    if candidate.is_symlink() or not stat.S_ISREG(source_stat.st_mode):
        raise ModelPackError(
            "invalid_source_file",
            f"{label} must be a regular file, not a directory or symbolic link.",
        )
    return candidate.resolve()


def _default_output_name(model_id: str) -> str:
    """Derive a filesystem-safe default artifact name from a model id."""
    slug = _OUTPUT_NAME_PATTERN.sub("-", model_id.lower()).strip("-._")
    return f"{slug or 'model'}-v{MODEL_PACK_FORMAT_VERSION}.modelpack"


def _validate_output_target(path: Path, *, label: str) -> None:
    """Require an existing publication target to be a replaceable regular file."""
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ModelPackError(
            "invalid_output_path",
            f"{label} could not be inspected. Check permissions and try again.",
        ) from exc
    if path.is_symlink() or not stat.S_ISREG(path_stat.st_mode):
        raise ModelPackError(
            "invalid_output_path",
            f"{label} must be a regular file path, not a directory or symbolic link.",
        )


def _move_existing_to_backup(path: Path, *, label: str) -> Optional[Path]:
    """Move one existing regular output aside for transactional rollback."""
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return None
    if path.is_symlink() or not stat.S_ISREG(path_stat.st_mode):
        raise ModelPackError(
            "invalid_output_path",
            f"{label} must be a regular file path, not a directory or symbolic link.",
        )
    backup_fd, backup_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".bak",
        dir=path.parent,
    )
    os.close(backup_fd)
    backup = Path(backup_name)
    backup.unlink()
    os.replace(path, backup)
    return backup


def _publish_output_pair(
    artifact_temporary: Path,
    checksum_temporary: Path,
    destination: Path,
    checksum_path: Path,
) -> None:
    """Publish both outputs and restore the prior pair on ordinary failures."""
    destination_backup: Optional[Path] = None
    checksum_backup: Optional[Path] = None
    artifact_published = False
    checksum_published = False
    try:
        _validate_output_target(destination, label="Output")
        _validate_output_target(checksum_path, label="Checksum output")
        destination_backup = _move_existing_to_backup(destination, label="Output")
        checksum_backup = _move_existing_to_backup(
            checksum_path,
            label="Checksum output",
        )
        os.replace(artifact_temporary, destination)
        artifact_published = True
        os.replace(checksum_temporary, checksum_path)
        checksum_published = True
    except BaseException as exc:
        rollback_errors = []
        for published, path in (
            (checksum_published, checksum_path),
            (artifact_published, destination),
        ):
            if published:
                try:
                    path.unlink(missing_ok=True)
                except OSError as rollback_error:
                    rollback_errors.append(rollback_error)
        for backup, path in (
            (destination_backup, destination),
            (checksum_backup, checksum_path),
        ):
            if backup is not None:
                try:
                    os.replace(backup, path)
                except OSError as rollback_error:
                    rollback_errors.append(rollback_error)
        if rollback_errors:
            raise ModelPackError(
                "output_publish_failed",
                (
                    "Could not publish or restore the Model Pack outputs. "
                    "Inspect the output directory before trying again."
                ),
            ) from exc
        if isinstance(exc, OSError):
            raise ModelPackError(
                "output_publish_failed",
                (
                    "Could not publish the Model Pack and checksum. "
                    "Check output permissions and try again."
                ),
            ) from exc
        raise
    else:
        for backup in (destination_backup, checksum_backup):
            if backup is not None:
                try:
                    backup.unlink(missing_ok=True)
                except OSError:
                    # Publication is complete; a stale private backup is safer
                    # than reporting failure after the matching pair is live.
                    pass


def _file_entry(path: Path, role: str) -> Dict[str, object]:
    """Build one bounded manifest entry from a stable source-file read."""
    digest = hashlib.sha256()
    prefix = bytearray()
    try:
        path_stat = path.lstat()
        with path.open("rb") as file_obj:
            opened_stat = os.fstat(file_obj.fileno())
            if (
                not stat.S_ISREG(path_stat.st_mode)
                or not stat.S_ISREG(opened_stat.st_mode)
                or (path_stat.st_dev, path_stat.st_ino)
                != (opened_stat.st_dev, opened_stat.st_ino)
            ):
                raise ModelPackError(
                    "invalid_source_file",
                    f"{path.name} changed while it was opened. Stop modifying it and retry.",
                )
            size = opened_stat.st_size
            if size < 1:
                raise ModelPackError(
                    "invalid_source_file",
                    f"{path.name} must not be empty.",
                )
            if size > MAX_MODEL_PACK_BYTES:
                raise ModelPackError(
                    "model_pack_too_large",
                    "A Model Pack source exceeds the 64 GiB limit. Use a smaller file.",
                )
            remaining = size
            while remaining:
                chunk = file_obj.read(min(_COPY_CHUNK_SIZE, remaining))
                if not chunk:
                    raise ModelPackError(
                        "source_changed",
                        f"{path.name} changed while it was read. Stop modifying it and retry.",
                    )
                if len(prefix) < 4:
                    prefix.extend(chunk[: 4 - len(prefix)])
                digest.update(chunk)
                remaining -= len(chunk)
            if file_obj.read(1):
                raise ModelPackError(
                    "source_changed",
                    f"{path.name} changed while it was read. Stop modifying it and retry.",
                )
    except ModelPackError:
        raise
    except OSError as exc:
        raise ModelPackError(
            "invalid_source_file",
            f"{path.name} could not be read. Check permissions and try again.",
        ) from exc
    if role == "gguf" and bytes(prefix) != b"GGUF":
        raise ModelPackError(
            "invalid_gguf",
            "The selected weight file is not GGUF. Select the correct file and try again.",
        )
    return {
        "path": path.name,
        "role": role,
        "sha256": digest.hexdigest(),
        "size_bytes": size,
    }


def _bytes_entry(path: Path, role: str, payload: bytes) -> Dict[str, object]:
    """Build one manifest entry from the exact canonical bytes to be archived."""
    return {
        "path": path.name,
        "role": role,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def build_manifest(
    *,
    gguf: Path,
    modelfile: Path,
    license_file: Path,
    model_id: str,
    display_name: str,
    license_id: str,
    minimum_memory_gb: int,
) -> Tuple[Dict[str, object], bytes, bytes]:
    """Build the manifest and retain canonical bounded text payload bytes."""
    names = (gguf.name, modelfile.name, license_file.name)
    if len({name.casefold() for name in names}) != len(names):
        raise ModelPackError(
            "duplicate_source_filename",
            "GGUF, Modelfile, and license text must have distinct file names.",
        )
    gguf_entry = _file_entry(gguf, "gguf")
    if modelfile.stat().st_size > MAX_MODELFILE_BYTES:
        raise ModelPackError(
            "unsafe_modelfile",
            f"Modelfile must not exceed {MAX_MODELFILE_BYTES} bytes. "
            "Reduce it and rebuild the pack.",
        )
    with modelfile.open("rb") as modelfile_source:
        modelfile_bytes = modelfile_source.read(MAX_MODELFILE_BYTES + 1)
    if len(modelfile_bytes) > MAX_MODELFILE_BYTES:
        raise ModelPackError(
            "unsafe_modelfile",
            f"Modelfile must not exceed {MAX_MODELFILE_BYTES} bytes. "
            "Reduce it and rebuild the pack.",
        )
    parsed_modelfile = parse_modelfile(
        modelfile_bytes,
        expected_gguf_file=gguf.name,
    )
    if parsed_modelfile.from_file != gguf.name:
        raise ModelPackError(
            "unsafe_modelfile",
            f"Modelfile FROM must reference ./{gguf.name}.",
        )
    if license_file.stat().st_size > MAX_LICENSE_BYTES:
        raise ModelPackError(
            "invalid_license_file",
            f"The license file must not exceed {MAX_LICENSE_BYTES} bytes.",
        )
    with license_file.open("rb") as license_source:
        license_bytes = license_source.read(MAX_LICENSE_BYTES + 1)
    if len(license_bytes) > MAX_LICENSE_BYTES:
        raise ModelPackError(
            "invalid_license_file",
            f"The license file must not exceed {MAX_LICENSE_BYTES} bytes.",
        )
    try:
        license_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ModelPackError(
            "invalid_license_file",
            "The license file must contain UTF-8 text.",
        ) from exc

    manifest: Dict[str, object] = {
        "format_version": MODEL_PACK_FORMAT_VERSION,
        "model_id": model_id,
        "display_name": display_name,
        "gguf_file": gguf.name,
        "modelfile": modelfile.name,
        "license": {"id": license_id, "file": license_file.name},
        "minimum_memory_gb": minimum_memory_gb,
        "files": [
            gguf_entry,
            _bytes_entry(modelfile, "modelfile", modelfile_bytes),
            _bytes_entry(license_file, "license", license_bytes),
        ],
    }
    parse_manifest(manifest)
    return manifest, modelfile_bytes, license_bytes


def _zip_info(filename: str, *, compression: int) -> ZipInfo:
    """Return deterministic ZIP metadata for one regular file."""
    info = ZipInfo(filename=filename, date_time=_ARCHIVE_TIMESTAMP)
    info.compress_type = compression
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _write_bytes(
    archive: ZipFile,
    filename: str,
    payload: bytes,
    *,
    compression: int = ZIP_DEFLATED,
) -> None:
    """Write exact deterministic bytes to an archive."""
    compresslevel = 9 if compression == ZIP_DEFLATED else None
    archive.writestr(
        _zip_info(filename, compression=compression),
        payload,
        compress_type=compression,
        compresslevel=compresslevel,
    )


def _write_file(
    archive: ZipFile,
    source: Path,
    *,
    compression: int,
    expected_size: int,
    expected_sha256: str,
) -> None:
    """Stream exactly the declared bytes and reject a changing source."""
    digest = hashlib.sha256()
    try:
        path_stat = source.lstat()
        with source.open("rb") as input_file:
            opened_stat = os.fstat(input_file.fileno())
            if (
                not stat.S_ISREG(path_stat.st_mode)
                or not stat.S_ISREG(opened_stat.st_mode)
                or (path_stat.st_dev, path_stat.st_ino)
                != (opened_stat.st_dev, opened_stat.st_ino)
                or opened_stat.st_size != expected_size
            ):
                raise ModelPackError(
                    "source_changed",
                    f"{source.name} changed while the pack was built. Stop modifying it and retry.",
                )
            info = _zip_info(source.name, compression=compression)
            info.file_size = expected_size
            with archive.open(info, "w", force_zip64=True) as output_file:
                remaining = expected_size
                while remaining:
                    chunk = input_file.read(min(_COPY_CHUNK_SIZE, remaining))
                    if not chunk:
                        raise ModelPackError(
                            "source_changed",
                            (
                                f"{source.name} changed while the pack was built. "
                                "Stop modifying it and retry."
                            ),
                        )
                    output_file.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
                if input_file.read(1):
                    raise ModelPackError(
                        "source_changed",
                        (
                            f"{source.name} changed while the pack was built. "
                            "Stop modifying it and retry."
                        ),
                    )
    except ModelPackError:
        raise
    except OSError as exc:
        raise ModelPackError(
            "invalid_source_file",
            f"{source.name} could not be read. Check permissions and try again.",
        ) from exc
    if digest.hexdigest() != expected_sha256:
        raise ModelPackError(
            "source_changed",
            f"{source.name} changed while the pack was built. Stop modifying it and retry.",
        )


def build_model_pack(
    *,
    gguf_path: Path,
    modelfile_path: Path,
    license_file_path: Path,
    model_id: str,
    display_name: str,
    license_id: str,
    minimum_memory_gb: int,
    output_path: Optional[Path] = None,
) -> Tuple[Path, Path]:
    """Build one validated archive and publish it with a matching checksum."""
    gguf = _require_regular_file(gguf_path, label="GGUF file")
    modelfile = _require_regular_file(modelfile_path, label="Modelfile")
    license_file = _require_regular_file(license_file_path, label="License file")
    manifest, modelfile_bytes, license_bytes = build_manifest(
        gguf=gguf,
        modelfile=modelfile,
        license_file=license_file,
        model_id=model_id,
        display_name=display_name,
        license_id=license_id,
        minimum_memory_gb=minimum_memory_gb,
    )

    destination = (
        output_path.expanduser()
        if output_path is not None
        else Path.cwd() / _default_output_name(model_id)
    ).resolve()
    if destination.suffix.lower() not in {".modelpack", ".zip"}:
        raise ModelPackError(
            "invalid_output_path",
            "Output must use the .modelpack or .zip extension.",
        )
    checksum_path = destination.with_name(f"{destination.name}.sha256")
    sources = {gguf, modelfile, license_file}
    if destination in sources or checksum_path in sources:
        raise ModelPackError(
            "invalid_output_path",
            "Output and checksum paths cannot overwrite a Model Pack source file.",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    _validate_output_target(destination, label="Output")
    _validate_output_target(checksum_path, label="Checksum output")
    temporary: Optional[Path] = None
    checksum_temporary: Optional[Path] = None

    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        + b"\n"
    )
    try:
        artifact_fd, artifact_temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(artifact_temp_name)
        os.close(artifact_fd)
        checksum_fd, checksum_temp_name = tempfile.mkstemp(
            prefix=f".{checksum_path.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        checksum_temporary = Path(checksum_temp_name)
        os.close(checksum_fd)
        with ZipFile(temporary, "w", allowZip64=True) as archive:
            _write_bytes(archive, "manifest.json", manifest_bytes)
            gguf_entry = next(
                entry for entry in manifest["files"] if entry["role"] == "gguf"
            )
            _write_file(
                archive,
                gguf,
                compression=ZIP_STORED,
                expected_size=int(gguf_entry["size_bytes"]),
                expected_sha256=str(gguf_entry["sha256"]),
            )
            _write_bytes(
                archive,
                modelfile.name,
                modelfile_bytes,
            )
            _write_bytes(
                archive,
                license_file.name,
                license_bytes,
            )
        if temporary.stat().st_size > MAX_MODEL_PACK_BYTES:
            raise ModelPackError(
                "model_pack_too_large",
                "The completed Model Pack exceeds the 64 GiB limit. "
                "Use smaller source files and build it again.",
            )
        artifact_digest = sha256_file(temporary)
        checksum_temporary.write_text(
            f"{artifact_digest}  {destination.name}\n",
            encoding="ascii",
        )
        _publish_output_pair(
            temporary,
            checksum_temporary,
            destination,
            checksum_path,
        )
        temporary = None
        checksum_temporary = None
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if checksum_temporary is not None:
            checksum_temporary.unlink(missing_ok=True)
        raise
    return destination, checksum_path


def _parser() -> argparse.ArgumentParser:
    """Create the release-builder command-line parser."""
    parser = argparse.ArgumentParser(
        description="Build a deterministic StockPulse Model Pack.",
    )
    parser.add_argument("--gguf", required=True, type=Path, help="GGUF weight file")
    parser.add_argument("--modelfile", required=True, type=Path, help="Constrained Modelfile")
    parser.add_argument("--license-file", required=True, type=Path, help="UTF-8 license text")
    parser.add_argument("--model-id", required=True, help="Ollama model id for import")
    parser.add_argument("--display-name", required=True, help="User-visible model name")
    parser.add_argument("--license-id", required=True, help="SPDX id or LicenseRef")
    parser.add_argument(
        "--minimum-memory-gb",
        required=True,
        type=int,
        help="Minimum system-memory tier in GiB",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output .modelpack path; defaults to a model-id-derived name",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the release builder and return a stable process exit code."""
    args = _parser().parse_args(argv)
    try:
        artifact, checksum = build_model_pack(
            gguf_path=args.gguf,
            modelfile_path=args.modelfile,
            license_file_path=args.license_file,
            model_id=args.model_id,
            display_name=args.display_name,
            license_id=args.license_id,
            minimum_memory_gb=args.minimum_memory_gb,
            output_path=args.output,
        )
    except ModelPackError as exc:
        print(f"error: {exc.user_message}", file=sys.stderr)
        return 2
    except OSError:
        print(
            "error: Could not write the Model Pack. Check disk space and permissions.",
            file=sys.stderr,
        )
        return 1
    print(f"Model Pack: {artifact}")
    print(f"SHA-256: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
