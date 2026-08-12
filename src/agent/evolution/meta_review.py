# -*- coding: utf-8 -*-
"""Cross-run (meta) reflection aggregator (Issue #1094).

Periodic offline job that aggregates episodes into a human-readable evolution
report. It **never** auto-mutates Agent Soul, ToolSurface denials, or runtime
config. Sample thresholds gate report emission so sparse history does not
produce over-confident recommendations.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from src.agent.evolution.budget import (
    BUDGET_SKIPPED,
    DEFAULT_META_REVIEW_LLM_BUDGET,
    LlmCallBudget,
)
from src.agent.evolution.guards import (
    assert_soul_unchanged,
    assert_tool_surface_unchanged,
    snapshot_soul_identity,
    snapshot_tool_surface_denials,
)
from src.agent.evolution.lessons import LESSON_KINDS
from src.agent.public_contract import sanitize_agent_diagnostic
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

DEFAULT_META_MIN_EPISODES = 30
DEFAULT_META_MIN_KIND_COUNT = 3
DEFAULT_META_MAX_EXAMPLES = 5
META_REPORT_SCHEMA_VERSION = "agent-meta-review-v1"

LlmCompleteFn = Callable[[str, str], str]


def is_meta_review_enabled(config: Any) -> bool:
    return getattr(config, "agent_meta_review_enabled", False) is True


@dataclass
class MetaReviewReport:
    """Actionable offline evolution report (Markdown + JSON)."""

    schema_version: str = META_REPORT_SCHEMA_VERSION
    status: str = "completed"
    skip_reason: Optional[str] = None
    sample_count: int = 0
    sample_threshold: int = DEFAULT_META_MIN_EPISODES
    threshold_met: bool = False
    generated_at: str = ""
    top_failure_kinds: List[Dict[str, Any]] = field(default_factory=list)
    worst_tools: List[Dict[str, Any]] = field(default_factory=list)
    high_revise_modes: List[Dict[str, Any]] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)
    examples_by_kind: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    llm_budget_total: int = 0
    llm_budget_consumed: int = 0
    llm_budget_remaining: int = 0
    validation_status: str = "valid"
    strategy_note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "skip_reason": self.skip_reason,
            "sample_count": self.sample_count,
            "sample_threshold": self.sample_threshold,
            "threshold_met": self.threshold_met,
            "generated_at": self.generated_at,
            "top_failure_kinds": list(self.top_failure_kinds),
            "worst_tools": list(self.worst_tools),
            "high_revise_modes": list(self.high_revise_modes),
            "recommended_actions": list(self.recommended_actions),
            "examples_by_kind": {
                kind: list(items) for kind, items in self.examples_by_kind.items()
            },
            "llm_budget_total": self.llm_budget_total,
            "llm_budget_consumed": self.llm_budget_consumed,
            "llm_budget_remaining": self.llm_budget_remaining,
            "validation_status": self.validation_status,
            "strategy_note": self.strategy_note,
            "mutates_soul": False,
            "mutates_tool_surface": False,
            "mutates_runtime_config": False,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Agent Meta-Review Report",
            "",
            f"- Schema: `{self.schema_version}`",
            f"- Generated at: `{self.generated_at or 'n/a'}`",
            f"- Status: **{self.status}**",
            f"- Samples: **{self.sample_count}** (threshold {self.sample_threshold})",
            f"- Threshold met: **{self.threshold_met}**",
            f"- LLM budget: consumed {self.llm_budget_consumed} / total {self.llm_budget_total}",
            "",
            "Product rules: this report is research/quality-ops only. It does "
            "**not** rewrite Agent Soul, ToolSurface denials, or runtime config.",
            "",
        ]
        if self.skip_reason:
            lines.extend([f"> Skip reason: {self.skip_reason}", ""])

        lines.append("## Top failure kinds")
        if not self.top_failure_kinds:
            lines.append("- (none)")
        else:
            for item in self.top_failure_kinds:
                examples = ", ".join(item.get("example_run_ids") or []) or "n/a"
                lines.append(
                    f"- `{item.get('kind')}`: count={item.get('count')} examples={examples}"
                )
        lines.append("")

        lines.append("## Worst tools")
        if not self.worst_tools:
            lines.append("- (none)")
        else:
            for item in self.worst_tools:
                examples = ", ".join(item.get("example_run_ids") or []) or "n/a"
                lines.append(
                    f"- `{item.get('tool')}`: failures={item.get('count')} examples={examples}"
                )
        lines.append("")

        lines.append("## Modes with high revise rate")
        if not self.high_revise_modes:
            lines.append("- (none)")
        else:
            for item in self.high_revise_modes:
                lines.append(
                    f"- `{item.get('mode')}`: revise_rate={item.get('revise_rate'):.2f} "
                    f"samples={item.get('samples')}"
                )
        lines.append("")

        lines.append("## Recommended actions")
        if not self.recommended_actions:
            lines.append("- (none — insufficient signal or threshold not met)")
        else:
            for action in self.recommended_actions:
                lines.append(f"- {action}")
        lines.append("")

        if self.strategy_note:
            lines.extend(["## Strategy note", "", self.strategy_note, ""])

        lines.append("## Examples by kind")
        if not self.examples_by_kind:
            lines.append("- (none)")
        else:
            for kind, examples in self.examples_by_kind.items():
                lines.append(f"### `{kind}`")
                for example in examples:
                    run_id = example.get("run_id") or "unknown"
                    remedy = example.get("remedy") or ""
                    lines.append(f"- run_id=`{run_id}` remedy={remedy}")
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def run_meta_review(
    episodes: Sequence[Dict[str, Any]],
    *,
    config: Any = None,
    min_episodes: Optional[int] = None,
    min_kind_count: int = DEFAULT_META_MIN_KIND_COUNT,
    max_examples: int = DEFAULT_META_MAX_EXAMPLES,
    budget: Optional[LlmCallBudget] = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    tool_surface: Any = None,
    denied_tools: Optional[Sequence[str]] = None,
    denial_codes: Optional[Sequence[str]] = None,
    force: bool = False,
) -> MetaReviewReport:
    """Aggregate episodes into a meta-review report under sample + LLM budgets."""
    soul_before = snapshot_soul_identity()
    tools_before = snapshot_tool_surface_denials(
        tool_surface,
        denied_tools=denied_tools,
        denial_codes=denial_codes,
    )

    if config is not None and not is_meta_review_enabled(config) and not force:
        report = MetaReviewReport(
            status="disabled",
            skip_reason="Meta-review is disabled by configuration.",
            validation_status="disabled",
            generated_at=_utc_now(),
        )
        _assert_immutable(soul_before, tools_before, tool_surface, denied_tools, denial_codes)
        return report

    threshold = _resolve_threshold(config, min_episodes)
    call_budget = budget or _budget_from_config(config)
    samples = [ep for ep in episodes if isinstance(ep, dict)]
    sample_count = len(samples)
    generated_at = _utc_now()

    if sample_count < threshold:
        report = MetaReviewReport(
            status="threshold_not_met",
            skip_reason=(
                f"Sample count {sample_count} is below meta-review threshold {threshold}."
            ),
            sample_count=sample_count,
            sample_threshold=threshold,
            threshold_met=False,
            generated_at=generated_at,
            llm_budget_total=call_budget.total,
            llm_budget_consumed=call_budget.consumed,
            llm_budget_remaining=call_budget.remaining,
            validation_status="threshold_not_met",
        )
        _assert_immutable(soul_before, tools_before, tool_surface, denied_tools, denial_codes)
        return report

    kind_counter: Counter = Counter()
    tool_counter: Counter = Counter()
    kind_examples: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    tool_examples: Dict[str, List[str]] = defaultdict(list)
    mode_stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"samples": 0, "revised": 0}
    )

    for episode in samples:
        run_id = str(episode.get("run_id") or episode.get("episode_id") or "unknown")
        mode = str(
            episode.get("mode")
            or (episode.get("meta") or {}).get("mode")
            or "unknown"
        )
        mode_stats[mode]["samples"] += 1
        if episode.get("revised") or (episode.get("meta") or {}).get("revised"):
            mode_stats[mode]["revised"] += 1

        for lesson in _iter_lessons(episode):
            kind = str(lesson.get("kind") or "").strip()
            if kind not in LESSON_KINDS:
                continue
            kind_counter[kind] += 1
            if len(kind_examples[kind]) < max_examples:
                kind_examples[kind].append(
                    {
                        "run_id": run_id,
                        "remedy": sanitize_agent_diagnostic(
                            str(lesson.get("remedy") or "")
                        ),
                        "source_step": str(lesson.get("source_step") or ""),
                    }
                )
            tool = _tool_from_source_step(lesson.get("source_step"))
            if tool:
                tool_counter[tool] += 1
                if (
                    run_id not in tool_examples[tool]
                    and len(tool_examples[tool]) < max_examples
                ):
                    tool_examples[tool].append(run_id)

        for tool_name, count in _failed_tools_from_trajectory(episode):
            tool_counter[tool_name] += count
            if (
                run_id not in tool_examples[tool_name]
                and len(tool_examples[tool_name]) < max_examples
            ):
                tool_examples[tool_name].append(run_id)

    top_kinds = [
        {
            "kind": kind,
            "count": count,
            "example_run_ids": [ex["run_id"] for ex in kind_examples.get(kind, [])],
        }
        for kind, count in kind_counter.most_common(10)
        if count >= min_kind_count
    ]
    worst_tools = [
        {
            "tool": tool,
            "count": count,
            "example_run_ids": list(tool_examples.get(tool, [])),
        }
        for tool, count in tool_counter.most_common(10)
        if count >= min_kind_count
    ]
    high_revise = []
    for mode, stats in sorted(mode_stats.items(), key=lambda item: item[0]):
        samples_n = stats["samples"]
        if samples_n < min_kind_count:
            continue
        rate = stats["revised"] / float(samples_n)
        if rate >= 0.3:
            high_revise.append(
                {
                    "mode": mode,
                    "samples": samples_n,
                    "revised": stats["revised"],
                    "revise_rate": round(rate, 4),
                }
            )
    high_revise.sort(key=lambda item: item["revise_rate"], reverse=True)

    actions = _recommended_actions(top_kinds, worst_tools, high_revise)
    strategy_note: Optional[str] = None
    validation_status = "valid"
    skip_reason: Optional[str] = None
    status = "completed"

    if llm_complete is not None:
        if not call_budget.try_consume(reason="meta_review"):
            skip_reason = "Meta-review LLM enrichment skipped: budget exhausted."
            validation_status = BUDGET_SKIPPED
        else:
            try:
                raw = llm_complete(
                    _meta_system_prompt(),
                    _meta_user_payload(top_kinds, worst_tools, high_revise, actions),
                )
                note = _extract_strategy_note(raw)
                if note:
                    strategy_note = note
            except Exception as exc:  # broad-exception: fallback_recorded - optional LLM fail-soft
                log_safe_exception(
                    logger,
                    "Meta-review LLM call failed",
                    exc,
                    error_code="agent_meta_review_llm_failed",
                    level=logging.WARNING,
                )
                skip_reason = sanitize_agent_diagnostic(
                    f"Meta-review LLM failed: {type(exc).__name__}"
                )

    report = MetaReviewReport(
        status=status,
        skip_reason=skip_reason,
        sample_count=sample_count,
        sample_threshold=threshold,
        threshold_met=True,
        generated_at=generated_at,
        top_failure_kinds=top_kinds,
        worst_tools=worst_tools,
        high_revise_modes=high_revise,
        recommended_actions=actions,
        examples_by_kind={k: list(v) for k, v in kind_examples.items()},
        llm_budget_total=call_budget.total,
        llm_budget_consumed=call_budget.consumed,
        llm_budget_remaining=call_budget.remaining,
        validation_status=validation_status,
        strategy_note=strategy_note,
    )
    _assert_immutable(soul_before, tools_before, tool_surface, denied_tools, denial_codes)
    return report


def write_meta_review_report(
    report: MetaReviewReport,
    output_dir: str | Path,
    *,
    basename: str = "meta_review",
) -> Dict[str, str]:
    """Write Markdown + JSON report artifacts; does not touch runtime config."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    md_path = directory / f"{basename}.md"
    json_path = directory / f"{basename}.json"
    md_path.write_text(report.to_markdown(), encoding="utf-8")
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return {"markdown": str(md_path), "json": str(json_path)}


