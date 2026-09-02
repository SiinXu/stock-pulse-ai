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
 * Phase 2 domain collapse (#1300). The `--home-action-*` family is deleted;
 * Chat jump-to-bottom (`.chat-copy-btn`) inlines Layer 1 `--primary` alpha and
 * keeps the historical class name. Unused `--home-action-report-*` names are
 * removed with no replacement. This guard keeps the family from coming back
 * and pins the replacements plus the lowered page-scoped ceiling.
 */
const COLLAPSED_HOME_ACTION_TOKENS = [
  '--home-action-ai-bg',
  '--home-action-ai-border',
  '--home-action-ai-hover-bg',
  '--home-action-ai-text',
  '--home-action-report-bg',
  '--home-action-report-border',
  '--home-action-report-hover-bg',
  '--home-action-report-text',
];

const SRC_ROOT = resolve(__dirname, '..', 'src');

function readIndexCss(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'index.css'), 'utf8');
}

function readInventorySource(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'design', 'themeTokenInventory.ts'), 'utf8');
}

function readChatPage(): string {
  return readFileSync(resolve(__dirname, '..', 'src', 'pages', 'ChatPage.tsx'), 'utf8');
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

describe('home-action theme tokens', () => {
  it('keeps the light theme root block free of page-scoped home-action tokens', () => {
    const rootMatch = readIndexCss().match(/:root\s*\{([\s\S]*?)\n\}/);

    expect(rootMatch).not.toBeNull();
    const rootBlock = rootMatch?.[1] ?? '';

    expect(rootBlock).not.toContain('--home-action-');
    for (const token of COLLAPSED_HOME_ACTION_TOKENS) {
      expect(rootBlock, token).not.toContain(token);
    }
  });

  it('keeps the dark theme block free of page-scoped home-action tokens', () => {
    const darkMatch = readIndexCss().match(/\.dark\s*\{([\s\S]*?)\n\}/);

    expect(darkMatch).not.toBeNull();
    const darkBlock = darkMatch?.[1] ?? '';

    expect(darkBlock).not.toContain('--home-action-');
    for (const token of COLLAPSED_HOME_ACTION_TOKENS) {
      expect(darkBlock, token).not.toContain(token);
    }
  });

  it('removes the collapsed names from the defined inventory and does not raise the ceiling above 48', () => {
    expect(THEME_PAGE_SCOPED_TOKEN_CEILING).toBeLessThanOrEqual(48);

    const inventorySource = readInventorySource();
    for (const token of COLLAPSED_HOME_ACTION_TOKENS) {
      expect(THEME_DEFINED_TOKEN_NAMES, token).not.toContain(token);
      expect(inventorySource, token).not.toContain(`'${token}'`);
    }
  });

  it('keeps home in the page-scoped prefix ban after the action family reaches zero', () => {
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
    expect(readIndexCss()).not.toContain('--chat-jump-');
    expect(readIndexCss()).not.toContain('--chat-copy-');
  });

  it('inlines Layer 1 primary alphas on .chat-copy-btn including explicit dark hover 0.2', () => {
    const indexCss = readIndexCss();

    expect(indexCss).not.toContain('--home-action-');
    expect(indexCss).toContain('.chat-copy-btn {');
    expect(indexCss).toContain('color: hsl(var(--primary));');
    expect(indexCss).toContain('background: hsl(var(--primary) / 0.1);');
    expect(indexCss).toContain('border: 1px solid hsl(var(--primary) / 0.2);');
    expect(indexCss).toContain('.chat-copy-btn:hover {\n  background: hsl(var(--primary) / 0.18);\n}');
    expect(indexCss).toContain('.dark .chat-copy-btn:hover {\n  background: hsl(var(--primary) / 0.2);\n}');
    expect(indexCss).toContain('min-height: 2.75rem;');
    expect(indexCss).toContain('.chat-copy-btn:active {');
    expect(indexCss).toContain(
      '.chat-copy-btn:focus-visible,\n.session-item:focus-visible,\n.session-item-row .delete-btn:focus-visible {',
    );
    expect(indexCss).toContain('box-shadow: 0 0 0 3px hsl(var(--primary) / 0.16);');
  });

  it('keeps ChatPage on the historical chat-copy-btn class without page-scoped action tokens', () => {
    const source = readChatPage();

    expect(source).not.toContain('--home-action-');
    expect(source).toContain('chat-copy-btn');
    expect(source).toContain("aria-label={t('chat.latestMessages')}");
  });

  it('has zero production references to the collapsed home-action tokens', () => {
    const productionSources = walkProductionSources(SRC_ROOT);
    expect(productionSources.length).toBeGreaterThan(0);

    for (const filePath of productionSources) {
      const source = readFileSync(filePath, 'utf8');
      for (const token of COLLAPSED_HOME_ACTION_TOKENS) {
        expect(source, `${filePath} ${token}`).not.toContain(token);
      }
    }
  });
});
