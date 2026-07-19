import { describe, expect, it } from 'vitest';
import { getLoginConnectionStatus } from '../loginConnection';

describe('getLoginConnectionStatus', () => {
  it('reports HTTPS connections as secure', () => {
    expect(getLoginConnectionStatus('https:', 'stocks.example.com')).toBe('secure');
    expect(getLoginConnectionStatus('https:', 'localhost')).toBe('secure');
  });

  it.each(['localhost', '127.0.0.1', '::1', '[::1]'])(
    'reports HTTP loopback host %s as a local development connection',
    (hostname) => {
      expect(getLoginConnectionStatus('http:', hostname)).toBe('local');
    },
  );

  it('reports non-loopback HTTP connections as insecure', () => {
    expect(getLoginConnectionStatus('http:', 'stocks.example.com')).toBe('insecure');
  });
});
