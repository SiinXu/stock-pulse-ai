import { describe, expect, it } from 'vitest';

import { localizeParsedApiError, parseApiError } from '../error';

describe('stable API error parsing', () => {
  it('localizes a known code and keeps server diagnostics out of primary copy', () => {
    const parsed = parseApiError({
      response: {
        status: 401,
        data: {
          error: 'invalid_password',
          message: '密码错误：backend diagnostic only',
          params: { attempts: 2 },
          details: { reason: 'mismatch' },
          trace_id: 'trace-auth',
        },
      },
    });

    expect(parsed).toMatchObject({
      code: 'invalid_password',
      title: '密码验证失败',
      message: '请检查密码后重试。',
      params: { attempts: 2 },
      details: { reason: 'mismatch' },
      traceId: 'trace-auth',
    });
    expect(parsed.rawMessage).toContain('backend diagnostic only');
    expect(parsed.rawMessage).toContain('trace-auth');

    expect(localizeParsedApiError(parsed, 'en')).toMatchObject({
      title: 'Password verification failed',
      message: 'Check the password and try again.',
    });
  });

  it('uses generic localized primary copy for unknown codes', () => {
    const parsed = parseApiError({
      response: {
        status: 400,
        data: {
          error: 'future_server_code',
          message: '服务端原始中文诊断',
          details: { field: 'route' },
        },
      },
    });

    expect(parsed).toMatchObject({
      code: 'future_server_code',
      title: '请求失败',
      message: '请求未能完成，请稍后重试。',
      category: 'unknown',
    });
    expect(parsed.rawMessage).toContain('服务端原始中文诊断');
    expect(localizeParsedApiError(parsed, 'en')).toMatchObject({
      title: 'Request failed',
      message: 'The request could not be completed. Try again later.',
    });
  });

  it('adapts a legacy raw response without promoting it to primary copy', () => {
    const parsed = parseApiError({
      response: { status: 400, data: 'legacy raw server failure' },
    });

    expect(parsed).toMatchObject({
      title: '请求失败',
      message: '请求未能完成，请稍后重试。',
      category: 'http_error',
    });
    expect(parsed.rawMessage).toBe('legacy raw server failure');
  });

  it('does not expose a server-side 500 diagnostic even in details', () => {
    const parsed = parseApiError({
      response: {
        status: 500,
        data: {
          error: 'internal_error',
          message: 'database password=super-secret',
          details: { exception: 'token=super-secret' },
          trace_id: 'trace-internal',
        },
      },
    });

    expect(parsed.rawMessage).toBe('Trace ID: trace-internal');
    expect(JSON.stringify(parsed)).not.toContain('super-secret');
  });
});
