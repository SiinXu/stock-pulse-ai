// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Agent Behavior setup presets (issue #868).
 *
 * Presentation-only profiles that batch-write existing agent config keys.
 * Values are taken from real registry defaults / documented option ranges —
 * no invented parameters. Presets never touch credentials, skill lists,
 * event-monitor JSON, or conversation-context compression keys.
 */
import { createUiLanguageRecord } from '../../i18n/createUiLanguageRecord';

/** Stable preset ids used for match/status and tests. */
export type AgentSetupPresetId = 'simple_qa' | 'standard_research' | 'deep_governed';

/** Keys a preset is allowed to write. Unrelated keys are left alone. */
export const AGENT_PRESET_MANAGED_KEYS = [
  'AGENT_MODE',
  'AGENT_FEATURES_ACKNOWLEDGED_OFF',
  'AGENT_GENERATION_BACKEND',
  'AGENT_MAX_STEPS',
  'AGENT_ARCH',
  'AGENT_ORCHESTRATOR_MODE',
  'AGENT_ORCHESTRATOR_TIMEOUT_S',
  'AGENT_CRITIC_ENABLED',
  'AGENT_MEMORY_ENABLED',
  'AGENT_SKILL_ROUTING',
  'AGENT_SKILL_AUTOWEIGHT',
  'AGENT_NL_ROUTING',
  'AGENT_INVESTMENT_COMMITTEE_MODE',
  'AGENT_MULTI_STRATEGY_DELIBERATION',
] as const;

export type AgentPresetManagedKey = (typeof AGENT_PRESET_MANAGED_KEYS)[number];

/** Essentials always shown in the default Agent Behavior view. */
export const AGENT_ESSENTIAL_KEYS = [
  'AGENT_MODE',
  'AGENT_GENERATION_BACKEND',
  'AGENT_MAX_STEPS',
  'AGENT_ARCH',
  'AGENT_ORCHESTRATOR_MODE',
] as const;

export type AgentEssentialKey = (typeof AGENT_ESSENTIAL_KEYS)[number];

const ESSENTIAL_KEY_SET = new Set<string>(AGENT_ESSENTIAL_KEYS);
const MANAGED_KEY_SET = new Set<string>(AGENT_PRESET_MANAGED_KEYS);

export type AgentPresetValues = Readonly<Record<AgentPresetManagedKey, string>>;

export type AgentSetupPreset = {
  id: AgentSetupPresetId;
  /** Recommended for first-time / default product path. */
  recommended?: boolean;
  values: AgentPresetValues;
};

/**
 * Three semantic profiles over real agent knobs:
 * - simple_qa: single-agent, low step/timeout budgets, no deep research expansion
 * - standard_research: multi/standard pipeline with bounded Agent time limits
 * - deep_governed: higher Agent step/timeout ceilings, critic + deliberation on
 */
export const AGENT_SETUP_PRESETS: readonly AgentSetupPreset[] = [
  {
    id: 'simple_qa',
    values: {
      AGENT_MODE: 'true',
      AGENT_FEATURES_ACKNOWLEDGED_OFF: 'false',
      AGENT_GENERATION_BACKEND: 'auto',
      AGENT_MAX_STEPS: '5',
      AGENT_ARCH: 'single',
      AGENT_ORCHESTRATOR_MODE: 'quick',
      AGENT_ORCHESTRATOR_TIMEOUT_S: '300',
      AGENT_CRITIC_ENABLED: 'false',
      AGENT_MEMORY_ENABLED: 'false',
      AGENT_SKILL_ROUTING: 'auto',
      AGENT_SKILL_AUTOWEIGHT: 'true',
      AGENT_NL_ROUTING: 'false',
      AGENT_INVESTMENT_COMMITTEE_MODE: 'false',
      AGENT_MULTI_STRATEGY_DELIBERATION: 'false',
    },
  },
  {
    id: 'standard_research',
    recommended: true,
    values: {
      AGENT_MODE: 'true',
      AGENT_FEATURES_ACKNOWLEDGED_OFF: 'false',
      AGENT_GENERATION_BACKEND: 'auto',
      AGENT_MAX_STEPS: '10',
      AGENT_ARCH: 'multi',
      AGENT_ORCHESTRATOR_MODE: 'standard',
      AGENT_ORCHESTRATOR_TIMEOUT_S: '600',
      AGENT_CRITIC_ENABLED: 'false',
      AGENT_MEMORY_ENABLED: 'false',
      AGENT_SKILL_ROUTING: 'auto',
      AGENT_SKILL_AUTOWEIGHT: 'true',
      AGENT_NL_ROUTING: 'false',
      AGENT_INVESTMENT_COMMITTEE_MODE: 'false',
      AGENT_MULTI_STRATEGY_DELIBERATION: 'false',
    },
  },
  {
    id: 'deep_governed',
    values: {
      AGENT_MODE: 'true',
      AGENT_FEATURES_ACKNOWLEDGED_OFF: 'false',
      AGENT_GENERATION_BACKEND: 'auto',
      AGENT_MAX_STEPS: '25',
      AGENT_ARCH: 'multi',
      AGENT_ORCHESTRATOR_MODE: 'full',
      AGENT_ORCHESTRATOR_TIMEOUT_S: '1200',
      AGENT_CRITIC_ENABLED: 'true',
      AGENT_MEMORY_ENABLED: 'true',
      AGENT_SKILL_ROUTING: 'auto',
      AGENT_SKILL_AUTOWEIGHT: 'true',
      AGENT_NL_ROUTING: 'false',
      AGENT_INVESTMENT_COMMITTEE_MODE: 'false',
      AGENT_MULTI_STRATEGY_DELIBERATION: 'true',
    },
  },
];

