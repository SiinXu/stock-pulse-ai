# -*- coding: utf-8 -*-
"""Safe simulation sandbox contracts (Issues #247 / #202 / #442)."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.agent.sandbox import (
    SIMULATION_LABEL,
    SandboxContext,
    SandboxDataAccess,
    SandboxDataAccessError,
    SandboxExternalEffectBlocked,
    SandboxRunRequest,
    SandboxRunner,
    active_sandbox_context,
    build_promotion_receipt,
    get_sandbox_isolation_policy,
    is_sandbox_active,
    run_agent_variant_in_sandbox,
)
from src.agent.sandbox.clock import FakeClock
from src.agent.sandbox.effects import (
    EFFECT_ANALYSIS_HISTORY,
    EFFECT_DECISION_MEMORY,
    EFFECT_DECISION_SIGNAL,
    EFFECT_NOTIFICATION,
    EFFECT_PRODUCTION_PORTFOLIO,
)
from src.agent.sandbox.policy import SANDBOX_MODE
from src.services.decision_signal_service import (
    DecisionSignalService,
    DecisionSignalWriteOutcome,
)

FIXED_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_isolation_policy_fail_closed():
    policy = get_sandbox_isolation_policy()
    assert policy["mode"] == SANDBOX_MODE
    assert policy["label"] == SIMULATION_LABEL
    assert policy["persist_decision_signal"] is False
    assert policy["persist_decision_memory"] is False
    assert policy["persist_analysis_history"] is False
    assert policy["send_real_notifications"] is False
    assert policy["place_real_orders"] is False
    assert policy["auto_promote_to_production"] is False
    assert "persist_decision_signal" in policy["enforced_in_batch1"]
    assert "persist_decision_memory" in policy["enforced_in_batch1"]
    assert "persist_analysis_history" in policy["enforced_in_batch1"]
    assert "write_production_portfolio" in policy["enforced_in_batch1"]
    assert policy["declared_not_yet_enforced"] == ()
    assert "place_real_orders" in policy["not_applicable_no_write_surface"]
    assert "persist_agent_memory" in policy["not_applicable_no_write_surface"]


def test_fake_clock_is_deterministic_and_advances():
    clock = FakeClock.fixed("2026-08-01T12:00:00Z")
    assert clock.isoformat() == "2026-08-01T12:00:00Z"
    clock.advance(seconds=30)
    assert clock.utcnow().second == 30
    with pytest.raises(ValueError):
        clock.advance(seconds=-1)


def test_context_requires_snapshot_when_mode_snapshot():
    with pytest.raises(ValueError, match="snapshot"):
        SandboxContext.create(data_mode="snapshot", snapshot={})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_context_rejects_non_finite_public_values(value):
    with pytest.raises(ValueError, match="finite JSON-compatible"):
        SandboxContext.create(config_overlay={"risk_limit": value})


def test_snapshot_data_access_is_read_only():
    ctx = SandboxContext.create(
        fixed_now=FIXED_NOW,
        data_mode="snapshot",
        snapshot={"quote:AAPL": {"close": 190.5}},
    )
    access = SandboxDataAccess(context=ctx)
    assert access.get("quote:AAPL")["close"] == 190.5
    assert access.describe()["writable"] is False
    with pytest.raises(SandboxDataAccessError):
        access.get("missing")


def test_readonly_live_uses_reader_without_write_api():
    calls = []

    def reader(key, params):
        calls.append((key, dict(params)))
        return {"key": key, "ok": True}

    ctx = SandboxContext.create(fixed_now=FIXED_NOW, data_mode="readonly_live")
    access = SandboxDataAccess(context=ctx, live_reader=reader)
    assert access.get("bars", params={"code": "600519"})["ok"] is True
    assert calls == [("bars", {"code": "600519"})]


def test_active_context_arms_simulation_metadata():
    ctx = SandboxContext.create(
        fixed_now=FIXED_NOW,
        agent_variant_id="risk-averse",
        config_overlay={"max_steps": 3},
        language="en",
    )
    assert not is_sandbox_active()
    with active_sandbox_context(ctx) as active:
        assert is_sandbox_active()
        meta = active.public_metadata()
        assert meta["simulation"] is True
        assert meta["label"] == SIMULATION_LABEL
        assert meta["mode"] == SANDBOX_MODE
        assert "SIMULATION" in meta["banner"]
        assert active.config_digest
    assert not is_sandbox_active()


def test_nested_sandbox_context_rejected():
    outer = SandboxContext.create(fixed_now=FIXED_NOW)
    inner = SandboxContext.create(fixed_now=FIXED_NOW)
    with active_sandbox_context(outer):
        with pytest.raises(RuntimeError, match="nested"):
            with active_sandbox_context(inner):
                pass


def test_runner_labels_output_and_emits_isomorphic_trace():
    result = run_agent_variant_in_sandbox(
        SandboxRunRequest(
            prompt="Compare risk gates",
            agent_variant_id="variant-a",
            config_overlay={"temperature": 0.0},
        ),
        context=SandboxContext.create(fixed_now=FIXED_NOW, agent_variant_id="variant-a"),
    )
    assert result.success
    assert SIMULATION_LABEL in result.content or "SIMULATION" in result.content
    payload = result.to_dict()
    assert payload["simulation"] is True
    assert payload["label"] == SIMULATION_LABEL
    trace = result.trace.to_dict()
    assert trace["schema_version"] == "sandbox-trace-v1"
    assert trace["simulation"] is True
    assert trace["agent_variant_id"] == "variant-a"
    assert len(trace["events"]) >= 2
    runs = result.trace.trajectory_compatible_runs()
    assert runs[0]["schema_version"] == "agent-trajectory-input-v1"
    assert runs[0]["run_id"] == result.context.sandbox_run_id
    assert "sandbox" not in runs[0]
    # Strict trajectory schema rejects extra keys; projection must validate.
    from src.schemas.agent_trajectory import TrajectoryRunInput

    TrajectoryRunInput.model_validate(runs[0])
    projection = result.trace.trajectory_projection()
    assert projection["sandbox"]["simulation"] is True
    assert projection["sandbox"]["config_digest"] == result.context.config_digest
    TrajectoryRunInput.model_validate(projection["runs"][0])


def test_compare_two_agent_variants():
    runner = SandboxRunner()
    base = SandboxContext.create(
        fixed_now=FIXED_NOW,
        data_mode="snapshot",
        snapshot={"universe": ["AAPL", "600519"]},
    )
    results = runner.compare_variants(
        SandboxRunRequest(prompt="stress rates up 50bp"),
        variants=[
            {"id": "conservative", "config": {"risk": "low"}},
            {"id": "aggressive", "config": {"risk": "high"}},
        ],
        base_context=base,
    )
    assert len(results) == 2
    assert results[0].context.agent_variant_id == "conservative"
    assert results[1].context.agent_variant_id == "aggressive"
    assert results[0].context.config_digest != results[1].context.config_digest
    for item in results:
        assert item.trace.label == SIMULATION_LABEL
        assert item.promotion_receipt is not None
        assert item.promotion_receipt.auto_promote is False
        assert item.promotion_receipt.review_required is True


def test_runner_failure_is_sanitized_and_trace_is_not_completed():
    secret = "sk-secret-shaped-value-1234567890"

    def variant(request, context, data):
        raise RuntimeError(f"api_key={secret}")

    result = SandboxRunner(variant_callable=variant).run(
        SandboxRunRequest(prompt="probe"),
        context=SandboxContext.create(fixed_now=FIXED_NOW),
    )

    payload = result.to_dict()
    assert result.success is False
    assert result.error == "sandbox_variant_failed"
    assert secret not in str(payload)
    assert payload["trace"]["completed"] is False
    assert result.trace.trajectory_compatible_runs()[0]["completed"] is False


def test_runner_rejects_non_finite_variant_output():
    result = SandboxRunner(
        variant_callable=lambda request, context, data: {
            "success": True,
            "content": "bad metric",
            "events": [{"duration_ms": float("nan")}],
        }
    ).run(
        SandboxRunRequest(prompt="probe"),
        context=SandboxContext.create(fixed_now=FIXED_NOW),
    )

    assert result.success is False
    assert result.error == "sandbox_variant_failed"
    assert result.trace.completed is False


def test_runner_redacts_secrets_from_all_public_variant_fields():
    secret = "sk-public-output-secret-1234567890"

    def variant(request, context, data):
        return {
            "content": f"api_key={secret}",
            "events": [{"attrs": {"authorization": f"Bearer {secret}"}}],
            "simulated_actions": [{"detail": f"token={secret}"}],
            "raw": {"api_key": secret},
        }

    result = SandboxRunner(variant_callable=variant).run(
        SandboxRunRequest(prompt="probe"),
        context=SandboxContext.create(
            fixed_now=FIXED_NOW,
            source_data_window={"from": "2026-01-01", "api_key": secret},
        ),
    )

    payload = result.to_dict()
    assert result.success is True
    assert secret not in str(payload)
    assert "[REDACTED]" in str(payload)


def test_promotion_receipt_is_review_gated_never_auto():
    ctx = SandboxContext.create(
        fixed_now=FIXED_NOW,
        source_data_window={"from": "2026-01-01", "to": "2026-06-30"},
        agent_variant_id="v1",
    )
    result = run_agent_variant_in_sandbox(
        SandboxRunRequest(prompt="x", agent_variant_id="v1"),
        context=ctx,
    )
    receipt = result.promotion_receipt
    assert receipt is not None
    body = receipt.to_dict()
    assert body["schema_version"] == "sandbox-promotion-receipt-v1"
    assert body["sandbox_run_id"] == ctx.sandbox_run_id
    assert body["source_data_window"]["from"] == "2026-01-01"
    assert body["config_digest"]
    assert body["review_required"] is True
    assert body["auto_promote"] is False
    assert body["first_live_run_guard"] == "human_approval_required"
    assert body["risk_boundary"]["force_paper_only"] is True
    assert "decision_signal" in body["production_authority_scope"]["may_not_touch"]
    assert any(
        item["classification"] in {"observed", "inferred", "not_checked"}
        for item in body["assumptions"]
    )


def test_counterexample_decision_signal_write_blocked_under_sandbox():
    """Sandbox results must not write production DecisionSignals."""
    ctx = SandboxContext.create(fixed_now=FIXED_NOW)
    service = DecisionSignalService(repo=MagicMock())
    with active_sandbox_context(ctx):
        with pytest.raises(SandboxExternalEffectBlocked) as raised:
            service.create_signal_with_outcome(
                {
                    "stock_code": "AAPL",
                    "market": "US",
                    "action": "hold",
                    "score": 50,
                }
            )
    assert raised.value.effect == EFFECT_DECISION_SIGNAL
    service.repo.create_if_absent.assert_not_called()

    captured = []

    def variant(request, context, data):
        svc = DecisionSignalService(repo=MagicMock())
        try:
            svc.create_signal({"stock_code": "AAPL", "market": "US", "action": "buy"})
        except SandboxExternalEffectBlocked as exc:
            captured.append(exc.effect)
            return {
                "success": True,
                "content": "blocked as expected",
                "rejected_actions": [
                    {"action": "decision_signal.write", "reason": str(exc)}
                ],
            }
        return {
            "success": False,
            "content": "should have blocked",
            "error": "not_blocked",
        }

    result = SandboxRunner(variant_callable=variant).run(
        SandboxRunRequest(prompt="try write signal", agent_variant_id="probe"),
        context=SandboxContext.create(fixed_now=FIXED_NOW),
    )
    assert result.success
    assert captured == [EFFECT_DECISION_SIGNAL]
    assert any(
        item.get("effect") == EFFECT_DECISION_SIGNAL
        or item.get("action") == "decision_signal.write"
        for item in list(result.blocked_external_effects)
        + list(result.rejected_actions)
    )


def test_counterexample_notification_send_blocked_under_sandbox():
    """Sandbox results must not send real notifications."""
    from src.notification_parts.dispatch import _DispatchMethods

    class _Probe:
        pass

    probe = _Probe()
    ctx = SandboxContext.create(fixed_now=FIXED_NOW)
    with active_sandbox_context(ctx):
        with pytest.raises(SandboxExternalEffectBlocked) as raised:
            _DispatchMethods.send_with_results(probe, "hello")
    assert raised.value.effect == EFFECT_NOTIFICATION


def test_counterexample_analysis_history_write_blocked_under_sandbox():
    """Authoritative save_analysis_history fence covers all history callers."""
    from src.storage_parts.history import _HistoryMethods

    class _Probe(_HistoryMethods):
        def _extract_sniper_points(self, result):
            raise AssertionError("write path must not run under sandbox")

        def _build_raw_result(self, result):
            raise AssertionError("write path must not run under sandbox")

        def _run_write_transaction(self, *args, **kwargs):
            raise AssertionError("write path must not run under sandbox")

    probe = _Probe()
    ctx = SandboxContext.create(fixed_now=FIXED_NOW)
    with active_sandbox_context(ctx):
        with pytest.raises(SandboxExternalEffectBlocked) as raised:
            probe.save_analysis_history(
                result=SimpleNamespace(code="AAPL", name="Apple"),
                query_id="q-sandbox",
                report_type="standard",
                news_content=None,
            )
    assert raised.value.effect == EFFECT_ANALYSIS_HISTORY


def test_counterexample_decision_memory_flag_write_blocked_under_sandbox():
    """Decision-memory flag upserts must not land under an active sandbox."""
    from src.repositories.decision_signal_memory_flag_repo import (
        DecisionSignalMemoryFlagRepository,
    )

    mock_db = MagicMock()
    repo = DecisionSignalMemoryFlagRepository(db_manager=mock_db)
    ctx = SandboxContext.create(fixed_now=FIXED_NOW)
    with active_sandbox_context(ctx):
        with pytest.raises(SandboxExternalEffectBlocked) as raised:
            repo.upsert(
                {"signal_id": 1, "memorable": True, "ignored": False}
            )
    assert raised.value.effect == EFFECT_DECISION_MEMORY
    # Session path must not start under sandbox.
    mock_db.get_session.assert_not_called()


def test_counterexample_production_portfolio_write_blocked_under_sandbox():
    """Portfolio repository mutations must stop before opening a DB session."""
    from src.repositories.portfolio_repo import PortfolioRepository

    mock_db = MagicMock()
    repo = PortfolioRepository(db_manager=mock_db)
    ctx = SandboxContext.create(fixed_now=FIXED_NOW)
    with active_sandbox_context(ctx):
        with pytest.raises(SandboxExternalEffectBlocked) as raised:
            repo.create_account(
                name="must-not-persist",
                broker=None,
                market="us",
                base_currency="USD",
            )
    assert raised.value.effect == EFFECT_PRODUCTION_PORTFOLIO
    mock_db.get_session.assert_not_called()


def test_production_path_unblocked_when_sandbox_inactive():
    """Fence must not fire outside sandbox (no false positives)."""
    service = DecisionSignalService(repo=MagicMock())
    assert not is_sandbox_active()
    row = SimpleNamespace(
        id=1,
        status="inactive",
        created_at=None,
        stock_code="AAPL",
        market="US",
        action="hold",
    )
    create_result = SimpleNamespace(
        row=row,
        created=True,
        refreshed=False,
        duplicate=False,
        invalidation_reference_at=None,
    )
    service.repo.create_if_absent = MagicMock(return_value=create_result)
    service._normalize_payload = MagicMock(
        return_value=({}, {"horizon_defaulted": False})
    )
    service._serialize = MagicMock(return_value={"id": 1})
    outcome = service.create_signal_with_outcome({"stock_code": "AAPL"})
    assert isinstance(outcome, DecisionSignalWriteOutcome)
    service.repo.create_if_absent.assert_called_once()


def test_build_promotion_receipt_rejects_unknown_guard():
    ctx = SandboxContext.create(fixed_now=FIXED_NOW)
    with pytest.raises(ValueError, match="first_live_run_guard"):
        build_promotion_receipt(context=ctx, first_live_run_guard="auto_ship")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "risk_boundary",
            {
                "force_paper_only": False,
                "allow_real_orders": True,
                "allow_real_notifications": True,
            },
        ),
        (
            "production_authority_scope",
            {"may_touch": ["real_order"], "may_not_touch": [], "declared": True},
        ),
    ],
)
def test_build_promotion_receipt_rejects_authority_override(field, value):
    ctx = SandboxContext.create(fixed_now=FIXED_NOW)
    with pytest.raises(ValueError, match="authority|remain"):
        build_promotion_receipt(context=ctx, **{field: value})
