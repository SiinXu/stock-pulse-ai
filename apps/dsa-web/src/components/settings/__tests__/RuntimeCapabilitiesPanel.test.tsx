// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

function capabilityResponse(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: 'capability-inventory/v1',
    partial: false,
    sources: [{ source: 'tool', state: 'ok', generation: '1', as_of: '2026-08-13' }],
    items: [{
      id: 'tool:market.quote',
      domain: 'tool',
      type: 'agent_tool',
      owner: 'agent-tools',
      provider: 'core',
      version: '1',
      source_generation: '1',
      as_of: '2026-08-13',
      registered: true,
      executable: true,
      display_name: 'Market quote',
    }],
    total: 1,
    executable_count: 1,
    non_executable_count: 0,
    unknown_executable_count: 0,
    ...overrides,
  };
}

function modelResponse() {
  return {
    models: [{
      deployment_id: 'primary-agent',
      deployment_name: 'Primary Agent',
      model: 'provider/model',
      provider: 'provider',
      source: 'AGENT_LITELLM_MODEL',
      api_base: null,
      is_primary: true,
      is_fallback: false,
    }],
  };
}

function renderPanel() {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <RuntimeCapabilitiesPanel />
    </UiLanguageProvider>,
  );
}

describe('RuntimeCapabilitiesPanel', () => {
  beforeEach(() => {
    listCapabilities.mockReset();
    getModels.mockReset();
  });

  it('shows read-only capability and Agent deployment data through shared tables', async () => {
    listCapabilities.mockResolvedValue(capabilityResponse());
    getModels.mockResolvedValue(modelResponse());

    renderPanel();

    expect(await screen.findByText('Market quote')).toBeInTheDocument();
    expect(screen.getByText('Primary Agent')).toBeInTheDocument();
    expect(screen.getAllByText('Executable').length).toBeGreaterThan(0);
    expect(screen.getByText('Primary')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByText(/register|retire|resolve|route/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole('region').length).toBeGreaterThanOrEqual(2);
  });

  it('keeps partial capability data visible when the model inventory fails', async () => {
    listCapabilities.mockResolvedValue(capabilityResponse({
      partial: true,
      sources: [{
        source: 'data',
        state: 'error',
        generation: '1',
        as_of: '2026-08-13',
        error_code: 'probe_failed',
      }],
    }));
    getModels.mockRejectedValue(new Error('models unavailable'));

    renderPanel();

    expect(await screen.findByText('Market quote')).toBeInTheDocument();
    expect(screen.getByText('Partial')).toBeInTheDocument();
    expect(screen.getByText('data: Unavailable')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Reload: Agent · Available models' }))
      .toBeInTheDocument();
  });

  it('retries failed model data independently from capabilities', async () => {
    listCapabilities.mockResolvedValue(capabilityResponse());
    getModels
      .mockRejectedValueOnce(new Error('models unavailable'))
      .mockResolvedValueOnce(modelResponse());

    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Reload: Agent · Available models' }));

    expect(await screen.findByText('Primary Agent')).toBeInTheDocument();
    expect(listCapabilities).toHaveBeenCalledTimes(1);
    expect(getModels).toHaveBeenCalledTimes(2);
  });

  it('preserves the last capability snapshot when a refresh fails', async () => {
    listCapabilities
      .mockResolvedValueOnce(capabilityResponse())
      .mockRejectedValueOnce(new Error('capabilities unavailable'));
    getModels.mockResolvedValue(modelResponse());

    renderPanel();
    expect(await screen.findByText('Market quote')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Reload: Capabilities' }));

    await waitFor(() => expect(listCapabilities).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Market quote')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload: Capabilities' })).toBeInTheDocument();
  });
});
