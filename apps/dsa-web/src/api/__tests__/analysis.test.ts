import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi, DuplicateTaskError } from '../analysis';
import { getParsedApiError } from '../error';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('../index', () => ({
  default: { post },
}));

describe('analysisApi conflict handling', () => {
  beforeEach(() => {
    post.mockReset();
  });

  it('creates a duplicate domain error only for duplicate_task and retains its envelope', async () => {
    post.mockResolvedValueOnce({
      status: 409,
      data: {
        error: 'duplicate_task',
        message: 'diagnostic duplicate message',
        params: { stock_code: '600519.SH', existing_task_id: 'task-current' },
        details: { worker: 7 },
        trace_id: 'trace-duplicate',
      },
    });

    const failure = await analysisApi.analyzeAsync({ stockCode: '600519.SH' })
      .catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(DuplicateTaskError);
    expect(failure).toMatchObject({
      code: 'duplicate_task',
      stockCode: '600519.SH',
      existingTaskId: 'task-current',
      params: { stock_code: '600519.SH', existing_task_id: 'task-current' },
      details: { worker: 7 },
      traceId: 'trace-duplicate',
    });
    expect(getParsedApiError(failure, 'en')).toMatchObject({
      code: 'duplicate_task',
      message: 'An analysis task for 600519.SH is already running.',
      traceId: 'trace-duplicate',
    });
  });

  it('keeps compatibility with legacy top-level duplicate fields', async () => {
    post.mockResolvedValueOnce({
      status: 409,
      data: {
        error: 'duplicate_task',
        message: 'legacy duplicate message',
        stock_code: 'AAPL',
        existing_task_id: 'task-legacy',
      },
    });

    const failure = await analysisApi.analyzeAsync({ stockCode: 'AAPL' })
      .catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(DuplicateTaskError);
    expect(failure).toMatchObject({
      stockCode: 'AAPL',
      existingTaskId: 'task-legacy',
    });
  });

  it('routes a non-duplicate analysis 409 through the shared stable parser', async () => {
    post.mockResolvedValueOnce({
      status: 409,
      data: {
        error: 'config_conflict',
        message: 'server configuration changed',
        params: { server_version: 'v2' },
        details: { expected: 'v1' },
        trace_id: 'trace-conflict',
      },
    });

    const failure = await analysisApi.analyzeAsync({ stockCode: 'AAPL' })
      .catch((error: unknown) => error);

    expect(failure).not.toBeInstanceOf(DuplicateTaskError);
    expect(getParsedApiError(failure, 'en')).toMatchObject({
      code: 'config_conflict',
      details: { expected: 'v1' },
      traceId: 'trace-conflict',
    });
  });

  it('preserves the stable Market Review conflict envelope', async () => {
    post.mockResolvedValueOnce({
      status: 409,
      data: {
        error: 'duplicate_market_review',
        message: 'diagnostic market review message',
        params: {},
        details: { lock: 'held' },
        trace_id: 'trace-market-review',
      },
    });

    const failure = await analysisApi.triggerMarketReview()
      .catch((error: unknown) => error);

    expect(getParsedApiError(failure, 'en')).toMatchObject({
      code: 'duplicate_market_review',
      message: 'Wait for the current market review to finish.',
      details: { lock: 'held' },
      traceId: 'trace-market-review',
    });
  });
});
