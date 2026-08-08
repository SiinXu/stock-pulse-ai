// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { AgentBehaviorPanel } from '../AgentBehaviorPanel';
import {
  AGENT_ESSENTIAL_KEYS,
  AGENT_PRESET_MANAGED_KEYS,
  AGENT_SETUP_PRESETS,
} from '../agentSetupPresets';

// Mock SettingsField so this suite does not depend on pre-existing settingsHelp
// inventory drift on main (unrelated RSS_NEWS_FEED_URLS source/en inventory gap).
vi.mock('../SettingsField', () => ({
  SettingsField: ({ item }: { item: { key: string } }) => (
    <div data-testid={`settings-field-${item.key}`}>{item.key}</div>
  ),
}));

function buildItem(key: string, value: string, displayOrder = 1): SystemConfigItem {
  return {
    key,
    value,
    rawValueExists: value !== '',
    isMasked: false,
    schema: {
      key,
      category: 'agent',
      dataType: key.includes('STEPS') || key.includes('TIMEOUT') || key.includes('BUDGET')
        ? 'integer'
        : key.includes('ENABLED') || key === 'AGENT_MODE' || key.endsWith('_OVERRIDE')
          ? 'boolean'
          : 'string',
      uiControl: key.includes('STEPS') || key.includes('TIMEOUT') || key.includes('BUDGET')
        ? 'number'
        : key.includes('ENABLED') || key === 'AGENT_MODE' || key.endsWith('_OVERRIDE')
          ? 'switch'
          : 'text',
      isSensitive: false,
      isRequired: false,
      isEditable: true,
      options: [],
      validation: {},
      displayOrder,
      title: key,
    },
  };
}

function standardValues(): Record<string, string> {
  return { ...AGENT_SETUP_PRESETS.find((preset) => preset.id === 'standard_research')!.values };
}

function buildItems(values: Record<string, string>): SystemConfigItem[] {
  // Essentials + a few advanced keys so progressive disclosure is observable.
  const keys = [
    ...AGENT_ESSENTIAL_KEYS,
    'AGENT_ORCHESTRATOR_TIMEOUT_S',
    'AGENT_CRITIC_ENABLED',
    'AGENT_RISK_OVERRIDE',
    'AGENT_DEEP_RESEARCH_BUDGET',
    'AGENT_MEMORY_ENABLED',
    'AGENT_SKILLS',
    'AGENT_SKILL_DIR',
  ];
  return keys.map((key, index) => buildItem(key, values[key] ?? '', index + 1));
}

function renderPanel(
  values: Record<string, string> = standardValues(),
  onChange = vi.fn(),
) {
  const items = buildItems(values);
  render(
    <AgentBehaviorPanel
      items={items}
      disabled={false}
      onChange={onChange}
      issueByKey={{}}
      allValuesByKey={values}
    />,
  );
  return { onChange, items };
}

describe('AgentBehaviorPanel', () => {
  it('shows presets and only essentials in the default (collapsed) view', () => {
    renderPanel();

    expect(screen.getByTestId('agent-setup-presets')).toBeInTheDocument();
    expect(screen.getByTestId('agent-preset-card-simple_qa')).toBeInTheDocument();
    expect(screen.getByTestId('agent-preset-card-standard_research')).toBeInTheDocument();
    expect(screen.getByTestId('agent-preset-card-deep_governed')).toBeInTheDocument();

    const essentials = screen.getByTestId('agent-essentials-fields');
    for (const key of AGENT_ESSENTIAL_KEYS) {
      expect(within(essentials).getByTestId(`settings-field-${key}`)).toBeInTheDocument();
    }

    // Advanced block exists but is a collapsed <details> — fields stay in DOM
    // for a11y but the default open state must be false.
    const advanced = screen.getByTestId('agent-advanced-fields');
    expect(advanced).toBeInTheDocument();
    expect(advanced).not.toHaveAttribute('open');
    expect(within(advanced).getByTestId('settings-field-AGENT_SKILLS')).toBeInTheDocument();
    expect(within(advanced).getByTestId('settings-field-AGENT_CRITIC_ENABLED')).toBeInTheDocument();

    // Default visible field count = essentials only (acceptance: far fewer than flat 20+).
    expect(AGENT_ESSENTIAL_KEYS.length).toBeLessThanOrEqual(5);
    expect(AGENT_ESSENTIAL_KEYS.length).toBeLessThan(AGENT_PRESET_MANAGED_KEYS.length);
  });

  it('marks an exact preset match and applies another preset through onChange', () => {
    const values = standardValues();
    const onChange = vi.fn();
    renderPanel(values, onChange);

    expect(screen.getByTestId('agent-preset-status')).toHaveTextContent(/Standard research|标准研究/);

    fireEvent.click(screen.getByTestId('agent-preset-apply-simple_qa'));

    // Managed keys that differ from standard → simple_qa must be written.
    const written = Object.fromEntries(
      onChange.mock.calls.map((call) => {
        const [key, value] = call as [string, string];
        return [key, value];
      }),
    );
    expect(written.AGENT_ARCH).toBe('single');
    expect(written.AGENT_MAX_STEPS).toBe('5');
    expect(written.AGENT_ORCHESTRATOR_MODE).toBe('quick');
    // Skill list is not managed by presets.
    expect(written.AGENT_SKILLS).toBeUndefined();
    expect(screen.getByTestId('agent-preset-last-applied')).toBeInTheDocument();
  });

  it('shows custom status after a field diverges from the last applied preset base', () => {
    const values = { ...standardValues(), AGENT_MAX_STEPS: '12' };
    renderPanel(values);

    // Without last-applied state, still custom (not an exact match).
    const status = screen.getByTestId('agent-preset-status');
    expect(status).toHaveTextContent(/Custom|自定义/);
  });

  it('previews the field list for a hovered/focused preset before apply', () => {
    const values = standardValues();
    renderPanel(values);

    const applyDeep = screen.getByTestId('agent-preset-apply-deep_governed');
    fireEvent.mouseEnter(applyDeep);

    const preview = screen.getByTestId('agent-preset-preview-deep_governed');
    expect(preview).toBeInTheDocument();
    expect(within(preview).getByText(/AGENT_MAX_STEPS/)).toBeInTheDocument();
  });
});
