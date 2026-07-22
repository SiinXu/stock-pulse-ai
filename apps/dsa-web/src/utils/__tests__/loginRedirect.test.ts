// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { buildSettingsHref } from '../../routing/routes';
import { resolveLoginRedirect } from '../loginRedirect';

describe('resolveLoginRedirect', () => {
  it('returns same-origin absolute paths including query strings', () => {
    expect(resolveLoginRedirect('?redirect=%2Fportfolio')).toBe('/portfolio');
    const settingsHref = buildSettingsHref({ section: 'ai_models', view: 'connections' });
    expect(resolveLoginRedirect(`?${new URLSearchParams({ redirect: settingsHref })}`))
      .toBe(settingsHref);
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

  it('rejects paths that normalize to a protocol-relative destination', () => {
    expect(resolveLoginRedirect('?redirect=/%2e%2e//evil.example')).toBe('/');
    expect(resolveLoginRedirect('?redirect=/%252e%252e//evil.example')).toBe('/');
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

  it.each([
    ['non-breaking space', '\u00a0'],
    ['line separator', '\u2028'],
    ['em space', '\u2003'],
    ['ideographic space', '\u3000'],
  ])('rejects Unicode White_Space characters such as %s', (_label, whitespace) => {
    const params = new URLSearchParams();
    params.set('redirect', `/safe${whitespace}path`);

    expect(resolveLoginRedirect(params)).toBe('/');
  });

  it('preserves ordinary Unicode paths with query strings and hashes', () => {
    const params = new URLSearchParams();
    params.set('redirect', '/持仓/腾讯?视图=详情#摘要');

    expect(resolveLoginRedirect(params)).toBe(
      '/%E6%8C%81%E4%BB%93/%E8%85%BE%E8%AE%AF?%E8%A7%86%E5%9B%BE=%E8%AF%A6%E6%83%85#%E6%91%98%E8%A6%81',
    );
  });
});
