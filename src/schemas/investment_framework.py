# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Stable domain schemas for personal investment framework content."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


FrameworkKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
FrameworkRule = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]


class InvestmentFrameworkDecisionBranch(BaseModel):
    """One condition leading to another node or a terminal outcome."""

    condition: FrameworkRule
    target_node_id: Optional[FrameworkKey] = None
    outcome: Optional[FrameworkRule] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _require_one_destination(self) -> "InvestmentFrameworkDecisionBranch":
        if (self.target_node_id is None) == (self.outcome is None):
            raise ValueError("A decision branch must define exactly one target or outcome")
        return self


class InvestmentFrameworkDecisionNode(BaseModel):
    """Addressable decision-tree node with bounded branches."""

    node_id: FrameworkKey
    question: FrameworkRule
    branches: List[InvestmentFrameworkDecisionBranch] = Field(
        ...,
        min_length=1,
        max_length=20,
    )

    model_config = ConfigDict(extra="forbid")


class InvestmentFrameworkEvaluationDimension(BaseModel):
    """Weighted evaluation dimension and its explicit criteria."""

    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ]
    weight: float = Field(..., ge=0, le=100)
    criteria: List[FrameworkRule] = Field(default_factory=list, max_length=30)
    description: Optional[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
        ]
    ] = None

    model_config = ConfigDict(extra="forbid")


class InvestmentFrameworkContent(BaseModel):
    """Versioned, portable framework content independent of persistence state."""

    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    ]
    description: Optional[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
        ]
    ] = None
    root_node_id: Optional[FrameworkKey] = None
    decision_tree: List[InvestmentFrameworkDecisionNode] = Field(
        default_factory=list,
        max_length=100,
    )
    evaluation_dimensions: List[InvestmentFrameworkEvaluationDimension] = Field(
        default_factory=list,
        max_length=50,
    )
    risk_rules: List[FrameworkRule] = Field(default_factory=list, max_length=100)
    tracking_criteria: List[FrameworkRule] = Field(default_factory=list, max_length=100)
    free_form_rules: Optional[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=10000),
        ]
    ] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_structure(self) -> "InvestmentFrameworkContent":
        if not any(
            (
                self.decision_tree,
                self.evaluation_dimensions,
                self.risk_rules,
                self.tracking_criteria,
                self.free_form_rules,
            )
        ):
            raise ValueError("Investment framework content must define at least one criterion")

        node_ids = [node.node_id for node in self.decision_tree]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Decision-tree node IDs must be unique")
        if self.decision_tree:
            known_node_ids = set(node_ids)
            if self.root_node_id is None or self.root_node_id not in known_node_ids:
                raise ValueError("root_node_id must identify a decision-tree node")
            unknown_targets = sorted(
                {
                    branch.target_node_id
                    for node in self.decision_tree
                    for branch in node.branches
                    if branch.target_node_id is not None
                    and branch.target_node_id not in known_node_ids
                }
            )
            if unknown_targets:
                raise ValueError("Decision-tree branches reference unknown target nodes")

            adjacency = {
                node.node_id: tuple(
                    branch.target_node_id
                    for branch in node.branches
                    if branch.target_node_id is not None
                )
                for node in self.decision_tree
            }
            visited = set()
            visiting = set()

            def visit(node_id: str) -> None:
                if node_id in visiting:
                    raise ValueError("Decision tree must not contain cycles")
                if node_id in visited:
                    return
                visiting.add(node_id)
                for target_node_id in adjacency[node_id]:
                    visit(target_node_id)
                visiting.remove(node_id)
                visited.add(node_id)

            visit(self.root_node_id)
            if visited != known_node_ids:
                raise ValueError("Every decision-tree node must be reachable from the root")
        elif self.root_node_id is not None:
            raise ValueError("root_node_id requires a decision tree")

        dimension_names = [item.name.casefold() for item in self.evaluation_dimensions]
        if len(dimension_names) != len(set(dimension_names)):
            raise ValueError("Evaluation dimension names must be unique")
        return self


class InvestmentFrameworkAnalysisContext(BaseModel):
    """Read-only adapter payload for future Agent context assembly."""

    schema_version: Literal["investment-framework-context-v1"] = (
        "investment-framework-context-v1"
    )
    framework_id: int = Field(..., ge=1)
    framework_version: int = Field(..., ge=1)
    content: InvestmentFrameworkContent
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", frozen=True)
