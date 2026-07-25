from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, Mapping

from src.model_pack.errors import ModelPackError
from src.model_pack.models import ModelPackFile, ModelPackLicense, ModelPackManifest


MODEL_PACK_FORMAT_VERSION = 1
MANIFEST_FILENAME = "manifest.json"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_MODEL_PACK_BYTES = 64 * 1024 * 1024 * 1024
MAX_METADATA_TEXT_LENGTH = 160
MODEL_ID_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)?"
    r"(?::[a-z0-9]+(?:[._-][a-z0-9]+)*)?$",
    re.IGNORECASE,
)
SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LICENSE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]{0,127}$")
REQUIRED_FILE_ROLES = frozenset({"gguf", "modelfile", "license"})

_MANIFEST_KEYS = frozenset(
    {
        "format_version",
        "model_id",
        "display_name",
        "gguf_file",
        "modelfile",
        "license",
        "minimum_memory_gb",
        "files",
    }
)
_LICENSE_KEYS = frozenset({"id", "file"})
_FILE_KEYS = frozenset({"path", "role", "sha256", "size_bytes"})


def _invalid_manifest(message: str) -> ModelPackError:
    """Return one actionable strict-manifest validation error."""
    return ModelPackError(
        "invalid_manifest",
        f"manifest.json is invalid: {message}. Build the pack again with the current tool.",
    )


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: Iterable[str],
    *,
    location: str,
) -> None:
    """Require an object to contain exactly the allowed keys."""
    expected_keys = set(expected)
    actual_keys = set(value)
    missing = sorted(expected_keys - actual_keys)
    extra = sorted(actual_keys - expected_keys)
    if missing:
        raise _invalid_manifest(f"{location} is missing {', '.join(missing)}")
    if extra:
        raise _invalid_manifest(f"{location} has unsupported fields {', '.join(extra)}")


