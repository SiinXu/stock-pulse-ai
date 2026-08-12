# -*- coding: utf-8 -*-
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from src.services.event_research_brief_service import (
    MAX_EVENT_BRIEF_MARKDOWN_CHARS,
    EventResearchBriefService, build_earnings_event_brief,
    build_event_research_brief_background_tasks, resolve_event_research_brief_config,
)
from src.services.event_alerts import CORPORATE_EVENT_DATA_SOURCE

class _Trigger:
    def __init__(self, trigger_id, target, reason, categories=None, title="Q2 earnings", *, data_source=CORPORATE_EVENT_DATA_SOURCE):
        self.id=trigger_id; self.target=target; self.reason=reason; self.data_source=data_source
        self.triggered_at=datetime(2026,8,6,1,0,0,tzinfo=timezone.utc)
        self.diagnostics=json.dumps({"event_context":{"event_category":(categories or ["earnings"])[0],
            "event_categories":categories or ["earnings"],"what_happened":title,"why_it_matters":"reprice"}})

class _AlertRepo:
    def __init__(self, rows): self.rows=rows
    def list_recent_triggered_for_targets(self, **_k): return list(self.rows)

class _Notifier:
    def __init__(self): self.sent=[]; self.saved=[]; self.dispatches=[]
    def is_available(self): return True
    def send_with_results(self, content, **_kwargs):
        self.sent.append(content)
        return self.dispatches.pop(0) if self.dispatches else SimpleNamespace(status="sent", success=True)
    def save_report_to_file(self, content, filename): self.saved.append(filename); return filename

def _cfg(**o):
    d=dict(event_research_brief_enabled=True, event_research_brief_notify=False,
           event_research_brief_persist_history=False, event_research_brief_save_report_file=False,
           event_research_brief_lookback_hours=48, event_research_brief_categories="earnings",
           report_language="en", stock_list=["AAPL","MSFT"], report_templates_dir="templates")
    d.update(o); return SimpleNamespace(**d)

def test_structure_and_universe():
    brief=build_earnings_event_brief(stock_code="aapl", stock_name="Apple",
        event_context={"event_category":"earnings","what_happened":"Print"}, on_watchlist=True, in_portfolio=True, report_language="en")
    assert brief["event_category"]=="earnings" and brief["metrics_to_watch"] and brief["post_event_checklist"]
    assert brief["phase"]=="observed_event_review"
    assert brief["verify_hook"]["kind"]=="post_event_checklist"
    svc=EventResearchBriefService(
        alert_repository=_AlertRepo([
            _Trigger(1,"AAPL","earnings"), _Trigger(2,"MSFT","earnings"),
            _Trigger(3,"TSLA","mna",categories=["mna"], title="M&A"),
            _Trigger(4,"AAPL","earnings",data_source="manual"),
        ]),
        portfolio_repository=type("P",(),{"list_cached_positions":staticmethod(lambda **_k:[{"symbol":"AAPL"}])})(),
        config_provider=lambda:_cfg(), clock=lambda:datetime(2026,8,6,8,0,tzinfo=timezone.utc),
    )
    briefs=svc.build_briefs_for_universe(config=_cfg())
    codes=[b["stock_code"] for b in briefs]
    assert codes[0]=="AAPL" and "MSFT" in codes and "TSLA" not in codes
    md=svc.render_markdown(briefs[0]); assert "Metrics to watch" in md

def test_notify_fail_open_and_gate():
    n=_Notifier()
    n.send_with_results=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("down"))
    svc=EventResearchBriefService(
        alert_repository=_AlertRepo([_Trigger(1,"AAPL","earnings")]),
        portfolio_repository=type("P",(),{"list_cached_positions":staticmethod(lambda **_k:[])})(),
        notifier=n, config_provider=lambda:_cfg(event_research_brief_notify=True,event_research_brief_save_report_file=True),
        clock=lambda:datetime(2026,8,6,8,0,tzinfo=timezone.utc),
    )
    result=svc.run(force=True)
    assert result.briefs and result.notification_status=="failed" and n.saved
    assert build_event_research_brief_background_tasks(_cfg(event_research_brief_enabled=False), config_provider=lambda:_cfg(event_research_brief_enabled=False))==[]
    on=build_event_research_brief_background_tasks(_cfg(), config_provider=lambda:_cfg())
    assert on and on[0]["name"]=="event_research_brief"
    assert resolve_event_research_brief_config(SimpleNamespace()).enabled is False


def test_structured_partial_dispatch_and_failed_delivery_retry():
    notifier = _Notifier()
    notifier.dispatches = [
        SimpleNamespace(status="all_failed", success=False),
        SimpleNamespace(status="partial_failed", success=True),
    ]
    service = EventResearchBriefService(
        alert_repository=_AlertRepo([_Trigger(10, "AAPL", "earnings")]),
        portfolio_repository=SimpleNamespace(list_cached_positions=lambda **_kwargs: []),
        notifier=notifier,
        config_provider=lambda: _cfg(event_research_brief_notify=True),
        clock=lambda:datetime(2026,8,6,8,0,tzinfo=timezone.utc),
    )

    failed = service.run(force=True)
    retried = service.run(force=True)
    completed = service.run(force=True)

    assert failed.notification_status == "degraded" and failed.notification_ok is False
    assert retried.notification_status == "degraded" and retried.notification_ok is True
    assert completed.skipped_reason == "no_fresh_events"
    assert len(notifier.sent) == 2


def test_real_trigger_json_is_strict_and_wrong_source_is_rejected():
    valid = _Trigger(1, "AAPL", "earnings")
    invalid_json = _Trigger(2, "MSFT", "earnings")
    invalid_json.diagnostics = '{"event_context":{"event_category":"earnings","score":NaN}}'
    wrong_source = _Trigger(3, "AAPL", "earnings", data_source="manual")
    service = EventResearchBriefService(
        alert_repository=_AlertRepo([valid, invalid_json, wrong_source]),
        portfolio_repository=SimpleNamespace(list_cached_positions=lambda **_kwargs: []),
        config_provider=lambda: _cfg(),
        clock=lambda:datetime(2026,8,6,8,0,tzinfo=timezone.utc),
    )

    briefs = service.build_briefs_for_universe(config=_cfg())

    assert [brief["stock_code"] for brief in briefs] == ["AAPL"]
    assert briefs[0]["what_happened"] == "Q2 earnings"


def test_event_markdown_obeys_length_budget():
    brief = build_earnings_event_brief(stock_code="AAPL", report_language="en")
    brief["metrics_to_watch"] = [
        {"label": "X" * 100, "why": "Y" * 500} for _ in range(100)
    ]
    service = EventResearchBriefService()

    markdown = service.render_markdown(brief)

    assert len(markdown) <= MAX_EVENT_BRIEF_MARKDOWN_CHARS
    assert "Content truncated to the report length budget" in markdown
