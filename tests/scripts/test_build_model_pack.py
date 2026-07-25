from __future__ import annotations

import hashlib
import os
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import pytest

import scripts.build_model_pack as model_pack_builder
from scripts.build_model_pack import build_model_pack, main
from src.model_pack import MAX_LICENSE_BYTES, ModelPackError, inspect_model_pack
from src.model_pack.modelfile import MAX_MODELFILE_BYTES


def _sources(root: Path):
    gguf = root / "weights.gguf"
    modelfile = root / "Modelfile"
    license_file = root / "LICENSE"
    gguf.write_bytes(b"GGUF-deterministic-test")
    modelfile.write_text(
        "FROM ./weights.gguf\nPARAMETER temperature 0.2\n",
        encoding="utf-8",
    )
    license_file.write_text("Apache License test text\n", encoding="utf-8")
    return gguf, modelfile, license_file


def _build(root: Path, output: Path):
    gguf, modelfile, license_file = _sources(root)
    return build_model_pack(
        gguf_path=gguf,
        modelfile_path=modelfile,
        license_file_path=license_file,
        model_id="stockpulse/test:q4",
        display_name="StockPulse Test",
        license_id="Apache-2.0",
        minimum_memory_gb=8,
        output_path=output,
    )


def test_builder_outputs_a_valid_pack_and_release_checksum(tmp_path: Path) -> None:
    artifact, checksum = _build(tmp_path, tmp_path / "release" / "test.modelpack")

    expected_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert checksum.read_text(encoding="ascii") == f"{expected_digest}  test.modelpack\n"
    with ZipFile(artifact) as archive:
        assert archive.namelist() == [
            "manifest.json",
            "weights.gguf",
            "Modelfile",
            "LICENSE",
        ]
        assert archive.getinfo("weights.gguf").compress_type == ZIP_STORED

    with inspect_model_pack(artifact) as inspected:
        assert inspected.manifest.model_id == "stockpulse/test:q4"
        assert inspected.manifest.license.id == "Apache-2.0"
        assert inspected.modelfile.parameters == {"temperature": 0.2}


def test_builder_rejects_a_payload_named_like_the_reserved_manifest(tmp_path: Path) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    reserved_modelfile = tmp_path / "Manifest.json"
    modelfile.rename(reserved_modelfile)

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=reserved_modelfile,
            license_file_path=license_file,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=tmp_path / "test.modelpack",
        )

    assert error.value.code == "invalid_manifest"
    assert "reserved manifest.json" in error.value.user_message


@pytest.mark.parametrize("unsafe_filename", ["CON", "nul.txt", "LICENSE."])
def test_builder_rejects_cross_platform_unsafe_source_filenames(
    tmp_path: Path,
    unsafe_filename: str,
) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    unsafe_license = tmp_path / unsafe_filename
    license_file.rename(unsafe_license)
    output = tmp_path / "unsafe-filename.modelpack"

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=unsafe_license,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=output,
        )

    assert error.value.code == "invalid_manifest"
    assert "root-level safe filename" in error.value.user_message
    assert not output.exists()


