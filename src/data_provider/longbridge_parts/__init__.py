# -*- coding: utf-8 -*-
"""Internal implementation parts for the Longbridge data-provider fetcher.

Capability-domain modules under this package are private to ``data_provider``.
External callers must continue to import from
``src.data_provider.longbridge_fetcher`` (or ``src.data_provider``) so public
surfaces and test patch targets stay stable (ADR-006 / Issue #1068).

Owned domains:
- ``realtime`` — realtime quote, static info cache, and volume-ratio computation
"""
