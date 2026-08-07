// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ComponentProps } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { SetupStatusResponse } from '../../../types/systemConfig';
import { UiLanguageProvider, useUiLanguage } from '../../../contexts/UiLanguageContext';
import { HomeReadinessCard } from '../HomeReadinessCard';

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

function Harness(props: Omit<ComponentProps<typeof HomeReadinessCard>, 't'>) {
  const { t } = useUiLanguage();
  return <HomeReadinessCard {...props} t={t} />;
}

function renderCard(props: Omit<ComponentProps<typeof HomeReadinessCard>, 't'>) {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <MemoryRouter>
        <LocationProbe />
        <Harness {...props} />
      </MemoryRouter>
    </UiLanguageProvider>,
  );
}

const completeStatus: SetupStatusResponse = {
  isComplete: true,
  readyForSmoke: true,
  requiredMissingKeys: [],
  nextStepKey: null,
  checks: [
    {
      key: 'llm_primary',
      title: 'Primary model',
      category: 'ai_model',
      required: true,
      status: 'configured',
      message: 'Model connected',
    },
    {
      key: 'stock_list',
      title: 'Watchlist',
      category: 'base',
      required: true,
      status: 'configured',
      message: '3 symbols',
    },
  ],
};

const gapStatus: SetupStatusResponse = {
  isComplete: false,
  readyForSmoke: false,
  requiredMissingKeys: ['llm_primary', 'stock_list'],
  nextStepKey: 'llm_primary',
  checks: [
    {
      key: 'llm_primary',
      title: 'Primary model',
      category: 'ai_model',
      required: true,
      status: 'needs_action',
      message: 'missing model',
      nextStep: 'Add a model connection',
    },
    {
      key: 'stock_list',
      title: 'Watchlist',
      category: 'base',
      required: true,
      status: 'needs_action',
      message: 'empty list',
      nextStep: 'Add at least one symbol',
    },
    {
      key: 'notification',
      title: 'Notifications',
      category: 'notification',
      required: false,
      status: 'optional',
      message: 'optional channel',
    },
  ],
};

describe('HomeReadinessCard', () => {
  it('renders loading state', () => {
    renderCard({
      status: null,
      isLoading: true,
      error: null,
      onRefresh: () => {},
    });
    expect(screen.getByTestId('home-readiness-card')).toBeInTheDocument();
    expect(screen.getByText('Checking')).toBeInTheDocument();
  });

  it('renders error state with retry', () => {
    const onRefresh = vi.fn();
    renderCard({
      status: null,
      isLoading: false,
      error: {
        title: 'Request failed',
        message: 'network down',
        rawMessage: 'network down',
        category: 'upstream_network',
      },
      onRefresh,
    });
    expect(screen.getByText('Readiness unavailable')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRefresh).toHaveBeenCalled();
  });

  it('renders empty checks state', () => {
    renderCard({
      status: {
        isComplete: true,
        readyForSmoke: true,
        requiredMissingKeys: [],
        checks: [],
      },
      isLoading: false,
      error: null,
      onRefresh: () => {},
    });
    expect(screen.getByText('No readiness checks')).toBeInTheDocument();
  });

  it('renders all-green complete state without gap CTAs', () => {
    renderCard({
      status: completeStatus,
      isLoading: false,
      error: null,
      onRefresh: () => {},
    });
    expect(screen.getByText('Ready to analyze')).toBeInTheDocument();
    expect(screen.getByTestId('home-readiness-check-llm_primary')).toHaveAttribute('data-tone', 'success');
    expect(screen.queryByRole('button', { name: 'Connect model' })).not.toBeInTheDocument();
  });

  it('exposes exactly one primary CTA per gap and navigates to the fix surface', () => {
    renderCard({
      status: gapStatus,
      isLoading: false,
      error: null,
      onRefresh: () => {},
    });
    expect(screen.getByText(/2 items need attention/)).toBeInTheDocument();
    const modelCta = screen.getByRole('button', { name: /Connect model/ });
    const stockCta = screen.getByRole('button', { name: /Add symbols/ });
    expect(modelCta).toBeInTheDocument();
    expect(stockCta).toBeInTheDocument();
    // Optional/configured rows do not get a CTA.
    expect(screen.queryByRole('button', { name: /Configure notifications/ })).not.toBeInTheDocument();

    fireEvent.click(modelCta);
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/settings?section=ai_models&view=connections&from=home_readiness',
    );
  });

  it('shows last-success client signal with a single CTA when missing', () => {
    renderCard({
      status: completeStatus,
      isLoading: false,
      error: null,
      onRefresh: () => {},
      lastSuccess: {
        ok: false,
        href: '/research/analysis?segment=launch',
      },
    });
    fireEvent.click(screen.getByRole('button', { name: /Start analysis/ }));
    expect(screen.getByTestId('location')).toHaveTextContent('/research/analysis');
  });
});
