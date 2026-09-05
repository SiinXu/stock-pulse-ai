// @vitest-environment node

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { THEME_LEGACY_PRICE_ALIASES, THEME_PAGE_SCOPED_PREFIXES } from '../src/design/theme';
import {
  THEME_DEFINED_TOKEN_NAMES,
  THEME_PAGE_SCOPED_TOKEN_CEILING,
} from '../src/design/themeTokenInventory';

/**
 * Phase 2 leftover collapse (#1300). `--home-title-accent` is deleted;
 * `.home-title-accent` inlines Layer 1 `hsl(var(--foreground))` with no
 * `.dark` split (light and dark were already the same wrap). The class
 * rule stays earlier than equal-specificity `.label-uppercase`, so the
 * rendered eyebrow still computes `--text-secondary-text`. This guard
 * keeps the leftover from coming back, pins the replacements plus the
 * lowered page-scoped ceiling, and pins that source-order winner.
 */
const COLLAPSED_HOME_TITLE_ACCENT_TOKEN = '--home-title-accent';

const SRC_ROOT = resolve(__dirname, '..', 'src');
const CONTRACT_GUARD_PATH = resolve(
  __dirname,
  '..',
  'src',
  'components',
  '__tests__',
  'themeContractGuard.test.ts',
);

function readIndexCss(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'index.css'), 'utf8');
}

function readInventorySource(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'design', 'themeTokenInventory.ts'), 'utf8');
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

describe('home-title-accent theme tokens', () => {
  it('keeps the light theme root block free of leftover home-title-accent', () => {
    const rootMatch = readIndexCss().match(/:root\s*\{([\s\S]*?)\n\}/);

    expect(rootMatch).not.toBeNull();
    const rootBlock = rootMatch?.[1] ?? '';

    expect(rootBlock).not.toContain(COLLAPSED_HOME_TITLE_ACCENT_TOKEN);
  });

  it('keeps the dark theme block free of leftover home-title-accent', () => {
    const darkMatch = readIndexCss().match(/\.dark\s*\{([\s\S]*?)\n\}/);

    expect(darkMatch).not.toBeNull();
    const darkBlock = darkMatch?.[1] ?? '';

    expect(darkBlock).not.toContain(COLLAPSED_HOME_TITLE_ACCENT_TOKEN);
  });

  it('removes the collapsed name from the defined inventory and does not raise the ceiling above 43', () => {
    // Historical title-accent slice landed at 43. Later unused-wrapper
    // shrinks may lower the ceiling; growth above 43 remains forbidden.
    expect(THEME_PAGE_SCOPED_TOKEN_CEILING).toBeLessThanOrEqual(43);

    const inventorySource = readInventorySource();
    expect(THEME_DEFINED_TOKEN_NAMES).not.toContain(COLLAPSED_HOME_TITLE_ACCENT_TOKEN);
    expect(inventorySource).not.toContain(`'${COLLAPSED_HOME_TITLE_ACCENT_TOKEN}'`);
    expect(THEME_DEFINED_TOKEN_NAMES.length).toBeGreaterThan(158);
  });

  it('keeps home in the page-scoped prefix ban after title-accent reaches zero', () => {
    expect(THEME_PAGE_SCOPED_PREFIXES).toContain('home');
    expect(THEME_PAGE_SCOPED_PREFIXES).toEqual([
      'home',
      'settings',
      'login',
      'chat',
      'backtest',
      'portfolio',
    ]);
  });

  it('keeps the Layer-0 home-price aliases and does not invent a replacement page token', () => {
    expect(THEME_LEGACY_PRICE_ALIASES).toEqual(['--home-price-up', '--home-price-down']);
    expect(THEME_DEFINED_TOKEN_NAMES).toContain('--home-price-up');
    expect(THEME_DEFINED_TOKEN_NAMES).toContain('--home-price-down');
    expect(readIndexCss()).toMatch(/--home-price-up\s*:\s*var\(--price-red\)/);
    expect(readIndexCss()).toMatch(/--home-price-down\s*:\s*var\(--price-green\)/);
    expect(readIndexCss()).not.toContain('--title-accent-');
    expect(readIndexCss()).not.toContain('--panel-title-accent');
  });

  it('inlines Layer 1 foreground on .home-title-accent with no dark split', () => {
    const indexCss = readIndexCss();

    expect(indexCss).not.toContain(COLLAPSED_HOME_TITLE_ACCENT_TOKEN);
    expect(indexCss).toContain('.home-title-accent {\n  color: hsl(var(--foreground));\n}');
    expect(indexCss).not.toContain('.dark .home-title-accent');
    expect(indexCss).not.toContain('color: var(--foreground)');
  });

  it('keeps earlier .home-title-accent from winning over later equal-specificity .label-uppercase', () => {
    const indexCss = readIndexCss();
    const titleAccentSelector = '.home-title-accent {';
    const labelSelector = '.label-uppercase {';
    const titleAccentIndex = indexCss.indexOf(titleAccentSelector);
    const labelIndex = indexCss.indexOf(labelSelector);

    expect(titleAccentIndex).toBeGreaterThan(-1);
    expect(labelIndex).toBeGreaterThan(-1);
    expect(titleAccentIndex).toBeLessThan(labelIndex);
    expect(indexCss.split(titleAccentSelector)).toHaveLength(2);
    expect(indexCss.split(labelSelector)).toHaveLength(2);
    expect(indexCss).not.toMatch(/\.label-uppercase\.home-title-accent|\.home-title-accent\.label-uppercase/);
    expect(indexCss).not.toMatch(/\.home-title-accent[^{]*!important/);

    const titleAccentRule = indexCss.slice(
      titleAccentIndex,
      indexCss.indexOf('}', titleAccentIndex) + 1,
    );
    const labelRule = indexCss.slice(labelIndex, indexCss.indexOf('}', labelIndex) + 1);

    expect(titleAccentRule).toBe('.home-title-accent {\n  color: hsl(var(--foreground));\n}');
    expect(labelRule).toContain('color: var(--text-secondary-text);');
    expect(labelRule).not.toContain('--foreground');

    const header = readFileSync(
      resolve(SRC_ROOT, 'components/dashboard/DashboardPanelHeader.tsx'),
      'utf8',
    );
    expect(header).toContain("cn('label-uppercase', accentEyebrow && 'home-title-accent')");
  });

  it('keeps TOKEN_FORMAT_DEBT at 12 because title-accent was a conforming wrap', () => {
    const contractGuard = readFileSync(CONTRACT_GUARD_PATH, 'utf8');
    expect(contractGuard).toMatch(/const MAX_TOKEN_FORMAT_DEBT = 12;/);
    expect(contractGuard).not.toContain(COLLAPSED_HOME_TITLE_ACCENT_TOKEN);
  });

  it('keeps the historical home-title-accent class in production sources without the deleted token', () => {
    const productionSources = walkProductionSources(SRC_ROOT);
    expect(productionSources.length).toBeGreaterThan(0);

    const sourcesWithClass = productionSources.filter((filePath) => {
      const source = readFileSync(filePath, 'utf8');
      expect(source, `${filePath} ${COLLAPSED_HOME_TITLE_ACCENT_TOKEN}`).not.toContain(
        COLLAPSED_HOME_TITLE_ACCENT_TOKEN,
      );
      return /\bhome-title-accent\b/.test(source);
    });

    expect(sourcesWithClass.some((filePath) => filePath.endsWith('DashboardPanelHeader.tsx'))).toBe(true);
  });
});
