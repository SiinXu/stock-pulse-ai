// @vitest-environment node

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  THEME_DEFINED_TOKEN_NAMES,
  THEME_PAGE_SCOPED_TOKEN_CEILING,
} from '../src/design/themeTokenInventory';

/**
 * Phase 2 domain collapse (#1300). The `--backtest-*` family is deleted; Backtest
 * Workspace recipes inline Layer 1 `--foreground` alpha. Packs that override
 * `--foreground` could recolour those leftover borders; the current slate pack
 * does not. This guard keeps the prefix from coming back and pins the
 * replacements plus the lowered page-scoped ceiling.
 */
const COLLAPSED_BACKTEST_TOKENS = [
  '--backtest-border-dim',
  '--backtest-border-light',
  '--backtest-border-subtle',
  '--backtest-spinner-head',
  '--backtest-spinner-track',
  '--backtest-table-bg',
];

const BACKTEST_WORKSPACE_CLASS_NAMES = [
  '.backtest-metric-row',
  '.backtest-summary',
  '.backtest-status-chip',
];

function readIndexCss(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'index.css'), 'utf8');
}

function readInventorySource(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'design', 'themeTokenInventory.ts'), 'utf8');
}

function readBacktestPage(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'pages', 'BacktestPage.tsx'), 'utf8');
}

describe('backtest theme tokens', () => {
  it('keeps the light theme root block free of page-scoped backtest tokens', () => {
    const rootMatch = readIndexCss().match(/:root\s*\{([\s\S]*?)\n\}/);

    expect(rootMatch).not.toBeNull();
    const rootBlock = rootMatch?.[1] ?? '';

    for (const token of COLLAPSED_BACKTEST_TOKENS) {
      expect(rootBlock, token).not.toContain(token);
    }
  });

  it('keeps the dark theme block free of page-scoped backtest tokens', () => {
    const darkMatch = readIndexCss().match(/\.dark\s*\{([\s\S]*?)\n\}/);

    expect(darkMatch).not.toBeNull();
    const darkBlock = darkMatch?.[1] ?? '';

    for (const token of COLLAPSED_BACKTEST_TOKENS) {
      expect(darkBlock, token).not.toContain(token);
    }
  });

  it('removes the collapsed names from the defined inventory and does not raise the ceiling above 94', () => {
    expect(THEME_PAGE_SCOPED_TOKEN_CEILING).toBeLessThanOrEqual(94);

    const inventorySource = readInventorySource();
    for (const token of COLLAPSED_BACKTEST_TOKENS) {
      expect(THEME_DEFINED_TOKEN_NAMES, token).not.toContain(token);
      expect(inventorySource, token).not.toContain(`'${token}'`);
    }
  });

  it('keeps Backtest Workspace class names and inlines Layer 1 foreground-alpha borders', () => {
    const indexCss = readIndexCss();

    for (const className of BACKTEST_WORKSPACE_CLASS_NAMES) {
      expect(indexCss, className).toContain(className);
    }
    expect(indexCss).not.toContain('--backtest-');
    expect(indexCss).toContain('border-bottom: 1px solid hsl(var(--foreground) / 0.05)');
    expect(indexCss).toContain('.dark .backtest-metric-row');
    expect(indexCss).toContain('border: 1px solid hsl(var(--foreground) / 0.05)');
    expect(indexCss).toContain('.dark .backtest-summary');
    expect(indexCss).toContain('border: 1px solid hsl(var(--foreground) / 0.06)');
    expect(indexCss).toContain('border-top: 1px solid hsl(var(--border) / 0.40)');
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

  it('does not introduce page-scoped backtest tokens on BacktestPage', () => {
    expect(readBacktestPage()).not.toContain('--backtest-');
  });
});
