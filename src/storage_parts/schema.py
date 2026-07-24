# ORM schema source for the public src.storage facade.

if __name__ != "src.storage":
    from datetime import datetime, timezone
    from typing import Any, Dict

    from sqlalchemy import (
        Boolean,
        Column,
        Date,
        DateTime,
        Float,
        ForeignKey,
        Index,
        Integer,
        String,
        Text,
        UniqueConstraint,
    )
    from sqlalchemy.orm import declarative_base

    INTELLIGENCE_ITEM_NULL_SCOPE_VALUE = "__dsa_null_scope__"
    Base = declarative_base()

def utc_naive_now() -> datetime:
    """Return current UTC time without tzinfo for SQLite DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive_datetime(value: datetime) -> datetime:
    """Normalize aware datetimes to UTC-naive; treat naive values as UTC-naive."""
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


# === Data model definitions ===

class DatabaseSchemaMigration(Base):
    """Applied database schema version marker."""

    __tablename__ = 'schema_migrations'

    version = Column(String(64), primary_key=True)
    description = Column(String(255), nullable=False)
    applied_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    checksum = Column(String(64), nullable=True)


class StockDaily(Base):
    """
    股票日线数据模型
\x20\x20\x20\x20
    存储每日行情数据和计算的技术指标
    支持多股票、多日期的唯一约束
    """
    __tablename__ = 'stock_daily'

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Stock code (for example, 600519 or 000001)
    code = Column(String(10), nullable=False, index=True)

    # Trading date
    date = Column(Date, nullable=False, index=True)

    # OHLC data
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)

    # Trading data
    volume = Column(Float)  # Volume (shares)
    amount = Column(Float)  # Trading amount (CNY)
    pct_chg = Column(Float)  # Percentage change (%)

    # Technical indicators
    ma5 = Column(Float)
    ma10 = Column(Float)
    ma20 = Column(Float)
    volume_ratio = Column(Float)  # Relative volume

    # Data source
    data_source = Column(String(50))  # Records the source (for example, AkshareFetcher)

    # Updated at
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Unique constraint: one row per stock and trading date
    __table_args__ = (
        UniqueConstraint('code', 'date', name='uix_code_date'),
        Index('ix_code_date', 'code', 'date'),
    )

    def __repr__(self):
        return f"<StockDaily(code={self.code}, date={self.date}, close={self.close})>"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'code': self.code,
            'date': self.date,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'amount': self.amount,
            'pct_chg': self.pct_chg,
            'ma5': self.ma5,
            'ma10': self.ma10,
            'ma20': self.ma20,
            'volume_ratio': self.volume_ratio,
            'data_source': self.data_source,
        }


class NewsIntel(Base):
    """
    新闻情报数据模型

    存储搜索到的新闻情报条目，用于后续分析与查询
    """
    __tablename__ = 'news_intel'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Associated user query
    query_id = Column(String(64), index=True)

    # Stock metadata
    code = Column(String(10), nullable=False, index=True)
    name = Column(String(50))

    # Search context
    dimension = Column(String(32), index=True)  # latest_news / risk_check / earnings / market_analysis / industry
    query = Column(String(255))
    provider = Column(String(32), index=True)

    # News content
    title = Column(String(300), nullable=False)
    snippet = Column(Text)
    url = Column(String(1000), nullable=False)
    source = Column(String(100))
    published_date = Column(DateTime, index=True)

    # Ingested at
    fetched_at = Column(DateTime, default=datetime.now, index=True)
    query_source = Column(String(32), index=True)  # bot/web/cli/system
    requester_platform = Column(String(20))
    requester_user_id = Column(String(64))
    requester_user_name = Column(String(64))
    requester_chat_id = Column(String(64))
    requester_message_id = Column(String(64))
    requester_query = Column(String(255))

    __table_args__ = (
        UniqueConstraint('url', name='uix_news_url'),
        Index('ix_news_code_pub', 'code', 'published_date'),
    )

    def __repr__(self) -> str:
        return f"<NewsIntel(code={self.code}, title={self.title[:20]}...)>"


class IntelligenceSource(Base):
    """可配置资讯源。"""

    __tablename__ = 'intelligence_sources'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    source_type = Column(String(32), nullable=False, default='rss', index=True)
    url = Column(String(1000), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    scope_type = Column(String(32), nullable=False, default='market', index=True)
    scope_value = Column(String(64), index=True)
    market = Column(String(32), nullable=False, default='cn', index=True)
    description = Column(Text)
    last_status = Column(String(32))
    last_error = Column(Text)
    last_fetched_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index('ix_intel_source_scope', 'scope_type', 'scope_value', 'market'),
    )


class IntelligenceItem(Base):
    """沉淀后的资讯 / 情报条目。"""

    __tablename__ = 'intelligence_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey('intelligence_sources.id', ondelete='SET NULL'), nullable=True, index=True)
    source_name = Column(String(100), index=True)
    source_type = Column(String(32), nullable=False, default='rss', index=True)
    title = Column(String(300), nullable=False)
    summary = Column(Text)
    url = Column(String(1000), nullable=False, index=True)
    source = Column(String(100))
    published_at = Column(DateTime, index=True)
    fetched_at = Column(DateTime, default=datetime.now, index=True)
    scope_type = Column(String(32), nullable=False, default='market', index=True)
    scope_value = Column(String(64), nullable=False, default=INTELLIGENCE_ITEM_NULL_SCOPE_VALUE, index=True)
    market = Column(String(32), nullable=False, default='cn', index=True)
    raw_payload = Column(Text)

    __table_args__ = (
        UniqueConstraint(
            'source_id',
            'url',
            'scope_type',
            'scope_value',
            'market',
            name='uix_intel_item_source_scope_url',
        ),
        Index('ix_intel_item_scope_time', 'scope_type', 'scope_value', 'market', 'published_at'),
        Index('ix_intel_item_fetch_time', 'fetched_at'),
    )


class FundamentalSnapshot(Base):
    """
    基本面上下文快照（P0 write-only）。

    仅用于写入，主链路不依赖读取该表，便于后续回测/画像扩展。
    """
    __tablename__ = 'fundamental_snapshot'

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_id = Column(String(64), nullable=False, index=True)
    code = Column(String(10), nullable=False, index=True)
    payload = Column(Text, nullable=False)
    source_chain = Column(Text)
    coverage = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_fundamental_snapshot_query_code', 'query_id', 'code'),
        Index('ix_fundamental_snapshot_created', 'created_at'),
    )

    def __repr__(self) -> str:
        return f"<FundamentalSnapshot(query_id={self.query_id}, code={self.code})>"


class AnalysisHistory(Base):
    """
    分析结果历史记录模型

    保存每次分析结果，支持按 query_id/股票代码检索
    """
    __tablename__ = 'analysis_history'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Associated query chain
    query_id = Column(String(64), index=True)

    # Stock metadata
    code = Column(String(10), nullable=False, index=True)
    name = Column(String(50))
    report_type = Column(String(16), index=True)

    # Core conclusion
    sentiment_score = Column(Integer)
    operation_advice = Column(String(20))
    trend_prediction = Column(String(50))
    analysis_summary = Column(Text)

    # Detailed data
    raw_result = Column(Text)
    news_content = Column(Text)
    context_snapshot = Column(Text)

    # Sniper levels (for backtesting)
    ideal_buy = Column(Float)
    secondary_buy = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)

    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_analysis_code_time', 'code', 'created_at'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'query_id': self.query_id,
            'code': self.code,
            'name': self.name,
            'report_type': self.report_type,
            'sentiment_score': self.sentiment_score,
            'operation_advice': self.operation_advice,
            'trend_prediction': self.trend_prediction,
            'analysis_summary': self.analysis_summary,
            'raw_result': self.raw_result,
            'news_content': self.news_content,
            'context_snapshot': self.context_snapshot,
            'ideal_buy': self.ideal_buy,
            'secondary_buy': self.secondary_buy,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BacktestResult(Base):
    """单条分析记录的回测结果。"""

    __tablename__ = 'backtest_results'

    id = Column(Integer, primary_key=True, autoincrement=True)

    analysis_history_id = Column(
        Integer,
        ForeignKey('analysis_history.id'),
        nullable=False,
        index=True,
    )

    # Redundant field for filtering by stock
    code = Column(String(10), nullable=False, index=True)
    analysis_date = Column(Date, index=True)

    # Backtest parameters
    eval_window_days = Column(Integer, nullable=False, default=10)
    engine_version = Column(String(16), nullable=False, default='v1')

    # Status
    eval_status = Column(String(16), nullable=False, default='pending')
    evaluated_at = Column(DateTime, default=datetime.now, index=True)

    # Recommendation snapshot keeps backtests interpretable if analysis fields change later
    operation_advice = Column(String(20))
    position_recommendation = Column(String(8))  # long/cash

    # Prices and returns
    start_price = Column(Float)
    end_close = Column(Float)
    max_high = Column(Float)
    min_low = Column(Float)
    stock_return_pct = Column(Float)

    # Direction and outcome
    direction_expected = Column(String(16))  # up/down/flat/not_down
    direction_correct = Column(Boolean, nullable=True)
    outcome = Column(String(16))  # win/loss/neutral

    # Target-price hit (meaningful only for long positions with take-profit/stop-loss configured)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    hit_stop_loss = Column(Boolean)
    hit_take_profit = Column(Boolean)
    first_hit = Column(String(16))  # take_profit/stop_loss/ambiguous/neither/not_applicable
    first_hit_date = Column(Date)
    first_hit_trading_days = Column(Integer)

    # Simulated execution (long-only)
    simulated_entry_price = Column(Float)
    simulated_exit_price = Column(Float)
    simulated_exit_reason = Column(String(24))  # stop_loss/take_profit/window_end/cash/ambiguous_stop_loss
    simulated_return_pct = Column(Float)

    __table_args__ = (
        UniqueConstraint(
            'analysis_history_id',
            'eval_window_days',
            'engine_version',
            name='uix_backtest_analysis_window_version',
        ),
        Index('ix_backtest_code_date', 'code', 'analysis_date'),
    )


class BacktestSummary(Base):
    """回测汇总指标（按股票或全局）。"""

    __tablename__ = 'backtest_summaries'

    id = Column(Integer, primary_key=True, autoincrement=True)

    scope = Column(String(16), nullable=False, index=True)  # overall/stock
    code = Column(String(16), index=True)

    eval_window_days = Column(Integer, nullable=False, default=10)
    engine_version = Column(String(16), nullable=False, default='v1')
    computed_at = Column(DateTime, default=datetime.now, index=True)

    # Counts
    total_evaluations = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    insufficient_count = Column(Integer, default=0)
    long_count = Column(Integer, default=0)
    cash_count = Column(Integer, default=0)

    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    neutral_count = Column(Integer, default=0)

    # Accuracy/win rate
    direction_accuracy_pct = Column(Float)
    win_rate_pct = Column(Float)
    neutral_rate_pct = Column(Float)

    # Returns
    avg_stock_return_pct = Column(Float)
    avg_simulated_return_pct = Column(Float)

    # Target-price trigger statistics (long positions with take-profit/stop-loss only)
    stop_loss_trigger_rate = Column(Float)
    take_profit_trigger_rate = Column(Float)
    ambiguous_rate = Column(Float)
    avg_days_to_first_hit = Column(Float)

    # Diagnostic fields (JSON strings)
    advice_breakdown_json = Column(Text)
    diagnostics_json = Column(Text)

    __table_args__ = (
        UniqueConstraint(
            'scope',
            'code',
            'eval_window_days',
            'engine_version',
            name='uix_backtest_summary_scope_code_window_version',
        ),
    )


class PortfolioAccount(Base):
    """Portfolio account metadata."""

    __tablename__ = 'portfolio_accounts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(String(64), index=True)
    name = Column(String(64), nullable=False)
    broker = Column(String(64))
    market = Column(String(8), nullable=False, default='cn', index=True)  # cn/hk/us
    base_currency = Column(String(8), nullable=False, default='CNY')
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('ix_portfolio_account_owner_active', 'owner_id', 'is_active'),
    )


class PortfolioIdempotencyRecord(Base):
    """Persisted result for one scoped client-generated portfolio mutation."""

    __tablename__ = 'portfolio_idempotency_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Kept as the physical unique key for compatibility with the original table.
    operation_id = Column(String(128), nullable=False, unique=True, index=True)
    client_operation_id = Column(String(128), index=True)
    operation_type = Column(String(32), nullable=False, index=True)
    scope_key = Column(String(64), index=True)
    scope_account_id = Column(Integer, index=True)
    scope_owner_id = Column(String(64), index=True)
    request_hash = Column(String(64), nullable=False)
    response_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)

    __table_args__ = (
        Index(
            'uix_portfolio_idempotency_scope_operation',
            'operation_type',
            'scope_key',
            'client_operation_id',
            unique=True,
        ),
    )


class PortfolioTrade(Base):
    """Executed trade events used as the source of truth for replay."""

    __tablename__ = 'portfolio_trades'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    trade_uid = Column(String(128))
    symbol = Column(String(16), nullable=False, index=True)
    market = Column(String(8), nullable=False, default='cn')
    currency = Column(String(8), nullable=False, default='CNY')
    trade_date = Column(Date, nullable=False, index=True)
    side = Column(String(8), nullable=False)  # buy/sell
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fee = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    note = Column(String(255))
    dedup_hash = Column(String(64), index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint('account_id', 'trade_uid', name='uix_portfolio_trade_uid'),
        UniqueConstraint('account_id', 'dedup_hash', name='uix_portfolio_trade_dedup_hash'),
        Index('ix_portfolio_trade_account_date', 'account_id', 'trade_date'),
    )


class PortfolioCashLedger(Base):
    """Cash in/out events."""

    __tablename__ = 'portfolio_cash_ledger'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    event_date = Column(Date, nullable=False, index=True)
    direction = Column(String(8), nullable=False)  # in/out
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default='CNY')
    note = Column(String(255))
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_portfolio_cash_account_date', 'account_id', 'event_date'),
    )


class PortfolioCorporateAction(Base):
    """Corporate actions that impact cash or share quantity."""

    __tablename__ = 'portfolio_corporate_actions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)
    market = Column(String(8), nullable=False, default='cn')
    currency = Column(String(8), nullable=False, default='CNY')
    effective_date = Column(Date, nullable=False, index=True)
    action_type = Column(String(24), nullable=False)  # cash_dividend/split_adjustment
    cash_dividend_per_share = Column(Float)
    split_ratio = Column(Float)
    note = Column(String(255))
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_portfolio_ca_account_date', 'account_id', 'effective_date'),
    )


class PortfolioPosition(Base):
    """Latest replayed position snapshot for each symbol in one account."""

    __tablename__ = 'portfolio_positions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    cost_method = Column(String(8), nullable=False, default='fifo')
    symbol = Column(String(16), nullable=False, index=True)
    market = Column(String(8), nullable=False, default='cn')
    currency = Column(String(8), nullable=False, default='CNY')
    quantity = Column(Float, nullable=False, default=0.0)
    avg_cost = Column(Float, nullable=False, default=0.0)
    total_cost = Column(Float, nullable=False, default=0.0)
    last_price = Column(Float, nullable=False, default=0.0)
    market_value_base = Column(Float, nullable=False, default=0.0)
    unrealized_pnl_base = Column(Float, nullable=False, default=0.0)
    valuation_currency = Column(String(8), nullable=False, default='CNY')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint(
            'account_id',
            'symbol',
            'market',
            'currency',
            'cost_method',
            name='uix_portfolio_position_account_symbol_market_currency',
        ),
    )


class PortfolioPositionLot(Base):
    """Lot-level remaining quantities used by FIFO replay."""

    __tablename__ = 'portfolio_position_lots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    cost_method = Column(String(8), nullable=False, default='fifo')
    symbol = Column(String(16), nullable=False, index=True)
    market = Column(String(8), nullable=False, default='cn')
    currency = Column(String(8), nullable=False, default='CNY')
    open_date = Column(Date, nullable=False, index=True)
    remaining_quantity = Column(Float, nullable=False, default=0.0)
    unit_cost = Column(Float, nullable=False, default=0.0)
    source_trade_id = Column(Integer, ForeignKey('portfolio_trades.id'))
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index('ix_portfolio_lot_account_symbol', 'account_id', 'symbol'),
    )


class PortfolioDailySnapshot(Base):
    """Daily account snapshot generated by read-time replay."""

    __tablename__ = 'portfolio_daily_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('portfolio_accounts.id'), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    cost_method = Column(String(8), nullable=False, default='fifo')  # fifo/avg
    base_currency = Column(String(8), nullable=False, default='CNY')
    total_cash = Column(Float, nullable=False, default=0.0)
    total_market_value = Column(Float, nullable=False, default=0.0)
    total_equity = Column(Float, nullable=False, default=0.0)
    unrealized_pnl = Column(Float, nullable=False, default=0.0)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    fee_total = Column(Float, nullable=False, default=0.0)
    tax_total = Column(Float, nullable=False, default=0.0)
    fx_stale = Column(Boolean, nullable=False, default=False)
    payload = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint(
            'account_id',
            'snapshot_date',
            'cost_method',
            name='uix_portfolio_snapshot_account_date_method',
        ),
    )


class PortfolioFxRate(Base):
    """Cached FX rates used for cross-currency portfolio conversion."""

    __tablename__ = 'portfolio_fx_rates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_currency = Column(String(8), nullable=False, index=True)
    to_currency = Column(String(8), nullable=False, index=True)
    rate_date = Column(Date, nullable=False, index=True)
    rate = Column(Float, nullable=False)
    source = Column(String(32), nullable=False, default='manual')
    is_stale = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint(
            'from_currency',
            'to_currency',
            'rate_date',
            name='uix_portfolio_fx_pair_date',
        ),
    )


class ConversationMessage(Base):
    """
    Agent 对话历史记录表
    """
    __tablename__ = 'conversation_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), index=True, nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now, index=True)


class ConversationSummary(Base):
    """Rolling summary for visible Agent chat history."""

    __tablename__ = 'conversation_summaries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, unique=True, index=True)
    summary = Column(Text, nullable=False)
    covered_message_id = Column(Integer, nullable=False, default=0)
    source_message_count = Column(Integer, nullable=False, default=0)
    estimated_tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)


class AgentProviderTurn(Base):
    """Provider protocol trace required for thinking/tool-call roundtrip."""

    __tablename__ = 'agent_provider_turns'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, index=True)
    run_id = Column(String(64), nullable=False, index=True)
    provider = Column(String(64), nullable=False, index=True)
    model = Column(String(160), nullable=False, index=True)
    anchor_user_message_id = Column(Integer, nullable=False, index=True)
    anchor_assistant_message_id = Column(Integer, nullable=False, index=True)
    messages_json = Column(Text, nullable=False)
    contains_reasoning = Column(Boolean, nullable=False, default=False)
    contains_tool_calls = Column(Boolean, nullable=False, default=False)
    contains_thinking_blocks = Column(Boolean, nullable=False, default=False)
    must_roundtrip = Column(Boolean, nullable=False, default=False, index=True)
    estimated_tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_agent_provider_turn_bucket', 'session_id', 'provider', 'model', 'must_roundtrip'),
    )


class LLMUsage(Base):
    """One row per litellm.completion() call — token-usage audit log."""

    __tablename__ = 'llm_usage'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 'analysis' | 'agent' | 'market_review'
    call_type = Column(String(32), nullable=False, index=True)
    model = Column(String(128), nullable=False)
    stock_code = Column(String(16), nullable=True)
    provider = Column(String(64), nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)

    # Sanitized provider usage snapshot; raw prompts, messages, headers, and
    # tokenizer free-text fields are intentionally not persisted here.
    provider_usage_json = Column(Text, nullable=True)
    provider_usage_schema_name = Column(String(64), nullable=True)
    provider_usage_schema_version = Column(String(32), nullable=True)
    provider_usage_observed_at = Column(String(32), nullable=True)

    # Normalized telemetry values are derived from provider usage and may stay
    # NULL when the provider payload is absent or explicitly invalid.
    normalized_prompt_tokens = Column(Integer, nullable=True)
    normalized_completion_tokens = Column(Integer, nullable=True)
    normalized_total_tokens = Column(Integer, nullable=True)
    normalized_cache_read_tokens = Column(Integer, nullable=True)
    normalized_cache_write_tokens = Column(Integer, nullable=True)
    normalized_cache_miss_tokens = Column(Integer, nullable=True)
    normalized_uncached_input_tokens = Column(Integer, nullable=True)
    normalized_cache_eligible_input_tokens = Column(Integer, nullable=True)
    normalized_cache_hit_ratio = Column(Float, nullable=True)
    normalized_cache_write_ratio = Column(Float, nullable=True)
    cache_capability = Column(String(32), nullable=True)
    cache_eligibility = Column(String(32), nullable=True)
    cache_observation = Column(String(32), nullable=True)
    estimated_prefix_tokens = Column(Integer, nullable=True)
    provider_reported_prompt_tokens = Column(Integer, nullable=True)
    provider_reported_cached_tokens = Column(Integer, nullable=True)
    provider_min_cache_tokens = Column(Integer, nullable=True)
    eligibility_confidence = Column(String(32), nullable=True)

    # Kept nullable for schema compatibility; new writes do not store provider
    # or proxy tokenizer free-text values.
    tokenizer_name = Column(String(128), nullable=True)
    tokenizer_version = Column(String(64), nullable=True)

    # HMAC fingerprints let deployments compare message shapes without storing
    # raw prompt/message content.
    messages_hmac = Column(String(64), nullable=True)
    system_message_hmac = Column(String(64), nullable=True)
    user_message_hmac = Column(String(64), nullable=True)
    hmac_key_version = Column(String(64), nullable=True)
    hmac_domain = Column(String(32), nullable=True)
    hash_scope = Column(String(32), nullable=True)

    # P0.5a internal legacy message stability audit. These diagnostics are
    # stored locally only and are not returned by public usage APIs.
    language = Column(String(16), nullable=True)
    market_group = Column(String(16), nullable=True)
    analysis_mode = Column(String(64), nullable=True)
    legacy_prompt_mode = Column(String(32), nullable=True)
    skill_config_hmac = Column(String(64), nullable=True)
    transport = Column(String(64), nullable=True)
    message_count = Column(Integer, nullable=True)
    estimated_total_prompt_tokens = Column(Integer, nullable=True)
    approx_common_prefix_chars = Column(Integer, nullable=True)
    approx_common_prefix_tokens = Column(Integer, nullable=True)
    known_dynamic_marker_positions = Column(Text, nullable=True)
    called_at = Column(DateTime, default=datetime.now, index=True)


_LLM_USAGE_TELEMETRY_COLUMN_SQL: Dict[str, str] = {
    "provider_usage_json": "TEXT",
    "provider": "VARCHAR(64)",
    "provider_usage_schema_name": "VARCHAR(64)",
    "provider_usage_schema_version": "VARCHAR(32)",
    "provider_usage_observed_at": "VARCHAR(32)",
    "normalized_prompt_tokens": "INTEGER",
    "normalized_completion_tokens": "INTEGER",
    "normalized_total_tokens": "INTEGER",
    "normalized_cache_read_tokens": "INTEGER",
    "normalized_cache_write_tokens": "INTEGER",
    "normalized_cache_miss_tokens": "INTEGER",
    "normalized_uncached_input_tokens": "INTEGER",
    "normalized_cache_eligible_input_tokens": "INTEGER",
    "normalized_cache_hit_ratio": "FLOAT",
    "normalized_cache_write_ratio": "FLOAT",
    "cache_capability": "VARCHAR(32)",
    "cache_eligibility": "VARCHAR(32)",
    "cache_observation": "VARCHAR(32)",
    "estimated_prefix_tokens": "INTEGER",
    "provider_reported_prompt_tokens": "INTEGER",
    "provider_reported_cached_tokens": "INTEGER",
    "provider_min_cache_tokens": "INTEGER",
    "eligibility_confidence": "VARCHAR(32)",
    "tokenizer_name": "VARCHAR(128)",
    "tokenizer_version": "VARCHAR(64)",
    "messages_hmac": "VARCHAR(64)",
    "system_message_hmac": "VARCHAR(64)",
    "user_message_hmac": "VARCHAR(64)",
    "hmac_key_version": "VARCHAR(64)",
    "hmac_domain": "VARCHAR(32)",
    "hash_scope": "VARCHAR(32)",
    "language": "VARCHAR(16)",
    "market_group": "VARCHAR(16)",
    "analysis_mode": "VARCHAR(64)",
    "legacy_prompt_mode": "VARCHAR(32)",
    "skill_config_hmac": "VARCHAR(64)",
    "transport": "VARCHAR(64)",
    "message_count": "INTEGER",
    "estimated_total_prompt_tokens": "INTEGER",
    "approx_common_prefix_chars": "INTEGER",
    "approx_common_prefix_tokens": "INTEGER",
    "known_dynamic_marker_positions": "TEXT",
}
_LLM_USAGE_INTEGER_TELEMETRY_COLUMNS = {
    column
    for column, column_type in _LLM_USAGE_TELEMETRY_COLUMN_SQL.items()
    if column_type == "INTEGER"
}
_LLM_USAGE_DROPPED_FREE_TEXT_COLUMNS = {"tokenizer_name", "tokenizer_version"}
_LLM_PROMPT_CACHE_TELEMETRY_DISABLED_ATTR = "prompt_cache_telemetry_disabled"
_LLM_PROMPT_CACHE_TELEMETRY_COLUMNS = {
    "provider_usage_json",
    "provider_usage_schema_name",
    "provider_usage_schema_version",
    "provider_usage_observed_at",
    "normalized_cache_read_tokens",
    "normalized_cache_write_tokens",
    "normalized_cache_miss_tokens",
    "normalized_uncached_input_tokens",
    "normalized_cache_eligible_input_tokens",
    "normalized_cache_hit_ratio",
    "normalized_cache_write_ratio",
    "cache_capability",
    "cache_eligibility",
    "cache_observation",
    "estimated_prefix_tokens",
    "provider_reported_cached_tokens",
    "provider_min_cache_tokens",
    "eligibility_confidence",
}


class AlertRuleRecord(Base):
    """Persisted alert rule managed through the Alert API."""

    __tablename__ = 'alert_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    target_scope = Column(String(32), nullable=False, default='single_symbol', index=True)
    target = Column(String(64), nullable=False, index=True)
    alert_type = Column(String(32), nullable=False, index=True)
    parameters = Column(Text, nullable=False, default='{}')
    severity = Column(String(16), nullable=False, default='warning', index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    source = Column(String(16), nullable=False, default='api', index=True)
    cooldown_policy = Column(Text)
    notification_policy = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        Index('ix_alert_rule_type_target', 'alert_type', 'target'),
    )


class AlertTriggerRecord(Base):
    """Alert trigger history row.

    P1 exposes read APIs and table shape; runtime writer integration lands in
    later phases.
    """

    __tablename__ = 'alert_triggers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, index=True)
    target = Column(String(64), nullable=False, index=True)
    observed_value = Column(Float)
    threshold = Column(Float)
    reason = Column(Text)
    data_source = Column(String(64))
    data_timestamp = Column(DateTime, index=True)
    triggered_at = Column(DateTime, default=datetime.now, index=True)
    status = Column(String(16), nullable=False, default='triggered', index=True)
    diagnostics = Column(Text)

    __table_args__ = (
        Index('ix_alert_trigger_rule_time', 'rule_id', 'triggered_at'),
    )


class AlertNotificationRecord(Base):
    """Notification attempt row for alert triggers.

    P1 exposes read APIs and table shape; runtime writer integration lands in
    later phases.
    """

    __tablename__ = 'alert_notifications'

    id = Column(Integer, primary_key=True, autoincrement=True)
    trigger_id = Column(Integer, index=True)
    channel = Column(String(32), nullable=False, index=True)
    attempt = Column(Integer, nullable=False, default=1)
    success = Column(Boolean, nullable=False, default=False, index=True)
    error_code = Column(String(64))
    retryable = Column(Boolean, nullable=False, default=False)
    latency_ms = Column(Integer)
    diagnostics = Column(Text)
    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index('ix_alert_notification_trigger_channel', 'trigger_id', 'channel'),
    )


class AlertCooldownRecord(Base):
    """Persisted alert cooldown state for DB-managed alert rules."""

    __tablename__ = 'alert_cooldowns'

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, index=True)
    # Reserved for future non-DB/expanded-scope rules; P4 queries by rule_id.
    rule_key = Column(String(255), index=True)
    target = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default='warning', index=True)
    last_triggered_at = Column(DateTime, index=True)
    cooldown_until = Column(DateTime, index=True)
    reason = Column(Text)
    state = Column(String(16), nullable=False, default='active', index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    __table_args__ = (
        UniqueConstraint('rule_id', 'target', 'severity', name='uix_alert_cooldown_rule_target_severity'),
    )


class DecisionSignalRecord(Base):
    """Persisted AI decision signal asset for Issue #1390 P1."""

    __tablename__ = 'decision_signals'

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(16), nullable=False, index=True)
    stock_name = Column(String(64))
    market = Column(String(8), nullable=False, index=True)
    source_type = Column(String(32), nullable=False, index=True)
    source_agent = Column(String(64))
    source_report_id = Column(Integer, index=True)
    trace_id = Column(String(64), index=True)
    decision_profile = Column(String(16), index=True)
    market_phase = Column(String(24), index=True)
    trigger_source = Column(String(64), nullable=False, index=True)
    action = Column(String(16), nullable=False, index=True)
    action_label = Column(String(32))
    confidence = Column(Float)
    score = Column(Integer)
    horizon = Column(String(16), index=True)
    entry_low = Column(Float)
    entry_high = Column(Float)
    stop_loss = Column(Float)
    target_price = Column(Float)
    invalidation = Column(Text)
    watch_conditions = Column(Text)
    reason = Column(Text)
    risk_summary = Column(Text)
    catalyst_summary = Column(Text)
    evidence_json = Column(Text)
    data_quality_summary_json = Column(Text)
    plan_quality = Column(String(16), nullable=False, default='unknown', index=True)
    status = Column(String(16), nullable=False, default='active', index=True)
    expires_at = Column(DateTime, index=True)
    created_at = Column(DateTime, default=utc_naive_now, index=True)
    updated_at = Column(DateTime, default=utc_naive_now, onupdate=utc_naive_now, index=True)
    metadata_json = Column(Text)

    __table_args__ = (
        Index('ix_decision_signal_stock_status_time', 'stock_code', 'status', 'created_at'),
        Index('ix_decision_signal_market_status_time', 'market', 'status', 'created_at'),
        Index(
            'ix_decision_signal_report_type_market_stock_action_horizon_phase',
            'source_report_id',
            'source_type',
            'market',
            'stock_code',
            'action',
            'horizon',
            'market_phase',
        ),
        Index(
            'ix_decision_signal_trace_type_market_stock_action_horizon_phase',
            'trace_id',
            'source_type',
            'market',
            'stock_code',
            'action',
            'horizon',
            'market_phase',
        ),
        Index(
            'ix_decision_signal_report_type_market_stock_profile_action_horizon_phase',
            'source_report_id',
            'source_type',
            'market',
            'stock_code',
            'decision_profile',
            'action',
            'horizon',
            'market_phase',
        ),
        Index(
            'ix_decision_signal_trace_type_market_stock_profile_action_horizon_phase',
            'trace_id',
            'source_type',
            'market',
            'stock_code',
            'decision_profile',
            'action',
            'horizon',
            'market_phase',
        ),
        Index(
            'ix_decision_signal_market_stock_profile_created',
            'market',
            'stock_code',
            'decision_profile',
            'created_at',
        ),
    )


