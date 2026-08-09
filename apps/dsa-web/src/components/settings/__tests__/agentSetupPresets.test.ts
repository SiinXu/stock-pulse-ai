// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  AGENT_ESSENTIAL_KEYS,
  AGENT_PRESET_MANAGED_KEYS,
  AGENT_SETUP_PRESETS,
  buildAgentPresetUpdates,
  diffAgentPreset,
  matchesAgentPreset,
  resolveAgentPresetStatus,
} from '../agentSetupPresets';

describe('agentSetupPresets', () => {
  it('defines three presets over real managed keys only', () => {
    expect(AGENT_SETUP_PRESETS.map((preset) => preset.id)).toEqual([
      'simple_qa',
      'standard_research',
      'deep_governed',
    ]);
    expect(AGENT_SETUP_PRESETS.some((preset) => preset.recommended)).toBe(true);
    for (const preset of AGENT_SETUP_PRESETS) {
      expect(Object.keys(preset.values).sort()).toEqual([...AGENT_PRESET_MANAGED_KEYS].sort());
    }
  });

  it('keeps essentials a strict subset of managed keys so default view stays short', () => {
    for (const key of AGENT_ESSENTIAL_KEYS) {
      expect(AGENT_PRESET_MANAGED_KEYS).toContain(key);
    }
    expect(AGENT_ESSENTIAL_KEYS.length).toBeLessThan(AGENT_PRESET_MANAGED_KEYS.length);
    expect(AGENT_ESSENTIAL_KEYS.length).toBeLessThanOrEqual(5);
  });

  it('matches a preset only when every available managed key equals the profile', () => {
    const standard = AGENT_SETUP_PRESETS.find((preset) => preset.id === 'standard_research')!;
    expect(matchesAgentPreset('standard_research', standard.values)).toBe(true);
    expect(matchesAgentPreset('simple_qa', standard.values)).toBe(false);

    const partial = { ...standard.values, AGENT_MAX_STEPS: '99' };
    expect(matchesAgentPreset('standard_research', partial)).toBe(false);
    expect(matchesAgentPreset('standard_research', standard.values, new Set(['AGENT_MODE']))).toBe(false);
  });

  it('diffs only keys that are available to the panel', () => {
    const available = new Set(['AGENT_MODE', 'AGENT_MAX_STEPS', 'AGENT_ARCH']);
    const current = {
      AGENT_MODE: 'false',
      AGENT_MAX_STEPS: '10',
      AGENT_ARCH: 'multi',
    };
    const changes = diffAgentPreset('simple_qa', current, available);
    expect(changes.map((change) => change.key).sort()).toEqual([
      'AGENT_ARCH',
      'AGENT_MAX_STEPS',
      'AGENT_MODE',
    ].sort());
    expect(changes.find((change) => change.key === 'AGENT_MODE')).toEqual({
      key: 'AGENT_MODE',
      from: 'false',
      to: 'true',
    });
  });

  it('builds updates only for keys present in the panel', () => {
    const updates = buildAgentPresetUpdates('deep_governed', ['AGENT_MODE', 'AGENT_CRITIC_ENABLED']);
    expect(updates).toEqual([
      { key: 'AGENT_MODE', value: 'true' },
      { key: 'AGENT_CRITIC_ENABLED', value: 'true' },
    ]);
  });

  it('reports custom status when values diverge, preferring last-applied base', () => {
    const standard = AGENT_SETUP_PRESETS.find((preset) => preset.id === 'standard_research')!;
    const customValues = { ...standard.values, AGENT_MAX_STEPS: '12' };
    expect(resolveAgentPresetStatus(customValues, {
      lastAppliedPresetId: 'standard_research',
    })).toEqual({ kind: 'custom', basePresetId: 'standard_research' });

    expect(resolveAgentPresetStatus(standard.values)).toEqual({
      kind: 'exact',
      presetId: 'standard_research',
    });
  });

  it('does not manage skill list, event JSON, or context compression keys', () => {
    for (const key of AGENT_PRESET_MANAGED_KEYS) {
      expect(key.startsWith('AGENT_CONTEXT_')).toBe(false);
      expect(key.startsWith('AGENT_EVENT_')).toBe(false);
    }
    expect(AGENT_PRESET_MANAGED_KEYS).not.toContain('AGENT_SKILLS');
    expect(AGENT_PRESET_MANAGED_KEYS).not.toContain('AGENT_SKILL_DIR');
    expect(AGENT_PRESET_MANAGED_KEYS).not.toContain('AGENT_EVENT_ALERT_RULES_JSON');
    expect(AGENT_PRESET_MANAGED_KEYS).not.toContain('AGENT_DEEP_RESEARCH_BUDGET');
    expect(AGENT_PRESET_MANAGED_KEYS).not.toContain('AGENT_DEEP_RESEARCH_TIMEOUT');
    expect(AGENT_PRESET_MANAGED_KEYS).toContain('AGENT_FEATURES_ACKNOWLEDGED_OFF');
    expect(AGENT_PRESET_MANAGED_KEYS.every((key) => !/(API_KEY|TOKEN|PASSWORD|SECRET)/.test(key))).toBe(true);
  });
});