def _require_text(
    value: Any,
    *,
    field_name: str,
    max_length: int = MAX_METADATA_TEXT_LENGTH,
) -> str:
    """Normalize one bounded visible metadata string."""
    if not isinstance(value, str):
        raise _invalid_manifest(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise _invalid_manifest(
            f"{field_name} must contain between 1 and {max_length} characters"
        )
    if any(ord(character) < 32 for character in normalized):
        raise _invalid_manifest(f"{field_name} contains control characters")
    return normalized


def validate_pack_filename(value: Any, *, field_name: str) -> str:
    """Validate one root-level portable payload filename."""
    filename = _require_text(value, field_name=field_name, max_length=128)
    if not SAFE_FILENAME_PATTERN.fullmatch(filename) or filename in {".", ".."}:
        raise _invalid_manifest(f"{field_name} must be a root-level safe filename")
    return filename


def parse_manifest_bytes(payload: bytes) -> ModelPackManifest:
    """Decode and parse one bounded UTF-8 JSON manifest."""
    if not payload or len(payload) > MAX_MANIFEST_BYTES:
        raise _invalid_manifest(
            f"manifest.json must contain between 1 and {MAX_MANIFEST_BYTES} bytes"
        )
    try:
        decoded = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _invalid_manifest("manifest.json must use UTF-8") from exc
    try:
        raw = json.loads(decoded)
    except (json.JSONDecodeError, ValueError) as exc:
        raise _invalid_manifest("manifest.json must contain valid JSON") from exc
    if not isinstance(raw, dict):
        raise _invalid_manifest("the root value must be an object")
    return parse_manifest(raw)


def parse_manifest(raw: Mapping[str, Any]) -> ModelPackManifest:
    """Parse one strict format-v1 manifest without accepting extra fields."""
    _require_exact_keys(raw, _MANIFEST_KEYS, location="the manifest")

    format_version = raw.get("format_version")
    if not isinstance(format_version, int) or isinstance(format_version, bool):
        raise _invalid_manifest("format_version must be an integer")
    if format_version != MODEL_PACK_FORMAT_VERSION:
        raise ModelPackError(
            "unsupported_format_version",
            (
                f"This Model Pack uses format version {format_version}. "
                f"Update StockPulse or use a version {MODEL_PACK_FORMAT_VERSION} pack."
            ),
            details={
                "actual_version": format_version,
                "supported_versions": [MODEL_PACK_FORMAT_VERSION],
            },
        )

    model_id = _require_text(raw.get("model_id"), field_name="model_id", max_length=96)
    if not MODEL_ID_PATTERN.fullmatch(model_id):
        raise _invalid_manifest("model_id is not a valid Ollama model name")

    display_name = _require_text(raw.get("display_name"), field_name="display_name")
    gguf_file = validate_pack_filename(raw.get("gguf_file"), field_name="gguf_file")
    if not gguf_file.lower().endswith(".gguf"):
        raise _invalid_manifest("gguf_file must end in .gguf")
    modelfile = validate_pack_filename(raw.get("modelfile"), field_name="modelfile")

    raw_license = raw.get("license")
    if not isinstance(raw_license, dict):
        raise _invalid_manifest("license must be an object")
    _require_exact_keys(raw_license, _LICENSE_KEYS, location="license")
    license_id = _require_text(
        raw_license.get("id"),
        field_name="license.id",
        max_length=128,
    )
    if not LICENSE_ID_PATTERN.fullmatch(license_id):
        raise _invalid_manifest("license.id must be an SPDX id or LicenseRef identifier")
    license_file = validate_pack_filename(
        raw_license.get("file"),
        field_name="license.file",
    )

    minimum_memory_gb = raw.get("minimum_memory_gb")
    if (
        not isinstance(minimum_memory_gb, int)
        or isinstance(minimum_memory_gb, bool)
        or not 1 <= minimum_memory_gb <= 2048
    ):
        raise _invalid_manifest("minimum_memory_gb must be an integer from 1 to 2048")

    raw_files = raw.get("files")
    if not isinstance(raw_files, list) or len(raw_files) != len(REQUIRED_FILE_ROLES):
        raise _invalid_manifest("files must list exactly one gguf, modelfile, and license")

    files = []
    seen_paths = set()
    seen_roles = set()
    for index, raw_file in enumerate(raw_files):
        if not isinstance(raw_file, dict):
            raise _invalid_manifest(f"files[{index}] must be an object")
        _require_exact_keys(raw_file, _FILE_KEYS, location=f"files[{index}]")
        path = validate_pack_filename(
            raw_file.get("path"),
            field_name=f"files[{index}].path",
        )
        if path.casefold() == MANIFEST_FILENAME.casefold():
            raise _invalid_manifest(
                f"files[{index}].path cannot use the reserved manifest.json name"
            )
        role = _require_text(
            raw_file.get("role"),
            field_name=f"files[{index}].role",
            max_length=16,
        )
        if role not in REQUIRED_FILE_ROLES:
            raise _invalid_manifest(f"files[{index}].role is unsupported")
        digest = _require_text(
            raw_file.get("sha256"),
            field_name=f"files[{index}].sha256",
            max_length=64,
        ).lower()
        if not SHA256_PATTERN.fullmatch(digest):
            raise _invalid_manifest(f"files[{index}].sha256 must be 64 lowercase hex characters")
        size_bytes = raw_file.get("size_bytes")
        if (
            not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 1
        ):
            raise _invalid_manifest(f"files[{index}].size_bytes must be a positive integer")
        if path.casefold() in seen_paths:
            raise _invalid_manifest("files contains duplicate paths")
        if role in seen_roles:
            raise _invalid_manifest(f"files contains more than one {role} entry")
        seen_paths.add(path.casefold())
        seen_roles.add(role)
        files.append(
            ModelPackFile(
                path=path,
                role=role,
                sha256=digest,
                size_bytes=size_bytes,
            )
        )

    if seen_roles != REQUIRED_FILE_ROLES:
        raise _invalid_manifest("files must include gguf, modelfile, and license roles")
    if sum(entry.size_bytes for entry in files) > MAX_MODEL_PACK_BYTES:
        raise ModelPackError(
            "model_pack_too_large",
            "This Model Pack exceeds the 64 GiB limit. Build or select a smaller pack.",
        )
    role_paths: Dict[str, str] = {entry.role: entry.path for entry in files}
    if role_paths["gguf"] != gguf_file:
        raise _invalid_manifest("gguf_file must match the file with role gguf")
    if role_paths["modelfile"] != modelfile:
        raise _invalid_manifest("modelfile must match the file with role modelfile")
    if role_paths["license"] != license_file:
        raise _invalid_manifest("license.file must match the file with role license")

    return ModelPackManifest(
        format_version=format_version,
        model_id=model_id,
        display_name=display_name,
        gguf_file=gguf_file,
        modelfile=modelfile,
        license=ModelPackLicense(id=license_id, file=license_file),
        minimum_memory_gb=minimum_memory_gb,
        files=tuple(files),
    )


__all__ = [
    "MANIFEST_FILENAME",
    "MAX_MANIFEST_BYTES",
    "MAX_MODEL_PACK_BYTES",
    "MODEL_PACK_FORMAT_VERSION",
    "MODEL_ID_PATTERN",
    "parse_manifest",
    "parse_manifest_bytes",
    "validate_pack_filename",
]
