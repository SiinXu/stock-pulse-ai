# -*- coding: utf-8 -*-
"""Provider message conversion and response parsing methods."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.agent.provider_trace import (
    resolved_model_provider_identity,
    resolved_provider_namespace,
)
from src.llm.provider_cache import filter_prompt_cache_telemetry
from src.llm.usage import (
    attach_message_hmacs,
    extract_usage_payload,
    normalize_litellm_usage,
)

if TYPE_CHECKING:
    from src.agent.llm_adapter import (
        LLMResponse,
        ToolCall,
        _extract_provider_blocks,
        _message_trace_matches_target,
        _provider_specific_fields_from,
    )


class _MessageMethods:
    """Source container rebound onto ``LLMToolAdapter`` by the facade."""

    def _convert_messages(
        self,
        messages: List[Dict[str, Any]],
        *,
        target_model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Convert internal message format to OpenAI-compatible format for litellm."""
        openai_messages: List[Dict[str, Any]] = []
        target_provider = self._trace_provider_for_target(target_model)
        for msg in messages:
            trace_matches_target = _message_trace_matches_target(
                msg,
                target_model,
                target_provider=target_provider,
            )
            if not trace_matches_target:
                continue
            if msg["role"] == "tool":
                openai_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": msg["content"] if isinstance(msg["content"], str) else json.dumps(msg["content"]),
                })
            elif msg["role"] == "assistant" and msg.get("tool_calls"):
                openai_tc = []
                for tc in msg["tool_calls"]:
                    tc_dict: Dict[str, Any] = {
                        "id": tc.get("id", str(uuid.uuid4())[:8]),
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    provider_specific_fields = dict(tc.get("provider_specific_fields") or {})
                    sig = tc.get("thought_signature")
                    if sig is not None:
                        provider_specific_fields.setdefault("thought_signature", sig)
                    if provider_specific_fields:
                        tc_dict["provider_specific_fields"] = provider_specific_fields
                    openai_tc.append(tc_dict)
                content = (
                    msg.get("provider_blocks")
                    if msg.get("provider_blocks")
                    else msg.get("content")
                )
                openai_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": openai_tc,
                }
                if msg.get("reasoning_content") is not None:
                    openai_msg["reasoning_content"] = msg["reasoning_content"]
                openai_messages.append(openai_msg)
            else:
                openai_messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })
        return openai_messages

    def _trace_provider_for_target(self, target_model: Optional[str]) -> str:
        if not target_model:
            return ""
        resolution = getattr(self, "_route_resolution", None)
        model_list = (
            getattr(resolution, "model_list", None)
            or getattr(getattr(self, "_config", None), "llm_model_list", [])
            or []
        )
        return resolved_provider_namespace(target_model, model_list)

    def _parse_litellm_response(
        self,
        response: Any,
        model: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        *,
        model_list: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
        """Parse litellm OpenAI-compatible response into LLMResponse."""
        choice = response.choices[0]
        tool_calls: List[ToolCall] = []

        provider_blocks, provider_text = _extract_provider_blocks(choice)

        # Handle MiniMax-specific content_blocks format
        # MiniMax-M3 may return content_blocks at choice level or inside message
        # Check both possible locations for content_blocks to ensure consistency
        # Concatenate ALL text blocks to avoid truncating multi-block responses
        text_content = choice.message.content
        if isinstance(text_content, list):
            text_content = provider_text
        if text_content is None:
            text_content = provider_text

        # DeepSeek/Qwen thinking mode; not in standard OpenAI type, accessed via getattr
        reasoning_content = getattr(choice.message, "reasoning_content", None)

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                args: Dict[str, Any] = {}
                if tc.function.arguments:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {"raw": tc.function.arguments}

                provider_specific_fields = _provider_specific_fields_from(
                    getattr(tc, "provider_specific_fields", None)
                )
                provider_specific_fields.update(
                    _provider_specific_fields_from(
                        getattr(tc.function, "provider_specific_fields", None)
                    )
                )
                sig = provider_specific_fields.get("thought_signature")
                if sig is None:
                    sig = getattr(tc, "thought_signature", None)
                raw_tool_name = tc.function.name
                tool_name = raw_tool_name if type(raw_tool_name) is str else ""

                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tool_name,
                    arguments=args,
                    thought_signature=sig,
                    provider_specific_fields=provider_specific_fields,
                ))

        usage_model_list = (
            model_list
            if model_list is not None
            else getattr(getattr(self, "_config", None), "llm_model_list", []) or []
        )
        usage_model, provider_name = resolved_model_provider_identity(model, usage_model_list)
        usage_payload = extract_usage_payload(response)
        if usage_payload:
            usage = normalize_litellm_usage(
                usage_payload,
                model=usage_model or model,
                provider=provider_name,
            )
            usage = attach_message_hmacs(usage, messages)
            usage = filter_prompt_cache_telemetry(usage, getattr(self, "_config", None))
        else:
            usage = {}
        return LLMResponse(
            content=text_content,
            tool_calls=tool_calls,
            reasoning_content=reasoning_content,
            provider_blocks=provider_blocks,
            usage=usage,
            provider=provider_name,
            model=model,
            raw=response,
        )
