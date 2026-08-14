// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { RuntimeCapabilitiesPanel } from '../RuntimeCapabilitiesPanel';

const listCapabilities = vi.fn();
const getModels = vi.fn();

vi.mock('../../../api/capabilities', () => ({
  capabilitiesApi: { list: (...args: unknown[]) => listCapabilities(...args) },
}));

vi.mock('../../../api/agent', () => ({
  agentApi: { getModels: (...args: unknown[]) => getModels(...args) },
}));

describe('RuntimeCapabilitiesPanel', () => {
  beforeEach(() => {
    listCapabilities.mockReset();
    getModels.mockReset();
  });

  it('shows runtime capabilities and Agent deployments without edit controls', async () => {
    listCapabilities.mockResolvedValue({
      schema_version: 'capability-inventory/v1',
      partial: false,
      sources: [{ source: 'tool', state: 'ok', generation: '1', as_of: '2026-08-13' }],
      items: [{
        id: 'tool:market.quote', domain: 'tool', type: 'agent_tool', owner: 'agent-tools',
        provider: 'core', version: '1', source_generation: '1', as_of: '2026-08-13',
        registered: true, executable: true, display_name: 'Market quote',
      }],
      total: 1,
      executable_count: 1,
      non_executable_count: 0,
      unknown_executable_count: 0,
    });
    getModels.mockResolvedValue({
      models: [{
        deployment_id: 'primary-agent', deployment_name: 'Primary Agent',
        model: 'provider/model', provider: 'provider', source: 'runtime',
        api_base: null, is_primary: true, is_fallback: false,
      }],
    });

    render(
      <UiLanguageProvider initialLanguage="en">
        <RuntimeCapabilitiesPanel />
      </UiLanguageProvider>,
    );

    expect(await screen.findByText('Market quote')).toBeInTheDocument();
    expect(screen.getByText('Primary Agent')).toBeInTheDocument();
    expect(screen.getByText('executable')).toBeInTheDocument();
    expect(screen.getByText('primary')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByText(/register|retire|resolve|route/i)).not.toBeInTheDocument();
  });

  it('keeps partial and failed sources visible instead of folding them into empty', async () => {
    listCapabilities.mockResolvedValue({
      schema_version: 'capability-inventory/v1', partial: true,
      sources: [{ source: 'data', state: 'error', generation: '1', as_of: '2026-08-13', error_code: 'probe_failed' }],
      items: [], total: 0, executable_count: 0, non_executable_count: 0, unknown_executable_count: 0,
    });
    getModels.mockRejectedValue(new Error('models unavailable'));

    render(
      <UiLanguageProvider initialLanguage="en">
        <RuntimeCapabilitiesPanel />
      </UiLanguageProvider>,
    );

    expect(await screen.findByText('partial')).toBeInTheDocument();
    expect(screen.getByText('data: error')).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Reload' }).length).toBeGreaterThan(0);
  });
});
