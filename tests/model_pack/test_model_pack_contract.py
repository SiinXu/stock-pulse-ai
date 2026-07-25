from __future__ import annotations

import hashlib
import json
import shutil
import stat
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

import src.model_pack.validation as model_pack_validation
from src.model_pack import (
    MAX_LICENSE_BYTES,
    MAX_MODEL_PACK_ENTRIES,
    MAX_MODEL_PACK_BYTES,
    ModelPackError,
    ModelPackImporter,
    inspect_model_pack,
    parse_manifest,
)
from src.model_pack.manifest import MAX_MANIFEST_BYTES
from src.model_pack.modelfile import MAX_MODELFILE_BYTES


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_pack(
    root: Path,
    *,
    format_version: int = 1,
    modelfile: str = "FROM ./weights.gguf\nPARAMETER temperature 0.2\n",
    include_license: bool = True,
    tamper_gguf: bool = False,
) -> Path:
    root.mkdir(parents=True)
    gguf_path = root / "weights.gguf"
    modelfile_path = root / "Modelfile"
    license_path = root / "LICENSE"
    gguf_path.write_bytes(b"GGUF-test-weights")
    modelfile_path.write_text(modelfile, encoding="utf-8")
    if include_license:
        license_path.write_text("Test license text\n", encoding="utf-8")

    files = [
        {
            "path": "weights.gguf",
            "role": "gguf",
            "sha256": _sha256(gguf_path),
            "size_bytes": gguf_path.stat().st_size,
        },
        {
            "path": "Modelfile",
            "role": "modelfile",
            "sha256": _sha256(modelfile_path),
            "size_bytes": modelfile_path.stat().st_size,
        },
        {
            "path": "LICENSE",
            "role": "license",
            "sha256": _sha256(license_path) if include_license else "0" * 64,
            "size_bytes": license_path.stat().st_size if include_license else 18,
        },
    ]
    manifest = {
        "format_version": format_version,
        "model_id": "stockpulse-test:latest",
        "display_name": "StockPulse Test Model",
        "gguf_file": "weights.gguf",
        "modelfile": "Modelfile",
        "license": {"id": "LicenseRef-Test", "file": "LICENSE"},
        "minimum_memory_gb": 8,
        "files": files,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    if tamper_gguf:
        gguf_path.write_bytes(b"GGUF-evil-weights")
    return root


def _zip_pack(source: Path, destination: Path, *, unsafe_entry: str | None = None) -> Path:
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(source.iterdir(), key=lambda item: item.name):
            archive.write(path, arcname=path.name)
        if unsafe_entry is not None:
            archive.writestr(unsafe_entry, b"escape")
    return destination


def _assert_error(error: pytest.ExceptionInfo[ModelPackError], code: str, advice: str) -> None:
    assert error.value.code == code
    assert advice in error.value.user_message
    assert error.value.user_message


def test_inspect_valid_directory_verifies_real_files_and_reports_extras(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path / "pack")
    (pack_path / "release-notes.txt").write_text("extra", encoding="utf-8")

    with inspect_model_pack(pack_path) as inspected:
        assert inspected.manifest.model_id == "stockpulse-test:latest"
        assert inspected.manifest.minimum_memory_gb == 8
        assert inspected.gguf_path.read_bytes() == b"GGUF-test-weights"
        assert inspected.modelfile.from_file == "weights.gguf"
        assert inspected.modelfile.parameters == {"temperature": 0.2}
        assert inspected.warnings == (
            "Unexpected file is not part of the manifest: release-notes.txt",
        )


def test_manifest_rejects_declared_payloads_above_the_shared_limit(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path / "oversized")
    manifest_path = pack_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["size_bytes"] = MAX_MODEL_PACK_BYTES + 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(pack_path):
            pass

    _assert_error(error, "model_pack_too_large", "64 GiB")


def test_directory_rejects_an_unbounded_extra_file_inventory(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path / "too-many-files")
    for index in range(MAX_MODEL_PACK_ENTRIES):
        (pack_path / f"extra-{index:03d}").write_text("x", encoding="utf-8")

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(pack_path):
            pass

    _assert_error(error, "invalid_archive", "too many entries")


def test_directory_counts_empty_directories_toward_the_inventory_limit(
    tmp_path: Path,
) -> None:
    pack_path = _write_pack(tmp_path / "too-many-directories")
    for index in range(MAX_MODEL_PACK_ENTRIES):
        (pack_path / f"empty-{index:03d}").mkdir()

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(pack_path):
            pass

    _assert_error(error, "invalid_archive", "too many entries")


def test_manifest_reserves_its_own_filename_for_the_metadata_entry(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path / "reserved-manifest")
    manifest = json.loads((pack_path / "manifest.json").read_text(encoding="utf-8"))
    manifest["modelfile"] = "Manifest.json"
    manifest["files"][1]["path"] = "Manifest.json"

    with pytest.raises(ModelPackError) as error:
        parse_manifest(manifest)

    _assert_error(error, "invalid_manifest", "reserved manifest.json")


def test_inspect_directory_uses_a_private_snapshot_until_cleanup(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path / "pack")

    with inspect_model_pack(pack_path) as inspected:
        snapshot_root = inspected.root
        assert snapshot_root != pack_path
        (pack_path / "weights.gguf").write_bytes(b"GGUF-replaced-after-validation")
        (pack_path / "Modelfile").write_text(
            "FROM /private/outside.gguf\n",
            encoding="utf-8",
        )
        assert inspected.gguf_path.read_bytes() == b"GGUF-test-weights"
        assert inspected.modelfile_path.read_text(encoding="utf-8").startswith(
            "FROM ./weights.gguf"
        )

    assert not snapshot_root.exists()


def test_directory_rejects_actual_size_before_snapshot_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pack_path = _write_pack(tmp_path / "declared-size-mismatch")
    (pack_path / "weights.gguf").write_bytes(b"GGUF" + b"x" * (4 * 1024 * 1024))

    def reject_snapshot(*_args, **_kwargs) -> None:
        raise AssertionError("a size mismatch must fail before snapshot copying")

    monkeypatch.setattr(
        model_pack_validation,
        "_copy_directory_payload",
        reject_snapshot,
    )

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(pack_path):
            pass

    _assert_error(error, "size_mismatch", "Download or build the pack again")


def test_directory_rejects_growth_between_preflight_and_bounded_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pack_path = _write_pack(tmp_path / "growing-payload")
    gguf_path = pack_path / "weights.gguf"

    def grow_after_preflight(*_args, **_kwargs) -> None:
        with gguf_path.open("ab") as file_obj:
            file_obj.write(b"x" * (4 * 1024 * 1024))

    monkeypatch.setattr(model_pack_validation, "_check_disk", grow_after_preflight)

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(pack_path):
            pass

    _assert_error(error, "size_mismatch", "Stop modifying the Model Pack")


def test_directory_manifest_growth_is_read_with_a_hard_byte_bound(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pack_path = _write_pack(tmp_path / "growing-manifest")
    manifest_path = pack_path / "manifest.json"
    original_open = Path.open

    class BoundedReader:
        def __init__(self, file_obj) -> None:
            self._file_obj = file_obj

        def fileno(self) -> int:
            return self._file_obj.fileno()

        def read(self, size: int = -1) -> bytes:
            assert size == MAX_MANIFEST_BYTES + 1
            return self._file_obj.read(size)

        def close(self) -> None:
            self._file_obj.close()

    def open_with_growth(path: Path, *args, **kwargs):
        file_obj = original_open(path, *args, **kwargs)
        if path == manifest_path and args and args[0] == "rb":
            with original_open(manifest_path, "ab") as output:
                output.write(b"x" * (MAX_MANIFEST_BYTES + 1))
            return BoundedReader(file_obj)
        return file_obj

    monkeypatch.setattr(Path, "open", open_with_growth)

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(pack_path):
            pass

    _assert_error(error, "invalid_manifest", "too large")


@pytest.mark.parametrize(
    ("role", "limit", "code"),
    [
        ("modelfile", MAX_MODELFILE_BYTES, "unsafe_modelfile"),
        ("license", MAX_LICENSE_BYTES, "invalid_license_file"),
    ],
)
def test_archive_rejects_declared_role_size_before_extraction(
    tmp_path: Path,
    monkeypatch,
    role: str,
    limit: int,
    code: str,
) -> None:
    source = _write_pack(tmp_path / role)
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["role"] == role)
    entry["size_bytes"] = limit + 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    archive = _zip_pack(source, tmp_path / f"{role}.modelpack")

    def reject_extraction(*_args, **_kwargs) -> None:
        raise AssertionError("an oversized role must fail before extraction")

    monkeypatch.setattr(
        model_pack_validation,
        "_extract_declared_files",
        reject_extraction,
    )

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(archive):
            pass

    _assert_error(error, code, "limit")


def test_inspect_valid_archive_extracts_only_declared_data(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    archive = _zip_pack(source, tmp_path / "stockpulse-test.modelpack")

    with inspect_model_pack(archive) as inspected:
        extracted_root = inspected.root
        assert extracted_root != source
        assert inspected.gguf_path.is_file()
        assert inspected.license_path.read_text(encoding="utf-8") == "Test license text\n"

    assert not extracted_root.exists()


@pytest.mark.parametrize(
    ("mutator", "code", "advice"),
    [
        (
            lambda root: (root / "manifest.json").write_text(
                (root / "manifest.json")
                .read_text(encoding="utf-8")
                .replace('"format_version": 1', '"format_version": 99'),
                encoding="utf-8",
            ),
            "unsupported_format_version",
            "Update StockPulse",
        ),
        (
            lambda root: (root / "LICENSE").unlink(),
            "missing_file",
            "Download or build the pack again",
        ),
        (
            lambda root: (root / "weights.gguf").write_bytes(b"GGUF-evil-weights"),
            "hash_mismatch",
            "Download or build the pack again",
        ),
        (
            lambda root: (root / "Modelfile").write_text(
                "FROM ../outside.gguf\n",
                encoding="utf-8",
            ),
            "size_mismatch",
            "Download or build the pack again",
        ),
    ],
)
def test_inspect_rejects_invalid_payloads_before_import(
    tmp_path: Path,
    mutator,
    code: str,
    advice: str,
) -> None:
    pack_path = _write_pack(tmp_path / "pack")
    mutator(pack_path)

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(pack_path):
            pass

    _assert_error(error, code, advice)


def test_inspect_rejects_external_from_after_real_hash_validation(tmp_path: Path) -> None:
    pack_path = _write_pack(
        tmp_path / "pack",
        modelfile="FROM /Users/example/private.gguf\n",
    )

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(pack_path):
            pass

    _assert_error(error, "unsafe_modelfile", "FROM must reference weights.gguf")


def test_inspect_rejects_non_utf8_license_before_create(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path / "pack")
    license_path = pack_path / "LICENSE"
    license_path.write_bytes(b"\xff\xfe")
    manifest = json.loads((pack_path / "manifest.json").read_text(encoding="utf-8"))
    license_entry = next(entry for entry in manifest["files"] if entry["role"] == "license")
    license_entry["sha256"] = _sha256(license_path)
    license_entry["size_bytes"] = license_path.stat().st_size
    (pack_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(pack_path):
            pass

    _assert_error(error, "invalid_license_file", "UTF-8 text")


def test_inspect_rejects_a_top_level_symbolic_link(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path / "pack")
    linked_path = tmp_path / "linked-pack"
    linked_path.symlink_to(pack_path, target_is_directory=True)

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(linked_path):
            pass

    _assert_error(error, "unsafe_package_entry", "symbolic link")


@pytest.mark.parametrize(
    "directive",
    [
        "ADAPTER ./adapter.gguf",
        "LICENSE ./OTHER-LICENSE",
        "MESSAGE user hello",
    ],
)
def test_inspect_rejects_modelfile_directives_outside_the_data_only_subset(
    tmp_path: Path,
    directive: str,
) -> None:
    pack_path = _write_pack(
        tmp_path / directive.split()[0].lower(),
        modelfile=f"FROM ./weights.gguf\n{directive}\n",
    )

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(pack_path):
            pass

    _assert_error(error, "unsafe_modelfile", "Remove the unsupported instruction")


def test_inspect_rejects_archive_path_escape(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    archive = _zip_pack(
        source,
        tmp_path / "unsafe.modelpack",
        unsafe_entry="../outside.txt",
    )

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(archive):
            pass

    _assert_error(error, "unsafe_archive_entry", "Build the pack again")
    assert not (tmp_path / "outside.txt").exists()


def test_inspect_rejects_archive_directory_path_escape(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    archive = _zip_pack(source, tmp_path / "unsafe-directory.modelpack")
    with ZipFile(archive, "a") as zip_file:
        zip_file.writestr("../outside/", b"")

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(archive):
            pass

    _assert_error(error, "unsafe_archive_entry", "Build the pack again")


def test_inspect_rejects_duplicate_archive_names(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    archive = _zip_pack(source, tmp_path / "duplicate.modelpack")
    with pytest.warns(UserWarning, match="Duplicate name"):
        with ZipFile(archive, "a") as zip_file:
            zip_file.writestr("LICENSE", b"duplicate")

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(archive):
            pass

    _assert_error(error, "unsafe_archive_entry", "duplicate file names")


def test_inspect_rejects_undeclared_archive_symbolic_links(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    archive = _zip_pack(source, tmp_path / "symlink.modelpack")
    symlink = ZipInfo("license-link")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(archive, "a") as zip_file:
        zip_file.writestr(symlink, b"LICENSE")

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(archive):
            pass

    _assert_error(error, "unsafe_archive_entry", "symbolic link")


def test_inspect_rejects_insufficient_disk_before_archive_extraction(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source")
    archive = _zip_pack(source, tmp_path / "stockpulse-test.modelpack")

    def no_free_space(_path: Path):
        usage = shutil.disk_usage(tmp_path)
        return usage._replace(free=0)

    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(archive, disk_usage=no_free_space):
            pass

    _assert_error(error, "insufficient_disk_space", "Free at least")


def test_importer_validates_then_creates_and_registers_the_model(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path / "pack")
    events: list[tuple[str, object]] = []

    class RecordingExecutor:
        def create(self, inspected, *, on_progress=None):
            assert inspected.gguf_path.read_bytes() == b"GGUF-test-weights"
            assert inspected.modelfile.parameters == {"temperature": 0.2}
            events.append(("create", inspected.manifest.model_id))
            if on_progress is not None:
                on_progress(80, "Creating the Ollama model")

    def register(model_id: str):
        events.append(("register", model_id))
        return {"models": model_id}

    result = ModelPackImporter(
        executor=RecordingExecutor(),
        register_model=register,
    ).import_pack(
        pack_path,
        on_progress=lambda progress, message: events.append(
            ("progress", (progress, message))
        ),
    )

    assert result.model_id == "stockpulse-test:latest"
    assert result.display_name == "StockPulse Test Model"
    assert result.minimum_memory_gb == 8
    assert result.activated is True
    assert result.selected_primary is False
    assert events == [
        ("create", "stockpulse-test:latest"),
        ("progress", (80, "Creating the Ollama model")),
        ("register", "stockpulse-test:latest"),
    ]


def test_importer_never_calls_ollama_or_registration_when_validation_fails(
    tmp_path: Path,
) -> None:
    pack_path = _write_pack(tmp_path / "pack", tamper_gguf=True)
    calls: list[str] = []

    class ForbiddenExecutor:
        def create(self, _inspected, *, on_progress=None):
            calls.append("create")

    with pytest.raises(ModelPackError) as error:
        ModelPackImporter(
            executor=ForbiddenExecutor(),
            register_model=lambda _model_id: calls.append("register"),
        ).import_pack(pack_path)

    assert error.value.code == "hash_mismatch"
    assert calls == []
