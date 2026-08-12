# -*- coding: utf-8 -*-
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, List, Optional
from src.services.event_research_brief_service import (
    EventResearchBriefService, build_earnings_event_brief,
    build_event_research_brief_background_tasks, resolve_event_research_brief_config,
)

class _Trigger:
    def __init__(self, trigger_id, target, message, categories=None, title="Q2 earnings"):
        self.id=trigger_id; self.target=target; self.message=message
        self.triggered_at=datetime(2026,8,6,1,0,0,tzinfo=timezone.utc)
        self.diagnostics={"event_context":{"event_category":(categories or ["earnings"])[0],
            "event_categories":categories or ["earnings"],"what_happened":title,"why_it_matters":"reprice"}}

class _AlertRepo:
    def __init__(self, rows): self.rows=rows
    def list_recent_triggered_for_targets(self, **_k): return list(self.rows)

class _Notifier:
    def __init__(self): self.sent=[]; self.saved=[]
    def is_available(self): return True
    def send(self, content, email_send_to_all=False, route_type="report"): self.sent.append(content); return True
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
    assert brief["verify_hook"]["kind"]=="post_event_checklist"
    svc=EventResearchBriefService(
        alert_repository=_AlertRepo([
            _Trigger(1,"AAPL","earnings"), _Trigger(2,"MSFT","earnings"),
            _Trigger(3,"TSLA","mna",categories=["mna"], title="M&A"),
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
    n.send=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("down"))
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
