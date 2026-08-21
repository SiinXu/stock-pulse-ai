// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  collectClassConstructionPrefixes,
  collectDefinedGlobalClassNames,
  collectUnreferencedGlobalClasses,
  diffGlobalCssClassLiveness,
  formatLivenessFindings,
  GENERIC_UNTRACKED_GLOBAL_CLASS_SET,
  sourceReferencesGlobalClass,
  type SuspectedDeadClass,
} from './globalCssClassLiveness';
import {
  assertNonEmptyProductionInventory,
  productionCssSources,
  productionTypeScriptSources,
} from './productionSourceInventory';

const INDEX_CSS_PATH = 'src/index.css';
const INDEX_HTML_PATH = 'index.html';

/**
 * Classes that remain in `index.css` but have no production className/cn/@apply
 * hit. Shrink-only: a new unreferenced class fails this guard, and an allowlist
 * entry that becomes referenced must be removed.
 */
const SUSPECTED_DEAD_ALLOWLIST: readonly SuspectedDeadClass[] = [
  {
    className: 'bg-primary-gradient',
    reason: 'Named only as a forbidden primary-CTA token in the design guard fixtures.',
  },
  {
    className: 'home-accent-chip',
    reason: 'Named only as a querySelector absence marker in report tests; not applied in production.',
  },
  {
    className: 'input-surface',
    reason: 'Input no longer applies the class; the rule still hosts optional-slot var() fallbacks tracked by the theme freeze debt list.',
  },
];

assertNonEmptyProductionInventory(productionTypeScriptSources, 'productionTypeScriptSources');
assertNonEmptyProductionInventory(productionCssSources, 'productionCssSources');

function isIndexCssPath(filename: string): boolean {
  return filename.endsWith('/index.css') || filename.endsWith('index.css');
}

function loadReferenceSources(): Record<string, string> {
  const sources: Record<string, string> = {};
  for (const [filename, raw] of Object.entries(productionTypeScriptSources)) {
    sources[filename] = raw;
  }
  for (const [filename, raw] of Object.entries(productionCssSources)) {
    if (isIndexCssPath(filename)) continue;
    sources[filename] = raw;
  }
  sources[INDEX_HTML_PATH] = fs.readFileSync(INDEX_HTML_PATH, 'utf8');
  return sources;
}

function collectPrefixes(sources: Record<string, string>): Set<string> {
  const prefixes = new Set<string>();
  for (const raw of Object.values(sources)) {
    for (const prefix of collectClassConstructionPrefixes(raw)) {
      prefixes.add(prefix);
    }
  }
  return prefixes;
}

describe('global CSS class liveness guard', () => {
  const indexCss = fs.readFileSync(INDEX_CSS_PATH, 'utf8');
  const definedClasses = collectDefinedGlobalClassNames(indexCss);
  const sources = loadReferenceSources();
  const constructionPrefixes = collectPrefixes(sources);
  const unreferenced = collectUnreferencedGlobalClasses({
    definedClasses,
    sources,
    constructionPrefixes,
    untracked: GENERIC_UNTRACKED_GLOBAL_CLASS_SET,
  });

  it('refuses to pass a vacuous class inventory', () => {
    expect(definedClasses.length).toBeGreaterThan(80);
    expect(Object.keys(sources).length).toBeGreaterThan(50);
  });

  it('treats CSS variables and longer class names as non-references', () => {
    expect(sourceReferencesGlobalClass('text-muted', 'color: var(--text-muted-text);', new Set())).toBe(false);
    expect(sourceReferencesGlobalClass('text-muted', 'className="text-muted-text"', new Set())).toBe(false);
    expect(sourceReferencesGlobalClass('settings-surface', 'bg-[var(--settings-surface)]', new Set())).toBe(false);
    expect(sourceReferencesGlobalClass('settings-border', 'className="settings-border"', new Set())).toBe(true);
  });

  it('treats className template prefixes as live constructed classes', () => {
    const source = '<span className={`backtest-status-chip backtest-status-chip-${tone}`} />';
    const prefixes = new Set(collectClassConstructionPrefixes(source));
    expect([...prefixes]).toEqual(['backtest-status-chip']);
    expect(sourceReferencesGlobalClass('backtest-status-chip-success', source, prefixes)).toBe(true);
    expect(sourceReferencesGlobalClass('backtest-status-chip-danger', '', prefixes)).toBe(true);
  });

  it('detects a newly unreferenced class in fixtures', () => {
    const findings = diffGlobalCssClassLiveness({
      unreferenced: ['ghost-panel'],
      allowlist: SUSPECTED_DEAD_ALLOWLIST,
    });
    expect(findings.some((finding) => finding.className === 'ghost-panel')).toBe(true);
  });

  it('fails closed when a suspected-dead allowlist entry is referenced again', () => {
    const findings = diffGlobalCssClassLiveness({
      unreferenced: SUSPECTED_DEAD_ALLOWLIST.slice(1).map((entry) => entry.className),
      allowlist: SUSPECTED_DEAD_ALLOWLIST,
    });
    expect(findings.some((finding) => (
      finding.className === 'bg-primary-gradient'
      && finding.reason.includes('now referenced')
    ))).toBe(true);
  });

  it('keeps unreferenced global classes on a shrink-only suspected-dead allowlist', () => {
    const findings = diffGlobalCssClassLiveness({
      unreferenced,
      allowlist: SUSPECTED_DEAD_ALLOWLIST,
    });
    expect(findings, formatLivenessFindings(findings)).toEqual([]);
    expect(unreferenced).toEqual(SUSPECTED_DEAD_ALLOWLIST.map((entry) => entry.className).sort());
  });
});
