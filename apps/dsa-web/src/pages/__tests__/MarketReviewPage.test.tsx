// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi } from '../../api/analysis';
import { historyApi } from '../../api/history';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import { useStockPoolStore } from '../../stores/stockPoolStore';
import MarketReviewPage from '../MarketReviewPage';

vi.mock('../../api/history', () => ({
  historyApi: {
    getList: vi.fn(),
    getDetail: vi.fn(),
    getNews: vi.fn().mockResolvedValue({ total: 0, items: [] }),
    getMarkdown: vi.fn().mockResolvedValue('# Market review'),
    getDiagnostics: vi.fn(),
    getRecordFlow: vi.fn(),
    deleteRecords: vi.fn(),
  },
}));

vi.mock('../../api/analysis', async () => {
  const actual = await vi.importActual<typeof import('../../api/analysis')>('../../api/analysis');
  return {
    ...actual,
    analysisApi: {
      ...actual.analysisApi,
      triggerMarketReview: vi.fn(),
      getStatus: vi.fn(),
    },
  };
});

const marketReviewHistoryItem = {
  id: 2,
  queryId: 'market-task',
  stockCode: 'MARKET',
  stockName: '大盘复盘',
  reportType: 'market_review' as const,
  createdAt: '2026-07-22T08:00:00Z',
};

const marketReviewReport = {
  meta: {
    ...marketReviewHistoryItem,
    reportLanguage: 'zh' as const,
  },
  summary: {
    analysisSummary: '大盘复盘摘要',
    operationAdvice: '关注量能变化',
    trendPrediction: '震荡偏强',
    sentimentScore: 65,
  },
};

const stockReport = {
  meta: {
    id: 1,
    queryId: 'stock-task',
    stockCode: '600519',
    stockName: '贵州茅台',
    reportType: 'detailed' as const,
    reportLanguage: 'zh' as const,
    createdAt: '2026-07-22T08:00:00Z',
  },
  summary: {
    analysisSummary: '个股报告不得留在大盘复盘页面',
    operationAdvice: '观察',
    trendPrediction: '震荡',
    sentimentScore: 55,
  },
};

function LocationProbe() {
  const location = useLocation();
  return <output>{`${location.pathname}${location.search}${location.hash}`}</output>;
}

function renderMarketReview(initialEntry: string = APP_ROUTE_PATHS.researchMarket) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path={APP_ROUTE_PATHS.researchMarket} element={<MarketReviewPage />} />
        <Route path={APP_ROUTE_PATHS.home} element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('MarketReviewPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.sessionStorage.clear();
    useStockPoolStore.getState().resetDashboardState();
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 0,
      page: 1,
      limit: 10,
      items: [],
    });
    vi.mocked(historyApi.getDetail).mockResolvedValue(marketReviewReport);
    vi.mocked(analysisApi.triggerMarketReview).mockResolvedValue({
      status: 'accepted',
      sendNotification: true,
      message: '大盘复盘任务已提交',
    });
  });

  it('owns market-review history and gives the empty state a primary action', async () => {
    renderMarketReview();

    expect(await screen.findByRole('heading', { name: '大盘复盘' })).toBeInTheDocument();
    await waitFor(() => {
      expect(historyApi.getList).toHaveBeenCalledWith({
        stockCode: 'MARKET',
        reportType: 'market_review',
        page: 1,
        limit: 10,
      });
    });
    expect(document.title).toBe('大盘复盘 - StockPulse');
    const primaryActions = screen.getAllByRole('button', { name: '大盘复盘' });
    expect(primaryActions.length).toBeGreaterThanOrEqual(2);
    expect(primaryActions.every((button) => button.getAttribute('data-variant') === 'primary')).toBe(true);
  });

  it('loads a persisted market report from canonical URL state', async () => {
    vi.mocked(historyApi.getList).mockResolvedValue({
      total: 1,
      page: 1,
      limit: 10,
      items: [marketReviewHistoryItem],
    });
    vi.mocked(historyApi.getDetail).mockResolvedValue(marketReviewReport);

    renderMarketReview(`${APP_ROUTE_PATHS.researchMarket}?recordId=2`);

    expect(await screen.findByText('大盘复盘摘要')).toBeInTheDocument();
    expect(historyApi.getDetail).toHaveBeenCalledWith(2);
    expect(screen.getByRole('button', { name: '重新复盘' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重新分析' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '追问 AI' })).not.toBeInTheDocument();
  });

  it('renders only the matching persisted result after a completed task', async () => {
    vi.mocked(historyApi.getList)
      .mockResolvedValueOnce({ total: 0, page: 1, limit: 10, items: [] })
      .mockResolvedValue({
        total: 1,
        page: 1,
        limit: 10,
        items: [marketReviewHistoryItem],
      });
    vi.mocked(historyApi.getDetail).mockResolvedValue(marketReviewReport);
    vi.mocked(analysisApi.triggerMarketReview).mockResolvedValue({
      status: 'accepted',
      sendNotification: true,
      message: '大盘复盘任务已提交',
      taskId: 'market-task',
    });
    vi.mocked(analysisApi.getStatus).mockResolvedValue({
      taskId: 'market-task',
      status: 'completed',
      marketReviewReport: 'RAW_TASK_OUTPUT_MUST_NOT_RENDER',
    });

    renderMarketReview();
    fireEvent.click((await screen.findAllByRole('button', { name: '大盘复盘' }))[0]);

    expect(await screen.findByText('大盘复盘摘要')).toBeInTheDocument();
    expect(screen.getByText('大盘复盘任务已完成，结果如下：')).toBeInTheDocument();
    expect(screen.queryByText('RAW_TASK_OUTPUT_MUST_NOT_RENDER')).not.toBeInTheDocument();
    expect(historyApi.getDetail).toHaveBeenCalledWith(2);
  });

  it('redirects a non-market record to Home while preserving query and hash', async () => {
    vi.mocked(historyApi.getDetail).mockResolvedValue(stockReport);

    renderMarketReview(
      `${APP_ROUTE_PATHS.researchMarket}?recordId=1&keep=yes#snapshot`,
    );

    expect(await screen.findByText('/?recordId=1&keep=yes#snapshot')).toBeInTheDocument();
    expect(screen.queryByText('个股报告不得留在大盘复盘页面')).not.toBeInTheDocument();
  });
});