def test_builder_is_deterministic_for_the_same_sources(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first, _first_checksum = _build(first_dir, tmp_path / "first.modelpack")
    second, _second_checksum = _build(second_dir, tmp_path / "second.modelpack")

    assert first.read_bytes() == second.read_bytes()


def test_builder_archives_the_exact_validated_modelfile_and_license_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    original_modelfile = modelfile.read_bytes()
    original_license = license_file.read_bytes()
    output = tmp_path / "canonical-text.modelpack"
    original_write_bytes = model_pack_builder._write_bytes

    def mutate_after_manifest(
        archive,
        filename: str,
        payload: bytes,
        **kwargs,
    ) -> None:
        if filename == "manifest.json":
            modelfile.write_text("FROM /private/outside.gguf\n", encoding="utf-8")
            license_file.write_bytes(b"\xff\xfe")
        original_write_bytes(archive, filename, payload, **kwargs)

    monkeypatch.setattr(
        model_pack_builder,
        "_write_bytes",
        mutate_after_manifest,
    )

    artifact, _checksum = build_model_pack(
        gguf_path=gguf,
        modelfile_path=modelfile,
        license_file_path=license_file,
        model_id="stockpulse/test:q4",
        display_name="StockPulse Test",
        license_id="Apache-2.0",
        minimum_memory_gb=8,
        output_path=output,
    )

    with ZipFile(artifact) as archive:
        assert archive.read("Modelfile") == original_modelfile
        assert archive.read("LICENSE") == original_license
    with inspect_model_pack(artifact) as inspected:
        assert inspected.modelfile.from_file == "weights.gguf"


@pytest.mark.parametrize("same_size", [False, True])
def test_builder_rejects_gguf_mutation_after_manifest_validation(
    tmp_path: Path,
    monkeypatch,
    same_size: bool,
) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    output = tmp_path / "changing-gguf.modelpack"
    original_write_bytes = model_pack_builder._write_bytes

    def mutate_after_manifest(
        archive,
        filename: str,
        payload: bytes,
        **kwargs,
    ) -> None:
        if filename == "manifest.json":
            if same_size:
                original = gguf.read_bytes()
                gguf.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            else:
                with gguf.open("ab") as file_obj:
                    file_obj.write(b"growth")
        original_write_bytes(archive, filename, payload, **kwargs)

    monkeypatch.setattr(
        model_pack_builder,
        "_write_bytes",
        mutate_after_manifest,
    )

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=output,
        )

    assert error.value.code == "source_changed"
    assert "Stop modifying" in error.value.user_message
    assert not output.exists()
    assert not output.with_name(f"{output.name}.sha256").exists()
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


def test_builder_rejects_unsafe_modelfile_before_writing(tmp_path: Path) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    modelfile.write_text(
        "FROM ../../private.gguf\nADAPTER ./adapter.gguf\n",
        encoding="utf-8",
    )
    output = tmp_path / "unsafe.modelpack"

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=output,
        )

    assert error.value.code == "unsafe_modelfile"
    assert not output.exists()


@pytest.mark.parametrize(
    "ambiguous_instruction",
    [
        'SYSTEM "quoted system text"',
        "PARAMETER temperature 0.1\nPARAMETER temperature 0.2",
    ],
)
def test_builder_rejects_transport_ambiguous_modelfile_syntax(
    tmp_path: Path,
    ambiguous_instruction: str,
) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    modelfile.write_text(
        f"FROM ./weights.gguf\n{ambiguous_instruction}\n",
        encoding="utf-8",
    )
    output = tmp_path / "ambiguous.modelpack"

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=output,
        )

    assert error.value.code == "unsafe_modelfile"
    assert not output.exists()


@pytest.mark.parametrize(
    "ambiguous_instruction",
    [
        "FROM\t./weights.gguf",
        'SYSTEM \ufeff"quoted system text"',
        "SYSTEM safe\u2028ADAPTER ./outside.gguf",
        "PARAMETER temperature NaN",
        "PARAMETER temperature 1e999",
        "PARAMETER temperature 1e39",
        "PARAMETER temperature 1e-999",
        "PARAMETER num_ctx 9007199254740992",
        "PARAMETER num_ctx 1.0",
        "PARAMETER future_option 1",
        "PARAMETER TEMPERATURE 0.1",
        "PARAMETER use_mmap 1",
        "PARAMETER stop true",
        'PARAMETER stop "a\\"b"',
        'PARAMETER stop "unclosed',
        "PARAMETER stop unquoted",
        "PARAMETER stop null",
        "PARAMETER stop [1]",
    ],
)
def test_builder_rejects_nonportable_modelfile_grammar(
    tmp_path: Path,
    ambiguous_instruction: str,
) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    modelfile.write_text(
        f"FROM ./weights.gguf\n{ambiguous_instruction}\n",
        encoding="utf-8",
    )
    output = tmp_path / "nonportable.modelpack"

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=output,
        )

    assert error.value.code == "unsafe_modelfile"
    assert not output.exists()


def test_builder_uses_portable_manifest_text_contract(tmp_path: Path) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    output = tmp_path / "unicode.modelpack"

    artifact, _checksum = build_model_pack(
        gguf_path=gguf,
        modelfile_path=modelfile,
        license_file_path=license_file,
        model_id="stockpulse/unicode:q4",
        display_name="😀" * 160,
        license_id="Apache-2.0",
        minimum_memory_gb=8,
        output_path=output,
    )
    with inspect_model_pack(artifact) as inspected:
        assert inspected.manifest.display_name == "😀" * 160

    invalid_output = tmp_path / "invalid-model-id.modelpack"
    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id="K:q4",
            display_name="Portable",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=invalid_output,
        )
    assert error.value.code == "invalid_manifest"
    assert not invalid_output.exists()


