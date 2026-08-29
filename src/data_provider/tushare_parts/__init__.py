# -*- coding: utf-8 -*-
"""Internal implementation parts for the Tushare data-provider fetcher.

Capability-domain modules under this package are private to ``data_provider``.
External callers must continue to import from ``data_provider.tushare_fetcher``
(or ``data_provider``) so public surfaces and test patch targets stay stable
(ADR-006 / Issue #1068).

Owned domains:
- ``client`` — HTTP client, URL resolve, and rate-limit wrappers
- ``symbols`` — ETF/US classifiers and ts_code conversion
- ``history`` — daily/history fetch and normalize methods
- ``facade_bind`` — ADR-006 clone/bind helpers
"""
