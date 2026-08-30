// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  classifyThemeToken,
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

/**
 * Frozen value-shape contract for every `index.css` custom property (issue #1300
 * Phase 0 format freeze). Names were frozen in #1385; this ratchet freezes the
 * *format* of each assignment without rewriting non-conforming values.
 *
 * Canonical shapes:
 * - hsl-triplet: `H S% L%` (Layer 1 / Tailwind-interop channels)
 * - hsl-function: `hsl(var(--token))` or `hsl(var(--token) / alpha)`
 * - var-ref: `var(--token)`
 * - length / shadow / gradient / hex: geometry, elevation, masks
 *
 * Raw `hsl(H S% L%)` stored in a variable is `hsl-literal` debt, not a
 * canonical format. Do not convert those values here — shrink the ledger later.
 */
const TOKEN_FORMATS = [
  'hsl-triplet',
  'hsl-function',
  'var-ref',
  'length',
  'shadow',
  'gradient',
  'hex',
] as const;

type TokenFormat = (typeof TOKEN_FORMATS)[number];
type TokenValueShape = TokenFormat | 'hsl-literal' | 'unknown';

type TokenAssignment = { token: string; value: string; line: number };

type TokenFormatFinding = TokenAssignment & {
  declared: TokenFormat;
  observed: TokenValueShape;
};

type MeasuredFormatDebt = { token: string; shapes: TokenValueShape[] };

type TokenFormatDebt = {
  token: string;
  allowedDebtShapes: readonly TokenValueShape[];
  reason: string;
  removeWhen: string;
};

type TokenFormatDiff = {
  code: 'new-format-debt' | 'stale-format-debt' | 'shape-drift';
  token: string;
  detail: string;
};

const TOKEN_FORMAT_OVERRIDES = {
  '--bg-subtle-raw': 'var-ref',
  '--border-default': 'var-ref',
  '--border-dim-raw': 'var-ref',
  '--border-subtle-raw': 'var-ref',
  '--color-danger-alert-bg': 'hsl-triplet',
  '--color-danger-alert-border': 'hsl-triplet',
  '--color-danger-alert-text': 'hsl-triplet',
  '--gradient-primary': 'gradient',
  '--home-cool-surface': 'hsl-triplet',
  '--home-cool-surface-strong': 'hsl-triplet',
  '--home-hero-shadow': 'shadow',
  '--home-history-item-selected-bg': 'gradient',
  '--home-mobile-overlay-bg': 'var-ref',
  '--home-panel-selected-shadow': 'shadow',
  '--home-panel-shadow': 'shadow',
  '--home-panel-shadow-hover': 'shadow',
  '--home-rail-bg': 'gradient',
  '--home-rail-shadow': 'shadow',
  '--home-shadow-deep': 'hsl-triplet',
  '--home-shadow-neutral': 'hsl-triplet',
  '--input-surface-bg': 'var-ref',
  '--input-surface-focus-ring': 'shadow',
  '--mask-opaque': 'hex',
  '--nav-indicator-width': 'length',
  '--nav-item-height': 'length',
  '--nav-item-padding-x': 'length',
  '--neutral-black': 'hsl-triplet',
  '--neutral-white': 'hsl-triplet',
  '--overlay-sheet-footer-toast-offset': 'length',
  '--radius-dot': 'length',
} as const satisfies Record<string, TokenFormat>;

function rawHslLiteralDebt(token: string, reason: string): TokenFormatDebt {
  return {
    token,
    allowedDebtShapes: ['hsl-literal'],
    reason,
    removeWhen:
      'Rewrite remaining raw hsl() literals to hsl(var(--token)) during T25/T40 format unification.',
  };
}

const LIGHT_MODE_RAW_HSL_REASON =
  'At least one assignment stores a raw hsl() literal instead of hsl(var(--token)).';
const REPORT_STRATEGY_RAW_HSL_REASON =
  'Strategy hue is stored as a raw hsl() literal instead of hsl(var(--price-*)) or Layer 1.';

