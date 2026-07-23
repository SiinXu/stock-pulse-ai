import pytest

from src.llm.response_content import strip_leading_think_wrapper


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        # Case-insensitive leading wrapper is stripped down to the final answer.
        (
            '<THINK>internal reasoning</THINK>\n{"status":"ok"}',
            '{"status":"ok"}',
        ),
        # A literal <think> tag inside a JSON string is preserved.
        (
            '{"summary":"literal <think>text</think>"}',
            '{"summary":"literal <think>text</think>"}',
        ),
        # The match is anchored at the start; a non-leading wrapper is untouched.
        (
            'prefix <think>internal reasoning</think>{"status":"ok"}',
            'prefix <think>internal reasoning</think>{"status":"ok"}',
        ),
        # A malformed/unclosed wrapper fails closed for strict validation.
        (
            '<think>unclosed reasoning{"status":"ok"}',
            '<think>unclosed reasoning{"status":"ok"}',
        ),
    ],
)
def test_strip_leading_think_wrapper_is_anchored_and_fail_closed(
    response: str,
    expected: str,
) -> None:
    assert strip_leading_think_wrapper(response) == expected


def test_strip_leading_think_wrapper_handles_empty_and_none() -> None:
    assert strip_leading_think_wrapper("") == ""
    assert strip_leading_think_wrapper(None) == ""  # type: ignore[arg-type]
