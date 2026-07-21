import { describe, expect, it } from 'vitest';
import { isPlaygroundFrameMessage } from '../types';

const validLog = {
  channel: 'stockpulse-playground',
  version: 1,
  type: 'api-log',
  event: {
    id: 'request-1',
    method: 'GET',
    path: '/api/v1/history',
    status: 200,
    durationMs: 42,
  },
};

describe('playground iframe messages', () => {
  it('accepts only the versioned ready and safe request-log contracts', () => {
    expect(isPlaygroundFrameMessage({ channel: 'stockpulse-playground', version: 1, type: 'ready' })).toBe(true);
    expect(isPlaygroundFrameMessage(validLog)).toBe(true);
  });

  it.each([
    { ...validLog, token: 'secret' },
    { ...validLog, event: { ...validLog.event, payload: { token: 'secret' } } },
    { ...validLog, event: { ...validLog.event, path: '/api/v1/history?token=secret' } },
    { ...validLog, event: { ...validLog.event, method: 'TRACE' } },
    { ...validLog, event: { ...validLog.event, status: 700 } },
    { ...validLog, event: { ...validLog.event, durationMs: -1 } },
    { ...validLog, version: 2 },
  ])('rejects malformed or payload-bearing messages', (message) => {
    expect(isPlaygroundFrameMessage(message)).toBe(false);
  });
});
