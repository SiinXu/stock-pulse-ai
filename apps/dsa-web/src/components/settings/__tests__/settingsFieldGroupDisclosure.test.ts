// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  SETTINGS_DEFAULT_OPEN_GROUP_IDS,
  isSettingsGroupDefaultOpen,
  parseSettingsFieldHash,
  resolveSettingsRevealFieldKey,
} from '../settingsFieldGroupDisclosure';

describe('settingsFieldGroupDisclosure', () => {
  it('defaults open only quote, primary, and schedule', () => {
    expect([...SETTINGS_DEFAULT_OPEN_GROUP_IDS]).toEqual(['quote', 'primary', 'schedule']);
    expect(isSettingsGroupDefaultOpen('quote')).toBe(true);
    expect(isSettingsGroupDefaultOpen('primary')).toBe(true);
    expect(isSettingsGroupDefaultOpen('schedule')).toBe(true);
    for (const groupId of ['search', 'news', 'other', 'routing', 'report', 'behavior', 'web', 'log']) {
      expect(isSettingsGroupDefaultOpen(groupId), groupId).toBe(false);
    }
  });

  it('parses a field hash and prefers an explicit reveal request', () => {
    expect(parseSettingsFieldHash('#setting-WEBUI_PORT')).toBe('WEBUI_PORT');
    expect(parseSettingsFieldHash('#other')).toBeNull();
    expect(resolveSettingsRevealFieldKey({
      requestKey: 'TAVILY_API_KEYS',
      queryField: 'WEBUI_PORT',
      hash: '#setting-LOG_LEVEL',
    })).toBe('TAVILY_API_KEYS');
    expect(resolveSettingsRevealFieldKey({
      queryField: 'WEBUI_PORT',
      hash: '#setting-LOG_LEVEL',
    })).toBe('WEBUI_PORT');
    expect(resolveSettingsRevealFieldKey({
      hash: '#setting-LOG_LEVEL',
    })).toBe('LOG_LEVEL');
  });
});
