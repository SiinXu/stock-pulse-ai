from __future__ import annotations

import json
from pathlib import Path

from api.app import create_app


ROOT = Path(__file__).resolve().parents[2]


def test_model_pack_document_covers_format_user_and_publisher_contracts() -> None:
    document = (ROOT / "docs/model-packs.md").read_text(encoding="utf-8")

    for required in (
        "## User Import",
        "## Format Version 1",
        "### Constrained Modelfile",
        "## Publisher Workflow",
        "scripts/build_model_pack.py",
        "manifest.json",
        "OUTBOUND_HTTP_ALLOWLIST",
        "under 2 GiB",
        "limited to 64 GiB",
        "Modelfile are each capped at 1 MiB",
        "capped at 2 MiB",
        "`invalid_license_file`",
        "model_pack_registry.json",
        "bundled runtime as fallback",
        "does not publish weights",
    ):
        assert required in document
    assert "LITELLM_FALLBACK_MODELS" in document
    assert "There is no `LITELLM_FALLBACK_MODELS` setting" in document


def test_english_index_links_the_model_pack_guide() -> None:
    index = (ROOT / "docs/INDEX_EN.md").read_text(encoding="utf-8")
    assert "[StockPulse Model Packs](model-packs.md)" in index


def test_changelog_keeps_the_model_pack_entry_flat() -> None:
    changelog = (ROOT / "docs/CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = changelog.split("## [Unreleased]", 1)[1].split("\n## ", 1)[0]

    assert "- [Added] Added a versioned data-only Model Pack format" in unreleased
    assert "\n### " not in unreleased


def test_static_openapi_contains_the_runtime_model_pack_contract() -> None:
    static = json.loads(
        (ROOT / "docs/architecture/api_spec.json").read_text(encoding="utf-8")
    )
    runtime = create_app().openapi()

    for path in (
        "/api/v1/model-packs/import",
        "/api/v1/model-packs/imports/{task_id}",
        "/api/v1/model-packs/desktop-activations",
    ):
        assert static["paths"][path] == runtime["paths"][path]
    for schema in (
        "ModelPackImportAccepted",
        "ModelPackImportResult",
        "ModelPackImportStatus",
        "ModelPackDesktopActivationRequest",
    ):
        assert static["components"]["schemas"][schema] == runtime["components"][
            "schemas"
        ][schema]
