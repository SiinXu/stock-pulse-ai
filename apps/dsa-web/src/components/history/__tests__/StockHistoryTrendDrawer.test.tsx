import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { StockHistoryTrendDrawer } from '../StockHistoryTrendDrawer';
import type { AnalysisReport, HistoryItem } from '../../../types/analysis';

const report: AnalysisReport = {
  meta: {
    id: 1,
    queryId: 'q-1',
    stockCode: '600519',
    stockName: '贵州茅台',
    reportType: 'detailed',
    createdAt: '2026-03-20T08:00:00Z',
  },
  summary: {
    analysisSummary: '等待确认',
    operationAdvice: '买入',
    action: 'avoid',
    actionLabel: '回避',
    trendPrediction: '震荡',
    sentimentScore: 35,
  },
};

const items: HistoryItem[] = [
  {
    id: 1,
    queryId: 'q-1',
    stockCode: '600519',
    stockName: '贵州茅台',
    sentimentScore: 35,
    operationAdvice: '买入',
    action: 'avoid',
    actionLabel: '回避',
    trendPrediction: '震荡',
    modelUsed: 'openai/gpt-test',
    createdAt: '2026-03-20T08:00:00Z',
  },
];

describe('StockHistoryTrendDrawer', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('uses structured action in summary and rows', () => {
    render(
      <StockHistoryTrendDrawer
        report={report}
        items={items}
        total={1}
        hasMore={false}
        isLoading={false}
        isLoadingMore={false}
        filters={{ range: 'all', model: 'all', sort: 'desc' }}
        onClose={vi.fn()}
        onRangeChange={vi.fn()}
        onLoadMore={vi.fn()}
        onSelectRecord={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getAllByText('回避').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('买入')).not.toBeInTheDocument();
    for (const rangeButton of ['全部历史', '近30天', '近90天'].map((name) => screen.getByRole('button', { name }))) {
      expect(rangeButton).toHaveClass('min-h-11', 'min-w-11');
    }
    expect(screen.getByRole('button', { name: '查看报告' })).toHaveClass('min-h-11', 'min-w-11');
    const model = within(screen.getByRole('table')).getByText('gpt-test');
    fireEvent.mouseEnter(model);
    expect(screen.getByRole('tooltip')).toHaveTextContent('openai/gpt-test');
  });

  it('keeps fixed proportional columns, keyboard row selection, and nested report actions isolated', () => {
    const onClose = vi.fn();
    const onSelectRecord = vi.fn();
    render(
      <StockHistoryTrendDrawer
        report={report}
        items={[
          items[0],
          {
            ...items[0],
            id: 2,
            queryId: 'q-2',
            createdAt: '2026-03-19T08:00:00Z',
          },
        ]}
        total={2}
        hasMore={false}
        isLoading={false}
        isLoadingMore={false}
        filters={{ range: 'all', model: 'all', sort: 'desc' }}
        onClose={onClose}
        onRangeChange={vi.fn()}
        onLoadMore={vi.fn()}
        onSelectRecord={onSelectRecord}
        onRetry={vi.fn()}
      />,
    );

    const table = screen.getByRole('table', { name: '历史分析记录' });
    const [, firstRow, secondRow] = within(table).getAllByRole('row');
    expect(table).toHaveAttribute('data-layout', 'fixed');
    expect(table).toHaveClass('min-w-[64rem]');
    expect(table.querySelectorAll('colgroup col')).toHaveLength(9);
    expect(table.parentElement).toHaveAttribute('data-data-table', 'ready');
    expect(table.parentElement).not.toHaveAttribute('data-surface-level');
    expect(firstRow).toHaveAttribute('aria-selected', 'true');
    expect(secondRow).toHaveAttribute('aria-selected', 'false');

    fireEvent.keyDown(secondRow, { key: 'Enter' });
    expect(firstRow).toHaveAttribute('aria-selected', 'false');
    expect(secondRow).toHaveAttribute('aria-selected', 'true');

    fireEvent.click(within(firstRow).getByRole('button', { name: '查看报告' }));
    expect(onSelectRecord).toHaveBeenCalledWith(1);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(secondRow).toHaveAttribute('aria-selected', 'true');
  });

  it('keeps full legacy operation advice when structured action is absent', () => {
    render(
      <StockHistoryTrendDrawer
        report={{
          ...report,
          summary: {
            ...report.summary,
            operationAdvice: '继续持有，等待突破',
            action: null,
            actionLabel: null,
          },
        }}
        items={[
          {
            ...items[0],
            operationAdvice: '继续持有，等待突破',
            action: null,
            actionLabel: null,
          },
        ]}
        total={1}
        hasMore={false}
        isLoading={false}
        isLoadingMore={false}
        filters={{ range: 'all', model: 'all', sort: 'desc' }}
        onClose={vi.fn()}
        onRangeChange={vi.fn()}
        onLoadMore={vi.fn()}
        onSelectRecord={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getAllByText('继续持有，等待突破').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('持有')).not.toBeInTheDocument();
  });

  it('keeps multi-guard legacy advice as full text when structured action is absent', () => {
    render(
      <StockHistoryTrendDrawer
        report={{
          ...report,
          summary: {
            ...report.summary,
            operationAdvice: 'risk alert, avoid buying',
            action: null,
            actionLabel: null,
          },
        }}
        items={[
          {
            ...items[0],
            operationAdvice: 'risk alert, avoid buying',
            action: null,
            actionLabel: null,
          },
        ]}
        total={1}
        hasMore={false}
        isLoading={false}
        isLoadingMore={false}
        filters={{ range: 'all', model: 'all', sort: 'desc' }}
        onClose={vi.fn()}
        onRangeChange={vi.fn()}
        onLoadMore={vi.fn()}
        onSelectRecord={vi.fn()}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getAllByText('risk alert, avoid buying').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('回避')).not.toBeInTheDocument();
    expect(screen.queryByText('预警')).not.toBeInTheDocument();
  });

  it('uses localized taxonomy labels before server labels in English UI mode', () => {
    window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');

    render(
      <UiLanguageProvider>
        <StockHistoryTrendDrawer
          report={{
            ...report,
            summary: {
              ...report.summary,
              action: 'sell',
              actionLabel: '买入',
            },
          }}
          items={[
            {
              ...items[0],
              action: 'sell',
              actionLabel: '买入',
            },
          ]}
          total={1}
          hasMore={false}
          isLoading={false}
          isLoadingMore={false}
          filters={{ range: 'all', model: 'all', sort: 'desc' }}
          onClose={vi.fn()}
          onRangeChange={vi.fn()}
          onLoadMore={vi.fn()}
          onSelectRecord={vi.fn()}
          onRetry={vi.fn()}
        />
      </UiLanguageProvider>,
    );

    expect(screen.getAllByText('Sell').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('买入')).not.toBeInTheDocument();
  });
});
