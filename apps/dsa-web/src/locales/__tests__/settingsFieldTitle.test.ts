// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { resolveSettingsFieldTitle } from '../settingsFieldTitle';

describe('resolveSettingsFieldTitle', () => {
  it('uses localized help copy when a non-English field has no title-map entry', () => {
    expect(resolveSettingsFieldTitle({
      itemKey: 'AGENT_MULTI_STRATEGY_DELIBERATION',
      fallbackTitle: 'Multi-Strategy Deliberation',
      language: 'de',
    })).toBe('Multi-Strategie-Beratung');
  });

  it('keeps the backend schema title authoritative in English', () => {
    expect(resolveSettingsFieldTitle({
      itemKey: 'FUTURE_SETTING',
      fallbackTitle: 'Future Setting',
      language: 'en',
    })).toBe('Future Setting');
  });
});
