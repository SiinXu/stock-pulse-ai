#!/usr/bin/env python3
"""
AI code review script used by GitHub Actions PR Review workflow.
"""
import json
import os
import re
import subprocess
import traceback


MAX_DIFF_LENGTH = 18000
CHARACTER_REFERENCE_PATTERN = re.compile(
    r"&(?:\#[xX][0-9A-Fa-f]+|\#\d+|[A-Za-z][A-Za-z0-9]+);"
)
REVIEW_PATHS = [
    '*.py',
    '*.md',
    'README.md',
    'AGENTS.md',
    'docs/**',
    '.github/PULL_REQUEST_TEMPLATE.md',
    'requirements.txt',
    '.github/requirements-ci.txt',
    'pyproject.toml',
    'setup.cfg',
    '.github/workflows/*.yml',
    '.github/scripts/*.py',
    'apps/dsa-web/**',
]


def _escape_non_ascii(value):
    """Escape non-ASCII characters before writing dynamic values to Actions logs."""
    text = str(value)

    def escape(character):
        code_point = ord(character)
        if code_point <= 0xFFFF:
            return f"\\u{code_point:04X}"
        return f"\\u{{{code_point:X}}}"

    return ''.join(escape(character) if ord(character) > 0x7F else character for character in text)


def _contains_non_english_letter(value):
    """Return whether text contains letters outside the basic English alphabet."""
    return any(character.isalpha() and not character.isascii() for character in str(value))


def _contains_character_reference(value):
    """Reject Markdown character references that could render localized text."""
    return CHARACTER_REFERENCE_PATTERN.search(str(value)) is not None


def _log_exception(prefix, exc):
    """Write an exception and traceback without leaking localized text."""
    print(f"{prefix}: {_escape_non_ascii(exc)}")
    formatted = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    print(_escape_non_ascii(formatted.rstrip()))


def run_git(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"⚠️ git command failed: {_escape_non_ascii(' '.join(args))}")
        print(_escape_non_ascii(result.stderr.strip()))
        return ''
    return result.stdout.strip()


def get_diff():
    """Get PR diff content for review-relevant files."""
    base_ref = os.environ.get('GITHUB_BASE_REF', 'main')
    diff = run_git(['git', 'diff', f'origin/{base_ref}...HEAD', '--', *REVIEW_PATHS])
    truncated = len(diff) > MAX_DIFF_LENGTH
    return diff[:MAX_DIFF_LENGTH], truncated


def get_changed_files():
    """Get changed file list for review-relevant files."""
    base_ref = os.environ.get('GITHUB_BASE_REF', 'main')
    output = run_git(['git', 'diff', '--name-only', f'origin/{base_ref}...HEAD', '--', *REVIEW_PATHS])
    return output.split('\n') if output else []


