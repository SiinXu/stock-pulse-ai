// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { candidateDiscoveryApi } from '../../../api/candidateDiscovery';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { SOURCE_CANDIDATE_DISCOVERY_TEXT } from '../../../locales/candidateDiscoveryText';
import { SCREENING_TEXT } from '../../../locales/screening';
import type { DiscoveryScreeningText } from '../screeningText';
import ScreeningDiscoveryPanel from '../ScreeningDiscoveryPanel';

const navigate = vi.hoisted(() => vi.fn());

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigate,
  };
});

vi.mock('../../../api/candidateDiscovery', () => ({
  candidateDiscoveryApi: {
    startTask: vi.fn(),
    getTask: vi.fn(),
    cancelTask: vi.fn(),
  },
}));

const text = {
  ...SCREENING_TEXT.en,
  ...SOURCE_CANDIDATE_DISCOVERY_TEXT.en,
} as DiscoveryScreeningText;

function discoveryResult(count: number) {
  const candidates = Array.from({ length: count }, (_, index) => ({
    rank: index + 1,
    code: `SYM${String(index + 1).padStart(3, '0')}`,
    name: `Candidate ${index + 1}`,
    score: 70 - index,
    reason: 'Wrapping compact reason plus stacked analyze and watchlist actions in this cell.',
    changePct: 1.25,
    raw: {},
  }));
  return {
    packVersion: '1',
    runId: 'run-1',
    status: 'ok',
    universe: 'watchlist',
    candidateCount: count,
    candidates,
    costContract: { providerCalls: 1, maxProviderCalls: 20 },
    universeContract: { source: 'watchlist', resolvedCount: count, evaluatedCount: count },
  };
}

function emptyDiscoveryResult(overrides: Record<string, unknown> = {}) {
  return {
    packVersion: '1',
    runId: 'run-empty',
    status: 'empty',
    universe: 'watchlist',
    candidateCount: 0,
    candidates: [],
    costContract: { providerCalls: 0, maxProviderCalls: 20 },
    universeContract: { source: 'watchlist', resolvedCount: 0, evaluatedCount: 0 },
    ...overrides,
  };
}

async function renderCompletedDiscovery(result: Record<string, unknown>) {
  vi.mocked(candidateDiscoveryApi.startTask).mockResolvedValue({
    taskId: 'task-empty',
    traceId: 'trace-empty',
    status: 'accepted',
    message: 'accepted',
    universe: 'watchlist',
    page: 1,
    pageSize: 50,
    maxResults: 10,
    maxProviderCalls: 20,
  });
  vi.mocked(candidateDiscoveryApi.getTask).mockResolvedValue({
    taskId: 'task-empty',
    status: 'completed',
    progress: 100,
    message: 'done',
    result,
  });

  const view = render(
    <MemoryRouter>
      <UiLanguageProvider initialLanguage="en">
        <ScreeningDiscoveryPanel text={text} />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Run discovery' }));
  return view;
}

describe('ScreeningDiscoveryPanel virtualization fallback', () => {
  beforeEach(() => {
    navigate.mockReset();
    vi.mocked(candidateDiscoveryApi.startTask).mockReset();
    vi.mocked(candidateDiscoveryApi.getTask).mockReset();
  });

  it('keeps wrapping reasons and stacked actions on the full DataTable path', async () => {
    vi.mocked(candidateDiscoveryApi.startTask).mockResolvedValue({
      taskId: 'task-1',
      traceId: 'trace-1',
      status: 'accepted',
      message: 'accepted',
      universe: 'watchlist',
      page: 1,
      pageSize: 50,
      maxResults: 30,
      maxProviderCalls: 20,
    });
    vi.mocked(candidateDiscoveryApi.getTask).mockResolvedValue({
      taskId: 'task-1',
      status: 'completed',
      progress: 100,
      message: 'done',
      result: discoveryResult(30),
    });

    render(
      <MemoryRouter>
        <UiLanguageProvider initialLanguage="en">
          <ScreeningDiscoveryPanel text={text} />
        </UiLanguageProvider>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Run discovery' }));
    expect(await screen.findByText('SYM030')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'AI candidate discovery (bounded)' }))
        .toHaveAttribute('data-data-table-virtualized', 'false');
    });
    const region = screen.getByRole('region', { name: 'AI candidate discovery (bounded)' });
    expect(region).toHaveAttribute('data-data-table-virtual-reason', 'disabled');
    expect(region).toHaveAttribute('data-mounted-count', '30');
    expect(region).toHaveAttribute('data-total-count', '30');
    expect(screen.getByText('SYM001')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Analyze' })).toHaveLength(30);
  });
});

