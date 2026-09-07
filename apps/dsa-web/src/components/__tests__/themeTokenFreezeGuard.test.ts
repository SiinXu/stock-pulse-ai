// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  classifyThemeToken,
  DESKTOP_CHROME_TOKEN_OWNERS,
  THEME_COMPAT_ALIAS_VARS,
  THEME_CORE_CSS_VARS,
  THEME_LAYER0_CSS_VARS,
  THEME_LAYER1_CSS_VARS,
  THEME_LEGACY_PRICE_ALIASES,
  THEME_PAGE_SCOPED_PREFIXES,
} from '../../design/theme';
import {
  DESKTOP_CHROME_DEFINED_TOKENS,
  THEME_DEFINED_TOKEN_NAMES,
  THEME_PAGE_SCOPED_TOKEN_CEILING,
} from '../../design/themeTokenInventory';
import {
  classifyDefinedInventory,
  collectLocalStyleTokenDefinitions,
  diffThemeTokenFreeze,
  formatFreezeDiffs,
  frozenPageScopedTokenNames,
  uniqueDefinedCustomPropertyNames,
  type ThemeUngovernedReferenceDebt,
} from './themeTokenFreeze';
import {
  assertNonEmptyProductionInventory,
  productionCssSources,
  productionTypeScriptSources,
} from './productionSourceInventory';

const INDEX_CSS_PATH = 'src/index.css';
const TAILWIND_CONFIG_PATH = 'tailwind.config.js';

/**
 * Shrink-only undefined `var(--*)` sites. Lives in this `.test.ts` file so the
 * production design guard does not treat the helper module as a chromatic
 * consumer (`./themeTokenFreeze.ts` is not path-filtered as `__tests__`).
 */
const THEME_UNGOVERNED_REFERENCE_DEBT: readonly ThemeUngovernedReferenceDebt[] = [
  {
    token: '--bg-subtle-active',
    file: 'index.css',
    kind: 'undefined-ref',
    reason: 'Utility hover/active recipes reference an undefined derived token.',
  },
  {
    token: '--bg-subtle-hover',
    file: 'index.css',
    kind: 'undefined-ref',
    reason: 'Utility hover recipes reference an undefined derived token.',
  },
  {
    token: '--color-purple',
    file: 'tailwind.config.js',
    kind: 'undefined-ref',
    reason: 'Legacy glow-purple shadow maps to a token that was never defined.',
  },
  {
    token: '--home-border',
    file: 'components/report/ReportStrata.tsx',
    kind: 'undefined-ref',
    reason: 'Report strata uses a page-named token that does not exist in index.css.',
  },
  {
    token: '--info',
    file: 'components/charts/KlineChart.tsx',
    kind: 'undefined-ref',
    reason: 'Third MA stroke reads an undefined chart token instead of Layer 1.',
  },
  {
    token: '--input-surface-caret',
    file: 'index.css',
    kind: 'optional-fallback',
    reason: '.input-surface accepts an optional slot with a Layer 1 fallback.',
  },
  {
    token: '--input-surface-fill',
    file: 'index.css',
    kind: 'optional-fallback',
    reason: '.input-surface accepts an optional slot with a Layer 1 fallback.',
  },
  {
    token: '--input-surface-placeholder',
    file: 'index.css',
    kind: 'optional-fallback',
    reason: '.input-surface accepts an optional slot with a Layer 1 fallback.',
  },
  {
    token: '--input-surface-shadow',
    file: 'index.css',
    kind: 'optional-fallback',
    reason: '.input-surface accepts an optional slot with a Layer 1 fallback.',
  },
  {
    token: '--input-surface-text',
    file: 'index.css',
    kind: 'optional-fallback',
    reason: '.input-surface accepts an optional slot with a Layer 1 fallback.',
  },
];

function loadDesktopSources(): Record<string, string> {
  return Object.fromEntries(
    DESKTOP_CHROME_TOKEN_OWNERS.map((owner) => [owner, fs.readFileSync(owner, 'utf8')]),
  );
}