export const AGENT_SETUP_COPY = createUiLanguageRecord(
  'components.settings.agentSetupPresets.COPY',
  {
    zh: {
      presetsTitle: 'Agent 配置预设',
      presetsDescription: '先选一个使用场景，再按需展开高级字段。应用预设只会改动下列受管理的配置项，不会静默覆盖技能列表或其它无关项。',
      recommended: '推荐',
      apply: '应用预设',
      active: '当前匹配',
      custom: '自定义',
      customBasedOn: '自定义（基于 {name}）',
      unmatched: '未匹配任何预设',
      changesTitle: '将写入的字段',
      confirmTitle: '确认应用 {name}？',
      confirmDescription: '确认后会将 {count} 项变更作为一个设置草稿批次提交，并由现有自动保存事务持久化。',
      confirmWarnings: '请核对下方步数与超时变更：更高上限会增加模型调用、耗时和费用；内存会持久化上下文；Critic 与多策略审议会增加推理工作量。应用预设会取消“暂不使用 Agent”的确认，但不会修改 Risk Agent 否决、HITL 审批、全局深度研究预算、技能列表或凭据。',
      confirm: '确认应用',
      cancel: '取消',
      pending: '正在等待保存',
      saved: '已保存',
      failed: '自动保存失败',
      conflicted: '保存冲突',
      reset: '放弃此预设的草稿更改',
      unsupported: '后端缺少部分预设字段；无法判定完整匹配',
      summaryTitle: '已保存的 Agent 状态',
      model: 'Agent 模型',
      explicitModel: '专用模型',
      inheritedModel: '继承报告模型',
      modelReady: '可用',
      modelChecking: '正在检查',
      modelUnavailable: '不可用',
      modelUnknown: '状态未知',
      modelNotConfigured: '未配置',
      agentAcknowledgedOff: '已确认暂不使用 Agent',
      hitl: '风险与 HITL',
      hitlEnabled: 'Risk Agent 否决已开启；HITL 绕过仍由 /approvals 单独控制',
      hitlDisabled: 'Risk Agent 否决已关闭；HITL 绕过仍由 /approvals 单独控制',
      deepTools: '深度工具',
      deepToolsEnabled: '估值 Agent 工具已开启',
      deepToolsDisabled: '估值 Agent 工具已关闭',
      noChanges: '当前值已与该预设一致',
      essentialsTitle: '基础配置',
      advancedTitle: '高级字段',
      advancedDescription: '策略目录、研究预算、治理与诊断类开关。默认折叠，展开后可完整编辑。',
      emptyValue: '（空）',
      simple_qa: {
        name: '简单问答',
        description: '单 Agent、较低步数与超时，适合报告/个股快速追问。',
      },
      standard_research: {
        name: '标准研究',
        description: '多 Agent 标准管线，采用适中的 Agent 步数与超时，不开启持久化内存。',
      },
      deep_governed: {
        name: '深度研究',
        description: '提高 Agent 步数与超时上限，开启持久化内存、Critic 与多策略审议。',
      },
    },
    en: {
      presetsTitle: 'Agent setup presets',
      presetsDescription: 'Pick a usage profile first, then expand advanced fields only if needed. Applying a preset writes only the managed keys listed below and never silently overwrites skill lists or unrelated settings.',
      recommended: 'Recommended',
      apply: 'Apply preset',
      active: 'Current match',
      custom: 'Custom',
      customBasedOn: 'Custom (based on {name})',
      unmatched: 'No matching preset',
      changesTitle: 'Fields that will be written',
      confirmTitle: 'Apply {name}?',
      confirmDescription: 'Confirming submits {count} changes as one Settings draft batch, which the existing autosave transaction then persists.',
      confirmWarnings: 'Review the step and timeout changes below: higher limits increase model calls, latency, and cost; memory persists context; Critic and multi-strategy deliberation add reasoning work. Applying a preset clears “Agent acknowledged off” but does not change Risk Agent veto, HITL approvals, global Deep Research budgets, skill lists, or credentials.',
      confirm: 'Apply preset',
      cancel: 'Cancel',
      pending: 'Waiting to save',
      saved: 'Saved',
      failed: 'Autosave failed',
      conflicted: 'Save conflict',
      reset: 'Discard this preset draft',
      unsupported: 'The backend is missing preset fields; a complete match cannot be determined',
      summaryTitle: 'Saved Agent status',
      model: 'Agent model',
      explicitModel: 'Dedicated model',
      inheritedModel: 'Inherits report model',
      modelReady: 'Ready',
      modelChecking: 'Checking',
      modelUnavailable: 'Unavailable',
      modelUnknown: 'Status unknown',
      modelNotConfigured: 'Not configured',
      agentAcknowledgedOff: 'Agent use acknowledged off',
      hitl: 'Risk and HITL',
      hitlEnabled: 'Risk Agent veto is enabled; HITL bypass remains controlled separately in /approvals',
      hitlDisabled: 'Risk Agent veto is disabled; HITL bypass remains controlled separately in /approvals',
      deepTools: 'Deep tools',
      deepToolsEnabled: 'Valuation Agent tool enabled',
      deepToolsDisabled: 'Valuation Agent tool disabled',
      noChanges: 'Values already match this preset',
      essentialsTitle: 'Essentials',
      advancedTitle: 'Advanced fields',
      advancedDescription: 'Strategy paths, research budgets, governance, and diagnostic toggles. Collapsed by default; expand to edit the full set.',
      emptyValue: '(empty)',
      simple_qa: {
        name: 'Simple Q&A',
        description: 'Single agent, lower step/timeout budgets — best for quick report or stock follow-ups.',
      },
      standard_research: {
        name: 'Standard research',
        description: 'Multi-agent standard pipeline with moderate Agent step/time limits and persisted memory off.',
      },
      deep_governed: {
        name: 'Deep + governed',
        description: 'Higher Agent step/time limits with persisted memory, Critic, and multi-strategy deliberation.',
      },
    },
  },
);

