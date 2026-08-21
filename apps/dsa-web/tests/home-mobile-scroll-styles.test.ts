// @vitest-environment node

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { PLAYGROUND_CATALOG } from '../src/playground/catalog';

const WEB_ROOT = resolve(__dirname, '..');
const INDEX_CSS_PATH = resolve(WEB_ROOT, 'src', 'index.css');
const STOCK_BAR_PATH = resolve(WEB_ROOT, 'src', 'components', 'history', 'StockBar.tsx');
const WORKSPACE_PATH = resolve(WEB_ROOT, 'src', 'components', 'watchlist', 'HomeStockWorkspace.tsx');
const SCROLL_AREA_PATH = resolve(WEB_ROOT, 'src', 'components', 'common', 'ScrollArea.tsx');
const STOCK_BAR_SCENARIO_PATH = resolve(
  WEB_ROOT,
  'src',
  'playground',
  'scenarios',
  'alertHistoryScenarios.tsx',
);
const WORKSPACE_SCENARIO_PATH = resolve(
  WEB_ROOT,
  'src',
  'playground',
  'scenarios',
  'watchlistWorkspaceScenarios.tsx',
);

const SHELL_SELECTOR = '(?:\\.home-stock-scroll-shell(?:\\s*,\\s*\\[data-surface-level\\]\\.home-stock-scroll-shell)?)';

function stripCssComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '');
}

