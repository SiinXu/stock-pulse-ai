# -*- coding: utf-8 -*-
"""Internal implementation parts for the yfinance data-provider fetcher.

Capability-domain modules under this package are private to ``data_provider``.
External callers must continue to import from
``src.data_provider.yfinance_fetcher`` (or ``src.data_provider``) so public
surfaces and test patch targets stay stable (ADR-006 / Issue #1068).

Owned domains:
- ``main_indices`` — regional main-index quotes and the shared ticker fetch
"""
