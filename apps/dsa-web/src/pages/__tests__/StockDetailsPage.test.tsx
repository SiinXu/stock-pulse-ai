import type React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StockDetailsPage from '../StockDetailsPage';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import { stocksApi } from '../../api/stocks';
import { systemConfigApi } from '../../api/systemConfig';
import {
  APP_ROUTE_PATHS,
  SIGNAL_CENTER_TAB_VALUES,
  buildSignalCenterHref,
} from '../../routing/routes';
import type { StockHistoryResponse, StockQuote } from '../../types/stocks';

vi.mock('../../api/stocks', () => ({
  stocksApi: { getQuote: vi.fn(), getDailyHistory: vi.fn() },
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: { addToWatchlist: vi.fn() },
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  CartesianGrid: () => null,
}));

const getQuoteMock = vi.mocked(stocksApi.getQuote);
const getHistoryMock = vi.mocked(stocksApi.getDailyHistory);
const addWatchlistMock = vi.mocked(systemConfigApi.addToWatchlist);

function SignalLocationProbe() {
  const location = useLocation();
  return <output data-testid="signal-location">{`${location.pathname}${location.search}`}</output>;
}

function makeQuote(overrides: Partial<StockQuote> = {}): StockQuote {
  return {
    stockCode: '600519',
    stockName: 'Kweichow Moutai',
    currentPrice: 1700,
    change: 20,
    changePercent: 1.2,
    open: 1690,
    high: 1710,
    low: 1685,
    prevClose: 1680,
    volume: 12345,
    amount: 67890,
    updateTime: '2026-01-05T09:30:00Z',
    ...overrides,
  };
}

function makeHistory(): StockHistoryResponse {
  return {
    stockCode: '600519',
    stockName: 'Kweichow Moutai',
    period: 'daily',
    data: [
      { date: '2026-01-05', open: 10, high: 12, low: 9, close: 11, volume: 100, changePercent: 1 },
      { date: '2026-01-06', open: 11, high: 13, low: 10, close: 12, volume: 200, changePercent: 2 },
    ],
  };
}

function renderPage(code = '600519') {
  render(
    <UiLanguageProvider initialLanguage="en">
      <MemoryRouter initialEntries={[`/stocks/${code}`]}>
        <Routes>
          <Route path="/stocks/:stockCode" element={<StockDetailsPage />} />
          <Route path="/" element={<div>home-route</div>} />
          <Route path={APP_ROUTE_PATHS.signals} element={<SignalLocationProbe />} />
        </Routes>
      </MemoryRouter>
    </UiLanguageProvider>,
  );
}

describe('StockDetailsPage', () => {
  beforeEach(() => {
    getQuoteMock.mockReset();
    getHistoryMock.mockReset();
    addWatchlistMock.mockReset();
  });

  it('renders the quote and the accessible history table', async () => {
    getQuoteMock.mockResolvedValue(makeQuote());
    getHistoryMock.mockResolvedValue(makeHistory());

    renderPage();

    await waitFor(() => expect(screen.getByText('Kweichow Moutai')).toBeTruthy());
    expect(screen.getByText(/Latest available quote/)).toBeTruthy();
    // history table rows
    expect(screen.getByText('2026-01-05')).toBeTruthy();
    expect(screen.getByText('2026-01-06')).toBeTruthy();
    expect(getHistoryMock).toHaveBeenCalledWith('600519', 90);
  });

  it('fails quote and history independently', async () => {
    getQuoteMock.mockRejectedValue(new Error('quote down'));
    getHistoryMock.mockResolvedValue(makeHistory());

    renderPage();

    // history still renders despite quote failure
    await waitFor(() => expect(screen.getByText('2026-01-05')).toBeTruthy());
    // quote price not shown
    expect(screen.queryByText('1,700')).toBeNull();
  });

  it('adds the canonical code to the watchlist', async () => {
    getQuoteMock.mockResolvedValue(makeQuote());
    getHistoryMock.mockResolvedValue(makeHistory());
    addWatchlistMock.mockResolvedValue(['600519']);

    renderPage();
    await waitFor(() => expect(screen.getByText('Kweichow Moutai')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: 'Add to watchlist' }));
    await waitFor(() => expect(addWatchlistMock).toHaveBeenCalledWith('600519'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'In watchlist' })).toBeTruthy());
  });

  it('deep-links rule creation from the current stock into the Signal Center', async () => {
    getQuoteMock.mockResolvedValue(makeQuote());
    getHistoryMock.mockResolvedValue(makeHistory());

    renderPage();
    await waitFor(() => expect(screen.getByText('Kweichow Moutai')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: 'Create rule from this signal' }));

    expect(await screen.findByTestId('signal-location'))
      .toHaveTextContent(buildSignalCenterHref({
        tab: SIGNAL_CENTER_TAB_VALUES.rules,
        createRule: true,
        stock: '600519',
      }));
  });

  it('canonicalizes an equivalent stock-code spelling in the route', async () => {
    getQuoteMock.mockResolvedValue(makeQuote({ stockCode: 'HK00700', stockName: 'Tencent' }));
    getHistoryMock.mockResolvedValue({ ...makeHistory(), stockCode: 'HK00700' });

    renderPage('00700');

    // The page redirects 00700 -> HK00700 and loads the canonical code.
    await waitFor(() => expect(getQuoteMock).toHaveBeenCalledWith('HK00700'));
  });
});
