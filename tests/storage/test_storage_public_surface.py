"""Guard the compatibility surface of :mod:`src.storage`."""

import __future__
import ast
import builtins
import contextlib
import hashlib
import importlib
import inspect
import json
import subprocess
import sys
import typing
from pathlib import Path
from types import CodeType, FunctionType


EXPECTED_PUBLIC_EXPORTS = frozenset(
    """
    AgentProviderTurn AlertCooldownRecord AlertNotificationRecord
    AlertRuleRecord AlertTriggerRecord AnalysisHistory Any BacktestResult
    BacktestSummary Base Boolean CURRENT_SCHEMA_VERSION Callable Column
    ConversationMessage ConversationSummary DatabaseManager
    DatabaseSchemaMigration Date DateTime DecisionSignalFeedbackRecord
    DecisionSignalMemoryFlagRecord
    DecisionSignalOutcomeRecord DecisionSignalRecord Dict Float ForeignKey
    FundamentalSnapshot INTELLIGENCE_ITEM_NULL_SCOPE_VALUE Index Integer
    IntegrityError IntelligenceItem IntelligenceSource
    LEGACY_BASELINE_MIGRATION LLMUsage List MigrationError NewsIntel
    OperationalError Optional PORTFOLIO_LEGACY_IDEMPOTENCY_GUARD_TRIGGER
    PROVIDER_TRACE_RETENTION_LIMIT PortfolioAccount PortfolioAccountKind
    PortfolioCashLedger
    PortfolioCorporateAction PortfolioDailySnapshot PortfolioFxRate
    PortfolioIdempotencyRecord PortfolioPosition PortfolioPositionLot
    PortfolioTrade ScheduledTaskRecord ScheduledTaskRunRecord Session StockDaily
    String T TYPE_CHECKING Text Tuple
    TypeVar Union UniqueConstraint agent_history_public_fields and_
    apply_pending_within_transaction atexit contextmanager
    create_database_engine create_engine date datetime declarative_base delete
    desc event extract_sniper_points func get_config get_db hashlib inspect json
    log_safe_exception logger logging match_legacy_schema_profile or_
    parse_sniper_value pd persist_llm_usage preflight_existing
    sanitize_agent_history_content select sessionmaker sqlite_insert
    sqlite_type_affinity threading time timedelta timezone
    to_utc_naive_datetime utc_naive_now
    """.split()
)

