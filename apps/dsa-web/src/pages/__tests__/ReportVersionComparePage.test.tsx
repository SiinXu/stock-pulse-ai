// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { reportVersionCompareApi } from '../../api/reportVersionCompare';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import {
  RouteFocusRegistrationContext,
  type RouteFocusTarget,
} from '../../contexts/routeFocusContext';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import ReportVersionComparePage from '../ReportVersionComparePage';

vi.mock('../../api/reportVersionCompare', () => ({
  reportVersionCompareApi: {
    listRuns: vi.fn(),
    compare: vi.fn(),
  },
}));

const routeFocusRegister = vi.fn((target: RouteFocusTarget) => {
  void target;
  return () => {};
});

function renderPage() {
  return render(
    <RouteFocusRegistrationContext.Provider value={{ register: routeFocusRegister }}>
      <UiLanguageProvider initialLanguage="en">
        <MemoryRouter initialEntries={[APP_ROUTE_PATHS.researchReportCompare]}>
          <ReportVersionComparePage />
        </MemoryRouter>
      </UiLanguageProvider>
    </RouteFocusRegistrationContext.Provider>,
  );
}

const runs = [
  {
    runId: '1',
    queryId: 'a',
    stockCode: '600519',
    createdAt: '2026-08-01T00:00:00',
    action: 'buy',
    actionLabel: 'Buy',
    sentimentScore: 80,
    modelUsed: 'm1',
    configFingerprint: 'fp1',
    configComponents: {},
    configComplete: true,
    configMissingKeys: [],
  },
  {
    runId: '2',
    queryId: 'b',
    stockCode: '600519',
    createdAt: '2026-08-08T00:00:00',
    action: 'sell',
    actionLabel: 'Sell',
    sentimentScore: 20,
    modelUsed: 'm2',
    configFingerprint: 'fp2',
    configComponents: {},
    configComplete: true,
    configMissingKeys: [],
  },
];

const compareResult = {
  status: 'engine_pending' as const,
  stockCode: '600519',
  baseRun: runs[0],
  targetRun: runs[1],
  configDiff: {
    baseFingerprint: 'fp1',
    targetFingerprint: 'fp2',
    identical: false,
    hasDifferences: true,
    comparisonStatus: 'different' as const,
    baseComplete: true,
    targetComplete: true,
    baseMissingKeys: [],
    targetMissingKeys: [],
    components: [
      {
        key: 'model_used',
        baseValue: 'm1',
        targetValue: 'm2',
        changed: true,
      },
    ],
  },
  fieldDiffs: [
    {
      field: 'action',
      baseValue: 'buy',
      targetValue: 'sell',
      changed: true,
      severity: 'major' as const,
    },
  ],
  delta: null,
  engineStatus: 'engine_pending' as const,
};

async function loadAndSelectRuns() {
  fireEvent.change(screen.getByTestId('report-version-compare-stock-input'), {
    target: { value: '600519' },
  });
  fireEvent.click(screen.getByTestId('report-version-compare-load-runs'));
  await waitFor(() => {
    expect(screen.getByRole('combobox', { name: 'Baseline version' })).toBeEnabled();
  });
  fireEvent.click(screen.getByRole('combobox', { name: 'Baseline version' }));
  fireEvent.click(within(await screen.findByRole('listbox')).getAllByRole('option')[0]);
  fireEvent.click(screen.getByRole('combobox', { name: 'Candidate version' }));
  fireEvent.click(within(await screen.findByRole('listbox')).getAllByRole('option')[1]);
}

