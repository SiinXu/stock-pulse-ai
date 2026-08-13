// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Guard against policy drift: the generated SW template in vite-plugin-shell-pwa.ts
 * must keep the same never-cache / shell-static path rules as shellCachePolicy.ts.
 */
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { readFileSync } from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  decideShellCacheStrategy,
  isNeverCachePath,
  isShellStaticPath,
} from '../shellCachePolicy';

const pluginPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../vite-plugin-shell-pwa.ts',
);

const pluginSource = readFileSync(pluginPath, 'utf8');

describe('shell SW template mirrors shellCachePolicy', () => {
  it('keeps never-cache path checks in the generated worker template', () => {
    for (const fragment of [
      "path === '/api'",
      "path.startsWith('/api/')",
      "path === '/health'",
      'stocks.index.json',
      "path === '/docs'",
      "path === '/redoc'",
      "path === '/openapi.json'",
      "path === '/sw.js'",
    ]) {
      expect(pluginSource).toContain(fragment);
    }
  });

  it('keeps shell-static path checks in the generated worker template', () => {
    for (const fragment of [
      "path === '/manifest.webmanifest'",
      "path.startsWith('/icons/')",
      "path.startsWith('/assets/')",
    ]) {
      expect(pluginSource).toContain(fragment);
    }
  });

  it('excludes market index from the install precache seed list', () => {
    // Seed list is built in writeBundle; never-precache basenames must stay present.
    expect(pluginSource).toContain("'stocks.index.json'");
    expect(pluginSource).toContain("urls.delete('/stocks.index.json')");
  });

  it('seeds install precache from the entry static import graph, not only index-*', () => {
    expect(pluginSource).toContain('collectSyncShellAssetPaths');
    expect(pluginSource).toContain('item.isEntry');
    expect(pluginSource).toContain('item.imports');
    expect(pluginSource).not.toContain('/^assets\\/index-[^/]+\\.(js|css)$/');
  });

  it('unit policy still denies API and market index (behavioral lock)', () => {
    expect(isNeverCachePath('/api/v1/history')).toBe(true);
    expect(isNeverCachePath('/stocks.index.json')).toBe(true);
    expect(isShellStaticPath('/assets/index-abc.js')).toBe(true);
    expect(decideShellCacheStrategy({
      method: 'GET',
      url: 'https://example.test/api/v1/focus/today',
    })).toBe('network-only');
  });
});
