BEGIN;

-- Transitional registry shape: checksum metadata exists but has not been stamped.
CREATE TABLE schema_migrations (
    version VARCHAR(64) NOT NULL PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    applied_at DATETIME NOT NULL,
    checksum VARCHAR(64)
);

INSERT INTO schema_migrations (version, description, applied_at, checksum)
VALUES (
    '2026-06-05-create-all-baseline',
    'Baseline schema created through SQLAlchemy metadata.create_all',
    '2026-06-05 00:00:00',
    NULL
);

-- The business tables use the current pre-runner shape so the fixture exercises
-- real Portfolio and Analysis facts without inventing incomplete application tables.
CREATE TABLE portfolio_accounts (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    owner_id VARCHAR(64),
    name VARCHAR(64) NOT NULL,
    broker VARCHAR(64),
    market VARCHAR(8) NOT NULL,
    base_currency VARCHAR(8) NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_at DATETIME,
    updated_at DATETIME
);

INSERT INTO portfolio_accounts (
    id, owner_id, name, broker, market, base_currency, is_active, created_at, updated_at
)
VALUES (
    1, 'fixture-owner', 'Sanitized Account', 'fixture-broker', 'test', 'USD', 1,
    '2026-06-02 08:00:00', '2026-06-02 08:00:00'
);

CREATE TABLE portfolio_trades (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    trade_uid VARCHAR(128),
    symbol VARCHAR(16) NOT NULL,
    market VARCHAR(8) NOT NULL,
    currency VARCHAR(8) NOT NULL,
    trade_date DATE NOT NULL,
    side VARCHAR(8) NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL,
    tax REAL,
    note VARCHAR(255),
    dedup_hash VARCHAR(64),
    created_at DATETIME,
    FOREIGN KEY(account_id) REFERENCES portfolio_accounts(id),
    CONSTRAINT uix_portfolio_trade_uid UNIQUE (account_id, trade_uid),
    CONSTRAINT uix_portfolio_trade_dedup_hash UNIQUE (account_id, dedup_hash)
);

INSERT INTO portfolio_trades (
    id, account_id, trade_uid, symbol, market, currency, trade_date, side,
    quantity, price, fee, tax, note, dedup_hash, created_at
)
VALUES (
    1, 1, 'fixture-trade-002', 'DEMO002', 'test', 'USD', '2026-06-02', 'buy',
    8.0, 21.25, 0.2, 0.0, 'Sanitized fixture trade.', 'fixture-dedup-002',
    '2026-06-02 08:15:00'
);

CREATE TABLE analysis_history (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    query_id VARCHAR(64),
    code VARCHAR(10) NOT NULL,
    name VARCHAR(50),
    report_type VARCHAR(16) NOT NULL,
    sentiment_score INTEGER,
    operation_advice VARCHAR(20),
    trend_prediction VARCHAR(50),
    analysis_summary TEXT,
    raw_result TEXT,
    news_content TEXT,
    context_snapshot TEXT,
    ideal_buy REAL,
    secondary_buy REAL,
    stop_loss REAL,
    take_profit REAL,
    created_at DATETIME
);

INSERT INTO analysis_history (
    id, query_id, code, name, report_type, sentiment_score, operation_advice,
    trend_prediction, analysis_summary, raw_result, news_content, context_snapshot,
    ideal_buy, secondary_buy, stop_loss, take_profit, created_at
)
VALUES (
    1,
    'fixture-query-002',
    'DEMO002',
    'Sanitized Equity',
    'stock',
    54,
    'hold',
    'neutral',
    'Sanitized transitional analysis fixture.',
    '{}',
    '[]',
    '{}',
    21.0,
    20.0,
    18.0,
    25.0,
    '2026-06-02 09:15:00'
);

COMMIT;
