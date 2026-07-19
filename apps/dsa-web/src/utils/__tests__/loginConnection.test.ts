import { describe, expect, it } from 'vitest';
import { getLoginConnectionStatus } from '../loginConnection';

describe('getLoginConnectionStatus', () => {
  it.each([
    ['https:', 'stocks.example.com'],
    ['https:', 'localhost'],
  ])('classifies %s//%s as HTTPS', (protocol, hostname) => {
    expect(getLoginConnectionStatus({ protocol, hostname })).toBe('https');
  });

  it.each([
    'localhost',
    'LOCALHOST.',
    'dev.localhost',
    '127.0.0.1',
    '127.42.0.7',
    '::1',
    '[::1]',
  ])('classifies HTTP loopback host %s as local HTTP', (hostname) => {
    expect(getLoginConnectionStatus({ protocol: 'http:', hostname })).toBe('local-http');
  });

  it.each([
    'stocks.example.com',
    'localhost.example.com',
    '192.168.1.20',
    '0.0.0.0',
  ])('classifies HTTP host %s as insecure HTTP', (hostname) => {
    expect(getLoginConnectionStatus({ protocol: 'http:', hostname })).toBe('insecure-http');
  });

  it('does not describe non-HTTP schemes as HTTPS or local HTTP', () => {
    expect(getLoginConnectionStatus({ protocol: 'file:', hostname: '' })).toBe('insecure-http');
  });
});
