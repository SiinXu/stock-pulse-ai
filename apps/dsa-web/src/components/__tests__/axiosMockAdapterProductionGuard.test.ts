// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { readFileSync } from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  isProductionSourcePath,
  productionTypeScriptSources,
} from './productionSourceInventory';

const TEST_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(TEST_DIRECTORY, '../../..');
const PACKAGE_JSON_PATH = path.join(WEB_ROOT, 'package.json');
const PACKAGE_LOCK_PATH = path.join(WEB_ROOT, 'package-lock.json');
const PLAYGROUND_RENDER_PATH = path.resolve(
  TEST_DIRECTORY,
  '../../playground/PlaygroundRenderPage.tsx',
);
const MOCK_ADAPTER = 'axios-mock-adapter';

type PackageManifest = {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
};

type PackageLock = {
  packages?: Record<string, {
    dependencies?: Record<string, string>;
    devDependencies?: Record<string, string>;
    dev?: boolean;
  }>;
};

describe('axios-mock-adapter production boundary', () => {
  it('keeps axios-mock-adapter in devDependencies only', () => {
    const manifest = JSON.parse(readFileSync(PACKAGE_JSON_PATH, 'utf8')) as PackageManifest;
    const lockfile = JSON.parse(readFileSync(PACKAGE_LOCK_PATH, 'utf8')) as PackageLock;
    const root = lockfile.packages?.[''] ?? {};
    const installed = lockfile.packages?.['node_modules/axios-mock-adapter'] ?? {};

    expect(manifest.dependencies?.[MOCK_ADAPTER]).toBeUndefined();
    expect(manifest.devDependencies?.[MOCK_ADAPTER]).toMatch(/^\^?2\./);
    expect(root.dependencies?.[MOCK_ADAPTER]).toBeUndefined();
    expect(root.devDependencies?.[MOCK_ADAPTER]).toBe(manifest.devDependencies?.[MOCK_ADAPTER]);
    expect(installed.dev).toBe(true);
  });

  it('does not let production sources outside playground import the mock adapter', () => {
    const leaks = Object.entries(productionTypeScriptSources).flatMap(([filename, sourceText]) => {
      if (!isProductionSourcePath(filename)) return [];
      if (filename.includes('/playground/')) return [];
      if (!sourceText.includes(MOCK_ADAPTER)) return [];
      return [filename];
    });

    expect(leaks).toEqual([]);
  });

  it('loads the playground mock adapter only behind the compile-time DEV flag', () => {
    const renderSource = readFileSync(PLAYGROUND_RENDER_PATH, 'utf8');

    expect(renderSource).not.toMatch(
      /^import\s+\{[^}]*installPlaygroundApiMock[^}]*\}\s+from\s+'\.\/mockApi'/m,
    );
    expect(renderSource).toMatch(
      /if\s*\(\s*import\.meta\.env\.DEV\s*\)[\s\S]*import\('\.\/mockApi'\)/,
    );
  });
});
