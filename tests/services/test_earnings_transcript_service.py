# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic tests for earnings transcript parsing (no network, no LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.services.earnings_transcript_service import (
    MAX_CHUNK_CHARS,
    TRANSCRIPT_DISCLAIMER,
    TRANSCRIPT_SCHEMA_VERSION,
    EarningsTranscriptService,
    assert_metrics_source_traceable,
    chunk_transcript_text,
    extract_metrics_with_offsets,
    parse_transcript_path,
    parse_transcript_text,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "multimodal"
SAMPLE_TXT = FIXTURES / "sample_earnings_transcript.txt"


def _load_sample() -> str:
    return SAMPLE_TXT.read_text(encoding="utf-8")


def test_parse_fixture_segments_and_qa() -> None:
    text = _load_sample()
    result = parse_transcript_text(text, filename="sample_earnings_transcript.txt")

    assert result["schema_version"] == TRANSCRIPT_SCHEMA_VERSION
    assert result["status"] in {"available", "degraded"}
    assert result["disclaimer"] == TRANSCRIPT_DISCLAIMER
    assert result["method"] == "local_deterministic"
    assert result["text_char_count"] == len(text.replace("\r\n", "\n").replace("\r", "\n"))

    segment_types = {seg["type"] for seg in result["segments"]}
    assert "prepared_remarks" in segment_types or "qa" in segment_types
    assert any(seg["type"] == "qa" for seg in result["segments"])

    assert len(result["qa_items"]) >= 2
    first_q = result["qa_items"][0]
    assert first_q.get("question_text")
    assert first_q.get("start_char") is not None
    assert "Alice" in (first_q.get("questioner") or "") or "Chen" in (
        first_q.get("questioner") or ""
    )


def test_metrics_are_source_traceable() -> None:
    """Mandatory acceptance: every metric value equals text[start:end]."""
    text = _load_sample()
    result = parse_transcript_text(text)
    metrics = result["metrics"]
    assert metrics, "expected at least one metric from the fixture"

    failures = assert_metrics_source_traceable(
        text.replace("\r\n", "\n").replace("\r", "\n"),
        metrics,
    )
    assert failures == []

    values = {m["value_text"] for m in metrics}
    assert any("1,250" in v or "1250" in v for v in values)
    assert any("48.5%" in v or "48.5" in v for v in values)
    assert any("$1.42" in v or "1.42" in v for v in values)

    for metric in metrics:
        assert metric.get("source_verified") is True
        start = metric["start_char"]
        end = metric["end_char"]
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        assert normalized[start:end] == metric["value_text"]


def test_does_not_fabricate_absent_numbers() -> None:
    """Construct text without a target figure; assert it is never invented."""
    text = (
        "Prepared Remarks\n"
        "CEO: We had a good quarter and remain confident.\n"
        "Question-and-Answer Session\n"
        "Operator: First question from Sam Lee with Acme Research.\n"
        "Q - Sam Lee, Acme Research:\n"
        "Any color on demand?\n"
        "A - CEO:\n"
        "Demand was stable. We do not provide a specific figure today.\n"
    )
    result = parse_transcript_text(text)
    values = [m["value_text"] for m in result["metrics"]]
    forbidden = {"42%", "$999 million", "3.14159", "777", "99.9%"}
    for fake in forbidden:
        assert fake not in values
        assert not any(fake in v for v in values)

    failures = assert_metrics_source_traceable(text, result["metrics"])
    assert failures == []
    for metric in result["metrics"]:
        assert metric["value_text"] in text
        assert text[metric["start_char"] : metric["end_char"]] == metric["value_text"]


def test_extract_metrics_rejects_span_mismatch_via_helper() -> None:
    text = "Revenue was $100 million."
    metrics = extract_metrics_with_offsets(text)
    assert metrics
    bad = dict(metrics[0])
    bad["value_text"] = "999%"
    failures = assert_metrics_source_traceable(text, [bad])
    assert len(failures) == 1


def test_long_transcript_chunking_respects_limit() -> None:
    paragraph = (
        "Management discussed recurring revenue of $10 million and growth of 8%.\n\n"
    )
    text = "Prepared Remarks\n" + (paragraph * 120)
    assert len(text) > MAX_CHUNK_CHARS

    chunks = chunk_transcript_text(text, max_chunk_chars=2_000, overlap_chars=100)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk["char_count"] <= 2_000
        assert chunk["end_char"] - chunk["start_char"] == chunk["char_count"]
        assert text[chunk["start_char"] : chunk["end_char"]] == chunk["text"]

    result = parse_transcript_text(text, max_chunk_chars=2_000)
    assert result["chunks"]
    assert all(c["char_count"] <= 2_000 for c in result["chunks"])
    assert all(c["char_count"] <= MAX_CHUNK_CHARS for c in result["chunks"])


def test_forward_looking_and_optional_tone() -> None:
    text = _load_sample()
    result = parse_transcript_text(text)
    kinds = {item["kind"] for item in result["forward_looking"]}
    assert "guidance" in kinds or "disclaimer" in kinds
    if result["management_tone"] is not None:
        assert result["management_tone"]["judgment"] == "subjective"
        assert result["management_tone"]["label"] in {
            "confident",
            "cautious",
            "mixed",
        }


def test_empty_input_unavailable() -> None:
    result = parse_transcript_text("   ")
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "empty_input"
    assert result["metrics"] == []


def test_parse_path_text_under_root(tmp_path: Path) -> None:
    target = tmp_path / "call.txt"
    target.write_text(_load_sample(), encoding="utf-8")
    result = parse_transcript_path("call.txt", file_root=str(tmp_path))
    assert result["status"] in {"available", "degraded"}
    assert result["metrics"]
    failures = assert_metrics_source_traceable(
        target.read_text(encoding="utf-8"),
        result["metrics"],
    )
    assert failures == []


def test_path_traversal_unavailable(tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("Revenue was $1 million.\n", encoding="utf-8")
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    result = parse_transcript_path("../secret.txt", file_root=str(sandbox))
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "path_outside_root"


def test_service_wrapper() -> None:
    service = EarningsTranscriptService()
    result = service.parse_text(_load_sample(), filename="f.txt")
    assert result["schema_version"] == TRANSCRIPT_SCHEMA_VERSION
    assert isinstance(result["qa_items"], list)


def test_chunk_overlap_progresses() -> None:
    text = ("word " * 500).strip()
    chunks = chunk_transcript_text(text, max_chunk_chars=200, overlap_chars=20)
    assert len(chunks) >= 2
    starts = [c["start_char"] for c in chunks]
    assert starts == sorted(starts)
    assert starts[0] == 0
    assert chunks[-1]["end_char"] == len(text)