function findMatchingBrace(source: string, openIndex: number): number {
  let depth = 0;
  for (let index = openIndex; index < source.length; index += 1) {
    const character = source[index];
    if (character === '{') depth += 1;
    else if (character === '}') {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  return -1;
}

function splitLayeredAndUnlayered(css: string): { layered: string; unlayered: string } {
  const source = stripCssComments(css);
  let cursor = 0;
  let layered = '';
  let unlayered = '';

  while (cursor < source.length) {
    const remaining = source.slice(cursor);
    const layerMatch = remaining.match(/^@layer(?:\s+[\w-]+(?:\s*,\s*[\w-]+)*)?\s*\{/);
    if (layerMatch) {
      const openIndex = cursor + layerMatch[0].length - 1;
      const closeIndex = findMatchingBrace(source, openIndex);
      if (closeIndex < 0) {
        throw new Error('Unclosed @layer block in src/index.css');
      }
      layered += source.slice(openIndex + 1, closeIndex);
      cursor = closeIndex + 1;
      continue;
    }
    unlayered += source[cursor];
    cursor += 1;
  }

  return { layered, unlayered };
}

function extractRuleBody(css: string, selectorPattern: RegExp): string | null {
  const match = selectorPattern.exec(css);
  if (!match) return null;
  const openIndex = css.indexOf('{', match.index);
  if (openIndex < 0 || openIndex > match.index + match[0].length + 32) return null;
  const closeIndex = findMatchingBrace(css, openIndex);
  if (closeIndex < 0) return null;
  return css.slice(openIndex + 1, closeIndex);
}

function extractMediaBodies(css: string, query: string): string[] {
  const bodies: string[] = [];
  const pattern = new RegExp(`@media\\s*\\(\\s*min-width:\\s*${query}\\s*\\)\\s*\\{`, 'g');
  let match = pattern.exec(css);
  while (match) {
    const openIndex = match.index + match[0].length - 1;
    const closeIndex = findMatchingBrace(css, openIndex);
    if (closeIndex >= 0) {
      bodies.push(css.slice(openIndex + 1, closeIndex));
    }
    match = pattern.exec(css);
  }
  return bodies;
}

function declarations(body: string): Record<string, string> {
  return Object.fromEntries(
    body
      .split(';')
      .map((entry) => entry.trim())
      .filter(Boolean)
      .map((entry) => {
        const separator = entry.indexOf(':');
        return [entry.slice(0, separator).trim(), entry.slice(separator + 1).trim()];
      }),
  );
}

describe('home stock-bar mobile scroll styles', () => {
  const css = readFileSync(INDEX_CSS_PATH, 'utf8');
  const { layered, unlayered } = splitLayeredAndUnlayered(css);

  it('keeps .home-stock-scroll-shell unlayered with mobile overflow visible', () => {
    const layeredRule = extractRuleBody(
      layered,
      new RegExp(`${SHELL_SELECTOR}\\s*\\{`),
    );
    expect(layeredRule, 'shell rule must not live inside @layer').toBeNull();

    const mobileRule = extractRuleBody(
      unlayered,
      new RegExp(`${SHELL_SELECTOR}\\s*\\{`),
    );
    expect(mobileRule, 'unlayered .home-stock-scroll-shell rule is missing').not.toBeNull();
    expect(declarations(mobileRule ?? '')).toMatchObject({ overflow: 'visible' });
    expect(mobileRule).not.toMatch(/overflow\s*:\s*hidden/);
  });

  it('restores desktop clipping at min-width 48rem', () => {
    const desktopBodies = extractMediaBodies(unlayered, '48rem');
    expect(desktopBodies.length).toBeGreaterThan(0);

    const desktopRule = desktopBodies
      .map((body) => extractRuleBody(body, new RegExp(`${SHELL_SELECTOR}\\s*\\{`)))
      .find((body) => body !== null);
    expect(desktopRule, 'desktop shell rule missing from unlayered 48rem media query').not.toBeNull();
    expect(declarations(desktopRule ?? '')).toMatchObject({ overflow: 'hidden' });

    const weakerBreakpoints = ['40rem', '768px', '640px', 'sm']
      .flatMap((query) => extractMediaBodies(unlayered, query))
      .some((body) => extractRuleBody(body, new RegExp(`${SHELL_SELECTOR}\\s*\\{`)));
    expect(weakerBreakpoints).toBe(false);

    const layeredDesktop = extractMediaBodies(layered, '48rem')
      .some((body) => extractRuleBody(body, new RegExp(`${SHELL_SELECTOR}\\s*\\{`)));
    expect(layeredDesktop).toBe(false);
  });

  it('is wired on StockBar and HomeStockWorkspace, including playground hosts', () => {
    const stockBar = readFileSync(STOCK_BAR_PATH, 'utf8');
    const workspace = readFileSync(WORKSPACE_PATH, 'utf8');
    const scrollArea = readFileSync(SCROLL_AREA_PATH, 'utf8');
    const stockBarScenario = readFileSync(STOCK_BAR_SCENARIO_PATH, 'utf8');
    const workspaceScenario = readFileSync(WORKSPACE_SCENARIO_PATH, 'utf8');

    expect(stockBar).toMatch(/data-testid=["']home-stock-bar["']/);
    expect(stockBar).toMatch(/className=["'][^"']*home-stock-scroll-shell/);
    expect(stockBar).toMatch(/testId=["']home-stock-bar-scroll["']/);
    expect(stockBar).not.toMatch(/overflow-hidden/);

    expect(workspace).toMatch(/data-testid=["']home-stock-workspace["']/);
    expect(workspace).toMatch(/home-stock-scroll-shell/);
    expect(workspace).toMatch(/testId=["']home-stock-workspace-scroll["']/);
    expect(workspace).not.toMatch(/overflow-hidden/);
    expect(workspace).not.toMatch(/touch-pan-y/);

    expect(scrollArea).toMatch(/Do not add touch-pan-y/);
    const classLiterals = [...scrollArea.matchAll(/(['"`])([^'"`]*?)\1/g)].map((match) => match[2]);
    expect(classLiterals.some((value) => /(^|\s)touch-pan-y(\s|$)/.test(value))).toBe(false);

    expect(stockBarScenario).toMatch(/import \{ StockBar \} from ['"][^'"]+\/StockBar['"]/);
    expect(stockBarScenario).toMatch(/<StockBar[\s\S]*?\/>/);
    expect(workspaceScenario).toMatch(/HomeStockWorkspace,/);
    expect(workspaceScenario).toMatch(/<HomeStockWorkspace[\s\S]*?\/>/);

    const stockBarEntry = PLAYGROUND_CATALOG.find((entry) => entry.id === 'stock-bar');
    const workspaceEntry = PLAYGROUND_CATALOG.find((entry) => entry.id === 'home-stock-workspace');
    expect(stockBarEntry).toMatchObject({
      name: 'StockBar',
      sourcePath: 'components/history/StockBar.tsx',
    });
    expect(workspaceEntry).toMatchObject({
      name: 'HomeStockWorkspace',
      sourcePath: 'components/watchlist/HomeStockWorkspace.tsx',
    });
  });
});
