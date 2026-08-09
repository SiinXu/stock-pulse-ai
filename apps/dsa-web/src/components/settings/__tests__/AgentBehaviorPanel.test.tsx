// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { AgentBehaviorPanel, type AgentBehaviorPanelProps } from '../AgentBehaviorPanel';
import {
  AGENT_ESSENTIAL_KEYS,
  AGENT_PRESET_MANAGED_KEYS,
  AGENT_SETUP_PRESETS,
} from '../agentSetupPresets';

function buildItem(key: string, value: string, displayOrder = 1): SystemConfigItem {
  return {
    key,
    value,
    rawValueExists: value !== '',
    isMasked: false,
    schema: {
      key,
      category: 'agent',
      dataType: key.includes('STEPS') || key.includes('TIMEOUT') ? 'integer' : key.includes('ENABLED') || key === 'AGENT_MODE' || key === 'AGENT_FEATURES_ACKNOWLEDGED_OFF' ? 'boolean' : 'string',
      uiControl: key.includes('STEPS') || key.includes('TIMEOUT') ? 'number' : key.includes('ENABLED') || key === 'AGENT_MODE' || key === 'AGENT_FEATURES_ACKNOWLEDGED_OFF' ? 'switch' : 'text',
      isSensitive: false,
      isRequired: false,
      isEditable: true,
      options: [],
      validation: {},
      displayOrder,
      title: key.replaceAll('_', ' '),
    },
  };
}

function standardValues(): Record<string, string> {
  return { ...AGENT_SETUP_PRESETS.find((preset) => preset.id === 'standard_research')!.values };
}

function buildItems(values: Record<string, string>, keys: readonly string[] = AGENT_PRESET_MANAGED_KEYS): SystemConfigItem[] {
  return [...keys, 'AGENT_SKILLS', 'AGENT_SKILL_DIR', 'AGENT_RISK_OVERRIDE', 'VALUATION_AGENT_TOOL_ENABLED']
    .filter((key, index, all) => all.indexOf(key) === index)
    .map((key, index) => buildItem(key, values[key] ?? '', index + 1));
}

function propsFor(overrides: Partial<AgentBehaviorPanelProps> = {}): AgentBehaviorPanelProps {
  const values = standardValues();
  return {
    items: buildItems(values),
    disabled: false,
    onChange: vi.fn(),
    onBatchChange: vi.fn(),
    onResetKeys: vi.fn(),
    issueByKey: {},
    draftValuesByKey: values,
    persistedValuesByKey: { ...values, AGENT_LITELLM_MODEL: 'primary/gpt', AGENT_RISK_OVERRIDE: 'true', VALUATION_AGENT_TOOL_ENABLED: 'false' },
    saveStatus: 'idle',
    modelSummary: { value: 'GPT · primary', source: 'explicit', readiness: 'ready' },
    fieldGroups: [
      { id: 'mode', titleKey: 'settings.agentGroupMode' },
      { id: 'skills', titleKey: 'settings.agentGroupSkills' },
      { id: 'context', titleKey: 'settings.agentGroupContext' },
      { id: 'other', titleKey: 'settings.categoryGroupOther' },
    ],
    fieldGroupIdOf: (key) => key.includes('SKILL') ? 'skills' : key.includes('MEMORY') ? 'context' : key === 'VALUATION_AGENT_TOOL_ENABLED' ? 'other' : 'mode',
    fieldGroupOrderOf: (key) => buildItems(values).findIndex((item) => item.key === key),
    ...overrides,
  };
}

