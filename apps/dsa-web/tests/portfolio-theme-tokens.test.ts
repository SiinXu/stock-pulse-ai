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
 * Phase 2 domain collapse (#1300). The `--portfolio-*` family is deleted; the
 * one light `.portfolio-page .btn-secondary` outline inlines Layer 1
 * `--foreground` alpha. Packs that override `--foreground` could recolour that
 * leftover border; the current slate pack does not. This guard keeps the prefix
 * from coming back and pins the replacement plus the lowered page-scoped
 * ceiling.
 */
const COLLAPSED_PORTFOLIO_TOKENS = [
  '--portfolio-control-border',
];

const SRC_ROOT = resolve(__dirname, '..', 'src');

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

describe('portfolio theme tokens', () => {
  it('keeps the light theme root block free of page-scoped portfolio tokens', () => {
    const rootMatch = readIndexCss().match(/:root\s*\{([\s\S]*?)\n\}/);

    expect(rootMatch).not.toBeNull();
    const rootBlock = rootMatch?.[1] ?? '';

    for (const token of COLLAPSED_PORTFOLIO_TOKENS) {
      expect(rootBlock, token).not.toContain(token);
    }
  });

  it('keeps the dark theme block free of page-scoped portfolio tokens', () => {
    const darkMatch = readIndexCss().match(/\.dark\s*\{([\s\S]*?)\n\}/);

    expect(darkMatch).not.toBeNull();
    const darkBlock = darkMatch?.[1] ?? '';

    for (const token of COLLAPSED_PORTFOLIO_TOKENS) {
      expect(darkBlock, token).not.toContain(token);
    }
  });

  it('removes the collapsed names from the defined inventory and lowers the ceiling to 93', () => {
    expect(THEME_PAGE_SCOPED_TOKEN_CEILING).toBe(93);

    const inventorySource = readInventorySource();
    for (const token of COLLAPSED_PORTFOLIO_TOKENS) {
      expect(THEME_DEFINED_TOKEN_NAMES, token).not.toContain(token);
      expect(inventorySource, token).not.toContain(`'${token}'`);
    }
  });

  it('keeps portfolio in the page-scoped prefix ban after the family reaches zero', () => {
    expect(THEME_PAGE_SCOPED_PREFIXES).toContain('portfolio');
    expect(THEME_PAGE_SCOPED_PREFIXES).toEqual([
      'home',
      'settings',
      'login',
      'chat',
      'backtest',
      'portfolio',
    ]);
  });

  it('inlines the light portfolio secondary-button outline on Layer 1 foreground alpha', () => {
    const indexCss = readIndexCss();

    expect(indexCss).not.toContain('--portfolio-');
    expect(indexCss).not.toContain('.dark .portfolio-page .btn-secondary');
    expect(indexCss).toContain(
      ':root:not(.dark) .portfolio-page .btn-secondary:not(:disabled) {\n'
      + '  border-color: hsl(var(--foreground) / 0.2);\n'
      + '}',
    );
  });

  it('does not treat the current slate pack as a foreground override for leftover borders', () => {
    const indexCss = readIndexCss();
    const slateMatch = indexCss.match(/\[data-theme-pack="slate"\]\s*\{([\s\S]*?)\n\}/);
    const darkSlateMatch = indexCss.match(/\.dark\[data-theme-pack="slate"\]\s*\{([\s\S]*?)\n\}/);

    expect(slateMatch).not.toBeNull();
    expect(darkSlateMatch).not.toBeNull();

    const slateBlock = slateMatch?.[1] ?? '';
    const darkSlateBlock = darkSlateMatch?.[1] ?? '';
    const foregroundDeclaration = /(?:^|\n)\s*--foreground\s*:/;
    const borderDeclaration = /(?:^|\n)\s*--border\s*:/;

    expect(slateBlock).toMatch(borderDeclaration);
    expect(slateBlock).not.toMatch(foregroundDeclaration);
    expect(darkSlateBlock).toMatch(borderDeclaration);
    expect(darkSlateBlock).not.toMatch(foregroundDeclaration);
  });

  it('has zero production references to the collapsed portfolio tokens', () => {
    const productionSources = walkProductionSources(SRC_ROOT);
    expect(productionSources.length).toBeGreaterThan(0);

    for (const filePath of productionSources) {
      const source = readFileSync(filePath, 'utf8');
      for (const token of COLLAPSED_PORTFOLIO_TOKENS) {
        expect(source, filePath).not.toContain(token);
      }
    }
  });
});
