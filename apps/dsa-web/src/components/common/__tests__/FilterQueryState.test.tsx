// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import {
  useFilterQueryState,
  type FilterQueryCodec,
} from '../useFilterQueryState';

type Filters = {
  market: string;
  status: string;
};

const DEFAULT_FILTERS: Filters = { market: '', status: '' };

const FILTER_CODEC: FilterQueryCodec<Filters> = {
  read: (params) => ({
    market: ['cn', 'us'].includes(params.get('market') ?? '') ? params.get('market') ?? '' : '',
    status: ['open', 'closed'].includes(params.get('status') ?? '') ? params.get('status') ?? '' : '',
  }),
  write: (params, filters) => {
    if (filters.market) params.set('market', filters.market);
    else params.delete('market');
    if (filters.status) params.set('status', filters.status);
    else params.delete('status');
  },
};

const equalsFilters = (left: Filters, right: Filters) => (
  left.market === right.market && left.status === right.status
);

function QueryHarness({ navigation = 'push' }: { navigation?: 'push' | 'replace' }) {
  const location = useLocation();
  const navigate = useNavigate();
  const filters = useFilterQueryState({
    codec: FILTER_CODEC,
    defaultValue: DEFAULT_FILTERS,
    equals: equalsFilters,
    getActiveCount: (value) => Number(Boolean(value.market)) + Number(Boolean(value.status)),
    clearKeysOnApply: ['page'],
    navigation,
  });
  const [unrelatedRender, setUnrelatedRender] = useState(0);

  return (
    <main>
      <output aria-label="URL search">{location.search}</output>
      <output aria-label="Applied market">{filters.applied.market || 'all'}</output>
      <output aria-label="Draft market">{filters.draft.market || 'all'}</output>
      <output aria-label="Applied count">{filters.activeCount}</output>
      <output aria-label="Draft count">{filters.draftActiveCount}</output>
      <output aria-label="Dirty state">{String(filters.isDirty)}</output>
      <button
        type="button"
        onClick={() => filters.setDraft((current) => ({ ...current, market: 'cn' }))}
      >
        Draft China
      </button>
      <button type="button" onClick={filters.applyDraft}>Apply draft</button>
      <button type="button" onClick={() => filters.applyValue({ ...filters.applied, market: '' })}>
        Remove market
      </button>
      <button type="button" onClick={filters.resetDraft}>Reset draft</button>
      <button type="button" onClick={filters.resetApplied}>Clear applied</button>
      <button type="button" onClick={filters.discardDraft}>Discard draft</button>
      <button type="button" onClick={() => navigate(-1)}>Back</button>
      <button type="button" onClick={() => navigate(1)}>Forward</button>
      <button type="button" onClick={() => setUnrelatedRender((count) => count + 1)}>
        Rerender {unrelatedRender}
      </button>
    </main>
  );
}

function renderHarness(initialEntry: string, navigation: 'push' | 'replace' = 'push') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <QueryHarness navigation={navigation} />
    </MemoryRouter>,
  );
}

describe('useFilterQueryState', () => {
  it('keeps drafts local, preserves unrelated params, and restores applied filters through history', async () => {
    renderHarness('/signals?market=us&page=3&source=report');

    expect(screen.getByLabelText('Applied market')).toHaveTextContent('us');
    expect(screen.getByLabelText('Draft market')).toHaveTextContent('us');
    expect(screen.getByLabelText('Applied count')).toHaveTextContent('1');
    expect(screen.getByLabelText('Dirty state')).toHaveTextContent('false');

    fireEvent.click(screen.getByRole('button', { name: 'Draft China' }));
    expect(screen.getByLabelText('Draft market')).toHaveTextContent('cn');
    expect(screen.getByLabelText('Applied market')).toHaveTextContent('us');
    expect(screen.getByLabelText('URL search')).toHaveTextContent('market=us');
    expect(screen.getByLabelText('Dirty state')).toHaveTextContent('true');

    fireEvent.click(screen.getByRole('button', { name: 'Apply draft' }));
    await waitFor(() => expect(screen.getByLabelText('Applied market')).toHaveTextContent('cn'));
    expect(screen.getByLabelText('URL search')).toHaveTextContent('market=cn');
    expect(screen.getByLabelText('URL search')).toHaveTextContent('source=report');
    expect(screen.getByLabelText('URL search')).not.toHaveTextContent('page=3');
    expect(screen.getByLabelText('Dirty state')).toHaveTextContent('false');

    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    await waitFor(() => expect(screen.getByLabelText('Applied market')).toHaveTextContent('us'));
    expect(screen.getByLabelText('Draft market')).toHaveTextContent('us');
    expect(screen.getByLabelText('URL search')).toHaveTextContent('page=3');

    fireEvent.click(screen.getByRole('button', { name: 'Forward' }));
    await waitFor(() => expect(screen.getByLabelText('Applied market')).toHaveTextContent('cn'));
    expect(screen.getByLabelText('Draft market')).toHaveTextContent('cn');
  });

  it('does not erase a dirty draft on unrelated renders and separates draft reset from applied reset', async () => {
    renderHarness('/signals?market=us&status=open');

    fireEvent.click(screen.getByRole('button', { name: 'Draft China' }));
    fireEvent.click(screen.getByRole('button', { name: /Rerender/ }));
    expect(screen.getByLabelText('Draft market')).toHaveTextContent('cn');
    expect(screen.getByLabelText('Draft count')).toHaveTextContent('2');

    fireEvent.click(screen.getByRole('button', { name: 'Reset draft' }));
    expect(screen.getByLabelText('Draft market')).toHaveTextContent('all');
    expect(screen.getByLabelText('Applied market')).toHaveTextContent('us');
    expect(screen.getByLabelText('Dirty state')).toHaveTextContent('true');

    fireEvent.click(screen.getByRole('button', { name: 'Discard draft' }));
    expect(screen.getByLabelText('Draft market')).toHaveTextContent('us');
    expect(screen.getByLabelText('Dirty state')).toHaveTextContent('false');

    fireEvent.click(screen.getByRole('button', { name: 'Clear applied' }));
    await waitFor(() => expect(screen.getByLabelText('Applied market')).toHaveTextContent('all'));
    expect(screen.getByLabelText('Applied count')).toHaveTextContent('0');
  });

  it('supports replace navigation for canonicalization without adding a history entry', async () => {
    renderHarness('/signals?market=us', 'replace');
    fireEvent.click(screen.getByRole('button', { name: 'Draft China' }));
    fireEvent.click(screen.getByRole('button', { name: 'Apply draft' }));
    await waitFor(() => expect(screen.getByLabelText('Applied market')).toHaveTextContent('cn'));

    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    await waitFor(() => expect(screen.getByLabelText('Applied market')).toHaveTextContent('cn'));
  });

  it('normalizes unsupported query values and avoids redundant navigation', () => {
    renderHarness('/signals?market=invalid&source=report');
    expect(screen.getByLabelText('Applied market')).toHaveTextContent('all');
    expect(screen.getByLabelText('Dirty state')).toHaveTextContent('false');

    fireEvent.click(screen.getByRole('button', { name: 'Apply draft' }));
    expect(screen.getByLabelText('URL search')).toHaveTextContent('market=invalid');
    expect(screen.getByLabelText('URL search')).toHaveTextContent('source=report');
  });
});
