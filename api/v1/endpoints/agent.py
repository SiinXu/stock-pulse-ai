# -*- coding: utf-8 -*-
"""
Agent API endpoints.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from api.v1.errors import api_error
from src.agent.public_contract import (
    AGENT_CHAT_FAILED,
    AGENT_CHAT_FAILURE_MESSAGE,
    AGENT_RESEARCH_FAILED,
    AGENT_RESEARCH_FAILURE_MESSAGE,
    AGENT_STREAM_FAILED,
    AGENT_STREAM_FAILURE_MESSAGE,
    AGENT_STREAM_TIMEOUT,
    AGENT_STREAM_TIMEOUT_MESSAGE,
    sanitize_agent_diagnostic,
    sanitize_stream_event,
)
from src.agent.runtime import (
    ExecutionContext,
    ExecutionLifecycle,
    ExecutionMode,
    to_public_sse_event,
)
from src.config import get_config
from src.services.agent_model_service import list_agent_model_deployments

# Tool name -> Chinese display name mapping
TOOL_DISPLAY_NAMES: Dict[str, str] = {
    "get_realtime_quote":         "获取实时行情",
    "get_daily_history":          "获取历史K线",
    "get_chip_distribution":      "分析筹码分布",
    "get_analysis_context":       "获取分析上下文",
    "get_stock_info":             "获取股票基本面",
    "search_stock_news":          "搜索股票新闻",
    "search_comprehensive_intel": "搜索综合情报",
    "analyze_trend":              "分析技术趋势",
    "calculate_ma":               "计算均线系统",
    "get_volume_analysis":        "分析量能变化",
    "analyze_pattern":            "识别K线形态",
    "get_market_indices":         "获取市场指数",
    "get_sector_rankings":        "分析行业板块",
    "get_skill_backtest_summary": "获取技能回测概览",
    "get_strategy_backtest_summary": "获取策略回测概览",
    "get_stock_backtest_summary": "获取个股回测数据",
}

logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str
    session_id: Optional[str] = None
    skills: Optional[List[str]] = Field(
        default=None,
        validation_alias=AliasChoices("skills", "strategies"),
    )
    context: Optional[Dict[str, Any]] = None  # Previous analysis context for data reuse

    @property
    def effective_skills(self) -> Optional[List[str]]:
        """Return skill ids from the unified request shape."""
        return self.skills

class ChatResponse(BaseModel):
    success: bool
    content: str
    session_id: str
    error: Optional[str] = None

class SkillInfo(BaseModel):
    id: str
    name: str
    description: str

class SkillsResponse(BaseModel):
    skills: List[SkillInfo]
    default_skill_id: str = ""


class StrategiesResponse(BaseModel):
    strategies: List[SkillInfo]
    default_strategy_id: str = ""


class AgentModelDeployment(BaseModel):
    deployment_id: str
    model: str
    provider: str
    source: str
    api_base: Optional[str] = None
    deployment_name: Optional[str] = None
    is_primary: bool = False
    is_fallback: bool = False


class AgentModelsResponse(BaseModel):
    models: List[AgentModelDeployment]


@router.get("/models", response_model=AgentModelsResponse)
async def get_agent_models():
    """Get configured Agent model deployments for frontend selection."""
    config = get_config()
    return AgentModelsResponse(
        models=[AgentModelDeployment(**item) for item in list_agent_model_deployments(config)]
    )


def _build_skills_response(config) -> SkillsResponse:
    from src.agent.factory import get_skill_manager
    from src.agent.skills.defaults import get_primary_default_skill_id

    skill_manager = get_skill_manager(config)
    available_skills = sorted(
        [
            skill
            for skill in skill_manager.list_skills()
            if getattr(skill, "user_invocable", True)
        ],
        key=lambda skill: (
            int(getattr(skill, "default_priority", 100)),
            skill.display_name,
            skill.name,
        ),
    )
    skills = [
        SkillInfo(id=skill.name, name=skill.display_name, description=skill.description)
        for skill in available_skills
    ]
    return SkillsResponse(
        skills=skills,
        default_skill_id=get_primary_default_skill_id(available_skills),
    )


@router.get("/skills", response_model=SkillsResponse)
async def get_skills():
    """
    Get available agent strategy skills.
    """
    return _build_skills_response(get_config())


@router.get("/strategies", response_model=StrategiesResponse, include_in_schema=False)
async def get_strategies():
    """Compatibility alias for legacy clients."""
    payload = _build_skills_response(get_config())
    return StrategiesResponse(
        strategies=payload.skills,
        default_strategy_id=payload.default_skill_id,
    )

@router.post("/chat", response_model=ChatResponse)
async def agent_chat(request: ChatRequest):
    """
    Chat with the AI Agent.
    """
    config = get_config()
    
    if not config.is_agent_available():
        raise api_error(400, "agent_disabled", "Agent mode is not enabled")
        
    session_id = request.session_id or str(uuid.uuid4())
    
    try:
        skills = request.effective_skills
        executor = _build_executor(config, skills or None)

        # Pass explicit skills into context for the orchestrator.
        # Direct assignment so caller-provided skills always take precedence
        # over any stale value carried in the context dict.
        ctx = dict(request.context or {})
        if skills is not None:
            ctx["skills"] = skills

        # Offload the blocking call to a thread to avoid blocking the event loop.
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: executor.chat(message=request.message, session_id=session_id,
                                  context=ctx),
        )

        if not result.success:
            logger.error(
                "Agent chat failed: session_id=%s diagnostic=%s",
                session_id,
                sanitize_agent_diagnostic(result.error),
            )
            return ChatResponse(
                success=False,
                content="",
                session_id=session_id,
                error=AGENT_CHAT_FAILED,
            )

        return ChatResponse(
            success=True,
            content=result.content,
            session_id=session_id,
            error=None,
        )
            
    except Exception as exc:
        logger.error(
            "Agent chat API failed: session_id=%s exception_type=%s diagnostic=%s",
            session_id,
            type(exc).__name__,
            sanitize_agent_diagnostic(exc),
        )
        raise api_error(500, AGENT_CHAT_FAILED, AGENT_CHAT_FAILURE_MESSAGE)


class SessionItem(BaseModel):
    session_id: str
    title: str
    message_count: int
    created_at: Optional[str] = None
    last_active: Optional[str] = None

class SessionsResponse(BaseModel):
    sessions: List[SessionItem]


class SessionMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: Optional[str] = None
    error: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class SessionMessagesResponse(BaseModel):
    session_id: str
    messages: List[SessionMessage]


@router.get("/chat/sessions", response_model=SessionsResponse)
async def list_chat_sessions(limit: int = 50, user_id: Optional[str] = None):
    """Get chat session list

    Args:
        limit: Maximum number of sessions to return.
        user_id: Optional platform-prefixed user identifier for session
            isolation.  When provided, only sessions whose session_id
            starts with this prefix are returned.  The value must
            include the platform prefix, e.g. ``telegram_12345``,
            ``feishu_ou_abc``.
    """
    from src.storage import get_db
    sessions = get_db().get_chat_sessions(
        limit=limit,
        session_prefix=user_id,
        extra_session_ids=[user_id] if user_id else None,
    )
    return SessionsResponse(sessions=sessions)


@router.get(
    "/chat/sessions/{session_id}",
    response_model=SessionMessagesResponse,
    response_model_exclude_none=True,
)
async def get_chat_session_messages(session_id: str, limit: int = 100):
    """Get the complete message for a single session"""
    from src.storage import get_db
    messages = get_db().get_conversation_messages(session_id, limit=limit)
    return SessionMessagesResponse(session_id=session_id, messages=messages)


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str):
    """Delete specified session"""
    from src.storage import get_db
    count = get_db().delete_conversation_session(session_id)
    return {"deleted": count}


class SendChatRequest(BaseModel):
    """Request body for sending chat content to notification channels."""

    content: str = Field(..., min_length=1, max_length=50000)
    title: Optional[str] = None


@router.post("/chat/send")
async def send_chat_to_notification(request: SendChatRequest):
    """
    Send chat session content to configured notification channels.
    Uses run_in_executor to avoid blocking the event loop.
    """
    from src.notification import NotificationService

    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(
        None,
        lambda: NotificationService().send(request.content),
    )
    if not success:
        return {
            "success": False,
            "error": "no_channels",
            "message": "未配置通知渠道，请先在设置中配置",
        }
    return {"success": True}


def _build_executor(config, skills: Optional[List[str]] = None):
    """Build and return a configured AgentExecutor (sync helper)."""
    from src.agent.factory import build_agent_executor
    return build_agent_executor(config, skills=skills)


async def _run_research_in_background(
    agent,
    question: str,
    context: Optional[Dict[str, Any]],
    *,
    timeout: int,
):
    """Run deep research off the event loop with an internal overall timeout."""
    return await asyncio.to_thread(
        agent.research,
        question,
        context,
        timeout_seconds=timeout,
    )


# ============================================================
# Deep research endpoint
# ============================================================

class ResearchRequest(BaseModel):
    question: str
    stock_code: Optional[str] = None

class ResearchResponse(BaseModel):
    success: bool
    content: str
    sources: List[str] = Field(default_factory=list)
    token_usage: int = 0
    error: Optional[str] = None


@router.post("/research", response_model=ResearchResponse)
async def agent_research(request: ResearchRequest):
    """Run a deep-research query via the ResearchAgent.

    Similar to the ``/research`` bot command but exposed as a REST endpoint.
    """
    config = get_config()
    if not config.is_agent_available():
        raise api_error(400, "agent_disabled", "Agent mode is not enabled")

    question = request.question
    context: Optional[Dict[str, Any]] = None
    if request.stock_code:
        question = f"[Stock: {request.stock_code}] {question}"
        context = {"stock_code": request.stock_code}

    try:
        from src.agent.research import ResearchAgent
        from src.agent.factory import get_tool_registry
        from src.agent.llm_adapter import LLMToolAdapter

        registry = get_tool_registry()
        llm_adapter = LLMToolAdapter(config)
        budget = getattr(config, "agent_deep_research_budget", 30000)

        agent = ResearchAgent(
            tool_registry=registry,
            llm_adapter=llm_adapter,
            token_budget=budget,
        )

        research_timeout = getattr(config, "agent_deep_research_timeout", 180)

        result = await _run_research_in_background(
            agent,
            question,
            context,
            timeout=research_timeout,
        )
        if getattr(result, "timed_out", False):
            logger.warning(
                "Agent research API timed out after %ss: diagnostic=%s",
                research_timeout,
                sanitize_agent_diagnostic(result.error),
            )
            return ResearchResponse(
                success=False,
                content="",
                sources=[],
                token_usage=0,
                error=AGENT_RESEARCH_FAILED,
            )

        if not result.success:
            logger.error(
                "Agent research API failed: diagnostic=%s",
                sanitize_agent_diagnostic(result.error),
            )
            return ResearchResponse(
                success=False,
                content="",
                sources=[],
                token_usage=0,
                error=AGENT_RESEARCH_FAILED,
            )

        return ResearchResponse(
            success=True,
            content=result.report,
            sources=[f"Sub-question {i+1}: {q}" for i, q in enumerate(result.sub_questions)],
            token_usage=result.total_tokens,
            error=None,
        )
    except Exception as exc:
        logger.error(
            "Agent research API failed: exception_type=%s diagnostic=%s",
            type(exc).__name__,
            sanitize_agent_diagnostic(exc),
        )
        raise api_error(500, AGENT_RESEARCH_FAILED, AGENT_RESEARCH_FAILURE_MESSAGE)


@router.post("/chat/stream")
async def agent_chat_stream(request: ChatRequest):
    """
    Chat with the AI Agent, streaming progress via SSE.
    Each SSE event is a JSON object with a 'type' field:
      - thinking: AI is deciding next action
      - stage_start: an agent or orchestrator stage has begun
      - stage_done: an agent or orchestrator stage finished
      - tool_start: a tool call has begun
      - tool_done: a tool call finished
      - generating: final answer being generated
      - pipeline_timeout: analysis stopped because the stage/pipeline budget expired
      - pipeline_budget_skipped: analysis stopped before an unstarted stage
        because the remaining budget was too low for useful work
      - done: analysis complete, contains 'content' and 'success'
      - error: error occurred, contains 'message'
    """
    config = get_config()
    if not config.is_agent_available():
        raise api_error(400, "agent_disabled", "Agent mode is not enabled")

    session_id = request.session_id or str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    # Pass explicit skills into context for the orchestrator.
    # Direct assignment so caller-provided skills always take precedence.
    skills = request.effective_skills
    stream_ctx = dict(request.context or {})
    if skills is not None:
        stream_ctx["skills"] = skills

    # Bind this stream to one runtime execution: it owns the versioned
    # event stream (with its late-write fence) and the cancellation intent
    # consumed cooperatively by the native loop when the client disconnects.
    lifecycle = ExecutionLifecycle(
        ExecutionContext(
            mode=ExecutionMode.CHAT,
            prompt=request.message,
            session_id=session_id,
            request_context=stream_ctx,
        )
    )

    def progress_callback(event: dict):
        # Enrich tool events with display names
        if event.get("type") in ("tool_start", "tool_done"):
            tool = event.get("tool", "")
            event["display_name"] = TOOL_DISPLAY_NAMES.get(tool, tool)
        # Uplift the legacy progress dict to a typed runtime event. A None
        # return means the late-write fence dropped it after the terminal
        # state; such events must never reach the wire.
        runtime_event = lifecycle.ingest_progress_event(event)
        if runtime_event is None:
            return
        public_event = sanitize_stream_event(
            to_public_sse_event(runtime_event), trace_id=session_id
        )
        asyncio.run_coroutine_threadsafe(queue.put(public_event), loop)

    def run_sync():
        try:
            lifecycle.start()
            executor = _build_executor(config, skills or None)
            result = executor.chat(
                message=request.message,
                session_id=session_id,
                progress_callback=progress_callback,
                context=stream_ctx,
                cancelled_check=lifecycle.cancelled_check,
            )
            lifecycle.finish_from_result(result)
            if not result.success and not getattr(result, "cancelled", False):
                logger.error(
                    "Agent stream chat failed: session_id=%s diagnostic=%s",
                    session_id,
                    sanitize_agent_diagnostic(result.error),
                )
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "type": "done",
                    "success": result.success,
                    "content": result.content if result.success else "",
                    "error": None if result.success else AGENT_CHAT_FAILED,
                    "message": None if result.success else AGENT_CHAT_FAILURE_MESSAGE,
                    "params": {},
                    "details": None,
                    "trace_id": session_id,
                    "total_steps": result.total_steps,
                    "session_id": session_id,
                }),
                loop,
            )
        except Exception as exc:
            lifecycle.fail(sanitize_agent_diagnostic(exc))
            logger.error(
                "Agent stream error: session_id=%s exception_type=%s diagnostic=%s",
                session_id,
                type(exc).__name__,
                sanitize_agent_diagnostic(exc),
            )
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "type": "error",
                    "error": AGENT_STREAM_FAILED,
                    "message": AGENT_STREAM_FAILURE_MESSAGE,
                    "params": {},
                    "details": None,
                    "trace_id": session_id,
                }),
                loop,
            )

    async def event_generator():
        # Start executor in a thread so we don't block the event loop
        fut = loop.run_in_executor(None, run_sync)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    yield "data: " + json.dumps({
                        "type": "error",
                        "error": AGENT_STREAM_TIMEOUT,
                        "message": AGENT_STREAM_TIMEOUT_MESSAGE,
                        "params": {"timeout_seconds": 300},
                        "details": None,
                        "trace_id": session_id,
                    }, ensure_ascii=False) + "\n\n"
                    break
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if event.get("type") in ("done", "error"):
                    break
        finally:
            # If the client disconnected (or the stream ended) before the
            # execution terminated, signal cooperative cancellation so the
            # native loop stops at its next checkpoint instead of burning a
            # full LLM/tool cycle no one is listening to.
            lifecycle.request_cancel()
            try:
                await asyncio.wait_for(fut, timeout=5.0)
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                # Cleanup taking longer than 5s is treated as an expected timeout; no warning.
                logger.debug("agent executor cleanup timed out after 5s for session %s", session_id)
            except Exception as exc:
                logger.warning(
                    "agent executor cleanup error (ignored): session_id=%s "
                    "exception_type=%s diagnostic=%s",
                    session_id,
                    type(exc).__name__,
                    sanitize_agent_diagnostic(exc),
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
