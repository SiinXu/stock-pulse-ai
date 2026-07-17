-- StockPulse historical schema fixture; sanitized test data only.
-- Profile: stockpulse_v3_20_0
-- Source tag: v3.20.0
-- Source commit: d22ff1c42d37d1b1d7d955c6dfb00daf1f62e69d
-- Generation: git archive <commit>; set DATABASE_PATH to an isolated file;
--   run that revision's DatabaseManager.get_instance(); insert fixed canaries;
--   export with sqlite3.Connection.iterdump().
-- Schema digest: SHA-256 of canonical sqlite_master rows ordered by type/name.
-- Schema digest value: 476b2e179a2506344fc10c0289017e0ba00307505f8cd9bb5842724cbffd156f
-- Profile digest: SHA-256 of canonical tables/columns/affinity/PK/NOT NULL/
--   defaults/unique keys/collations/FKs/table options semantic JSON.
-- Profile digest value: ce59784e3a49e140d6586a5e49235df875829031dd0c8ca36243f73405f350c6
BEGIN TRANSACTION;
CREATE TABLE agent_provider_turns (
	id INTEGER NOT NULL, 
	session_id VARCHAR(100) NOT NULL, 
	run_id VARCHAR(64) NOT NULL, 
	provider VARCHAR(64) NOT NULL, 
	model VARCHAR(160) NOT NULL, 
	anchor_user_message_id INTEGER NOT NULL, 
	anchor_assistant_message_id INTEGER NOT NULL, 
	messages_json TEXT NOT NULL, 
	contains_reasoning BOOLEAN NOT NULL, 
	contains_tool_calls BOOLEAN NOT NULL, 
	contains_thinking_blocks BOOLEAN NOT NULL, 
	must_roundtrip BOOLEAN NOT NULL, 
	estimated_tokens INTEGER NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE alert_cooldowns (
	id INTEGER NOT NULL, 
	rule_id INTEGER, 
	rule_key VARCHAR(255), 
	target VARCHAR(64) NOT NULL, 
	severity VARCHAR(16) NOT NULL, 
	last_triggered_at DATETIME, 
	cooldown_until DATETIME, 
	reason TEXT, 
	state VARCHAR(16) NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_alert_cooldown_rule_target_severity UNIQUE (rule_id, target, severity)
);
CREATE TABLE alert_notifications (
	id INTEGER NOT NULL, 
	trigger_id INTEGER, 
	channel VARCHAR(32) NOT NULL, 
	attempt INTEGER NOT NULL, 
	success BOOLEAN NOT NULL, 
	error_code VARCHAR(64), 
	retryable BOOLEAN NOT NULL, 
	latency_ms INTEGER, 
	diagnostics TEXT, 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE alert_rules (
	id INTEGER NOT NULL, 
	name VARCHAR(64) NOT NULL, 
	target_scope VARCHAR(32) NOT NULL, 
	target VARCHAR(64) NOT NULL, 
	alert_type VARCHAR(32) NOT NULL, 
	parameters TEXT NOT NULL, 
	severity VARCHAR(16) NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	source VARCHAR(16) NOT NULL, 
	cooldown_policy TEXT, 
	notification_policy TEXT, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE alert_triggers (
	id INTEGER NOT NULL, 
	rule_id INTEGER, 
	target VARCHAR(64) NOT NULL, 
	observed_value FLOAT, 
	threshold FLOAT, 
	reason TEXT, 
	data_source VARCHAR(64), 
	data_timestamp DATETIME, 
	triggered_at DATETIME, 
	status VARCHAR(16) NOT NULL, 
	diagnostics TEXT, 
	PRIMARY KEY (id)
);
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
CREATE TABLE conversation_summaries (
	id INTEGER NOT NULL, 
	session_id VARCHAR(100) NOT NULL, 
	summary TEXT NOT NULL, 
	covered_message_id INTEGER NOT NULL, 
	source_message_count INTEGER NOT NULL, 
	estimated_tokens INTEGER NOT NULL, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE fundamental_snapshot (
	id INTEGER NOT NULL, 
	query_id VARCHAR(64) NOT NULL, 
	code VARCHAR(10) NOT NULL, 
	payload TEXT NOT NULL, 
	source_chain TEXT, 
	coverage TEXT, 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE llm_usage (
	id INTEGER NOT NULL, 
	call_type VARCHAR(32) NOT NULL, 
	model VARCHAR(128) NOT NULL, 
	stock_code VARCHAR(16), 
	prompt_tokens INTEGER NOT NULL, 
	completion_tokens INTEGER NOT NULL, 
	total_tokens INTEGER NOT NULL, 
	called_at DATETIME, 
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
CREATE TABLE portfolio_accounts (
	id INTEGER NOT NULL, 
	owner_id VARCHAR(64), 
	name VARCHAR(64) NOT NULL, 
	broker VARCHAR(64), 
	market VARCHAR(8) NOT NULL, 
	base_currency VARCHAR(8) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
);
INSERT INTO "portfolio_accounts" VALUES(1,'fixture-owner','Fixture Account','fixture','us','USD',1,'2020-01-02 07:00:00','2020-01-02 07:00:00');
CREATE TABLE portfolio_cash_ledger (
	id INTEGER NOT NULL, 
	account_id INTEGER NOT NULL, 
	event_date DATE NOT NULL, 
	direction VARCHAR(8) NOT NULL, 
	amount FLOAT NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	note VARCHAR(255), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES portfolio_accounts (id)
);
CREATE TABLE portfolio_corporate_actions (
	id INTEGER NOT NULL, 
	account_id INTEGER NOT NULL, 
	symbol VARCHAR(16) NOT NULL, 
	market VARCHAR(8) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	effective_date DATE NOT NULL, 
	action_type VARCHAR(24) NOT NULL, 
	cash_dividend_per_share FLOAT, 
	split_ratio FLOAT, 
	note VARCHAR(255), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES portfolio_accounts (id)
);
CREATE TABLE portfolio_daily_snapshots (
	id INTEGER NOT NULL, 
	account_id INTEGER NOT NULL, 
	snapshot_date DATE NOT NULL, 
	cost_method VARCHAR(8) NOT NULL, 
	base_currency VARCHAR(8) NOT NULL, 
	total_cash FLOAT NOT NULL, 
	total_market_value FLOAT NOT NULL, 
	total_equity FLOAT NOT NULL, 
	unrealized_pnl FLOAT NOT NULL, 
	realized_pnl FLOAT NOT NULL, 
	fee_total FLOAT NOT NULL, 
	tax_total FLOAT NOT NULL, 
	fx_stale BOOLEAN NOT NULL, 
	payload TEXT, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_portfolio_snapshot_account_date_method UNIQUE (account_id, snapshot_date, cost_method), 
	FOREIGN KEY(account_id) REFERENCES portfolio_accounts (id)
);
CREATE TABLE portfolio_fx_rates (
	id INTEGER NOT NULL, 
	from_currency VARCHAR(8) NOT NULL, 
	to_currency VARCHAR(8) NOT NULL, 
	rate_date DATE NOT NULL, 
	rate FLOAT NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	is_stale BOOLEAN NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_portfolio_fx_pair_date UNIQUE (from_currency, to_currency, rate_date)
);
CREATE TABLE portfolio_position_lots (
	id INTEGER NOT NULL, 
	account_id INTEGER NOT NULL, 
	cost_method VARCHAR(8) NOT NULL, 
	symbol VARCHAR(16) NOT NULL, 
	market VARCHAR(8) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	open_date DATE NOT NULL, 
	remaining_quantity FLOAT NOT NULL, 
	unit_cost FLOAT NOT NULL, 
	source_trade_id INTEGER, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES portfolio_accounts (id), 
	FOREIGN KEY(source_trade_id) REFERENCES portfolio_trades (id)
);
CREATE TABLE portfolio_positions (
	id INTEGER NOT NULL, 
	account_id INTEGER NOT NULL, 
	cost_method VARCHAR(8) NOT NULL, 
	symbol VARCHAR(16) NOT NULL, 
	market VARCHAR(8) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	quantity FLOAT NOT NULL, 
	avg_cost FLOAT NOT NULL, 
	total_cost FLOAT NOT NULL, 
	last_price FLOAT NOT NULL, 
	market_value_base FLOAT NOT NULL, 
	unrealized_pnl_base FLOAT NOT NULL, 
	valuation_currency VARCHAR(8) NOT NULL, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_portfolio_position_account_symbol_market_currency UNIQUE (account_id, symbol, market, currency, cost_method), 
	FOREIGN KEY(account_id) REFERENCES portfolio_accounts (id)
);
CREATE TABLE portfolio_trades (
	id INTEGER NOT NULL, 
	account_id INTEGER NOT NULL, 
	trade_uid VARCHAR(128), 
	symbol VARCHAR(16) NOT NULL, 
	market VARCHAR(8) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	trade_date DATE NOT NULL, 
	side VARCHAR(8) NOT NULL, 
	quantity FLOAT NOT NULL, 
	price FLOAT NOT NULL, 
	fee FLOAT, 
	tax FLOAT, 
	note VARCHAR(255), 
	dedup_hash VARCHAR(64), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_portfolio_trade_uid UNIQUE (account_id, trade_uid), 
	CONSTRAINT uix_portfolio_trade_dedup_hash UNIQUE (account_id, dedup_hash), 
	FOREIGN KEY(account_id) REFERENCES portfolio_accounts (id)
);
INSERT INTO "portfolio_trades" VALUES(1,1,'fixture-trade-001','TEST0001','us','USD','2020-01-02','buy',3.0,11.0,0.1,0.0,'Sanitized fixture trade.','fixture-dedup-001','2020-01-02 07:30:00');
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
CREATE INDEX ix_code_date ON stock_daily (code, date);
CREATE INDEX ix_stock_daily_code ON stock_daily (code);
CREATE INDEX ix_stock_daily_date ON stock_daily (date);
CREATE INDEX ix_news_intel_provider ON news_intel (provider);
CREATE INDEX ix_news_intel_fetched_at ON news_intel (fetched_at);
CREATE INDEX ix_news_intel_query_id ON news_intel (query_id);
CREATE INDEX ix_news_intel_query_source ON news_intel (query_source);
CREATE INDEX ix_news_code_pub ON news_intel (code, published_date);
CREATE INDEX ix_news_intel_published_date ON news_intel (published_date);
CREATE INDEX ix_news_intel_dimension ON news_intel (dimension);
CREATE INDEX ix_news_intel_code ON news_intel (code);
CREATE INDEX ix_fundamental_snapshot_query_code ON fundamental_snapshot (query_id, code);
CREATE INDEX ix_fundamental_snapshot_created_at ON fundamental_snapshot (created_at);
CREATE INDEX ix_fundamental_snapshot_code ON fundamental_snapshot (code);
CREATE INDEX ix_fundamental_snapshot_created ON fundamental_snapshot (created_at);
CREATE INDEX ix_fundamental_snapshot_query_id ON fundamental_snapshot (query_id);
CREATE INDEX ix_analysis_history_created_at ON analysis_history (created_at);
CREATE INDEX ix_analysis_history_code ON analysis_history (code);
CREATE INDEX ix_analysis_code_time ON analysis_history (code, created_at);
CREATE INDEX ix_analysis_history_query_id ON analysis_history (query_id);
CREATE INDEX ix_analysis_history_report_type ON analysis_history (report_type);
CREATE INDEX ix_backtest_summaries_code ON backtest_summaries (code);
CREATE INDEX ix_backtest_summaries_computed_at ON backtest_summaries (computed_at);
CREATE INDEX ix_backtest_summaries_scope ON backtest_summaries (scope);
CREATE INDEX ix_portfolio_accounts_owner_id ON portfolio_accounts (owner_id);
CREATE INDEX ix_portfolio_accounts_is_active ON portfolio_accounts (is_active);
CREATE INDEX ix_portfolio_accounts_created_at ON portfolio_accounts (created_at);
CREATE INDEX ix_portfolio_account_owner_active ON portfolio_accounts (owner_id, is_active);
CREATE INDEX ix_portfolio_accounts_market ON portfolio_accounts (market);
CREATE INDEX ix_portfolio_fx_rates_rate_date ON portfolio_fx_rates (rate_date);
CREATE INDEX ix_portfolio_fx_rates_from_currency ON portfolio_fx_rates (from_currency);
CREATE INDEX ix_portfolio_fx_rates_to_currency ON portfolio_fx_rates (to_currency);
CREATE INDEX ix_conversation_messages_created_at ON conversation_messages (created_at);
CREATE INDEX ix_conversation_messages_session_id ON conversation_messages (session_id);
CREATE UNIQUE INDEX ix_conversation_summaries_session_id ON conversation_summaries (session_id);
CREATE INDEX ix_conversation_summaries_created_at ON conversation_summaries (created_at);
CREATE INDEX ix_conversation_summaries_updated_at ON conversation_summaries (updated_at);
CREATE INDEX ix_agent_provider_turns_created_at ON agent_provider_turns (created_at);
CREATE INDEX ix_agent_provider_turns_model ON agent_provider_turns (model);
CREATE INDEX ix_agent_provider_turns_anchor_user_message_id ON agent_provider_turns (anchor_user_message_id);
CREATE INDEX ix_agent_provider_turns_run_id ON agent_provider_turns (run_id);
CREATE INDEX ix_agent_provider_turns_must_roundtrip ON agent_provider_turns (must_roundtrip);
CREATE INDEX ix_agent_provider_turns_session_id ON agent_provider_turns (session_id);
CREATE INDEX ix_agent_provider_turns_provider ON agent_provider_turns (provider);
CREATE INDEX ix_agent_provider_turns_anchor_assistant_message_id ON agent_provider_turns (anchor_assistant_message_id);
CREATE INDEX ix_agent_provider_turn_bucket ON agent_provider_turns (session_id, provider, model, must_roundtrip);
CREATE INDEX ix_llm_usage_call_type ON llm_usage (call_type);
CREATE INDEX ix_llm_usage_called_at ON llm_usage (called_at);
CREATE INDEX ix_alert_rules_created_at ON alert_rules (created_at);
CREATE INDEX ix_alert_rules_severity ON alert_rules (severity);
CREATE INDEX ix_alert_rules_target ON alert_rules (target);
CREATE INDEX ix_alert_rules_updated_at ON alert_rules (updated_at);
CREATE INDEX ix_alert_rule_type_target ON alert_rules (alert_type, target);
CREATE INDEX ix_alert_rules_enabled ON alert_rules (enabled);
CREATE INDEX ix_alert_rules_source ON alert_rules (source);
CREATE INDEX ix_alert_rules_alert_type ON alert_rules (alert_type);
CREATE INDEX ix_alert_rules_target_scope ON alert_rules (target_scope);
CREATE INDEX ix_alert_triggers_triggered_at ON alert_triggers (triggered_at);
CREATE INDEX ix_alert_trigger_rule_time ON alert_triggers (rule_id, triggered_at);
CREATE INDEX ix_alert_triggers_status ON alert_triggers (status);
CREATE INDEX ix_alert_triggers_rule_id ON alert_triggers (rule_id);
CREATE INDEX ix_alert_triggers_data_timestamp ON alert_triggers (data_timestamp);
CREATE INDEX ix_alert_triggers_target ON alert_triggers (target);
CREATE INDEX ix_alert_notifications_channel ON alert_notifications (channel);
CREATE INDEX ix_alert_notifications_created_at ON alert_notifications (created_at);
CREATE INDEX ix_alert_notifications_trigger_id ON alert_notifications (trigger_id);
CREATE INDEX ix_alert_notification_trigger_channel ON alert_notifications (trigger_id, channel);
CREATE INDEX ix_alert_notifications_success ON alert_notifications (success);
CREATE INDEX ix_alert_cooldowns_rule_id ON alert_cooldowns (rule_id);
CREATE INDEX ix_alert_cooldowns_target ON alert_cooldowns (target);
CREATE INDEX ix_alert_cooldowns_cooldown_until ON alert_cooldowns (cooldown_until);
CREATE INDEX ix_alert_cooldowns_severity ON alert_cooldowns (severity);
CREATE INDEX ix_alert_cooldowns_state ON alert_cooldowns (state);
CREATE INDEX ix_alert_cooldowns_rule_key ON alert_cooldowns (rule_key);
CREATE INDEX ix_alert_cooldowns_last_triggered_at ON alert_cooldowns (last_triggered_at);
CREATE INDEX ix_alert_cooldowns_updated_at ON alert_cooldowns (updated_at);
CREATE INDEX ix_backtest_results_code ON backtest_results (code);
CREATE INDEX ix_backtest_results_analysis_history_id ON backtest_results (analysis_history_id);
CREATE INDEX ix_backtest_results_analysis_date ON backtest_results (analysis_date);
CREATE INDEX ix_backtest_results_evaluated_at ON backtest_results (evaluated_at);
CREATE INDEX ix_backtest_code_date ON backtest_results (code, analysis_date);
CREATE INDEX ix_portfolio_trades_dedup_hash ON portfolio_trades (dedup_hash);
CREATE INDEX ix_portfolio_trades_trade_date ON portfolio_trades (trade_date);
CREATE INDEX ix_portfolio_trades_created_at ON portfolio_trades (created_at);
CREATE INDEX ix_portfolio_trades_symbol ON portfolio_trades (symbol);
CREATE INDEX ix_portfolio_trade_account_date ON portfolio_trades (account_id, trade_date);
CREATE INDEX ix_portfolio_trades_account_id ON portfolio_trades (account_id);
CREATE INDEX ix_portfolio_cash_account_date ON portfolio_cash_ledger (account_id, event_date);
CREATE INDEX ix_portfolio_cash_ledger_account_id ON portfolio_cash_ledger (account_id);
CREATE INDEX ix_portfolio_cash_ledger_event_date ON portfolio_cash_ledger (event_date);
CREATE INDEX ix_portfolio_cash_ledger_created_at ON portfolio_cash_ledger (created_at);
CREATE INDEX ix_portfolio_ca_account_date ON portfolio_corporate_actions (account_id, effective_date);
CREATE INDEX ix_portfolio_corporate_actions_effective_date ON portfolio_corporate_actions (effective_date);
CREATE INDEX ix_portfolio_corporate_actions_symbol ON portfolio_corporate_actions (symbol);
CREATE INDEX ix_portfolio_corporate_actions_account_id ON portfolio_corporate_actions (account_id);
CREATE INDEX ix_portfolio_corporate_actions_created_at ON portfolio_corporate_actions (created_at);
CREATE INDEX ix_portfolio_positions_updated_at ON portfolio_positions (updated_at);
CREATE INDEX ix_portfolio_positions_account_id ON portfolio_positions (account_id);
CREATE INDEX ix_portfolio_positions_symbol ON portfolio_positions (symbol);
CREATE INDEX ix_portfolio_daily_snapshots_created_at ON portfolio_daily_snapshots (created_at);
CREATE INDEX ix_portfolio_daily_snapshots_snapshot_date ON portfolio_daily_snapshots (snapshot_date);
CREATE INDEX ix_portfolio_daily_snapshots_account_id ON portfolio_daily_snapshots (account_id);
CREATE INDEX ix_portfolio_position_lots_updated_at ON portfolio_position_lots (updated_at);
CREATE INDEX ix_portfolio_position_lots_open_date ON portfolio_position_lots (open_date);
CREATE INDEX ix_portfolio_position_lots_account_id ON portfolio_position_lots (account_id);
CREATE INDEX ix_portfolio_position_lots_symbol ON portfolio_position_lots (symbol);
CREATE INDEX ix_portfolio_lot_account_symbol ON portfolio_position_lots (account_id, symbol);
COMMIT;
