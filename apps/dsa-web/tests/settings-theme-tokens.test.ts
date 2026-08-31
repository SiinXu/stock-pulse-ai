// @vitest-environment node

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { THEME_PAGE_SCOPED_PREFIXES } from '../src/design/theme';
import {
  THEME_DEFINED_TOKEN_NAMES,
  THEME_PAGE_SCOPED_TOKEN_CEILING,
} from '../src/design/themeTokenInventory';

/**
 * Phase 2 domain collapse (#1300). The `--settings-*` family is deleted;
 * Settings, onboarding, and helpers now read Layer 1 semantics plus use-site
 * alpha so theme packs such as slate recolour the page. This guard keeps the
 * prefix from coming back and pins the replacements plus the lowered
 * page-scoped ceiling.
 */
const COLLAPSED_SETTINGS_TOKENS = [
  '--settings-accent-shadow',
  '--settings-border',
  '--settings-border-overlay',
  '--settings-border-soft',
  '--settings-border-strong',
  '--settings-input-rest-border',
  '--settings-primary-border',
  '--settings-secondary-bg',
  '--settings-secondary-bg-hover',
  '--settings-secondary-border',
  '--settings-secondary-border-hover',
  '--settings-skeleton-soft',
  '--settings-skeleton-strong',
  '--settings-surface',
  '--settings-surface-hover',
  '--settings-surface-overlay',
  '--settings-surface-overlay-muted',
  '--settings-surface-overlay-soft',
  '--settings-surface-panel',
  '--settings-surface-strong',
];

const DELETED_HELPER_CLASSES = [
  '.settings-surface-strong',
  '.settings-surface-panel',
  '.settings-surface-overlay-soft',
  '.settings-surface-overlay-muted',
  '.settings-border {',
  '.settings-border-strong',
  '.settings-skeleton-strong',
  '.settings-skeleton-soft',
];

const SRC_ROOT = resolve(__dirname, '..', 'src');

function readIndexCss(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'index.css'), 'utf8');
}

function readInventorySource(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'design', 'themeTokenInventory.ts'), 'utf8');
}

function readSettingsPage(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'pages', 'SettingsPage.tsx'), 'utf8');
}

function isProductionSourcePath(filename: string): boolean {
  return !filename.includes('/__tests__/')
    && !filename.includes('/__fixtures__/')
    && !filename.includes('/fixtures/')
    && !filename.includes('/dev/')
    && !filename.includes('/generated/')
    && !filename.includes('/stories/')
    && !/\.(?:test|spec)\.[jt]sx?$/.test(filename)
    && !/\.(?:story|stories|generated)\.[jt]sx?$/.test(filename)
    && !/\.(?:test|spec|story|stories|generated)\.css$/.test(filename);
}

function walkProductionSources(dir: string): string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    const fullPath = join(dir, entry);
    const stats = statSync(fullPath);
    if (stats.isDirectory()) {
      files.push(...walkProductionSources(fullPath));
      continue;
    }
    if (!/\.(?:css|ts|tsx)$/.test(fullPath)) continue;
    if (!isProductionSourcePath(fullPath)) continue;
    files.push(fullPath);
  }
  return files;
}

describe('settings theme tokens', () => {
  it('keeps the light theme root block free of page-scoped settings tokens', () => {
    const rootMatch = readIndexCss().match(/:root\s*\{([\s\S]*?)\n\}/);

    expect(rootMatch).not.toBeNull();
    const rootBlock = rootMatch?.[1] ?? '';

    for (const token of COLLAPSED_SETTINGS_TOKENS) {
      expect(rootBlock, token).not.toContain(token);
    }
  });

  it('keeps the dark theme block free of page-scoped settings tokens', () => {
    const darkMatch = readIndexCss().match(/\.dark\s*\{([\s\S]*?)\n\}/);

    expect(darkMatch).not.toBeNull();
    const darkBlock = darkMatch?.[1] ?? '';

    for (const token of COLLAPSED_SETTINGS_TOKENS) {
      expect(darkBlock, token).not.toContain(token);
    }
  });

  it('removes the collapsed names from the defined inventory and does not raise the ceiling above 56', () => {
    expect(THEME_PAGE_SCOPED_TOKEN_CEILING).toBeLessThanOrEqual(56);

    const inventorySource = readInventorySource();
    for (const token of COLLAPSED_SETTINGS_TOKENS) {
      expect(THEME_DEFINED_TOKEN_NAMES, token).not.toContain(token);
      expect(inventorySource, token).not.toContain(`'${token}'`);
    }
  });

  it('keeps settings in the page-scoped prefix ban after the family reaches zero', () => {
    expect(THEME_PAGE_SCOPED_PREFIXES).toContain('settings');
    expect(THEME_PAGE_SCOPED_PREFIXES).toEqual([
      'home',
      'settings',
      'login',
      'chat',
      'backtest',
      'portfolio',
    ]);
  });

  it('deletes the page-token helper classes and inlines the Settings input rest border', () => {
    const indexCss = readIndexCss();

    expect(indexCss).not.toContain('--settings-');
    for (const className of DELETED_HELPER_CLASSES) {
      expect(indexCss, className).not.toContain(className);
    }
    expect(indexCss).toContain('.settings-accent-text');
    expect(indexCss).toContain('.settings-drag-active');
    expect(indexCss).toContain('.settings-page .input-surface:not(:hover):not(:focus):not(:disabled)');
    expect(indexCss).toContain('border-color: hsl(var(--border) / 0.72);');
    expect(indexCss).toContain('.dark .settings-page .input-surface:not(:hover):not(:focus):not(:disabled)');
    expect(indexCss).toContain('border-color: hsl(var(--border) / 0.58);');
  });

  it('paints Settings from Layer 1 semantics only', () => {
    const source = readSettingsPage();

    expect(source).not.toContain('--settings-');
    expect(source).toContain('border border-border');
    expect(source).toContain('bg-card');
  });

  it('has zero production references to the collapsed settings tokens', () => {
    const productionSources = walkProductionSources(SRC_ROOT);
    expect(productionSources.length).toBeGreaterThan(0);

    for (const filePath of productionSources) {
      const source = readFileSync(filePath, 'utf8');
      for (const token of COLLAPSED_SETTINGS_TOKENS) {
        expect(source, `${filePath} ${token}`).not.toContain(token);
      }
    }

    const e2eFixture = readFileSync(
      resolve(__dirname, '..', 'e2e', 'data-table-fixture.tsx'),
      'utf8',
    );
    expect(e2eFixture).not.toContain('--settings-');
  });
});