/** Shrink-only. Never add an entry to absorb new format drift. */
const TOKEN_FORMAT_DEBT: readonly TokenFormatDebt[] = [
  rawHslLiteralDebt('--home-history-item-hover-bg', LIGHT_MODE_RAW_HSL_REASON),
  rawHslLiteralDebt('--home-panel-subtle-bg', LIGHT_MODE_RAW_HSL_REASON),
  rawHslLiteralDebt('--home-panel-subtle-bg-hover', LIGHT_MODE_RAW_HSL_REASON),
  rawHslLiteralDebt('--home-surface-button-bg', LIGHT_MODE_RAW_HSL_REASON),
  rawHslLiteralDebt('--home-surface-button-bg-hover', LIGHT_MODE_RAW_HSL_REASON),
  rawHslLiteralDebt('--input-surface-border', LIGHT_MODE_RAW_HSL_REASON),
  rawHslLiteralDebt('--input-surface-border-hover', LIGHT_MODE_RAW_HSL_REASON),
  rawHslLiteralDebt('--nav-active-bg', LIGHT_MODE_RAW_HSL_REASON),
  rawHslLiteralDebt('--nav-active-border', LIGHT_MODE_RAW_HSL_REASON),
  rawHslLiteralDebt('--report-strategy-buy', REPORT_STRATEGY_RAW_HSL_REASON),
  rawHslLiteralDebt('--report-strategy-stop', REPORT_STRATEGY_RAW_HSL_REASON),
  rawHslLiteralDebt('--report-strategy-take', REPORT_STRATEGY_RAW_HSL_REASON),
];

const MAX_TOKEN_FORMAT_DEBT = 12;

/**
 * Tokens that are allowed to exist only on `:root` because they are not
 * theme-mode paint: density/geometry, absolute mix inks, and price-direction
 * aliases owned by `[data-price-direction]` (must not be reassigned in `.dark`).
 * Shrink-only. Do not add a color/surface token here to dodge pairing.
 */
const THEME_INDEPENDENT_LIGHT_ONLY_TOKENS = [
  '--mask-opaque',
  '--neutral-black',
  '--neutral-white',
  '--overlay-sheet-footer-toast-offset',
  '--price-down',
  '--price-up',
  '--radius',
  '--radius-dot',
] as const;

/** Remaining `:root` color/surface tokens with no `.dark` assignment. Shrink only. */
const MAX_LIGHT_ONLY_SURFACE_TOKENS = 0;

function extractThemeBlock(source: string, selector: string): string {
  const pattern = new RegExp(`^${selector}\\s*\\{([\\s\\S]*?)^\\}`, 'm');
  const match = source.match(pattern);
  return match?.[1] ?? '';
}

function tokenNamesInBlock(body: string): Set<string> {
  const names = new Set<string>();
  const pattern = /(--[a-zA-Z][\w-]*)\s*:\s*([^;]+);/g;
  for (const match of body.matchAll(pattern)) {
    const token = match[1] ?? '';
    if (token) names.add(token);
  }
  return names;
}

function isThemeIndependentLightOnlyToken(token: string): boolean {
  if (token.startsWith('--density-')) return true;
  return (THEME_INDEPENDENT_LIGHT_ONLY_TOKENS as readonly string[]).includes(token);
}

function collectLightOnlyRootTokens(indexCss: string): string[] {
  const source = maskComments(indexCss);
  const rootTokens = tokenNamesInBlock(extractThemeBlock(source, ':root'));
  const darkTokens = tokenNamesInBlock(extractThemeBlock(source, '\\.dark'));
  return [...rootTokens].filter((token) => !darkTokens.has(token)).sort();
}

function collectLightOnlySurfaceTokens(indexCss: string): string[] {
  return collectLightOnlyRootTokens(indexCss)
    .filter((token) => !isThemeIndependentLightOnlyToken(token));
}

