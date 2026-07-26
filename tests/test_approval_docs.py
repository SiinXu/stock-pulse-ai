"""Documentation contract for Human-in-the-Loop approvals."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_approval_docs_cover_security_api_migration_and_rollback() -> None:
    for filename in ("docs/human-approvals.md", "docs/human-approvals_EN.md"):
        content = (ROOT / filename).read_text(encoding="utf-8")
        for required in (
            "risk_control_bypass",
            "risk_veto",
            "risk_downgrade",
            "pending",
            "approved",
            "expected_version",
            "SecurityAuditService",
            "202607250001_approval_gate_schema",
            "rollback" if filename.endswith("_EN.md") else "回滚",
            "300",
            "AGENT_ORCHESTRATOR_TIMEOUT_S",
            "local_admin",
            "pipeline",
            "expires_in_seconds",
        ):
            assert required in content


def test_approval_change_log_is_flat() -> None:
    content = (ROOT / "docs/CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = content.split("## [Unreleased]", 1)[1].split("\n## ", 1)[0]
    assert "Human-in-the-Loop risk-control bypass" in unreleased
    assert "\n### " not in unreleased