def get_pr_context():
    """Read PR title/body from GitHub event payload when available."""
    event_path = os.environ.get('GITHUB_EVENT_PATH')
    if not event_path or not os.path.exists(event_path):
        return '', ''
    try:
        with open(event_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        pr = payload.get('pull_request', {})
        return (pr.get('title') or '').strip(), (pr.get('body') or '').strip()
    except Exception:
        return '', ''


def classify_files(files):
    py_files = [f for f in files if f.endswith('.py')]
    doc_files = [f for f in files if f.endswith('.md') or f.startswith('docs/') or f in ('README.md', 'AGENTS.md')]
    frontend_files = [f for f in files if f.startswith('apps/dsa-web/') or f.endswith(('.tsx', '.ts'))]
    ci_files = [f for f in files if f.startswith('.github/workflows/')]
    config_files = [
        f for f in files if f in ('requirements.txt', '.github/requirements-ci.txt', 'pyproject.toml', 'setup.cfg', '.github/PULL_REQUEST_TEMPLATE.md')
    ]
    return py_files, doc_files, frontend_files, ci_files, config_files


def _build_ci_context():
    """Build CI context section from environment variables set by the workflow."""
    auto_check_result = os.environ.get('CI_AUTO_CHECK_RESULT', '')
    syntax_ok = os.environ.get('CI_SYNTAX_OK', '')
    has_py = os.environ.get('CI_HAS_PY_CHANGES', 'false')

    if not auto_check_result:
        return """
## CI Check Status
> ⚠️ CI results are unavailable. Do not assume CI passed; mark verification conclusions as "Unable to confirm."
"""

    lines = ["\n## CI Check Status (from this pull request run)"]
    lines.append(f"- Overall static checks: **{'✅ Passed' if auto_check_result == 'success' else '❌ Failed'}**")
    if has_py == 'true':
        lines.append(f"- Python syntax (py_compile): **{'✅ Passed' if syntax_ok == 'true' else '❌ Failed' if syntax_ok == 'false' else '⏭️ Not run'}**")
        lines.append("- Critical Flake8 errors (E9/F63/F7/F82): **✅ Passed** (a failure would make the overall static check fail)")
    else:
        lines.append("- Python files: no changes; syntax checks were skipped")
    lines.append("")
    lines.append("> These checks cover syntax (py_compile) and fatal lint errors (Flake8 E9/F63/F7/F82) only. `./scripts/ci_gate.sh` is **not part of this review workflow**. For Python backend changes, mention a missing gate result or skip reason as a recommendation, not a blocker. When syntax and Flake8 already passed here, the PR description does not need to duplicate their local output.")
    lines.append("")
    return '\n'.join(lines)


def build_prompt(diff_content, files, truncated, pr_title, pr_body):
    """Build AI review prompt aligned with AGENTS.md requirements."""
    truncate_notice = ''
    if truncated:
        truncate_notice = "\n\n> ⚠️ The diff was truncated because it exceeded the review limit. Review the visible content and identify any uncertainty.\n"

    py_files, doc_files, frontend_files, ci_files, config_files = classify_files(files)
    ci_context = _build_ci_context()
    return f"""You are this repository's pull request review assistant. Review the code, documentation, and CI evidence together. Respond only in English.

## Pull Request Information
- Title: {pr_title or '(empty)'}
- Description:
{pr_body or '(empty)'}

## Changed File Summary
- Python: {len(py_files)}
- Docs/Markdown: {len(doc_files)}
- Frontend (apps/dsa-web): {len(frontend_files)}
- CI Workflow: {len(ci_files)}
- Config/Template: {len(config_files)}

Changed files:
{', '.join(files)}{truncate_notice}

## Code Changes (diff)
```diff
{diff_content}
```
{ci_context}
## Required Review Rules (from AGENTS.md)
1. Necessity: confirm the change addresses a clear problem or business need and avoids unrelated refactoring.
2. Traceability: check for a linked issue through `Fixes` or `Refs`. A natural-language issue reference is acceptable and must not fail review only for formatting. Without an issue, require a motivation and acceptance criteria.
3. Type: determine whether fix/feat/refactor/docs/chore/test/ci matches the actual change.
4. Description completeness: check for background, complete scope, verification commands and results, compatibility risks, and an actionable rollback plan. Use the CI status above when evaluating verification: (a) when py_compile and Flake8 passed, the PR may cite CI without repeating local output; (b) `./scripts/ci_gate.sh` is not covered by this review workflow, so a missing result or skip reason for Python backend changes is a recommendation; (c) without CI results, do not assume CI passed and mark verification as "Unable to confirm."
5. Merge readiness: return Ready or Not Ready and identify blockers.
6. For user-visible changes, confirm the relevant documentation and `docs/CHANGELOG.md` are updated. Update `README.md` only when homepage-level information changed.

## Blocker Versus Recommendation Criteria
Only the following may make the pull request Not Ready:
- Correctness or security problems, such as logic errors, swallowed exceptions, or vulnerabilities
- Failed blocking CI checks
- A material contradiction between the PR description and the actual changes
- No actionable rollback plan

Treat the following as recommendations that do not affect merge readiness:
- Nonstandard issue-reference formatting
- Missing local syntax/Flake8 evidence when the CI status above shows both passed
- No `./scripts/ci_gate.sh` result or skip reason for a Python backend change
- Nonessential wording or formatting concerns
- Comment-language style or unrelated lockfile changes

## Required Review Output
- Respond only in English.
- Begin with `Conclusion: Ready to Merge` or `Conclusion: Not Ready`.
- Then provide this structured result:
  - Necessity: Pass/Fail with rationale
  - Traceability: Pass/Fail with evidence
  - Type: recommended type
  - Description completeness: Complete/Incomplete with missing items
  - Risk level: Low/Medium/High with key risks
  - Required changes: at most five items, blockers only, ordered by priority
  - Recommendations: at most five items
- Keep nonblocking format, traceability, and verification-evidence concerns under Recommendations.
- Locate findings by file path where possible and explain their impact.
- When evidence is insufficient, write "Unable to confirm from the current diff and pull request description."
"""


def _accept_english_review(review: str | None, provider: str) -> str | None:
    """Reject provider output that would violate the English-only bot policy."""
    if not review:
        return None
    if _contains_non_english_letter(review):
        print(f"⚠️ {_escape_non_ascii(provider)} review rejected because it contains non-English letters")
        return None
    if _contains_character_reference(review):
        print(f"⚠️ {_escape_non_ascii(provider)} review rejected because it contains an HTML character reference")
        return None
    return review


def review_with_gemini(prompt):
    """Run review with Gemini API."""
    api_key = os.environ.get('GEMINI_API_KEY')
    model = os.environ.get('GEMINI_MODEL') or os.environ.get('GEMINI_MODEL_FALLBACK') or 'gemini-2.5-flash'

    if not api_key:
        print("❌ Gemini API key is not configured (check the GEMINI_API_KEY GitHub secret)")
        return None

    print(f"🤖 Using model: {_escape_non_ascii(model)}")

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt
        )
        print(f"✅ Gemini ({_escape_non_ascii(model)}) review completed successfully")
        return response.text
    except ImportError as e:
        print(f"❌ Gemini dependency is not installed: {_escape_non_ascii(e)}")
        print("   Install google-genai with: pip install google-genai")
        return None
    except Exception as e:
        _log_exception("❌ Gemini review failed", e)
        return None


