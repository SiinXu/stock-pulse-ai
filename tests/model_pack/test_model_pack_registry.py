from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.model_pack.registry import (
    MAX_MODEL_PACK_REGISTRY_BYTES,
    ModelPackRegistry,
)


RUNTIME_A = "a" * 64
RUNTIME_B = "b" * 64


def _register(
    registry: ModelPackRegistry,
    *,
    runtime_identity: str = RUNTIME_A,
    model_id: str = "stockpulse/finance:q4",
    display_name: str = "Finance Q4",
) -> None:
    registry.register(
        runtime_identity=runtime_identity,
        model_id=model_id,
        display_name=display_name,
        minimum_memory_gb=16,
        license_id="LicenseRef-Finance",
    )


def test_registry_persists_detached_metadata_and_replaces_case_insensitively(
    tmp_path: Path,
) -> None:
    path = tmp_path / "model-packs.json"
    registry = ModelPackRegistry(path)

    _register(registry)
    _register(
        registry,
        model_id="STOCKPULSE/FINANCE:Q4",
        display_name="Finance Q4 Updated",
    )
    _register(
        registry,
        runtime_identity=RUNTIME_B,
        model_id="stockpulse/finance:q4",
        display_name="Other Runtime",
    )

    assert ModelPackRegistry(path).list_for_runtime(RUNTIME_A) == (
        {
            "model_id": "STOCKPULSE/FINANCE:Q4",
            "display_name": "Finance Q4 Updated",
            "minimum_memory_gb": 16,
            "license_id": "LicenseRef-Finance",
        },
    )
    assert ModelPackRegistry(path).list_for_runtime(RUNTIME_B)[0]["display_name"] == "Other Runtime"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_registry_preserves_portable_non_ascii_display_boundaries(
    tmp_path: Path,
) -> None:
    path = tmp_path / "model-packs.json"
    registry = ModelPackRegistry(path)
    display_name = "\u00a0Finance Q4\u00a0"

    _register(registry, display_name=display_name)

    assert registry.list_for_runtime(RUNTIME_A)[0]["display_name"] == display_name
    assert ModelPackRegistry(path).list_for_runtime(RUNTIME_A)[0][
        "display_name"
    ] == display_name


def test_registry_rejects_unvalidated_fields_without_replacing_existing_data(
    tmp_path: Path,
) -> None:
    path = tmp_path / "model-packs.json"
    registry = ModelPackRegistry(path)
    _register(registry)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="Invalid Model Pack registry metadata"):
        registry.register(
            runtime_identity=RUNTIME_A,
            model_id="../../escape",
            display_name="Bad",
            minimum_memory_gb=8,
            license_id="Apache-2.0",
        )

    assert path.read_bytes() == before


def test_registry_fails_closed_for_malformed_or_oversized_files(tmp_path: Path) -> None:
    path = tmp_path / "model-packs.json"
    registry = ModelPackRegistry(path)

    path.write_text("{not json", encoding="utf-8")
    assert registry.list_for_runtime(RUNTIME_A) == ()

    path.write_bytes(b"x" * (MAX_MODEL_PACK_REGISTRY_BYTES + 1))
    assert registry.list_for_runtime(RUNTIME_A) == ()

    path.write_text(
        json.dumps({"schema_version": 99, "models": []}),
        encoding="utf-8",
    )
    assert registry.list_for_runtime(RUNTIME_A) == ()

    path.write_text(
        '{"schema_version":1,"models":[{"runtime_identity":"'
        + RUNTIME_A
        + '","model_id":"stockpulse/surrogate:q4",'
        '"display_name":"\\ud800","minimum_memory_gb":8,'
        '"license_id":"LicenseRef-Test"}]}',
        encoding="ascii",
    )
    assert registry.list_for_runtime(RUNTIME_A) == ()

    depth = 1200
    path.write_text(
        '{"schema_version":1,"models":'
        + ("[" * depth)
        + "{}"
        + ("]" * depth)
        + "}",
        encoding="utf-8",
    )
    assert registry.list_for_runtime(RUNTIME_A) == ()
