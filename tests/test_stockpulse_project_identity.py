# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression guards for StockPulse project identity and neutral provider links."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
TEXT_ROOTS = (
    ROOT_DIR / ".github",
    ROOT_DIR / "apps" / "dsa-web" / "src",
    ROOT_DIR / "docs",
    ROOT_DIR / "src",
)
STANDALONE_TEXT_FILES = (ROOT_DIR / ".env.example", ROOT_DIR / "README.md")
FORBIDDEN_REFERRAL_MARKERS = (
    "?share_code=",
    "?aff=CfMq",
    "?reg=834638",
    "utm_source=github_daily_stock_analysis",
    "GPIJ3886",
    "free quota for this project",
    "10% top-up discount for this project",
    "本项目免费额度",
    "本项目可享 10% 优惠",
)


def _iter_active_text() -> list[tuple[Path, str]]:
    paths = set(STANDALONE_TEXT_FILES)
    for root in TEXT_ROOTS:
        paths.update(path for path in root.rglob("*") if path.is_file())

    result: list[tuple[Path, str]] = []
    for path in sorted(paths):
        if "__pycache__" in path.parts:
            continue
        raw = path.read_bytes()
        if b"\0" in raw:
            continue
        try:
            result.append((path, raw.decode("utf-8")))
        except UnicodeDecodeError:
            continue
    return result


def test_active_project_assets_do_not_carry_upstream_referrals() -> None:
    violations: list[str] = []
    for path, content in _iter_active_text():
        for marker in FORBIDDEN_REFERRAL_MARKERS:
            if marker in content:
                violations.append(f"{path.relative_to(ROOT_DIR)}: {marker}")

    assert violations == [], "Upstream referral attribution found:\n" + "\n".join(violations)


def test_operational_links_target_stockpulse_without_false_availability_claims() -> None:
    stock_index = (ROOT_DIR / "src/services/stock_index_remote_service.py").read_text(encoding="utf-8")
    desktop_docs = (ROOT_DIR / "docs/desktop-package.md").read_text(encoding="utf-8")
    guide_zh = (ROOT_DIR / "docs/full-guide.md").read_text(encoding="utf-8")
    guide_en = (ROOT_DIR / "docs/full-guide_EN.md").read_text(encoding="utf-8")

    assert "raw.githubusercontent.com/SiinXu/stock-pulse-ai/" in stock_index
    assert "raw.githubusercontent.com/ZhuLinsen/daily_stock_analysis/" not in stock_index
    assert 'REPO="SiinXu/stock-pulse-ai"' in desktop_docs
    assert "docker pull zhulinsen/daily_stock_analysis" not in guide_zh + guide_en
    assert "cd stock-pulse-ai" in guide_zh
    assert "cd stock-pulse-ai" in guide_en
    assert "configured target does not guarantee" in guide_en


def test_unpublished_stockpulse_artifacts_are_not_advertised_as_available() -> None:
    docs = "\n".join(
        (ROOT_DIR / path).read_text(encoding="utf-8")
        for path in (
            "docs/FAQ.md",
            "docs/FAQ_EN.md",
            "docs/deploy-webui-cloud.md",
            "docs/beginner-client-setup.md",
        )
    )

    assert re.search(r"ghcr\.io/siinxu/stock-pulse-ai:v\d", docs, flags=re.IGNORECASE) is None
    assert "ghcr.io/siinxu/stock-pulse-ai:<published-tag>" in docs
    assert "github.com/SiinXu/stock-pulse-ai/releases/latest" not in docs
    assert "github.com/SiinXu/stock-pulse-ai/releases" in docs


def test_disabled_discussions_are_not_advertised() -> None:
    paths = (
        ROOT_DIR / ".github/ISSUE_TEMPLATE/config.yml",
        ROOT_DIR / "README.md",
        ROOT_DIR / "docs/README_CHT.md",
        ROOT_DIR / "docs/README_EN.md",
    )

    for path in paths:
        assert "SiinXu/stock-pulse-ai/discussions" not in path.read_text(encoding="utf-8"), path


def test_external_defaults_use_stockpulse_identity() -> None:
    from src.config import Config

    workflow = (ROOT_DIR / ".github/workflows/00-daily-analysis.yml").read_text(encoding="utf-8")
    api = (ROOT_DIR / "api/app.py").read_text(encoding="utf-8")
    api_spec = json.loads((ROOT_DIR / "docs/architecture/api_spec.json").read_text(encoding="utf-8"))
    user_agents = "\n".join(
        (ROOT_DIR / path).read_text(encoding="utf-8")
        for path in (
            "apps/dsa-desktop/main.js",
            "src/notification_sender/gotify_sender.py",
            "src/notification_sender/ntfy_sender.py",
            "src/services/intelligence_service.py",
        )
    )

    assert workflow.startswith("name: StockPulse Daily Analysis\n")
    assert "EMAIL_SENDER_NAME" in workflow and "'StockPulse'" in workflow
    assert Config.__dataclass_fields__["email_sender_name"].default == "StockPulse"
    assert 'title="StockPulse API"' in api
    assert api_spec["info"]["title"] == "StockPulse API"
    assert user_agents.count('"User-Agent": "StockPulse/1.0"') == 2
    assert "StockPulse-Desktop/1.0" in user_agents
    assert user_agents.count("StockPulse-Intel/1.0") == 2