def review_with_openai(prompt):
    """Run review with OpenAI-compatible API as fallback."""
    api_key = os.environ.get('OPENAI_API_KEY')
    base_url = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    model = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

    if not api_key:
        print("❌ OpenAI API key is not configured (check the OPENAI_API_KEY GitHub secret)")
        return None

    print(f"🌐 Base URL: {_escape_non_ascii(base_url)}")
    print(f"🤖 Using model: {_escape_non_ascii(model)}")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.3
        )
        print(f"✅ OpenAI-compatible review ({_escape_non_ascii(model)}) completed successfully")
        return response.choices[0].message.content
    except ImportError as e:
        print(f"❌ OpenAI dependency is not installed: {_escape_non_ascii(e)}")
        print("   Install openai with: pip install openai")
        return None
    except Exception as e:
        _log_exception("❌ OpenAI-compatible review failed", e)
        return None


def ai_review(diff_content, files, truncated):
    """Run AI review: Gemini first, then OpenAI fallback."""
    pr_title, pr_body = get_pr_context()
    prompt = build_prompt(diff_content, files, truncated, pr_title, pr_body)

    result = _accept_english_review(review_with_gemini(prompt), "Gemini")
    if result:
        return result

    print("Trying the OpenAI-compatible fallback...")
    result = _accept_english_review(review_with_openai(prompt), "OpenAI-compatible provider")
    if result:
        return result

    return None


def main():
    diff, truncated = get_diff()
    files = get_changed_files()

    if not diff or not files:
        print("No reviewable code, documentation, or configuration changes; skipping AI review")
        summary_file = os.environ.get('GITHUB_STEP_SUMMARY')
        if summary_file:
            with open(summary_file, 'a', encoding='utf-8') as f:
                f.write("## 🤖 AI Code Review\n\n✅ No reviewable changes\n")
        return

    print(f"Reviewing files: {_escape_non_ascii(files)}")
    if truncated:
        print(f"⚠️ Diff truncated to {MAX_DIFF_LENGTH} characters")

    review = ai_review(diff, files, truncated)

    summary_file = os.environ.get('GITHUB_STEP_SUMMARY')

    strict_mode = os.environ.get('AI_REVIEW_STRICT', 'false').lower() == 'true'

    if review:
        if summary_file:
            with open(summary_file, 'a', encoding='utf-8') as f:
                f.write(f"## 🤖 AI Code Review\n\n{review}\n")

        with open('ai_review_result.txt', 'w', encoding='utf-8') as f:
            f.write(review)

        print("AI review completed")
    else:
        print("⚠️ No AI review provider is available")
        if summary_file:
            with open(summary_file, 'a', encoding='utf-8') as f:
                f.write("## 🤖 AI Code Review\n\n⚠️ No AI provider is available; check the workflow configuration\n")
        if strict_mode:
            raise SystemExit("AI_REVIEW_STRICT=true and no AI review result is available")


if __name__ == '__main__':
    main()
