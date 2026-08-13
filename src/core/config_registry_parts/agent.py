"""Agent configuration field definitions."""

from __future__ import annotations

import ast
from pathlib import Path as _Path
from typing import Any, Dict

from src.config import AGENT_CONTEXT_COMPRESSION_PROFILES, AGENT_MAX_STEPS_DEFAULT

# Read runtime-guard defaults/enums from guards.py source without importing the
# heavy src.agent.runtime package (avoids package __init__ side effects).
def _load_runtime_guard_contract() -> Dict[str, Any]:
    guards_path = _Path(__file__).resolve().parents[2] / "agent" / "runtime" / "guards.py"
    tree = ast.parse(guards_path.read_text(encoding="utf-8"), filename=str(guards_path))
    constants: Dict[str, Any] = {}
    policy_values: list = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith("DEFAULT_"):
                    constants[target.id] = ast.literal_eval(node.value)
        elif isinstance(node, ast.ClassDef) and node.name == "StageFailurePolicy":
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            policy_values.append(ast.literal_eval(item.value))
    required = (
        "DEFAULT_TOOL_TIMEOUT_SECONDS",
        "DEFAULT_MAX_IDENTICAL_TOOL_CALLS",
        "DEFAULT_MAX_STAGE_ENTRIES",
    )
    missing = [name for name in required if name not in constants]
    if missing or not policy_values:
        raise RuntimeError(
            f"Unable to extract runtime guard contract from {guards_path}: "
            f"missing={missing}, policies={policy_values}"
        )
    return {
        "defaults": constants,
        "policy_values": policy_values,
    }

_RUNTIME_GUARD_CONTRACT = _load_runtime_guard_contract()
DEFAULT_TOOL_TIMEOUT_SECONDS = _RUNTIME_GUARD_CONTRACT["defaults"]["DEFAULT_TOOL_TIMEOUT_SECONDS"]
DEFAULT_MAX_IDENTICAL_TOOL_CALLS = _RUNTIME_GUARD_CONTRACT["defaults"]["DEFAULT_MAX_IDENTICAL_TOOL_CALLS"]
DEFAULT_MAX_STAGE_ENTRIES = _RUNTIME_GUARD_CONTRACT["defaults"]["DEFAULT_MAX_STAGE_ENTRIES"]
_STAGE_FAILURE_POLICY_VALUES = list(_RUNTIME_GUARD_CONTRACT["policy_values"])
_STAGE_FAILURE_POLICY_OPTIONS = [
    {
        "label": "Isolate (degrade non-critical stages)",
        "value": "isolate",
    },
    {
        "label": "Fail fast (stop pipeline on stage failure)",
        "value": "fail_fast",
    },
]
# Keep option values bound to extracted enum values (order may differ from labels).
if set(opt["value"] for opt in _STAGE_FAILURE_POLICY_OPTIONS) != set(_STAGE_FAILURE_POLICY_VALUES):
    _STAGE_FAILURE_POLICY_OPTIONS = [
        {"label": value, "value": value} for value in _STAGE_FAILURE_POLICY_VALUES
    ]