@pytest.mark.parametrize(
    "model_id",
    [
        "finance",
        "acme.finance/model:q4",
        f"{'n' * 81}/model:q4",
    ],
)
def test_builder_rejects_model_ids_without_a_stable_ollama_identity(
    tmp_path: Path,
    model_id: str,
) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    output = tmp_path / "invalid-model-id.modelpack"

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id=model_id,
            display_name="Portable",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=output,
        )

    assert error.value.code == "invalid_manifest"
    assert not output.exists()


@pytest.mark.skipif(os.name == "nt", reason="symbolic-link replacement requires POSIX")
@pytest.mark.parametrize("source_role", ["modelfile", "license"])
def test_builder_rejects_text_source_replacement_between_lstat_and_open(
    tmp_path: Path,
    monkeypatch,
    source_role: str,
) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    source = modelfile if source_role == "modelfile" else license_file
    replacement = tmp_path / f"{source_role}-replacement"
    replacement.write_text(
        "FROM ./weights.gguf\n" if source_role == "modelfile" else "private text\n",
        encoding="utf-8",
    )
    original = tmp_path / f"{source.name}.original"
    output = tmp_path / f"{source_role}-swap.modelpack"
    original_open = Path.open
    swapped = False

    def swap_before_open(path_obj: Path, *args, **kwargs):
        nonlocal swapped
        mode = args[0] if args else kwargs.get("mode", "r")
        if path_obj == source and mode == "rb" and not swapped:
            swapped = True
            source.rename(original)
            source.symlink_to(replacement)
        return original_open(path_obj, *args, **kwargs)

    monkeypatch.setattr(Path, "open", swap_before_open)

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=output,
        )

    assert error.value.code == "source_changed"
    assert swapped is True
    assert not output.exists()


def test_builder_rejects_symbolic_link_sources(tmp_path: Path) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    linked_gguf = tmp_path / "linked.gguf"
    linked_gguf.symlink_to(gguf)

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=linked_gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=tmp_path / "linked.modelpack",
        )

    assert error.value.code == "invalid_source_file"


@pytest.mark.skipif(os.name == "nt", reason="symbolic-link output requires POSIX")
def test_builder_rejects_an_existing_output_symlink_without_clobbering_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "unrelated.modelpack"
    target.write_bytes(b"unrelated data")
    output = tmp_path / "release.modelpack"
    output.symlink_to(target)

    with pytest.raises(ModelPackError) as error:
        _build(tmp_path, output)

    assert error.value.code == "invalid_output_path"
    assert output.is_symlink()
    assert target.read_bytes() == b"unrelated data"
    assert not target.with_name(f"{target.name}.sha256").exists()
    assert not output.with_name(f"{output.name}.sha256").exists()


@pytest.mark.skipif(os.name == "nt", reason="hard-link aliases require POSIX")
@pytest.mark.parametrize("alias_leaf", ["output", "checksum"])
def test_builder_rejects_existing_output_aliases_to_source_files(
    tmp_path: Path,
    alias_leaf: str,
) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    output = tmp_path / "release.modelpack"
    checksum = output.with_name(f"{output.name}.sha256")
    alias = output if alias_leaf == "output" else checksum
    os.link(license_file, alias)
    original_license = license_file.read_bytes()

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=output,
        )

    assert error.value.code == "invalid_output_path"
    assert license_file.read_bytes() == original_license
    assert alias.read_bytes() == original_license


def test_builder_rejects_oversized_modelfile_before_full_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    modelfile.write_bytes(b"x" * (MAX_MODELFILE_BYTES + 1))
    original_read_bytes = Path.read_bytes

    def reject_full_read(path: Path) -> bytes:
        if path.resolve() == modelfile.resolve():
            raise AssertionError("oversized Modelfile must not be read in full")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_full_read)

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=tmp_path / "oversized-modelfile.modelpack",
        )

    assert error.value.code == "unsafe_modelfile"
    assert str(MAX_MODELFILE_BYTES) in error.value.user_message