function collapseCssValue(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function isShadowValue(value: string): boolean {
  if (/^(?:linear|radial|conic)-gradient\(/i.test(value)) return false;
  if (/^(?:hsl|hsla|rgb|rgba|var)\(/i.test(value)) return false;
  const hasLength = /-?[\d.]+(?:px|rem|em)\b/.test(value);
  const hasColor = /\b(?:hsl|hsla|rgb|rgba|var)\(/i.test(value)
    || /#[0-9a-fA-F]{3,8}\b/.test(value);
  return hasLength && hasColor;
}

function observedTokenFormat(value: string): TokenValueShape {
  const collapsed = collapseCssValue(value);
  if (/^var\(--[a-zA-Z][\w-]*\)$/.test(collapsed)) return 'var-ref';
  if (/^hsl\(\s*var\(--[a-zA-Z][\w-]*\)\s*(?:\/\s*[\d.]+\s*)?\)$/.test(collapsed)) {
    return 'hsl-function';
  }
  if (/^hsl\(\s*-?[\d.]+(?:deg)?\s+[\d.]+%\s+[\d.]+%\s*(?:\/\s*[\d.]+\s*)?\)$/.test(collapsed)) {
    return 'hsl-literal';
  }
  if (/^-?[\d.]+(?:deg)?\s+[\d.]+%\s+[\d.]+%$/.test(collapsed)) return 'hsl-triplet';
  if (/^#(?:[0-9a-fA-F]{3,8})$/.test(collapsed)) return 'hex';
  if (/^-?[\d.]+(?:px|rem|em|%)$/.test(collapsed)) return 'length';
  if (/^(?:linear|radial|conic)-gradient\(/i.test(collapsed)) return 'gradient';
  if (isShadowValue(collapsed)) return 'shadow';
  return 'unknown';
}

function declaredTokenFormat(token: string): TokenFormat {
  if (Object.prototype.hasOwnProperty.call(TOKEN_FORMAT_OVERRIDES, token)) {
    return TOKEN_FORMAT_OVERRIDES[token as keyof typeof TOKEN_FORMAT_OVERRIDES];
  }
  const tokenClass = classifyThemeToken(token);
  switch (tokenClass) {
    case 'layer0':
      if (token.endsWith('-hsl')) return 'hsl-triplet';
      if (token === '--price-up' || token === '--price-down') return 'var-ref';
      return 'hsl-function';
    case 'layer1':
      return token === '--radius' ? 'length' : 'hsl-triplet';
    case 'layer1-derived':
      return 'hsl-function';
    case 'density':
      return token.startsWith('--density-space-') ? 'length' : 'var-ref';
    case 'elevation':
      return token.startsWith('--shadow-elevation-') ? 'var-ref' : 'shadow';
    case 'compat-alias':
      return token === '--success' || token === '--warning' || token === '--danger'
        ? 'var-ref'
        : 'hsl-triplet';
    case 'legacy-alias':
      return 'var-ref';
    case 'domain':
    case 'page-scoped-debt':
    case 'ungoverned':
      return 'hsl-function';
    default: {
      const exhaustive: never = tokenClass;
      return exhaustive;
    }
  }
}

function collectDefinedTokenAssignments(indexCss: string): TokenAssignment[] {
  const source = maskComments(indexCss);
  const assignments: TokenAssignment[] = [];
  const pattern = /(--[a-zA-Z][\w-]*)\s*:\s*([^;]+);/g;
  for (const match of source.matchAll(pattern)) {
    assignments.push({
      token: match[1] ?? '',
      value: collapseCssValue(match[2] ?? ''),
      line: lineOf(source, match.index ?? 0),
    });
  }
  return assignments;
}

function uniqueDefinedTokenNames(assignments: readonly TokenAssignment[]): string[] {
  return [...new Set(assignments.map((assignment) => assignment.token))].sort();
}

function measureTokenFormatDebt(
  assignments: readonly TokenAssignment[],
): MeasuredFormatDebt[] {
  const byToken = new Map<string, TokenAssignment[]>();
  for (const assignment of assignments) {
    const list = byToken.get(assignment.token) ?? [];
    list.push(assignment);
    byToken.set(assignment.token, list);
  }
  const debt: MeasuredFormatDebt[] = [];
  for (const token of [...byToken.keys()].sort()) {
    const declared = declaredTokenFormat(token);
    const shapes = [...new Set(
      (byToken.get(token) ?? [])
        .map((assignment) => observedTokenFormat(assignment.value))
        .filter((shape) => shape !== declared),
    )].sort();
    if (shapes.length === 0) continue;
    debt.push({ token, shapes });
  }
  return debt;
}

function diffTokenFormatDebt(
  measured: readonly MeasuredFormatDebt[],
  ledger: readonly TokenFormatDebt[],
): TokenFormatDiff[] {
  const diffs: TokenFormatDiff[] = [];
  const measuredMap = new Map(measured.map((entry) => [entry.token, entry]));
  const ledgerMap = new Map(ledger.map((entry) => [entry.token, entry]));
  for (const entry of measured) {
    const allowed = ledgerMap.get(entry.token);
    if (!allowed) {
      diffs.push({
        code: 'new-format-debt',
        token: entry.token,
        detail: entry.shapes.join(','),
      });
      continue;
    }
    const allowedShapes = [...allowed.allowedDebtShapes].sort();
    if (allowedShapes.join('\0') !== entry.shapes.join('\0')) {
      diffs.push({
        code: 'shape-drift',
        token: entry.token,
        detail: `measured=${entry.shapes.join(',')} allowed=${allowedShapes.join(',')}`,
      });
    }
  }
  for (const entry of ledger) {
    if (measuredMap.has(entry.token)) continue;
    diffs.push({
      code: 'stale-format-debt',
      token: entry.token,
      detail: 'ledger entry no longer measured',
    });
  }
  return diffs;
}

function collectTokenFormatAssignmentFindings(indexCss: string): TokenFormatFinding[] {
  const ledgerShapes = new Map(
    TOKEN_FORMAT_DEBT.map((entry) => [entry.token, new Set(entry.allowedDebtShapes)]),
  );
  const findings: TokenFormatFinding[] = [];
  for (const assignment of collectDefinedTokenAssignments(indexCss)) {
    const declared = declaredTokenFormat(assignment.token);
    const observed = observedTokenFormat(assignment.value);
    if (observed === declared) continue;
    if (ledgerShapes.get(assignment.token)?.has(observed)) continue;
    findings.push({ ...assignment, declared, observed });
  }
  return findings;
}

function formatTokenFormatFindings(findings: readonly TokenFormatFinding[]): string {
  return findings
    .map((finding) => (
      `${finding.token}: declared ${finding.declared}, observed ${finding.observed} (${finding.value})`
    ))
    .join('\n');
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

  describe('theme token format freeze', () => {
    const assignments = collectDefinedTokenAssignments(indexCss);
    const uniqueNames = uniqueDefinedTokenNames(assignments);
    const measuredDebt = measureTokenFormatDebt(assignments);
    const frozenCount = uniqueNames.length - measuredDebt.length;

    it('declares a format for every defined custom property', () => {
      // Non-vacuity floor only. Phase 2 domain collapses (login/backtest/
      // portfolio/chat/settings) shrank the defined inventory below 190.
      expect(uniqueNames.length).toBeGreaterThan(170);
      for (const token of uniqueNames) {
        expect(TOKEN_FORMATS, token).toContain(declaredTokenFormat(token));
      }
      for (const token of Object.keys(TOKEN_FORMAT_OVERRIDES)) {
        expect(uniqueNames, token).toContain(token);
        const declared = declaredTokenFormat(token);
        const shapes = [...new Set(
          assignments
            .filter((assignment) => assignment.token === token)
            .map((assignment) => observedTokenFormat(assignment.value)),
        )];
        expect(shapes, token).toEqual([declared]);
      }
    });

    it('keeps current index.css green against the seeded format ledger', () => {
      const counts = {
        unique: uniqueNames.length,
        frozen: frozenCount,
        allowlisted: measuredDebt.length,
      };
      expect(
        counts,
        `frozen=${counts.frozen} allowlisted=${counts.allowlisted} unique=${counts.unique}`,
      ).toEqual({
        unique: uniqueNames.length,
        frozen: uniqueNames.length - MAX_TOKEN_FORMAT_DEBT,
        allowlisted: MAX_TOKEN_FORMAT_DEBT,
      });
      expect(measuredDebt.length).toBeLessThanOrEqual(MAX_TOKEN_FORMAT_DEBT);
      expect(measuredDebt.length).toBe(MAX_TOKEN_FORMAT_DEBT);
      expect(TOKEN_FORMAT_DEBT.length).toBe(MAX_TOKEN_FORMAT_DEBT);
      expect(TOKEN_FORMAT_DEBT.map((entry) => entry.token)).toEqual(
        [...TOKEN_FORMAT_DEBT.map((entry) => entry.token)].sort(),
      );
      expect(diffTokenFormatDebt(measuredDebt, TOKEN_FORMAT_DEBT)).toEqual([]);
      expect(collectTokenFormatAssignmentFindings(indexCss)).toEqual([]);
      for (const entry of TOKEN_FORMAT_DEBT) {
        expect(entry.reason.trim().length, entry.token).toBeGreaterThan(0);
        expect(entry.removeWhen.trim().length, entry.token).toBeGreaterThan(0);
        expect(entry.allowedDebtShapes.length, entry.token).toBeGreaterThan(0);
        expect(entry.allowedDebtShapes).not.toContain(declaredTokenFormat(entry.token));
      }
    });

    it('fails when a frozen token is assigned a wrong-shaped value', () => {
      const findings = collectTokenFormatAssignmentFindings(`
        :root {
          --primary: #ff00aa;
          --radius: hsl(var(--primary));
        }
      `);
      const formatted = formatTokenFormatFindings(findings);
      expect(formatted).toContain('--primary: declared hsl-triplet, observed hex (#ff00aa)');
      expect(formatted).toContain('--radius: declared length, observed hsl-function (hsl(var(--primary)))');
    });

    it('rejects raising the format-debt ceiling without matching measured debt', () => {
      const raisedCeiling = MAX_TOKEN_FORMAT_DEBT + 1;
      expect(measuredDebt.length).toBeLessThan(raisedCeiling);
      expect(measuredDebt.length).toBe(MAX_TOKEN_FORMAT_DEBT);
      const staleLedger = [
        ...TOKEN_FORMAT_DEBT,
        rawHslLiteralDebt('--primary', 'synthetic extra ceiling slot'),
      ];
      expect(staleLedger.length).toBe(raisedCeiling);
      const stale = diffTokenFormatDebt(measuredDebt, staleLedger);
      expect(stale.some((item) => (
        item.code === 'stale-format-debt' && item.token === '--primary'
      ))).toBe(true);
    });

    it('rejects unlisted format drift and stale ledger entries', () => {
      const hexBackground = collectDefinedTokenAssignments(`
        ${indexCss}
        :root { --background: #ffffff; }
      `);
      const hexDebt = measureTokenFormatDebt(hexBackground);
      expect(hexDebt.some((entry) => (
        entry.token === '--background' && entry.shapes.includes('hex')
      ))).toBe(true);
      expect(diffTokenFormatDebt(hexDebt, TOKEN_FORMAT_DEBT).some((diff) => (
        diff.code === 'new-format-debt' && diff.token === '--background'
      ))).toBe(true);

      const convertedNav = assignments.filter((assignment) => (
        assignment.token !== '--nav-active-bg'
        || observedTokenFormat(assignment.value) === 'hsl-function'
      ));
      const stale = diffTokenFormatDebt(measureTokenFormatDebt(convertedNav), TOKEN_FORMAT_DEBT);
      expect(stale.some((diff) => (
        diff.code === 'stale-format-debt' && diff.token === '--nav-active-bg'
      ))).toBe(true);

      const hexNav = collectDefinedTokenAssignments(`
        :root { --nav-active-bg: #00ffaa; }
      `);
      expect(diffTokenFormatDebt(measureTokenFormatDebt(hexNav), TOKEN_FORMAT_DEBT).some((diff) => (
        diff.code === 'shape-drift' && diff.token === '--nav-active-bg'
      ))).toBe(true);
    });
  });

  describe('light/dark surface pairing', () => {
    const lightOnlyRoot = collectLightOnlyRootTokens(indexCss);
    const lightOnlySurface = collectLightOnlySurfaceTokens(indexCss);
    const independentLightOnly = lightOnlyRoot.filter(isThemeIndependentLightOnlyToken);

    it('keeps every :root color/surface token paired in .dark', () => {
      expect(lightOnlySurface.length).toBeLessThanOrEqual(MAX_LIGHT_ONLY_SURFACE_TOKENS);
      expect(lightOnlySurface.length).toBe(MAX_LIGHT_ONLY_SURFACE_TOKENS);
      expect(lightOnlySurface).toEqual([]);
      expect(lightOnlyRoot).toEqual(independentLightOnly);
      expect(THEME_INDEPENDENT_LIGHT_ONLY_TOKENS).toEqual(
        [...THEME_INDEPENDENT_LIGHT_ONLY_TOKENS].sort(),
      );
      expect(
        independentLightOnly.filter((token) => !token.startsWith('--density-')),
      ).toEqual([...THEME_INDEPENDENT_LIGHT_ONLY_TOKENS]);
      expect(
        independentLightOnly.filter((token) => token.startsWith('--density-')).length,
      ).toBeGreaterThan(0);
    });

    it('fails when a new color/surface token is defined only on :root', () => {
      const unpaired = collectLightOnlySurfaceTokens(`
:root {
  --radius: 0.75rem;
  --mask-opaque: #000;
  --audit-surface: 80 7% 97%;
}
.dark {
}
`);
      expect(unpaired).toEqual(['--audit-surface']);
      expect(unpaired).not.toContain('--radius');
      expect(unpaired).not.toContain('--mask-opaque');
    });

    it('does not treat density or price-direction tokens as unpaired surface paint', () => {
      const unpaired = collectLightOnlySurfaceTokens(`
:root {
  --density-space-1: 0.25rem;
  --price-up: var(--price-red);
  --price-down: var(--price-green);
  --card: 0 0% 100%;
}
.dark {
  --card: 70 4% 11%;
}
`);
      expect(unpaired).toEqual([]);
    });
  });
});
