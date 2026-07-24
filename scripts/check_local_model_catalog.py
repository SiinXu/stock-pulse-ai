#!/usr/bin/env python3
"""Validate the shared local-model catalog and every packaged consumer."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.llm.local_model_catalog import (  # noqa: E402
    LOCAL_MODEL_CATALOG_PATH,
    get_desktop_local_model_presets,
    get_local_model_catalog,
)


EXPECTED_MODEL_IDS = (
    "qwen3-4b",
    "qwen3-8b",
    "gemma4-12b",
    "deepseek-r1-8b",
    "dianjin-r1-7b",
    "fin-r1-7b",
    "xuanyuan-6b-chat",
)
EXPECTED_DESKTOP_TAGS = (
    "qwen3:4b",
    "qwen3:8b",
    "gemma4:12b",
    "deepseek-r1:8b",
)


def fail(message: str) -> None:
    print(f"[local-model-catalog] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def ensure_fixed_selection() -> None:
    catalog = get_local_model_catalog()
    model_ids = tuple(model["id"] for model in catalog["models"])
    if model_ids != EXPECTED_MODEL_IDS:
        fail(f"model selection or order drifted: {model_ids!r}")

    desktop_tags = tuple(preset["id"] for preset in get_desktop_local_model_presets())
    if desktop_tags != EXPECTED_DESKTOP_TAGS:
        fail(f"desktop preset projection drifted: {desktop_tags!r}")

    if any(model["install"]["hosted_by_stockpulse"] for model in catalog["models"]):
        fail("catalog claims StockPulse-hosted weights before a publishing task has verified them")

    xuanyuan = next(model for model in catalog["models"] if model["id"] == "xuanyuan-6b-chat")
    if xuanyuan["install"]["method"] != "guided_import":
        fail("XuanYuan must remain guided-import-only until its redistribution terms are cleared")


def ensure_desktop_consumes_catalog() -> None:
    package_path = ROOT / "apps" / "dsa-desktop" / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    build = package.get("build") or {}
    if "local-model-catalog.js" not in build.get("files", []):
        fail("desktop package does not include local-model-catalog.js")

    expected_resource = {
        "from": "../../src/llm/local_model_catalog.json",
        "to": "local-model-catalog.json",
    }
    if expected_resource not in build.get("extraResources", []):
        fail("desktop package does not copy the authoritative catalog resource")

    consumer_expectations = {
        "apps/dsa-desktop/main.js": "loadDesktopLocalModelPresets",
        "apps/dsa-desktop/model-preload.js": "--stockpulse-local-model-presets=",
    }
    for relative_path, expected in consumer_expectations.items():
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        if expected not in content:
            fail(f"{relative_path} does not consume the catalog projection")
        for tag in EXPECTED_DESKTOP_TAGS:
            if tag in content:
                fail(f"{relative_path} duplicates catalog tag {tag!r}")


def ensure_backend_packages_catalog() -> None:
    relative_catalog = LOCAL_MODEL_CATALOG_PATH.relative_to(ROOT).as_posix()
    packaging_expectations = {
        "scripts/build-backend-macos.sh": f"{relative_catalog}:src/llm",
        "scripts/build-backend.ps1": f"{relative_catalog};src/llm",
    }
    for relative_path, expected in packaging_expectations.items():
        if expected not in (ROOT / relative_path).read_text(encoding="utf-8"):
            fail(f"{relative_path} does not package {relative_catalog}")


def main() -> None:
    ensure_fixed_selection()
    ensure_desktop_consumes_catalog()
    ensure_backend_packages_catalog()
    print("[local-model-catalog] OK")


if __name__ == "__main__":
    main()
