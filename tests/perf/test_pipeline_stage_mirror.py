# -*- coding: utf-8 -*-
"""Pipeline stage observation mirrors into the perf collector when enabled."""

from __future__ import annotations

import pytest

from src.perf.collector import (
    activate_collector,
    reset_collector,
    set_collection_enabled_override,
)
from src.services.run_diagnostics import PipelineStageObservation

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _reset_perf_flags():
    set_collection_enabled_override(None)
    yield
    set_collection_enabled_override(None)


def test_pipeline_stage_mirror_records_when_enabled() -> None:
    set_collection_enabled_override(True)
    collector, token = activate_collector()
    try:
        with PipelineStageObservation("fetch") as obs:
            obs.finish(status="success")
        snapshot = collector.snapshot()
        assert snapshot["span_count"] == 1
        span = snapshot["spans"][0]
        assert span["name"] == "pipeline.fetch"
        assert span["category"] == "pipeline_stage"
        assert span["attrs"]["status"] == "success"
    finally:
        reset_collector(token)


def test_pipeline_stage_mirror_silent_when_disabled() -> None:
    set_collection_enabled_override(False)
    collector, token = activate_collector()
    try:
        with PipelineStageObservation("analyze") as obs:
            obs.finish(status="success")
        assert collector.snapshot()["span_count"] == 0
    finally:
        reset_collector(token)
