// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import {
  classifyThemeToken,
  THEME_PAGE_SCOPED_PREFIXES,
  type ThemeTokenClass,
} from '../../design/theme';
import { THEME_DEFINED_TOKEN_NAMES } from '../../design/themeTokenInventory';

export type ThemeUngovernedReferenceKind = 'undefined-ref' | 'optional-fallback';

export type ThemeUngovernedReferenceDebt = {
  token: string;
  file: string;
  kind: ThemeUngovernedReferenceKind;
  reason: string;
};

export type ThemeTokenFinding = {
  file: string;
  line: number;
  token: string;
  detail: string;
};

export type ThemeTokenFreezeDiff = {
  code:
    | 'new-defined-token'
    | 'stale-defined-token'
    | 'ungoverned-defined-token'
    | 'page-scoped-growth'
    | 'stale-page-scoped-token'
    | 'outside-definition'
    | 'new-ungoverned-reference'
    | 'stale-ungoverned-reference'
    | 'blessed-page-token'
    | 'desktop-token-growth'
    | 'stale-desktop-token';
  file: string;
  token: string;
  detail: string;
};

const DEFINED_NAME_SET = new Set<string>(THEME_DEFINED_TOKEN_NAMES);
const CUSTOM_PROPERTY_DEFINITION = /(--[a-zA-Z][\w-]*)\s*:/g;
const CUSTOM_PROPERTY_REFERENCE = /var\(\s*(--[a-zA-Z][\w-]*)/g;
const LOCAL_STYLE_DEFINITION = /(?:['"](--[a-zA-Z][\w-]*)['"](?:\s+as\s+[\w.]+)?\s*\]?\s*:|(?:setProperty)\(\s*['"](--[a-zA-Z][\w-]*)['"])/g;

export function maskCssAndScriptComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/gm, (comment) => comment.replace(/[^\n]/g, ' '));
}

export function lineOf(source: string, index: number): number {
  return source.slice(0, index).split('\n').length;
}

export function collectDefinedCustomProperties(
  file: string,
  raw: string,
): ThemeTokenFinding[] {
  const source = maskCssAndScriptComments(raw);
  const findings: ThemeTokenFinding[] = [];
  for (const match of source.matchAll(CUSTOM_PROPERTY_DEFINITION)) {
    const token = match[1] ?? '';
    findings.push({
      file,
      line: lineOf(source, match.index ?? 0),
      token,
      detail: 'definition',
    });
  }
  return findings;
}

export function uniqueDefinedCustomPropertyNames(raw: string): string[] {
  return [...new Set(collectDefinedCustomProperties('index.css', raw).map((finding) => finding.token))]
    .sort();
}

export function collectCustomPropertyReferences(
  file: string,
  raw: string,
): ThemeTokenFinding[] {
  const source = maskCssAndScriptComments(raw);
  const findings: ThemeTokenFinding[] = [];
  for (const match of source.matchAll(CUSTOM_PROPERTY_REFERENCE)) {
    const token = match[1] ?? '';
    findings.push({
      file,
      line: lineOf(source, match.index ?? 0),
      token,
      detail: 'reference',
    });
  }
  return findings;
}

export function collectLocalStyleTokenDefinitions(
  file: string,
  raw: string,
): ThemeTokenFinding[] {
  const source = maskCssAndScriptComments(raw);
  const findings: ThemeTokenFinding[] = [];
  for (const match of source.matchAll(LOCAL_STYLE_DEFINITION)) {
    const token = match[1] ?? match[2] ?? '';
    findings.push({
      file,
      line: lineOf(source, match.index ?? 0),
      token,
      detail: 'local-definition',
    });
  }
  return findings;
}

export function findDefinitionsOutsideIndex(
  sources: Record<string, string>,
): ThemeTokenFinding[] {
  const findings: ThemeTokenFinding[] = [];
  for (const [file, raw] of Object.entries(sources)) {
    if (file.endsWith('/index.css') || file === 'index.css' || file.endsWith('index.css')) {
      continue;
    }
    for (const finding of collectDefinedCustomProperties(file, raw)) {
      findings.push({
        ...finding,
        detail: 'defined-outside-index.css',
      });
    }
    for (const finding of collectLocalStyleTokenDefinitions(file, raw)) {
      if (DEFINED_NAME_SET.has(finding.token)) continue;
      findings.push({
        ...finding,
        detail: 'defined-outside-index.css',
      });
    }
  }
  return findings;
}

/** Align with themeContractGuard: glob keys from `src/components/__tests__/`. */
export function inventoryRelativeFile(file: string): string {
  if (file === 'index.css' || file.endsWith('/index.css') || file.endsWith('src/index.css')) {
    return 'index.css';
  }
  if (file.endsWith('tailwind.config.js') || file === 'tailwind.config.js') {
    return 'tailwind.config.js';
  }
  const srcIndex = file.lastIndexOf('src/');
  if (srcIndex >= 0) return file.slice(srcIndex + 'src/'.length);
  if (file.startsWith('../../')) return file.slice('../../'.length);
  if (file.startsWith('../')) return `components/${file.slice('../'.length)}`;
  return file;
}

export function collectUngovernedReferences(
  sources: Record<string, string>,
): ThemeTokenFinding[] {
  const findings: ThemeTokenFinding[] = [];
  for (const [file, raw] of Object.entries(sources)) {
    for (const finding of collectCustomPropertyReferences(file, raw)) {
      if (DEFINED_NAME_SET.has(finding.token)) continue;
      findings.push({
        ...finding,
        file: inventoryRelativeFile(file),
        detail: 'undefined-reference',
      });
    }
  }
  return findings;
}

export function frozenPageScopedTokenNames(): string[] {
  return THEME_DEFINED_TOKEN_NAMES.filter((token) => classifyThemeToken(token) === 'page-scoped-debt');
}

export function classifyDefinedInventory(): Record<string, ThemeTokenClass> {
  return Object.fromEntries(
    THEME_DEFINED_TOKEN_NAMES.map((token) => [token, classifyThemeToken(token)]),
  );
}

function debtKey(entry: Pick<ThemeUngovernedReferenceDebt, 'token' | 'file'>): string {
  return `${entry.file}::${entry.token}`;
}

export function diffThemeTokenFreeze(input: {
  indexCss: string;
  productionSources: Record<string, string>;
  desktopSources: Record<string, string>;
  desktopBaseline: Record<string, readonly string[]>;
  ungovernedReferenceDebt: readonly ThemeUngovernedReferenceDebt[];
}): ThemeTokenFreezeDiff[] {
  const diffs: ThemeTokenFreezeDiff[] = [];
  const measuredNames = uniqueDefinedCustomPropertyNames(input.indexCss);
  const measuredSet = new Set(measuredNames);
  const inventorySet = new Set<string>(THEME_DEFINED_TOKEN_NAMES);

  for (const token of measuredNames) {
    if (!inventorySet.has(token)) {
      diffs.push({
        code: 'new-defined-token',
        file: 'index.css',
        token,
        detail: `New custom property ${token} is not in THEME_DEFINED_TOKEN_NAMES. Follow the addition workflow in src/design/theme.ts; do not add page-scoped names.`,
      });
    }
    const tokenClass = classifyThemeToken(token);
    if (tokenClass === 'ungoverned') {
      diffs.push({
        code: 'ungoverned-defined-token',
        file: 'index.css',
        token,
        detail: `${token} is defined but classifyThemeToken() returned ungoverned. Add an explicit class before landing it.`,
      });
    }
  }

  for (const token of THEME_DEFINED_TOKEN_NAMES) {
    if (!measuredSet.has(token)) {
      diffs.push({
        code: 'stale-defined-token',
        file: 'src/design/themeTokenInventory.ts',
        token,
        detail: `${token} is inventoried but no longer defined in index.css. Remove it from the inventory in the same PR.`,
      });
    }
  }

  const measuredPageScoped = measuredNames.filter((token) => classifyThemeToken(token) === 'page-scoped-debt');
  const frozenPageScoped = frozenPageScopedTokenNames();
  const frozenPageSet = new Set(frozenPageScoped);
  for (const token of measuredPageScoped) {
    if (!frozenPageSet.has(token)) {
      diffs.push({
        code: 'page-scoped-growth',
        file: 'index.css',
        token,
        detail: `New page-scoped token ${token}. Phase 0 forbids new --${THEME_PAGE_SCOPED_PREFIXES.join('/--')}- names.`,
      });
    }
  }
  for (const token of frozenPageScoped) {
    if (!measuredSet.has(token)) {
      diffs.push({
        code: 'stale-page-scoped-token',
        file: 'src/design/themeTokenInventory.ts',
        token,
        detail: `${token} left the tree. Remove it from the inventory; do not reclassify leftover page tokens as Layer 1.`,
      });
    }
  }

  for (const finding of findDefinitionsOutsideIndex(input.productionSources)) {
    diffs.push({
      code: 'outside-definition',
      file: finding.file,
      token: finding.token,
      detail: 'Web custom properties may be defined only in src/index.css.',
    });
  }

  const measuredRefs = collectUngovernedReferences({
    ...input.productionSources,
    'index.css': input.indexCss,
  });
  const measuredRefKeys = new Set(measuredRefs.map((finding) => debtKey({
    token: finding.token,
    file: finding.file,
  })));
  const debtKeys = new Set(input.ungovernedReferenceDebt.map(debtKey));

  for (const finding of measuredRefs) {
    if (!debtKeys.has(debtKey(finding))) {
      diffs.push({
        code: 'new-ungoverned-reference',
        file: finding.file,
        token: finding.token,
        detail: `${finding.token} is referenced but not defined in index.css. Use a Layer 1 token or add a reviewed definition; do not grow ungoverned var() debt.`,
      });
    }
  }
  for (const entry of input.ungovernedReferenceDebt) {
    if (!measuredRefKeys.has(debtKey(entry))) {
      diffs.push({
        code: 'stale-ungoverned-reference',
        file: 'src/components/__tests__/themeTokenFreeze.ts',
        token: entry.token,
        detail: `${entry.token} in ${entry.file} is gone. Shrink THEME_UNGOVERNED_REFERENCE_DEBT; do not keep a blessed hole.`,
      });
    }
  }

  for (const token of THEME_DEFINED_TOKEN_NAMES) {
    if (
      isPageScopedBlessedAsPublic(token)
    ) {
      diffs.push({
        code: 'blessed-page-token',
        file: 'src/design/theme.ts',
        token,
        detail: `${token} matches a frozen page prefix but is classified as ${classifyThemeToken(token)}. Keep it as page-scoped-debt or legacy-alias.`,
      });
    }
  }

  for (const [owner, raw] of Object.entries(input.desktopSources)) {
    const measured = uniqueDefinedCustomPropertyNames(raw);
    const baselineKey = desktopBaselineKey(owner);
    const baseline = new Set(input.desktopBaseline[baselineKey] ?? input.desktopBaseline[owner] ?? []);
    for (const token of measured) {
      if (!baseline.has(token)) {
        diffs.push({
          code: 'desktop-token-growth',
          file: owner,
          token,
          detail: 'Desktop chrome tokens are a separate isolated inventory. Do not grow them without an explicit inventory update, and do not copy them into Web Layer 1.',
        });
      }
    }
    for (const token of input.desktopBaseline[baselineKey] ?? input.desktopBaseline[owner] ?? []) {
      if (!measured.includes(token)) {
        diffs.push({
          code: 'stale-desktop-token',
          file: owner,
          token,
          detail: `${token} left the desktop chrome surface. Shrink DESKTOP_CHROME_DEFINED_TOKENS.`,
        });
      }
    }
  }

  return diffs;
}

function desktopBaselineKey(owner: string): string {
  const base = owner.split('/').pop() ?? owner;
  if (base.startsWith('assistant')) return 'assistant';
  if (base.startsWith('loading')) return 'loading';
  return owner;
}

function isPageScopedBlessedAsPublic(token: string): boolean {
  if (!token.startsWith('--')) return false;
  const isPage = THEME_PAGE_SCOPED_PREFIXES.some((prefix) => token.startsWith(`--${prefix}-`));
  if (!isPage) return false;
  const tokenClass = classifyThemeToken(token);
  return tokenClass !== 'page-scoped-debt' && tokenClass !== 'legacy-alias';
}

export function formatFreezeDiffs(diffs: readonly ThemeTokenFreezeDiff[]): string {
  return diffs
    .map((diff) => `${diff.code} ${diff.file} ${diff.token}: ${diff.detail}`)
    .join('\n');
}
