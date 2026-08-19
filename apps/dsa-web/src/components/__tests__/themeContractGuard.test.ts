// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  THEME_CORE_CSS_VARS,
  THEME_LAYER0_CSS_VARS,
  THEME_LEGACY_PRICE_ALIASES,
  THEME_PACK_FORBIDDEN_VARS,
  THEME_PACK_IDS,
} from '../../design/theme';
import { THEME_PACKS } from '../../design/themePacks';
import {
  assertNonEmptyProductionInventory,
  isTypeScriptModulePath,
  productionCssSources,
  productionTypeScriptSources,
} from './productionSourceInventory';

const INDEX_CSS = '../../index.css';

type Finding = { file: string; line: number; token: string };

/** Ratchet ceilings — baseline only decreases. Never raise to absorb new debt. */
const MAX_LEGACY_HOME_PRICE_RAW_HUE_DEFINITIONS = 0;
const MAX_HARDCODED_HOME_PRICE_CSS_VAR_REFS = 0;
const MAX_PARALLEL_PRICE_TOKEN_DEFINITIONS = 0;
const MAX_PACK_FORBIDDEN_OVERRIDES = 0;
const MAX_COMMON_PAGE_TOKEN_REFS = 0;
const CANONICAL_PRICE_HUE_OWNER = 'utils/marketFormat.ts';

/**
 * Remaining production sites that map a signed change/PnL/return to
 * success/danger CSS instead of `changeColorCssVar`. Occurrence-level
 * ceiling — shrink only. MarketStructureCard `text-success` icons stay
 * decorative and are not a signed-direction mapping.
 */
const PRICE_DIRECTION_BYPASS_DEBT: readonly string[] = [];
const MAX_PRICE_DIRECTION_BYPASS_DEBT = 0;

function lineOf(source: string, index: number): number {
  return source.slice(0, index).split('\n').length;
}

function maskComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/gm, (comment) => comment.replace(/[^\n]/g, ' '));
}

function findMissingCoreVars(indexCss: string): string[] {
  const source = maskComments(indexCss);
  return THEME_CORE_CSS_VARS.filter((token) => !source.includes(`${token}:`));
}

function findMissingLegacyAliases(indexCss: string): Finding[] {
  const source = maskComments(indexCss);
  const findings: Finding[] = [];
  for (const alias of THEME_LEGACY_PRICE_ALIASES) {
    const pattern = new RegExp(`${alias.replace(/-/g, '\\-')}\\s*:\\s*([^;]+);`);
    const match = source.match(pattern);
    if (!match) {
      findings.push({ file: INDEX_CSS, line: 1, token: `${alias}:missing` });
      continue;
    }
    const value = match[1].trim();
    if (!value.startsWith('var(--price-')) {
      findings.push({
        file: INDEX_CSS,
        line: lineOf(source, match.index ?? 0),
        token: `${alias}:raw:${value}`,
      });
    }
  }
  return findings;
}

function findLegacyHomePriceRawHueDefinitions(indexCss: string): Finding[] {
  const source = maskComments(indexCss);
  const findings: Finding[] = [];
  const pattern = /--home-price-(?:up|down)\s*:\s*([^;]+);/g;
  for (const match of source.matchAll(pattern)) {
    const value = (match[1] ?? '').trim();
    // Accept only Layer 0 var() aliases; any other value is residual raw debt.
    if (value.startsWith('var(--price-')) continue;
    findings.push({
      file: INDEX_CSS,
      line: lineOf(source, match.index ?? 0),
      token: match[0].replace(/\s*;$/, ''),
    });
  }
  return findings;
}

function findParallelPriceDefinitions(sources: Record<string, string>): Finding[] {
  const findings: Finding[] = [];
  const definitionPattern = /--price-(?:red|green|up|down)\s*:/g;
  for (const [file, raw] of Object.entries(sources)) {
    if (file === INDEX_CSS || file.endsWith('/index.css')) continue;
    const source = maskComments(raw);
    for (const match of source.matchAll(definitionPattern)) {
      findings.push({
        file,
        line: lineOf(source, match.index ?? 0),
        token: match[0].replace(/\s*:$/, ''),
      });
    }
  }
  return findings;
}

