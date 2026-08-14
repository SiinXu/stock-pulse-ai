"""Unit tests for the derived-file merge resolvers.

Each resolver is exercised on a real conflicted git index (built in a temporary
repository) so that the index stages the resolvers rely on are genuine, and so
that the atomic-batch behaviour of ``resolve.py`` is tested end to end.

Every resolver is covered for at least:

* a normal additive merge,
* both sides changing the same entry (must refuse),
* an empty / marker-free file (no-op),
* an unexpected hunk shape (must refuse).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.merge_resolvers import (  # noqa: E402
    bundle_budget,
    docs_index,
    i18n_locales,
    playground_catalog,
    public_surface,
    resolve as resolve_entry,
    settings_help,
)
from scripts.merge_resolvers.common import (  # noqa: E402
    Context,
    Refusal,
    parse_conflicts,
    take_side,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )


def make_conflict(
    tmp_path: Path, files: dict[str, tuple[str, str, str]]
) -> Context:
    """Create a repository whose working tree holds a real merge conflict.

    ``files`` maps a repository-relative path to ``(base, ours, theirs)``.
    """

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")

    for rel_path, (base, _, _) in files.items():
        target = repo / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(base, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")

    _git(repo, "checkout", "-qb", "incoming")
    for rel_path, (_, _, theirs) in files.items():
        (repo / rel_path).write_text(theirs, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "theirs")

    _git(repo, "checkout", "-q", "main")
    for rel_path, (_, ours, _) in files.items():
        (repo / rel_path).write_text(ours, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "ours")

    merge = _git(repo, "merge", "--no-commit", "--no-ff", "incoming")
    assert merge.returncode != 0, "expected the synthetic merge to conflict"
    unmerged = _git(repo, "diff", "--name-only", "--diff-filter=U").stdout.split()
    assert unmerged, "expected at least one unmerged path"
    return Context(repo_root=repo)


# ---------------------------------------------------------------------------
# conflict parsing
# ---------------------------------------------------------------------------


def test_parse_conflicts_splits_and_renders_both_sides():
    text = "a\n<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> branch\nb\n"
    segments = parse_conflicts("x", text)
    assert take_side(segments, "ours") == "a\nours\nb\n"
    assert take_side(segments, "theirs") == "a\ntheirs\nb\n"


def test_parse_conflicts_supports_diff3_base_section():
    text = "<<<<<<< HEAD\nours\n||||||| base\nold\n=======\ntheirs\n>>>>>>> b\n"
    segments = parse_conflicts("x", text)
    assert take_side(segments, "ours") == "ours\n"
    assert take_side(segments, "theirs") == "theirs\n"


def test_parse_conflicts_refuses_stray_marker():
    with pytest.raises(Refusal):
        parse_conflicts("x", "a\n>>>>>>> branch\n")


def test_parse_conflicts_refuses_unterminated_hunk():
    with pytest.raises(Refusal):
        parse_conflicts("x", "<<<<<<< HEAD\nours\n")


# ---------------------------------------------------------------------------
# i18n locale tables
# ---------------------------------------------------------------------------

I18N_PATH = "apps/dsa-web/src/i18n/translations/de.ts"


def _i18n(entries: list[str]) -> str:
    body = "".join(f"  {line}\n" for line in entries)
    return "export const de = {\n" + body + "} as const;\n"


def test_i18n_merges_both_sides_and_restores_order(tmp_path):
    ctx = make_conflict(
        tmp_path,
        {
            I18N_PATH: (
                _i18n(['"a.one": "A",']),
                _i18n(['"a.one": "A",', '"m.ours": "Ours",']),
                _i18n(['"a.one": "A",', '"b.theirs": "Theirs",']),
            )
        },
    )
    resolution = i18n_locales.resolve(ctx, I18N_PATH)
    assert '"b.theirs": "Theirs",' in resolution.text
    assert '"m.ours": "Ours",' in resolution.text
    assert resolution.text.index('"b.theirs"') < resolution.text.index('"m.ours"')
    assert "<<<<<<<" not in resolution.text


def test_i18n_refuses_when_both_sides_translate_the_same_key(tmp_path):
    ctx = make_conflict(
        tmp_path,
        {
            I18N_PATH: (
                _i18n(['"a.one": "A",']),
                _i18n(['"a.one": "A",', '"z.same": "Ours",']),
                _i18n(['"a.one": "A",', '"z.same": "Theirs",']),
            )
        },
    )
    with pytest.raises(Refusal, match="translation conflict"):
        i18n_locales.resolve(ctx, I18N_PATH)


def test_i18n_refuses_non_entry_lines(tmp_path):
    ctx = make_conflict(
        tmp_path,
        {
            I18N_PATH: (
                _i18n(['"a.one": "A",']),
                _i18n(['"a.one": "A",', "...spreadOurs,"]),
                _i18n(['"a.one": "A",', '"b.theirs": "Theirs",']),
            )
        },
    )
    with pytest.raises(Refusal, match="not a flat entry line"):
        i18n_locales.resolve(ctx, I18N_PATH)


def test_i18n_is_a_no_op_without_conflict_markers(tmp_path):
    ctx = make_conflict(
        tmp_path,
        {
            I18N_PATH: (
                _i18n(['"a.one": "A",']),
                _i18n(['"a.one": "A",', '"m.ours": "Ours",']),
                _i18n(['"a.one": "A",', '"b.theirs": "Theirs",']),
            )
        },
    )
    clean = _i18n(['"a.one": "A",'])
    (ctx.repo_root / I18N_PATH).write_text(clean, encoding="utf-8")
    resolution = i18n_locales.resolve(ctx, I18N_PATH)
    assert resolution.text == clean
    assert resolution.detail == "no conflict markers"


# ---------------------------------------------------------------------------
# bundle size budget
# ---------------------------------------------------------------------------

BUDGET_PATH = "apps/dsa-web/scripts/bundle-size-budget.json"


def _budget(rules: list[dict], note: str = "base note") -> str:
    return (
        json.dumps(
            {
                "version": 1,
                "baselineNote": note,
                "outDir": "../../static",
                "gzipLevel": 9,
                "defaults": {"jsMaxGzipBytes": 100, "cssMaxGzipBytes": 100},
                "rules": rules,
            },
            indent=2,
        )
        + "\n"
    )


def _rule(rule_id: str, maximum: int, measured: int) -> dict:
    return {
        "id": rule_id,
        "match": f"assets/{rule_id}-*.js",
        "maxGzipBytes": maximum,
        "measuredGzipBytes": measured,
    }


def test_budget_merges_disjoint_rule_changes(tmp_path):
    base = [_rule("alpha", 100, 90), _rule("beta", 200, 180)]
    ours = [_rule("alpha", 150, 140), _rule("beta", 200, 180)]
    theirs = [_rule("alpha", 100, 90), _rule("beta", 260, 250)]
    # Both sides also rewrite the provenance note, which is what actually makes
    # git report a conflict when the changed rules are far apart in the file.
    ctx = make_conflict(
        tmp_path,
        {
            BUDGET_PATH: (
                _budget(base),
                _budget(ours, "main note"),
                _budget(theirs, "branch note"),
            )
        },
    )
    merged = json.loads(bundle_budget.resolve(ctx, BUDGET_PATH).text)
    by_id = {rule["id"]: rule for rule in merged["rules"]}
    assert by_id["alpha"]["maxGzipBytes"] == 150
    assert by_id["beta"]["maxGzipBytes"] == 260


def test_budget_refuses_when_both_sides_change_the_same_rule(tmp_path):
    base = [_rule("alpha", 100, 90)]
    ours = [_rule("alpha", 150, 140)]
    theirs = [_rule("alpha", 130, 120)]
    ctx = make_conflict(
        tmp_path, {BUDGET_PATH: (_budget(base), _budget(ours), _budget(theirs))}
    )
    with pytest.raises(Refusal, match="both sides changed the gzip numbers"):
        bundle_budget.resolve(ctx, BUDGET_PATH)


def test_budget_does_not_silently_take_the_larger_value(tmp_path):
    """The larger number is not the merged size; refusing is the contract."""

    base = [_rule("alpha", 100, 90)]
    ours = [_rule("alpha", 150, 140)]
    theirs = [_rule("alpha", 130, 120)]
    ctx = make_conflict(
        tmp_path, {BUDGET_PATH: (_budget(base), _budget(ours), _budget(theirs))}
    )
    with pytest.raises(Refusal):
        bundle_budget.resolve(ctx, BUDGET_PATH)
    on_disk = (ctx.repo_root / BUDGET_PATH).read_text(encoding="utf-8")
    assert "<<<<<<<" in on_disk, "the conflicted file must be left untouched"


def test_budget_refuses_a_match_glob_changed_on_both_sides(tmp_path):
    base = [_rule("alpha", 100, 90)]
    ours = [dict(_rule("alpha", 100, 90), match="assets/ours-*.js")]
    theirs = [dict(_rule("alpha", 100, 90), match="assets/theirs-*.js")]
    ctx = make_conflict(
        tmp_path, {BUDGET_PATH: (_budget(base), _budget(ours), _budget(theirs))}
    )
    with pytest.raises(Refusal, match="field 'match' was changed on both sides"):
        bundle_budget.resolve(ctx, BUDGET_PATH)


def test_budget_refuses_a_rule_deleted_on_one_side(tmp_path):
    base = [_rule("alpha", 100, 90), _rule("beta", 200, 180)]
    ours = [_rule("alpha", 100, 90)]
    theirs = [_rule("alpha", 100, 90), _rule("beta", 260, 250)]
    ctx = make_conflict(
        tmp_path, {BUDGET_PATH: (_budget(base), _budget(ours), _budget(theirs))}
    )
    with pytest.raises(Refusal, match="deleted"):
        bundle_budget.resolve(ctx, BUDGET_PATH)


def test_budget_keeps_first_match_ordering_for_an_incoming_rule(tmp_path):
    base = [_rule("alpha", 100, 90), _rule("omega", 300, 280)]
    ours = [_rule("alpha", 150, 140), _rule("omega", 300, 280)]
    theirs = [
        _rule("alpha", 100, 90),
        _rule("inserted", 120, 110),
        _rule("omega", 300, 280),
    ]
    ctx = make_conflict(
        tmp_path,
        {
            BUDGET_PATH: (
                _budget(base),
                _budget(ours, "main note"),
                _budget(theirs, "branch note"),
            )
        },
    )
    merged = json.loads(bundle_budget.resolve(ctx, BUDGET_PATH).text)
    assert [rule["id"] for rule in merged["rules"]] == ["alpha", "inserted", "omega"]


def test_budget_combines_provenance_notes(tmp_path):
    base = [_rule("alpha", 100, 90)]
    ctx = make_conflict(
        tmp_path,
        {
            BUDGET_PATH: (
                _budget(base, "base note"),
                _budget([_rule("alpha", 150, 140)], "main note"),
                _budget(base, "branch note"),
            )
        },
    )
    merged = json.loads(bundle_budget.resolve(ctx, BUDGET_PATH).text)
    assert "main note" in merged["baselineNote"]
    assert "branch note" in merged["baselineNote"]


def test_budget_refuses_invalid_json(tmp_path):
    ctx = make_conflict(
        tmp_path,
        {
            BUDGET_PATH: (
                _budget([_rule("alpha", 100, 90)]),
                "{not json at all\n",
                _budget([_rule("alpha", 130, 120)]),
            )
        },
    )
    with pytest.raises(Refusal, match="not valid JSON"):
        bundle_budget.resolve(ctx, BUDGET_PATH)


# ---------------------------------------------------------------------------
# docs index
# ---------------------------------------------------------------------------


def _index_doc(rows: list[str]) -> str:
    header = "# Index\n\n| Document | Contents |\n| --- | --- |\n"
    return header + "".join(f"{row}\n" for row in rows)


def test_docs_index_unions_appended_rows(tmp_path):
    base = ["| [a](a.md) | A |"]
    ours = base + ["| [main](main.md) | Main |"]
    theirs = base + ["| [branch](branch.md) | Branch |"]
    ctx = make_conflict(
        tmp_path,
        {
            docs_index.CHINESE_INDEX: (
                _index_doc(base),
                _index_doc(ours),
                _index_doc(theirs),
            )
        },
    )
    resolution = docs_index.resolve(ctx, docs_index.CHINESE_INDEX)
    assert "[main](main.md)" in resolution.text
    assert "[branch](branch.md)" in resolution.text
    assert "<<<<<<<" not in resolution.text


def test_docs_index_refuses_prose_inside_a_hunk(tmp_path):
    base = ["| [a](a.md) | A |"]
    ctx = make_conflict(
        tmp_path,
        {
            docs_index.CHINESE_INDEX: (
                _index_doc(base),
                _index_doc(base + ["Some prose, not a row."]),
                _index_doc(base + ["| [branch](branch.md) | Branch |"]),
            )
        },
    )
    with pytest.raises(Refusal, match="non-table line"):
        docs_index.resolve(ctx, docs_index.CHINESE_INDEX)


def test_docs_index_refuses_same_entry_edited_on_both_sides(tmp_path):
    base = ["| [a](a.md) | A |"]
    ctx = make_conflict(
        tmp_path,
        {
            docs_index.CHINESE_INDEX: (
                _index_doc(base),
                _index_doc(base + ["| [same](same.md) | Ours |"]),
                _index_doc(base + ["| [same](same.md) | Theirs |"]),
            )
        },
    )
    with pytest.raises(Refusal, match="edit conflict"):
        docs_index.resolve(ctx, docs_index.CHINESE_INDEX)


def test_docs_index_refuses_unbalanced_bilingual_pair(tmp_path):
    base = ["| [a](a.md) | A |"]
    files = {
        docs_index.CHINESE_INDEX: (
            _index_doc(base),
            _index_doc(base + ["| [main](main.md) | Main |"]),
            _index_doc(base + ["| [branch](branch.md) | Branch |"]),
        ),
        docs_index.ENGLISH_INDEX: (
            _index_doc(base),
            _index_doc(base + ["| [main](main.md) | Main |"]),
            _index_doc(
                base
                + [
                    "| [branch](branch.md) | Branch |",
                    "| [extra](extra.md) | Extra |",
                ]
            ),
        ),
    }
    ctx = make_conflict(tmp_path, files)
    resolutions = {
        path: docs_index.resolve(ctx, path)
        for path in (docs_index.CHINESE_INDEX, docs_index.ENGLISH_INDEX)
    }
    with pytest.raises(Refusal, match="bilingual documentation index"):
        docs_index.validate_batch(ctx, resolutions)


def test_docs_index_accepts_balanced_bilingual_pair(tmp_path):
    base = ["| [a](a.md) | A |"]
    pair = (
        _index_doc(base),
        _index_doc(base + ["| [main](main.md) | Main |"]),
        _index_doc(base + ["| [branch](branch.md) | Branch |"]),
    )
    ctx = make_conflict(
        tmp_path,
        {docs_index.CHINESE_INDEX: pair, docs_index.ENGLISH_INDEX: pair},
    )
    resolutions = {
        path: docs_index.resolve(ctx, path)
        for path in (docs_index.CHINESE_INDEX, docs_index.ENGLISH_INDEX)
    }
    docs_index.validate_batch(ctx, resolutions)


# ---------------------------------------------------------------------------
# playground catalog count
# ---------------------------------------------------------------------------

CATALOG_PATH = playground_catalog.RELATIVE_PATH


def _catalog_test(count: int) -> str:
    return (
        "describe('playground catalog', () => {\n"
        "  it('counts entries', () => {\n"
        f"    expect(PLAYGROUND_CATALOG).toHaveLength({count});\n"
        "  });\n"
        "});\n"
    )


def test_catalog_uses_three_way_arithmetic_without_esbuild(tmp_path):
    ctx = make_conflict(
        tmp_path,
        {CATALOG_PATH: (_catalog_test(200), _catalog_test(203), _catalog_test(202))},
    )
    resolution = playground_catalog.resolve(ctx, CATALOG_PATH)
    assert "toHaveLength(205)" in resolution.text
    assert "arithmetic" in resolution.detail


def test_catalog_refuses_when_a_side_removed_entries(tmp_path):
    ctx = make_conflict(
        tmp_path,
        {CATALOG_PATH: (_catalog_test(200), _catalog_test(203), _catalog_test(198))},
    )
    with pytest.raises(Refusal, match="lowered the catalog count"):
        playground_catalog.resolve(ctx, CATALOG_PATH)


def test_catalog_refuses_when_the_hunk_carries_other_changes(tmp_path):
    ours = _catalog_test(203).replace("counts entries", "counts entries (ours)")
    theirs = _catalog_test(202).replace("counts entries", "counts entries (theirs)")
    ctx = make_conflict(
        tmp_path, {CATALOG_PATH: (_catalog_test(200), ours, theirs)}
    )
    with pytest.raises(Refusal, match="more than the toHaveLength"):
        playground_catalog.resolve(ctx, CATALOG_PATH)


def test_catalog_is_a_no_op_without_conflict_markers(tmp_path):
    ctx = make_conflict(
        tmp_path,
        {CATALOG_PATH: (_catalog_test(200), _catalog_test(203), _catalog_test(202))},
    )
    (ctx.repo_root / CATALOG_PATH).write_text(_catalog_test(200), encoding="utf-8")
    resolution = playground_catalog.resolve(ctx, CATALOG_PATH)
    assert resolution.detail == "no conflict markers"


# ---------------------------------------------------------------------------
# settings help catalogue
# ---------------------------------------------------------------------------

HELP_PATH = "apps/dsa-web/src/locales/settingsHelp.en.ts"


def _help_file(blocks: list[str]) -> str:
    return "const settingsHelpEnUS = {\n" + "".join(blocks) + "};\n"


def _help_block(key: str, title: str) -> str:
    return f"  '{key}': {{\n    title: '{title}',\n  }},\n"


def test_settings_help_unions_both_sides_blocks(tmp_path):
    base = [_help_block("settings.a", "A")]
    ctx = make_conflict(
        tmp_path,
        {
            HELP_PATH: (
                _help_file(base),
                _help_file(base + [_help_block("settings.ours", "Ours")]),
                _help_file(base + [_help_block("settings.theirs", "Theirs")]),
            )
        },
    )
    resolution = settings_help.resolve(ctx, HELP_PATH)
    assert "settings.ours" in resolution.text
    assert "settings.theirs" in resolution.text
    assert "<<<<<<<" not in resolution.text


def test_settings_help_refuses_same_key_with_different_bodies(tmp_path):
    base = [_help_block("settings.a", "A")]
    ctx = make_conflict(
        tmp_path,
        {
            HELP_PATH: (
                _help_file(base),
                _help_file(
                    base
                    + [
                        _help_block("settings.ours", "Ours"),
                        _help_block("settings.same", "Ours"),
                    ]
                ),
                _help_file(
                    base
                    + [
                        _help_block("settings.theirs", "Theirs"),
                        _help_block("settings.same", "Theirs"),
                    ]
                ),
            )
        },
    )
    with pytest.raises(Refusal, match="edit conflict"):
        settings_help.resolve(ctx, HELP_PATH)


def test_settings_help_merges_a_hunk_cut_inside_the_appended_block(tmp_path):
    """Replicates the real shape from pull request #1185.

    Git cuts the hunk at the first differing line inside the appended block, so
    both sides end mid-block and share the closing brace that follows.
    """

    conflicted = (
        "const settingsHelpEnUS = {\n"
        "  'settings.a': {\n    title: 'A',\n  },\n"
        "<<<<<<< HEAD\n"
        "  'settings.ours': {\n    title: 'Ours',\n"
        "=======\n"
        "  'settings.theirs': {\n    title: 'Theirs',\n    summary: 'S',\n"
        ">>>>>>> branch\n"
        "  },\n"
        "};\n"
    )
    ctx = make_conflict(
        tmp_path,
        {HELP_PATH: ("const settingsHelpEnUS = {\n};\n", "a\n", "b\n")},
    )
    (ctx.repo_root / HELP_PATH).write_text(conflicted, encoding="utf-8")
    text = settings_help.resolve(ctx, HELP_PATH).text
    assert "<<<<<<<" not in text
    assert text.count("  },\n") == 3
    assert text.index("settings.ours") < text.index("settings.theirs")


def test_settings_help_refuses_when_only_one_side_ends_mid_block(tmp_path):
    conflicted = (
        "const settingsHelpEnUS = {\n"
        "<<<<<<< HEAD\n"
        "  'settings.ours': {\n    title: 'Ours',\n"
        "=======\n"
        "  'settings.theirs': {\n    title: 'Theirs',\n  },\n"
        ">>>>>>> branch\n"
        "  },\n"
        "};\n"
    )
    ctx = make_conflict(
        tmp_path,
        {HELP_PATH: ("const settingsHelpEnUS = {\n};\n", "a\n", "b\n")},
    )
    (ctx.repo_root / HELP_PATH).write_text(conflicted, encoding="utf-8")
    with pytest.raises(Refusal, match="only one side ends inside an entry block"):
        settings_help.resolve(ctx, HELP_PATH)


def test_settings_help_refuses_unexpected_lines(tmp_path):
    base = [_help_block("settings.a", "A")]
    ctx = make_conflict(
        tmp_path,
        {
            HELP_PATH: (
                _help_file(base),
                _help_file(base + ["  ...spreadOurs,\n"]),
                _help_file(base + [_help_block("settings.theirs", "Theirs")]),
            )
        },
    )
    with pytest.raises(Refusal, match="not a settings-help entry block"):
        settings_help.resolve(ctx, HELP_PATH)


# ---------------------------------------------------------------------------
# public-surface snapshot structure checks
# ---------------------------------------------------------------------------

SURFACE_PATH = "tests/agent/test_agent_orchestrator_public_surface.py"

_SURFACE_TEMPLATE = '''\
import importlib

EXPECTED_AST_HASHES = {{
    "_Methods": "{digest}",
}}


def _container_ast_hash(container):
    return ""


def test_surface():
    module = importlib.import_module("src.agent.orchestrator")
    assert {{"_Methods": _container_ast_hash(module._Methods)}} == EXPECTED_AST_HASHES
{extra}'''


def _surface(digest: str, extra: str = "") -> str:
    return _SURFACE_TEMPLATE.format(digest=digest, extra=extra)


def test_public_surface_refuses_structural_differences(tmp_path):
    ctx = make_conflict(
        tmp_path,
        {
            SURFACE_PATH: (
                _surface("0" * 64),
                _surface("1" * 64, extra="\n\ndef test_ours():\n    assert True\n"),
                _surface("2" * 64, extra="\n\ndef test_theirs():\n    assert False\n"),
            )
        },
    )
    with pytest.raises(Refusal, match="differ outside the EXPECTED_"):
        public_surface.resolve(ctx, SURFACE_PATH)


def test_public_surface_refuses_unparsable_side(tmp_path):
    ctx = make_conflict(
        tmp_path,
        {
            SURFACE_PATH: (
                _surface("0" * 64),
                _surface("1" * 64, extra="\ndef broken(:\n"),
                _surface("2" * 64, extra="\ndef fine():\n    pass\n"),
            )
        },
    )
    with pytest.raises(Refusal, match="does not parse as Python"):
        public_surface.resolve(ctx, SURFACE_PATH)


def test_public_surface_is_a_no_op_without_conflict_markers(tmp_path):
    ctx = make_conflict(
        tmp_path,
        {
            SURFACE_PATH: (
                _surface("0" * 64),
                _surface("1" * 64),
                _surface("2" * 64),
            )
        },
    )
    clean = _surface("0" * 64)
    (ctx.repo_root / SURFACE_PATH).write_text(clean, encoding="utf-8")
    resolution = public_surface.resolve(ctx, SURFACE_PATH)
    assert resolution.detail == "no conflict markers"


def test_public_surface_renders_a_sorted_wrapped_export_block():
    rendered = public_surface._render_exports(["Alpha", "Beta", "Gamma"])
    assert rendered.startswith("EXPECTED_PUBLIC_EXPORTS = frozenset(")
    assert "Alpha Beta Gamma" in rendered
    assert rendered.rstrip().endswith(")")
    for line in rendered.split("\n"):
        assert len(line) <= 79


def test_public_surface_does_not_claim_the_config_registry_snapshot():
    assert not public_surface.matches(
        "tests/core/test_config_registry_public_exports.py"
    )


# ---------------------------------------------------------------------------
# batch entry point
# ---------------------------------------------------------------------------


def test_batch_writes_nothing_when_one_file_is_refused(tmp_path, monkeypatch, capsys):
    files = {
        I18N_PATH: (
            _i18n(['"a.one": "A",']),
            _i18n(['"a.one": "A",', '"m.ours": "Ours",']),
            _i18n(['"a.one": "A",', '"b.theirs": "Theirs",']),
        ),
        BUDGET_PATH: (
            _budget([_rule("alpha", 100, 90)]),
            _budget([_rule("alpha", 150, 140)]),
            _budget([_rule("alpha", 130, 120)]),
        ),
    }
    ctx = make_conflict(tmp_path, files)
    monkeypatch.chdir(ctx.repo_root)

    exit_code = resolve_entry.main([I18N_PATH, BUDGET_PATH])
    assert exit_code == resolve_entry.EXIT_REFUSED

    for rel_path in files:
        assert "<<<<<<<" in (ctx.repo_root / rel_path).read_text(encoding="utf-8")
    unmerged = _git(
        ctx.repo_root, "diff", "--name-only", "--diff-filter=U"
    ).stdout.split()
    assert sorted(unmerged) == sorted(files)
    captured = capsys.readouterr()
    assert "REFUSED, nothing was written" in captured.err
    assert "would have resolved" in captured.err


def test_batch_writes_and_stages_when_every_file_resolves(tmp_path, monkeypatch):
    files = {
        I18N_PATH: (
            _i18n(['"a.one": "A",']),
            _i18n(['"a.one": "A",', '"m.ours": "Ours",']),
            _i18n(['"a.one": "A",', '"b.theirs": "Theirs",']),
        )
    }
    ctx = make_conflict(tmp_path, files)
    monkeypatch.chdir(ctx.repo_root)

    assert resolve_entry.main([I18N_PATH]) == resolve_entry.EXIT_OK
    text = (ctx.repo_root / I18N_PATH).read_text(encoding="utf-8")
    assert "<<<<<<<" not in text
    assert '"m.ours"' in text and '"b.theirs"' in text
    assert not _git(ctx.repo_root, "diff", "--name-only", "--diff-filter=U").stdout


def test_batch_refuses_files_without_a_resolver(tmp_path, monkeypatch, capsys):
    files = {
        "src/some_module.py": ("base = 1\n", "base = 2\n", "base = 3\n"),
    }
    ctx = make_conflict(tmp_path, files)
    monkeypatch.chdir(ctx.repo_root)

    assert resolve_entry.main(["src/some_module.py"]) == resolve_entry.EXIT_REFUSED
    assert "no resolver for this file" in capsys.readouterr().err


def test_batch_dry_run_writes_nothing(tmp_path, monkeypatch):
    files = {
        I18N_PATH: (
            _i18n(['"a.one": "A",']),
            _i18n(['"a.one": "A",', '"m.ours": "Ours",']),
            _i18n(['"a.one": "A",', '"b.theirs": "Theirs",']),
        )
    }
    ctx = make_conflict(tmp_path, files)
    monkeypatch.chdir(ctx.repo_root)

    assert resolve_entry.main([I18N_PATH, "--dry-run"]) == resolve_entry.EXIT_OK
    assert "<<<<<<<" in (ctx.repo_root / I18N_PATH).read_text(encoding="utf-8")


def test_batch_list_reports_every_resolver(capsys):
    assert resolve_entry.main(["--list"]) == resolve_entry.EXIT_OK
    out = capsys.readouterr().out
    for module in resolve_entry.RESOLVERS:
        assert module.NAME in out


def test_rebaseline_collateral_requires_remeasure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        resolve_entry.main(["--rebaseline-collateral", "some/file"])
