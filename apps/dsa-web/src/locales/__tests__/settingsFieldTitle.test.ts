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

  it('keeps AGENT_SKILL_RETRIEVAL_K titles aligned on the public Settings path', () => {
    expect(resolveSettingsFieldTitle({
      itemKey: 'AGENT_SKILL_RETRIEVAL_K',
      fallbackTitle: 'Skill Retrieval Top-K',
      language: 'en',
    })).toBe('Skill Retrieval Top-K');
    expect(resolveSettingsFieldTitle({
      itemKey: 'AGENT_SKILL_RETRIEVAL_K',
      fallbackTitle: 'Skill Retrieval Top-K',
      language: 'zh',
    })).toBe('技能检索 Top-K');
    expect(resolveSettingsFieldTitle({
      itemKey: 'AGENT_SKILL_RETRIEVAL_K',
      fallbackTitle: 'Skill Retrieval Top-K',
      language: 'de',
    })).toBe('Skill-Abruf Top-K');
  });
});