function findPackForbiddenOverrides(indexCss: string): Finding[] {
  const source = maskComments(indexCss);
  const findings: Finding[] = [];
  for (const pattern of [
    /\[data-theme-pack="[^"]+"\][^{]*\{([^}]*)\}/g,
    /\.dark\[data-theme-pack="[^"]+"\][^{]*\{([^}]*)\}/g,
  ]) {
    for (const block of source.matchAll(pattern)) {
      const body = block[1] ?? '';
      for (const token of THEME_PACK_FORBIDDEN_VARS) {
        if (body.includes(`${token}:`)) {
          findings.push({
            file: INDEX_CSS,
            line: lineOf(source, block.index ?? 0),
            token: `pack-forbidden:${token}`,
          });
        }
      }
    }
  }
  return findings;
}

function findHardcodedHomePriceRefs(sources: Record<string, string>): Finding[] {
  const findings: Finding[] = [];
  const pattern = /--home-price-(?:up|down)/g;
  for (const [file, raw] of Object.entries(sources)) {
    if (file.endsWith('/index.css') || file === INDEX_CSS) continue;
    if (file.includes('/design/theme')) continue;
    const source = maskComments(raw);
    for (const match of source.matchAll(pattern)) {
      findings.push({
        file,
        line: lineOf(source, match.index ?? 0),
        token: match[0],
      });
    }
  }
  return findings;
}

