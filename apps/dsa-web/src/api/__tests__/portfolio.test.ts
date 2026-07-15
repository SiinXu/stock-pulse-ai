import { beforeEach, describe, expect, it, vi } from 'vitest';
import { portfolioApi } from '../portfolio';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('../index', () => ({
  default: { post },
}));

describe('portfolioApi idempotency', () => {
  beforeEach(() => {
    post.mockReset();
    post.mockResolvedValue({ data: { id: 17 } });
  });

  it('sends one operation ID in the trade body and Idempotency-Key header', async () => {
    await portfolioApi.createTrade({
      accountId: 1,
      symbol: '600519',
      tradeDate: '2026-01-02',
      side: 'buy',
      quantity: 10,
      price: 100,
      operationId: 'trade-operation-1',
    });

    expect(post).toHaveBeenCalledWith(
      '/api/v1/portfolio/trades',
      expect.objectContaining({
        account_id: 1,
        operation_id: 'trade-operation-1',
      }),
      { headers: { 'Idempotency-Key': 'trade-operation-1' } },
    );
  });

  it('sends the same operation ID for a CSV commit form and header', async () => {
    post.mockResolvedValueOnce({
      data: {
        account_id: 1,
        record_count: 1,
        inserted_count: 1,
        duplicate_count: 0,
        failed_count: 0,
        dry_run: false,
        errors: [],
      },
    });
    const file = new File(['csv'], 'trades.csv', { type: 'text/csv' });

    await portfolioApi.commitCsvImport(1, 'huatai', file, false, 'csv-operation-1');

    const [, body, config] = post.mock.calls[0];
    expect(body).toBeInstanceOf(FormData);
    expect(body.get('operation_id')).toBe('csv-operation-1');
    expect(config.headers['Idempotency-Key']).toBe('csv-operation-1');
  });
});
