-- StockPulse historical schema fixture; sanitized test data only.
-- Profile: stockpulse_v3_0_0
-- Source tag: v3.0.0
-- Source commit: 52917baa02210fb7911491fcf48ecbf3f70e5812
-- Generation: git archive <commit>; set DATABASE_PATH to an isolated file;
--   run that revision's DatabaseManager.get_instance(); insert fixed canaries;
--   export with sqlite3.Connection.iterdump().
-- Schema digest: SHA-256 of canonical sqlite_master rows ordered by type/name.
-- Schema digest value: ec853a3e7ad482efbcfdd0a31a5f0affce1031725950bbae8006d7d300ade1c0
-- Profile digest: SHA-256 of canonical tables/columns/affinity/PK/NOT NULL/
--   defaults/unique keys/collations/FKs/table options semantic JSON.
-- Profile digest value: dc374be346f7c821deb25f72844ebaaad3eca9eea6c6186f8a9893240680ccf0
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
CREATE INDEX ix_code_date ON stock_daily (code, date);
CREATE INDEX ix_stock_daily_code ON stock_daily (code);
CREATE INDEX ix_stock_daily_date ON stock_daily (date);
CREATE INDEX ix_news_intel_dimension ON news_intel (dimension);
CREATE INDEX ix_news_intel_published_date ON news_intel (published_date);
CREATE INDEX ix_news_code_pub ON news_intel (code, published_date);
CREATE INDEX ix_news_intel_provider ON news_intel (provider);
CREATE INDEX ix_news_intel_code ON news_intel (code);
CREATE INDEX ix_news_intel_query_id ON news_intel (query_id);
CREATE INDEX ix_news_intel_query_source ON news_intel (query_source);
CREATE INDEX ix_news_intel_fetched_at ON news_intel (fetched_at);
CREATE INDEX ix_analysis_history_report_type ON analysis_history (report_type);
CREATE INDEX ix_analysis_history_query_id ON analysis_history (query_id);
CREATE INDEX ix_analysis_history_created_at ON analysis_history (created_at);
CREATE INDEX ix_analysis_history_code ON analysis_history (code);
CREATE INDEX ix_analysis_code_time ON analysis_history (code, created_at);
COMMIT;