EXPECTED_SCHEMA_DEFINITIONS = (
    "utc_naive_now",
    "to_utc_naive_datetime",
    "DatabaseSchemaMigration",
    "StockDaily",
    "NewsIntel",
    "IntelligenceSource",
    "IntelligenceItem",
    "FundamentalSnapshot",
    "AnalysisHistory",
    "BacktestResult",
    "BacktestSummary",
    "PortfolioAccount",
    "PortfolioIdempotencyRecord",
    "PortfolioTrade",
    "PortfolioCashLedger",
    "PortfolioCorporateAction",
    "PortfolioPosition",
    "PortfolioPositionLot",
    "PortfolioDailySnapshot",
    "PortfolioFxRate",
    "ConversationMessage",
    "ConversationSummary",
    "AgentProviderTurn",
    "LLMUsage",
    "_LLM_USAGE_TELEMETRY_COLUMN_SQL",
    "_LLM_USAGE_INTEGER_TELEMETRY_COLUMNS",
    "_LLM_USAGE_DROPPED_FREE_TEXT_COLUMNS",
    "_LLM_PROMPT_CACHE_TELEMETRY_DISABLED_ATTR",
    "_LLM_PROMPT_CACHE_TELEMETRY_COLUMNS",
    "AlertRuleRecord",
    "AlertTriggerRecord",
    "AlertNotificationRecord",
    "AlertCooldownRecord",
    "DecisionSignalRecord",
    "DecisionSignalOutcomeRecord",
    "DecisionSignalFeedbackRecord",
    "ScheduledTaskRecord",
    "ScheduledTaskRunRecord",
)
EXPECTED_SCHEMA_AST_HASH = (
    "aaafae447bd2f2496beccbc9ee8bbfbb7b0f3eed81eaf51f058c76703d699a96"
)
EXPECTED_SCHEMA_MODELS = (
    "DatabaseSchemaMigration",
    "StockDaily",
    "NewsIntel",
    "IntelligenceSource",
    "IntelligenceItem",
    "FundamentalSnapshot",
    "AnalysisHistory",
    "BacktestResult",
    "BacktestSummary",
    "PortfolioAccount",
    "PortfolioIdempotencyRecord",
    "PortfolioTrade",
    "PortfolioCashLedger",
    "PortfolioCorporateAction",
    "PortfolioPosition",
    "PortfolioPositionLot",
    "PortfolioDailySnapshot",
    "PortfolioFxRate",
    "ConversationMessage",
    "ConversationSummary",
    "AgentProviderTurn",
    "LLMUsage",
    "AlertRuleRecord",
    "AlertTriggerRecord",
    "AlertNotificationRecord",
    "AlertCooldownRecord",
    "DecisionSignalRecord",
    "DecisionSignalOutcomeRecord",
    "DecisionSignalFeedbackRecord",
    "DecisionSignalMemoryFlagRecord",
    "PortfolioAccountKind",
    "ScheduledTaskRecord",
    "ScheduledTaskRunRecord",
)
EXPECTED_SCHEMA_TABLES = (
    "schema_migrations",
    "stock_daily",
    "news_intel",
    "intelligence_sources",
    "intelligence_items",
    "fundamental_snapshot",
    "analysis_history",
    "backtest_results",
    "backtest_summaries",
    "portfolio_accounts",
    "portfolio_idempotency_records",
    "portfolio_trades",
    "portfolio_cash_ledger",
    "portfolio_corporate_actions",
    "portfolio_positions",
    "portfolio_position_lots",
    "portfolio_daily_snapshots",
    "portfolio_fx_rates",
    "conversation_messages",
    "conversation_summaries",
    "agent_provider_turns",
    "llm_usage",
    "alert_rules",
    "alert_triggers",
    "alert_notifications",
    "alert_cooldowns",
    "decision_signals",
    "decision_signal_outcomes",
    "decision_signal_feedback",
    "decision_signal_memory_flags",
    "portfolio_account_kinds",
    "scheduled_tasks",
    "scheduled_task_runs",
)
EXPECTED_SCHEMA_METHODS = {
    "StockDaily": ("__repr__", "to_dict"),
    "NewsIntel": ("__repr__",),
    "FundamentalSnapshot": ("__repr__",),
    "AnalysisHistory": ("to_dict",),
}
EXPECTED_UTC_COLUMN_CALLBACKS = (
    ("decision_signals", "created_at", "default"),
    ("decision_signals", "updated_at", "default"),
    ("decision_signals", "updated_at", "onupdate"),
    ("decision_signal_outcomes", "created_at", "default"),
    ("decision_signal_outcomes", "updated_at", "default"),
    ("decision_signal_outcomes", "updated_at", "onupdate"),
    ("decision_signal_feedback", "created_at", "default"),
    ("decision_signal_feedback", "updated_at", "default"),
    ("decision_signal_feedback", "updated_at", "onupdate"),
    ("decision_signal_memory_flags", "created_at", "default"),
    ("decision_signal_memory_flags", "updated_at", "default"),
    ("decision_signal_memory_flags", "updated_at", "onupdate"),
    ("portfolio_account_kinds", "created_at", "default"),
    ("portfolio_account_kinds", "updated_at", "default"),
    ("portfolio_account_kinds", "updated_at", "onupdate"),
    ("scheduled_tasks", "created_at", "default"),
    ("scheduled_tasks", "updated_at", "default"),
    ("scheduled_tasks", "updated_at", "onupdate"),
    ("scheduled_task_runs", "created_at", "default"),
    ("scheduled_task_runs", "updated_at", "default"),
    ("scheduled_task_runs", "updated_at", "onupdate"),
)

