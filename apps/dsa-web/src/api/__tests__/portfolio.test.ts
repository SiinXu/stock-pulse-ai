import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioApi } from '../portfolio';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('../index', () => ({
  default: { post },
}));

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
