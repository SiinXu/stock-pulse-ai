# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 存储层
===================================

职责：
1. 管理 SQLite 数据库连接（单例模式）
2. 定义 ORM 数据模型
3. 提供数据存取接口
4. 实现智能更新逻辑（断点续传）
"""

import atexit
from contextlib import contextmanager
import hashlib
from importlib import reload as _reload
from importlib.util import find_spec as _find_spec
import json
import logging
import threading
import time
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any, TYPE_CHECKING, Tuple, Callable, TypeVar, Union

import pandas as pd
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Float,
    Boolean,
    Date,
    DateTime,
    Integer,
    ForeignKey,
    Index,
    UniqueConstraint,
    Text,
    select,
    and_,
    or_,
    delete,
    desc,
    event,
    func,
    inspect,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    Session,
)
from sqlalchemy.exc import IntegrityError, OperationalError

from src.agent.provider_trace import PROVIDER_TRACE_RETENTION_LIMIT
from src.agent.public_contract import (
    agent_history_public_fields,
    sanitize_agent_history_content,
)
from src.config import get_config
from src.migrations.engine import create_database_engine
from src.migrations.legacy_profiles import (
    match_legacy_schema_profile,
    sqlite_type_affinity,
)
from src.migrations.registry import LEGACY_BASELINE_MIGRATION
from src.migrations.runner import (
    apply_pending_within_transaction,
    preflight_existing,
)
from src.migrations.types import MigrationError
from src.storage_parts.binding import (
    bind_storage_facade_methods as _bind_storage_facade_methods,
)
from src.utils.sanitize import log_safe_exception
from src.utils.sniper_points import extract_sniper_points, parse_sniper_value

logger = logging.getLogger(__name__)
T = TypeVar("T")
CURRENT_SCHEMA_VERSION = LEGACY_BASELINE_MIGRATION.id
INTELLIGENCE_ITEM_NULL_SCOPE_VALUE = "__dsa_null_scope__"
PORTFOLIO_LEGACY_IDEMPOTENCY_GUARD_TRIGGER = (
    "trg_portfolio_idempotency_legacy_key_guard"
)

# SQLAlchemy ORM base class
Base = declarative_base()

_STORAGE_FACADE_COMPAT_GLOBALS = (
    atexit,
    contextmanager,
    hashlib,
    json,
    time,
    timedelta,
    List,
    Tuple,
    Callable,
    Union,
    create_engine,
    select,
    and_,
    or_,
    delete,
    desc,
    event,
    func,
    inspect,
    sqlite_insert,
    sessionmaker,
    Session,
    IntegrityError,
    OperationalError,
    PROVIDER_TRACE_RETENTION_LIMIT,
    agent_history_public_fields,
    sanitize_agent_history_content,
    get_config,
    create_database_engine,
    match_legacy_schema_profile,
    sqlite_type_affinity,
    apply_pending_within_transaction,
    preflight_existing,
    MigrationError,
    extract_sniper_points,
    parse_sniper_value,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from src.storage_parts.schema import (
        AnalysisHistory,
        ConversationMessage,
        LLMUsage,
        StockDaily,
        _LLM_PROMPT_CACHE_TELEMETRY_COLUMNS,
        _LLM_PROMPT_CACHE_TELEMETRY_DISABLED_ATTR,
        _LLM_USAGE_INTEGER_TELEMETRY_COLUMNS,
        _LLM_USAGE_TELEMETRY_COLUMN_SQL,
    )


_storage_schema_spec = _find_spec("src.storage_parts.schema")
if _storage_schema_spec is None or _storage_schema_spec.loader is None:
    raise ImportError("Unable to load the storage schema source module")
_storage_schema_code = _storage_schema_spec.loader.get_code(
    "src.storage_parts.schema"
)
if _storage_schema_code is None:
    raise ImportError("Storage schema source module has no executable code")
exec(_storage_schema_code, globals())
del _storage_schema_code, _storage_schema_spec


class _DatabaseManagerMeta(type):
    """Serialize DatabaseManager construction across __new__ and __init__."""

    def __call__(cls, *args, **kwargs):
        with cls._init_lock:
            return super().__call__(*args, **kwargs)


class DatabaseManager(metaclass=_DatabaseManagerMeta):
    """
    数据库管理器 - 单例模式
    
    职责：
    1. 管理数据库连接池
    2. 提供 Session 上下文管理
    3. 封装数据存取操作
    """
    
    _instance: Optional['DatabaseManager'] = None
    _init_lock = threading.RLock()
    _initialized: bool = False


# Import after the facade types exist so source annotations retain the original
# eager runtime objects. Reload stale containers when this facade is reloaded.
from src.storage_parts import conversation as _storage_conversation  # noqa: E402
from src.storage_parts import history as _storage_history  # noqa: E402
from src.storage_parts import lifecycle as _storage_lifecycle  # noqa: E402
from src.storage_parts import market_data as _storage_market_data  # noqa: E402
from src.storage_parts import usage as _storage_usage  # noqa: E402

if _storage_lifecycle.T is not T:
    _storage_lifecycle = _reload(_storage_lifecycle)
if _storage_market_data.StockDaily is not StockDaily:
    _storage_market_data = _reload(_storage_market_data)
if _storage_history.AnalysisHistory is not AnalysisHistory:
    _storage_history = _reload(_storage_history)
if _storage_conversation.ConversationMessage is not ConversationMessage:
    _storage_conversation = _reload(_storage_conversation)
if _storage_usage.LLMUsage is not LLMUsage:
    _storage_usage = _reload(_storage_usage)

_LifecycleMethods = _storage_lifecycle._LifecycleMethods
_MarketDataMethods = _storage_market_data._MarketDataMethods
_HistoryMethods = _storage_history._HistoryMethods
_ConversationMethods = _storage_conversation._ConversationMethods
_UsageMethods = _storage_usage._UsageMethods

_LIFECYCLE_METHOD_NAMES = _bind_storage_facade_methods(
    DatabaseManager, _LifecycleMethods, globals()
)
_MARKET_DATA_METHOD_NAMES = _bind_storage_facade_methods(
    DatabaseManager, _MarketDataMethods, globals()
)
_HISTORY_METHOD_NAMES = _bind_storage_facade_methods(
    DatabaseManager, _HistoryMethods, globals()
)
_CONVERSATION_METHOD_NAMES = _bind_storage_facade_methods(
    DatabaseManager, _ConversationMethods, globals()
)
_USAGE_METHOD_NAMES = _bind_storage_facade_methods(
    DatabaseManager, _UsageMethods, globals()
)


# Convenience functions
def get_db() -> DatabaseManager:
    """Return the process-wide DatabaseManager via the application composition root.

    Delegating through the composition root keeps a single owner for the
    instance and lets tests inject an isolated DatabaseManager. The default
    root resolves to ``DatabaseManager.get_instance()``, so behaviour is
    unchanged when nothing is injected.
    """
    from src.application_services import get_application_services

    return get_application_services().database


def persist_llm_usage(
    usage: Dict[str, Any],
    model: str,
    call_type: str,
    stock_code: Optional[str] = None,
) -> None:
    """Fire-and-forget: write one LLM call record to llm_usage. Never raises."""
    try:
        if usage is None:
            usage = {}
        prompt_cache_telemetry_disabled = bool(
            getattr(usage, _LLM_PROMPT_CACHE_TELEMETRY_DISABLED_ATTR, False)
        )
        prompt_tokens = _coerce_llm_usage_non_negative_int(usage.get("prompt_tokens")) or 0
        completion_tokens = _coerce_llm_usage_non_negative_int(usage.get("completion_tokens")) or 0
        total_tokens = _coerce_llm_usage_non_negative_int(usage.get("total_tokens")) or 0
        telemetry = {
            column: usage.get(column)
            for column in _LLM_USAGE_TELEMETRY_COLUMN_SQL
        }
        if prompt_cache_telemetry_disabled:
            for column in _LLM_PROMPT_CACHE_TELEMETRY_COLUMNS:
                telemetry[column] = None
        for column in _LLM_USAGE_INTEGER_TELEMETRY_COLUMNS:
            telemetry[column] = _coerce_llm_usage_non_negative_int(telemetry.get(column))
        telemetry["normalized_prompt_tokens"] = (
            telemetry.get("normalized_prompt_tokens")
            if telemetry.get("normalized_prompt_tokens") is not None
            else prompt_tokens
        )
        telemetry["normalized_completion_tokens"] = (
            telemetry.get("normalized_completion_tokens")
            if telemetry.get("normalized_completion_tokens") is not None
            else completion_tokens
        )
        telemetry["normalized_total_tokens"] = (
            telemetry.get("normalized_total_tokens")
            if telemetry.get("normalized_total_tokens") is not None
            else total_tokens
        )
        has_usage_payload = bool(usage.get("provider_usage_json")) or any(
            key in usage
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "normalized_prompt_tokens",
                "normalized_completion_tokens",
                "normalized_total_tokens",
            )
        )
        if not prompt_cache_telemetry_disabled:
            telemetry["cache_capability"] = usage.get("cache_capability") or "unknown"
            telemetry["cache_eligibility"] = usage.get("cache_eligibility") or "unknown"
            telemetry["cache_observation"] = usage.get("cache_observation") or (
                "no_usage" if not has_usage_payload else "unknown"
            )
        db = DatabaseManager.get_instance()
        db.record_llm_usage(
            call_type=call_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            stock_code=stock_code,
            **telemetry,
        )
    except Exception as exc:
        log_safe_exception(
            logger,
            "LLM usage record persistence failed",
            exc,
            error_code="storage_llm_usage_persistence_failed",
            level=logging.WARNING,
        )


def _coerce_llm_usage_non_negative_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if value < 0 or not value.is_integer():
            return None
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or not text.isdigit():
            return None
        return int(text)
    return None


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.DEBUG)
    
    db = get_db()
    
    print("=== 数据库测试 ===")
    print(f"数据库初始化成功")
    
    # Test today's-data lookup
    has_data = db.has_today_data('600519')
    print(f"茅台今日是否有数据: {has_data}")
    
    # Test saving data
    test_df = pd.DataFrame({
        'date': [date.today()],
        'open': [1800.0],
        'high': [1850.0],
        'low': [1780.0],
        'close': [1820.0],
        'volume': [10000000],
        'amount': [18200000000],
        'pct_chg': [1.5],
        'ma5': [1810.0],
        'ma10': [1800.0],
        'ma20': [1790.0],
        'volume_ratio': [1.2],
    })
    
    saved = db.save_daily_data(test_df, '600519', 'TestSource')
    print(f"保存测试数据: {saved} 条")
    
    # Test context retrieval
    context = db.get_analysis_context('600519')
    print(f"分析上下文: {context}")
