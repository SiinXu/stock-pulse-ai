#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Three-way configuration source consistency check.

Compares configuration keys across:

1. ``.env.example`` (template defaults and documented assignment lines)
2. Configuration registry (``src/core/config_registry_parts/`` via
   ``get_registered_field_keys()``)
3. Documentation inventory tables in
   ``docs/environment-variables.md`` and ``docs/environment-variables_EN.md``

Reports three gap classes (always printed):

- **missing_from_docs**: present in ``.env.example`` but absent from one or both
  inventory documents
- **missing_from_env**: present in inventory docs or the registry but absent from
  ``.env.example``
- **missing_from_registry**: present in ``.env.example`` but not explicitly
  registered (informational by default; Task 1 / registry workers own fixes)

Also reports:

- **cn_en_mismatch**: keys present in only one language inventory
- **default_mismatch**: inventory default cells that disagree with
  ``.env.example`` (when the cell is a concrete default, not a placeholder)

Exit codes:

- ``0`` when no selected failure classes fire
- ``1`` when a selected failure class has findings
- ``2`` on usage / I/O / parse errors

Failure classes default to ``docs,env,cn_en,defaults`` so registry debt does not
block documentation PRs. Pass ``--fail-on registry`` (or ``all``) to enforce
registry coverage as well.

Usage:

```bash
python scripts/check_config_doc_consistency.py
python scripts/check_config_doc_consistency.py --json
python scripts/check_config_doc_consistency.py --write-inventory
python scripts/check_config_doc_consistency.py --self-test
```
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_EXAMPLE = ROOT / ".env.example"
DEFAULT_DOC_CN = ROOT / "docs" / "environment-variables.md"
DEFAULT_DOC_EN = ROOT / "docs" / "environment-variables_EN.md"

INVENTORY_START = "<!-- config-env-inventory:start -->"
INVENTORY_END = "<!-- config-env-inventory:end -->"

# Documented KEY= lines count whether active or commented (leading '#').
ENV_ASSIGNMENT_RE = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=(.*)$")
# Active (uncommented) assignment only.
ACTIVE_ENV_ASSIGNMENT_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
# Inventory table row: | `KEY` | default | registered | notes |
INVENTORY_ROW_RE = re.compile(
    r"^\|\s*`([A-Z][A-Z0-9_]*)`\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|\s*$"
)
# Placeholder defaults that do not claim a concrete value.
PLACEHOLDER_DEFAULTS = frozenset(
    {
        "",
        "-",
        "—",
        "–",
        "empty",
        "Empty",
        "空",
        "none",
        "None",
        "see .env.example",
        "See .env.example",
        "见 .env.example",
        "见 `.env.example`",
    }
)

FAIL_CLASS_DOCS = "docs"
FAIL_CLASS_ENV = "env"
FAIL_CLASS_REGISTRY = "registry"
FAIL_CLASS_CN_EN = "cn_en"
FAIL_CLASS_DEFAULTS = "defaults"
ALL_FAIL_CLASSES = (
    FAIL_CLASS_DOCS,
    FAIL_CLASS_ENV,
    FAIL_CLASS_REGISTRY,
    FAIL_CLASS_CN_EN,
    FAIL_CLASS_DEFAULTS,
)
DEFAULT_FAIL_ON = frozenset(
    {FAIL_CLASS_DOCS, FAIL_CLASS_ENV, FAIL_CLASS_CN_EN, FAIL_CLASS_DEFAULTS}
)


@dataclass(frozen=True)
class EnvEntry:
    """One assignment line from ``.env.example``."""

    key: str
    default: str
    active: bool
    description: str = ""


