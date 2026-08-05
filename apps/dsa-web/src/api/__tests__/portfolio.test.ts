// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioApi } from '../portfolio';
import { getParsedApiError, isApiRequestError } from '../error';

const { get, post, put } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get, post, put },
}));

describe('portfolioApi account and paper-trade mapping', () => {
  beforeEach(() => {
    post.mockReset();
  });

  it('keeps real as the default account type and maps the response type', async () => {
    post.mockResolvedValue({
      data: {
        id: 7,
        name: 'Main',
        market: 'us',
        base_currency: 'USD',
        is_active: true,
        account_type: 'real',
      },
    });

    const created = await portfolioApi.createAccount({
      name: 'Main',
      market: 'us',
      baseCurrency: 'USD',
    });

    expect(post).toHaveBeenCalledWith('/api/v1/portfolio/accounts', {
      name: 'Main',
      broker: undefined,
      market: 'us',
      base_currency: 'USD',
      owner_id: undefined,
      account_type: 'real',
    });
    expect(created.accountType).toBe('real');
  });

  it('maps paper account creation and explicit-price paper trades', async () => {
    post
      .mockResolvedValueOnce({
        data: {
          id: 8,
          name: 'Simulation',
          market: 'us',
          base_currency: 'USD',
          is_active: true,
          account_type: 'paper',
        },
      })
      .mockResolvedValueOnce({
        data: { id: 91, price: 205.5, price_source: 'manual' },
      });

    const account = await portfolioApi.createAccount({
      name: 'Simulation',
      market: 'us',
      baseCurrency: 'USD',
      accountType: 'paper',
    });
    const trade = await portfolioApi.createPaperTrade(8, {
      operationId: 'portfolio-paper-1',
      symbol: 'AAPL',
      tradeDate: '2026-07-29',
      side: 'buy',
      quantity: 2,
      price: 205.5,
      note: 'Paper entry',
    });

    expect(account.accountType).toBe('paper');
    expect(trade).toEqual({ id: 91, price: 205.5, priceSource: 'manual' });
  });

  it('omits paper-trade price so the backend can use the latest close', async () => {
    post.mockResolvedValue({
      data: { id: 92, price: 204, price_source: 'latest_close' },
    });

    await portfolioApi.createPaperTrade(8, {
      operationId: 'portfolio-paper-2',
      symbol: 'AAPL',
      tradeDate: '2026-07-29',
      side: 'sell',
      quantity: 1,
    });

    expect(post).toHaveBeenCalledWith(
      '/api/v1/portfolio/accounts/8/paper-trades',
      {
        operation_id: 'portfolio-paper-2',
        symbol: 'AAPL',
        trade_date: '2026-07-29',
        side: 'sell',
        quantity: 1,
      },
      { headers: { 'Idempotency-Key': 'portfolio-paper-2' } },
    );
  });

  it('rejects numeric-string paper trade price (contract is number, not string)', async () => {
    post.mockResolvedValue({
      data: { id: 93, price: '205.5', price_source: 'manual' },
    });

    await expect(
      portfolioApi.createPaperTrade(8, {
        operationId: 'portfolio-paper-3',
        symbol: 'AAPL',
        tradeDate: '2026-07-29',
        side: 'buy',
        quantity: 1,
        price: 205.5,
      }),
    ).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('PaperTradeCreatedResponse');
      return true;
    });
  });
});

describe('portfolioApi.updateAccount', () => {
  beforeEach(() => {
    put.mockReset();
  });

  it('PUTs a snake_case account payload and camelCases the response', async () => {
    put.mockResolvedValue({
      data: { id: 7, name: 'Renamed', broker: 'IBKR', market: 'us', base_currency: 'USD', is_active: true },
    });
    const updated = await portfolioApi.updateAccount(7, {
      name: 'Renamed',
      broker: 'IBKR',
      market: 'us',
      baseCurrency: 'USD',
    });
    expect(put).toHaveBeenCalledWith('/api/v1/portfolio/accounts/7', {
      name: 'Renamed',
      broker: 'IBKR',
      market: 'us',
      base_currency: 'USD',
    });
    expect(updated.baseCurrency).toBe('USD');
  });

  it('omits fields that are not provided', async () => {
    put.mockResolvedValue({ data: { id: 7, name: 'X', market: 'cn', base_currency: 'CNY', is_active: true } });
    await portfolioApi.updateAccount(7, { name: 'X' });
    expect(put).toHaveBeenCalledWith('/api/v1/portfolio/accounts/7', { name: 'X' });
  });
});

