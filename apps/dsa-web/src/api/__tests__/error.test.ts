// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { getParsedApiError, parseApiError } from '../error';

describe('stable API error contract', () => {
  it('localizes a known server code and keeps diagnostic copy out of the primary message', () => {
    const parsed = parseApiError({
      response: {
        status: 409,
        data: {
          error: 'duplicate_task',
          message: '股票 600519 正在分析中 (internal worker 7)',
          params: { stock_code: '600519', existing_task_id: 'task-1' },
          details: { worker: 7 },
          trace_id: 'trace-1',
        },
      },
    });

    const english = getParsedApiError(parsed, 'en');
    expect(english.title).toBe('Task already running');
    expect(english.message).toContain('600519');
    expect(english.message).not.toContain('worker');
    expect(english.rawMessage).toContain('internal worker 7');
    expect(english.traceId).toBe('trace-1');
  });

  it('uses localized generic copy for unknown codes while preserving details', () => {
    const parsed = getParsedApiError({
      response: {
        status: 418,
        data: {
          error: 'future_error_code',
          message: 'provider diagnostic in another language',
          params: {},
          details: { reason: 'future' },
          trace_id: 'trace-future',
        },
      },
    }, 'en');

    expect(parsed.title).toBe('Request failed');
    expect(parsed.message).toBe('The request could not be completed. Review the details and try again.');
    expect(parsed.rawMessage).toContain('provider diagnostic');
  });

  it('adapts legacy bare strings to generic UI copy', () => {
    const parsed = getParsedApiError({
      response: { status: 400, data: { detail: 'legacy raw failure' } },
    }, 'en');

    expect(parsed.message).toBe('The request could not be completed. Review the details and try again.');
    expect(parsed.rawMessage).toContain('legacy raw failure');
  });

  it('prefers details and falls back to the deprecated detail alias', () => {
    const canonical = getParsedApiError({
      response: {
        status: 418,
        data: {
          error: 'future_error_code',
          message: 'diagnostic',
          details: { source: 'canonical' },
          detail: { source: 'deprecated' },
        },
      },
    }, 'en');
    const legacy = getParsedApiError({
      response: {
        status: 418,
        data: {
          error: 'future_error_code',
          message: 'diagnostic',
          detail: { source: 'deprecated' },
        },
      },
    }, 'en');

    expect(canonical.details).toEqual({ source: 'canonical' });
    expect(legacy.details).toEqual({ source: 'deprecated' });
  });

  it('preserves non-object values from the deprecated detail alias', () => {
    const legacyArray = getParsedApiError({
      response: {
        status: 422,
        data: {
          error: 'validation_error',
          message: 'diagnostic',
          detail: [{ loc: ['body', 'value'], msg: 'Invalid value' }],
        },
      },
    }, 'en');
    const legacyScalar = getParsedApiError({
      response: {
        status: 409,
        data: {
          error: 'conflict',
          message: 'diagnostic',
          detail: 'safe legacy diagnostic',
        },
      },
    }, 'en');

    expect(legacyArray.details).toEqual([{ loc: ['body', 'value'], msg: 'Invalid value' }]);
    expect(legacyScalar.details).toBe('safe legacy diagnostic');
  });

  it('keeps a valid top-level envelope when diagnostic aliases contain a nested error', () => {
    const diagnostic = {
      error: 'provider_nested_failure',
      message: 'Nested provider diagnostic',
      reason: 'diagnostic-only',
    };
    const parsed = getParsedApiError({
      response: {
        status: 409,
        data: {
          error: 'config_conflict',
          message: 'Top-level configuration conflict',
          params: { current_config_version: 'version-2' },
          details: diagnostic,
          detail: diagnostic,
          trace_id: 'trace-top-level',
        },
      },
    }, 'en');

    expect(parsed.code).toBe('config_conflict');
    expect(parsed.title).toBe('Configuration conflict');
    expect(parsed.params).toEqual({ current_config_version: 'version-2' });
    expect(parsed.details).toEqual(diagnostic);
    expect(parsed.traceId).toBe('trace-top-level');
    expect(parsed.rawMessage).toContain('Top-level configuration conflict');
  });

  it('continues to adapt old service payloads nested under detail', () => {
    const parsed = getParsedApiError({
      response: {
        status: 409,
        data: {
          detail: {
            error: 'duplicate_task',
            message: 'Legacy task conflict',
            stock_code: '600519',
            existing_task_id: 'legacy-task-1',
          },
          trace_id: 'trace-legacy-service',
        },
      },
    }, 'en');

    expect(parsed.code).toBe('duplicate_task');
    expect(parsed.title).toBe('Task already running');
    expect(parsed.message).toContain('600519');
    expect(parsed.params).toEqual({
      stock_code: '600519',
      existing_task_id: 'legacy-task-1',
    });
    expect(parsed.traceId).toBe('trace-legacy-service');
    expect(parsed.rawMessage).toContain('Legacy task conflict');
  });
});