AGENT_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "AGENT_MODE": {
        "title": "Agent Mode",
        "description": "Enable ReAct Agent for stock analysis.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 10,
        "help_key": "settings.agent.AGENT_MODE",
        "examples": [
            "AGENT_MODE=true",
            "AGENT_MODE=false",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_GENERATION_BACKEND": {
        "title": "Ask-Stock Generation Method",
        "description": "Generation method used by the ask-stock assistant to generate replies and use tools.",
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "auto",
        "options": [
            {"label": "Auto", "value": "auto"},
            {"label": "Default model settings", "value": "litellm"},
            {"label": "Codex CLI (local)", "value": "codex_cli"},
            {"label": "Claude Code CLI (local)", "value": "claude_code_cli"},
            {"label": "OpenCode CLI (local)", "value": "opencode_cli"},
        ],
        "validation": {
            "enum": [
                "auto",
                "litellm",
                "codex_cli",
                "claude_code_cli",
                "opencode_cli",
            ]
        },
        "display_order": 2,
        "help_key": "settings.agent.AGENT_GENERATION_BACKEND",
        "examples": [
            "AGENT_GENERATION_BACKEND=auto",
            "AGENT_GENERATION_BACKEND=litellm",
            "AGENT_GENERATION_BACKEND=codex_cli",
            "AGENT_GENERATION_BACKEND=claude_code_cli",
            "AGENT_GENERATION_BACKEND=opencode_cli",
        ],
        "docs": [
            {
                "label": "LLM 配置指南",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/LLM_CONFIG_GUIDE.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_FEATURES_ACKNOWLEDGED_OFF": {
        "title": "Acknowledge Agent Features Off",
        "description": (
            "Confirm that Q&A Agent features are not needed. Settles the Agent model "
            "readiness check when neither an API model nor a local CLI backend is available."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 3,
        "help_key": "settings.agent.AGENT_FEATURES_ACKNOWLEDGED_OFF",
        "examples": [
            "AGENT_FEATURES_ACKNOWLEDGED_OFF=false",
            "AGENT_FEATURES_ACKNOWLEDGED_OFF=true",
        ],
        "docs": [
            {
                "label": "LLM 配置指南",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/LLM_CONFIG_GUIDE.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_MAX_STEPS": {
        "title": "Agent Max Steps",
        "description": f"Maximum reasoning-step limit for Agent mode. At the default ({AGENT_MAX_STEPS_DEFAULT}), each sub-agent keeps its own preset. When raised above {AGENT_MAX_STEPS_DEFAULT}, all sub-agents adopt this value. When lowered below a sub-agent's preset, that sub-agent is capped at this value.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": str(AGENT_MAX_STEPS_DEFAULT),
        "options": [],
        "validation": {"min": 1, "max": 50},
        "display_order": 20,
        "help_key": "settings.agent.AGENT_MAX_STEPS",
        "examples": [
            f"AGENT_MAX_STEPS={AGENT_MAX_STEPS_DEFAULT}",
            "AGENT_MAX_STEPS=25",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_SKILLS": {
        "title": "Agent Strategies",
        "description": "Comma-separated list of active agent strategy skills. Leave empty to use the primary default strategy skill declared in metadata (built-in default: bull_trend). When set to specific skills (not 'all'), scheduled tasks will automatically use the Agent pipeline.",
        "category": "agent",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {},
        "display_order": 30,
        "help_key": "settings.agent.AGENT_SKILLS",
        "examples": [
            "AGENT_SKILLS=",
            "AGENT_SKILLS=bull_trend,mean_reversion",
            "AGENT_SKILLS=all",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_SKILL_DIR": {
        "title": "Agent Strategy Dir",
        "description": "Directory containing agent strategy-skill definition files (YAML or SKILL.md bundles).",
        "category": "agent",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "strategies",
        "options": [],
        "validation": {},
        "display_order": 40,
        "help_key": "settings.agent.AGENT_SKILL_DIR",
        "examples": [
            "AGENT_SKILL_DIR=strategies",
            "AGENT_SKILL_DIR=my_strategies",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_NL_ROUTING": {
        "title": "Agent NL Routing",
        "description": "Enable natural-language routing in bot dispatcher. When on, high-confidence stock queries in private chat (or @mentions) are routed to the agent even without an explicit command.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 50,
        "help_key": "settings.agent.AGENT_NL_ROUTING",
        "examples": [
            "AGENT_NL_ROUTING=true",
            "AGENT_NL_ROUTING=false",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_ARCH": {
        "title": "Agent Architecture",
        "description": "Agent execution architecture. 'single' uses the classic ReAct executor; 'multi' uses the orchestrator pipeline with specialised sub-agents.",
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "single",
        "options": [
            {"label": "Single Agent", "value": "single"},
            {"label": "Multi Agent (Orchestrator)", "value": "multi"},
        ],
        "validation": {},
        "display_order": 60,
        "help_key": "settings.agent.AGENT_ARCH",
        "examples": [
            "AGENT_ARCH=single",
            "AGENT_ARCH=multi",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_ORCHESTRATOR_MODE": {
        "title": "Orchestrator Mode",
        "description": "Pipeline mode when AGENT_ARCH=multi. 'quick' (tech→decision), 'standard' (tech→intel→decision), 'full' (tech→intel→risk→decision), 'specialist' (full + per-strategy specialist agents).",
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "standard",
        "options": [
            {"label": "Quick", "value": "quick"},
            {"label": "Standard", "value": "standard"},
            {"label": "Full", "value": "full"},
            {"label": "Specialist", "value": "specialist"},
        ],
        "validation": {"enum": ["quick", "standard", "full", "specialist", "strategy", "skill"]},
        "display_order": 61,
        "help_key": "settings.agent.AGENT_ORCHESTRATOR_MODE",
        "examples": [
            "AGENT_ORCHESTRATOR_MODE=standard",
            "AGENT_ORCHESTRATOR_MODE=full",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_ORCHESTRATOR_TIMEOUT_S": {
        "title": "Agent Timeout",
        "description": "Shared timeout budget in seconds for Agent execution. Single-agent runs use it as the overall ReAct loop budget; multi-agent mode uses it as the cooperative pipeline budget. Set to 0 to disable.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "600",
        "unit": "s",
        "options": [],
        "validation": {"min": 0, "max": 3600},
        "display_order": 62,
        "help_key": "settings.agent.AGENT_ORCHESTRATOR_TIMEOUT_S",
        "examples": [
            "AGENT_ORCHESTRATOR_TIMEOUT_S=600",
            "AGENT_ORCHESTRATOR_TIMEOUT_S=0",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_MODE_BUDGET_ENABLED": {
        "title": "Mode Hard Budget Enabled",
        "description": "Enable hard per-mode budgets for LLM turns, tool calls, and estimated cost. On breach the run terminates with an explicit budget reason (never silent success). Residual wall-clock skips remain budget_skip under the same diagnostic snapshot.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 351,
        "help_key": "settings.agent.AGENT_MODE_BUDGET_ENABLED",
        "examples": [
            "AGENT_MODE_BUDGET_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Full guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_MODE_BUDGET_MAX_LLM_TURNS": {
        "title": "Mode Budget Max LLM Turns (global)",
        "description": "Optional global tightener for per-mode LLM turn caps. 0 keeps mode defaults (quick=6, standard=10, full/specialist=12, chat=10). Exceeding terminates with budget_turns.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0",
        "options": [],
        "validation": {"min": 0, "max": 100},
        "display_order": 352,
        "help_key": "settings.agent.AGENT_MODE_BUDGET_MAX_LLM_TURNS",
        "examples": [
            "AGENT_MODE_BUDGET_MAX_LLM_TURNS=0",
        ],
        "docs": [
            {
                "label": "Full guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_MODE_BUDGET_MAX_TOOL_CALLS": {
        "title": "Mode Budget Max Tool Calls (global)",
        "description": "Optional global tightener for per-mode tool-call caps. 0 keeps mode defaults. Exceeding terminates with budget_tools.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0",
        "options": [],
        "validation": {"min": 0, "max": 500},
        "display_order": 353,
        "help_key": "settings.agent.AGENT_MODE_BUDGET_MAX_TOOL_CALLS",
        "examples": [
            "AGENT_MODE_BUDGET_MAX_TOOL_CALLS=0",
        ],
        "docs": [
            {
                "label": "Full guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_MODE_BUDGET_MAX_COST_USD": {
        "title": "Mode Budget Max Cost USD (global)",
        "description": "Optional global tightener for per-mode estimated USD cost caps. 0 keeps mode defaults. Exceeding terminates with budget_cost.",
        "category": "agent",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0",
        "options": [],
        "validation": {"min": 0},
        "display_order": 354,
        "help_key": "settings.agent.AGENT_MODE_BUDGET_MAX_COST_USD",
        "examples": [
            "AGENT_MODE_BUDGET_MAX_COST_USD=0",
        ],
        "docs": [
            {
                "label": "Full guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_MODE_BUDGET_MAX_TOKENS": {
        "title": "Mode Budget Max Tokens (global)",
        "description": "Optional global hard token ceiling across the analysis run. 0 disables the token dimension (mode defaults also leave tokens unlimited unless set).",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0",
        "options": [],
        "validation": {"min": 0},
        "display_order": 355,
        "help_key": "settings.agent.AGENT_MODE_BUDGET_MAX_TOKENS",
        "examples": [
            "AGENT_MODE_BUDGET_MAX_TOKENS=0",
        ],
        "docs": [
            {
                "label": "Full guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
"SKILL_OPINION_RECORDING_ENABLED": {
        "title": "Skill Opinion Recording",
        "description": (
            "When enabled, record each valid individual skill opinion into the "
            "offline outcome-evaluation store after skill aggregation (and "
            "materialize from saved reports when analysis history is available). "
            "Default off keeps analysis output and database writes unchanged. "
            "Does not alter runtime aggregation weights."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 62,
        "help_key": "settings.agent.SKILL_OPINION_RECORDING_ENABLED",
        "examples": [
            "SKILL_OPINION_RECORDING_ENABLED=false",
            "SKILL_OPINION_RECORDING_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Skill Opinion Outcome Evaluation",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/skill-opinion-outcome-evaluation.md",
            },
        ],
        "warning_codes": [],
    },

    "SKILL_OPINION_OUTCOME_WEIGHTS_ENABLED": {
        "title": "Skill Opinion Outcome Weights",
        "description": (
            "When enabled, conservatively weight strategy-skill opinions from "
            "sufficient attributable Outcome samples (Beta(15,15) prior, terminal "
            "unable penalty, evidence-strength averaging, multiplicative bounds "
            "[1/1.2, 1.2]). Default off keeps the aggregation path byte-identical "
            "to the prior backtest/memory weighting behavior. Fail-neutral (1.0) "
            "for missing, insufficient, malformed, or mismatched-version buckets."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 62,
        "help_key": "settings.agent.SKILL_OPINION_OUTCOME_WEIGHTS_ENABLED",
        "examples": [
            "SKILL_OPINION_OUTCOME_WEIGHTS_ENABLED=false",
            "SKILL_OPINION_OUTCOME_WEIGHTS_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Skill Opinion Outcome Evaluation",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/skill-opinion-outcome-evaluation.md",
            },
        ],
        "warning_codes": [],
    },
    "DECISION_PROFILE_CALIBRATION_ENABLED": {
        "title": "Decision Profile Outcome Calibration",
        "description": (
            "When enabled, GET /api/v1/decision-signals/outcomes/stats includes "
            "profile_calibration breakdowns (profile, action, horizon, market "
            "phase, data quality, profile source) with a 30-completed-sample "
            "gate per exact bucket. Default off keeps the stats response "
            "compatible with pre-calibration clients and does not change "
            "evaluation or persistence."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 63,
        "help_key": "settings.agent.DECISION_PROFILE_CALIBRATION_ENABLED",
        "examples": [
            "DECISION_PROFILE_CALIBRATION_ENABLED=false",
            "DECISION_PROFILE_CALIBRATION_ENABLED=true",
        ],
        "docs": [
            {
                "label": "DecisionSignal documentation",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/decision-signals.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_CRITIC_ENABLED": {
        "title": "Bounded Multi-Agent Critic",
        "description": "Run one tool-free evidence Critic before Decision in Native Multi analysis. The Critic may request at most one retry of an already-entered intelligence or catalog-backed skill stage.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 63,
        "help_key": "settings.agent.AGENT_CRITIC_ENABLED",
        "examples": [
            "AGENT_CRITIC_ENABLED=false",
            "AGENT_CRITIC_ENABLED=true",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_INVESTMENT_COMMITTEE_MODE": {
        "title": "Investment Committee Mode",
        "description": (
            "Default-off preset that activates curated investment-persona Skills "
            "through the existing multi-agent specialist path and StrategyEngine "
            "synthesis. Does not replace Single/Multi analysis when disabled. "
            "Expect higher token cost when enabled. Requires AGENT_ARCH=multi and "
            "AGENT_ORCHESTRATOR_MODE=specialist for persona specialists to run."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 64,
        "help_key": "settings.agent.AGENT_INVESTMENT_COMMITTEE_MODE",
        "examples": [
            "AGENT_INVESTMENT_COMMITTEE_MODE=false",
            "AGENT_INVESTMENT_COMMITTEE_MODE=true",
        ],
        "docs": [
            {
                "label": "Investment Committee Mode",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/investment-committee-mode_EN.md",
            },
            {
                "label": "投资委员会模式",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/investment-committee-mode.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_RESEARCH_PERSONA": {
        "title": "Research Persona Preset",
        "description": (
            "Default-off research-stance preset that shapes Agent tone, risk framing, "
            "and conclusion style (rational_analyst | risk_guardian | long_term_compounder). "
            "Empty keeps default behavior. The active personal investment framework "
            "research_stance field takes precedence. Style labels are not performance claims."
        ),
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [
            {"value": "", "label": "Off (default)"},
            {"value": "rational_analyst", "label": "Rational Analyst"},
            {"value": "risk_guardian", "label": "Risk Guardian"},
            {"value": "long_term_compounder", "label": "Long-term Compounder"},
        ],
        "validation": {},
        "display_order": 641,
        "help_key": "settings.agent.AGENT_RESEARCH_PERSONA",
        "examples": [
            "AGENT_RESEARCH_PERSONA=",
            "AGENT_RESEARCH_PERSONA=rational_analyst",
        ],
        "docs": [
            {
                "label": "Investor Personas",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/investor-personas_EN.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_RESEARCH_PERSONA_CUSTOM": {
        "title": "Custom Research Stance",
        "description": (
            "Optional free-form research-stance text used when no personal investment "
            "framework research_stance is active. Leave empty by default. Prefer the "
            "versioned framework field for durable custom stance persistence. The value "
            "is untrusted preference data and cannot alter Agent Soul, ToolSurface, or permissions."
        ),
        "category": "agent",
        "data_type": "string",
        "ui_control": "textarea",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {"max_length": 2000},
        "display_order": 642,
        "help_key": "settings.agent.AGENT_RESEARCH_PERSONA_CUSTOM",
        "examples": ["AGENT_RESEARCH_PERSONA_CUSTOM="],
        "docs": [
            {
                "label": "Investor Personas",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/investor-personas_EN.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_RISK_OVERRIDE": {
        "title": "Risk Agent Override",
        "description": "Allow the risk agent to veto buy signals when critical risk flags are detected.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 63,
        "help_key": "settings.agent.AGENT_RISK_OVERRIDE",
        "examples": [
            "AGENT_RISK_OVERRIDE=true",
            "AGENT_RISK_OVERRIDE=false",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "RISK_GATE_PROFILE": {
        "title": "Risk Manager Profile",
        "description": "Select the mandatory final-action risk thresholds. The gate cannot be disabled and failures fail closed.",
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "balanced",
        "options": [
            {"label": "Conservative", "value": "conservative"},
            {"label": "Balanced", "value": "balanced"},
            {"label": "Aggressive", "value": "aggressive"},
        ],
        "validation": {
            "enum": ["conservative", "balanced", "aggressive"],
        },
        "display_order": 63,
        "help_key": "settings.agent.RISK_GATE_PROFILE",
        "examples": [
            "RISK_GATE_PROFILE=conservative",
            "RISK_GATE_PROFILE=balanced",
            "RISK_GATE_PROFILE=aggressive",
        ],
        "docs": [
            {
                "label": "Risk Manager gate",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/risk-manager-gate_EN.md",
            },
            {
                "label": "风控经理闸门",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/risk-manager-gate.md",
            },
        ],
        "warning_codes": [],
    },
    "ANALYSIS_QUALITY_GATE_ENABLED": {
        "title": "Analysis Quality Gate",
        "description": (
            "Run the pipeline quality gate that binds factual claims in the "
            "conclusion to input evidence using the same factuality / "
            "boundary_honesty dimensions as the offline agent-eval suite. "
            "Default on; disable only for diagnostics."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 630,
        "help_key": "settings.agent.ANALYSIS_QUALITY_GATE_ENABLED",
        "examples": [
            "ANALYSIS_QUALITY_GATE_ENABLED=true",
            "ANALYSIS_QUALITY_GATE_ENABLED=false",
        ],
        "docs": [
            {
                "label": "Analysis quality gate",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/analysis-quality-gate_EN.md",
            },
            {
                "label": "分析质量门",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/analysis-quality-gate.md",
            },
            {
                "label": "Agent eval dimensions",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-eval-dimensions_EN.md",
            },
        ],
        "warning_codes": [],
    },
    "ANALYSIS_QUALITY_GATE_ON_FAILURE": {
        "title": "Quality Gate Failure Policy",
        "description": (
            "When ungrounded factual claims are found: annotate demotes them "
            "to model opinion (default); intercept fails the analysis result. "
            "Gate-internal errors always fail closed to annotate."
        ),
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "annotate",
        "options": [
            {"label": "Annotate (default)", "value": "annotate"},
            {"label": "Intercept", "value": "intercept"},
        ],
        "validation": {
            "enum": ["annotate", "intercept"],
        },
        "display_order": 631,
        "help_key": "settings.agent.ANALYSIS_QUALITY_GATE_ON_FAILURE",
        "examples": [
            "ANALYSIS_QUALITY_GATE_ON_FAILURE=annotate",
            "ANALYSIS_QUALITY_GATE_ON_FAILURE=intercept",
        ],
        "docs": [
            {
                "label": "Analysis quality gate",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/analysis-quality-gate_EN.md",
            },
            {
                "label": "分析质量门",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/analysis-quality-gate.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_MULTI_STRATEGY_DELIBERATION": {
        "title": "Multi-Strategy Deliberation",
        "description": "Enable multi-strategy deliberation, concurrent specialist scheduling, and final disagreement explanation. Default off preserves Phase-1 synthesis byte-for-byte.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 64,
        "help_key": "settings.agent.AGENT_MULTI_STRATEGY_DELIBERATION",
        "examples": ["AGENT_MULTI_STRATEGY_DELIBERATION=false", "AGENT_MULTI_STRATEGY_DELIBERATION=true"],
        "docs": [{"label": "Multi-strategy contract", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/multi-strategy-contract.md"}],
        "warning_codes": [],
    },

    "AGENT_DEEP_RESEARCH_BUDGET": {
        "title": "Deep Research Token Budget",
        "description": "Maximum token budget for Deep Research planning, follow-up research, and final synthesis.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "30000",
        "options": [],
        "validation": {"min": 5000, "max": 100000},
        "display_order": 64,
        "help_key": "settings.agent.DEEP_RESEARCH",
        "examples": [
            "AGENT_DEEP_RESEARCH_BUDGET=30000",
            "AGENT_DEEP_RESEARCH_BUDGET=50000",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_DEEP_RESEARCH_TIMEOUT": {
        "title": "Deep Research Timeout",
        "description": "Maximum seconds allowed for a Deep Research request before returning a timeout response.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "180",
        "options": [],
        "validation": {"min": 30, "max": 600},
        "display_order": 65,
        "help_key": "settings.agent.DEEP_RESEARCH",
        "examples": [
            "AGENT_DEEP_RESEARCH_TIMEOUT=180",
            "AGENT_DEEP_RESEARCH_TIMEOUT=300",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_EVENT_IMPACT_CONTEXT_ENABLED": {
        "title": "Alert Impact Context",
        "description": (
            "When enabled, triggered alert notifications include a managed-data impact "
            "context block: what happened, why it matters, and whether the symbol is on "
            "the watchlist or in portfolio holdings. Uses intelligence items, portfolio "
            "snapshots without realtime refresh, and recent analysis history only."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 72,
        "help_key": "settings.agent.event_impact_context",
        "examples": [
            "AGENT_EVENT_IMPACT_CONTEXT_ENABLED=true",
            "AGENT_EVENT_IMPACT_CONTEXT_ENABLED=false",
        ],
        "docs": [
            {
                "label": "告警中心文档",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/alerts.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_MEMORY_ENABLED": {
        "title": "Agent Memory",
        "description": "Enable the memory & calibration system. Tracks prediction accuracy and adjusts agent confidence over time.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 66,
        "help_key": "settings.agent.AGENT_MEMORY_ENABLED",
        "examples": [
            "AGENT_MEMORY_ENABLED=true",
            "AGENT_MEMORY_ENABLED=false",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "LAYERED_MEMORY_COLLECTION_ENABLED": {
        "title": "Layered Memory Collection",
        "description": "Collect bounded per-principal records for the layered Agent memory service.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 661,
        "help_key": "settings.agent.AGENT_MEMORY_ENABLED",
        "examples": ["LAYERED_MEMORY_COLLECTION_ENABLED=false"],
        "docs": [{
            "label": "Agent memory guide",
            "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-memory.md",
        }],
        "warning_codes": [],
    },
    "LAYERED_MEMORY_RETENTION_DAYS": {
        "title": "Layered Memory Retention Days",
        "description": "Maximum retention window for layered Agent memory records.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "90",
        "options": [],
        "validation": {"min": 1, "max": 3650},
        "display_order": 662,
        "help_key": "settings.agent.AGENT_MEMORY_ENABLED",
        "examples": ["LAYERED_MEMORY_RETENTION_DAYS=90"],
        "docs": [{
            "label": "Agent memory guide",
            "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-memory.md",
        }],
        "warning_codes": [],
    },
    "LAYERED_MEMORY_VECTOR_ENABLED": {
        "title": "Layered Memory Vector Search",
        "description": "Enable optional vector retrieval for layered Agent memory.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 663,
        "help_key": "settings.agent.AGENT_MEMORY_ENABLED",
        "examples": ["LAYERED_MEMORY_VECTOR_ENABLED=false"],
        "docs": [{
            "label": "Agent memory guide",
            "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-memory.md",
        }],
        "warning_codes": [],
    },
    "LAYERED_MEMORY_MAX_RECORDS_PER_PRINCIPAL": {
        "title": "Layered Memory Record Limit",
        "description": "Maximum layered-memory records retained for each principal.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "200",
        "options": [],
        "validation": {"min": 1, "max": 200},
        "display_order": 664,
        "help_key": "settings.agent.AGENT_MEMORY_ENABLED",
        "examples": ["LAYERED_MEMORY_MAX_RECORDS_PER_PRINCIPAL=200"],
        "docs": [{
            "label": "Agent memory guide",
            "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-memory.md",
        }],
        "warning_codes": [],
    },
    "LAYERED_MEMORY_AUDIT_ENABLED": {
        "title": "Layered Memory Audit",
        "description": "Write audit events for layered Agent memory collection and retrieval.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 665,
        "help_key": "settings.agent.AGENT_MEMORY_ENABLED",
        "examples": ["LAYERED_MEMORY_AUDIT_ENABLED=true"],
        "docs": [{
            "label": "Agent memory guide",
            "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-memory.md",
        }],
        "warning_codes": [],
    },
    "AGENT_PLANNING_ENABLED": {
        "title": "Agent Planning Loop",
        "description": (
            "Opt-in plan→act→observe→replan on the Agent analysis RUN path "
            "(AgentExecutor.run). Default is off so the classic daily pipeline is unchanged. "
            "When enabled, the planner proposes bounded steps, tools run through BoundToolSession, "
            "and failures terminate with explicit reasons (no fail-open success). "
            "See docs/agent-planning-engine_EN.md."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 660,
        "help_key": "settings.agent.AGENT_PLANNING_ENABLED",
        "examples": [
            "AGENT_PLANNING_ENABLED=false",
            "AGENT_PLANNING_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Agent planning guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-planning-engine_EN.md",
            },
            {
                "label": "Agent 规划引擎（中文）",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-planning-engine.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_PLANNING_STRATEGY": {
        "title": "Agent Planning Strategy",
        "description": (
            "Planner strategy when AGENT_PLANNING_ENABLED=true. "
            "'template' uses the deterministic stock-analysis template (default); "
            "'llm' uses the Agent LLM adapter for proposals (falls back to template on failure)."
        ),
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "template",
        "options": [
            {"label": "Template (deterministic)", "value": "template"},
            {"label": "LLM proposal", "value": "llm"},
        ],
        "validation": {"enum": ["template", "llm"]},
        "display_order": 661,
        "help_key": "settings.agent.AGENT_PLANNING_STRATEGY",
        "examples": [
            "AGENT_PLANNING_STRATEGY=template",
            "AGENT_PLANNING_STRATEGY=llm",
        ],
        "docs": [
            {
                "label": "Agent planning guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-planning-engine_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_PLANNING_MAX_PLAN_STEPS": {
        "title": "Planning Max Plan Steps",
        "description": "Maximum steps allowed in one plan proposal (1-16). Default 8.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "8",
        "options": [],
        "validation": {"min": 1, "max": 16},
        "display_order": 662,
        "help_key": "settings.agent.AGENT_PLANNING_MAX_PLAN_STEPS",
        "examples": [
            "AGENT_PLANNING_MAX_PLAN_STEPS=8",
            "AGENT_PLANNING_MAX_PLAN_STEPS=4",
        ],
        "docs": [
            {
                "label": "Agent planning guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-planning-engine_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_PLANNING_MAX_REPLANS": {
        "title": "Planning Proposal Retries",
        "description": (
            "Maximum proposal retries after validation/LLM failure during plan creation (0-3). "
            "Default 1. Separate from observation-driven replans during execution."
        ),
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "1",
        "options": [],
        "validation": {"min": 0, "max": 3},
        "display_order": 663,
        "help_key": "settings.agent.AGENT_PLANNING_MAX_REPLANS",
        "examples": [
            "AGENT_PLANNING_MAX_REPLANS=1",
            "AGENT_PLANNING_MAX_REPLANS=0",
        ],
        "docs": [
            {
                "label": "Agent planning guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-planning-engine_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_PLANNING_MAX_TOKENS": {
        "title": "Planning Proposal Token Budget",
        "description": "Maximum planner LLM tokens when strategy=llm (1-8192). Default 1500.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "1500",
        "options": [],
        "validation": {"min": 1, "max": 8192},
        "display_order": 664,
        "help_key": "settings.agent.AGENT_PLANNING_MAX_TOKENS",
        "examples": [
            "AGENT_PLANNING_MAX_TOKENS=1500",
            "AGENT_PLANNING_MAX_TOKENS=2048",
        ],
        "docs": [
            {
                "label": "Agent planning guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-planning-engine_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_PLANNING_PROPOSAL_TIMEOUT_SECONDS": {
        "title": "Planning Proposal Timeout",
        "description": "Wall-clock seconds for one plan proposal attempt (0.1-60). Default 30. Non-finite values are rejected at runtime.",
        "category": "agent",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "30",
        "options": [],
        "validation": {"min": 0.1, "max": 60},
        "display_order": 665,
        "help_key": "settings.agent.AGENT_PLANNING_PROPOSAL_TIMEOUT_SECONDS",
        "examples": [
            "AGENT_PLANNING_PROPOSAL_TIMEOUT_SECONDS=30",
            "AGENT_PLANNING_PROPOSAL_TIMEOUT_SECONDS=15",
        ],
        "docs": [
            {
                "label": "Agent planning guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-planning-engine_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_PLANNING_MAX_TOTAL_TOOL_CALLS": {
        "title": "Planning Max Tool Calls",
        "description": (
            "Hard upper bound on tool invocations during plan→act→observe execution (1-32). "
            "Default 16. Exceeding terminates with max_tool_calls_exceeded."
        ),
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "16",
        "options": [],
        "validation": {"min": 1, "max": 32},
        "display_order": 666,
        "help_key": "settings.agent.AGENT_PLANNING_MAX_TOTAL_TOOL_CALLS",
        "examples": [
            "AGENT_PLANNING_MAX_TOTAL_TOOL_CALLS=16",
            "AGENT_PLANNING_MAX_TOTAL_TOOL_CALLS=8",
        ],
        "docs": [
            {
                "label": "Agent planning guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-planning-engine_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_PLANNING_MAX_OBSERVATION_REPLANS": {
        "title": "Planning Observation Replans",
        "description": (
            "Maximum observation-driven replans after a failed step (0-3). Default 1. "
            "When exhausted, execution terminates with max_observation_replans_exceeded."
        ),
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "1",
        "options": [],
        "validation": {"min": 0, "max": 3},
        "display_order": 667,
        "help_key": "settings.agent.AGENT_PLANNING_MAX_OBSERVATION_REPLANS",
        "examples": [
            "AGENT_PLANNING_MAX_OBSERVATION_REPLANS=1",
            "AGENT_PLANNING_MAX_OBSERVATION_REPLANS=0",
        ],
        "docs": [
            {
                "label": "Agent planning guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-planning-engine_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_PLANNING_EXEC_TIMEOUT_SECONDS": {
        "title": "Planning Execution Timeout",
        "description": (
            "Wall-clock seconds for the full plan→act→observe loop (0.1-120). Default 60. "
            "Exceeding terminates with execution_timeout. Non-finite values are rejected."
        ),
        "category": "agent",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "60",
        "options": [],
        "validation": {"min": 0.1, "max": 120},
        "display_order": 668,
        "help_key": "settings.agent.AGENT_PLANNING_EXEC_TIMEOUT_SECONDS",
        "examples": [
            "AGENT_PLANNING_EXEC_TIMEOUT_SECONDS=60",
            "AGENT_PLANNING_EXEC_TIMEOUT_SECONDS=30",
        ],
        "docs": [
            {
                "label": "Agent planning guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-planning-engine_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_PLANNING_ON_STEP_FAILURE": {
        "title": "Planning Step Failure Policy",
        "description": (
            "When a plan step's tool call fails: 'replan' (if observation replan budget remains) "
            "or 'terminate' immediately. Default replan. Failures never fail-open as success."
        ),
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "replan",
        "options": [
            {"label": "Replan (if budget remains)", "value": "replan"},
            {"label": "Terminate immediately", "value": "terminate"},
        ],
        "validation": {"enum": ["replan", "terminate"]},
        "display_order": 669,
        "help_key": "settings.agent.AGENT_PLANNING_ON_STEP_FAILURE",
        "examples": [
            "AGENT_PLANNING_ON_STEP_FAILURE=replan",
            "AGENT_PLANNING_ON_STEP_FAILURE=terminate",
        ],
        "docs": [
            {
                "label": "Agent planning guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-planning-engine_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
    },
    "AGENT_SKILL_AUTOWEIGHT": {
        "title": "Auto-Weight Strategies",
        "description": "Automatically weight strategy-skill opinions by their historical backtest performance.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 67,
        "help_key": "settings.agent.AGENT_SKILL_AUTOWEIGHT",
        "examples": [
            "AGENT_SKILL_AUTOWEIGHT=true",
            "AGENT_SKILL_AUTOWEIGHT=false",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_SKILL_ROUTING": {
        "title": "Strategy Routing",
        "description": "Strategy-skill selection mode. 'auto' detects market regime and picks relevant skills; 'manual' uses AGENT_SKILLS list only.",
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "auto",
        "options": [
            {"label": "Auto (Regime-based)", "value": "auto"},
            {"label": "Manual (Use AGENT_SKILLS)", "value": "manual"},
        ],
        "validation": {},
        "display_order": 68,
        "help_key": "settings.agent.AGENT_SKILL_ROUTING",
        "examples": [
            "AGENT_SKILL_ROUTING=auto",
            "AGENT_SKILL_ROUTING=manual",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "MARKET_REGIME_ENABLED": {
        "title": "Market Regime Detection",
        "description": "Enable explainable rule-based market regime detection and adaptive analysis focus. When unclear, labels unknown instead of forcing a side.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 681,
        "help_key": "settings.agent.market_regime",
        "examples": [
            "MARKET_REGIME_ENABLED=true",
            "MARKET_REGIME_ENABLED=false",
        ],
        "docs": [
            {
                "label": "Market Regime Detection",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/market-regime.md",
            },
        ],
        "warning_codes": [],
    },
    "MARKET_REGIME_OVERRIDE": {
        "title": "Market Regime Override",
        "description": "Optional forced regime label (trending_up/trending_down/sideways/volatile/unknown). Empty uses automatic rule-based detection.",
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [
            {"label": "Auto (rules)", "value": ""},
            {"label": "Trending up", "value": "trending_up"},
            {"label": "Trending down", "value": "trending_down"},
            {"label": "Sideways", "value": "sideways"},
            {"label": "Volatile", "value": "volatile"},
            {"label": "Unknown", "value": "unknown"},
        ],
        "validation": {},
        "display_order": 682,
        "help_key": "settings.agent.market_regime",
        "examples": [
            "MARKET_REGIME_OVERRIDE=",
            "MARKET_REGIME_OVERRIDE=trending_up",
            "MARKET_REGIME_OVERRIDE=unknown",
        ],
        "docs": [
            {
                "label": "Market Regime Detection",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/market-regime.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_CONTEXT_COMPRESSION_ENABLED": {

        "title": "Agent Context Compression",
        "description": "Enable rolling compression of visible Agent chat history. Default is off to preserve existing behavior.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 72,
        "help_key": "settings.agent.context_compression",
        "examples": [
            "AGENT_CONTEXT_COMPRESSION_ENABLED=false",
            "AGENT_CONTEXT_COMPRESSION_ENABLED=true",
        ],
        "docs": [
            {
                "label": "LLM 配置指南：问股可见对话上下文压缩",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/LLM_CONFIG_GUIDE.md#问股可见对话上下文压缩",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_CONTEXT_COMPRESSION_PROFILE": {
        "title": "Context Compression Profile",
        "description": "Preset for visible chat history compression. Trigger/protected-turn fields can be left empty to follow the selected profile.",
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "balanced",
        "options": [
            {"label": "成本优先", "value": "cost"},
            {"label": "均衡推荐", "value": "balanced"},
            {"label": "长上下文原文优先", "value": "long_context_raw_first"},
        ],
        "validation": {"enum": list(AGENT_CONTEXT_COMPRESSION_PROFILES.keys())},
        "display_order": 73,
        "help_key": "settings.agent.context_compression",
        "examples": [
            "AGENT_CONTEXT_COMPRESSION_PROFILE=balanced",
            "AGENT_CONTEXT_COMPRESSION_PROFILE=cost",
            "AGENT_CONTEXT_COMPRESSION_PROFILE=long_context_raw_first",
        ],
        "docs": [
            {
                "label": "LLM 配置指南：问股可见对话上下文压缩",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/LLM_CONFIG_GUIDE.md#问股可见对话上下文压缩",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS": {
        "title": "Context Compression Trigger Tokens",
        "description": "Token threshold for visible chat history compression. Leave empty to follow the selected compression profile preset.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {"min": 1000, "max": 200000},
        "display_order": 74,
        "help_key": "settings.agent.context_compression",
        "examples": [
            "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS=",
            "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS=12000",
        ],
        "docs": [
            {
                "label": "LLM 配置指南：问股可见对话上下文压缩",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/LLM_CONFIG_GUIDE.md#问股可见对话上下文压缩",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_CONTEXT_PROTECTED_TURNS": {
        "title": "Context Protected Turns",
        "description": "Recent user turns preserved verbatim during visible chat history compression. Leave empty to follow the selected compression profile preset.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {"min": 1, "max": 20},
        "display_order": 75,
        "help_key": "settings.agent.context_compression",
        "examples": [
            "AGENT_CONTEXT_PROTECTED_TURNS=",
            "AGENT_CONTEXT_PROTECTED_TURNS=4",
        ],
        "docs": [
            {
                "label": "LLM 配置指南：问股可见对话上下文压缩",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/LLM_CONFIG_GUIDE.md#问股可见对话上下文压缩",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },

    "AGENT_OBSERVABILITY_ENABLED": {
        "title": "Agent Observability Events",
        "description": (
            "Emit lightweight structured agent run events (phase/tool/model/decision) "
            "with trace and span ids into run diagnostics and the run-flow view. Default on."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 705,
        "help_key": "settings.agent.observability",
        "examples": [
            "AGENT_OBSERVABILITY_ENABLED=true",
            "AGENT_OBSERVABILITY_ENABLED=false",
        ],
        "docs": [
            {
                "label": "Agent Observability",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-observability_EN.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_OBSERVABILITY_DEEP_PAYLOAD": {
        "title": "Agent Observability Deep Payload",
        "description": (
            "When enabled, capture sanitized tool argument/result previews on agent events. "
            "Default off. Prompts, API keys, and other secrets remain redacted."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 706,
        "help_key": "settings.agent.observability",
        "examples": [
            "AGENT_OBSERVABILITY_DEEP_PAYLOAD=false",
            "AGENT_OBSERVABILITY_DEEP_PAYLOAD=true",
        ],
        "docs": [
            {
                "label": "Agent Observability",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-observability_EN.md",
            },
        ],
        "warning_codes": [],
    },
    "PERF_COLLECTION_ENABLED": {
        "title": "Performance Span Collection",
        "description": (
            "Opt-in recording of lightweight performance spans for key paths "
            "(pipeline stages, offline baselines). Default off. When disabled, "
            "collection helpers are no-ops."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 707,
        "help_key": "settings.agent.performance",
        "examples": [
            "PERF_COLLECTION_ENABLED=false",
            "PERF_COLLECTION_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Performance baselines and profiling",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/performance-baseline_EN.md",
            },
        ],
        "warning_codes": [],
    },
    "PERF_PROFILE_ENABLED": {
        "title": "Performance cProfile Flag",
        "description": (
            "Signals that optional stdlib cProfile wrapping is desired for "
            "offline baseline tooling. Default off. Does not auto-profile "
            "production request paths."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 708,
        "help_key": "settings.agent.performance",
        "examples": [
            "PERF_PROFILE_ENABLED=false",
            "PERF_PROFILE_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Performance baselines and profiling",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/performance-baseline_EN.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_EVENT_MONITOR_ENABLED": {
        "title": "Event Monitor",
        "description": "Enable background Event Monitor polling in schedule mode.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 69,
        "help_key": "settings.agent.event_monitor",
        "examples": [
            "AGENT_EVENT_MONITOR_ENABLED=true",
            "AGENT_EVENT_MONITOR_INTERVAL_MINUTES=5",
        ],
        "docs": [
            {
                "label": "告警中心文档",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/alerts.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_EVENT_MONITOR_INTERVAL_MINUTES": {
        "title": "Event Monitor Interval",
        "description": "Polling interval, in minutes, for background Event Monitor checks.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "5",
        "options": [],
        "validation": {"min": 1, "max": 1440},
        "display_order": 70,
        "help_key": "settings.agent.event_monitor",
        "examples": [
            "AGENT_EVENT_MONITOR_INTERVAL_MINUTES=5",
            "AGENT_EVENT_MONITOR_INTERVAL_MINUTES=15",
        ],
        "docs": [
            {
                "label": "告警中心文档",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/alerts.md",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_EVENT_ALERT_RULES_JSON": {
        "title": "Event Alert Rules",
        "description": (
            "JSON array of Event Monitor rules loaded by schedule mode. "
            "Legacy JSON supports only price_cross, price_change_percent, and volume_spike. "
            "Technical indicator, watchlist, portfolio, and market light alert rules "
            "are available through the Alert API/Web center."
        ),
        "category": "agent",
        "data_type": "json",
        "ui_control": "textarea",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {},
        "display_order": 71,
        "help_key": "settings.agent.EVENT_ALERT_RULES_JSON",
        "examples": [
            'AGENT_EVENT_ALERT_RULES_JSON=[{"alert_type":"price_cross","stock_code":"600519","direction":"above","price":1800}]',
            'AGENT_EVENT_ALERT_RULES_JSON=[{"alert_type":"volume_spike","stock_code":"300750","multiplier":2.5}]',
        ],
        "docs": [
            {
                "label": "告警中心文档",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/alerts.md",
            },
        ],
        "warning_codes": ["legacy_json_only_basic_rules"],
    },
    "MULTIMODAL_AGENT_TOOLS_ENABLED": {
        "title": "Enable Multimodal Agent Tools",
        "description": (
            "Opt-in PDF parsing and chart-reading Agent Tools (issue #253). "
            "Default is off. When enabled with MULTIMODAL_FILE_ROOT, Agents may call "
            "parse_financial_pdf and read_price_chart after a process restart. "
            "PDF parsing is local-first; chart reading uses VISION_MODEL and degrades "
            "honestly when vision is unavailable. See docs/multimodal-parsing_EN.md."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
        "display_order": 77,
        "help_key": "settings.agent.MULTIMODAL_AGENT_TOOLS_ENABLED",
        "examples": [
            "MULTIMODAL_AGENT_TOOLS_ENABLED=false",
            "MULTIMODAL_AGENT_TOOLS_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Multimodal parsing guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/multimodal-parsing_EN.md",
            },
            {
                "label": "多模态解析说明（中文）",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/multimodal-parsing.md",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "MULTIMODAL_FILE_ROOT": {
        "title": "Multimodal File Root",
        "description": (
            "Local directory that may contain user-provided PDF and chart files for "
            "multimodal Agent Tools. Paths are sandboxed to this root; URLs and path "
            "traversal are rejected. Required when MULTIMODAL_AGENT_TOOLS_ENABLED=true."
        ),
        "category": "agent",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {},
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
        "display_order": 78,
        "help_key": "settings.agent.MULTIMODAL_FILE_ROOT",
        "examples": [
            "MULTIMODAL_FILE_ROOT=",
            "MULTIMODAL_FILE_ROOT=/var/stockpulse/multimodal",
        ],
        "docs": [
            {
                "label": "Multimodal parsing guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/multimodal-parsing_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "CHART_READ_TIMEOUT_SECONDS": {
        "title": "Chart Read Timeout Seconds",
        "description": (
            "Per-call vision timeout for read_price_chart in seconds (clamped 1-120). "
            "Default 30. Aligns chart reading with OCR-style time bounds. "
            "See docs/multimodal-parsing_EN.md."
        ),
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "30",
        "options": [],
        "validation": {"min": 1, "max": 120},
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
        "display_order": 783,
        "help_key": "settings.agent.CHART_READ_TIMEOUT_SECONDS",
        "examples": [
            "CHART_READ_TIMEOUT_SECONDS=30",
            "CHART_READ_TIMEOUT_SECONDS=60",
        ],
        "docs": [
            {
                "label": "Multimodal parsing guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/multimodal-parsing_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "OCR_AGENT_TOOL_ENABLED": {
        "title": "Enable Offline OCR Agent Tool",
        "description": (
            "Opt-in bounded Tesseract OCR Agent Tool (issue #196). Default is off. "
            "When enabled with OCR_FILE_ROOT or MULTIMODAL_FILE_ROOT and optional "
            "requirements-ocr.txt + system Tesseract, Agents may call "
            "extract_image_text after a process restart. Image bytes stay local; "
            "redacted, untrusted OCR text enters Agent context and may reach a remote "
            "model unless LOCAL_ONLY_MODE=true. Supports screenshot, filing_page, "
            "table_statement, chart_annotation, and embedded pdf_page kinds as "
            "bounded raw-text extraction (not verified tables or decision authority). "
            "See docs/agent-ocr-tool_EN.md."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
        "display_order": 79,
        "help_key": "settings.agent.OCR_AGENT_TOOL_ENABLED",
        "examples": [
            "OCR_AGENT_TOOL_ENABLED=false",
            "OCR_AGENT_TOOL_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Offline OCR guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-ocr-tool_EN.md",
            },
            {
                "label": "离线 OCR 说明（中文）",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-ocr-tool.md",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "OCR_FILE_ROOT": {
        "title": "OCR File Root",
        "description": (
            "Local directory for user-provided images for offline OCR. Paths are "
            "sandboxed to this root. Falls back to MULTIMODAL_FILE_ROOT when empty. "
            "Required (directly or via multimodal root) when OCR_AGENT_TOOL_ENABLED=true."
        ),
        "category": "agent",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {},
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
        "display_order": 80,
        "help_key": "settings.agent.OCR_FILE_ROOT",
        "examples": [
            "OCR_FILE_ROOT=",
            "OCR_FILE_ROOT=/var/stockpulse/ocr-uploads",
        ],
        "docs": [
            {
                "label": "Offline OCR guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-ocr-tool_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "OCR_LANGS": {
        "title": "OCR Languages",
        "description": (
            "Tesseract language codes joined by '+'. Default chi_sim+eng for mixed "
            "Chinese/English statements. Requires matching traineddata packages."
        ),
        "category": "agent",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "chi_sim+eng",
        "options": [],
        "validation": {},
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
        "display_order": 81,
        "help_key": "settings.agent.OCR_LANGS",
        "examples": [
            "OCR_LANGS=chi_sim+eng",
            "OCR_LANGS=eng",
        ],
        "docs": [
            {
                "label": "Offline OCR guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-ocr-tool_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "OCR_TIMEOUT_SECONDS": {
        "title": "OCR Timeout Seconds",
        "description": (
            "Per-call OCR timeout in seconds (clamped 1-120). Default 30."
        ),
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "30",
        "options": [],
        "validation": {"min": 1, "max": 120},
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
        "display_order": 82,
        "help_key": "settings.agent.OCR_TIMEOUT_SECONDS",
        "examples": [
            "OCR_TIMEOUT_SECONDS=30",
            "OCR_TIMEOUT_SECONDS=60",
        ],
        "docs": [
            {
                "label": "Offline OCR guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/agent-ocr-tool_EN.md",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "VALUATION_AGENT_TOOL_ENABLED": {
        "title": "Enable Valuation Agent Tool",
        "description": (
            "Opt-in DCF and relative-valuation Agent Tool. Default is off. When enabled, "
            "Agents may call estimate_stock_valuation after a process restart. Every "
            "estimate includes explicit assumptions and a sensitivity range; missing "
            "fundamentals return insufficient_fundamentals rather than a fabricated number. "
            "See docs/valuation-models_EN.md."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "contract": {
            "requirement": "optional",
            "restart_required": True,
        },
        "display_order": 76,
        "help_key": "settings.agent.VALUATION_AGENT_TOOL_ENABLED",
        "examples": [
            "VALUATION_AGENT_TOOL_ENABLED=false",
            "VALUATION_AGENT_TOOL_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Valuation models guide (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/valuation-models_EN.md",
            },
            {
                "label": "估值模型说明（中文）",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/valuation-models.md",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "REASONING_TRACE_EXPORT_ENABLED": {
        "title": "Reasoning Trace Export",
        "description": (
            "Master switch for the reasoning-trace export API and service gate. "
            "Default off. Exports are redacted but still sensitive."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 724,
        "help_key": "settings.agent.reasoning_trace_export",
        "examples": [
            "REASONING_TRACE_EXPORT_ENABLED=false",
            "REASONING_TRACE_EXPORT_ENABLED=true",
        ],
        "docs": [
            {
                "label": "Reasoning trace export (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/reasoning-trace-export_EN.md",
            },
            {
                "label": "推理轨迹导出（中文）",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/reasoning-trace-export.md",
            },
        ],
        "warning_codes": [],
    },
    "REASONING_TRACE_EXPORT_MAX_CHARS": {
        "title": "Reasoning Trace Max Chars",
        "description": (
            "Character budget for complete reasoning-trace export responses. "
            "Default 500000; clamped to 10000–2000000 when loading config."
        ),
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "500000",
        "options": [],
        "validation": {"min": 10000, "max": 2000000},
        "display_order": 725,
        "help_key": "settings.agent.reasoning_trace_export",
        "examples": [
            "REASONING_TRACE_EXPORT_MAX_CHARS=500000",
            "REASONING_TRACE_EXPORT_MAX_CHARS=100000",
        ],
        "docs": [
            {
                "label": "Reasoning trace export (EN)",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/reasoning-trace-export_EN.md",
            },
            {
                "label": "推理轨迹导出（中文）",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/reasoning-trace-export.md",
            },
        ],
        "warning_codes": [],
    },


    "RESEARCH_PACK_EXPORT_ENABLED": {
        "title": "Research Pack Export",
        "description": (
            "Master switch for one-click research asset package export (ZIP). "
            "Default off. Packages always redact credentials and local paths."
        ),
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 726,
        "help_key": "settings.agent.research_pack_export",
        "examples": ["RESEARCH_PACK_EXPORT_ENABLED=false", "RESEARCH_PACK_EXPORT_ENABLED=true"],
        "docs": [
            {"label": "Research pack export (EN)", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/research-pack-export_EN.md"},
            {"label": "研报资产包导出（中文）", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/research-pack-export.md"},
        ],
        "warning_codes": [],
    },
    "RESEARCH_PACK_MAX_ZIP_BYTES": {
        "title": "Research Pack Max ZIP Bytes",
        "description": (
            "Upper bound for a single research-pack ZIP response. "
            "Default 25165824 (24 MiB); clamped to 1–64 MiB when loading config."
        ),
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "25165824",
        "options": [],
        "validation": {"min": 1048576, "max": 67108864},
        "display_order": 727,
        "help_key": "settings.agent.research_pack_export",
        "examples": ["RESEARCH_PACK_MAX_ZIP_BYTES=25165824", "RESEARCH_PACK_MAX_ZIP_BYTES=10485760"],
        "docs": [
            {"label": "Research pack export (EN)", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/research-pack-export_EN.md"},
            {"label": "研报资产包导出（中文）", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/research-pack-export.md"},
        ],
        "warning_codes": [],
    },

    "AGENT_TOOL_TIMEOUT_S": {
        "title": "Agent Tool Timeout",
        "description": (
            "Maximum seconds for one tool call during Agent execution. "
            f"Default {int(DEFAULT_TOOL_TIMEOUT_SECONDS)}. When multiple budgets apply, "
            "the shortest remaining budget wins."
        ),
        "category": "agent",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": str(int(DEFAULT_TOOL_TIMEOUT_SECONDS)),
        "unit": "s",
        "options": [],
        "validation": {"min": 0, "max": 3600},
        "display_order": 710,
        "help_key": "settings.agent.runtime_guards",
        "examples": [
            f"AGENT_TOOL_TIMEOUT_S={int(DEFAULT_TOOL_TIMEOUT_SECONDS)}",
            "AGENT_TOOL_TIMEOUT_S=60",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_MAX_IDENTICAL_TOOL_CALLS": {
        "title": "Max Identical Tool Calls",
        "description": (
            "Maximum times the same tool name with the same normalized arguments may run "
            f"in one Agent execution. Default {DEFAULT_MAX_IDENTICAL_TOOL_CALLS}. "
            "Set 0 to disable this guard."
        ),
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": str(DEFAULT_MAX_IDENTICAL_TOOL_CALLS),
        "options": [],
        "validation": {"min": 0, "max": 50},
        "display_order": 711,
        "help_key": "settings.agent.runtime_guards",
        "examples": [
            f"AGENT_MAX_IDENTICAL_TOOL_CALLS={DEFAULT_MAX_IDENTICAL_TOOL_CALLS}",
            "AGENT_MAX_IDENTICAL_TOOL_CALLS=0",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_MAX_STAGE_ENTRIES": {
        "title": "Max Stage Entries",
        "description": (
            "Maximum ordinary pipeline entries for the same stage name per run. "
            f"Default {DEFAULT_MAX_STAGE_ENTRIES}. Set 0 to disable."
        ),
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": str(DEFAULT_MAX_STAGE_ENTRIES),
        "options": [],
        "validation": {"min": 0, "max": 20},
        "display_order": 712,
        "help_key": "settings.agent.runtime_guards",
        "examples": [
            f"AGENT_MAX_STAGE_ENTRIES={DEFAULT_MAX_STAGE_ENTRIES}",
            "AGENT_MAX_STAGE_ENTRIES=0",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_STAGE_FAILURE_POLICY": {
        "title": "Stage Failure Policy",
        "description": (
            "How multi-agent pipeline stages handle failure. "
            "'isolate' (default) degrades non-critical stages; "
            "'fail_fast' stops the ordinary pipeline on failure."
        ),
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "isolate",
        "options": _STAGE_FAILURE_POLICY_OPTIONS,
        "validation": {"enum": list(_STAGE_FAILURE_POLICY_VALUES)},
        "display_order": 713,
        "help_key": "settings.agent.runtime_guards",
        "examples": [
            "AGENT_STAGE_FAILURE_POLICY=isolate",
            "AGENT_STAGE_FAILURE_POLICY=fail_fast",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_TECHNICAL_AGENT_TIMEOUT_S": {
        "title": "Technical Stage Timeout",
        "description": "Independent timeout for the technical multi-agent stage in seconds. Default 0 uses the shared orchestrator budget only.",
        "category": "agent",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0",
        "unit": "s",
        "options": [],
        "validation": {"min": 0, "max": 3600},
        "display_order": 714,
        "help_key": "settings.agent.stage_timeouts",
        "examples": ["AGENT_TECHNICAL_AGENT_TIMEOUT_S=0", "AGENT_TECHNICAL_AGENT_TIMEOUT_S=180"],
        "docs": [{"label": "完整指南：Agent 配置", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表"}],
        "warning_codes": [],
    },
    "AGENT_INTEL_AGENT_TIMEOUT_S": {
        "title": "Intelligence Stage Timeout",
        "description": "Independent timeout for the intelligence multi-agent stage in seconds. Default 0 uses the shared orchestrator budget only.",
        "category": "agent",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0",
        "unit": "s",
        "options": [],
        "validation": {"min": 0, "max": 3600},
        "display_order": 715,
        "help_key": "settings.agent.stage_timeouts",
        "examples": ["AGENT_INTEL_AGENT_TIMEOUT_S=0", "AGENT_INTEL_AGENT_TIMEOUT_S=180"],
        "docs": [{"label": "完整指南：Agent 配置", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表"}],
        "warning_codes": [],
    },
    "AGENT_RISK_AGENT_TIMEOUT_S": {
        "title": "Risk Stage Timeout",
        "description": "Independent timeout for the risk multi-agent stage in seconds. Default 0 uses the shared orchestrator budget only.",
        "category": "agent",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0",
        "unit": "s",
        "options": [],
        "validation": {"min": 0, "max": 3600},
        "display_order": 716,
        "help_key": "settings.agent.stage_timeouts",
        "examples": ["AGENT_RISK_AGENT_TIMEOUT_S=0", "AGENT_RISK_AGENT_TIMEOUT_S=180"],
        "docs": [{"label": "完整指南：Agent 配置", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表"}],
        "warning_codes": [],
    },
    "AGENT_DECISION_AGENT_TIMEOUT_S": {
        "title": "Decision Stage Timeout",
        "description": "Independent timeout for the decision multi-agent stage in seconds. Default 0 uses the shared orchestrator budget only.",
        "category": "agent",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0",
        "unit": "s",
        "options": [],
        "validation": {"min": 0, "max": 3600},
        "display_order": 717,
        "help_key": "settings.agent.stage_timeouts",
        "examples": ["AGENT_DECISION_AGENT_TIMEOUT_S=0", "AGENT_DECISION_AGENT_TIMEOUT_S=180"],
        "docs": [{"label": "完整指南：Agent 配置", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表"}],
        "warning_codes": [],
    },
    "AGENT_PORTFOLIO_AGENT_TIMEOUT_S": {
        "title": "Portfolio Stage Timeout",
        "description": "Independent timeout for the portfolio multi-agent stage in seconds. Default 0 uses the shared orchestrator budget only.",
        "category": "agent",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0",
        "unit": "s",
        "options": [],
        "validation": {"min": 0, "max": 3600},
        "display_order": 718,
        "help_key": "settings.agent.stage_timeouts",
        "examples": ["AGENT_PORTFOLIO_AGENT_TIMEOUT_S=0", "AGENT_PORTFOLIO_AGENT_TIMEOUT_S=180"],
        "docs": [{"label": "完整指南：Agent 配置", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表"}],
        "warning_codes": [],
    },
    "AGENT_SKILL_AGENT_TIMEOUT_S": {
        "title": "Skill Stage Timeout",
        "description": "Independent timeout for specialist/skill multi-agent stages in seconds. Default 0 uses the shared orchestrator budget only.",
        "category": "agent",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0",
        "unit": "s",
        "options": [],
        "validation": {"min": 0, "max": 3600},
        "display_order": 719,
        "help_key": "settings.agent.stage_timeouts",
        "examples": ["AGENT_SKILL_AGENT_TIMEOUT_S=0", "AGENT_SKILL_AGENT_TIMEOUT_S=180"],
        "docs": [{"label": "完整指南：Agent 配置", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/full-guide.md#环境变量完整列表"}],
        "warning_codes": [],
    },
    "DECISION_MEMORY_ENABLED": {
        "title": "Decision Memory",
        "description": "When enabled, stock analysis may inject recent evaluated decision outcomes for reflection. Default on. Per-request override via use_memory remains available.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 720,
        "help_key": "settings.agent.decision_memory",
        "examples": ["DECISION_MEMORY_ENABLED=true", "DECISION_MEMORY_ENABLED=false"],
        "docs": [{"label": "DecisionSignal documentation", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/decision-signals.md"}],
        "warning_codes": [],
    },
    "DECISION_MEMORY_LOOKBACK": {
        "title": "Decision Memory Lookback",
        "description": "Maximum recent evaluated signals per stock to inject into decision memory reflection. Default 5; hard cap 40.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "5",
        "options": [],
        "validation": {"min": 0, "max": 40},
        "display_order": 721,
        "help_key": "settings.agent.decision_memory",
        "examples": ["DECISION_MEMORY_LOOKBACK=5", "DECISION_MEMORY_LOOKBACK=10"],
        "docs": [{"label": "DecisionSignal documentation", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/decision-signals.md"}],
        "warning_codes": [],
    },
    "DECISION_MEMORY_MIN_AGE_DAYS": {
        "title": "Decision Memory Min Age (Days)",
        "description": "Only reflect on signals at least this many days old so outcomes have time to exist. Default 3.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "3",
        "options": [],
        "validation": {"min": 0, "max": 365},
        "display_order": 722,
        "help_key": "settings.agent.decision_memory",
        "examples": ["DECISION_MEMORY_MIN_AGE_DAYS=3", "DECISION_MEMORY_MIN_AGE_DAYS=7"],
        "docs": [{"label": "DecisionSignal documentation", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/decision-signals.md"}],
        "warning_codes": [],
    },
    "DECISION_MEMORY_MIN_SAMPLES": {
        "title": "Decision Memory Min Samples",
        "description": "Minimum decided outcomes (hit + miss) before a hit-rate is shown for a memory bucket. Default 5.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "5",
        "options": [],
        "validation": {"min": 1, "max": 1000},
        "display_order": 723,
        "help_key": "settings.agent.decision_memory",
        "examples": ["DECISION_MEMORY_MIN_SAMPLES=5", "DECISION_MEMORY_MIN_SAMPLES=10"],
        "docs": [{"label": "DecisionSignal documentation", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/decision-signals.md"}],
        "warning_codes": [],
    },
    "REASONING_TRACE_EXPORT_ENABLED": {
        "title": "Reasoning Trace Export",
        "description": "Master switch for the reasoning-trace export API and service gate. Default off. Exports are redacted but still sensitive.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 724,
        "help_key": "settings.agent.reasoning_trace_export",
        "examples": ["REASONING_TRACE_EXPORT_ENABLED=false", "REASONING_TRACE_EXPORT_ENABLED=true"],
        "docs": [
            {"label": "Reasoning trace export (EN)", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/reasoning-trace-export_EN.md"},
            {"label": "推理轨迹导出（中文）", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/reasoning-trace-export.md"},
        ],
        "warning_codes": [],
    },
    "REASONING_TRACE_EXPORT_MAX_CHARS": {
        "title": "Reasoning Trace Max Chars",
        "description": "Character budget for complete reasoning-trace export responses. Default 500000; clamped to 10000–2000000 when loading config.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "500000",
        "options": [],
        "validation": {"min": 10000, "max": 2000000},
        "display_order": 725,
        "help_key": "settings.agent.reasoning_trace_export",
        "examples": ["REASONING_TRACE_EXPORT_MAX_CHARS=500000", "REASONING_TRACE_EXPORT_MAX_CHARS=100000"],
        "docs": [
            {"label": "Reasoning trace export (EN)", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/reasoning-trace-export_EN.md"},
            {"label": "推理轨迹导出（中文）", "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/reasoning-trace-export.md"},
        ],
        "warning_codes": [],
    },

}