EXPECTED_GROUPS = (
    (
        "_LifecycleMethods",
        "_LIFECYCLE_METHOD_NAMES",
        (
            "__new__",
            "__init__",
            "_schema_initialization_scope",
            "_schema_connection",
            "_schema_bind",
            "_sqlite_user_tables",
            "_has_known_baseline_anchor",
            "_sqlite_ddl_tokens",
            "_sqlite_has_explicit_conflict_policy",
            "_verify_create_all_baseline",
            "_ensure_schema_migration_record",
            "get_instance",
            "reset_instance",
            "_cleanup_engine",
            "_install_sqlite_pragma_handler",
            "_enable_sqlite_wal_mode",
            "_is_file_sqlite_database",
            "_run_write_transaction",
            "_is_sqlite_locked_error",
            "_is_sqlite_duplicate_column_error",
            "_normalize_daily_date",
            "_normalize_sql_value",
            "get_session",
            "session_scope",
        ),
        "c881496ed61961e7b4b980ffafc9a8700d1692969e62ca0a3ea77fd7ae8798aa",
    ),
    (
        "_MarketDataMethods",
        "_MARKET_DATA_METHOD_NAMES",
        (
            "has_today_data",
            "get_latest_data",
            "save_news_intel",
            "save_fundamental_snapshot",
            "get_latest_fundamental_snapshot",
            "get_recent_news",
            "get_news_intel_by_query_id",
        ),
        "81921426d47d5ad678b856030eca419e11a67dd6ec3920b1164d1fd21d5d2c88",
    ),
    (
        "_HistoryMethods",
        "_HISTORY_METHOD_NAMES",
        (
            "save_analysis_history",
            "update_analysis_history_diagnostics",
            "get_analysis_history",
            "get_latest_analysis_history_id",
            "get_analysis_history_paginated",
            "get_analysis_history_by_id",
            "delete_analysis_history_records",
            "get_distinct_stocks_from_history",
            "get_latest_analysis_by_query_id",
            "get_data_range",
            "save_daily_data",
            "get_analysis_context",
            "_analyze_ma_status",
            "_parse_published_date",
            "_safe_json_dumps",
            "_build_raw_result",
            "_parse_sniper_value",
            "_extract_sniper_points",
            "_build_fallback_url_key",
        ),
        "f5aee9366c7cc397ff498a8ca194141ca0dd782f45758eeffcc14e92f6baf98d",
    ),
    (
        "_ConversationMethods",
        "_CONVERSATION_METHOD_NAMES",
        (
            "save_conversation_message",
            "get_conversation_history",
            "get_visible_conversation_messages",
            "get_conversation_summary",
            "save_agent_provider_turn",
            "get_agent_provider_turns",
            "_trim_agent_provider_turns",
            "upsert_conversation_summary",
            "conversation_session_exists",
            "get_chat_sessions",
            "get_conversation_messages",
            "delete_conversation_session",
        ),
        "507c839d148e0284b30d5b057c14c2167811e8cd9b736340236ea6378d3f541e",
    ),
    (
        "_UsageMethods",
        "_USAGE_METHOD_NAMES",
        (
            "record_llm_usage",
            "get_llm_usage_summary",
            "get_llm_usage_records",
        ),
        "09f5b539c64af212918a0222fa0086fabc891a5161f56492190f1906b4dce072",
    ),
)

EXPECTED_CONTEXTMANAGERS = frozenset(
    {"_schema_initialization_scope", "_schema_connection", "session_scope"}
)


def _canonical_ast(value):
    """Serialize ASTs without interpreter-version-only fields."""

    if isinstance(value, ast.AST):
        return [
            value.__class__.__name__,
            [
                [field, _canonical_ast(child)]
                for field, child in ast.iter_fields(value)
                if field != "type_params"
            ],
        ]
    if isinstance(value, list):
        return [_canonical_ast(item) for item in value]
    if value is Ellipsis:
        return {"constant": "Ellipsis"}
    return value


