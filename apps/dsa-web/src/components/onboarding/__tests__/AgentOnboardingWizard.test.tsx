// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AgentOnboardingWizard } from '../AgentOnboardingWizard';
import type { UiTextKey } from '../../../i18n/uiText';
import { UI_TEXT, formatUiText } from '../../../i18n/uiText';

const generatePlan = vi.fn();
const applyPlan = vi.fn();
const getConfig = vi.fn();

vi.mock('../../../api/onboarding', () => ({
  onboardingApi: {
    generatePlan: (...args: unknown[]) => generatePlan(...args),
    applyPlan: (...args: unknown[]) => applyPlan(...args),
    getState: vi.fn(),
    resetState: vi.fn(),
  },
}));

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    getConfig: (...args: unknown[]) => getConfig(...args),
  },
}));

function t(key: UiTextKey, params?: Record<string, string | number>): string {
  return formatUiText(UI_TEXT.en[key], params);
}

const samplePlan = {
  schemaVersion: 1,
  engine: 'rules',
  llmNote: 'Rule-based plan (default).',
  modelAvailable: false,
  preferLlm: false,
  profile: {
    schemaVersion: 1,
    experienceStage: 'beginner',
    markets: ['cn'],
    goals: ['pre_post_market'],
    holdings: 'none',
    interaction: 'web',
    riskTone: 'balanced',
    infrastructure: 'cloud_key',
    reportLanguage: 'en',
  },
  featureStage: 'L0',
  featurePath: {
    stage: 'L0',
    label: 'Cold start',
    primaryPath: ['Configure model'],
    emphasize: ['home'],
    defer: ['committee'],
  },
  recommendedPresetId: 'cloud-balanced',
  recommendedPresetName: 'Cloud balanced',
  beginnerModeRecommended: true,
  configChanges: [{ key: 'REPORT_LANGUAGE', from: '', to: 'en' }],
  configItems: [{ key: 'REPORT_LANGUAGE', value: 'en' }],
  todos: [{
    id: 'paste_cloud_key',
    priority: 1,
    title: 'Paste a cloud provider API key',
    description: 'Never invent keys.',
    href: '/settings',
    kind: 'secret_guide',
  }],
  todayPlan: [{
    id: 'step_analyze',
    title: 'Analyze one watchlist symbol',
    detail: 'Open Analysis Workbench.',
  }],
  weekPlan: [{ day: '2', title: 'Compare with history', detail: 'Review.' }],
  disclaimer: 'Never places buy/sell orders and never invents API keys.',
  generatedAt: '2026-08-06T00:00:00Z',
};

describe('AgentOnboardingWizard', () => {
  beforeEach(() => {
    generatePlan.mockReset();
    applyPlan.mockReset();
    getConfig.mockReset();
    window.localStorage.clear();
    generatePlan.mockResolvedValue(samplePlan);
    getConfig.mockResolvedValue({ configVersion: 'v1' });
    applyPlan.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedKeys: ['REPORT_LANGUAGE'],
      appliedCount: 1,
      plan: samplePlan,
      profile: samplePlan.profile,
      message: 'ok',
    });
  });

  it('renders intake, generates a rule-based plan preview, and applies non-secret config', async () => {
    const onApplied = vi.fn();
    render(
      <MemoryRouter>
        <AgentOnboardingWizard
          open
          onClose={() => {}}
          onApplied={onApplied}
          modelAvailable={false}
          reportLanguage="en"
          t={t}
        />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('agent-onboarding-wizard')).toBeInTheDocument();
    expect(screen.getByTestId('onboarding-intake')).toBeInTheDocument();
    expect(screen.getByText(/Rule engine is the default/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Generate config plan/i }));

    await waitFor(() => {
      expect(generatePlan).toHaveBeenCalled();
    });
    expect(await screen.findByTestId('onboarding-plan-preview')).toBeInTheDocument();
    expect(screen.getByTestId('onboarding-config-changes')).toHaveTextContent('REPORT_LANGUAGE');
    expect(screen.getByTestId('onboarding-disclaimer')).toHaveTextContent(/never invents API keys/i);

    fireEvent.click(screen.getByRole('button', { name: /Confirm and apply non-secret config/i }));

    await waitFor(() => {
      expect(applyPlan).toHaveBeenCalledWith(expect.objectContaining({
        configVersion: 'v1',
        confirm: true,
        modelAvailable: false,
      }));
    });
    expect(await screen.findByTestId('onboarding-done')).toBeInTheDocument();
    expect(onApplied).toHaveBeenCalled();
  });

  it('allows skip without calling apply', async () => {
    const onClose = vi.fn();
    render(
      <MemoryRouter>
        <AgentOnboardingWizard
          open
          onClose={onClose}
          modelAvailable={false}
          t={t}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Skip/i }));
    expect(onClose).toHaveBeenCalled();
    expect(applyPlan).not.toHaveBeenCalled();
  });
});
