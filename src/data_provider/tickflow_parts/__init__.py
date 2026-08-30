# -*- coding: utf-8 -*-
"""Internal implementation parts for the TickFlow data-provider fetcher.

Capability-domain modules under this package are private to ``data_provider``.
External callers must continue to import from
``src.data_provider.tickflow_fetcher`` (or ``src.data_provider``) so public
surfaces and test patch targets stay stable (ADR-006 / Issue #1068).

Owned domains:
- ``market_boards`` — main indices, market statistics, and sector rankings
- ``facade_bind`` — re-export of ``src.data_provider._facade_bind``
"""
