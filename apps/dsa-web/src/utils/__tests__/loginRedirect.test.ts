import { describe, expect, it } from 'vitest';
import { resolveLoginRedirect } from '../loginRedirect';

describe('resolveLoginRedirect', () => {
  it('returns same-origin absolute paths including query strings', () => {
    expect(resolveLoginRedirect('?redirect=%2Fportfolio')).toBe('/portfolio');
    expect(resolveLoginRedirect('?redirect=%2Fsettings%3Fsection%3Dai_models%26view%3Dconnections'))
      .toBe('/settings?section=ai_models&view=connections');
    expect(resolveLoginRedirect('?redirect=%2Fportfolio%3Ftab%3Dwatchlist%23saved')).toBe(
      '/portfolio?tab=watchlist#saved',
    );
  });

  it('accepts URLSearchParams input', () => {
    expect(resolveLoginRedirect(new URLSearchParams('redirect=%2Fchat'))).toBe('/chat');
  });

  it('falls back to home when the redirect is missing or empty', () => {
    expect(resolveLoginRedirect('')).toBe('/');
    expect(resolveLoginRedirect('?redirect=')).toBe('/');
    expect(resolveLoginRedirect('?other=1')).toBe('/');
  });

  it('rejects external and protocol-relative destinations', () => {
    expect(resolveLoginRedirect('?redirect=https%3A%2F%2Fevil.example.com')).toBe('/');
    expect(resolveLoginRedirect('?redirect=%2F%2Fevil.example.com')).toBe('/');
    expect(resolveLoginRedirect('?redirect=%2F%5Cevil.example.com')).toBe('/');
    expect(resolveLoginRedirect('?redirect=javascript%3Aalert(1)')).toBe('/');
  });

  it.each([
    ['tab', '?redirect=%2F%09%2Fevil.example.com'],
    ['line feed', '?redirect=%2F%0A%2Fevil.example.com'],
    ['carriage return', '?redirect=%2F%0D%2Fevil.example.com'],
    ['space', '?redirect=%2F%20%2Fevil.example.com'],
    ['delete character', '?redirect=%2F%7F%2Fevil.example.com'],
    ['control character before a backslash', '?redirect=%2F%00%5Cevil.example.com'],
    ['backslash after a path segment', '?redirect=%2Fsafe%5C%5Cevil.example.com'],
  ])('rejects encoded %s normalization tricks', (_label, search) => {
    expect(resolveLoginRedirect(search)).toBe('/');
  });

  it.each(['/\t/evil.example.com', '/\n/evil.example.com', '/\r/evil.example.com', '/\0\\evil.example.com'])(
    'rejects literal control, whitespace, and backslash variants: %j',
    (redirect) => {
      const params = new URLSearchParams();
      params.set('redirect', redirect);

      expect(resolveLoginRedirect(params)).toBe('/');
    },
  );
});
