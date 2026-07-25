#!/usr/bin/env python3
"""Build a deterministic StockPulse Model Pack and release checksum."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
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


def _file_entry(path: Path, role: str) -> Dict[str, object]:
    """Build one manifest file entry from a validated source."""
    return {
        "path": path.name,
        "role": role,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
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
) -> Dict[str, object]:
    """Build and validate the canonical manifest for three source files."""
    names = (gguf.name, modelfile.name, license_file.name)
    if len({name.casefold() for name in names}) != len(names):
        raise ModelPackError(
            "duplicate_source_filename",
            "GGUF, Modelfile, and license text must have distinct file names.",
        )
    with gguf.open("rb") as gguf_file:
        gguf_magic = gguf_file.read(4)
    if gguf_magic != b"GGUF":
        raise ModelPackError(
            "invalid_gguf",
            "The selected weight file is not GGUF. Select the correct file and try again.",
        )
    parsed_modelfile = parse_modelfile(
        modelfile.read_bytes(),
        expected_gguf_file=gguf.name,
    )
    if parsed_modelfile.from_file != gguf.name:
        raise ModelPackError(
            "unsafe_modelfile",
            f"Modelfile FROM must reference ./{gguf.name}.",
        )
    try:
        license_file.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ModelPackError(
            "invalid_license_file",
            "The license file must contain UTF-8 text.",
        ) from exc
    if license_file.stat().st_size > MAX_LICENSE_BYTES:
        raise ModelPackError(
            "invalid_license_file",
            f"The license file must not exceed {MAX_LICENSE_BYTES} bytes.",
        )

    manifest: Dict[str, object] = {
        "format_version": MODEL_PACK_FORMAT_VERSION,
        "model_id": model_id,
        "display_name": display_name,
        "gguf_file": gguf.name,
        "modelfile": modelfile.name,
        "license": {"id": license_id, "file": license_file.name},
        "minimum_memory_gb": minimum_memory_gb,
        "files": [
            _file_entry(gguf, "gguf"),
            _file_entry(modelfile, "modelfile"),
            _file_entry(license_file, "license"),
        ],
    }
    parse_manifest(manifest)
    return manifest


def _zip_info(filename: str, *, compression: int) -> ZipInfo:
    """Return deterministic ZIP metadata for one regular file."""
    info = ZipInfo(filename=filename, date_time=_ARCHIVE_TIMESTAMP)
    info.compress_type = compression
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _write_bytes(archive: ZipFile, filename: str, payload: bytes) -> None:
    """Write deterministic compressed bytes to an archive."""
    archive.writestr(
        _zip_info(filename, compression=ZIP_DEFLATED),
        payload,
        compress_type=ZIP_DEFLATED,
        compresslevel=9,
    )


def _write_file(
    archive: ZipFile,
    source: Path,
    *,
    compression: int,
) -> None:
    """Stream one source file into the archive with fixed metadata."""
    info = _zip_info(source.name, compression=compression)
    info.file_size = source.stat().st_size
    with source.open("rb") as input_file, archive.open(
        info,
        "w",
        force_zip64=True,
    ) as output_file:
        shutil.copyfileobj(input_file, output_file, length=_COPY_CHUNK_SIZE)


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
    """Build one validated archive and its release checksum atomically."""
    gguf = _require_regular_file(gguf_path, label="GGUF file")
    modelfile = _require_regular_file(modelfile_path, label="Modelfile")
    license_file = _require_regular_file(license_file_path, label="License file")
    manifest = build_manifest(
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
            _write_file(archive, gguf, compression=ZIP_STORED)
            _write_file(archive, modelfile, compression=ZIP_DEFLATED)
            _write_file(archive, license_file, compression=ZIP_DEFLATED)
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
        os.replace(temporary, destination)
        temporary = None
        os.replace(checksum_temporary, checksum_path)
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