class DecisionSignalOutcomeRecord(Base):
    """Signal-level forward outcome for Issue #1390 P5."""

    __tablename__ = 'decision_signal_outcomes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(Integer, nullable=False, index=True)
    horizon = Column(String(16), nullable=False, index=True)
    engine_version = Column(String(32), nullable=False, index=True)
    eval_status = Column(String(24), nullable=False, default='unable', index=True)
    outcome = Column(String(16), index=True)
    direction_expected = Column(String(16), index=True)
    direction_correct = Column(Boolean)
    unable_reason = Column(String(64), index=True)
    anchor_date = Column(Date, index=True)
    eval_window_days = Column(Integer)
    start_price = Column(Float)
    end_close = Column(Float)
    max_high = Column(Float)
    min_low = Column(Float)
    stock_return_pct = Column(Float)

    action = Column(String(16), index=True)
    market = Column(String(8), index=True)
    market_phase = Column(String(24), index=True)
    source_type = Column(String(32), index=True)
    source_agent = Column(String(64), index=True)
    plan_quality = Column(String(16), index=True)
    data_quality_level = Column(String(24), index=True)
    holding_state = Column(String(16), nullable=False, default='unknown', index=True)

    created_at = Column(DateTime, default=utc_naive_now, index=True)
    updated_at = Column(DateTime, default=utc_naive_now, onupdate=utc_naive_now, index=True)

    __table_args__ = (
        UniqueConstraint('signal_id', 'horizon', 'engine_version', name='uix_decision_signal_outcome_key'),
        Index('ix_decision_signal_outcome_stats_action', 'engine_version', 'action', 'horizon'),
        Index('ix_decision_signal_outcome_stats_market', 'engine_version', 'market', 'horizon'),
    )


