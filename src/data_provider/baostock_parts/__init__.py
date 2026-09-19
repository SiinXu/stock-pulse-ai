# -*- coding: utf-8 -*-
"""Internal implementation parts for the Baostock data-provider fetcher.

Capability-domain modules under this package are private to ``data_provider``.
External callers must continue to import from
``src.data_provider.baostock_fetcher`` (or ``src.data_provider``) so public
surfaces and test patch targets stay stable (ADR-006 / Issue #1068).

Owned domains:
- ``history`` — daily candlestick fetch (``_fetch_raw_data``) and normalize
"""