def _resolve_threshold(config: Any, override: Optional[int]) -> int:
    if override is not None:
        return max(1, int(override))
    raw = (
        getattr(config, "agent_meta_review_min_episodes", None)
        if config is not None
        else None
    )
    try:
        value = int(raw) if raw is not None else DEFAULT_META_MIN_EPISODES
    except (TypeError, ValueError):
        value = DEFAULT_META_MIN_EPISODES
    return max(1, value)


def _budget_from_config(config: Any) -> LlmCallBudget:
    raw = (
        getattr(config, "agent_meta_review_llm_budget", None)
        if config is not None
        else None
    )
    try:
        total = int(raw) if raw is not None else DEFAULT_META_REVIEW_LLM_BUDGET
    except (TypeError, ValueError):
        total = DEFAULT_META_REVIEW_LLM_BUDGET
    return LlmCallBudget(total=max(0, total))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _iter_lessons(episode: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    lessons = episode.get("lessons") or []
    if isinstance(lessons, list):
        for item in lessons:
            if isinstance(item, dict):
                yield item
    reflection = episode.get("reflection_result") or (episode.get("meta") or {}).get(
        "reflection_result"
    )
    if isinstance(reflection, dict):
        for item in reflection.get("lessons") or []:
            if isinstance(item, dict):
                yield item
    step = episode.get("step_critique_result") or (episode.get("meta") or {}).get(
        "step_critique_result"
    )
    if isinstance(step, dict):
        for item in step.get("lessons") or []:
            if isinstance(item, dict):
                yield item


def _tool_from_source_step(source_step: Any) -> Optional[str]:
    text = str(source_step or "").strip()
    if not text or ":" not in text:
        return None
    parts = [part for part in text.split(":") if part]
    if not parts:
        return None
    candidate = parts[-1]
    if candidate and candidate not in {"step", "tool"} and not candidate.isdigit():
        return candidate[:128]
    return None


def _failed_tools_from_trajectory(episode: Dict[str, Any]) -> List[Tuple[str, int]]:
    counts: Counter = Counter()
    trajectory = episode.get("trajectory_summary") or episode.get("trajectory") or []
    if not isinstance(trajectory, list):
        return []
    for step in trajectory:
        if not isinstance(step, dict):
            continue
        tool = str(step.get("tool") or step.get("tool_name") or "").strip()
        success = step.get("success")
        if tool and success is False:
            counts[tool] += 1
    return list(counts.items())


def _recommended_actions(
    top_kinds: Sequence[Dict[str, Any]],
    worst_tools: Sequence[Dict[str, Any]],
    high_revise: Sequence[Dict[str, Any]],
) -> List[str]:
    actions: List[str] = []
    for item in top_kinds[:5]:
        kind = item.get("kind")
        if kind == "tool_failure":
            actions.append(
                "investigate provider / tool reliability for frequent tool_failure lessons"
            )
        elif kind == "evidence_gap":
            actions.append(
                "tighten router or retrieval for evidence_gap cases before decision synthesis"
            )
        elif kind == "overconfidence":
            actions.append(
                "promote calibration skill / lower default confidence when overconfidence dominates"
            )
        elif kind == "risk_omission":
            actions.append("promote risk-checklist skill for risk_omission clusters")
        elif kind == "format_violation":
            actions.append(
                "tighten structured-output validators for format_violation clusters"
            )
        elif kind == "horizon_mismatch":
            actions.append("align forecast horizon policy for horizon_mismatch clusters")
        elif kind == "regime_shift":
            actions.append("review regime filters for regime_shift clusters")
        else:
            actions.append(
                f"review playbook for kind `{kind}` (count={item.get('count')})"
            )

    for item in worst_tools[:3]:
        actions.append(
            f"investigate provider/tool `{item.get('tool')}` "
            f"(failure count={item.get('count')})"
        )

    for item in high_revise[:3]:
        actions.append(
            f"tighten router for mode `{item.get('mode')}` "
            f"(revise_rate={item.get('revise_rate')})"
        )

    seen: set = set()
    unique: List[str] = []
    for action in actions:
        if action in seen:
            continue
        seen.add(action)
        unique.append(action)
    return unique[:12]


def _meta_system_prompt() -> str:
    return (
        "You summarize offline agent evolution stats for human operators. "
        "Do not rewrite Soul rules, grant tools, or change runtime config. "
        'Return JSON: {"strategy_note": "short human-readable note"}.'
    )


def _meta_user_payload(
    top_kinds: Sequence[Dict[str, Any]],
    worst_tools: Sequence[Dict[str, Any]],
    high_revise: Sequence[Dict[str, Any]],
    actions: Sequence[str],
) -> str:
    payload = {
        "top_failure_kinds": list(top_kinds),
        "worst_tools": list(worst_tools),
        "high_revise_modes": list(high_revise),
        "recommended_actions": list(actions),
    }
    return "Summarize this meta-review snapshot:\n" + json.dumps(
        payload, ensure_ascii=False
    )


def _extract_strategy_note(raw: str) -> Optional[str]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return sanitize_agent_diagnostic(text)[:500] or None
    if isinstance(parsed, dict):
        note = parsed.get("strategy_note")
        if isinstance(note, str) and note.strip():
            return sanitize_agent_diagnostic(note.strip())[:500] or None
    return None


def _assert_immutable(
    soul_before: Any,
    tools_before: Any,
    tool_surface: Any,
    denied_tools: Optional[Sequence[str]],
    denial_codes: Optional[Sequence[str]],
) -> None:
    assert_soul_unchanged(soul_before)
    assert_tool_surface_unchanged(
        tools_before,
        tool_surface,
        denied_tools=denied_tools,
        denial_codes=denial_codes,
    )


__all__ = [
    "DEFAULT_META_MAX_EXAMPLES",
    "DEFAULT_META_MIN_EPISODES",
    "DEFAULT_META_MIN_KIND_COUNT",
    "META_REPORT_SCHEMA_VERSION",
    "MetaReviewReport",
    "is_meta_review_enabled",
    "run_meta_review",
    "write_meta_review_report",
]
