// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ReactElement } from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { AgentBehaviorPanel, type AgentBehaviorPanelProps } from '../AgentBehaviorPanel';
import {
  AGENT_ESSENTIAL_KEYS,
  AGENT_PRESET_MANAGED_KEYS,
  AGENT_SETUP_PRESETS,
} from '../agentSetupPresets';

function renderPanel(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

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

const BEHAVIOR_TOGGLE_NAME = /行为|Behavior/;
const GOVERNANCE_TOGGLE_NAME = /治理 \/ 专家|Governance \/ Expert/;
const ESSENTIALS_FOCUS_TOGGLE_NAME = /显示高级设置|Show advanced settings/;

function disclosureToggle(testId: string, name: RegExp) {
  return within(screen.getByTestId(testId)).getByRole('button', { name });
}

function expectDefaultClosedDisclosure(testId: string, name: RegExp) {
  const toggle = disclosureToggle(testId, name);
  expect(toggle).toHaveAttribute('type', 'button');
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
  const panelId = toggle.getAttribute('aria-controls');
  expect(panelId).toBeTruthy();
  const panel = document.getElementById(panelId!);
  expect(panel).toHaveAttribute('hidden');
  expect(panel).toHaveAttribute('inert');
  return { toggle, panel: panel! };
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
  it('shows a persisted summary and keeps Behavior/Governance collapsed under semantic groups', () => {
    renderPanel(<AgentBehaviorPanel {...propsFor()} />);

    expect(screen.getByTestId('agent-active-summary')).toHaveTextContent(/Standard research|标准研究/);
    expect(screen.getByTestId('agent-active-summary')).toHaveTextContent(/GPT · primary/);
    const essentials = screen.getByTestId('agent-essentials-fields');
    for (const key of AGENT_ESSENTIAL_KEYS) {
      expect(within(essentials).getByTestId(`settings-field-${key}`)).toBeInTheDocument();
    }
    const { toggle: behaviorToggle, panel: behaviorPanel } = expectDefaultClosedDisclosure(
      'agent-behavior-fields',
      BEHAVIOR_TOGGLE_NAME,
    );
    fireEvent.click(behaviorToggle);
    expect(behaviorToggle).toHaveAttribute('aria-expanded', 'true');
    expect(behaviorPanel).not.toHaveAttribute('hidden');
    const behavior = screen.getByTestId('agent-behavior-fields');
    expect(within(behavior).getByText(/Runtime & mode|运行模式/)).toBeInTheDocument();
    expect(within(behavior).getByText(/Skills|技能/)).toBeInTheDocument();
    const { toggle: governanceToggle, panel: governancePanel } = expectDefaultClosedDisclosure(
      'agent-governance-fields',
      GOVERNANCE_TOGGLE_NAME,
    );
    fireEvent.click(governanceToggle);
    expect(governanceToggle).toHaveAttribute('aria-expanded', 'true');
    expect(governancePanel).not.toHaveAttribute('hidden');
    const governance = screen.getByTestId('agent-governance-fields');
    expect(within(governance).getByTestId('settings-field-AGENT_RISK_OVERRIDE')).toBeInTheDocument();
    expect(within(governance).getByTestId('settings-field-VALUATION_AGENT_TOOL_ENABLED')).toBeInTheDocument();
    expect(within(behavior).queryByTestId('settings-field-AGENT_RISK_OVERRIDE')).not.toBeInTheDocument();
  });

  it('surfaces a default ask path after preset selection without opening expert layers', async () => {
    renderPanel(<AgentBehaviorPanel {...propsFor()} />);

    const askCta = screen.getByTestId('agent-ask-cta');
    expect(askCta).toHaveAttribute('href', '/chat');

    fireEvent.click(screen.getByTestId('agent-preset-apply-simple_qa'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Apply preset|确认应用/ }));
    await waitFor(() => expect(document.activeElement).toBe(askCta));
    expectDefaultClosedDisclosure('agent-behavior-fields', BEHAVIOR_TOGGLE_NAME);
    expectDefaultClosedDisclosure('agent-governance-fields', GOVERNANCE_TOGGLE_NAME);
  });

  it('previews without mutation, then confirms exactly one atomic batch', () => {
    const onChange = vi.fn();
    const onBatchChange = vi.fn();
    renderPanel(<AgentBehaviorPanel {...propsFor({ onChange, onBatchChange })} />);

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
    renderPanel(<AgentBehaviorPanel {...propsFor({ onBatchChange })} />);
    fireEvent.click(screen.getByTestId('agent-preset-apply-deep_governed'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Cancel|取消/ }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(onBatchChange).not.toHaveBeenCalled();
  });

  it('surfaces a failed autosave and offers immediate draft recovery', () => {
    const onResetKeys = vi.fn();
    renderPanel(<AgentBehaviorPanel {...propsFor({ saveStatus: 'failed', onResetKeys })} />);
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
    renderPanel(<AgentBehaviorPanel {...propsFor({ draftValuesByKey: draft, persistedValuesByKey: persisted })} />);
    expect(screen.getByTestId('agent-preset-status')).toHaveTextContent(/Standard research|标准研究/);
  });

  it('fails closed when the backend omits any managed preset key', () => {
    const values = standardValues();
    renderPanel(<AgentBehaviorPanel {...propsFor({ items: buildItems(values, AGENT_ESSENTIAL_KEYS) })} />);
    expect(screen.getByTestId('agent-preset-status')).toHaveTextContent(/missing preset fields|缺少部分预设字段/);
    expect(screen.getByTestId('agent-preset-apply-simple_qa')).toBeDisabled();
    expect(screen.queryByTestId('agent-ask-path')).not.toBeInTheDocument();
  });

  it('restores focus to the preset trigger after keyboard cancellation', async () => {
    renderPanel(<AgentBehaviorPanel {...propsFor()} />);
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
      const { rerender } = renderPanel(<AgentBehaviorPanel {...initialProps} />);
      fireEvent.click(screen.getByTestId('agent-preset-apply-simple_qa'));
      fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Apply preset|确认应用/ }));

      rerender(
        <MemoryRouter>
          <AgentBehaviorPanel {...initialProps} saveStatus={saveStatus} />
        </MemoryRouter>,
      );
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
    renderPanel(<AgentBehaviorPanel {...props} />);

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
    renderPanel(<AgentBehaviorPanel {...propsFor({
      persistedValuesByKey,
      draftValuesByKey: { ...standardValues(), AGENT_FEATURES_ACKNOWLEDGED_OFF: 'true' },
      modelSummary: { value: 'GPT · primary', source: 'explicit', readiness: 'ready' },
    })} />);

    const summary = screen.getByTestId('agent-active-summary');
    expect(summary).toHaveTextContent(/Agent use acknowledged off|已确认暂不使用 Agent/);
    expect(summary).not.toHaveTextContent(/· Ready|· 可用/);
    expect(screen.queryByTestId('agent-ask-path')).not.toBeInTheDocument();
  });

  it('offers a model-source fix CTA when readiness is unconfigured without hiding the ask path', () => {
    renderPanel(<AgentBehaviorPanel {...propsFor({
      modelSummary: { value: '', source: 'inherited', readiness: 'unconfigured' },
    })} />);
    expect(screen.getByTestId('agent-configure-model-cta')).toBeInTheDocument();
    expect(screen.getByTestId('agent-ask-cta')).toHaveAttribute('href', '/chat');
  });

  it('nests Behavior and Governance under one disclosure when essentialsFocus is set', () => {
    renderPanel(<AgentBehaviorPanel {...propsFor({ essentialsFocus: true })} />);

    const shell = screen.getByTestId('agent-essentials-focus-advanced');
    const { toggle: shellToggle, panel: shellPanel } = expectDefaultClosedDisclosure(
      'agent-essentials-focus-advanced',
      ESSENTIALS_FOCUS_TOGGLE_NAME,
    );
    expect(within(shell).getByTestId('agent-behavior-fields')).toBeInTheDocument();
    expect(within(shell).getByTestId('agent-governance-fields')).toBeInTheDocument();
    // Primary surface still shows essentials + ask path outside the nested shell.
    expect(screen.getByTestId('agent-essentials-fields')).toBeInTheDocument();
    expect(screen.getByTestId('agent-ask-path')).toBeInTheDocument();

    fireEvent.click(shellToggle);
    expect(shellToggle).toHaveAttribute('aria-expanded', 'true');
    expect(shellPanel).not.toHaveAttribute('hidden');
    expect(screen.getByTestId('agent-behavior-fields').firstElementChild).toHaveClass('border-0');
    expect(screen.getByTestId('agent-governance-fields').firstElementChild).toHaveClass('border-0');
    const { toggle: behaviorToggle, panel: behaviorPanel } = expectDefaultClosedDisclosure(
      'agent-behavior-fields',
      BEHAVIOR_TOGGLE_NAME,
    );
    fireEvent.click(behaviorToggle);
    expect(behaviorToggle).toHaveAttribute('aria-expanded', 'true');
    expect(behaviorPanel).not.toHaveAttribute('hidden');
    expect(within(screen.getByTestId('agent-behavior-fields')).getByText(/Runtime & mode|运行模式/)).toBeInTheDocument();
    expectDefaultClosedDisclosure('agent-governance-fields', GOVERNANCE_TOGGLE_NAME);
  });
});