def _container_ast_hash(container) -> str:
    source_path = inspect.getsourcefile(container)
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == container.__name__
    )
    records = [
        (node.name, _canonical_ast(node))
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    payload = json.dumps(
        records,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _top_level_definition_name(node):
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if isinstance(node, ast.Assign):
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if len(names) == 1:
            return names[0]
    return None


def _schema_ast_hash(source_path: Path) -> str:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    records = [
        (_top_level_definition_name(node), _canonical_ast(node))
        for node in tree.body
        if _top_level_definition_name(node) in EXPECTED_SCHEMA_DEFINITIONS
    ]
    assert tuple(name for name, _ in records) == EXPECTED_SCHEMA_DEFINITIONS
    payload = json.dumps(
        records,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    return descriptor


def _loaded_globals(code: CodeType):
    import dis

    names = {
        instruction.argval
        for instruction in dis.get_instructions(code)
        if instruction.opname in {"LOAD_GLOBAL", "LOAD_NAME"}
    }
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            names.update(_loaded_globals(constant))
    return names


def _code_tree(code: CodeType):
    yield code
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            yield from _code_tree(constant)


def _all_method_names():
    return tuple(
        name
        for _, _, method_names, _ in EXPECTED_GROUPS
        for name in method_names
    )


def test_storage_public_exports_match_pre_split_snapshot():
    module = importlib.import_module("src.storage")

    assert {name for name in vars(module) if not name.startswith("_")} == (
        EXPECTED_PUBLIC_EXPORTS
    )


def test_storage_schema_asts_match_pre_split_snapshot():
    module = importlib.import_module("src.storage")
    schema_path = Path(module.__file__).with_name("storage_parts") / "schema.py"

    assert _schema_ast_hash(schema_path) == EXPECTED_SCHEMA_AST_HASH


def test_storage_schema_exec_preserves_facade_contract():
    module = importlib.import_module("src.storage")
    facade_globals = vars(module)

    assert tuple(module.Base.metadata.tables) == EXPECTED_SCHEMA_TABLES
    for helper_name in ("utc_naive_now", "to_utc_naive_datetime"):
        helper = getattr(module, helper_name)
        assert helper.__module__ == "src.storage"
        assert helper.__qualname__ == helper_name
        assert helper.__globals__ is facade_globals
        assert not helper.__code__.co_flags & __future__.annotations.compiler_flag

    for model_name in EXPECTED_SCHEMA_MODELS:
        model = getattr(module, model_name)
        assert model.__module__ == "src.storage"
        assert model.__qualname__ == model_name
        assert model.__table__.metadata is module.Base.metadata
        for method_name in EXPECTED_SCHEMA_METHODS.get(model_name, ()):
            method = vars(model)[method_name]
            assert method.__module__ == "src.storage"
            assert method.__qualname__ == f"{model_name}.{method_name}"
            assert method.__globals__ is facade_globals
            assert not method.__code__.co_flags & __future__.annotations.compiler_flag

    utc_callbacks = []
    for table in module.Base.metadata.tables.values():
        for column in table.columns:
            for callback_kind in ("default", "onupdate"):
                callback = getattr(column, callback_kind)
                if getattr(getattr(callback, "arg", None), "__wrapped__", None) is (
                    module.utc_naive_now
                ):
                    utc_callbacks.append((table.name, column.name, callback_kind))
    assert tuple(utc_callbacks) == EXPECTED_UTC_COLUMN_CALLBACKS


def test_storage_private_schema_import_is_isolated_from_facade_registry():
    module = importlib.import_module("src.storage")
    source = importlib.import_module("src.storage_parts.schema")

    assert source.Base is not module.Base
    assert tuple(source.Base.metadata.tables) == EXPECTED_SCHEMA_TABLES
    for model_name in EXPECTED_SCHEMA_MODELS:
        assert getattr(source, model_name) is not getattr(module, model_name)
        assert getattr(source, model_name).__module__ == "src.storage_parts.schema"
    assert tuple(module.Base.metadata.tables) == EXPECTED_SCHEMA_TABLES


def test_storage_manager_method_asts_match_pre_split_snapshot():
    module = importlib.import_module("src.storage")

    assert {
        container_name: _container_ast_hash(getattr(module, container_name))
        for container_name, _, _, _ in EXPECTED_GROUPS
    } == {
        container_name: expected_hash
        for container_name, _, _, expected_hash in EXPECTED_GROUPS
    }


def test_storage_manager_descriptors_preserve_facade_contract():
    module = importlib.import_module("src.storage")
    facade_globals = vars(module)

    for container_name, names_attribute, expected_names, _ in EXPECTED_GROUPS:
        container = getattr(module, container_name)
        assert getattr(module, names_attribute) == expected_names
        for name in expected_names:
            descriptor = module.DatabaseManager.__dict__[name]
            source_descriptor = container.__dict__[name]
            assert descriptor.__class__ is source_descriptor.__class__
            function = _descriptor_function(descriptor)
            source_function = _descriptor_function(source_descriptor)
            assert isinstance(function, FunctionType)
            assert function.__code__ is source_function.__code__
            assert function.__defaults__ == source_function.__defaults__
            assert function.__kwdefaults__ == source_function.__kwdefaults__
            assert function.__annotations__ == source_function.__annotations__
            assert inspect.signature(function) == inspect.signature(source_function)
            assert function.__doc__ == source_function.__doc__
            assert function.__module__ == "src.storage"
            assert function.__name__ == source_function.__name__
            assert function.__qualname__ == f"DatabaseManager.{name}"
            assert getattr(function, "__type_params__", ()) == getattr(
                source_function,
                "__type_params__",
                (),
            )

            if name in EXPECTED_CONTEXTMANAGERS:
                source_unwrapped = inspect.unwrap(source_function)
                unwrapped = inspect.unwrap(function)
                assert function.__globals__ is vars(contextlib)
                assert unwrapped.__globals__ is facade_globals
                assert unwrapped.__code__ is source_unwrapped.__code__
                assert function.__wrapped__ is unwrapped
                assert {
                    key: value
                    for key, value in function.__dict__.items()
                    if key != "__wrapped__"
                } == {
                    key: value
                    for key, value in source_function.__dict__.items()
                    if key != "__wrapped__"
                }
                loaded_function = unwrapped
            else:
                assert function.__globals__ is facade_globals
                assert function.__dict__ == source_function.__dict__
                if name == "__new__":
                    assert function.__code__.co_freevars == ("__class__",)
                    assert function.__closure__[0].cell_contents is module.DatabaseManager
                    assert (
                        source_function.__closure__[0].cell_contents
                        is container
                    )
                else:
                    assert function.__closure__ == source_function.__closure__
                loaded_function = function

            for global_name in _loaded_globals(loaded_function.__code__):
                assert global_name in facade_globals or hasattr(
                    builtins,
                    global_name,
                )
            for code in _code_tree(loaded_function.__code__):
                assert not code.co_flags & __future__.annotations.compiler_flag


def test_storage_manager_signatures_hints_and_order_match_pre_split_contract():
    module = importlib.import_module("src.storage")
    expected_names = _all_method_names()
    actual_names = tuple(
        name
        for name, descriptor in vars(module.DatabaseManager).items()
        if isinstance(descriptor, (FunctionType, staticmethod, classmethod))
    )
    assert actual_names == expected_names

    unresolved = set()
    for name in expected_names:
        function = _descriptor_function(module.DatabaseManager.__dict__[name])
        try:
            typing.get_type_hints(function)
        except NameError:
            unresolved.add(name)
    assert unresolved == {"save_news_intel", "save_analysis_history"}

    assert module.DatabaseManager.get_instance.__func__.__annotations__["return"] == (
        "DatabaseManager"
    )
    assert module.DatabaseManager.save_news_intel.__annotations__["response"] == (
        "SearchResponse"
    )
    assert module.DatabaseManager.save_analysis_history.__annotations__["result"] == (
        "AnalysisResult"
    )


def test_storage_manager_facade_patch_seams_are_preserved(monkeypatch):
    module = importlib.import_module("src.storage")

    monkeypatch.setattr(module, "parse_sniper_value", lambda _value: 17.5)
    assert module.DatabaseManager._parse_sniper_value("patched") == 17.5

    monkeypatch.setattr(module.json, "dumps", lambda *_args, **_kwargs: "patched")
    assert module.DatabaseManager._safe_json_dumps({"ignored": True}) == "patched"


def test_storage_nested_write_callback_preserves_eager_annotations():
    module = importlib.import_module("src.storage")
    manager = object.__new__(module.DatabaseManager)
    captured = {}

    def capture_write(_operation_name, write_operation):
        captured["callback"] = write_operation
        return 1

    manager._run_write_transaction = capture_write

    assert manager.save_fundamental_snapshot("query", "AAPL", {"ok": True}) == 1
    callback = captured["callback"]
    assert callback.__annotations__ == {
        "session": module.Session,
        "return": int,
    }
    assert str(inspect.signature(callback)) == (
        "(session: sqlalchemy.orm.session.Session) -> int"
    )
    assert not callback.__code__.co_flags & __future__.annotations.compiler_flag


def test_storage_manager_reload_recreates_facade_owned_state():
    code = """
import importlib
import inspect
import typing
import src.storage as module

old_class = module.DatabaseManager
old_meta = module._DatabaseManagerMeta
old_base = module.Base
old_stock_daily = module.StockDaily
old_utc_naive_now = module.utc_naive_now
old_telemetry_columns = module._LLM_USAGE_TELEMETRY_COLUMN_SQL
old_lock = old_class._init_lock
old_method = old_class.save_daily_data
old_class._instance = object()

first = importlib.reload(module)
first_class = first.DatabaseManager
first_method = first_class.save_daily_data

assert first_class is not old_class
assert first._DatabaseManagerMeta is not old_meta
assert first.Base is not old_base
assert first.StockDaily is not old_stock_daily
assert first.utc_naive_now is not old_utc_naive_now
assert first._LLM_USAGE_TELEMETRY_COLUMN_SQL is not old_telemetry_columns
assert first_class._instance is None
assert first_class._init_lock is not old_lock
assert first_method is not old_method
assert first_method.__globals__ is vars(first)
assert first_method.__annotations__["df"] is first.pd.DataFrame
assert first_class.get_latest_data.__annotations__["return"] == typing.List[
    first.StockDaily
]
assert first_class.__new__.__closure__[0].cell_contents is first_class
assert inspect.unwrap(first_class.session_scope).__globals__ is vars(first)
assert first.StockDaily.to_dict.__globals__ is vars(first)
assert first.StockDaily.__table__.metadata is first.Base.metadata
assert first.DecisionSignalRecord.created_at.default.arg.__wrapped__ is first.utc_naive_now

second = importlib.reload(first)
assert second.DatabaseManager is not first_class
assert second.DatabaseManager.save_daily_data is not first_method
assert second.DatabaseManager._instance is None
assert second.DatabaseManager.save_daily_data.__globals__ is vars(second)
assert second.DatabaseManager.__new__.__closure__[0].cell_contents is second.DatabaseManager
assert inspect.unwrap(second.DatabaseManager.session_scope).__globals__ is vars(second)
assert second.StockDaily.to_dict.__globals__ is vars(second)
assert second.StockDaily.__table__.metadata is second.Base.metadata
assert second.DecisionSignalRecord.created_at.default.arg.__wrapped__ is second.utc_naive_now
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