describe('AgentBehaviorPanel', () => {
  it('shows a persisted summary and keeps advanced fields collapsed under semantic groups', () => {
    render(<AgentBehaviorPanel {...propsFor()} />);

    expect(screen.getByTestId('agent-active-summary')).toHaveTextContent(/Standard research|标准研究/);
    expect(screen.getByTestId('agent-active-summary')).toHaveTextContent(/GPT · primary/);
    const essentials = screen.getByTestId('agent-essentials-fields');
    for (const key of AGENT_ESSENTIAL_KEYS) {
      expect(within(essentials).getByTestId(`settings-field-${key}`)).toBeInTheDocument();
    }
    const advanced = screen.getByTestId('agent-advanced-fields');
    expect(advanced).not.toHaveAttribute('open');
    expect(within(advanced).getByText(/Runtime & mode|运行模式/)).toBeInTheDocument();
    expect(within(advanced).getByText(/Skills|技能/)).toBeInTheDocument();
  });

  it('previews without mutation, then confirms exactly one atomic batch', () => {
    const onChange = vi.fn();
    const onBatchChange = vi.fn();
    render(<AgentBehaviorPanel {...propsFor({ onChange, onBatchChange })} />);

    const apply = screen.getByTestId('agent-preset-apply-simple_qa');
    fireEvent.mouseEnter(apply);
    expect(screen.getByTestId('agent-preset-preview-simple_qa')).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(onBatchChange).not.toHaveBeenCalled();

    fireEvent.click(apply);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(onBatchChange).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Apply preset|确认应用/ }));

    expect(onBatchChange).toHaveBeenCalledTimes(1);
    const updates = Object.fromEntries(onBatchChange.mock.calls[0][0].map((item: { key: string; value: string }) => [item.key, item.value]));
    expect(updates.AGENT_ARCH).toBe('single');
    expect(updates.AGENT_MAX_STEPS).toBe('5');
    expect(updates.AGENT_SKILLS).toBeUndefined();
    expect(updates.AGENT_DEEP_RESEARCH_BUDGET).toBeUndefined();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('cancels confirmation without changing the draft', () => {
    const onBatchChange = vi.fn();
    render(<AgentBehaviorPanel {...propsFor({ onBatchChange })} />);
    fireEvent.click(screen.getByTestId('agent-preset-apply-deep_governed'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Cancel|取消/ }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(onBatchChange).not.toHaveBeenCalled();
  });

  it('surfaces a failed autosave and offers immediate draft recovery', () => {
    const onResetKeys = vi.fn();
    render(<AgentBehaviorPanel {...propsFor({ saveStatus: 'failed', onResetKeys })} />);
    fireEvent.click(screen.getByTestId('agent-preset-apply-simple_qa'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Apply preset|确认应用/ }));

    expect(screen.getByTestId('agent-preset-status')).toHaveTextContent(/Autosave failed|自动保存失败/);
    fireEvent.click(screen.getByRole('button', { name: /Discard this preset draft|放弃此预设/ }));
    expect(onResetKeys).toHaveBeenCalledTimes(1);
    expect(onResetKeys.mock.calls[0][0]).toContain('AGENT_MAX_STEPS');
  });

  it('uses persisted values for the active badge instead of an unsaved draft', () => {
    const persisted = standardValues();
    const draft = { ...persisted, AGENT_MAX_STEPS: '12' };
    render(<AgentBehaviorPanel {...propsFor({ draftValuesByKey: draft, persistedValuesByKey: persisted })} />);
    expect(screen.getByTestId('agent-preset-status')).toHaveTextContent(/Standard research|标准研究/);
  });

  it('fails closed when the backend omits any managed preset key', () => {
    const values = standardValues();
    render(<AgentBehaviorPanel {...propsFor({ items: buildItems(values, AGENT_ESSENTIAL_KEYS) })} />);
    expect(screen.getByTestId('agent-preset-status')).toHaveTextContent(/missing preset fields|缺少部分预设字段/);
    expect(screen.getByTestId('agent-preset-apply-simple_qa')).toBeDisabled();
  });

  it('restores focus to the preset trigger after keyboard cancellation', async () => {
    render(<AgentBehaviorPanel {...propsFor()} />);
    const trigger = screen.getByTestId('agent-preset-apply-simple_qa');
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(document.activeElement).toBe(trigger);
  });

  it.each(['failed', 'conflicted'] as const)(
    'surfaces a %s preset save and restores only the preset draft keys',
    (saveStatus) => {
      const onResetKeys = vi.fn();
      const initialProps = propsFor({ onResetKeys });
      const { rerender } = render(<AgentBehaviorPanel {...initialProps} />);
      fireEvent.click(screen.getByTestId('agent-preset-apply-simple_qa'));
      fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Apply preset|确认应用/ }));

      rerender(<AgentBehaviorPanel {...initialProps} saveStatus={saveStatus} />);
      expect(screen.getByTestId('agent-preset-status')).toHaveTextContent(
        saveStatus === 'failed' ? /Autosave failed|自动保存失败/ : /Save conflict|保存冲突/,
      );
      fireEvent.click(screen.getByRole('button', { name: /Discard this preset draft|放弃此预设/ }));
      expect(onResetKeys).toHaveBeenCalledTimes(1);
      expect(onResetKeys.mock.calls[0][0]).toEqual(expect.arrayContaining([
        'AGENT_ARCH',
        'AGENT_MAX_STEPS',
        'AGENT_ORCHESTRATOR_MODE',
      ]));
      expect(onResetKeys.mock.calls[0][0]).not.toContain('AGENT_SKILLS');
    },
  );

  it('uses the real SettingsField validation and keeps catalog failures unknown', () => {
    const props = propsFor({
      issueByKey: {
        AGENT_MAX_STEPS: [{
          key: 'AGENT_MAX_STEPS',
          code: 'out_of_range',
          message: 'Step budget is outside the allowed range',
          severity: 'error',
        }],
      },
      modelSummary: { value: 'GPT · primary', source: 'explicit', readiness: 'unknown' },
    });
    render(<AgentBehaviorPanel {...props} />);

    const field = screen.getByTestId('settings-field-AGENT_MAX_STEPS');
    expect(field.querySelector('[aria-invalid="true"]')).not.toBeNull();
    expect(field).toHaveTextContent('Step budget is outside the allowed range');
    expect(screen.getByTestId('agent-active-summary')).toHaveTextContent(/Status unknown|状态未知/);
  });

  it('never reports a ready Agent while the saved acknowledged-off state is true', () => {
    const persistedValuesByKey = {
      ...standardValues(),
      AGENT_FEATURES_ACKNOWLEDGED_OFF: 'true',
      AGENT_LITELLM_MODEL: 'primary/gpt',
    };
    render(<AgentBehaviorPanel {...propsFor({
      persistedValuesByKey,
      modelSummary: { value: 'GPT · primary', source: 'explicit', readiness: 'ready' },
    })} />);

    const summary = screen.getByTestId('agent-active-summary');
    expect(summary).toHaveTextContent(/Agent use acknowledged off|已确认暂不使用 Agent/);
    expect(summary).not.toHaveTextContent(/· Ready|· 可用/);
  });
});
