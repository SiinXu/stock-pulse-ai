# -*- coding: utf-8 -*-
"""Internal implementation parts for the TickFlow data-provider fetcher.

Capability-domain modules under this package are private to ``data_provider``.
External callers must continue to import from
``src.data_provider.tickflow_fetcher`` (or ``src.data_provider``) so public
surfaces and test patch targets stay stable (ADR-006 / Issue #1068).

Owned domains:
- ``market_boards`` — main indices, market statistics, and sector rankings
- ``history`` — daily fetch (``_fetch_raw_data``) and normalize (``_normalize_data``)
- ``realtime`` — realtime quote mapping (``get_realtime_quote``, ``_quote_to_unified_quote``, ``_format_provider_timestamp``)
- ``stock_identity`` — name lookup and universe list (``get_stock_name``, ``_extract_instrument_name``, ``get_stock_list``)
- ``facade_bind`` — re-export of ``src.data_provider._facade_bind``
"""
