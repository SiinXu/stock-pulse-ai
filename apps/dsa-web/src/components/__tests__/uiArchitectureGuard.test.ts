// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
import { describe, expect, it } from 'vitest';

const tsxSources = import.meta.glob('../../**/*.tsx', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>;

const tsSources = import.meta.glob('../../**/*.ts', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>;

const NATIVE_CONTROL_PATTERN = /<(?:button|input|select|textarea)\b/g;
const INVALID_SURFACE_PATTERN = /(?<![\w-])bg-surface(?:\/[^\s"'}]*)?(?![\w-])/g;
const RAW_WHITE_PATTERN = /(?<![\w-])(?:bg|border|text|ring|shadow|divide|from|via|to)-white(?:\/[^\s"'}]*)?(?![\w-])/g;
const RAW_PALETTE_PATTERN = /(?<![\w-])(?:bg|border|text|ring|shadow|divide|from|via|to)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}(?:\/[^\s"'}]*)?(?![\w-])/g;
const OVERLAY_Z_PATTERN = /(?<![\w-])z-(?:3[0-9]|[4-9][0-9]|[1-9][0-9]{2,}|\[[^\]]+\])(?![\w-])/g;
const HOME_CLASS_PATTERN = /\bhome-[a-zA-Z0-9_-]+\b/g;
const SETTINGS_CLASS_PATTERN = /\bsettings-[a-zA-Z0-9_-]+\b/g;
const DISPLAY_TEXT_STATUS_LOGIC_PATTERN =
  /(?:\b(?:issue|error|status|reason|stage|state)\w*\s*(?:===|!==|==|!=)\s*['"][^'"\r\n]*[\u3400-\u9fff][^'"\r\n]*['"]|\b(?:issues?|errors?|statuses?)\.push\(\s*['"][^'"\r\n]*[\u3400-\u9fff][^'"\r\n]*['"])/gi;

type DebtAllowance = {
  count: number;
  owner: 'web-ui';
  introducedBy: 'pre-batch-0-baseline';
  removeByBatch: 'Batch 1' | 'Batch 2' | 'Batch 3' | 'Batch 4' | 'Batch 5' | 'Batch 6';
  deleteCondition: string;
};

const NATIVE_PAGE_CONTROL_DEBT: Record<string, DebtAllowance> = {};
const INVALID_SURFACE_DEBT: Record<string, DebtAllowance> = {};
const RAW_WHITE_DEBT: Record<string, DebtAllowance> = {};
const RAW_PALETTE_DEBT: Record<string, DebtAllowance> = {};
const OVERLAY_Z_DEBT: Record<string, DebtAllowance> = {};
const DOMAIN_CLASS_DEBT: Record<string, DebtAllowance> = {};

function isProductionSource(filename: string): boolean {
  return !filename.includes('/__tests__/')
    && !filename.includes('/fixtures/')
    && !filename.includes('/generated/')
    && !filename.includes('/stories/')
    && !/\.(?:test|spec|story|stories|generated)\.(?:ts|tsx)$/.test(filename);
}

function normalizePath(filename: string): string {
  if (filename.startsWith('../../')) {
    return filename.slice('../../'.length);
  }
  if (filename.startsWith('../')) {
    return 'components/' + filename.slice('../'.length);
  }
  return filename;
}

function maskComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/gm, (comment) => comment.replace(/[^\n]/g, ' '));
}

function countMatches(source: string, pattern: RegExp): number {
  return Array.from(maskComments(source).matchAll(new RegExp(pattern.source, pattern.flags))).length;
}

function collectCounts(
  sources: Record<string, string>,
  pattern: RegExp,
  include: (path: string) => boolean,
): Record<string, number> {
  return Object.fromEntries(
    Object.entries(sources)
      .filter(([filename]) => isProductionSource(filename))
      .map(([filename, source]) => [normalizePath(filename), source] as const)
      .filter(([path]) => include(path))
      .map(([path, source]) => [path, countMatches(source, pattern)] as const)
      .filter(([, count]) => count > 0)
      .sort(([left], [right]) => left.localeCompare(right)),
  );
}

function expectedCounts(allowances: Record<string, DebtAllowance>): Record<string, number> {
  return Object.fromEntries(
    Object.entries(allowances)
      .map(([path, allowance]) => [path, allowance.count] as const)
      .sort(([left], [right]) => left.localeCompare(right)),
  );
}

function expectDebtToMatch(
  actual: Record<string, number>,
  allowances: Record<string, DebtAllowance>,
  rule: string,
): void {
  expect(
    actual,
    rule + ' debt changed. Remove migrated entries or add a precise owner, target Batch, and delete condition.',
  ).toEqual(expectedCounts(allowances));
}

function isPageOrDomain(path: string): boolean {
  return path.startsWith('pages/')
    || (path.startsWith('components/') && !path.startsWith('components/common/'));
}

function isHomeClassLeak(path: string): boolean {
  return !path.startsWith('pages/HomePage.tsx');
}

function isSettingsClassLeak(path: string): boolean {
  return path !== 'pages/SettingsPage.tsx' && !path.startsWith('components/settings/');
}

function collectDomainClassDebt(): Record<string, number> {
  const homeDebt = collectCounts(tsxSources, HOME_CLASS_PATTERN, isHomeClassLeak);
  const settingsDebt = collectCounts(tsxSources, SETTINGS_CLASS_PATTERN, isSettingsClassLeak);
  const paths = new Set([...Object.keys(homeDebt), ...Object.keys(settingsDebt)]);
  return Object.fromEntries(
    Array.from(paths)
      .sort()
      .map((path) => [path, (homeDebt[path] ?? 0) + (settingsDebt[path] ?? 0)]),
  );
}

describe('UI architecture guard', () => {
  it('self-tests every migration rule', () => {
    expect(countMatches('<button type="button">Run</button>', NATIVE_CONTROL_PATTERN)).toBe(1);
    expect(countMatches('<div className="bg-surface/80" />', INVALID_SURFACE_PATTERN)).toBe(1);
    expect(countMatches('<div className="bg-surface-1" />', INVALID_SURFACE_PATTERN)).toBe(0);
    expect(countMatches('<div className="border-white/10" />', RAW_WHITE_PATTERN)).toBe(1);
    expect(countMatches('<div className="text-amber-700" />', RAW_PALETTE_PATTERN)).toBe(1);
    expect(countMatches('<div className="text-warning" />', RAW_PALETTE_PATTERN)).toBe(0);
    expect(countMatches('<div className="z-[120]" />', OVERLAY_Z_PATTERN)).toBe(1);
    expect(countMatches("if (issue === '缺少 API 密钥') return;", DISPLAY_TEXT_STATUS_LOGIC_PATTERN)).toBe(1);
    expect(countMatches("if (issue === 'missing_api_key') return;", DISPLAY_TEXT_STATUS_LOGIC_PATTERN)).toBe(0);
  });

  it('keeps migration debt metadata actionable', () => {
    const allowances = [
      NATIVE_PAGE_CONTROL_DEBT,
      INVALID_SURFACE_DEBT,
      RAW_WHITE_DEBT,
      RAW_PALETTE_DEBT,
      OVERLAY_Z_DEBT,
      DOMAIN_CLASS_DEBT,
    ].flatMap((group) => Object.values(group));

    expect(allowances).toEqual([]);
    for (const allowance of allowances) {
      expect(allowance.owner).toBe('web-ui');
      expect(allowance.introducedBy).toBe('pre-batch-0-baseline');
      expect(allowance.removeByBatch).toMatch(/^Batch [1-6]$/);
      expect(allowance.deleteCondition.trim().length).toBeGreaterThan(12);
    }
  });

  it('prevents native controls outside shared primitives', () => {
    const actual = collectCounts(
      tsxSources,
      NATIVE_CONTROL_PATTERN,
      isPageOrDomain,
    );
    expectDebtToMatch(actual, NATIVE_PAGE_CONTROL_DEBT, 'Native page or domain control');
  });

  it('prevents new invalid bg-surface utilities', () => {
    const actual = collectCounts(tsxSources, INVALID_SURFACE_PATTERN, () => true);
    expectDebtToMatch(actual, INVALID_SURFACE_DEBT, 'Invalid semantic utility');
  });

  it('prevents new raw white palette utilities in pages and domain components', () => {
    const actual = collectCounts(tsxSources, RAW_WHITE_PATTERN, isPageOrDomain);
    expectDebtToMatch(actual, RAW_WHITE_DEBT, 'Raw palette');
  });

  it('prevents raw Tailwind color scales in pages and domain components', () => {
    const actual = collectCounts(tsxSources, RAW_PALETTE_PATTERN, isPageOrDomain);
    expectDebtToMatch(actual, RAW_PALETTE_DEBT, 'Raw Tailwind palette');
  });

  it('reserves dashed borders for the intelligent-import drop zone', () => {
    const actual = collectCounts(tsxSources, /\bborder-dashed\b/g, isPageOrDomain);
    expect(actual).toEqual({ 'components/settings/IntelligentImport.tsx': 1 });
  });

  it('prevents new hardcoded overlay-level z-index utilities', () => {
    const actual = collectCounts(tsxSources, OVERLAY_Z_PATTERN, () => true);
    expectDebtToMatch(actual, OVERLAY_Z_DEBT, 'Overlay z-index');
  });

  it('prevents new page-prefixed classes outside their owning modules', () => {
    expectDebtToMatch(collectDomainClassDebt(), DOMAIN_CLASS_DEBT, 'Cross-module class');
  });

  it('keeps display text out of issue, error, and status comparisons', () => {
    const productionLogicSources = { ...tsSources, ...tsxSources };
    const actual = collectCounts(
      productionLogicSources,
      DISPLAY_TEXT_STATUS_LOGIC_PATTERN,
      () => true,
    );
    expect(actual).toEqual({});
  });
});
