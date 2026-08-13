# -*- coding: utf-8 -*-
"""Internal implementation parts for the AkShare data-provider fetcher.

Capability-domain modules under this package are private to ``data_provider``.
External callers must continue to import from ``data_provider.akshare_fetcher``
(or ``data_provider``) so public surfaces and test patch targets stay stable
(ADR-006 / Issue #1068).

Owned domains:
- ``symbols`` — market/code classification helpers
- ``timeout_client`` — process-bounded AkShare SDK calls
- ``parse_tencent`` / ``realtime_errors`` — pure parsers and failure labels
- ``history`` — daily/history orchestration methods
- ``realtime_quotes`` — EM/Sina/Tencent realtime methods
- ``market_boards`` — indices, stats, rankings, hot, limit-up
- ``enhanced`` — money flow, chip distribution, enhanced payload
- ``realtime_cache`` — full-market snapshot TTL / keep-last-good state
- ``facade_bind`` — ADR-006 clone/bind helpers
"""
