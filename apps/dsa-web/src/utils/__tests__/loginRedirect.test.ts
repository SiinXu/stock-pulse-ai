import { describe, expect, it } from 'vitest';
import { resolveLoginRedirect } from '../loginRedirect';

describe('resolveLoginRedirect', () => {
  it('returns same-origin absolute paths including query strings', () => {
    expect(resolveLoginRedirect('?redirect=%2Fportfolio')).toBe('/portfolio');
    expect(resolveLoginRedirect('?redirect=%2Fsettings%3Fsection%3Dai_models%26view%3Dconnections'))
      .toBe('/settings?section=ai_models&view=connections');
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
});
