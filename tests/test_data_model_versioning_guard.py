# -*- coding: utf-8 -*-
"""Guard the serialized domain-artifact version inventory.

These artifacts embed an explicit version tag so historical payloads stay
interpretable after the models evolve. This guard binds the inventory
documented in docs/database-migrations.md ("Serialized Artifact Versioning")
to the real constants and asserts producers keep emitting the version field
during serialization, protecting the "historical artifacts remain usable"
contract of issue #224.

Any drift in a constant here must be a deliberate change accompanied by an
update to the documented inventory and, for breaking changes, a read/degrade
branch for the old value.
"""

from __future__ import annotations

import dataclasses

from src.agent.runtime.events import RUNTIME_EVENT_SCHEMA_VERSION, RuntimeEvent
from src.llm.usage import (
    PROVIDER_USAGE_SCHEMA_NAME,
    PROVIDER_USAGE_SCHEMA_VERSION,
    normalize_litellm_usage,
)
from src.schemas.analysis_context_pack import (
    PACK_VERSION,
    AnalysisContextPack,
    AnalysisSubject,
)
from src.schemas.decision_scale import (
    CANONICAL_DECISION_SCALE_VERSION,
    score_band_metadata,
)
from src.schemas.market_structure import (
    MARKET_STRUCTURE_SCHEMA_VERSION,
    MARKET_THEME_SCHEMA_VERSION,
    STOCK_MARKET_POSITION_SCHEMA_VERSION,
    MarketStructureContext,
    MarketThemeContext,
    StockMarketPosition,
)


def test_serialized_artifact_version_constants_match_documented_inventory() -> None:
    assert PACK_VERSION == "1.0"
    assert MARKET_THEME_SCHEMA_VERSION == "market-theme-v1"
    assert STOCK_MARKET_POSITION_SCHEMA_VERSION == "stock-market-position-v1"
    assert MARKET_STRUCTURE_SCHEMA_VERSION == "market-structure-v1"
    assert CANONICAL_DECISION_SCALE_VERSION == "decision-scale-v1"
    assert RUNTIME_EVENT_SCHEMA_VERSION == 1
    assert PROVIDER_USAGE_SCHEMA_NAME == "provider_usage_v1"
    assert PROVIDER_USAGE_SCHEMA_VERSION == "2026-06-10"


def test_analysis_context_pack_serialization_emits_version() -> None:
    pack = AnalysisContextPack(subject=AnalysisSubject(code="600519"))
    assert pack.model_dump()["pack_version"] == PACK_VERSION
    assert pack.model_dump(mode="json")["pack_version"] == PACK_VERSION
    assert pack.to_safe_dict()["pack_version"] == PACK_VERSION


def test_market_structure_serialization_emits_version() -> None:
    theme = MarketThemeContext()
    position = StockMarketPosition(stock_code="600519")
    structure = MarketStructureContext(
        market_theme_context=theme,
        stock_market_position=position,
    )
    assert theme.model_dump()["schema_version"] == MARKET_THEME_SCHEMA_VERSION
    assert (
        position.model_dump()["schema_version"]
        == STOCK_MARKET_POSITION_SCHEMA_VERSION
    )
    assert (
        structure.model_dump()["schema_version"]
        == MARKET_STRUCTURE_SCHEMA_VERSION
    )


def test_runtime_event_carries_version_field() -> None:
    event = RuntimeEvent(
        event_type="stage_start",
        execution_id="exec-1",
        sequence=0,
        timestamp=0.0,
    )
    field_names = {field.name for field in dataclasses.fields(RuntimeEvent)}
    assert "schema_version" in field_names
    assert event.schema_version == RUNTIME_EVENT_SCHEMA_VERSION


def test_decision_scale_metadata_emits_version() -> None:
    metadata = score_band_metadata(85)
    assert metadata["scale_version"] == CANONICAL_DECISION_SCALE_VERSION


def test_provider_usage_record_emits_schema_version() -> None:
    record = normalize_litellm_usage(
        {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        model="openai/gpt-4o",
    )
    assert record["provider_usage_schema_name"] == PROVIDER_USAGE_SCHEMA_NAME
    assert record["provider_usage_schema_version"] == PROVIDER_USAGE_SCHEMA_VERSION
