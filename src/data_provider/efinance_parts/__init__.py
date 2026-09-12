# -*- coding: utf-8 -*-
"""Internal implementation parts for the efinance data-provider fetcher.

Capability-domain modules under this package are private to ``data_provider``.
External callers must continue to import from
``src.data_provider.efinance_fetcher`` (or ``src.data_provider``) so public
surfaces and test patch targets stay stable (ADR-006 / Issue #1068).

Owned domains:
- ``etf`` — ETF history fetch and ETF realtime-quote orchestration methods
- ``realtime`` — stock-path realtime quote method
- ``market_boards`` — main indices, market statistics, and sector rankings
- ``history`` — stock-path daily fetch/normalize methods
- ``info`` — per-symbol base info, belong-board, and enhanced-data orchestration
- ``rate_limit`` — UA rotation, request pacing, and history-failure formatting
- ``timeout_client`` — bounded-wait SDK wrapper (``_ef_call_with_timeout``)
- ``eastmoney_errors`` — Eastmoney request-failure classifier (``_classify_eastmoney_error``)
- ``facade_bind`` — ADR-006 clone/bind helpers
"""
