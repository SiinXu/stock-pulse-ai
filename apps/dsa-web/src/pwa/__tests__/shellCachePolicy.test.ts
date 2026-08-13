// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  decideShellCacheStrategy,
  isNeverCachePath,
  isShellStaticPath,
} from '../shellCachePolicy';

describe('shellCachePolicy', () => {
  it('never caches API, health, market index, or OpenAPI surfaces', () => {
    for (const path of [
      '/api/v1/history',
      '/api/v1/analysis/run',
      '/api/health',
      '/health',
      '/stocks.index.json',
      '/docs',
      '/redoc',
      '/openapi.json',
      '/sw.js',
    ]) {
      expect(isNeverCachePath(path)).toBe(true);
      expect(decideShellCacheStrategy({
        method: 'GET',
        url: `https://example.test${path}`,
      })).toBe('network-only');
    }
  });

  it('allows shell static assets under cache-first', () => {
    for (const path of [
      '/assets/index-abc123.js',
      '/assets/vendor-react-xyz.css',
      '/icons/icon-192.png',
      '/manifest.webmanifest',
      '/vite.svg',
    ]) {
      expect(isShellStaticPath(path)).toBe(true);
      expect(decideShellCacheStrategy({
        method: 'GET',
        url: `https://example.test${path}`,
      })).toBe('cache-first-shell');
    }
  });

  it('uses network-first for document navigations and never stores non-GET', () => {
    expect(decideShellCacheStrategy({
      method: 'GET',
      url: 'https://example.test/research/analysis',
      mode: 'navigate',
    })).toBe('network-first-navigation');

    expect(decideShellCacheStrategy({
      method: 'POST',
      url: 'https://example.test/assets/index-abc.js',
    })).toBe('network-only');
  });

  it('defaults unknown same-origin paths to network-only (no store)', () => {
    expect(decideShellCacheStrategy({
      method: 'GET',
      url: 'https://example.test/unknown-route-data.json',
    })).toBe('network-only');
  });
});
