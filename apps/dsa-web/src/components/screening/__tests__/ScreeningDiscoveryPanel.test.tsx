// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { candidateDiscoveryApi } from '../../../api/candidateDiscovery';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { SOURCE_CANDIDATE_DISCOVERY_TEXT } from '../../../locales/candidateDiscoveryText';
import { SCREENING_TEXT } from '../../../locales/screening';
import type { DiscoveryScreeningText } from '../screeningText';
import ScreeningDiscoveryPanel from '../ScreeningDiscoveryPanel';

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

describe('ScreeningDiscoveryPanel virtualization fallback', () => {
  beforeEach(() => {
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
