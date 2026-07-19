// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioApi } from '../portfolio';

const { post, put } = vi.hoisted(() => ({ post: vi.fn(), put: vi.fn() }));

vi.mock('../index', () => ({
  default: { post, put },
}));

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
    expect(updated.market).toBe('us');
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

    expect(post.mock.calls[0][1]).toEqual(expect.objectContaining({
      operation_id: 'portfolio-cash-1',
    }));
    expect(post.mock.calls[0][2]).toEqual({
      headers: { 'Idempotency-Key': 'portfolio-cash-1' },
    });
    expect(post.mock.calls[1][1]).toEqual(expect.objectContaining({
      operation_id: 'portfolio-corporate-1',
    }));
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
    expect(body.get('account_id')).toBe('7');
    expect(body.get('dry_run')).toBe('false');
    expect(body.get('file')).toBe(file);
    expect(config).toEqual({
      headers: {
        'Content-Type': 'multipart/form-data',
        'Idempotency-Key': 'portfolio-csv-1',
      },
    });
  });
});
