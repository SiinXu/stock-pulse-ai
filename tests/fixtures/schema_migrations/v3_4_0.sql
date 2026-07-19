-- StockPulse historical schema fixture; sanitized test data only.
-- Profile: stockpulse_v3_4_0
-- Source tag: v3.4.0
-- Source commit: 0154992e18f6a5a09199a151ee75661e78b9c12f
-- Generation: git archive <commit>; set DATABASE_PATH to an isolated file;
--   run that revision's DatabaseManager.get_instance(); insert fixed canaries;
--   export with sqlite3.Connection.iterdump().
-- Schema digest: SHA-256 of canonical sqlite_master rows ordered by type/name.
-- Schema digest value: 1dec14940883b5571ae43e88f93c31974a9d403defc9ccc835ca2e53a3055a4f
-- Profile digest: SHA-256 of canonical tables/columns/affinity/PK/NOT NULL/
--   defaults/unique keys/collations/FKs/table options semantic JSON.
-- Profile digest value: 86a9c06247e0ef4f3cf20eebe091a261ce05fa4e5eba8dc729c0c42cc312d93a
BEGIN TRANSACTION;
CREATE TABLE analysis_history (
	id INTEGER NOT NULL, 
	query_id VARCHAR(64), 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(50), 
	report_type VARCHAR(16), 
	sentiment_score INTEGER, 
	operation_advice VARCHAR(20), 
	trend_prediction VARCHAR(50), 
	analysis_summary TEXT, 
	raw_result TEXT, 
	news_content TEXT, 
	context_snapshot TEXT, 
	ideal_buy FLOAT, 
	secondary_buy FLOAT, 
	stop_loss FLOAT, 
	take_profit FLOAT, 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
INSERT INTO "analysis_history" VALUES(1,'fixture-query-001','TEST0001','Fixture Equity','stock',55,'hold','neutral','Sanitized fixture analysis.','{}','[]','{}',10.0,9.5,8.0,14.0,'2020-01-02 09:00:00');
CREATE TABLE backtest_results (
	id INTEGER NOT NULL, 
	analysis_history_id INTEGER NOT NULL, 
	code VARCHAR(10) NOT NULL, 
	analysis_date DATE, 
	eval_window_days INTEGER NOT NULL, 
	engine_version VARCHAR(16) NOT NULL, 
	eval_status VARCHAR(16) NOT NULL, 
	evaluated_at DATETIME, 
	operation_advice VARCHAR(20), 
	position_recommendation VARCHAR(8), 
	start_price FLOAT, 
	end_close FLOAT, 
	max_high FLOAT, 
	min_low FLOAT, 
	stock_return_pct FLOAT, 
	direction_expected VARCHAR(16), 
	direction_correct BOOLEAN, 
	outcome VARCHAR(16), 
	stop_loss FLOAT, 
	take_profit FLOAT, 
	hit_stop_loss BOOLEAN, 
	hit_take_profit BOOLEAN, 
	first_hit VARCHAR(16), 
	first_hit_date DATE, 
	first_hit_trading_days INTEGER, 
	simulated_entry_price FLOAT, 
	simulated_exit_price FLOAT, 
	simulated_exit_reason VARCHAR(24), 
	simulated_return_pct FLOAT, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_backtest_analysis_window_version UNIQUE (analysis_history_id, eval_window_days, engine_version), 
	FOREIGN KEY(analysis_history_id) REFERENCES analysis_history (id)
);
CREATE TABLE backtest_summaries (
	id INTEGER NOT NULL, 
	scope VARCHAR(16) NOT NULL, 
	code VARCHAR(16), 
	eval_window_days INTEGER NOT NULL, 
	engine_version VARCHAR(16) NOT NULL, 
	computed_at DATETIME, 
	total_evaluations INTEGER, 
	completed_count INTEGER, 
	insufficient_count INTEGER, 
	long_count INTEGER, 
	cash_count INTEGER, 
	win_count INTEGER, 
	loss_count INTEGER, 
	neutral_count INTEGER, 
	direction_accuracy_pct FLOAT, 
	win_rate_pct FLOAT, 
	neutral_rate_pct FLOAT, 
	avg_stock_return_pct FLOAT, 
	avg_simulated_return_pct FLOAT, 
	stop_loss_trigger_rate FLOAT, 
	take_profit_trigger_rate FLOAT, 
	ambiguous_rate FLOAT, 
	avg_days_to_first_hit FLOAT, 
	advice_breakdown_json TEXT, 
	diagnostics_json TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_backtest_summary_scope_code_window_version UNIQUE (scope, code, eval_window_days, engine_version)
);
CREATE TABLE conversation_messages (
	id INTEGER NOT NULL, 
	session_id VARCHAR(100) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	content TEXT NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE news_intel (
	id INTEGER NOT NULL, 
	query_id VARCHAR(64), 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(50), 
	dimension VARCHAR(32), 
	"query" VARCHAR(255), 
	provider VARCHAR(32), 
	title VARCHAR(300) NOT NULL, 
	snippet TEXT, 
	url VARCHAR(1000) NOT NULL, 
	source VARCHAR(100), 
	published_date DATETIME, 
	fetched_at DATETIME, 
	query_source VARCHAR(32), 
	requester_platform VARCHAR(20), 
	requester_user_id VARCHAR(64), 
	requester_user_name VARCHAR(64), 
	requester_chat_id VARCHAR(64), 
	requester_message_id VARCHAR(64), 
	requester_query VARCHAR(255), 
	PRIMARY KEY (id), 
	CONSTRAINT uix_news_url UNIQUE (url)
);
CREATE TABLE stock_daily (
	id INTEGER NOT NULL, 
	code VARCHAR(10) NOT NULL, 
	date DATE NOT NULL, 
	open FLOAT, 
	high FLOAT, 
	low FLOAT, 
	close FLOAT, 
	volume FLOAT, 
	amount FLOAT, 
	pct_chg FLOAT, 
	ma5 FLOAT, 
	ma10 FLOAT, 
	ma20 FLOAT, 
	volume_ratio FLOAT, 
	data_source VARCHAR(50), 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_code_date UNIQUE (code, date)
);
INSERT INTO "stock_daily" VALUES(1,'TEST0001','2020-01-02',10.0,12.0,9.0,11.0,1000.0,11000.0,10.0,NULL,NULL,NULL,NULL,'fixture','2020-01-02 08:00:00','2020-01-02 08:00:00');
CREATE INDEX ix_stock_daily_date ON stock_daily (date);
CREATE INDEX ix_stock_daily_code ON stock_daily (code);
CREATE INDEX ix_code_date ON stock_daily (code, date);
CREATE INDEX ix_news_intel_published_date ON news_intel (published_date);
CREATE INDEX ix_news_intel_query_id ON news_intel (query_id);
CREATE INDEX ix_news_intel_fetched_at ON news_intel (fetched_at);
CREATE INDEX ix_news_intel_provider ON news_intel (provider);
CREATE INDEX ix_news_intel_code ON news_intel (code);
CREATE INDEX ix_news_intel_query_source ON news_intel (query_source);
CREATE INDEX ix_news_code_pub ON news_intel (code, published_date);
CREATE INDEX ix_news_intel_dimension ON news_intel (dimension);
CREATE INDEX ix_analysis_code_time ON analysis_history (code, created_at);
CREATE INDEX ix_analysis_history_code ON analysis_history (code);
CREATE INDEX ix_analysis_history_report_type ON analysis_history (report_type);
CREATE INDEX ix_analysis_history_query_id ON analysis_history (query_id);
CREATE INDEX ix_analysis_history_created_at ON analysis_history (created_at);
CREATE INDEX ix_backtest_summaries_code ON backtest_summaries (code);
CREATE INDEX ix_backtest_summaries_scope ON backtest_summaries (scope);
CREATE INDEX ix_backtest_summaries_computed_at ON backtest_summaries (computed_at);
CREATE INDEX ix_conversation_messages_created_at ON conversation_messages (created_at);
CREATE INDEX ix_conversation_messages_session_id ON conversation_messages (session_id);
CREATE INDEX ix_backtest_results_code ON backtest_results (code);
CREATE INDEX ix_backtest_results_analysis_date ON backtest_results (analysis_date);
CREATE INDEX ix_backtest_code_date ON backtest_results (code, analysis_date);
CREATE INDEX ix_backtest_results_analysis_history_id ON backtest_results (analysis_history_id);
CREATE INDEX ix_backtest_results_evaluated_at ON backtest_results (evaluated_at);
COMMIT;
