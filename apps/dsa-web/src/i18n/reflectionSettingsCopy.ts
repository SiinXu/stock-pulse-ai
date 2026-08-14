// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { SettingsHelpMap } from '../locales/settingsHelpTypes';

export const MULTI_LEVEL_REFLECTION_HELP_KEY = 'settings.agent.multi_level_reflection';

const fieldTitleMapZh = {
  AGENT_STEP_CRITIQUE_ENABLED: '步骤批评',
  AGENT_META_REVIEW_ENABLED: '元审查',
  AGENT_META_REVIEW_MIN_EPISODES: '元审查样本',
} as const;

const fieldTitleMapEn = {
  AGENT_STEP_CRITIQUE_ENABLED: 'Step Critique',
  AGENT_META_REVIEW_ENABLED: 'Meta Review',
  AGENT_META_REVIEW_MIN_EPISODES: 'Review Minimum',
} satisfies Record<keyof typeof fieldTitleMapZh, string>;

export const REFLECTION_FIELD_TITLE_MAP_ZH = fieldTitleMapZh;
export const REFLECTION_FIELD_TITLE_MAP_EN = fieldTitleMapEn;

export const REFLECTION_SETTINGS_HELP_EN: SettingsHelpMap = {
  'settings.agent.multi_level_reflection': {
    title: 'Reflection',
    summary: 'All layers.',
  },
};

export const REFLECTION_SETTINGS_HELP_ZH: SettingsHelpMap = {
  'settings.agent.multi_level_reflection': {
    title: '反思',
    summary: '全层级。',
  },
};
