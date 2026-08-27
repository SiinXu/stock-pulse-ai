"""Reusable sections for history Markdown reports."""

from __future__ import annotations

from typing import Any

from src.report_language import (
    append_bull_bear_debate_lines,
    append_red_team_lines,
    format_strategy_skill_items,
    localize_conflict_severity,
    localize_consensus_level,
    localize_disagreement_verdict_mode,
    localize_strategy_signal,
    localize_strategy_synthesis_summary,
    normalize_disagreement_handling_payload,
    normalize_strategy_synthesis_payload,
    strategy_invalid_opinion_count,
)


def append_strategy_synthesis_lines(
    report_lines: list[str],
    dashboard: Any,
    labels: dict[str, str],
    report_language: str,
) -> None:
    """Append strategy synthesis and its high-disagreement annotation."""

    dashboard_data = dashboard if isinstance(dashboard, dict) else {}
    synthesis = normalize_strategy_synthesis_payload(
        dashboard_data.get("strategy_synthesis")
    )
    if synthesis:
        confidence = synthesis.get("confidence")
        confidence_text = (
            f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "N/A"
        )
        report_lines.extend(
            [
                f"### 🧩 {labels.get('strategy_synthesis_heading', '多策略综合')}",
                "",
                (
                    f"- {labels.get('strategy_final_signal_label', '综合信号')}: "
                    f"{localize_strategy_signal(synthesis.get('final_signal', 'N/A'), report_language)} | "
                    f"{labels.get('strategy_consensus_level_label', '共识度')}: "
                    f"{localize_consensus_level(synthesis.get('consensus_level', 'N/A'), report_language)} | "
                    f"{labels.get('strategy_conflict_label', '冲突')}: "
                    f"{localize_conflict_severity(synthesis.get('conflict_severity', 'none'), report_language)} "
                    f"({synthesis.get('conflict_count', 0)}) | "
                    f"{labels.get('strategy_confidence_label', '置信度')}: {confidence_text}"
                ),
            ]
        )
        summary = localize_strategy_synthesis_summary(synthesis, report_language)
        if summary:
            report_lines.append(
                f"- {labels.get('strategy_summary_label', '综合说明')}: {summary}"
            )
        report_lines.append(
            f"- {labels.get('strategy_supporting_skills_label', '支持策略')}: "
            f"{format_strategy_skill_items(synthesis.get('supporting_skills'), report_language)}"
        )
        report_lines.append(
            f"- {labels.get('strategy_opposing_skills_label', '反方策略')}: "
            f"{format_strategy_skill_items(synthesis.get('opposing_skills'), report_language)}"
        )
        invalid_count = strategy_invalid_opinion_count(synthesis)
        if invalid_count:
            template = labels.get(
                "strategy_invalid_opinions_label",
                "另有 {count} 个策略解析失败",
            )
            try:
                invalid_text = template.format(count=invalid_count)
            except (KeyError, IndexError):
                invalid_text = f"{template}: {invalid_count}"
            report_lines.append(f"- {invalid_text}")

    handling = normalize_disagreement_handling_payload(
        (synthesis.get("disagreement_handling") if synthesis else None)
        or dashboard_data.get("disagreement_handling")
    )
    if handling and handling.get("high_disagreement"):
        report_lines.append(
            f"- ⚠️ {labels.get('disagreement_high_banner', 'High disagreement')}"
        )
        report_lines.append(
            f"- {labels.get('disagreement_verdict_label', 'Verdict mode')}: "
            f"{localize_disagreement_verdict_mode(handling.get('verdict_mode'), report_language)} | "
            f"{labels.get('disagreement_escalation_label', 'Escalation')}: "
            f"{handling.get('escalation')} | "
            f"{labels.get('disagreement_no_majority_note', 'Majority vote was not used')}"
        )
    if synthesis or (handling and handling.get("high_disagreement")):
        report_lines.append("")


def append_debate_and_red_team_lines(
    report_lines: list[str],
    dashboard: Any,
    labels: dict[str, str],
) -> None:
    """Append debate then the additive red-team second-opinion section."""
    append_bull_bear_debate_lines(report_lines, dashboard, labels)
    append_red_team_lines(report_lines, dashboard, labels)


__all__ = ["append_debate_and_red_team_lines", "append_strategy_synthesis_lines"]