@dataclass
class ConsistencyReport:
    """Structured three-way consistency result."""

    env_keys: List[str] = field(default_factory=list)
    registry_keys: List[str] = field(default_factory=list)
    doc_cn_keys: List[str] = field(default_factory=list)
    doc_en_keys: List[str] = field(default_factory=list)
    missing_from_docs: List[str] = field(default_factory=list)
    missing_from_docs_cn: List[str] = field(default_factory=list)
    missing_from_docs_en: List[str] = field(default_factory=list)
    missing_from_env: List[str] = field(default_factory=list)
    missing_from_registry: List[str] = field(default_factory=list)
    cn_en_mismatch: List[str] = field(default_factory=list)
    default_mismatch: List[Dict[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def has_findings(self, classes: Iterable[str]) -> bool:
        selected = set(classes)
        if FAIL_CLASS_DOCS in selected and self.missing_from_docs:
            return True
        if FAIL_CLASS_ENV in selected and self.missing_from_env:
            return True
        if FAIL_CLASS_REGISTRY in selected and self.missing_from_registry:
            return True
        if FAIL_CLASS_CN_EN in selected and self.cn_en_mismatch:
            return True
        if FAIL_CLASS_DEFAULTS in selected and self.default_mismatch:
            return True
        return False


def _strip_inline_comment(value: str) -> str:
    """Return the assignment value without a trailing `` # comment`` segment."""

    text = value.strip()
    if not text:
        return ""
    if text.startswith("#"):
        return ""
    if " #" in text:
        return text.split(" #", 1)[0].strip()
    return text


def parse_env_example(path: Path) -> Dict[str, EnvEntry]:
    """Parse ``.env.example`` into unique key entries.

    When a key appears more than once, the last assignment wins (mirrors common
    dotenv override behaviour and matches how operators read the template).
    Leading comment lines immediately above an assignment are joined into
    ``description``.
    """

    if not path.is_file():
        raise FileNotFoundError(f".env.example not found: {path}")

    entries: Dict[str, EnvEntry] = {}
    pending_comments: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            pending_comments = []
            continue

        match = ENV_ASSIGNMENT_RE.match(stripped)
        if match:
            key = match.group(1)
            raw_value = match.group(2)
            default = _strip_inline_comment(raw_value)
            active = ACTIVE_ENV_ASSIGNMENT_RE.match(stripped) is not None
            inline = ""
            if " #" in raw_value:
                inline = raw_value.split(" #", 1)[1].strip()
            elif raw_value.strip().startswith("#"):
                inline = raw_value.strip().lstrip("#").strip()
            description = " ".join(pending_comments).strip()
            if inline:
                description = f"{description} {inline}".strip() if description else inline
            entries[key] = EnvEntry(
                key=key,
                default=default,
                active=active,
                description=description,
            )
            pending_comments = []
            continue

        if stripped.startswith("#"):
            comment = stripped.lstrip("#").strip()
            if comment:
                pending_comments.append(comment)
            continue

        pending_comments = []

    return entries


def load_registry_keys(root: Path = ROOT) -> Set[str]:
    """Load explicitly registered configuration keys.

    Prefers the public registry API. Falls back to a static parse of
    ``config_registry_parts`` when imports fail (keeps the checker usable in
    minimal environments).
    """

    src_root = str(root)
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    try:
        from src.core.config_registry import get_registered_field_keys

        return set(get_registered_field_keys())
    except Exception as exc:  # noqa: BLE001 - intentional offline fallback
        keys = _parse_registry_keys_static(root / "src" / "core" / "config_registry_parts")
        if not keys:
            raise RuntimeError(
                f"Unable to load configuration registry keys via import or static parse: {exc}"
            ) from exc
        return keys


def _parse_registry_keys_static(parts_dir: Path) -> Set[str]:
    """Heuristic parse of ``"KEY": {`` entries inside registry part modules."""

    keys: Set[str] = set()
    if not parts_dir.is_dir():
        return keys
    key_re = re.compile(r'^\s*"([A-Z][A-Z0-9_]*)"\s*:\s*\{', re.MULTILINE)
    for path in sorted(parts_dir.glob("*.py")):
        if path.name in {"__init__.py", "catalog.py", "help_metadata.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        keys.update(key_re.findall(text))
    return keys


def parse_inventory_table(path: Path) -> Dict[str, Dict[str, str]]:
    """Parse the machine-checked inventory table from a documentation file.

    Returns ``key -> {default, registered, notes}``. Raises ``ValueError`` when
    the inventory markers are missing or unbalanced.
    """

    if not path.is_file():
        raise FileNotFoundError(f"Inventory document not found: {path}")

    text = path.read_text(encoding="utf-8")
    start = text.find(INVENTORY_START)
    end = text.find(INVENTORY_END)
    if start < 0 or end < 0 or end <= start:
        raise ValueError(
            f"{path}: missing or unbalanced inventory markers "
            f"({INVENTORY_START!r} / {INVENTORY_END!r})"
        )

    block = text[start + len(INVENTORY_START) : end]
    rows: Dict[str, Dict[str, str]] = {}
    for line in block.splitlines():
        match = INVENTORY_ROW_RE.match(line.strip())
        if not match:
            continue
        key = match.group(1)
        rows[key] = {
            "default": match.group(2).strip().strip("`"),
            "registered": match.group(3).strip().lower(),
            "notes": match.group(4).strip(),
        }
    return rows


def _normalize_default_cell(value: str) -> str:
    return value.strip().strip("`").strip()


def _is_placeholder_default(value: str) -> bool:
    normalized = _normalize_default_cell(value)
    if normalized in PLACEHOLDER_DEFAULTS:
        return True
    if normalized.lower() in {"optional", "可选", "推荐", "recommended", "required", "必填"}:
        return True
    return False


def _escape_table_cell(value: str) -> str:
    """Escape pipe characters so Markdown tables stay well-formed."""

    return value.replace("|", "\\|").replace("\n", " ").strip()


def render_inventory_table(
    env_entries: Mapping[str, EnvEntry],
    registry_keys: Set[str],
    *,
    locale: str,
) -> str:
    """Render the machine-checked inventory Markdown table body."""

    yes = "yes" if locale == "en" else "是"
    no = "no" if locale == "en" else "否"
    header = (
        "| Key | Default (``.env.example``) | Registered | Notes |\n"
        "|-----|----------------------------|------------|-------|\n"
        if locale == "en"
        else "| 键名 | 默认值（``.env.example``） | 已注册 | 备注 |\n"
        "|------|---------------------------|--------|------|\n"
    )
    lines = [header.rstrip("\n")]
    for key in sorted(env_entries):
        entry = env_entries[key]
        default = entry.default if entry.default else ("empty" if locale == "en" else "空")
        registered = yes if key in registry_keys else no
        notes_parts: List[str] = []
        if not entry.active:
            notes_parts.append("commented template" if locale == "en" else "模板中注释")
        if key not in registry_keys:
            notes_parts.append(
                "registry gap (see issue #1026)"
                if locale == "en"
                else "注册表缺口（见 issue #1026）"
            )
        if entry.description and key in registry_keys:
            short = entry.description.split(". ")[0].strip()
            if len(short) > 120:
                short = short[:117] + "..."
            notes_parts.append(short)
        notes = "; ".join(notes_parts)
        lines.append(
            f"| `{key}` | `{_escape_table_cell(default)}` | {registered} | "
            f"{_escape_table_cell(notes)} |"
        )
    return "\n".join(lines) + "\n"


def replace_inventory_block(path: Path, table_body: str) -> None:
    """Replace the inventory table between markers, preserving surrounding prose."""

    text = path.read_text(encoding="utf-8")
    start = text.find(INVENTORY_START)
    end = text.find(INVENTORY_END)
    if start < 0 or end < 0 or end <= start:
        raise ValueError(f"{path}: missing inventory markers; cannot write")
    new_text = (
        text[: start + len(INVENTORY_START)]
        + "\n\n"
        + table_body.rstrip()
        + "\n\n"
        + text[end:]
    )
    path.write_text(new_text, encoding="utf-8")


def collect_report(
    *,
    root: Path = ROOT,
    env_path: Path = DEFAULT_ENV_EXAMPLE,
    doc_cn_path: Path = DEFAULT_DOC_CN,
    doc_en_path: Path = DEFAULT_DOC_EN,
    registry_keys: Optional[Set[str]] = None,
) -> ConsistencyReport:
    """Build a full consistency report for the three configuration sources."""

    env_entries = parse_env_example(env_path)
    env_keys = set(env_entries)
    if registry_keys is None:
        registry_keys = load_registry_keys(root)

    doc_cn = parse_inventory_table(doc_cn_path)
    doc_en = parse_inventory_table(doc_en_path)
    doc_cn_keys = set(doc_cn)
    doc_en_keys = set(doc_en)
    doc_keys = doc_cn_keys & doc_en_keys

    missing_from_docs_cn = sorted(env_keys - doc_cn_keys)
    missing_from_docs_en = sorted(env_keys - doc_en_keys)
    missing_from_docs = sorted(env_keys - doc_keys)

    missing_from_env = sorted((doc_cn_keys | doc_en_keys | registry_keys) - env_keys)

    missing_from_registry = sorted(env_keys - registry_keys)
    cn_en_mismatch = sorted(doc_cn_keys.symmetric_difference(doc_en_keys))

    default_mismatch: List[Dict[str, str]] = []
    for key in sorted(env_keys & doc_cn_keys & doc_en_keys):
        env_default = env_entries[key].default
        for locale, rows in (("cn", doc_cn), ("en", doc_en)):
            cell = rows[key]["default"]
            if _is_placeholder_default(cell):
                continue
            expected = env_default if env_default else ("empty" if locale == "en" else "空")
            if not env_default and _normalize_default_cell(cell) in {"empty", "空"}:
                continue
            if _normalize_default_cell(cell) != expected:
                default_mismatch.append(
                    {
                        "key": key,
                        "locale": locale,
                        "env_default": env_default,
                        "doc_default": _normalize_default_cell(cell),
                    }
                )

    notes: List[str] = []
    if missing_from_registry:
        notes.append(
            f"{len(missing_from_registry)} .env.example keys are not in the "
            "configuration registry (owned by registry registration tasks; "
            "this checker reports the gap and does not rewrite registry parts)."
        )

    return ConsistencyReport(
        env_keys=sorted(env_keys),
        registry_keys=sorted(registry_keys),
        doc_cn_keys=sorted(doc_cn_keys),
        doc_en_keys=sorted(doc_en_keys),
        missing_from_docs=missing_from_docs,
        missing_from_docs_cn=missing_from_docs_cn,
        missing_from_docs_en=missing_from_docs_en,
        missing_from_env=missing_from_env,
        missing_from_registry=missing_from_registry,
        cn_en_mismatch=cn_en_mismatch,
        default_mismatch=default_mismatch,
        notes=notes,
    )


def format_human_report(report: ConsistencyReport) -> str:
    """Render a human-readable report."""

    def _section(title: str, items: Sequence[str], limit: int = 40) -> List[str]:
        lines = [f"## {title} ({len(items)})"]
        if not items:
            lines.append("(none)")
            return lines
        for item in items[:limit]:
            lines.append(f"- `{item}`")
        if len(items) > limit:
            lines.append(f"- ... and {len(items) - limit} more")
        return lines

    lines: List[str] = [
        "# Configuration source consistency",
        "",
        f"- `.env.example` keys: {len(report.env_keys)}",
        f"- registry keys: {len(report.registry_keys)}",
        f"- docs CN inventory keys: {len(report.doc_cn_keys)}",
        f"- docs EN inventory keys: {len(report.doc_en_keys)}",
        "",
    ]
    lines.extend(_section("missing_from_docs (either language)", report.missing_from_docs))
    lines.append("")
    lines.extend(_section("missing_from_docs_cn", report.missing_from_docs_cn))
    lines.append("")
    lines.extend(_section("missing_from_docs_en", report.missing_from_docs_en))
    lines.append("")
    lines.extend(_section("missing_from_env", report.missing_from_env))
    lines.append("")
    lines.extend(_section("missing_from_registry", report.missing_from_registry))
    lines.append("")
    lines.extend(_section("cn_en_mismatch", report.cn_en_mismatch))
    lines.append("")
    lines.append(f"## default_mismatch ({len(report.default_mismatch)})")
    if not report.default_mismatch:
        lines.append("(none)")
    else:
        for item in report.default_mismatch[:40]:
            lines.append(
                f"- `{item['key']}` [{item['locale']}]: "
                f"env={item['env_default']!r} doc={item['doc_default']!r}"
            )
        if len(report.default_mismatch) > 40:
            lines.append(f"- ... and {len(report.default_mismatch) - 40} more")
    if report.notes:
        lines.append("")
        lines.append("## notes")
        for note in report.notes:
            lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def parse_fail_on(raw: str) -> Set[str]:
    """Parse ``--fail-on`` into a set of failure class names."""

    text = raw.strip().lower()
    if not text or text == "default":
        return set(DEFAULT_FAIL_ON)
    if text == "all":
        return set(ALL_FAIL_CLASSES)
    if text in {"none", "report-only", "report_only"}:
        return set()
    classes: Set[str] = set()
    for part in text.split(","):
        name = part.strip().lower()
        if not name:
            continue
        if name not in ALL_FAIL_CLASSES:
            raise ValueError(
                f"Unknown fail-on class {name!r}; "
                f"expected one of {', '.join(ALL_FAIL_CLASSES)}, all, none, default"
            )
        classes.add(name)
    return classes


def write_inventory_docs(
    *,
    root: Path = ROOT,
    env_path: Path = DEFAULT_ENV_EXAMPLE,
    doc_cn_path: Path = DEFAULT_DOC_CN,
    doc_en_path: Path = DEFAULT_DOC_EN,
    registry_keys: Optional[Set[str]] = None,
) -> None:
    """Regenerate inventory tables in both language documents."""

    env_entries = parse_env_example(env_path)
    if registry_keys is None:
        registry_keys = load_registry_keys(root)
    replace_inventory_block(
        doc_cn_path,
        render_inventory_table(env_entries, registry_keys, locale="zh"),
    )
    replace_inventory_block(
        doc_en_path,
        render_inventory_table(env_entries, registry_keys, locale="en"),
    )


def _self_test() -> None:
    """Offline fixture-based regressions (no repository tree required)."""

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        env_path = root / ".env.example"
        docs = root / "docs"
        docs.mkdir()
        doc_cn = docs / "environment-variables.md"
        doc_en = docs / "environment-variables_EN.md"

        env_path.write_text(
            "# Watchlist\n"
            "STOCK_LIST=600519\n"
            "# Optional feature\n"
            "# CRYPTO_PROVIDER_ENABLED=false\n"
            "REGISTERED_ONLY=1\n",
            encoding="utf-8",
        )

        skeleton = (
            "# Inventory\n\n"
            f"{INVENTORY_START}\n\n"
            "| Key | Default | Registered | Notes |\n"
            "|-----|---------|------------|-------|\n"
            "| `STOCK_LIST` | `600519` | yes | ok |\n"
            "\n"
            f"{INVENTORY_END}\n"
        )
        doc_cn.write_text(skeleton, encoding="utf-8")
        doc_en.write_text(skeleton, encoding="utf-8")

        registry = {"STOCK_LIST", "REGISTERED_ONLY", "ORPHAN_REGISTRY_KEY"}
        report = collect_report(
            root=root,
            env_path=env_path,
            doc_cn_path=doc_cn,
            doc_en_path=doc_en,
            registry_keys=registry,
        )
        assert "CRYPTO_PROVIDER_ENABLED" in report.missing_from_docs
        assert "REGISTERED_ONLY" in report.missing_from_docs
        assert "ORPHAN_REGISTRY_KEY" in report.missing_from_env
        assert "CRYPTO_PROVIDER_ENABLED" in report.missing_from_registry
        assert report.has_findings(DEFAULT_FAIL_ON)

        for path in (doc_cn, doc_en):
            path.write_text(
                "# Inventory\n\n"
                f"{INVENTORY_START}\n\n"
                f"{INVENTORY_END}\n",
                encoding="utf-8",
            )
        write_inventory_docs(
            root=root,
            env_path=env_path,
            doc_cn_path=doc_cn,
            doc_en_path=doc_en,
            registry_keys=registry,
        )
        report2 = collect_report(
            root=root,
            env_path=env_path,
            doc_cn_path=doc_cn,
            doc_en_path=doc_en,
            registry_keys=registry,
        )
        assert report2.missing_from_docs == []
        assert report2.cn_en_mismatch == []
        assert "ORPHAN_REGISTRY_KEY" in report2.missing_from_env
        assert "CRYPTO_PROVIDER_ENABLED" in report2.missing_from_registry
        assert report2.has_findings({FAIL_CLASS_ENV})
        assert not report2.has_findings({FAIL_CLASS_DOCS, FAIL_CLASS_CN_EN, FAIL_CLASS_DEFAULTS})

        env_entries = parse_env_example(env_path)
        body = render_inventory_table(env_entries, registry, locale="en")
        body = "\n".join(
            line for line in body.splitlines() if "CRYPTO_PROVIDER_ENABLED" not in line
        ) + "\n"
        replace_inventory_block(doc_en, body)
        report3 = collect_report(
            root=root,
            env_path=env_path,
            doc_cn_path=doc_cn,
            doc_en_path=doc_en,
            registry_keys=registry,
        )
        assert "CRYPTO_PROVIDER_ENABLED" in report3.cn_en_mismatch
        assert "CRYPTO_PROVIDER_ENABLED" in report3.missing_from_docs

        bad_default_body = render_inventory_table(env_entries, registry, locale="en").replace(
            "| `STOCK_LIST` | `600519` |",
            "| `STOCK_LIST` | `WRONG` |",
        )
        replace_inventory_block(doc_en, bad_default_body)
        report4 = collect_report(
            root=root,
            env_path=env_path,
            doc_cn_path=doc_cn,
            doc_en_path=doc_en,
            registry_keys=registry,
        )
        assert any(
            item["key"] == "STOCK_LIST" and item["locale"] == "en"
            for item in report4.default_mismatch
        )

        assert FAIL_CLASS_REGISTRY not in parse_fail_on("default")
        assert FAIL_CLASS_REGISTRY in parse_fail_on("all")
        assert parse_fail_on("none") == set()
        assert parse_fail_on("docs,env") == {FAIL_CLASS_DOCS, FAIL_CLASS_ENV}

        entries = parse_env_example(env_path)
        assert entries["STOCK_LIST"].description == "Watchlist"
        assert entries["CRYPTO_PROVIDER_ENABLED"].active is False
        assert entries["CRYPTO_PROVIDER_ENABLED"].default == "false"

    print("self-test: ok")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare .env.example, config registry, and docs inventory tables."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root (default: auto-detected)",
    )
    parser.add_argument(
        "--env-example",
        type=Path,
        default=None,
        help="Path to .env.example (default: <root>/.env.example)",
    )
    parser.add_argument(
        "--doc-cn",
        type=Path,
        default=None,
        help="Path to Chinese inventory doc",
    )
    parser.add_argument(
        "--doc-en",
        type=Path,
        default=None,
        help="Path to English inventory doc",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of Markdown text",
    )
    parser.add_argument(
        "--fail-on",
        default="default",
        help=(
            "Comma-separated failure classes: docs,env,registry,cn_en,defaults "
            "(or all / none / default). Default fails on docs/env/cn_en/defaults."
        ),
    )
    parser.add_argument(
        "--write-inventory",
        action="store_true",
        help="Rewrite inventory tables in both language docs from .env.example",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run offline fixture regressions and exit",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        try:
            _self_test()
        except AssertionError as exc:
            print(f"self-test failed: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"self-test error: {exc}", file=sys.stderr)
            return 2
        return 0

    root: Path = args.root.resolve()
    env_path = (args.env_example or (root / ".env.example")).resolve()
    doc_cn = (args.doc_cn or (root / "docs" / "environment-variables.md")).resolve()
    doc_en = (args.doc_en or (root / "docs" / "environment-variables_EN.md")).resolve()

    try:
        fail_on = parse_fail_on(args.fail_on)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        if args.write_inventory:
            write_inventory_docs(
                root=root,
                env_path=env_path,
                doc_cn_path=doc_cn,
                doc_en_path=doc_en,
            )
            print(f"Wrote inventory tables to {doc_cn} and {doc_en}")

        report = collect_report(
            root=root,
            env_path=env_path,
            doc_cn_path=doc_cn,
            doc_en_path=doc_en,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print(format_human_report(report), end="")

    if report.has_findings(fail_on):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
