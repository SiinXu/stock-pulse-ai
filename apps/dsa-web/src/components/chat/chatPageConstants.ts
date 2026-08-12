// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiTextKey } from '../../i18n/uiText';

/** Quick question examples shown on the empty Chat state. */
export const QUICK_QUESTION_DEFINITIONS: Array<{ labelKey: UiTextKey; skill: string }> = [
  { labelKey: 'chat.quick.chan', skill: 'chan_theory' },
  { labelKey: 'chat.quick.wave', skill: 'wave_theory' },
  { labelKey: 'chat.quick.trend', skill: 'bull_trend' },
  { labelKey: 'chat.quick.box', skill: 'box_oscillation' },
  { labelKey: 'chat.quick.tencent', skill: 'bull_trend' },
  { labelKey: 'chat.quick.emotion', skill: 'emotion_cycle' },
];

export const MAX_SELECTED_SKILLS = 3;
export const CONTEXT_COMPRESSION_CONFIG_KEY = 'AGENT_CONTEXT_COMPRESSION_ENABLED';
export const CHAT_SESSION_QUERY_KEY = 'session';
export const CHAT_CONTEXT_STATE_QUERY_KEY = 'context';
export const CHAT_ACTIVE_CONTEXT_STATE = 'active';
export const CHAT_UNKNOWN_CONTEXT_STATE = 'unknown';
export const CHAT_DESKTOP_RAIL_QUERY = '(min-width: 1280px)';
