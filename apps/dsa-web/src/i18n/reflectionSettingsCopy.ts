// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { SettingsHelpMap } from '../locales/settingsHelpTypes';

export const MULTI_LEVEL_REFLECTION_HELP_KEY = 'settings.agent.multi_level_reflection';

const fieldTitleMapZh = {
  AGENT_CRITIC_ENABLED: '有界 Multi-Agent Critic',
  AGENT_STEP_CRITIQUE_ENABLED: '步骤批评',
  AGENT_REFLECTION_ENABLED: '反思',
  AGENT_REFLECTION_LLM_BUDGET: '反思 LLM 预算',
  AGENT_META_REVIEW_ENABLED: '元审查',
  AGENT_META_REVIEW_MIN_EPISODES: '元审查样本',
} as const;

const fieldTitleMapEn = {
  AGENT_CRITIC_ENABLED: 'Bounded Multi-Agent Critic',
  AGENT_STEP_CRITIQUE_ENABLED: 'Step Critique',
  AGENT_REFLECTION_ENABLED: 'Reflection',
  AGENT_REFLECTION_LLM_BUDGET: 'Reflection Budget',
  AGENT_META_REVIEW_ENABLED: 'Meta Review',
  AGENT_META_REVIEW_MIN_EPISODES: 'Review Minimum',
} satisfies Record<keyof typeof fieldTitleMapZh, string>;

export const REFLECTION_FIELD_TITLE_MAP_ZH = fieldTitleMapZh;
export const REFLECTION_FIELD_TITLE_MAP_EN = fieldTitleMapEn;

export const REFLECTION_SETTINGS_HELP_EN: SettingsHelpMap = {
  'settings.agent.AGENT_CRITIC_ENABLED': {
    title: 'Bounded Multi-Agent Critic',
    summary: 'Adds one read-only Critic call before the Native Multi Decision stage.',
    usage: 'Enable only when the extra Critic call and a possible single whitelist-stage retry fit the run budget.',
    valueNotes: [
      'Disabled by default; Single and Chat behavior is unchanged.',
      'A retry can target only an already-entered intelligence or catalog-backed skill stage.',
    ],
    impact: ['Adds one Critic LLM call and, only after a retry verdict, at most one stage rerun.'],
    notes: ['Invalid output and unavailable retry targets fail closed to fail_soft without spending retry budget.'],
  },
  'settings.agent.multi_level_reflection': {
    title: 'Reflection',
    summary: 'All layers.',
  },
};

export const REFLECTION_SETTINGS_HELP_ZH: SettingsHelpMap = {
  'settings.agent.AGENT_CRITIC_ENABLED': {
    title: '有界 Multi-Agent Critic',
    summary: '在 Native Multi 的 Decision 阶段前执行一次只读证据复核。',
    usage: '仅在运行预算能够承担额外 Critic 调用及可能的一次白名单阶段重试时开启。',
    valueNotes: [
      '默认关闭；Single 与 Chat 行为不变。',
      '重试只能指向已经进入过的 intelligence 或目录中存在的 skill 阶段。',
    ],
    impact: ['增加一次 Critic LLM 调用；仅在 retry verdict 下最多再执行一次目标阶段。'],
    notes: ['非法输出或不可用重试目标会 fail-closed 为 fail_soft，且不消耗重试预算。'],
  },
  'settings.agent.multi_level_reflection': {
    title: '反思',
    summary: '全层级。',
  },
};
