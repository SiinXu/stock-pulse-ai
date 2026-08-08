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
  },
];

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
    vi.mocked(reportVersionCompareApi.compare).mockResolvedValue({
      status: 'engine_pending',
      stockCode: '600519',
      baseRun: { ...runs[0], configComponents: {} },
      targetRun: { ...runs[1], configComponents: {} },
      configDiff: {
        baseFingerprint: 'fp1',
        targetFingerprint: 'fp2',
        identical: false,
        hasDifferences: true,
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
          severity: 'major',
        },
      ],
      delta: null,
      engineStatus: 'engine_pending',
    });

    renderPage();
    fireEvent.change(screen.getByTestId('report-version-compare-stock-input'), {
      target: { value: '600519' },
    });
    fireEvent.click(screen.getByTestId('report-version-compare-load-runs'));

    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Baseline version' })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole('combobox', { name: 'Baseline version' }));
    const baseList = await screen.findByRole('listbox');
    fireEvent.click(within(baseList).getAllByRole('option')[0]);

    fireEvent.click(screen.getByRole('combobox', { name: 'Candidate version' }));
    const targetList = await screen.findByRole('listbox');
    fireEvent.click(within(targetList).getAllByRole('option')[1]);

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
});
