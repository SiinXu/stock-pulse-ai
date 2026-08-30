# -*- coding: utf-8 -*-
"""Internal implementation parts for the efinance data-provider fetcher.

Capability-domain modules under this package are private to ``data_provider``.
External callers must continue to import from
``src.data_provider.efinance_fetcher`` (or ``src.data_provider``) so public
surfaces and test patch targets stay stable (ADR-006 / Issue #1068).

Owned domains:
- ``etf`` — ETF history fetch and ETF realtime-quote orchestration methods
- ``realtime`` — stock-path realtime quote method
"""
