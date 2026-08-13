from __future__ import annotations

import pytest

from scripts.merge_resolvers.common import RefusalError
from scripts.merge_resolvers.playground_catalog import CATALOG_PATH, SUPPORTED_PATH, resolve


def _current(ours: str, theirs: str) -> str:
    return (
        "describe('catalog', () => {\n"
        "<<<<<<< HEAD\n"
        f"    {ours}\n"
        "=======\n"
        f"    {theirs}\n"
        ">>>>>>> branch\n"
        "});\n"
    )


@pytest.fixture
def catalog_root(tmp_path):
    path = tmp_path / CATALOG_PATH
    path.parent.mkdir(parents=True)
    path.write_text(
        "export const PLAYGROUND_CATALOG: readonly Entry[] = [\n"
        "  common('a', 'A'),\n"
        "  entry('category', 'b', 'B', 'B.tsx'),\n"
        "  common('c', 'C'),\n"
        "\n];\n",
        encoding="utf-8",
    )
    return tmp_path


def test_recomputes_catalog_count(context_factory, catalog_root):
    output = resolve(
        context_factory(
            SUPPORTED_PATH,
            current=_current(
                "expect(PLAYGROUND_CATALOG).toHaveLength(1);",
                "expect(PLAYGROUND_CATALOG).toHaveLength(2);",
            ),
        ),
        catalog_root,
    )
    assert "toHaveLength(3)" in output


def test_refuses_same_count_on_both_sides(context_factory, catalog_root):
    assertion = "expect(PLAYGROUND_CATALOG).toHaveLength(2);"
    with pytest.raises(RefusalError, match="same value"):
        resolve(context_factory(SUPPORTED_PATH, current=_current(assertion, assertion)), catalog_root)


def test_refuses_empty_conflict(context_factory, catalog_root):
    with pytest.raises(RefusalError, match="no conflict hunks"):
        resolve(context_factory(SUPPORTED_PATH, current="describe('catalog', () => {});\n"), catalog_root)


def test_refuses_non_assertion_conflict(context_factory, catalog_root):
    with pytest.raises(RefusalError, match="non-length-assertion"):
        resolve(
            context_factory(
                SUPPORTED_PATH,
                current=_current("const count = 1;", "const count = 2;"),
            ),
            catalog_root,
        )
