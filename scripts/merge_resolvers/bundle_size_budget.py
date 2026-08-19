"""Resolve independent bundle-budget rule changes by stable rule ID."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .common import ConflictContext, RefusalError, parse_conflict_hunks


SUPPORTED_PATH = Path("apps/dsa-web/scripts/bundle-size-budget.json")
OPTIONAL_TOP_LEVEL_KEYS = frozenset({"aggregateRules"})


def _parse_document(path: Path, label: str, text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RefusalError(path, f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("rules"), list):
        raise RefusalError(path, f"{label} must be an object with a rules array")
    if "aggregateRules" in value and not isinstance(value.get("aggregateRules"), list):
        raise RefusalError(path, f"{label} aggregateRules must be an array when present")
    return value


def _has_valid_match(match: Any, allow_list: bool) -> bool:
    if isinstance(match, str) and match.strip():
        return True
    if allow_list and isinstance(match, list) and match and all(
        isinstance(item, str) and item.strip() for item in match
    ):
        return True
    return False


def _rules_by_id(
    path: Path,
    label: str,
    rules: list[Any],
    *,
    allow_list_match: bool = False,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
            raise RefusalError(path, f"{label} rule {index} has no string id")
        rule_id = rule["id"]
        if rule_id in result:
            raise RefusalError(path, f"{label} contains duplicate rule id {rule_id!r}")
        if not _has_valid_match(rule.get("match"), allow_list_match):
            raise RefusalError(path, f"{label} rule {rule_id!r} has no string match")
        for field in ("maxGzipBytes", "measuredGzipBytes"):
            if not isinstance(rule.get(field), int) or rule[field] < 0:
                raise RefusalError(path, f"{label} rule {rule_id!r} has invalid {field}")
        if rule["maxGzipBytes"] < rule["measuredGzipBytes"]:
            raise RefusalError(path, f"{label} rule {rule_id!r} budget is below measurement")
        result[rule_id] = rule
    return result


def _merge_scalar(path: Path, field: str, base: Any, ours: Any, theirs: Any) -> Any:
    if ours == theirs:
        return deepcopy(ours)
    if ours == base:
        return deepcopy(theirs)
    if theirs == base:
        return deepcopy(ours)
    raise RefusalError(path, f"top-level field {field!r} changed differently on both sides")


def _validate_changed_note(path: Path, rule_id: str, base: dict[str, Any], merged: dict[str, Any]) -> None:
    numeric_changed = any(
        base.get(field) != merged.get(field)
        for field in ("maxGzipBytes", "measuredGzipBytes")
    )
    if not numeric_changed:
        return
    note = merged.get("note")
    if not isinstance(note, str) or "measur" not in note.lower() or not (
        "headroom" in note.lower() or "+" in note
    ):
        raise RefusalError(
            path,
            f"rule {rule_id!r} changed numeric budgets without a measurement/headroom note",
        )


def _addition_gaps(path: Path, base_ids: list[str], side_ids: list[str], label: str) -> list[list[str]]:
    base_set = set(base_ids)
    retained = [rule_id for rule_id in side_ids if rule_id in base_set]
    if retained != base_ids:
        raise RefusalError(path, f"{label} removed or reordered existing rules")

    gaps: list[list[str]] = [[] for _ in range(len(base_ids) + 1)]
    gap_index = 0
    base_index = 0
    for rule_id in side_ids:
        if base_index < len(base_ids) and rule_id == base_ids[base_index]:
            base_index += 1
            gap_index = base_index
        elif rule_id not in base_set:
            gaps[gap_index].append(rule_id)
    return gaps


def _required_keys(document: dict[str, Any]) -> set[str]:
    return set(document) - OPTIONAL_TOP_LEVEL_KEYS


def _merge_named_rules(
    path: Path,
    base_rules: list[Any],
    our_rules: list[Any],
    their_rules: list[Any],
    *,
    collection_label: str,
    allow_list_match: bool,
) -> list[dict[str, Any]]:
    parsed_base = _rules_by_id(path, f"base {collection_label}", base_rules, allow_list_match=allow_list_match)
    parsed_ours = _rules_by_id(path, f"ours {collection_label}", our_rules, allow_list_match=allow_list_match)
    parsed_theirs = _rules_by_id(path, f"theirs {collection_label}", their_rules, allow_list_match=allow_list_match)
    base_ids = list(parsed_base)

    our_gaps = _addition_gaps(path, base_ids, list(parsed_ours), f"ours {collection_label}")
    their_gaps = _addition_gaps(path, base_ids, list(parsed_theirs), f"theirs {collection_label}")

    merged_rules: dict[str, dict[str, Any]] = {}
    for rule_id in base_ids:
        base_rule = parsed_base[rule_id]
        our_rule = parsed_ours[rule_id]
        their_rule = parsed_theirs[rule_id]
        ours_changed = our_rule != base_rule
        theirs_changed = their_rule != base_rule
        if ours_changed and theirs_changed:
            raise RefusalError(path, f"rule {rule_id!r} changed on both sides; rebuild measurement required")
        selected = their_rule if theirs_changed else our_rule
        _validate_changed_note(path, rule_id, base_rule, selected)
        merged_rules[rule_id] = deepcopy(selected)

    additions = (set(parsed_ours) | set(parsed_theirs)) - set(parsed_base)
    for rule_id in additions:
        if rule_id in parsed_ours and rule_id in parsed_theirs:
            raise RefusalError(path, f"new rule {rule_id!r} was added on both sides")
        merged_rules[rule_id] = deepcopy(parsed_ours.get(rule_id) or parsed_theirs[rule_id])

    ordered_ids: list[str] = []
    for gap_index in range(len(base_ids) + 1):
        ordered_ids.extend(sorted(set(our_gaps[gap_index] + their_gaps[gap_index])))
        if gap_index < len(base_ids):
            ordered_ids.append(base_ids[gap_index])
    if set(ordered_ids) != set(merged_rules) or len(ordered_ids) != len(merged_rules):
        raise RefusalError(path, f"could not derive a unique merged {collection_label} order")

    return [merged_rules[rule_id] for rule_id in ordered_ids]


def resolve(context: ConflictContext) -> str:
    """Return merged JSON, refusing overlapping rule or metadata changes."""

    path = context.path
    _, hunk_count = parse_conflict_hunks(path, context.current)
    if hunk_count == 0:
        raise RefusalError(path, "file has no conflict hunks")
    base = _parse_document(path, "base", context.base)
    ours = _parse_document(path, "ours", context.ours)
    theirs = _parse_document(path, "theirs", context.theirs)

    if _required_keys(base) != _required_keys(ours) or _required_keys(base) != _required_keys(theirs):
        raise RefusalError(path, "top-level JSON keys changed; only rule values are supported")

    merged: dict[str, Any] = {}
    for field in base:
        if field in {"rules", "aggregateRules"}:
            continue
        merged[field] = _merge_scalar(path, field, base[field], ours[field], theirs[field])

    merged["rules"] = _merge_named_rules(
        path,
        base["rules"],
        ours["rules"],
        theirs["rules"],
        collection_label="rules",
        allow_list_match=False,
    )

    if any("aggregateRules" in document for document in (base, ours, theirs)):
        merged["aggregateRules"] = _merge_named_rules(
            path,
            base.get("aggregateRules") or [],
            ours.get("aggregateRules") or [],
            theirs.get("aggregateRules") or [],
            collection_label="aggregateRules",
            allow_list_match=True,
        )

    return json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
