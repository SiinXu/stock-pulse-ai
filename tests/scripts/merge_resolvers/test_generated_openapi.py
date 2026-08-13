from __future__ import annotations

from pathlib import Path

import pytest

from scripts.merge_resolvers import generated_openapi
from scripts.merge_resolvers.common import RefusalError


CONFLICT = "<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> branch\n"


@pytest.fixture
def generator_root(tmp_path):
    binary = tmp_path / "apps/dsa-web/node_modules/.bin/openapi-typescript"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    return tmp_path


def test_regenerates_openapi_and_types_together(
    monkeypatch,
    context_factory,
    generator_root,
):
    def fake_run(path, command, cwd):
        del path, cwd
        if any(argument.endswith("export_openapi.py") for argument in command):
            Path(command[-1]).write_text('{"openapi":"3.1.0"}\n', encoding="utf-8")
        else:
            Path(command[-1]).write_text("export interface paths {}\n", encoding="utf-8")

    monkeypatch.setattr(generated_openapi, "_run", fake_run)
    context = context_factory(
        generated_openapi.OPENAPI_PATH,
        ours="ours\n",
        theirs="theirs\n",
        current=CONFLICT,
    )

    outputs = generated_openapi.resolve(
        {generated_openapi.OPENAPI_PATH: context},
        generator_root,
    )

    assert set(outputs) == {
        generated_openapi.OPENAPI_PATH,
        generated_openapi.TYPES_PATH,
    }
    assert b'"openapi"' in outputs[generated_openapi.OPENAPI_PATH]
    assert b"interface paths" in outputs[generated_openapi.TYPES_PATH]


def test_refuses_identical_generated_changes(context_factory, generator_root):
    context = context_factory(
        generated_openapi.OPENAPI_PATH,
        ours="same\n",
        theirs="same\n",
        current=CONFLICT,
    )
    with pytest.raises(RefusalError, match="identically"):
        generated_openapi.resolve(
            {generated_openapi.OPENAPI_PATH: context},
            generator_root,
        )


def test_refuses_empty_conflict(context_factory, generator_root):
    context = context_factory(
        generated_openapi.OPENAPI_PATH,
        ours="ours\n",
        theirs="theirs\n",
        current="{}\n",
    )
    with pytest.raises(RefusalError, match="no conflict hunks"):
        generated_openapi.resolve(
            {generated_openapi.OPENAPI_PATH: context},
            generator_root,
        )


def test_refuses_malformed_conflict(context_factory, generator_root):
    context = context_factory(
        generated_openapi.OPENAPI_PATH,
        ours="ours\n",
        theirs="theirs\n",
        current="<<<<<<< HEAD\nunterminated\n",
    )
    with pytest.raises(RefusalError, match="unterminated"):
        generated_openapi.resolve(
            {generated_openapi.OPENAPI_PATH: context},
            generator_root,
        )