function findCommonPageTokenRefs(sources: Record<string, string>): Finding[] {
  const findings: Finding[] = [];
  const pattern = /var\(--(?:home|settings|login|chat|backtest)-[\w-]+/g;
  for (const [file, raw] of Object.entries(sources)) {
    if (!file.includes('/common/')) continue;
    const source = maskComments(raw);
    for (const match of source.matchAll(pattern)) {
      findings.push({
        file,
        line: lineOf(source, match.index ?? 0),
        token: match[0].slice(4),
      });
    }
  }
  return findings;
}

function findMissingPackSelectors(indexCss: string): string[] {
  const source = maskComments(indexCss);
  const missing: string[] = [];
  for (const id of THEME_PACK_IDS) {
    if (id === 'classic') continue;
    if (!source.includes(`[data-theme-pack="${id}"]`)) missing.push(id);
  }
  return missing;
}

function findMissingPriceDirectionSelectors(indexCss: string): string[] {
  const source = maskComments(indexCss);
  const missing: string[] = [];
  if (!source.includes('[data-price-direction="cn"]')) missing.push('cn');
  if (!source.includes('[data-price-direction="us"]')) missing.push('us');
  return missing;
}

/** Glob keys from `src/components/__tests__/` → path under `src/`. */
function srcRelativeGuardPath(file: string): string {
  if (file.startsWith('../../')) return file.slice('../../'.length);
  if (file.startsWith('../')) return `components/${file.slice('../'.length)}`;
  return file;
}

function isCanonicalPriceHueOwner(file: string): boolean {
  return srcRelativeGuardPath(file) === CANONICAL_PRICE_HUE_OWNER
    || file.endsWith('/utils/marketFormat.ts');
}

/**
 * Any production module other than `utils/marketFormat.ts` that maps a
 * change direction / ChangeColor / signed change onto a CSS colour value.
 */
function findPriceDirectionCssMappings(file: string, raw: string): Finding[] {
  if (isCanonicalPriceHueOwner(file)) return [];
  const source = maskComments(raw);
  const findings: Finding[] = [];
  const patterns: ReadonlyArray<{ token: string; regex: RegExp }> = [
    { token: 'changeColorToCss', regex: /\bchangeColorToCss\b/g },
    { token: 'CHANGE_COLOR_CSS_VAR', regex: /\bCHANGE_COLOR_CSS_VAR\b/g },
    {
      token: 'change-color-eq-css',
      regex: /(?:\bcolor\s*===\s*['"](?:red|green)['"]|['"](?:red|green)['"]\s*===\s*\bcolor\b)[\s\S]{0,160}?(?:--price-red|--price-green|--danger|--success)/g,
    },
    {
      token: 'change-color-table',
      regex: /['"]red['"]\s*:\s*['"][^'"]*(?:--price-red|--danger)/g,
    },
    {
      token: 'signed-to-status-css',
      regex: /(?:>=?|<=?)\s*0\s*\?\s*['"](?:text-)?(?:success|danger)['"][\s\S]{0,160}?['"](?:text-)?(?:success|danger)['"]/g,
    },
  ];
  for (const { token, regex } of patterns) {
    for (const match of source.matchAll(regex)) {
      findings.push({
        file,
        line: lineOf(source, match.index ?? 0),
        token,
      });
    }
  }
  return findings;
}

function collectPriceDirectionCssMappings(sources: Record<string, string>): Finding[] {
  return Object.entries(sources).flatMap(([file, raw]) => findPriceDirectionCssMappings(file, raw));
}

/** `.dark { }` (not `.dark .child` / `.dark[attr]`) must not reassign direction tokens. */
function findDarkThemeDirectionOverrides(indexCss: string): Finding[] {
  const source = maskComments(indexCss);
  const findings: Finding[] = [];
  const match = source.match(/^\.dark\s*\{([\s\S]*?)^\}/m);
  if (!match) return findings;
  const body = match[1] ?? '';
  for (const token of ['--price-up', '--price-down'] as const) {
    const tokenIndex = body.search(new RegExp(`${token}\\s*:`));
    if (tokenIndex < 0) continue;
    findings.push({
      file: INDEX_CSS,
      line: lineOf(source, (match.index ?? 0) + tokenIndex),
      token,
    });
  }
  return findings;
}

describe('theme contract guard', () => {
  assertNonEmptyProductionInventory(productionTypeScriptSources, 'productionTypeScriptSources');
  assertNonEmptyProductionInventory(productionCssSources, 'productionCssSources');
  const indexCss = fs.readFileSync('src/index.css', 'utf8');
  const productionCssAndTypeScript = {
    ...productionCssSources,
    [INDEX_CSS]: indexCss,
    ...productionTypeScriptSources,
  };

  it('keeps Theme Contract v1 core tokens declared in index.css', () => {
    expect(findMissingCoreVars(indexCss)).toEqual([]);
    for (const token of THEME_LAYER0_CSS_VARS) {
      expect(indexCss.includes(`${token}:`)).toBe(true);
    }
  });

  it('aliases legacy --home-price-* to Layer 0 price hues (no raw hue values)', () => {
    const rawHue = findLegacyHomePriceRawHueDefinitions(indexCss);
    expect(rawHue.length).toBeLessThanOrEqual(MAX_LEGACY_HOME_PRICE_RAW_HUE_DEFINITIONS);
    expect(rawHue).toEqual([]);
    expect(findMissingLegacyAliases(indexCss)).toEqual([]);
  });

  it('rejects parallel --price-* definitions outside index.css', () => {
    const parallel = findParallelPriceDefinitions(productionCssAndTypeScript);
    expect(parallel.length).toBeLessThanOrEqual(MAX_PARALLEL_PRICE_TOKEN_DEFINITIONS);
    expect(parallel).toEqual([]);
  });

  it('forbids theme packs from overriding Layer 0 price tokens', () => {
    const forbidden = findPackForbiddenOverrides(indexCss);
    expect(forbidden.length).toBeLessThanOrEqual(MAX_PACK_FORBIDDEN_OVERRIDES);
    expect(forbidden).toEqual([]);
  });

  it('requires slate pack + price-direction selectors for system validation', () => {
    expect(findMissingPackSelectors(indexCss)).toEqual([]);
    expect(findMissingPriceDirectionSelectors(indexCss)).toEqual([]);
    expect(indexCss).toContain('[data-theme-pack="slate"]');
    expect(THEME_PACKS.slate.id).toBe('slate');
    expect(THEME_PACKS.classic.modes.light).toEqual({});
  });

  it('keeps data-price-direction after .dark so US mapping is not reset', () => {
    const source = maskComments(indexCss);
    const darkIdx = source.search(/^\.dark\s*\{/m);
    const usIdx = source.indexOf('[data-price-direction="us"]');
    expect(darkIdx).toBeGreaterThanOrEqual(0);
    expect(usIdx).toBeGreaterThan(darkIdx);
    expect(findDarkThemeDirectionOverrides(indexCss)).toEqual([]);
  });

  it('ratchets hardcoded --home-price-* production references downward only', () => {
    const refs = findHardcodedHomePriceRefs(productionCssAndTypeScript);
    expect(refs.length).toBeLessThanOrEqual(MAX_HARDCODED_HOME_PRICE_CSS_VAR_REFS);
    expect(refs).toEqual([]);
  });

  it('forbids shared common components from depending on page token families', () => {
    const refs = findCommonPageTokenRefs(productionCssAndTypeScript);
    expect(refs.length).toBeLessThanOrEqual(MAX_COMMON_PAGE_TOKEN_REFS);
    expect(refs).toEqual([]);
  });

  it('wires badge-trend classes to direction tokens', () => {
    expect(indexCss).toMatch(/\.badge-trend-up\s*\{[^}]*var\(--price-up\)/s);
    expect(indexCss).toMatch(/\.badge-trend-down\s*\{[^}]*var\(--price-down\)/s);
    expect(indexCss).toMatch(/\.price-up\s*\{[^}]*var\(--price-up\)/s);
    expect(indexCss).toMatch(/\.price-down\s*\{[^}]*var\(--price-down\)/s);
  });

  it('detects contract violations in fixtures without expanding production debt', () => {
    const parallel = findParallelPriceDefinitions({
      '../../pages/ExamplePage.tsx': 'const rules = `--price-up: red;`;',
    });
    expect(parallel.map(({ token }) => token)).toContain('--price-up');

    const packLeak = findPackForbiddenOverrides(`
      [data-theme-pack="evil"] {
        --primary: 0 0% 50%;
        --price-red: hsl(0 0% 50%);
      }
    `);
    expect(packLeak.map(({ token }) => token)).toContain('pack-forbidden:--price-red');

    const rawHue = findLegacyHomePriceRawHueDefinitions(`
      :root { --home-price-up: hsl(0 88% 62%); }
    `);
    expect(rawHue.length).toBe(1);

    const homeRefs = findHardcodedHomePriceRefs({
      '../../components/report/ReportOverview.tsx': "return { color: 'var(--home-price-up)' };",
    });
    expect(homeRefs.map(({ token }) => token)).toContain('--home-price-up');

    const darkOverride = findDarkThemeDirectionOverrides(`
.dark {
  --price-up: var(--price-red);
  --price-down: var(--price-green);
}
`);
    expect(darkOverride.map(({ token }) => token)).toEqual(['--price-up', '--price-down']);

    const commonPageRefs = findCommonPageTokenRefs({
      '../../components/common/Example.tsx': "return <div style={{ color: 'var(--login-text)' }} />;",
    });
    expect(commonPageRefs.map(({ token }) => token)).toEqual(['--login-text']);

    const mapper = findPriceDirectionCssMappings('../charts/chartUtils.ts', `
export function changeColorToCss(color: ChangeColor): string {
  if (color === 'red') return 'hsl(var(--danger))';
  if (color === 'green') return 'hsl(var(--success))';
  return 'hsl(var(--muted-foreground))';
}
`);
    expect(mapper.map(({ token }) => token)).toContain('changeColorToCss');
    expect(mapper.map(({ token }) => token)).toContain('change-color-eq-css');

    expect(findPriceDirectionCssMappings(
      '../../utils/marketFormat.ts',
      "export const CHANGE_COLOR_CSS_VAR = { red: 'var(--price-red)', green: 'var(--price-green)' };",
    )).toEqual([]);

    expect(findPriceDirectionCssMappings(
      '../../pages/ExamplePage.tsx',
      "const cls = value >= 0 ? 'text-success' : 'text-danger';",
    ).map((finding) => finding.token)).toContain('signed-to-status-css');
  });

  it('fails closed when the TypeScript inventory is empty and still scans .ts modules', () => {
    expect(Object.keys(productionTypeScriptSources).some(isTypeScriptModulePath)).toBe(true);
    expect(() => assertNonEmptyProductionInventory({}, 'productionTypeScriptSources'))
      .toThrow(/empty/);
    const parallel = findParallelPriceDefinitions({
      '../../utils/themeFixture.ts': 'const rules = `--price-up: red;`;',
    });
    expect(parallel).toEqual([
      expect.objectContaining({
        file: '../../utils/themeFixture.ts',
        token: '--price-up',
      }),
    ]);
  });

  it('forbids production modules other than marketFormat from mapping change direction to CSS', () => {
    const findings = collectPriceDirectionCssMappings(productionTypeScriptSources);
    const forbidden = findings.filter((finding) => finding.token !== 'signed-to-status-css');
    expect(forbidden).toEqual([]);
    expect(findings.some((finding) => finding.token === 'changeColorToCss')).toBe(false);
  });

  it('ratchets remaining price-direction bypass debt downward only', () => {
    const findings = collectPriceDirectionCssMappings(productionTypeScriptSources)
      .filter((finding) => finding.token === 'signed-to-status-css');
    const files = [...new Set(findings.map((finding) => srcRelativeGuardPath(finding.file)))].sort();
    expect(findings.length).toBeLessThanOrEqual(MAX_PRICE_DIRECTION_BYPASS_DEBT);
    expect(findings.length).toBe(MAX_PRICE_DIRECTION_BYPASS_DEBT);
    expect(files).toEqual([...PRICE_DIRECTION_BYPASS_DEBT].sort());
  });
});
