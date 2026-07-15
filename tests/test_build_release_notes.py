from __future__ import annotations

import importlib.util
import io
import json
import logging
import urllib.error
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT_DIR / ".github" / "scripts" / "build_release_notes.py"


def _load_release_notes_module():
    spec = importlib.util.spec_from_file_location("build_release_notes", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _JsonResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> io.StringIO:
        return io.StringIO(json.dumps(self._payload))

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_github_login_from_pr_returns_successful_author(monkeypatch) -> None:
    module = _load_release_notes_module()

    def fake_urlopen(request, timeout):
        return _JsonResponse({"user": {"login": "octocat"}})

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    assert module._github_login_from_pr("owner/repo", "token", "123") == "octocat"


def test_github_login_from_pr_expected_degrades_without_warning(caplog) -> None:
    module = _load_release_notes_module()

    with caplog.at_level(logging.WARNING, logger=module.LOGGER.name):
        assert module._github_login_from_pr("owner/repo", "", "124") is None

    assert not caplog.records


def test_github_login_from_pr_404_degrades_without_warning(monkeypatch, caplog) -> None:
    module = _load_release_notes_module()

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    with caplog.at_level(logging.WARNING, logger=module.LOGGER.name):
        assert module._github_login_from_pr("owner/repo", "token", "125") is None

    assert not caplog.records


def test_github_login_from_pr_http_error_warns_with_pr_and_exception_type(
    monkeypatch,
    caplog,
) -> None:
    module = _load_release_notes_module()

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    with caplog.at_level(logging.WARNING, logger=module.LOGGER.name):
        assert module._github_login_from_pr("owner/repo", "secret-token", "126") is None

    assert "PR #126" in caplog.text
    assert "exception_type=HTTPError" in caplog.text
    assert "status=403" in caplog.text
    assert "secret-token" not in caplog.text


def test_github_login_from_pr_network_error_warns_with_pr_and_exception_type(
    monkeypatch,
    caplog,
) -> None:
    module = _load_release_notes_module()

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    with caplog.at_level(logging.WARNING, logger=module.LOGGER.name):
        assert module._github_login_from_pr("owner/repo", "secret-token", "127") is None

    assert "PR #127" in caplog.text
    assert "exception_type=URLError" in caplog.text
    assert "secret-token" not in caplog.text


def test_release_body_does_not_publish_localized_changelog_text(monkeypatch) -> None:
    module = _load_release_notes_module()
    monkeypatch.setattr(
        module,
        "_section_for",
        lambda version: """### 发布亮点

- feat: 新增市场分析
- fix: レビューを改善
- docs: Обновить документацию
- fix: &#x4E2D;&#x6587;
- docs: &#20013;&#25991;
- fix: Improve release reliability
""",
    )
    monkeypatch.setattr(module, "_previous_tag", lambda tag: "v1.2.2")
    monkeypatch.setattr(module, "_contributors", lambda previous_tag, tag: ["@octocat"])

    body = module.build("v1.2.3")

    assert "Improve release reliability" in body
    assert "新增市场分析" not in body
    assert "レビューを改善" not in body
    assert "Обновить документацию" not in body
    assert "&#x4E2D;" not in body
    assert "&#20013;" not in body
    assert module.HAN_PATTERN.search(body) is None
    assert not any(character.isalpha() and not character.isascii() for character in body)


def test_fallback_login_rejects_non_github_author_names() -> None:
    module = _load_release_notes_module()

    assert module._fallback_login("octocat <octocat@example.com>") == "octocat"
    assert module._fallback_login("中文作者 <author@example.com>") is None
