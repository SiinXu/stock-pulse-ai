# -*- coding: utf-8 -*-
"""Deterministic tests for daily brief + historical accuracy review (#466)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from src.services.daily_brief_service import (
    DAILY_BRIEF_HISTORY_CODE,
    DAILY_BRIEF_REPORT_TYPE,
    DailyBriefService,
    resolve_daily_brief_config,
)


class _FakeAnalysis:
    def __init__(
        self,
        *,
        code: str,
        created_at: datetime,
        name: str = "",
        operation_advice: str = "Hold",
        sentiment_score: int = 55,
        trend_prediction: str = "sideways",
        analysis_summary: str = "summary",
        report_type: str = "detailed",
        query_id: str = "q1",
    ) -> None:
        self.code = code
        self.stock_name = name or code
        self.created_at = created_at
        self.operation_advice = operation_advice
        self.sentiment_score = sentiment_score
        self.trend_prediction = trend_prediction
        self.analysis_summary = analysis_summary
        self.report_type = report_type
        self.query_id = query_id


class _FakeOutcome:
    def __init__(
        self,
        *,
        signal_id: int,
        outcome: str,
        stock_return_pct: float,
        action: str = "buy",
        horizon: str = "5d",
        eval_status: str = "completed",
        anchor_date: Optional[date] = None,
    ) -> None:
        self.signal_id = signal_id
        self.outcome = outcome
        self.stock_return_pct = stock_return_pct
        self.action = action
        self.horizon = horizon
        self.eval_status = eval_status
        self.anchor_date = anchor_date or date(2026, 7, 1)


class _FakeSignal:
    def __init__(self, signal_id: int, stock_code: str, stock_name: str, action: str) -> None:
        self.id = signal_id
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.action = action


class _OutcomeService:
    def __init__(self, rows: List[_FakeOutcome]) -> None:
        self.repo = SimpleNamespace(list_stats_rows=lambda **_kwargs: list(rows))

    @staticmethod
    def aggregate_outcome_rows(rows: List[Any]) -> Dict[str, Any]:
        from src.services.decision_signal_outcome_service import DecisionSignalOutcomeService

        return DecisionSignalOutcomeService.aggregate_outcome_rows(rows)


class _Notifier:
    def __init__(self) -> None:
        self.saved: List[tuple[str, str]] = []
        self.sent: List[str] = []
        self.available = True

    def is_available(self) -> bool:
        return self.available

    def save_report_to_file(self, content: str, filename: str) -> str:
        self.saved.append((filename, content))
        return f"/tmp/{filename}"

    def send(self, content: str, email_send_to_all: bool = False, route_type: str = "report") -> bool:
        self.sent.append(content)
        return True


def _fixed_clock(local_iso: str = "2026-08-06T09:00:00+08:00"):
    dt = datetime.fromisoformat(local_iso)

    def _clock() -> datetime:
        return dt.astimezone(timezone.utc)

    return _clock


def _base_config(**overrides: Any) -> SimpleNamespace:
    data = {
        "daily_brief_enabled": True,
        "daily_brief_schedule_time": "08:30",
        "daily_brief_timezone": "Asia/Shanghai",
        "daily_brief_min_samples": 3,
        "daily_brief_notify": False,
        "daily_brief_persist_history": False,
        "daily_brief_save_report_file": False,
        "report_language": "en",
        "stock_list": ["AAPL", "MSFT", "600519"],
        "report_templates_dir": "templates",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_resolve_daily_brief_config_defaults_off():
    view = resolve_daily_brief_config(SimpleNamespace())
    assert view.enabled is False
    assert view.min_samples == 10
    assert view.schedule_time == "08:30"


def test_no_history_accuracy_is_explicit_and_template_honest():
    config = _base_config(daily_brief_min_samples=5)
    analysis_repo = SimpleNamespace(get_list=lambda **_kwargs: [])
    outcome_service = _OutcomeService([])
    signal_repo = SimpleNamespace(get=lambda _id: None)
    backtest_service = SimpleNamespace(get_summary=lambda **_kwargs: None)
    skill_service = SimpleNamespace(
        get_stats=lambda **_kwargs: {
            "buckets": [
                {
                    "skill_id": "trend",
                    "horizon": "5d",
                    "evaluated": 2,
                    "hit_rate_pct": None,
                    "miss_rate_pct": None,
                    "sample_sufficient": False,
                    "sample_status": "observational",
                }
            ]
        }
    )
    service = DailyBriefService(
        analysis_repo=analysis_repo,
        decision_outcome_service=outcome_service,
        decision_signal_repo=signal_repo,
        backtest_service=backtest_service,
        skill_performance_service=skill_service,
        config_provider=lambda: config,
        clock=_fixed_clock(),
    )

    payload = service.build_payload(config=config)
    accuracy = payload["accuracy"]
    assert accuracy["status"] == "insufficient_history"
    assert accuracy["decision_signals"]["hit_rate_pct"] is None
    assert accuracy["backtest"]["direction_accuracy_pct"] is None
    assert accuracy["skill_outcomes"]["status"] == "insufficient_data"
    assert "insufficient" in accuracy["honesty_note"].lower()

    markdown = service.render_markdown(payload)
    assert "Historical accuracy review" in markdown or "历史准确率" in markdown
    assert "Insufficient history" in markdown or "历史样本不足" in markdown
    assert "Hit rate: **None**" not in markdown
    assert "fabricated" in markdown.lower() or "编造" in markdown


def test_rich_history_publishes_hit_rates_and_notables():
    yesterday_utc = datetime(2026, 8, 5, 4, 0, 0)
    analyses = [
        _FakeAnalysis(
            code="AAPL",
            name="Apple",
            created_at=yesterday_utc,
            operation_advice="Buy",
            sentiment_score=72,
            analysis_summary="Strong setup",
        ),
        _FakeAnalysis(
            code="TSLA",
            name="Tesla",
            created_at=yesterday_utc,
            operation_advice="Hold",
            sentiment_score=50,
        ),
        _FakeAnalysis(
            code="MARKET",
            created_at=yesterday_utc,
            report_type="market_review",
        ),
        _FakeAnalysis(
            code=DAILY_BRIEF_HISTORY_CODE,
            created_at=yesterday_utc,
            report_type=DAILY_BRIEF_REPORT_TYPE,
        ),
    ]
    outcomes = [
        _FakeOutcome(signal_id=1, outcome="hit", stock_return_pct=8.5, action="buy"),
        _FakeOutcome(signal_id=2, outcome="hit", stock_return_pct=3.0, action="add"),
        _FakeOutcome(signal_id=3, outcome="miss", stock_return_pct=-6.2, action="buy"),
        _FakeOutcome(signal_id=4, outcome="miss", stock_return_pct=-1.0, action="hold"),
        _FakeOutcome(signal_id=5, outcome="neutral", stock_return_pct=0.2, action="hold"),
    ]
    signals = {
        1: _FakeSignal(1, "AAPL", "Apple", "buy"),
        2: _FakeSignal(2, "MSFT", "Microsoft", "add"),
        3: _FakeSignal(3, "NVDA", "Nvidia", "buy"),
        4: _FakeSignal(4, "AMD", "AMD", "hold"),
        5: _FakeSignal(5, "INTC", "Intel", "hold"),
    }
    config = _base_config(daily_brief_min_samples=3, report_language="en")
    service = DailyBriefService(
        analysis_repo=SimpleNamespace(get_list=lambda **_kwargs: analyses),
        decision_outcome_service=_OutcomeService(outcomes),
        decision_signal_repo=SimpleNamespace(get=lambda sid: signals.get(sid)),
        backtest_service=SimpleNamespace(
            get_summary=lambda **_kwargs: {
                "completed_count": 12,
                "direction_accuracy_pct": 58.3,
                "win_rate_pct": 54.0,
                "avg_stock_return_pct": 1.2,
                "eval_window_days": 10,
                "engine_version": "v1",
            }
        ),
        skill_performance_service=SimpleNamespace(
            get_stats=lambda **_kwargs: {
                "buckets": [
                    {
                        "skill_id": "momentum",
                        "horizon": "5d",
                        "evaluated": 40,
                        "hit_rate_pct": 62.5,
                        "miss_rate_pct": 37.5,
                        "sample_sufficient": True,
                        "sample_status": "sufficient",
                    }
                ]
            }
        ),
        config_provider=lambda: config,
        clock=_fixed_clock(),
    )

    payload = service.build_payload(config=config)
    accuracy = payload["accuracy"]
    assert accuracy["status"] == "ok"
    assert accuracy["decision_signals"]["status"] == "ok"
    assert accuracy["decision_signals"]["hit_rate_pct"] == 50.0
    assert accuracy["decision_signals"]["sample_size"] == 4
    assert accuracy["decision_signals"]["notable_hits"][0]["stock_code"] == "AAPL"
    assert accuracy["decision_signals"]["notable_misses"][0]["stock_code"] == "NVDA"
    assert accuracy["backtest"]["direction_accuracy_pct"] == 58.3
    assert accuracy["skill_outcomes"]["buckets"][0]["hit_rate_pct"] == 62.5

    yesterday = payload["yesterday_analyses"]
    codes = {item["code"] for item in yesterday}
    assert "AAPL" in codes
    assert "TSLA" in codes
    assert "MARKET" not in codes
    assert DAILY_BRIEF_HISTORY_CODE not in codes
    aapl = next(item for item in yesterday if item["code"] == "AAPL")
    assert aapl["on_watchlist"] is True

    watchlist = payload["watchlist"]
    assert watchlist["total"] == 3
    assert watchlist["with_yesterday_analysis"] >= 1

    markdown = service.render_markdown(payload)
    assert "50.0%" in markdown or "50%" in markdown
    assert "58.3%" in markdown
    assert "momentum" in markdown
    assert "AAPL" in markdown
    assert "Insufficient history" not in markdown


def test_run_skips_when_disabled_and_notify_failure_does_not_abort():
    config = _base_config(daily_brief_enabled=False)
    service = DailyBriefService(config_provider=lambda: config, clock=_fixed_clock())
    skipped = service.run(force=False)
    assert skipped.skipped_reason == "disabled"

    notifier = _Notifier()

    def _boom(*_a, **_k):
        raise RuntimeError("channel down")

    notifier.send = _boom  # type: ignore[method-assign]
    enabled = _base_config(
        daily_brief_enabled=True,
        daily_brief_notify=True,
        daily_brief_persist_history=False,
        daily_brief_save_report_file=True,
        daily_brief_min_samples=100,
    )
    service = DailyBriefService(
        analysis_repo=SimpleNamespace(get_list=lambda **_kwargs: []),
        decision_outcome_service=_OutcomeService([]),
        decision_signal_repo=SimpleNamespace(get=lambda _id: None),
        backtest_service=SimpleNamespace(get_summary=lambda **_kwargs: None),
        skill_performance_service=SimpleNamespace(get_stats=lambda **_kwargs: {"buckets": []}),
        notifier=notifier,
        config_provider=lambda: enabled,
        clock=_fixed_clock(),
    )
    result = service.run(force=True, persist_history=False)
    assert result.markdown
    assert result.notification_status == "failed"
    assert result.notification_ok is False
    assert result.payload["accuracy"]["status"] == "insufficient_history"
    assert notifier.saved


def test_should_run_now_respects_schedule_and_once_per_day():
    config = _base_config(daily_brief_schedule_time="10:00")
    service = DailyBriefService(
        analysis_repo=SimpleNamespace(get_list=lambda **_kwargs: []),
        config_provider=lambda: config,
        clock=_fixed_clock("2026-08-06T09:00:00+08:00"),
    )
    assert service.should_run_now(config=config) is False

    late = DailyBriefService(
        analysis_repo=SimpleNamespace(get_list=lambda **_kwargs: []),
        config_provider=lambda: config,
        clock=_fixed_clock("2026-08-06T10:05:00+08:00"),
    )
    assert late.should_run_now(config=config) is True
    late._last_run_local_date = "2026-08-06"
    assert late.should_run_now(config=config) is False


def test_build_daily_brief_background_tasks_gated():
    from src.services.daily_brief_service import build_daily_brief_background_tasks

    off = build_daily_brief_background_tasks(
        _base_config(daily_brief_enabled=False),
        config_provider=lambda: _base_config(daily_brief_enabled=False),
    )
    assert off == []

    on = build_daily_brief_background_tasks(
        _base_config(daily_brief_enabled=True),
        config_provider=lambda: _base_config(daily_brief_enabled=True),
    )
    assert len(on) == 1
    assert on[0]["name"] == "daily_brief"
    assert on[0]["interval_seconds"] >= 30
