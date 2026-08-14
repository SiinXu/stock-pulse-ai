// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { portfolioHealthApi } from '../../../api/portfolioHealth';
import type { PortfolioHealthSummary } from '../../../types/portfolioHealth';
import { HomePortfolioHealthWidget } from '../HomePortfolioHealthWidget';

vi.mock('../../../api/portfolioHealth', () => ({
  portfolioHealthApi: {
    getSummary: vi.fn(),
  },
}));

function renderWidget() {
  return render(
    <MemoryRouter>
      <UiLanguageProvider>
        <HomePortfolioHealthWidget />
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

const storedUnavailable: PortfolioHealthSummary = {
  asOf: '2026-08-13',
  comparable: false,
  costMethod: 'fifo',
  coverageRatio: 0,
  currency: 'CNY',
  status: 'unavailable',
  statusMessage: 'Portfolio equity is negative; health scoring is undefined.',
};

describe('HomePortfolioHealthWidget', () => {
  beforeEach(() => {
    vi.mocked(portfolioHealthApi.getSummary).mockReset();
  });

  it('uses empty copy when no snapshot has been stored', async () => {
    vi.mocked(portfolioHealthApi.getSummary).mockResolvedValue(null);
    renderWidget();
    expect(await screen.findByText('No portfolio health snapshot')).toBeInTheDocument();
  });

  it('shows the stored unavailable status message instead of empty copy', async () => {
    vi.mocked(portfolioHealthApi.getSummary).mockResolvedValue(storedUnavailable);
    renderWidget();
    expect(await screen.findByText('Portfolio health unavailable')).toBeInTheDocument();
    expect(
      screen.getByText('Portfolio equity is negative; health scoring is undefined.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('No portfolio health snapshot')).not.toBeInTheDocument();
  });
});
