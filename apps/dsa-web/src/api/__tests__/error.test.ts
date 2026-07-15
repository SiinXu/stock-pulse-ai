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
});