describe('ScreeningDiscoveryPanel empty and degraded states', () => {
  beforeEach(() => {
    navigate.mockReset();
    vi.mocked(candidateDiscoveryApi.startTask).mockReset();
    vi.mocked(candidateDiscoveryApi.getTask).mockReset();
  });

  it('renders genuine empty, degraded, and unconfigured discovery results differently', async () => {
    const titles = {
      noHits: text.discoveryNoHits,
      degraded: text.sourcesUnavailableTitle,
      unconfigured: text.diagnosticEmpty,
    };
    expect(new Set(Object.values(titles)).size).toBe(3);

    const emptyRun = await renderCompletedDiscovery(emptyDiscoveryResult({
      status: 'empty',
      emptyReason: 'no_criteria_match',
      universeContract: { source: 'watchlist', resolvedCount: 8, evaluatedCount: 8 },
    }));
    const emptyPanel = (await screen.findByText(titles.noHits)).closest('[data-state-panel="empty"]');
    expect(emptyPanel).not.toBeNull();
    expect(within(emptyPanel as HTMLElement).getByText(text.noHitsDescription)).toBeInTheDocument();
    expect(within(emptyPanel as HTMLElement).getByRole('button', {
      name: `${text.retry} · ${titles.noHits}`,
    })).toBeInTheDocument();
    expect(within(emptyPanel as HTMLElement).queryByRole('button', {
      name: `${text.openDataSources} · ${titles.noHits}`,
    })).toBeNull();
    expect(screen.queryByText(titles.degraded)).not.toBeInTheDocument();
    expect(screen.queryByText(titles.unconfigured)).not.toBeInTheDocument();
    emptyRun.unmount();

    const degradedRun = await renderCompletedDiscovery(emptyDiscoveryResult({
      status: 'degraded_empty',
      emptyReason: 'provider_unavailable',
    }));
    const degradedPanel = (await screen.findByText(titles.degraded)).closest('[data-state-panel="empty"]');
    expect(degradedPanel).not.toBeNull();
    expect(within(degradedPanel as HTMLElement).getByRole('button', {
      name: `${text.openDataSources} · ${titles.degraded}`,
    })).toBeInTheDocument();
    expect(screen.queryByText(titles.noHits)).not.toBeInTheDocument();
    expect(screen.queryByText(titles.unconfigured)).not.toBeInTheDocument();
    degradedRun.unmount();

    await renderCompletedDiscovery(emptyDiscoveryResult({
      status: 'empty',
      emptyReason: 'empty_universe',
    }));
    const unconfiguredPanel = (await screen.findByText(titles.unconfigured)).closest('[data-state-panel="empty"]');
    expect(unconfiguredPanel).not.toBeNull();
    expect(within(unconfiguredPanel as HTMLElement).getByRole('button', {
      name: `${text.openDataSources} · ${titles.unconfigured}`,
    })).toBeInTheDocument();
    expect(screen.queryByText(titles.noHits)).not.toBeInTheDocument();
    expect(screen.queryByText(titles.degraded)).not.toBeInTheDocument();
  });

  it('links degraded discovery empty state to Settings data sources', async () => {
    await renderCompletedDiscovery(emptyDiscoveryResult({
      status: 'degraded_empty',
      emptyReason: 'provider_unavailable',
      emptyMessage: 'data_provider returned no usable quotes within the call budget.',
    }));
    const emptyPanel = (await screen.findByText(text.sourcesUnavailableTitle)).closest('[data-state-panel="empty"]');
    expect(emptyPanel).not.toBeNull();
    expect(within(emptyPanel as HTMLElement).getByText(text.sourcesUnavailableDescription)).toBeInTheDocument();
    expect(screen.queryByText(text.discoveryNoHits)).not.toBeInTheDocument();
    fireEvent.click(within(emptyPanel as HTMLElement).getByRole('button', {
      name: `${text.openDataSources} · ${text.sourcesUnavailableTitle}`,
    }));
    expect(navigate).toHaveBeenCalledWith('/settings?section=data_sources&view=providers');
  });

  it('links unconfigured discovery empty state to Settings data sources', async () => {
    await renderCompletedDiscovery(emptyDiscoveryResult({
      status: 'empty',
      emptyReason: 'empty_universe',
    }));
    const emptyPanel = (await screen.findByText(text.diagnosticEmpty)).closest('[data-state-panel="empty"]');
    expect(emptyPanel).not.toBeNull();
    expect(within(emptyPanel as HTMLElement).getByText(text.sourcesUnavailableDescription)).toBeInTheDocument();
    expect(screen.queryByText(text.discoveryNoHits)).not.toBeInTheDocument();
    expect(screen.queryByText(text.sourcesUnavailableTitle)).not.toBeInTheDocument();
    fireEvent.click(within(emptyPanel as HTMLElement).getByRole('button', {
      name: `${text.openDataSources} · ${text.diagnosticEmpty}`,
    }));
    expect(navigate).toHaveBeenCalledWith('/settings?section=data_sources&view=providers');
  });
});
