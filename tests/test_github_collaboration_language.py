"""Guards for English-only GitHub collaboration assets."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType


ROOT_DIR = Path(__file__).resolve().parent.parent
GITHUB_DIR = ROOT_DIR / ".github"
ADDITIONAL_ACTIONS_TEXT_FILES = {
    ROOT_DIR / "scripts" / "test.sh",
}
HAN_PATTERN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ebef\U00030000-\U0003134f]"
)
ALLOWED_LOCALIZED_LINES = {
    GITHUB_DIR / "copilot-instructions.md": {
        "- In `docs/CHANGELOG.md`, the `[Unreleased]` section uses a **flat format**: one line per entry "
        "formatted as `- [type] description`, where type is one of `新功能`/`改进`/`修复`/`文档`/`测试`/`chore`. "
        "**Do not add `### category headers` inside `[Unreleased]`** to minimize merge conflicts in concurrent "
        "PRs. A maintainer will reorganize into the full categorized format at release time.",
    },
    GITHUB_DIR / "scripts" / "build_release_notes.py": {
        'r"^### 发布亮点\\s*(.*?)(?=^### |\\Z)",',
    },
}


def _read_utf8_text(path: Path) -> str | None:
    """Read repository text assets while ignoring binary files and bytecode caches."""
    if "__pycache__" in path.parts:
        return None
    raw = path.read_bytes()
    if b"\0" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _contains_non_ascii_letter(value: str) -> bool:
    return any(character.isalpha() and not character.isascii() for character in value)


def _load_ai_review_module() -> ModuleType:
    path = GITHUB_DIR / "scripts" / "ai_review.py"
    spec = importlib.util.spec_from_file_location("github_ai_review", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_github_collaboration_assets_use_english() -> None:
    violations: list[str] = []
    paths = set(GITHUB_DIR.rglob("*")) | ADDITIONAL_ACTIONS_TEXT_FILES

    for path in sorted(paths):
        if not path.is_file():
            continue

        content = _read_utf8_text(path)
        if content is None:
            continue

        for line_number, line in enumerate(content.splitlines(), start=1):
            if _contains_non_ascii_letter(line) and line.strip() not in ALLOWED_LOCALIZED_LINES.get(path, set()):
                violations.append(f"{path.relative_to(ROOT_DIR)}:{line_number}: {line.strip()}")

    assert violations == [], "Non-English scripts found in GitHub collaboration text:\n" + "\n".join(violations)


def test_pr_review_fetches_every_changed_file() -> None:
    workflow = (GITHUB_DIR / "workflows" / "pr-review.yml").read_text(encoding="utf-8")

    assert workflow.count("github.paginate(github.rest.pulls.listFiles") == 2
    assert "const escapeDynamicText = value => value.replace(unsafeDynamicPattern" in workflow
    assert "const displayFilename = escapeDynamicText(file.filename);" in workflow
    assert "\\`${file.filename}\\`" not in workflow
    assert "\\`${displayFilename}\\`" in workflow
    assert "const containsNonEnglishLetter = value =>" in workflow
    assert "const containsCharacterReference = value =>" in workflow
    artifact_guard = workflow.split("if (containsNonEnglishLetter(aiReview)) {", 1)[1].split("}", 1)[0]
    assert "AI review artifact omitted because it contains non-English letters" in artifact_guard
    assert "if (containsCharacterReference(aiReview)) {" in workflow
    assert "AI review artifact omitted because it contains an HTML character reference" in workflow
    assert "aiReview = '';" in artifact_guard
    assert "aiReview ? '✅ Completed'" in workflow
    assert "⏭️ No publishable result" in workflow
    assert "## 🤖 Automated Review Report" in workflow
    assert "## 🤖 自动审查报告" not in workflow


def test_pr_review_escapes_dynamic_step_summary_paths() -> None:
    workflow = (GITHUB_DIR / "workflows" / "pr-review.yml").read_text(encoding="utf-8")

    assert workflow.count("escape_dynamic_text() {") == 4
    assert "([^\\x00-\\x7F]|&)" in workflow
    assert "const unsafeDynamicPattern = /[^\\x00-\\x7F]|&/gu;" in workflow
    assert 'echo "$SENSITIVE_FILES" | escape_dynamic_text >> $GITHUB_STEP_SUMMARY' in workflow
    assert 'echo -e "$ERRORS" | escape_dynamic_text >> $GITHUB_STEP_SUMMARY' in workflow
    assert 'echo "$RESULT" | escape_dynamic_text >> $GITHUB_STEP_SUMMARY' in workflow
    assert 'echo "$STATS" | escape_dynamic_text >> $GITHUB_STEP_SUMMARY' in workflow
    assert 'echo "$SENSITIVE_FILES" >> $GITHUB_STEP_SUMMARY' not in workflow
    assert 'echo -e "$ERRORS" >> $GITHUB_STEP_SUMMARY' not in workflow
    assert 'echo "$RESULT" >> $GITHUB_STEP_SUMMARY' not in workflow
    assert 'echo "$STATS" >> $GITHUB_STEP_SUMMARY' not in workflow
    assert 'COMPILE_OUTPUT=$(python -m py_compile "$file" 2>&1)' in workflow
    assert 'printf \'%s\\n\' "$COMPILE_OUTPUT" | escape_dynamic_text' in workflow


def test_ai_review_falls_back_when_provider_returns_han(monkeypatch) -> None:
    ai_review = _load_ai_review_module()
    monkeypatch.setattr(ai_review, "get_pr_context", lambda: ("", ""))
    monkeypatch.setattr(ai_review, "review_with_gemini", lambda _prompt: "结论：可以合并")
    monkeypatch.setattr(
        ai_review,
        "review_with_openai",
        lambda _prompt: "Conclusion: Ready to Merge",
    )

    result = ai_review.ai_review("diff", ["example.py"], False)

    assert result == "Conclusion: Ready to Merge"


def test_ai_review_does_not_publish_han_from_fallback(monkeypatch) -> None:
    ai_review = _load_ai_review_module()
    monkeypatch.setattr(ai_review, "get_pr_context", lambda: ("", ""))
    monkeypatch.setattr(ai_review, "review_with_gemini", lambda _prompt: None)
    monkeypatch.setattr(ai_review, "review_with_openai", lambda _prompt: "需要修改")

    result = ai_review.ai_review("diff", ["example.py"], False)

    assert result is None


def test_ai_review_rejects_non_english_scripts() -> None:
    ai_review = _load_ai_review_module()

    reviews = (
        "Conclusion: Ready to Merge\nРезультат готов",
        "Conclusion: Ready to Merge\n리뷰 완료",
        "Conclusion: Ready to Merge\nレビュー完了",
    )

    for review in reviews:
        assert ai_review._accept_english_review(review, "test") is None


def test_ai_review_rejects_html_character_reference_bypasses() -> None:
    ai_review = _load_ai_review_module()

    reviews = (
        "Conclusion: Ready to Merge\n&#x4E2D;&#x6587;",
        "Conclusion: Ready to Merge\n&#20013;&#25991;",
        "Conclusion: Ready to Merge\n&zhcy;&ucy;&kcy;&vcy;&acy;",
    )

    for review in reviews:
        assert ai_review._accept_english_review(review, "test") is None


def test_ai_review_escapes_han_in_action_logs(monkeypatch, capsys) -> None:
    ai_review = _load_ai_review_module()

    class FailedCommand:
        returncode = 1
        stdout = ""
        stderr = "路径错误"

    monkeypatch.setattr(ai_review.subprocess, "run", lambda *_args, **_kwargs: FailedCommand())

    assert ai_review.run_git(["git", "status", "中文目录"]) == ""
    output = capsys.readouterr().out

    assert HAN_PATTERN.search(output) is None
    assert r"\u4E2D\u6587\u76EE\u5F55" in output
    assert r"\u8DEF\u5F84\u9519\u8BEF" in output


def test_manual_docker_publish_validates_and_quotes_image_tag() -> None:
    workflow = (GITHUB_DIR / "workflows" / "ghcr-dockerhub.yml").read_text(encoding="utf-8")

    assert "IMAGE_TAG: ${{ inputs.image_tag }}" in workflow
    assert '[[ ! "$IMAGE_TAG" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]]' in workflow

    run_blocks = re.findall(r"run: \|\n((?: {10}.*\n?)*)", workflow)
    assert run_blocks
    assert all("${{ inputs.image_tag }}" not in block for block in run_blocks)
    assert 'echo "- Tags: $IMAGE_TAG, latest"' in workflow
    assert ':$IMAGE_TAG" >> "$GITHUB_STEP_SUMMARY"' in workflow
