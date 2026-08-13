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
  productionCssSources,
  productionTsxSources,
} from './productionSourceInventory';

const INDEX_CSS = '../../index.css';

type Finding = { file: string; line: number; token: string };

/** Ratchet ceilings — baseline only decreases. Never raise to absorb new debt. */
const MAX_LEGACY_HOME_PRICE_RAW_HUE_DEFINITIONS = 0;
const MAX_HARDCODED_HOME_PRICE_CSS_VAR_REFS = 0;
const MAX_PARALLEL_PRICE_TOKEN_DEFINITIONS = 0;
const MAX_PACK_FORBIDDEN_OVERRIDES = 0;

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

describe('theme contract guard', () => {
  const indexCss = fs.readFileSync('src/index.css', 'utf8');
  const productionCssAndTsx = {
    ...productionCssSources,
    [INDEX_CSS]: indexCss,
    ...productionTsxSources,
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
    const parallel = findParallelPriceDefinitions(productionCssAndTsx);
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

  it('ratchets hardcoded --home-price-* production references downward only', () => {
    const refs = findHardcodedHomePriceRefs(productionCssAndTsx);
    expect(refs.length).toBeLessThanOrEqual(MAX_HARDCODED_HOME_PRICE_CSS_VAR_REFS);
    expect(refs).toEqual([]);
  });

  it('wires badge-trend classes to direction tokens', () => {
    expect(indexCss).toMatch(/\.badge-trend-up\s*\{[^}]*var\(--price-up\)/s);
    expect(indexCss).toMatch(/\.badge-trend-down\s*\{[^}]*var\(--price-down\)/s);
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
  });
});
