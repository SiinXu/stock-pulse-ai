"""Configuration defaults and value objects for :mod:`src.config`."""

import logging
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional
from urllib.parse import unquote, urlparse

from src.config_parts.binding import bind_wrapped_function, clone_descriptor

logger = logging.getLogger("src.config")

DEFAULT_ALPHASIFT_INSTALL_SPEC = (
    "git+https://github.com/ZhuLinsen/alphasift.git@9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf"
)


@dataclass
class ConfigIssue:
    """Structured configuration validation issue with a severity level.

    Attributes:
        severity: One of "error", "warning", or "info".
        message:  Human-readable description of the issue.
        field:    The environment variable / config field name most relevant to
                  this issue (empty string when not applicable).
    """

    severity: Literal["error", "warning", "info"]
    message: str
    field: str = ""
    code: str = ""

    def __str__(self) -> str:  # noqa: D105
        return self.message


_MANAGED_LITELLM_KEY_PROVIDERS = {"gemini", "vertex_ai", "anthropic", "openai", "deepseek"}
SUPPORTED_LLM_CHANNEL_PROTOCOLS = ("openai", "anthropic", "gemini", "vertex_ai", "deepseek", "ollama")
_FALSEY_ENV_VALUES = {"0", "false", "no", "off"}
PROMPT_CACHE_DIAGNOSTICS_LEVELS = {"off", "basic", "debug"}
TICKFLOW_KLINE_ADJUST_VALUES = {"none", "forward", "backward", "forward_additive", "backward_additive"}
# Fallback defaults used when ANSPIRE_API_KEYS is reused as legacy OpenAI-compatible source.
# These are compatibility examples; actual availability should be validated by Anspire console/model entitlement.
ANSPIRE_LLM_BASE_URL_DEFAULT = "https://open-gateway.anspire.cn/v6"
ANSPIRE_LLM_MODEL_DEFAULT = "Doubao-Seed-2.0-lite"


def _has_ntfy_topic_endpoint(value: Optional[str]) -> bool:
    """Return whether an ntfy URL points at a concrete topic endpoint."""
    raw_url = (value or "").strip()
    if not raw_url:
        return False
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return False
    return any(unquote(segment).strip() for segment in parsed.path.split("/") if segment)


def _has_gotify_base_url(value: Optional[str]) -> bool:
    """Return whether a Gotify URL points at a server base URL, not /message."""
    raw_url = (value or "").strip().rstrip("/")
    if not raw_url:
        return False
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.query or parsed.fragment:
        return False
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    return not (path_segments and path_segments[-1].lower() == "message")


def normalize_tickflow_kline_adjust(value: Optional[str]) -> str:
    """Normalize TickFlow daily K-line adjustment mode."""
    normalized = (value or "none").strip().lower()
    if normalized in TICKFLOW_KLINE_ADJUST_VALUES:
        return normalized
    logger.warning(
        "Invalid TICKFLOW_KLINE_ADJUST=%r; falling back to none",
        value,
    )
    return "none"


def parse_prompt_cache_diagnostics_level(value: Optional[str]) -> str:
    """Parse prompt-cache diagnostics level with a conservative fallback."""
    normalized = (value or "off").strip().lower()
    if normalized in PROMPT_CACHE_DIAGNOSTICS_LEVELS:
        return normalized
    logger.warning(
        "Invalid LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL=%r; falling back to off",
        value,
    )
    return "off"


AGENT_MAX_STEPS_DEFAULT = 10
FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT = 8.0
PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS_DEFAULT = 7
NEWS_STRATEGY_WINDOWS: Dict[str, int] = {
    "ultra_short": 1,
    "short": 3,
    "medium": 7,
    "long": 30,
}


@dataclass(frozen=True)
class AgentContextCompressionPreset:
    """Preset values for visible chat history compression."""

    trigger_tokens: int
    protected_turns: int
    summary_target_tokens: int
    # P1 reserves this budget for future prompt-size controls; it is not
    # enforced by the current rolling-summary state table.
    history_budget_tokens: int


AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE = "balanced"
AGENT_CONTEXT_COMPRESSION_PROFILES: Dict[str, AgentContextCompressionPreset] = {
    "cost": AgentContextCompressionPreset(
        trigger_tokens=6000,
        protected_turns=2,
        summary_target_tokens=900,
        history_budget_tokens=4000,
    ),
    "balanced": AgentContextCompressionPreset(
        trigger_tokens=12000,
        protected_turns=4,
        summary_target_tokens=1500,
        history_budget_tokens=8000,
    ),
    "long_context_raw_first": AgentContextCompressionPreset(
        trigger_tokens=24000,
        protected_turns=6,
        summary_target_tokens=2600,
        history_budget_tokens=14000,
    ),
}

for _compat_name, _compat_value in tuple(globals().items()):
    if getattr(_compat_value, "__module__", None) == __name__:
        _compat_value.__module__ = "src.config"

for _compat_class in (ConfigIssue, AgentContextCompressionPreset):
    for _compat_descriptor in vars(_compat_class).values():
        if isinstance(_compat_descriptor, (classmethod, staticmethod)):
            _compat_functions = (_compat_descriptor.__func__,)
        elif isinstance(_compat_descriptor, property):
            _compat_functions = tuple(
                function
                for function in (
                    _compat_descriptor.fget,
                    _compat_descriptor.fset,
                    _compat_descriptor.fdel,
                )
                if function is not None
            )
        elif callable(_compat_descriptor):
            _compat_functions = (_compat_descriptor,)
        else:
            _compat_functions = ()
        for _compat_function in _compat_functions:
            if getattr(_compat_function, "__module__", None) == __name__:
                _compat_function.__module__ = "src.config"

del _compat_name, _compat_value
del _compat_class, _compat_descriptor, _compat_function, _compat_functions


def _bind_config_facade(facade_globals: Dict[str, object]) -> None:
    """Bind facade-owned dataclass methods to the original global namespace."""
    for compat_class in (ConfigIssue, AgentContextCompressionPreset):
        for method_name, descriptor in tuple(vars(compat_class).items()):
            if isinstance(descriptor, (classmethod, staticmethod)):
                function = descriptor.__func__
            elif callable(descriptor):
                function = descriptor
            else:
                continue
            bind_wrapped_function(function, facade_globals)
            if getattr(function, "__globals__", None) is not globals():
                continue
            cloned_descriptor = clone_descriptor(descriptor, facade_globals)
            cloned_function = (
                cloned_descriptor.__func__
                if isinstance(cloned_descriptor, (classmethod, staticmethod))
                else cloned_descriptor
            )
            cloned_function.__module__ = "src.config"
            cloned_function.__qualname__ = f"{compat_class.__name__}.{method_name}"
            setattr(compat_class, method_name, cloned_descriptor)