def test_builder_rejects_license_text_above_the_import_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    license_file.write_bytes(b"x" * (MAX_LICENSE_BYTES + 1))
    original_read_text = Path.read_text

    def reject_full_read(path: Path, *args, **kwargs) -> str:
        if path.resolve() == license_file.resolve():
            raise AssertionError("oversized license must not be read in full")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_full_read)

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=tmp_path / "oversized-license.modelpack",
        )

    assert error.value.code == "invalid_license_file"
    assert str(MAX_LICENSE_BYTES) in error.value.user_message


def test_builder_rejects_a_final_archive_above_the_import_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    payload_bytes = sum(
        path.stat().st_size for path in (gguf, modelfile, license_file)
    )
    monkeypatch.setattr(
        model_pack_builder,
        "MAX_MODEL_PACK_BYTES",
        payload_bytes,
    )
    output = tmp_path / "oversized-artifact.modelpack"

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=license_file,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=output,
        )

    assert error.value.code == "model_pack_too_large"
    assert "completed Model Pack" in error.value.user_message
    assert not output.exists()
    assert not output.with_name(f"{output.name}.sha256").exists()
    assert list(tmp_path.glob(f".{output.name}.*.tmp")) == []


def test_builder_does_not_overwrite_a_source_with_the_checksum(tmp_path: Path) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    checksum_source = tmp_path / "release.modelpack.sha256"
    license_file.rename(checksum_source)

    with pytest.raises(ModelPackError) as error:
        build_model_pack(
            gguf_path=gguf,
            modelfile_path=modelfile,
            license_file_path=checksum_source,
            model_id="stockpulse/test:q4",
            display_name="StockPulse Test",
            license_id="Apache-2.0",
            minimum_memory_gb=8,
            output_path=tmp_path / "release.modelpack",
        )

    assert error.value.code == "invalid_output_path"
    assert checksum_source.read_text(encoding="utf-8") == "Apache License test text\n"


def test_builder_rejects_non_file_checksum_target_before_publishing(
    tmp_path: Path,
) -> None:
    output = tmp_path / "release.modelpack"
    checksum = tmp_path / "release.modelpack.sha256"
    checksum.mkdir()

    with pytest.raises(ModelPackError) as error:
        _build(tmp_path, output)

    assert error.value.code == "invalid_output_path"
    assert not output.exists()
    assert checksum.is_dir()


def test_builder_restores_the_previous_pair_when_checksum_publish_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "release.modelpack"
    checksum = tmp_path / "release.modelpack.sha256"
    output.write_bytes(b"previous artifact")
    checksum.write_text("previous checksum\n", encoding="ascii")
    original_replace = model_pack_builder.os.replace

    def fail_new_checksum(source, destination) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            destination_path == checksum
            and source_path.suffix == ".tmp"
        ):
            raise OSError("simulated checksum publication failure")
        original_replace(source, destination)

    monkeypatch.setattr(model_pack_builder.os, "replace", fail_new_checksum)

    with pytest.raises(ModelPackError) as error:
        _build(tmp_path, output)

    assert error.value.code == "output_publish_failed"
    assert output.read_bytes() == b"previous artifact"
    assert checksum.read_text(encoding="ascii") == "previous checksum\n"
    assert list(tmp_path.glob(".*.tmp")) == []
    assert list(tmp_path.glob(".*.bak")) == []


def test_builder_preserves_unrelated_legacy_temp_names(tmp_path: Path) -> None:
    legacy_temp = tmp_path / ".release.modelpack.tmp"
    legacy_temp.write_text("keep", encoding="utf-8")

    _build(tmp_path, tmp_path / "release.modelpack")

    assert legacy_temp.read_text(encoding="utf-8") == "keep"


def test_cli_returns_actionable_error_without_a_traceback(tmp_path: Path, capsys) -> None:
    gguf, modelfile, license_file = _sources(tmp_path)
    gguf.write_bytes(b"not-a-gguf")

    exit_code = main(
        [
            "--gguf",
            str(gguf),
            "--modelfile",
            str(modelfile),
            "--license-file",
            str(license_file),
            "--model-id",
            "stockpulse/test:q4",
            "--display-name",
            "StockPulse Test",
            "--license-id",
            "Apache-2.0",
            "--minimum-memory-gb",
            "8",
            "--output",
            str(tmp_path / "bad.modelpack"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "not GGUF" in captured.err
    assert "Traceback" not in captured.err
