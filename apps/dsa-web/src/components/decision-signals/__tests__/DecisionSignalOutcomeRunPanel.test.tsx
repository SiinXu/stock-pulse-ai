import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DecisionSignalOutcomeRunPanel } from '../DecisionSignalOutcomeRunPanel';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { decisionSignalsApi } from '../../../api/decisionSignals';
import type { DecisionSignalOutcomeRunResponse } from '../../../types/decisionSignals';

vi.mock('../../../api/decisionSignals', () => ({
  decisionSignalsApi: { runOutcomes: vi.fn() },
}));

const runMock = vi.mocked(decisionSignalsApi.runOutcomes);

function makeRun(overrides: Partial<DecisionSignalOutcomeRunResponse> = {}): DecisionSignalOutcomeRunResponse {
  return {
    items: [],
    evaluated: 25,
    created: 15,
    updated: 10,
    skipped: 65,
    engineVersion: 'decision-signal-v1',
    ...overrides,
  };
}

function renderPanel(onCompleted = vi.fn()) {
  render(
    <UiLanguageProvider initialLanguage="en">
      <DecisionSignalOutcomeRunPanel onCompleted={onCompleted} />
    </UiLanguageProvider>,
  );
  return onCompleted;
}

const runButton = () => screen.getByRole('button', { name: 'Run outcomes' });
const confirmRun = () => {
  fireEvent.click(runButton());
  fireEvent.click(screen.getByRole('button', { name: 'OK' }));
};

describe('DecisionSignalOutcomeRunPanel', () => {
  beforeEach(() => {
    runMock.mockReset();
  });

  it('shows the run button and an empty recent-runs state', () => {
    renderPanel();
    expect(runButton()).toBeTruthy();
    expect(screen.getByText('No runs in this session yet.')).toBeTruthy();
  });

  it('requires confirmation and does not run when cancelled', () => {
    renderPanel();
    fireEvent.click(runButton());
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(runMock).not.toHaveBeenCalled();
  });

  it('runs with safe default params after confirming', async () => {
    const onCompleted = renderPanel();
    runMock.mockResolvedValue(makeRun());

    confirmRun();

    await waitFor(() => expect(runMock).toHaveBeenCalledTimes(1));
    expect(runMock).toHaveBeenCalledWith({ status: 'active', force: false, limit: 100 });
    await waitFor(() => expect(onCompleted).toHaveBeenCalledTimes(1));
  });

  it('shows the summary and records the run in recent runs', async () => {
    renderPanel();
    runMock.mockResolvedValue(makeRun());

    confirmRun();

    // Summary appears in the result banner and in the recent-runs list.
    await waitFor(() => {
      const summaries = screen.getAllByText(/Evaluated 25 · created 15 · updated 10 · skipped 65/);
      expect(summaries.length).toBeGreaterThanOrEqual(2);
    });
    expect(screen.queryByText('No runs in this session yet.')).toBeNull();
  });

  it('disables the trigger while a run is in flight to prevent duplicate submits', async () => {
    renderPanel();
    let resolveRun: (value: DecisionSignalOutcomeRunResponse) => void = () => {};
    runMock.mockReturnValue(new Promise<DecisionSignalOutcomeRunResponse>((resolve) => {
      resolveRun = resolve;
    }));

    confirmRun();

    await waitFor(() => expect(runButton()).toBeDisabled());
    expect(runMock).toHaveBeenCalledTimes(1);

    resolveRun(makeRun());
    await waitFor(() => expect(runButton()).not.toBeDisabled());
  });

  it('surfaces an error when the run fails', async () => {
    renderPanel();
    runMock.mockRejectedValue(new Error('boom'));

    confirmRun();

    await waitFor(() => expect(screen.getByText('Outcome run failed')).toBeTruthy());
  });
});
