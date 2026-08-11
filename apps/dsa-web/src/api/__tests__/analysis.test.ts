// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi, DuplicateTaskError } from '../analysis';
import { getParsedApiError, isApiRequestError } from '../error';

const { post, get } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));

vi.mock('../index', () => ({
  default: {
    post,
    get,
    defaults: { baseURL: '' },
  },
  locallyRecoverableResourceConfig: () => ({}),
}));

function taskAcceptedWire(overrides: Record<string, unknown> = {}) {
  return {
    task_id: 'task-auto',
    status: 'pending',
    message_code: 'task.queued',
    analysis_phase: 'auto',
    ...overrides,
  };
}

describe('analysisApi phase request mapping', () => {
  beforeEach(() => {
    post.mockReset();
  });

  it('preserves the automatic phase payload when no override is selected', async () => {
    post.mockResolvedValue({
      status: 202,
      data: taskAcceptedWire(),
    });

    await analysisApi.analyzeAsync({ stockCode: 'AAPL' });

    expect(post.mock.calls[0][0]).toBe('/api/v1/analysis/analyze');
    expect(post.mock.calls[0][1]).toEqual({
      stock_code: 'AAPL',
      stock_codes: undefined,
      report_type: 'detailed',
      force_refresh: false,
      async_mode: true,
      analysis_phase: 'auto',
      stock_name: undefined,
      original_query: undefined,
      selection_source: undefined,
      skills: undefined,
      report_language: undefined,
    });
    expect(post.mock.calls[0][2]).toEqual({
      validateStatus: expect.any(Function),
    });
  });

  it('maps an explicit phase exactly for a batch request', async () => {
    post.mockResolvedValue({
      status: 202,
      data: {
        message: 'submitted',
        accepted: [],
        duplicates: [],
      },
    });

    await analysisApi.analyzeAsync({
      stockCodes: ['AAPL', 'MSFT'],
      reportType: 'brief',
      forceRefresh: true,
      analysisPhase: 'postmarket',
      notify: false,
      skills: ['quality'],
      reportLanguage: 'en',
    });

    expect(post.mock.calls[0][1]).toEqual({
      stock_code: undefined,
      stock_codes: ['AAPL', 'MSFT'],
      report_type: 'brief',
      force_refresh: true,
      async_mode: true,
      analysis_phase: 'postmarket',
      stock_name: undefined,
      original_query: undefined,
      selection_source: undefined,
      skills: ['quality'],
      report_language: 'en',
      notify: false,
    });
  });
});

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

describe('analysisApi response validation', () => {
  beforeEach(() => {
    post.mockReset();
    get.mockReset();
  });

  it('camelCases async accept payloads and preserves extra keys (pass-through)', async () => {
    post.mockResolvedValue({
      status: 202,
      data: {
        ...taskAcceptedWire({ unexpected_server_field: 'keep-me' }),
      },
    });

    const result = await analysisApi.analyzeAsync({ stockCode: 'AAPL' });
    expect(result).toEqual({
      taskId: 'task-auto',
      status: 'pending',
      messageCode: 'task.queued',
      analysisPhase: 'auto',
      unexpectedServerField: 'keep-me',
    });
  });

  it('surfaces analyzeAsync shape mismatches through ParsedApiError', async () => {
    post.mockResolvedValue({
      status: 202,
      data: {
        // missing task_id / message for both accepted shapes
        status: 'pending',
      },
    });

    await expect(analysisApi.analyzeAsync({ stockCode: 'AAPL' })).rejects.toSatisfy(
      (error: unknown) => {
        expect(isApiRequestError(error)).toBe(true);
        const parsed = getParsedApiError(error);
        expect(parsed.code).toBe('api_response_validation_failed');
        expect(parsed.message).toContain('AnalyzeAsyncResponse');
        return true;
      },
    );
  });

  it('validates market-review accepted payloads and rejects missing required fields', async () => {
    post.mockResolvedValueOnce({
      status: 202,
      data: {
        status: 'accepted',
        message: 'queued',
        message_code: 'task.market_review.queued',
        send_notification: true,
        region: 'cn',
        unexpected_flag: true,
      },
    });

    const accepted = await analysisApi.triggerMarketReview();
    expect(accepted).toEqual({
      status: 'accepted',
      message: 'queued',
      messageCode: 'task.market_review.queued',
      sendNotification: true,
      region: 'cn',
      unexpectedFlag: true,
    });

    post.mockResolvedValueOnce({
      status: 202,
      data: {
        status: 'accepted',
        message: 'queued',
        // message_code / send_notification / region missing
      },
    });

    await expect(analysisApi.triggerMarketReview()).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params).toMatchObject({ label: 'MarketReviewAccepted' });
      return true;
    });
  });

  it('validates task status and list responses', async () => {
    get.mockResolvedValueOnce({
      data: {
        task_id: 't1',
        status: 'processing',
        message_code: 'task.status',
        progress: 40,
        unexpected_nested: { keep: true },
      },
    });

    const status = await analysisApi.getStatus('t1');
    expect(status).toEqual({
      taskId: 't1',
      status: 'processing',
      messageCode: 'task.status',
      progress: 40,
      unexpectedNested: { keep: true },
    });

    get.mockResolvedValueOnce({
      data: {
        // task_id missing
        status: 'processing',
        message_code: 'task.status',
      },
    });

    await expect(analysisApi.getStatus('t1')).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params).toMatchObject({ label: 'TaskStatus' });
      return true;
    });

    get.mockResolvedValueOnce({
      data: {
        total: 1,
        pending: 0,
        processing: 1,
        tasks: [{
          task_id: 't1',
          stock_code: 'AAPL',
          status: 'processing',
          progress: 10,
          report_type: 'detailed',
          created_at: '2026-01-01T00:00:00Z',
          message_code: 'task.status',
          analysis_phase: 'auto',
        }],
      },
    });

    const list = await analysisApi.getTasks();
    expect(list.tasks[0].stockCode).toBe('AAPL');
  });
});
