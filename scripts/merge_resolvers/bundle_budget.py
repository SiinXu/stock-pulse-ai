"""Resolver for ``apps/dsa-web/scripts/bundle-size-budget.json``.

Why neither side is correct
---------------------------
The budget file records the gzip size of *every* production chunk of the whole
Web build. Any pull request that touches the frontend re-measures the chunks it
grows, so two pull requests almost always rewrite overlapping slots of the same
file. ``--ours`` drops the incoming measurement, ``--theirs`` drops main's, and
a line-level union produces invalid JSON.

The true post-merge value of a chunk that *both* sides grew is neither number:
it is the size of the chunk built from the merged tree, which is usually close
to ``base + (ours - base) + (theirs - base)``. This resolver never guesses that
number.

Refusal conditions (documented contract)
----------------------------------------
* any index stage missing (add/add, delete/modify);
* either stage is not valid JSON, or ``rules`` is not a list of objects with
  unique string ``id`` values;
* a rule id was removed on one side and kept/changed on the other;
* a rule's ``match`` glob differs on both sides (that is a routing change, not
  a measurement);
* a rule's ``maxGzipBytes`` / ``measuredGzipBytes`` were changed on **both**
  sides — unless ``--remeasure`` is passed, in which case the merged tree is
  actually built and measured;
* a top-level key other than the provenance keys ``baselineNote`` /
  ``measuredAt`` was changed on both sides to different values;
* a rule that is only present in the incoming side cannot be anchored into the
  merged ordering (ordering is semantic: ``check-bundle-size.mjs`` matches the
  first rule whose glob matches);
* under ``--remeasure``: any rule not involved in the conflict now exceeds its
  merged budget (a real regression a human must review).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .common import Context, Refusal, Resolution

RELATIVE_PATH = "apps/dsa-web/scripts/bundle-size-budget.json"
NUMERIC_FIELDS = ("maxGzipBytes", "measuredGzipBytes")
PROVENANCE_KEYS = ("baselineNote", "measuredAt")
DEFAULT_HEADROOM_BYTES = 200

NAME = "bundle-size-budget"
DESCRIPTION = "Merge gzip budget rules by id; refuse ambiguous same-rule numbers."


def matches(rel_path: str) -> bool:
    return rel_path == RELATIVE_PATH


def _load(path: str, label: str, text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Refusal(path, f"{label} stage is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise Refusal(path, f"{label} stage is not a JSON object")
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise Refusal(path, f"{label} stage has no rules array")
    ids: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
            raise Refusal(path, f"{label} stage has a rule without a string id")
        ids.append(rule["id"])
    if len(set(ids)) != len(ids):
        raise Refusal(path, f"{label} stage has duplicate rule ids")
    return data


def _index(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {rule["id"]: rule for rule in data["rules"]}


def _order(data: dict[str, Any]) -> list[str]:
    return [rule["id"] for rule in data["rules"]]


def _merge_scalar(path: str, key: str, base: Any, ours: Any, theirs: Any) -> Any:
    if ours == theirs:
        return ours
    if base == ours:
        return theirs
    if base == theirs:
        return ours
    if key == "measuredAt":
        return max(str(ours), str(theirs))
    if key == "baselineNote":
        if str(theirs) in str(ours):
            return ours
        if str(ours) in str(theirs):
            return theirs
        return f"{ours} Merged with: {theirs}"
    raise Refusal(
        path,
        f"top-level key {key!r} was changed on both sides to different values",
    )


def _merge_rule(
    path: str,
    rule_id: str,
    base: dict[str, Any] | None,
    ours: dict[str, Any],
    theirs: dict[str, Any],
    ambiguous: list[str],
) -> dict[str, Any]:
    if ours == theirs:
        return dict(ours)
    if base is not None and base == ours:
        return dict(theirs)
    if base is not None and base == theirs:
        return dict(ours)

    merged: dict[str, Any] = {}
    keys = list(ours) + [key for key in theirs if key not in ours]
    numeric_conflict = False
    for key in keys:
        base_value = (base or {}).get(key)
        our_value = ours.get(key)
        their_value = theirs.get(key)
        if key not in ours or key not in theirs:
            raise Refusal(
                path,
                f"rule {rule_id!r}: field {key!r} exists on only one side",
            )
        if our_value == their_value:
            merged[key] = our_value
            continue
        if base is not None and base_value == our_value:
            merged[key] = their_value
            continue
        if base is not None and base_value == their_value:
            merged[key] = our_value
            continue
        if key in NUMERIC_FIELDS:
            numeric_conflict = True
            merged[key] = max(our_value, their_value)
            continue
        if key == "note":
            merged[key] = our_value
            continue
        raise Refusal(
            path,
            f"rule {rule_id!r}: field {key!r} was changed on both sides "
            f"({our_value!r} vs {their_value!r})",
        )
    if numeric_conflict:
        ambiguous.append(rule_id)
    return merged


def _merge_order(
    path: str,
    base_order: list[str],
    our_order: list[str],
    their_order: list[str],
    merged_ids: set[str],
) -> list[str]:
    order = [rule_id for rule_id in our_order if rule_id in merged_ids]
    incoming = [
        rule_id
        for rule_id in their_order
        if rule_id in merged_ids and rule_id not in set(our_order)
    ]
    for rule_id in incoming:
        position = their_order.index(rule_id)
        anchor = None
        for candidate in reversed(their_order[:position]):
            if candidate in order:
                anchor = candidate
                break
        if anchor is None:
            order.insert(0, rule_id)
            continue
        order.insert(order.index(anchor) + 1, rule_id)
    if set(order) != merged_ids:
        raise Refusal(path, "could not reconstruct a total rule ordering")
    return order


def resolve(ctx: Context, rel_path: str) -> Resolution:
    base_text, our_text, their_text = ctx.require_stages(rel_path)
    base = _load(rel_path, "base", base_text)
    ours = _load(rel_path, "ours", our_text)
    theirs = _load(rel_path, "theirs", their_text)

    merged: dict[str, Any] = {}
    top_keys = list(ours) + [key for key in theirs if key not in ours]
    for key in top_keys:
        if key == "rules":
            merged[key] = []
            continue
        if key not in ours or key not in theirs:
            raise Refusal(rel_path, f"top-level key {key!r} exists on only one side")
        merged[key] = _merge_scalar(
            rel_path, key, base.get(key), ours[key], theirs[key]
        )

    base_rules, our_rules, their_rules = _index(base), _index(ours), _index(theirs)
    all_ids = set(our_rules) | set(their_rules)
    for rule_id in set(base_rules) - all_ids:
        raise Refusal(rel_path, f"rule {rule_id!r} was deleted; needs a human")
    for rule_id in all_ids:
        if rule_id in our_rules and rule_id in their_rules:
            continue
        present = "ours" if rule_id in our_rules else "theirs"
        if rule_id in base_rules:
            raise Refusal(
                rel_path,
                f"rule {rule_id!r} was deleted on one side and kept on {present}",
            )

    ambiguous: list[str] = []
    merged_rules: dict[str, dict[str, Any]] = {}
    for rule_id in all_ids:
        if rule_id in our_rules and rule_id in their_rules:
            merged_rules[rule_id] = _merge_rule(
                rel_path,
                rule_id,
                base_rules.get(rule_id),
                our_rules[rule_id],
                their_rules[rule_id],
                ambiguous,
            )
        elif rule_id in our_rules:
            merged_rules[rule_id] = dict(our_rules[rule_id])
        else:
            merged_rules[rule_id] = dict(their_rules[rule_id])

    order = _merge_order(
        rel_path, _order(base), _order(ours), _order(theirs), set(merged_rules)
    )
    merged["rules"] = [merged_rules[rule_id] for rule_id in order]

    notes: list[str] = []
    if ambiguous:
        if not ctx.remeasure:
            raise Refusal(
                rel_path,
                "both sides changed the gzip numbers of rule(s) "
                + ", ".join(sorted(ambiguous))
                + "; the merged size is neither value. Re-run with --remeasure to "
                "build and measure the merged tree, or let the pull request out of "
                "the train and rebaseline it by hand.",
            )
        merged["rules"] = [merged_rules[rule_id] for rule_id in order]
        measured = _remeasure(ctx, rel_path, merged)
        notes.extend(
            _apply_measurements(
                ctx,
                rel_path,
                merged_rules,
                ambiguous,
                our_rules,
                their_rules,
                measured,
            )
        )

    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    detail = (
        f"merged {len(order)} rules by id"
        + (f"; remeasured {', '.join(sorted(ambiguous))}" if ambiguous else "")
    )
    return Resolution(path=rel_path, text=text, detail=detail, notes=notes)


# --------------------------------------------------------------------------
# --remeasure support
# --------------------------------------------------------------------------

_MEASURE_JS = r"""
const { readFileSync, readdirSync, statSync, existsSync } = require('node:fs');
const path = require('node:path');
const { gzipSync } = require('node:zlib');