describe('portfolioApi idempotent mutations', () => {
  beforeEach(() => {
    post.mockReset();
    post.mockResolvedValue({ data: { id: 42 } });
  });

  it('sends the same trade operation ID in the body and idempotency header', async () => {
    await portfolioApi.createTrade({
      operationId: 'portfolio-trade-1',
      accountId: 7,
      symbol: 'AAPL',
      tradeDate: '2026-07-15',
      side: 'buy',
      quantity: 2,
      price: 210,
    });

    expect(post).toHaveBeenCalledWith('/api/v1/portfolio/trades', expect.objectContaining({
      operation_id: 'portfolio-trade-1',
      account_id: 7,
      symbol: 'AAPL',
    }), {
      headers: { 'Idempotency-Key': 'portfolio-trade-1' },
    });
  });

  it('sends operation IDs for cash and corporate-action writes', async () => {
    await portfolioApi.createCashLedger({
      operationId: 'portfolio-cash-1',
      accountId: 7,
      eventDate: '2026-07-15',
      direction: 'in',
      amount: 1000,
    });
    await portfolioApi.createCorporateAction({
      operationId: 'portfolio-corporate-1',
      accountId: 7,
      symbol: 'AAPL',
      effectiveDate: '2026-07-15',
      actionType: 'cash_dividend',
      cashDividendPerShare: 0.25,
    });

    expect(post.mock.calls[0][2]).toEqual({
      headers: { 'Idempotency-Key': 'portfolio-cash-1' },
    });
    expect(post.mock.calls[1][2]).toEqual({
      headers: { 'Idempotency-Key': 'portfolio-corporate-1' },
    });
  });

  it('sends a CSV commit operation ID in multipart data and the header', async () => {
    post.mockResolvedValueOnce({
      data: {
        account_id: 7,
        record_count: 1,
        inserted_count: 1,
        duplicate_count: 0,
        failed_count: 0,
        dry_run: false,
        errors: [],
      },
    });
    const file = new File(['header\nrow'], 'trades.csv', { type: 'text/csv' });

    await portfolioApi.commitCsvImport(7, 'huatai', file, 'portfolio-csv-1', false);

    const [url, body, config] = post.mock.calls[0] as [string, FormData, Record<string, unknown>];
    expect(url).toBe('/api/v1/portfolio/imports/csv/commit');
    expect(body.get('operation_id')).toBe('portfolio-csv-1');
    expect(config).toEqual({
      headers: {
        'Content-Type': 'multipart/form-data',
        'Idempotency-Key': 'portfolio-csv-1',
      },
    });
  });
});

describe('portfolioApi snapshot money-math validation', () => {
  beforeEach(() => {
    get.mockReset();
  });

  const validSnapshot = {
    as_of: '2026-07-15',
    cost_method: 'avg',
    currency: 'USD',
    account_count: 1,
    total_cash: 10000.5,
    total_market_value: 20500,
    total_equity: 30500.5,
    realized_pnl: 120.25,
    unrealized_pnl: -50.1,
    fee_total: 1.5,
    tax_total: 0,
    fx_stale: false,
    accounts: [
      {
        account_id: 7,
        account_name: 'Main',
        as_of: '2026-07-15',
        base_currency: 'USD',
        cost_method: 'avg',
        market: 'us',
        fee_total: 1.5,
        fx_stale: false,
        realized_pnl: 120.25,
        tax_total: 0,
        total_cash: 10000.5,
        total_equity: 30500.5,
        total_market_value: 20500,
        unrealized_pnl: -50.1,
        positions: [
          {
            symbol: 'AAPL',
            market: 'us',
            currency: 'USD',
            quantity: 10,
            avg_cost: 200,
            total_cost: 2000,
            last_price: 205,
            market_value_base: 2050,
            unrealized_pnl_base: 50,
            valuation_currency: 'USD',
          },
        ],
      },
    ],
  };

  it('camelCases snapshot money fields and preserves extras (pass-through)', async () => {
    get.mockResolvedValue({
      data: { ...validSnapshot, unexpected_server_field: 'keep-me' },
    });

    const snapshot = await portfolioApi.getSnapshot({ accountId: 7 });
    expect(snapshot.totalCash).toBe(10000.5);
    expect(snapshot.totalEquity).toBe(30500.5);
    expect(snapshot.accounts[0].positions[0].lastPrice).toBe(205);
    expect(snapshot).toEqual(expect.objectContaining({ unexpectedServerField: 'keep-me' }));
  });

  it('rejects numeric-string equity/cash (contract is number)', async () => {
    get.mockResolvedValue({
      data: { ...validSnapshot, total_cash: '10000.5', total_equity: '30500.5' },
    });

    await expect(portfolioApi.getSnapshot()).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('PortfolioSnapshotResponse');
      return true;
    });
  });

  it('rejects numeric-string position quantity/price nested under accounts', async () => {
    get.mockResolvedValue({
      data: {
        ...validSnapshot,
        accounts: [{
          ...validSnapshot.accounts[0],
          positions: [{
            ...validSnapshot.accounts[0].positions[0],
            quantity: '10',
            last_price: '205',
          }],
        }],
      },
    });

    await expect(portfolioApi.getSnapshot()).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      return true;
    });
  });
});