describe('theme token freeze guard', () => {
  assertNonEmptyProductionInventory(productionTypeScriptSources, 'productionTypeScriptSources');
  assertNonEmptyProductionInventory(productionCssSources, 'productionCssSources');

  const indexCss = fs.readFileSync(INDEX_CSS_PATH, 'utf8');
  const tailwindConfig = fs.readFileSync(TAILWIND_CONFIG_PATH, 'utf8');
  const desktopSources = loadDesktopSources();
  const productionSources = {
    ...productionCssSources,
    ...productionTypeScriptSources,
    [TAILWIND_CONFIG_PATH]: tailwindConfig,
  };

  it('keeps the classified index.css inventory exact and rejects ungoverned growth', () => {
    const diffs = diffThemeTokenFreeze({
      indexCss,
      productionSources,
      desktopSources,
      desktopBaseline: DESKTOP_CHROME_DEFINED_TOKENS,
      ungovernedReferenceDebt: THEME_UNGOVERNED_REFERENCE_DEBT,
    });
    expect(formatFreezeDiffs(diffs), formatFreezeDiffs(diffs)).toBe('');
    expect(uniqueDefinedCustomPropertyNames(indexCss)).toEqual([...THEME_DEFINED_TOKEN_NAMES]);
  });

  it('classifies every inventoried token and never promotes page leftovers to Layer 1', () => {
    const inventory = classifyDefinedInventory();
    expect(Object.keys(inventory)).toHaveLength(THEME_DEFINED_TOKEN_NAMES.length);
    expect(new Set(Object.values(inventory)).has('ungoverned')).toBe(false);

    for (const token of THEME_CORE_CSS_VARS) {
      expect(THEME_DEFINED_TOKEN_NAMES).toContain(token);
    }
    for (const token of THEME_LAYER0_CSS_VARS) {
      expect(classifyThemeToken(token)).toBe('layer0');
    }
    for (const token of THEME_LAYER1_CSS_VARS) {
      expect(classifyThemeToken(token)).toBe('layer1');
    }
    for (const token of THEME_LEGACY_PRICE_ALIASES) {
      expect(classifyThemeToken(token)).toBe('legacy-alias');
    }
    for (const token of THEME_COMPAT_ALIAS_VARS) {
      expect(classifyThemeToken(token)).toBe('compat-alias');
    }

    const pageScoped = frozenPageScopedTokenNames();
    expect(pageScoped.length).toBeGreaterThan(0);
    expect(pageScoped.length).toBeLessThanOrEqual(THEME_PAGE_SCOPED_TOKEN_CEILING);
    expect(pageScoped.length).toBe(THEME_PAGE_SCOPED_TOKEN_CEILING);
    for (const token of pageScoped) {
      expect(classifyThemeToken(token)).toBe('page-scoped-debt');
      expect(THEME_LAYER1_CSS_VARS).not.toContain(token);
    }
    expect(classifyThemeToken('--home-price-up')).toBe('legacy-alias');
    expect(classifyThemeToken('--home-new-tint')).toBe('page-scoped-debt');
    expect(classifyThemeToken('--wizard-bg')).toBe('ungoverned');
  });

  it('keeps unused Home loading-ring wrappers absent from definitions and inventory', () => {
    const unusedHomeLoadingRingWrappers = [
      '--home-loading-ring-head',
      '--home-loading-ring-track',
    ] as const;
    const definedNames = uniqueDefinedCustomPropertyNames(indexCss);
    for (const token of unusedHomeLoadingRingWrappers) {
      expect(definedNames, token).not.toContain(token);
      expect(THEME_DEFINED_TOKEN_NAMES, token).not.toContain(token);
    }
  });

  it('keeps unused Home divider wrapper absent from definitions and inventory', () => {
    const unusedHomeDividerWrapper = '--home-divider-border';
    const definedNames = uniqueDefinedCustomPropertyNames(indexCss);
    expect(definedNames, unusedHomeDividerWrapper).not.toContain(unusedHomeDividerWrapper);
    expect(THEME_DEFINED_TOKEN_NAMES, unusedHomeDividerWrapper).not.toContain(unusedHomeDividerWrapper);
  });

  it('keeps unused Home state-icon wrapper absent from definitions and inventory', () => {
    const unusedHomeStateIconWrapper = '--home-state-icon-muted';
    const definedNames = uniqueDefinedCustomPropertyNames(indexCss);
    expect(definedNames, unusedHomeStateIconWrapper).not.toContain(unusedHomeStateIconWrapper);
    expect(THEME_DEFINED_TOKEN_NAMES, unusedHomeStateIconWrapper).not.toContain(unusedHomeStateIconWrapper);
  });

  it('keeps unused Home secondary-accent wrapper absent from definitions and inventory', () => {
    const unusedHomeSecondaryAccentWrapper = '--home-secondary-accent-text';
    const definedNames = uniqueDefinedCustomPropertyNames(indexCss);
    expect(definedNames, unusedHomeSecondaryAccentWrapper).not.toContain(unusedHomeSecondaryAccentWrapper);
    expect(THEME_DEFINED_TOKEN_NAMES, unusedHomeSecondaryAccentWrapper).not.toContain(unusedHomeSecondaryAccentWrapper);
  });

  it('keeps unused Home accent-bg-hover wrapper absent from definitions and inventory', () => {
    const unusedHomeAccentBgHoverWrapper = '--home-accent-bg-hover';
    const definedNames = uniqueDefinedCustomPropertyNames(indexCss);
    expect(definedNames, unusedHomeAccentBgHoverWrapper).not.toContain(unusedHomeAccentBgHoverWrapper);
    expect(THEME_DEFINED_TOKEN_NAMES, unusedHomeAccentBgHoverWrapper).not.toContain(unusedHomeAccentBgHoverWrapper);
  });

  it('keeps unused Home accent-border-hover wrapper absent from definitions and inventory', () => {
    const unusedHomeAccentBorderHoverWrapper = '--home-accent-border-hover';
    const definedNames = uniqueDefinedCustomPropertyNames(indexCss);
    expect(definedNames, unusedHomeAccentBorderHoverWrapper).not.toContain(unusedHomeAccentBorderHoverWrapper);
    expect(THEME_DEFINED_TOKEN_NAMES, unusedHomeAccentBorderHoverWrapper).not.toContain(unusedHomeAccentBorderHoverWrapper);
  });

  it('keeps unused Home hero-border wrapper absent from definitions and inventory', () => {
    const unusedHomeHeroBorderWrapper = '--home-hero-border';
    const definedNames = uniqueDefinedCustomPropertyNames(indexCss);
    expect(definedNames, unusedHomeHeroBorderWrapper).not.toContain(unusedHomeHeroBorderWrapper);
    expect(THEME_DEFINED_TOKEN_NAMES, unusedHomeHeroBorderWrapper).not.toContain(unusedHomeHeroBorderWrapper);
  });

  it('keeps unused Home hero-gradient-start wrapper absent from definitions and inventory', () => {
    const unusedHomeHeroGradientStartWrapper = '--home-hero-gradient-start';
    const definedNames = uniqueDefinedCustomPropertyNames(indexCss);
    expect(definedNames, unusedHomeHeroGradientStartWrapper).not.toContain(unusedHomeHeroGradientStartWrapper);
    expect(THEME_DEFINED_TOKEN_NAMES, unusedHomeHeroGradientStartWrapper).not.toContain(unusedHomeHeroGradientStartWrapper);
  });

  it('keeps unused Home hero-gradient-mid wrapper absent from definitions and inventory', () => {
    const unusedHomeHeroGradientMidWrapper = '--home-hero-gradient-mid';
    const definedNames = uniqueDefinedCustomPropertyNames(indexCss);
    expect(definedNames, unusedHomeHeroGradientMidWrapper).not.toContain(unusedHomeHeroGradientMidWrapper);
    expect(THEME_DEFINED_TOKEN_NAMES, unusedHomeHeroGradientMidWrapper).not.toContain(unusedHomeHeroGradientMidWrapper);
  });

  it('keeps unused Home hero-gradient-end wrapper absent from definitions and inventory', () => {
    const unusedHomeHeroGradientEndWrapper = '--home-hero-gradient-end';
    const definedNames = uniqueDefinedCustomPropertyNames(indexCss);
    expect(definedNames, unusedHomeHeroGradientEndWrapper).not.toContain(unusedHomeHeroGradientEndWrapper);
    expect(THEME_DEFINED_TOKEN_NAMES, unusedHomeHeroGradientEndWrapper).not.toContain(unusedHomeHeroGradientEndWrapper);
  });

  it('accounts for light/dark, price-direction, charts, aliases, and desktop chrome', () => {
    expect(indexCss).toMatch(/:root\s*\{/);
    expect(indexCss).toMatch(/^\.dark\s*\{/m);
    expect(indexCss).toContain('[data-price-direction="cn"]');
    expect(indexCss).toContain('[data-price-direction="us"]');
    expect(indexCss).toContain('--price-up:');
    expect(indexCss).toContain('--price-down:');
    expect(indexCss).toMatch(/--home-price-up\s*:\s*var\(--price-red\)/);
    expect(indexCss).toMatch(/--home-price-down\s*:\s*var\(--price-green\)/);
    const klineSource = productionTypeScriptSources['../../components/charts/KlineChart.tsx']
      ?? productionTypeScriptSources['../charts/KlineChart.tsx']
      ?? fs.readFileSync('src/components/charts/KlineChart.tsx', 'utf8');
    expect(klineSource).toContain('var(--info)');
    expect(tailwindConfig).toContain('var(--color-purple)');
    expect(DESKTOP_CHROME_DEFINED_TOKENS.assistant).toContain('--bg');
    expect(DESKTOP_CHROME_DEFINED_TOKENS.loading).toContain('--panel');
    expect(THEME_DEFINED_TOKEN_NAMES).not.toContain('--bg');
    expect(THEME_DEFINED_TOKEN_NAMES).not.toContain('--panel');
    expect(THEME_PAGE_SCOPED_PREFIXES).toEqual([
      'home',
      'settings',
      'login',
      'chat',
      'backtest',
      'portfolio',
    ]);
  });

  it('records undefined semantic bypasses as shrink-only debt', () => {
    const tokens = THEME_UNGOVERNED_REFERENCE_DEBT.map((entry) => entry.token).sort();
    expect(tokens).toEqual([
      '--bg-subtle-active',
      '--bg-subtle-hover',
      '--color-purple',
      '--home-border',
      '--info',
      '--input-surface-caret',
      '--input-surface-fill',
      '--input-surface-placeholder',
      '--input-surface-shadow',
      '--input-surface-text',
    ]);
    for (const entry of THEME_UNGOVERNED_REFERENCE_DEBT) {
      expect(THEME_DEFINED_TOKEN_NAMES, entry.token).not.toContain(entry.token);
    }
  });

  it('allows local overrides of inventoried tokens and rejects new local names', () => {
    const inputSource = productionTypeScriptSources['../../components/common/Input.tsx']
      ?? productionTypeScriptSources['../common/Input.tsx']
      ?? fs.readFileSync('src/components/common/Input.tsx', 'utf8');
    const allowed = collectLocalStyleTokenDefinitions(
      '../../components/common/Input.tsx',
      inputSource,
    );
    expect(allowed.map((finding) => finding.token).sort()).toEqual([
      '--input-surface-border-focus',
      '--input-surface-focus-ring',
    ]);
    const leak = collectLocalStyleTokenDefinitions(
      '../../pages/ExamplePage.tsx',
      "const style = { ['--wizard-accent' as string]: 'red' };",
    );
    expect(leak.map((finding) => finding.token)).toEqual(['--wizard-accent']);
  });

  it('detects contract violations in fixtures without expanding production debt', () => {
    const newToken = diffThemeTokenFreeze({
      indexCss: `${indexCss}\n:root { --wizard-bg: 0 0% 50%; }\n`,
      productionSources,
      desktopSources,
      desktopBaseline: DESKTOP_CHROME_DEFINED_TOKENS,
      ungovernedReferenceDebt: THEME_UNGOVERNED_REFERENCE_DEBT,
    });
    expect(newToken.some((diff) => diff.code === 'new-defined-token' && diff.token === '--wizard-bg')).toBe(true);
    expect(newToken.some((diff) => diff.code === 'ungoverned-defined-token' && diff.token === '--wizard-bg')).toBe(true);

    const pageGrowth = diffThemeTokenFreeze({
      indexCss: `${indexCss}\n:root { --home-new-tint: hsl(var(--primary) / 0.2); }\n`,
      productionSources,
      desktopSources,
      desktopBaseline: DESKTOP_CHROME_DEFINED_TOKENS,
      ungovernedReferenceDebt: THEME_UNGOVERNED_REFERENCE_DEBT,
    });
    expect(pageGrowth.some((diff) => diff.code === 'new-defined-token' && diff.token === '--home-new-tint')).toBe(true);
    expect(pageGrowth.some((diff) => diff.code === 'page-scoped-growth' && diff.token === '--home-new-tint')).toBe(true);

    const outside = diffThemeTokenFreeze({
      indexCss,
      productionSources: {
        ...productionSources,
        '../../pages/ExamplePage.tsx': 'const rules = `--chat-new-glow: red;`;',
      },
      desktopSources,
      desktopBaseline: DESKTOP_CHROME_DEFINED_TOKENS,
      ungovernedReferenceDebt: THEME_UNGOVERNED_REFERENCE_DEBT,
    });
    expect(outside.some((diff) => diff.code === 'outside-definition' && diff.token === '--chat-new-glow')).toBe(true);

    const localStyleOutside = diffThemeTokenFreeze({
      indexCss,
      productionSources: {
        ...productionSources,
        '../../pages/ExamplePage.tsx': "const style = { ['--wizard-accent' as string]: 'red' };",
      },
      desktopSources,
      desktopBaseline: DESKTOP_CHROME_DEFINED_TOKENS,
      ungovernedReferenceDebt: THEME_UNGOVERNED_REFERENCE_DEBT,
    });
    expect(localStyleOutside.some((diff) => (
      diff.code === 'outside-definition' && diff.token === '--wizard-accent'
    ))).toBe(true);

    const ungovernedRef = diffThemeTokenFreeze({
      indexCss,
      productionSources: {
        ...productionSources,
        '../../components/charts/ExampleChart.tsx': "const stroke = 'hsl(var(--chart-7))';",
      },
      desktopSources,
      desktopBaseline: DESKTOP_CHROME_DEFINED_TOKENS,
      ungovernedReferenceDebt: THEME_UNGOVERNED_REFERENCE_DEBT,
    });
    expect(ungovernedRef.some((diff) => (
      diff.code === 'new-ungoverned-reference' && diff.token === '--chart-7'
    ))).toBe(true);

    const desktopGrowth = diffThemeTokenFreeze({
      indexCss,
      productionSources,
      desktopSources: {
        ...desktopSources,
        [DESKTOP_CHROME_TOKEN_OWNERS[0]]: `${desktopSources[DESKTOP_CHROME_TOKEN_OWNERS[0]]}\n:root { --assistant-glow: #0ff; }\n`,
      },
      desktopBaseline: DESKTOP_CHROME_DEFINED_TOKENS,
      ungovernedReferenceDebt: THEME_UNGOVERNED_REFERENCE_DEBT,
    });
    expect(desktopGrowth.some((diff) => (
      diff.code === 'desktop-token-growth' && diff.token === '--assistant-glow'
    ))).toBe(true);

    const staleDebt = diffThemeTokenFreeze({
      indexCss,
      productionSources: Object.fromEntries(
        Object.entries(productionSources).map(([file, raw]) => [
          file,
          raw.replaceAll('var(--info)', 'var(--primary)'),
        ]),
      ),
      desktopSources,
      desktopBaseline: DESKTOP_CHROME_DEFINED_TOKENS,
      ungovernedReferenceDebt: THEME_UNGOVERNED_REFERENCE_DEBT,
    });
    expect(staleDebt.some((diff) => (
      diff.code === 'stale-ungoverned-reference' && diff.token === '--info'
    ))).toBe(true);
  });

  it('fails closed when the inventory file is missing from disk', () => {
    expect(fs.existsSync('src/design/themeTokenInventory.ts')).toBe(true);
    // Non-vacuity floor only. Phase 2 domain collapses (login/backtest/
    // portfolio/chat/settings/home-action/home-prose) shrank the defined
    // inventory below 170.
    expect(THEME_DEFINED_TOKEN_NAMES.length).toBeGreaterThan(151);
    expect(() => {
      if (THEME_DEFINED_TOKEN_NAMES.length === 0) {
        throw new Error('theme token inventory is empty; refusing to pass a vacuous freeze.');
      }
    }).not.toThrow();
  });
});