const budget = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const outDir = path.resolve(process.argv[3], budget.outDir || '../../static');
const gzipLevel = typeof budget.gzipLevel === 'number' ? budget.gzipLevel : 9;

function globToRegExp(globPattern) {
  const escaped = globPattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '[^/]*');
  return new RegExp(`^${escaped}$`);
}

const assetsDirectory = path.join(outDir, 'assets');
if (!existsSync(assetsDirectory)) {
  console.error(`assets directory not found: ${assetsDirectory}`);
  process.exit(1);
}
const files = readdirSync(assetsDirectory)
  .filter((name) => name.endsWith('.js') || name.endsWith('.css'))
  .map((name) => path.join(assetsDirectory, name))
  .filter((filePath) => statSync(filePath).isFile());

const measured = {};
for (const filePath of files) {
  const relativePath = path.relative(outDir, filePath).split(path.sep).join('/');
  const rule = budget.rules.find((candidate) => globToRegExp(candidate.match).test(relativePath));
  if (!rule) continue;
  const size = gzipSync(readFileSync(filePath), { level: gzipLevel }).length;
  measured[rule.id] = Math.max(measured[rule.id] || 0, size);
}
process.stdout.write(JSON.stringify(measured));
"""


def _remeasure(ctx: Context, rel_path: str, merged: dict[str, Any]) -> dict[str, int]:
    web_root = ctx.repo_root / "apps" / "dsa-web"
    if not (web_root / "node_modules").is_dir():
        raise Refusal(
            rel_path,
            "--remeasure needs apps/dsa-web/node_modules; run `npm ci` there first",
        )
    if shutil.which("npm") is None or shutil.which("node") is None:
        raise Refusal(rel_path, "--remeasure needs node and npm on PATH")

    build = subprocess.run(
        ["npm", "run", "build"], cwd=web_root, capture_output=True, text=True
    )
    if build.returncode != 0:
        raise Refusal(
            rel_path,
            "--remeasure production build failed: "
            + (build.stderr or build.stdout).strip()[-600:],
        )

    tmp_budget = web_root / ".merge-resolver-budget.json"
    tmp_script = web_root / ".merge-resolver-measure.cjs"
    try:
        tmp_budget.write_text(json.dumps(merged), encoding="utf-8")
        tmp_script.write_text(_MEASURE_JS, encoding="utf-8")
        proc = subprocess.run(
            ["node", str(tmp_script), str(tmp_budget), str(web_root)],
            cwd=web_root,
            capture_output=True,
            text=True,
        )
    finally:
        tmp_budget.unlink(missing_ok=True)
        tmp_script.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise Refusal(
            rel_path, "--remeasure measurement failed: " + proc.stderr.strip()[-400:]
        )
    return {key: int(value) for key, value in json.loads(proc.stdout).items()}


def _headroom(rule: dict[str, Any]) -> int | None:
    if isinstance(rule.get("maxGzipBytes"), int) and isinstance(
        rule.get("measuredGzipBytes"), int
    ):
        return rule["maxGzipBytes"] - rule["measuredGzipBytes"]
    return None


def _apply_measurements(
    ctx: Context,
    rel_path: str,
    merged_rules: dict[str, dict[str, Any]],
    ambiguous: list[str],
    our_rules: dict[str, dict[str, Any]],
    their_rules: dict[str, dict[str, Any]],
    measured: dict[str, int],
) -> list[str]:
    notes: list[str] = []
    context_label = _merge_label(ctx)
    for rule_id in sorted(ambiguous):
        if rule_id not in measured:
            raise Refusal(
                rel_path,
                f"rule {rule_id!r} matched no built asset; cannot remeasure",
            )
        actual = measured[rule_id]
        headroom = max(
            _headroom(our_rules.get(rule_id, {})) or 0,
            _headroom(their_rules.get(rule_id, {})) or 0,
            DEFAULT_HEADROOM_BYTES,
        )
        rule = merged_rules[rule_id]
        rule["measuredGzipBytes"] = actual
        rule["maxGzipBytes"] = actual + headroom
        rule["note"] = (
            f"Combined production-build measurement of the merged tree "
            f"({context_label}); both sides changed this chunk, so neither "
            f"pre-merge number is the post-merge size. Measured {actual} B with "
            f"{headroom} B headroom."
        )
        notes.append(f"{rule_id}: measured {actual} B, budget {actual + headroom} B")

    regressions = []
    for rule_id, actual in measured.items():
        if rule_id in ambiguous or rule_id not in merged_rules:
            continue
        cap = merged_rules[rule_id].get("maxGzipBytes")
        if isinstance(cap, int) and actual > cap:
            regressions.append(f"{rule_id} ({actual} B > {cap} B)")
    if regressions:
        raise Refusal(
            rel_path,
            "the merged build exceeds budgets that neither side touched: "
            + ", ".join(sorted(regressions))
            + "; this is a real regression, not a merge artefact",
        )
    return notes


def _merge_label(ctx: Context) -> str:
    ours = ctx.git("rev-parse", "--short", "HEAD", check=False).stdout.strip()
    theirs = ctx.git("rev-parse", "--short", "MERGE_HEAD", check=False).stdout.strip()
    if ours and theirs:
        return f"{ours} + {theirs}"
    return "local merge"