export function isAgentEssentialKey(key: string): boolean {
  return ESSENTIAL_KEY_SET.has(key.toUpperCase());
}

export function isAgentPresetManagedKey(key: string): boolean {
  return MANAGED_KEY_SET.has(key.toUpperCase());
}

export function normalizeAgentConfigValue(value: string | undefined | null): string {
  return String(value ?? '').trim();
}


function asKeySet(
  availableKeys?: ReadonlySet<string> | readonly string[] | null,
): ReadonlySet<string> | null {
  if (!availableKeys) {
    return null;
  }
  return availableKeys instanceof Set ? availableKeys : new Set(availableKeys);
}

function keySetHas(set: ReadonlySet<string> | null, key: string): boolean {
  return set === null || set.has(key);
}

export function getAgentSetupPreset(id: AgentSetupPresetId): AgentSetupPreset {
  const preset = AGENT_SETUP_PRESETS.find((entry) => entry.id === id);
  if (!preset) {
    throw new Error(`Unknown agent setup preset: ${id}`);
  }
  return preset;
}

export type AgentPresetFieldChange = {
  key: AgentPresetManagedKey;
  from: string;
  to: string;
};

/**
 * Diff current values against a preset. Only managed keys present in
 * `availableKeys` (the keys the panel can actually edit) are considered.
 */
