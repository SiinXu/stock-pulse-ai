// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type {
  DecisionSignalOutcomeItem,
  DecisionSignalOutcomeListResponse,
} from '../../../types/decisionSignals';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { DecisionSignalOutcomeExplorer } from '../DecisionSignalOutcomeExplorer';

const { listOutcomes } = vi.hoisted(() => ({
  listOutcomes: vi.fn(),
}));

vi.mock('../../../api/decisionSignals', () => ({
  decisionSignalsApi: {
    listOutcomes,
  },
}));

const outcome: DecisionSignalOutcomeItem = {
  id: 21,
  signalId: 13,
  horizon: '3d',
  engineVersion: 'decision-signal-v1',
  evalStatus: 'completed',
  outcome: 'hit',
  stockReturnPct: 5.25,
  action: 'buy',
  holdingState: 'holding',
  createdAt: '2026-07-29T01:00:00Z',
  updatedAt: '2026-07-29T01:05:00Z',
};

function response(
  items: DecisionSignalOutcomeItem[] = [outcome],
  total = items.length,
  page = 1,
): DecisionSignalOutcomeListResponse {
  return { items, total, page, pageSize: 20 };
}

function chooseOption(trigger: HTMLElement, value: string) {
  fireEvent.click(trigger);
  const listbox = document.getElementById(trigger.getAttribute('aria-controls')!)!;
  const option = within(listbox)
    .getAllByRole('option')
    .find((item) => item.getAttribute('data-value') === value)!;
  fireEvent.click(option);
}

function renderExplorer(onOpenSignal = vi.fn()) {
  window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');
  render(
    <UiLanguageProvider>
      <DecisionSignalOutcomeExplorer onOpenSignal={onOpenSignal} />
    </UiLanguageProvider>,
  );
  return onOpenSignal;
}

describe('DecisionSignalOutcomeExplorer', () => {
  beforeEach(() => {
    window.localStorage.clear();
    listOutcomes.mockReset();
  });

  it('filters and paginates using only backend-supported outcome parameters', async () => {
    listOutcomes
      .mockResolvedValueOnce(response([outcome], 45, 1))
      .mockResolvedValueOnce(response([outcome], 45, 1))
      .mockResolvedValueOnce(response([outcome], 45, 2));

    renderExplorer();

    expect(await screen.findByText('#13')).toBeInTheDocument();
    chooseOption(screen.getByLabelText('Horizon'), '3d');
    chooseOption(screen.getByLabelText('Outcome results'), 'hit');
    chooseOption(screen.getByLabelText('Status'), 'completed');
    fireEvent.change(screen.getByLabelText('Engine version'), {
      target: { value: ' decision-signal-v1 ' },
    });
    fireEvent.change(screen.getByLabelText('Signal ID'), { target: { value: '13' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));

    await waitFor(() => {
      expect(listOutcomes).toHaveBeenLastCalledWith({
        signalId: 13,
        horizon: '3d',
        engineVersion: 'decision-signal-v1',
        evalStatus: 'completed',
        outcome: 'hit',
        page: 1,
        pageSize: 20,
      });
    });

    fireEvent.click(screen.getByRole('button', { name: '2' }));
    await waitFor(() => {
      expect(listOutcomes).toHaveBeenLastCalledWith(expect.objectContaining({
        page: 2,
        pageSize: 20,
      }));
    });
  });

  it('renders an explicit empty state', async () => {
    listOutcomes.mockResolvedValueOnce(response([], 0));

    renderExplorer();

    expect(await screen.findByText('No outcome results yet')).toBeInTheDocument();
    expect(screen.getByText('No outcome results match the current filters.')).toBeInTheDocument();
  });

  it('shows request failure and retries', async () => {
    listOutcomes
      .mockRejectedValueOnce(new Error('network failed'))
      .mockResolvedValueOnce(response());

    renderExplorer();

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('#13')).toBeInTheDocument();
    expect(listOutcomes).toHaveBeenCalledTimes(2);
  });

  it('opens the signal related to an outcome row', async () => {
    listOutcomes.mockResolvedValueOnce(response());
    const onOpenSignal = renderExplorer(vi.fn().mockResolvedValue(undefined));

    fireEvent.click(await screen.findByRole('button', { name: 'View signal #13' }));

    await waitFor(() => expect(onOpenSignal).toHaveBeenCalledWith(13));
  });

  it('rejects an invalid signal ID before issuing a filtered request', async () => {
    listOutcomes.mockResolvedValueOnce(response());

    renderExplorer();
    await screen.findByText('#13');
    fireEvent.change(screen.getByLabelText('Signal ID'), { target: { value: '1.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }));

    expect(await screen.findByText('Signal ID must be a whole number greater than 0.'))
      .toBeInTheDocument();
    expect(listOutcomes).toHaveBeenCalledTimes(1);
  });
});