describe('ReportVersionComparePage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    routeFocusRegister.mockClear();
    document.title = '';
  });

  it('loads runs and shows empty-runs state', async () => {
    vi.mocked(reportVersionCompareApi.listRuns).mockResolvedValue({
      stockCode: '600519',
      total: 0,
      page: 1,
      limit: 50,
      items: [],
    });

    renderPage();
    fireEvent.change(screen.getByTestId('report-version-compare-stock-input'), {
      target: { value: '600519' },
    });
    fireEvent.click(screen.getByTestId('report-version-compare-load-runs'));

    await waitFor(() => {
      expect(screen.getByTestId('report-version-compare-empty-runs')).toBeInTheDocument();
    });
  });

  it('shows need-two-runs empty state for a single version', async () => {
    vi.mocked(reportVersionCompareApi.listRuns).mockResolvedValue({
      stockCode: '600519',
      total: 1,
      page: 1,
      limit: 50,
      items: [runs[0]],
    });

    renderPage();
    fireEvent.change(screen.getByTestId('report-version-compare-stock-input'), {
      target: { value: '600519' },
    });
    fireEvent.click(screen.getByTestId('report-version-compare-load-runs'));

    await waitFor(() => {
      expect(screen.getByTestId('report-version-compare-need-two')).toBeInTheDocument();
    });
  });

  it('compares two selected runs and surfaces major severity', async () => {
    vi.mocked(reportVersionCompareApi.listRuns).mockResolvedValue({
      stockCode: '600519',
      total: 2,
      page: 1,
      limit: 50,
      items: runs,
    });
    vi.mocked(reportVersionCompareApi.compare).mockResolvedValue(compareResult);

    renderPage();
    await loadAndSelectRuns();

    fireEvent.click(screen.getByTestId('report-version-compare-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('report-version-compare-result')).toBeInTheDocument();
    });
    expect(reportVersionCompareApi.compare).toHaveBeenCalledWith(
      expect.objectContaining({
        stockCode: '600519',
        baseRunId: '1',
        targetRunId: '2',
      }),
    );
    expect(screen.getByTestId('report-version-field-action')).toHaveAttribute(
      'data-severity',
      'major',
    );
    expect(screen.getByTestId('report-version-compare-status-engine_pending')).toBeInTheDocument();
  });

  it('retries the failed compare with the same inputs without reloading runs', async () => {
    vi.mocked(reportVersionCompareApi.listRuns).mockResolvedValue({
      stockCode: '600519', total: 2, page: 1, limit: 50, items: runs,
    });
    vi.mocked(reportVersionCompareApi.compare)
      .mockRejectedValueOnce(new Error('compare failed'))
      .mockResolvedValueOnce(compareResult);

    renderPage();
    await loadAndSelectRuns();
    fireEvent.click(screen.getByTestId('report-version-compare-submit'));
    await screen.findByTestId('report-version-compare-error');
    fireEvent.click(await screen.findByRole('button', { name: 'Retry' }));

    await screen.findByTestId('report-version-compare-result');
    expect(reportVersionCompareApi.compare).toHaveBeenCalledTimes(2);
    expect(reportVersionCompareApi.compare).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ stockCode: '600519', baseRunId: '1', targetRunId: '2' }),
    );
    expect(reportVersionCompareApi.listRuns).toHaveBeenCalledTimes(1);
  });

  it('invalidates loaded runs when the draft stock identity changes', async () => {
    vi.mocked(reportVersionCompareApi.listRuns).mockResolvedValue({
      stockCode: '600519', total: 2, page: 1, limit: 50, items: runs,
    });

    renderPage();
    await loadAndSelectRuns();
    fireEvent.change(screen.getByTestId('report-version-compare-stock-input'), {
      target: { value: 'AAPL' },
    });

    expect(screen.getByRole('combobox', { name: 'Baseline version' })).toBeDisabled();
    expect(screen.getByTestId('report-version-compare-submit')).toBeDisabled();
    fireEvent.click(screen.getByTestId('report-version-compare-submit'));
    expect(reportVersionCompareApi.compare).not.toHaveBeenCalled();
  });

  it('loads later pages without replacing already selected versions', async () => {
    vi.mocked(reportVersionCompareApi.listRuns)
      .mockResolvedValueOnce({
        stockCode: '600519', total: 3, page: 1, limit: 50, items: runs,
      })
      .mockResolvedValueOnce({
        stockCode: '600519', total: 3, page: 2, limit: 50, items: [
          { ...runs[0], runId: '3', queryId: 'c' },
        ],
      });

    renderPage();
    await loadAndSelectRuns();
    fireEvent.click(screen.getByTestId('report-version-compare-load-more'));

    await waitFor(() => {
      expect(reportVersionCompareApi.listRuns).toHaveBeenNthCalledWith(
        2,
        expect.objectContaining({ stockCode: '600519', page: 2, limit: 50 }),
      );
    });
    expect(screen.getByRole('combobox', { name: 'Baseline version' })).toBeEnabled();
  });
});