export function diffAgentPreset(
  presetId: AgentSetupPresetId,
  currentValues: Readonly<Record<string, string>>,
  availableKeys?: ReadonlySet<string> | readonly string[],
): AgentPresetFieldChange[] {
  const preset = getAgentSetupPreset(presetId);
  const allowed = asKeySet(availableKeys);
  const changes: AgentPresetFieldChange[] = [];
  for (const key of AGENT_PRESET_MANAGED_KEYS) {
    if (!keySetHas(allowed, key)) {
      continue;
    }
    const from = normalizeAgentConfigValue(currentValues[key]);
    const to = normalizeAgentConfigValue(preset.values[key]);
    if (from !== to) {
      changes.push({ key, from, to });
    }
  }
  return changes;
}

/**
 * Exact match against a preset for every managed key that is available.
 * Missing availableKeys means all managed keys must match.
 */
export function matchesAgentPreset(
  presetId: AgentSetupPresetId,
  currentValues: Readonly<Record<string, string>>,
  availableKeys?: ReadonlySet<string> | readonly string[],
): boolean {
  const allowed = asKeySet(availableKeys);
  if (allowed && AGENT_PRESET_MANAGED_KEYS.some((key) => !allowed.has(key))) {
    return false;
  }
  return diffAgentPreset(presetId, currentValues, availableKeys).length === 0;
}

export type AgentPresetMatchStatus =
  | { kind: 'exact'; presetId: AgentSetupPresetId }
  | { kind: 'custom'; basePresetId: AgentSetupPresetId | null };

/**
 * Resolve the active preset badge. Prefer an exact match; otherwise fall back
 * to the last applied preset (custom-based-on) or the closest partial match.
 */
export function resolveAgentPresetStatus(
  currentValues: Readonly<Record<string, string>>,
  options?: {
    availableKeys?: ReadonlySet<string> | readonly string[];
    lastAppliedPresetId?: AgentSetupPresetId | null;
  },
): AgentPresetMatchStatus {
  const availableKeys = options?.availableKeys;
  for (const preset of AGENT_SETUP_PRESETS) {
    if (matchesAgentPreset(preset.id, currentValues, availableKeys)) {
      return { kind: 'exact', presetId: preset.id };
    }
  }
  if (options?.lastAppliedPresetId) {
    return { kind: 'custom', basePresetId: options.lastAppliedPresetId };
  }
  // Closest partial match (most managed keys already equal) as a soft base label.
  let bestId: AgentSetupPresetId | null = null;
  let bestScore = -1;
  for (const preset of AGENT_SETUP_PRESETS) {
    const total = diffAgentPreset(preset.id, currentValues, availableKeys);
    const allowed = asKeySet(availableKeys);
    const managedCount = allowed
      ? AGENT_PRESET_MANAGED_KEYS.filter((key) => allowed.has(key)).length
      : AGENT_PRESET_MANAGED_KEYS.length;
    const score = managedCount - total.length;
    if (score > bestScore) {
      bestScore = score;
      bestId = preset.id;
    }
  }
  return { kind: 'custom', basePresetId: bestScore > 0 ? bestId : null };
}

/**
 * Produce the key/value pairs a preset would write for keys present in items.
 * Callers apply these through the existing draft `onChange` path.
 */
export function buildAgentPresetUpdates(
  presetId: AgentSetupPresetId,
  availableKeys: ReadonlySet<string> | readonly string[],
): Array<{ key: AgentPresetManagedKey; value: string }> {
  const preset = getAgentSetupPreset(presetId);
  const allowed = asKeySet(availableKeys) ?? new Set<string>();
  const updates: Array<{ key: AgentPresetManagedKey; value: string }> = [];
  for (const key of AGENT_PRESET_MANAGED_KEYS) {
    if (!allowed.has(key)) {
      continue;
    }
    updates.push({ key, value: preset.values[key] });
  }
  return updates;
}

export function formatAgentPresetValue(
  value: string,
  emptyLabel: string,
): string {
  const normalized = normalizeAgentConfigValue(value);
  return normalized === '' ? emptyLabel : normalized;
}
