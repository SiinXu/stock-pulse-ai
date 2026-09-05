# -*- coding: utf-8 -*-
"""Internal implementation parts for the BaseFetcher abstract base.

Capability-domain modules under this package are private to ``data_provider``.
Subclasses and external callers must continue to inherit from and import
``src.data_provider.base`` so public surfaces and test patch targets stay
stable (ADR-006 / Issue #1067).

Unlike ``manager_parts`` (which serves ``DataFetcherManager``), this package
serves the ``BaseFetcher`` abstract base that every provider fetcher inherits.

Owned domains:
- ``daily_pipeline`` — the daily-data template method and its clean/indicator steps
- ``market_stubs`` — default market-overview and rankings stubs (``return None``)
"""