class DecisionSignalFeedbackRecord(Base):
    """Latest user feedback for a decision signal."""

    __tablename__ = 'decision_signal_feedback'

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(Integer, nullable=False, unique=True, index=True)
    feedback_value = Column(String(16), nullable=False, index=True)
    reason_code = Column(String(64), index=True)
    note = Column(Text)
    source = Column(String(16), nullable=False, default='api', index=True)
    created_at = Column(DateTime, default=utc_naive_now, index=True)
    updated_at = Column(DateTime, default=utc_naive_now, onupdate=utc_naive_now, index=True)


class DecisionSignalMemoryFlagRecord(Base):
    """User curation of a signal for decision memory (Issue #118).

    ``memorable`` highlights a call in the reflection; ``ignored`` excludes it
    from the reflection entirely. Additive sidecar, one row per signal.
    """

    __tablename__ = 'decision_signal_memory_flags'

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(Integer, nullable=False, unique=True, index=True)
    memorable = Column(Boolean, nullable=False, default=False, index=True)
    ignored = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, default=utc_naive_now, index=True)
    updated_at = Column(DateTime, default=utc_naive_now, onupdate=utc_naive_now, index=True)


class PortfolioAccountKind(Base):
    """Paper vs real classification for a portfolio account (Issue #370).

    Additive sidecar keyed by account_id so paper trading can be introduced
    without altering the frozen ``portfolio_accounts`` schema. A missing row
    means the account is ``real`` (the pre-existing default); a ``paper`` row
    marks a forward-simulation account.
    """

    __tablename__ = 'portfolio_account_kinds'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(
        Integer,
        ForeignKey('portfolio_accounts.id'),
        nullable=False,
        unique=True,
        index=True,
    )
    account_type = Column(String(16), nullable=False, default='paper', index=True)
    created_at = Column(DateTime, default=utc_naive_now, index=True)
    updated_at = Column(DateTime, default=utc_naive_now, onupdate=utc_naive_now, index=True)


class InvestmentFrameworkRecord(Base):
    """Single-local-account investment framework aggregate."""

    __tablename__ = 'investment_frameworks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope_key = Column(String(32), nullable=False)
    latest_version = Column(Integer, nullable=False)
    active_version = Column(Integer)
    revision = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utc_naive_now, nullable=False)
    updated_at = Column(
        DateTime,
        default=utc_naive_now,
        onupdate=utc_naive_now,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint('scope_key', name='uix_investment_framework_scope'),
    )


class InvestmentFrameworkVersionRecord(Base):
    """Immutable content version belonging to an investment framework."""

    __tablename__ = 'investment_framework_versions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    framework_id = Column(
        Integer,
        ForeignKey('investment_frameworks.id', ondelete='CASCADE'),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    content_json = Column(Text, nullable=False)
    change_summary = Column(String(500))
    created_at = Column(DateTime, default=utc_naive_now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            'framework_id',
            'version',
            name='uix_investment_framework_version',
        ),
    )
