import type React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StockDetailsPage from '../StockDetailsPage';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import { stocksApi } from '../../api/stocks';
import { systemConfigApi } from '../../api/systemConfig';
import { estimateStockValuation } from '../../api/valuation';
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
  systemConfigApi: {
    addToWatchlist: vi.fn(),
    getConfig: vi.fn().mockResolvedValue({ configVersion: 'test', maskToken: '******', items: [] }),
  },
}));

vi.mock('../../api/valuation', () => ({
  estimateStockValuation: vi.fn(),
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

function wrapWithQueryClient(ui: ReactElement): ReactElement {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

function renderPage(code = '600519') {
  return render(
    wrapWithQueryClient(
      <UiLanguageProvider initialLanguage="en">
        <MemoryRouter initialEntries={[`/stocks/${code}`]}>
          <Routes>
            <Route path="/stocks/:stockCode" element={<StockDetailsPage />} />
            <Route path="/" element={<div>home-route</div>} />
            <Route path={APP_ROUTE_PATHS.signals} element={<SignalLocationProbe />} />
          </Routes>
        </MemoryRouter>
      </UiLanguageProvider>,
    ),
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
    // CN market: currency code + 2dp from marketFormat
    expect(screen.getByText('CNY 1,700.00')).toBeTruthy();
    // CN convention red_up: positive change uses red paint token
    const changeNode = screen.getByText(/\+20\.00/);
    expect(changeNode.getAttribute('data-change-color')).toBe('red');
    expect(changeNode.getAttribute('data-change-pref')).toBe('red_up');
    // history table rows
    expect(screen.getByText('2026-01-05')).toBeTruthy();
    expect(screen.getByText('2026-01-06')).toBeTruthy();
    expect(getHistoryMock).toHaveBeenCalledWith('600519', 90);
  });

  it('formats US quotes with green_up convention and USD currency', async () => {
    getQuoteMock.mockResolvedValue(makeQuote({
      stockCode: 'AAPL',
      stockName: 'Apple',
      currentPrice: 189.1,
      change: 1.25,
      changePercent: 0.66,
    }));
    getHistoryMock.mockResolvedValue({
      stockCode: 'AAPL',
      stockName: 'Apple',
      period: 'daily',
      data: [
        { date: '2026-01-05', open: 180, high: 190, low: 179, close: 189.1, volume: 100, changePercent: 0.66 },
      ],
    });

    renderPage('AAPL');

    await waitFor(() => expect(screen.getByText('Apple')).toBeTruthy());
    expect(screen.getAllByText('USD 189.10').length).toBeGreaterThanOrEqual(1);
    const changeNode = screen.getByText(/\+1\.25/);
    expect(changeNode.getAttribute('data-change-color')).toBe('green');
    expect(changeNode.getAttribute('data-change-pref')).toBe('green_up');
  });

  it('formats HK quotes with HKD 3dp and red_up convention', async () => {
    getQuoteMock.mockResolvedValue(makeQuote({
      stockCode: 'HK00700',
      stockName: 'Tencent',
      currentPrice: 321.12345,
      change: -1.5,
      changePercent: -0.46,
    }));
    getHistoryMock.mockResolvedValue({
      stockCode: 'HK00700',
      stockName: 'Tencent',
      period: 'daily',
      data: [
        { date: '2026-01-05', open: 320, high: 322, low: 319, close: 321.123, volume: 100, changePercent: -0.46 },
      ],
    });

    renderPage('HK00700');

    await waitFor(() => expect(screen.getByText('Tencent')).toBeTruthy());
    expect(screen.getAllByText('HKD 321.123').length).toBeGreaterThanOrEqual(1);
    const changeNode = screen.getByText(/-1\.500/);
    expect(changeNode.getAttribute('data-change-color')).toBe('green');
    expect(changeNode.getAttribute('data-change-pref')).toBe('red_up');
  });

  it('renders non-finite known-market quote and candle numbers as missing and neutral', async () => {
    getQuoteMock.mockResolvedValue(makeQuote({
      currentPrice: Number.POSITIVE_INFINITY,
      change: Number.POSITIVE_INFINITY,
      changePercent: Number.NEGATIVE_INFINITY,
      open: Number.NEGATIVE_INFINITY,
      high: Number.POSITIVE_INFINITY,
      low: Number.NEGATIVE_INFINITY,
      prevClose: Number.POSITIVE_INFINITY,
      volume: Number.POSITIVE_INFINITY,
      amount: Number.NEGATIVE_INFINITY,
    }));
    getHistoryMock.mockResolvedValue({
      ...makeHistory(),
      data: [{
        date: '2026-01-05',
        open: Number.POSITIVE_INFINITY,
        high: Number.NEGATIVE_INFINITY,
        low: Number.POSITIVE_INFINITY,
        close: Number.NEGATIVE_INFINITY,
        volume: Number.POSITIVE_INFINITY,
        changePercent: Number.NEGATIVE_INFINITY,
      }],
    });

    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText('Kweichow Moutai')).toBeTruthy());
    const changeNode = screen.getByText('— (—)');
    expect(changeNode).toHaveAttribute('data-change-direction', 'flat');
    expect(changeNode).toHaveAttribute('data-change-color', 'neutral');
    expect(changeNode).not.toHaveStyle({ color: 'var(--home-price-up)' });
    expect(changeNode).not.toHaveStyle({ color: 'var(--home-price-down)' });
    expect(container.textContent).not.toMatch(/∞|Infinity/);
  });

  it('renders non-finite unknown-market fallback numbers as missing', async () => {
    getQuoteMock.mockResolvedValue(makeQuote({
      stockCode: '7203.T',
      stockName: 'Toyota',
      currentPrice: Number.POSITIVE_INFINITY,
      change: Number.NEGATIVE_INFINITY,
      changePercent: Number.POSITIVE_INFINITY,
      open: Number.NEGATIVE_INFINITY,
      high: Number.POSITIVE_INFINITY,
      low: Number.NEGATIVE_INFINITY,
      prevClose: Number.POSITIVE_INFINITY,
      volume: Number.NEGATIVE_INFINITY,
      amount: Number.POSITIVE_INFINITY,
    }));
    getHistoryMock.mockResolvedValue({
      ...makeHistory(),
      stockCode: '7203.T',
      stockName: 'Toyota',
      data: [],
    });

    const { container } = renderPage('7203.T');

    await waitFor(() => expect(screen.getByText('Toyota')).toBeTruthy());
    const changeNode = screen.getByText('— (—)');
    expect(changeNode).not.toHaveAttribute('data-change-direction');
    expect(changeNode).not.toHaveAttribute('data-change-color');
    expect(container.textContent).not.toMatch(/∞|Infinity/);
  });

  it('fails quote and history independently', async () => {
    getQuoteMock.mockRejectedValue(new Error('quote down'));
    getHistoryMock.mockResolvedValue(makeHistory());

    renderPage();

    // history still renders despite quote failure
    await waitFor(() => expect(screen.getByText('2026-01-05')).toBeTruthy());
    // quote price not shown (currency-formatted form either)
    expect(screen.queryByText('CNY 1,700.00')).toBeNull();
    expect(screen.queryByText(/1,700/)).toBeNull();
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
  it('mounts the DCF sensitivity panel with the stock code from the route', async () => {
    getQuoteMock.mockResolvedValue(makeQuote());
    getHistoryMock.mockResolvedValue(makeHistory());
    vi.mocked(estimateStockValuation).mockResolvedValue({
      status: 'ok',
      stockCode: '600519',
      dcf: {
        status: 'ok',
        equityValue: 100,
        intrinsicValuePerShare: 10,
        assumptions: {
          growthRate: 0.05,
          discountRate: 0.1,
          terminalGrowthRate: 0.03,
          projectionYears: 5,
        },
        sensitivity: {
          rows: [
            { growthRate: 0.04, discountRate: 0.1, equityValue: 90 },
            { growthRate: 0.05, discountRate: 0.1, equityValue: 100 },
          ],
        },
      },
    });

    renderPage('600519');

    expect(await screen.findByTestId('stock-details-dcf-section')).toBeInTheDocument();
    expect(screen.getByTestId('dcf-sensitivity-panel')).toBeInTheDocument();
    expect(screen.getByTestId('dcf-stock-code')).toHaveValue('600519');
  });

});
