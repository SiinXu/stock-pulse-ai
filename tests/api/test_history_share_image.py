# -*- coding: utf-8 -*-

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.v1.endpoints import history as history_endpoint


class _FakeHistoryService:
    def __init__(self, result, markdown="# 中钨高新 000657 分析报告"):
        self.result = result
        self.markdown = markdown

    def resolve_and_get_detail(self, record_id):
        return self.result

    def get_markdown_report(self, record_id):
        return self.markdown


def _patch_service(
    monkeypatch,
    result,
    markdown="# 中钨高新 000657 分析报告",
    *,
    share_image_max_chars=100000,
    md2img_engine="markdown-to-file",
):
    service = _FakeHistoryService(result, markdown)
    monkeypatch.setattr(history_endpoint, "HistoryService", lambda _db: service)
    monkeypatch.setattr(
        history_endpoint,
        "get_config",
        lambda: SimpleNamespace(
            markdown_to_image_max_chars=15000,
            share_image_max_chars=share_image_max_chars,
            md2img_engine=md2img_engine,
        ),
    )
    return service


def test_history_share_image_returns_png_with_stock_payload(monkeypatch):
    raw_result = {"code": "000657", "name": "中钨高新", "dashboard": {}}
    _patch_service(
        monkeypatch,
        {
            "id": 17,
            "report_type": "detailed",
            "raw_result": raw_result,
            "context_snapshot": {},
        },
    )
    calls = []

    def fake_markdown_to_image(markdown, **kwargs):
        calls.append((markdown, kwargs))
        return b"\x89PNG\r\n\x1a\nposter"

    monkeypatch.setattr(history_endpoint, "markdown_to_image", fake_markdown_to_image)

    response = history_endpoint.get_history_share_image("17", db_manager=object())

    assert response.status_code == 200
    assert response.media_type == "image/png"
    assert response.body.startswith(b"\x89PNG")
    assert response.headers["content-disposition"] == 'attachment; filename="stockpulse-report-17.png"'
    assert calls[0][1]["structured_payload"] is raw_result
    assert calls[0][1]["max_chars"] == 100000


def test_history_share_image_prefers_market_review_payload(monkeypatch):
    market_payload = {"kind": "market_review", "date": "2026-08-01"}
    _patch_service(
        monkeypatch,
        {
            "id": 18,
            "report_type": "market_review",
            "raw_result": {"raw_response": "market report"},
            "context_snapshot": {"market_review_payload": market_payload},
        },
        markdown="# A股市场复盘",
    )
    captured = {}

    def fake_markdown_to_image(markdown, **kwargs):
        captured.update(kwargs)
        return b"png"

    monkeypatch.setattr(history_endpoint, "markdown_to_image", fake_markdown_to_image)

    history_endpoint.get_history_share_image("18", db_manager=object())

    assert captured["structured_payload"] is market_payload


def test_history_share_image_reports_renderer_unavailable(monkeypatch):
    _patch_service(
        monkeypatch,
        {
            "id": 19,
            "report_type": "detailed",
            "raw_result": {"code": "000657"},
            "context_snapshot": {},
        },
    )
    monkeypatch.setattr(history_endpoint, "markdown_to_image", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        history_endpoint.get_history_share_image("19", db_manager=object())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "share_image_unavailable"


def test_history_share_image_rejects_oversize_content_with_413(monkeypatch):
    """Length check runs in the endpoint before the renderer (no md2img mock of the check)."""
    limit = 64
    markdown = "x" * (limit + 1)
    renderer_calls = []

    def fake_markdown_to_image(*_args, **_kwargs):
        renderer_calls.append(True)
        return b"should-not-run"

    _patch_service(
        monkeypatch,
        {
            "id": 21,
            "report_type": "detailed",
            "raw_result": {"code": "000657"},
            "context_snapshot": {},
        },
        markdown=markdown,
        share_image_max_chars=limit,
    )
    monkeypatch.setattr(history_endpoint, "markdown_to_image", fake_markdown_to_image)

    with pytest.raises(HTTPException) as exc_info:
        history_endpoint.get_history_share_image("21", db_manager=object())

    assert exc_info.value.status_code == 413
    detail = exc_info.value.detail
    assert detail["error"] == "share_image_content_too_large"
    assert detail["params"]["limit"] == limit
    assert detail["params"]["actual"] == len(markdown)
    assert renderer_calls == []


def test_history_share_image_allows_content_above_im_cap(monkeypatch):
    """Share-image bound is independent of MARKDOWN_TO_IMAGE_MAX_CHARS (15000)."""
    markdown = "d" * 20000  # longer than the IM notification cap
    calls = []

    def fake_markdown_to_image(content, **kwargs):
        calls.append((len(content), kwargs.get("max_chars")))
        return b"\x89PNG\r\n\x1a\nposter"

    _patch_service(
        monkeypatch,
        {
            "id": 22,
            "report_type": "detailed",
            "raw_result": {"code": "000657"},
            "context_snapshot": {},
        },
        markdown=markdown,
        share_image_max_chars=100000,
    )
    monkeypatch.setattr(history_endpoint, "markdown_to_image", fake_markdown_to_image)

    response = history_endpoint.get_history_share_image("22", db_manager=object())

    assert response.status_code == 200
    assert calls == [(20000, 100000)]


def test_history_share_image_returns_not_found(monkeypatch):
    _patch_service(monkeypatch, None)

    with pytest.raises(HTTPException) as exc_info:
        history_endpoint.get_history_share_image("missing", db_manager=object())

    assert exc_info.value.status_code == 404
