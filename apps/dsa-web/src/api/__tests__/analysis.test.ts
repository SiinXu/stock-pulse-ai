// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi, DuplicateTaskError } from '../analysis';
import { getParsedApiError } from '../error';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('../index', () => ({
  default: { post },
}));

describe('analysisApi phase request mapping', () => {
  beforeEach(() => {
    post.mockReset();
  });

  it('preserves the automatic phase payload when no override is selected', async () => {
    post.mockResolvedValue({
      status: 202,
      data: { task_id: 'task-auto', status: 'pending', analysis_phase: 'auto' },
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
      data: { accepted: [], duplicates: [] },
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
