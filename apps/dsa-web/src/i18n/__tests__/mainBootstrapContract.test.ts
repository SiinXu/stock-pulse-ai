// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const sourceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

describe('main bootstrap locale-neutral first paint', () => {
  it('creates the React root without awaiting extra-locale catalogs', () => {
    const source = fs.readFileSync(path.join(sourceRoot, 'main.tsx'), 'utf8');
    expect(source).toContain('beginInitialUiLanguage');
    expect(source).toContain('InitialUiLanguageGate');
    expect(source).toContain('createRoot');
    expect(source).not.toMatch(/await\s+prepareInitialUiLanguage\s*\(/);
    expect(source).not.toMatch(/const\s+initialUiLanguage\s*=\s*await/);
    const beginIndex = source.indexOf('beginInitialUiLanguage(');
    const createRootCallIndex = source.indexOf('createRoot(');
    expect(beginIndex).toBeGreaterThan(-1);
    expect(createRootCallIndex).toBeGreaterThan(beginIndex);
  });

  it('keeps a locale-neutral HTML placeholder before the module graph runs', () => {
    const source = fs.readFileSync(path.join(sourceRoot, '../index.html'), 'utf8');
    expect(source).toContain('data-locale-neutral-shell');
    expect(source).toContain("localStorage.getItem('dsa.uiLanguage')");
    expect(source).not.toContain('首页');
    expect(source).not.toContain('Settings');
  });
});
