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
 * Phase 2 domain collapse (#1300). The `--home-prose-*` family is deleted;
 * report markdown, shared `.prose` tables, and chat markdown inline Layer 1
 * `--foreground` / `--primary` alpha and keep historical class names. This
 * guard keeps the family from coming back and pins the replacements plus the
 * lowered page-scoped ceiling.
 */
const COLLAPSED_HOME_PROSE_TOKENS = [
  '--home-prose-blockquote-bg',
  '--home-prose-blockquote-border',
  '--home-prose-border',
  '--home-prose-border-strong',
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

describe('home-prose theme tokens', () => {
  it('keeps the light theme root block free of page-scoped home-prose tokens', () => {
    const rootMatch = readIndexCss().match(/:root\s*\{([\s\S]*?)\n\}/);

    expect(rootMatch).not.toBeNull();
    const rootBlock = rootMatch?.[1] ?? '';

    expect(rootBlock).not.toContain('--home-prose-');
    for (const token of COLLAPSED_HOME_PROSE_TOKENS) {
      expect(rootBlock, token).not.toContain(token);
    }
  });

  it('keeps the dark theme block free of page-scoped home-prose tokens', () => {
    const darkMatch = readIndexCss().match(/\.dark\s*\{([\s\S]*?)\n\}/);

    expect(darkMatch).not.toBeNull();
    const darkBlock = darkMatch?.[1] ?? '';

    expect(darkBlock).not.toContain('--home-prose-');
    for (const token of COLLAPSED_HOME_PROSE_TOKENS) {
      expect(darkBlock, token).not.toContain(token);
    }
  });

  it('removes the collapsed names from the defined inventory and does not raise the ceiling above 44', () => {
    expect(THEME_PAGE_SCOPED_TOKEN_CEILING).toBeLessThanOrEqual(44);

    const inventorySource = readInventorySource();
    for (const token of COLLAPSED_HOME_PROSE_TOKENS) {
      expect(THEME_DEFINED_TOKEN_NAMES, token).not.toContain(token);
      expect(inventorySource, token).not.toContain(`'${token}'`);
    }
  });

  it('keeps home in the page-scoped prefix ban after the prose family reaches zero', () => {
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
    expect(readIndexCss()).not.toContain('--report-prose-');
    expect(readIndexCss()).not.toContain('--markdown-prose-');
  });

  it('inlines prior light/dark Layer 1 alphas on report, shared prose, and chat markdown', () => {
    const indexCss = readIndexCss();

    expect(indexCss).not.toContain('--home-prose-');

    expect(indexCss).toContain('.report-markdown-prose :where(h1) {\n  border-bottom: 1px solid hsl(var(--foreground) / 0.1);\n');
    expect(indexCss).toContain('.dark .report-markdown-prose :where(h1) {\n  border-bottom: 1px solid hsl(var(--foreground) / 0.12);\n}');
    expect(indexCss).toContain('.report-markdown-prose :where(pre) {\n  border: 1px solid hsl(var(--foreground) / 0.1);\n');
    expect(indexCss).toContain('.dark .report-markdown-prose :where(pre) {\n  border: 1px solid hsl(var(--foreground) / 0.12);\n}');
    expect(indexCss).toContain('.report-markdown-prose :where(th, td) {\n  border: none;\n  border-bottom: 1px solid hsl(var(--foreground) / 0.1);\n');
    expect(indexCss).toContain('.dark .report-markdown-prose :where(th, td) {\n  border-bottom: 1px solid hsl(var(--foreground) / 0.12);\n}');
    expect(indexCss).toContain('.report-markdown-prose :where(th) {\n  background: transparent;\n  color: hsl(var(--muted-text));\n  font-weight: 600;\n  font-size: 0.6875rem;\n  letter-spacing: 0.04em;\n  text-transform: uppercase;\n  border-bottom: 1px solid hsl(var(--foreground) / 0.16);\n');
    expect(indexCss).toContain('.dark .report-markdown-prose :where(th) {\n  border-bottom: 1px solid hsl(var(--foreground) / 0.18);\n}');
    expect(indexCss).toContain('.report-markdown-prose :where(hr) {\n  border-color: hsl(var(--foreground) / 0.1);\n}');
    expect(indexCss).toContain('.dark .report-markdown-prose :where(hr) {\n  border-color: hsl(var(--foreground) / 0.12);\n}');
    expect(indexCss).toContain(
      '.report-markdown-prose :where(blockquote) {\n'
      + '  border-color: hsl(var(--primary) / 0.28);\n'
      + '  background: hsl(var(--primary) / 0.06);\n',
    );
    expect(indexCss).toContain(
      '.dark .report-markdown-prose :where(blockquote) {\n'
      + '  border-color: hsl(var(--primary) / 0.3);\n'
      + '  background: hsl(var(--primary) / 0.08);\n'
      + '}',
    );

    expect(indexCss).toContain('.prose :where(th, td) {\n  padding: 0.5rem 0.75rem;\n  border: none;\n  border-bottom: 1px solid hsl(var(--foreground) / 0.1);\n');
    expect(indexCss).toContain('.dark .prose :where(th, td) {\n  border-bottom: 1px solid hsl(var(--foreground) / 0.12);\n}');
    expect(indexCss).toContain('.prose :where(th) {\n  background: transparent;\n  color: hsl(var(--muted-text));\n  font-weight: 600;\n  font-size: 0.6875rem;\n  letter-spacing: 0.04em;\n  text-transform: uppercase;\n  border-bottom: 1px solid hsl(var(--foreground) / 0.16);\n');
    expect(indexCss).toContain('.dark .prose :where(th) {\n  border-bottom: 1px solid hsl(var(--foreground) / 0.18);\n}');

    expect(indexCss).toContain('.chat-prose pre {\n  max-width: 100%;\n  overflow-x: auto;\n  background: hsl(var(--background) / 0.3);\n  border: 1px solid hsl(var(--foreground) / 0.1);\n');
    expect(indexCss).toContain('.dark .chat-prose pre {\n  border: 1px solid hsl(var(--foreground) / 0.12);\n}');
    expect(indexCss).toContain('.chat-prose th,\n.chat-prose td {\n  padding: 0.25rem 0.375rem;\n  border: 1px solid hsl(var(--foreground) / 0.16);\n}');
    expect(indexCss).toContain('.dark .chat-prose th,\n.dark .chat-prose td {\n  border: 1px solid hsl(var(--foreground) / 0.18);\n}');
    expect(indexCss).toContain('.chat-prose hr {\n  border-color: hsl(var(--foreground) / 0.1);\n  margin: 0.75rem 0;\n}');
    expect(indexCss).toContain('.dark .chat-prose hr {\n  border-color: hsl(var(--foreground) / 0.12);\n}');
    expect(indexCss).toContain(
      '.chat-prose blockquote {\n'
      + '  border-color: hsl(var(--secondary-text) / 0.3);\n'
      + '  background: hsl(var(--secondary-text) / 0.08);\n',
    );
  });

  it('does not treat the current slate pack as a foreground override for leftover prose borders', () => {
    const indexCss = readIndexCss();
    const slateMatch = indexCss.match(/\[data-theme-pack="slate"\]\s*\{([\s\S]*?)\n\}/);
    const darkSlateMatch = indexCss.match(/\.dark\[data-theme-pack="slate"\]\s*\{([\s\S]*?)\n\}/);

    expect(slateMatch).not.toBeNull();
    expect(darkSlateMatch).not.toBeNull();

    const slateBlock = slateMatch?.[1] ?? '';
    const darkSlateBlock = darkSlateMatch?.[1] ?? '';
    const foregroundDeclaration = /(?:^|\n)\s*--foreground\s*:/;
    const primaryDeclaration = /(?:^|\n)\s*--primary\s*:/;
    const borderDeclaration = /(?:^|\n)\s*--border\s*:/;

    expect(slateBlock).toMatch(borderDeclaration);
    expect(slateBlock).toMatch(primaryDeclaration);
    expect(slateBlock).not.toMatch(foregroundDeclaration);
    expect(darkSlateBlock).toMatch(borderDeclaration);
    expect(darkSlateBlock).toMatch(primaryDeclaration);
    expect(darkSlateBlock).not.toMatch(foregroundDeclaration);
  });

  it('has zero production references to the collapsed home-prose tokens', () => {
    const productionSources = walkProductionSources(SRC_ROOT);
    expect(productionSources.length).toBeGreaterThan(0);

    for (const filePath of productionSources) {
      const source = readFileSync(filePath, 'utf8');
      for (const token of COLLAPSED_HOME_PROSE_TOKENS) {
        expect(source, `${filePath} ${token}`).not.toContain(token);
      }
    }
  });
});
