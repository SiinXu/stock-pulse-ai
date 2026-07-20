// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const productionTs = import.meta.glob('../../**/*.ts', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>;
const productionTsx = import.meta.glob('../../**/*.tsx', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>;
const productionSources = { ...productionTs, ...productionTsx };

const PAGE_PATTERN_OWNERS = new Map<string, string>([
  ['AppPage', '../common/AppPage.tsx'],
  ['PageHeader', '../common/PageHeader.tsx'],
  ['ResponsiveRail', '../common/ResponsiveRail.tsx'],
  ['SummaryStrip', '../common/SummaryStrip.tsx'],
  ['TabPanel', '../common/Tabs.tsx'],
  ['Tabs', '../common/Tabs.tsx'],
  ['Toolbar', '../common/Toolbar.tsx'],
  ['WorkspaceNavigation', '../common/WorkspaceNavigation.tsx'],
  ['WorkspacePage', '../common/WorkspacePage.tsx'],
  ['RouteFocusCoordinator', '../routing/RouteFocusCoordinator.tsx'],
  ['useRouteFocusTarget', '../../hooks/useRouteFocusTarget.ts'],
]);

type HistoryMethod = 'pushState' | 'replaceState';
type LegacyHistoryAllowance = {
  file: string;
  method: HistoryMethod;
  count: number;
  owner: 'TRACK-UI1' | 'TRACK-UI2' | 'TRACK-UI3';
  removeBy: string;
};

const LEGACY_HISTORY_ALLOWANCES: readonly LegacyHistoryAllowance[] = [
  {
    file: '../../pages/BacktestPage.tsx',
    method: 'replaceState',
    count: 1,
    owner: 'TRACK-UI2',
    removeBy: 'UI-BT01',
  },
  {
    file: '../../pages/DecisionSignalsPage.tsx',
    method: 'replaceState',
    count: 1,
    owner: 'TRACK-UI2',
    removeBy: 'UI-D01',
  },
  {
    file: '../../pages/StockScreeningPage.tsx',
    method: 'replaceState',
    count: 1,
    owner: 'TRACK-UI2',
    removeBy: 'UI-SCR01',
  },
];

type SourceFinding = {
  file: string;
  line: number;
  token: string;
};

function isProductionSource(filename: string): boolean {
  return !filename.includes('/__tests__/')
    && !filename.includes('/fixtures/')
    && !filename.includes('/generated/')
    && !/\.(?:test|spec)\.[jt]sx?$/.test(filename);
}

function parseSource(filename: string, source: string): ts.SourceFile {
  return ts.createSourceFile(
    filename,
    source,
    ts.ScriptTarget.Latest,
    true,
    filename.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
}

function lineOf(sourceFile: ts.SourceFile, node: ts.Node): number {
  return sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
}

function declaredIdentifier(node: ts.Node): ts.Identifier | undefined {
  if ((ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node)) && node.name) {
    return node.name;
  }
  if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) return node.name;
  return undefined;
}

function findPatternOwnershipViolations(filename: string, source: string): SourceFinding[] {
  const sourceFile = parseSource(filename, source);
  const findings: SourceFinding[] = [];
  const visit = (node: ts.Node): void => {
    const identifier = declaredIdentifier(node);
    if (identifier) {
      const expectedOwner = PAGE_PATTERN_OWNERS.get(identifier.text);
      if (expectedOwner && expectedOwner !== filename) {
        findings.push({
          file: filename,
          line: lineOf(sourceFile, identifier),
          token: identifier.text,
        });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

function historyMethod(node: ts.Expression): HistoryMethod | undefined {
  if (ts.isIdentifier(node) && (node.text === 'pushState' || node.text === 'replaceState')) {
    return node.text;
  }
  if (ts.isPropertyAccessExpression(node) && (node.name.text === 'pushState' || node.name.text === 'replaceState')) {
    return node.name.text;
  }
  if (ts.isElementAccessExpression(node) && ts.isStringLiteral(node.argumentExpression)) {
    const method = node.argumentExpression.text;
    if (method === 'pushState' || method === 'replaceState') return method;
  }
  return undefined;
}

function findHistoryMutations(filename: string, source: string): SourceFinding[] {
  const sourceFile = parseSource(filename, source);
  const findings: SourceFinding[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node)) {
      const method = historyMethod(node.expression);
      if (method) {
        findings.push({
          file: filename,
          line: lineOf(sourceFile, node.expression),
          token: method,
        });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

function historyCountKey(file: string, method: string): string {
  return `${file}:${method}`;
}

describe('page and Router pattern production guard', () => {
  it('rejects page-local copies of shared page Patterns', () => {
    const fixture = [
      'const WorkspacePage = () => null;',
      'function useRouteFocusTarget() { return undefined; }',
    ].join('\n');

    expect(findPatternOwnershipViolations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'WorkspacePage' },
      { file: '../../pages/ExamplePage.tsx', line: 2, token: 'useRouteFocusTarget' },
    ]);
  });

  it('keeps every page and Router Pattern in its declared owner', () => {
    const violations = Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename))
      .flatMap(([filename, source]) => findPatternOwnershipViolations(filename, source));
    expect(violations).toEqual([]);

    for (const [symbol, owner] of PAGE_PATTERN_OWNERS) {
      const source = productionSources[owner];
      expect(source, `${owner} must remain in the production scan`).toBeDefined();
      expect(source).toMatch(new RegExp(`(?:const|function)\\s+${symbol}\\b`));
    }
  });

  it('detects direct history mutations through properties, aliases, and computed access', () => {
    const fixture = [
      'window.history.replaceState({}, "", "?market=us");',
      'const historyAlias = window.history;',
      'historyAlias.pushState({}, "", "?market=cn");',
      'historyAlias["replaceState"]({}, "", "?market=hk");',
      'const { pushState } = historyAlias; pushState({}, "", "?market=us");',
    ].join('\n');

    expect(findHistoryMutations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 3, token: 'pushState' },
      { file: '../../pages/ExamplePage.tsx', line: 4, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 5, token: 'pushState' },
    ]);
  });

  it('allows only the exact file/method/count migration inventory without line pinning', () => {
    const actual = Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename))
      .flatMap(([filename, source]) => findHistoryMutations(filename, source));
    const actualCounts = new Map<string, number>();
    for (const finding of actual) {
      const key = historyCountKey(finding.file, finding.token);
      actualCounts.set(key, (actualCounts.get(key) ?? 0) + 1);
    }
    const allowedCounts = new Map(
      LEGACY_HISTORY_ALLOWANCES.map(({ file, method, count }) => [historyCountKey(file, method), count]),
    );

    expect([...actualCounts.entries()].sort()).toEqual([...allowedCounts.entries()].sort());
    for (const allowance of LEGACY_HISTORY_ALLOWANCES) {
      expect(allowance.owner).toMatch(/^TRACK-UI[123]$/);
      expect(allowance.removeBy).toMatch(/^UI-[A-Z0-9]+$/);
      expect(productionSources[allowance.file], `${allowance.file} must remain in the production scan`).toBeDefined();
    }
  });

  it('keeps route-focus metadata memory-only and outside public target input', () => {
    const coordinator = productionSources['../routing/RouteFocusCoordinator.tsx'];
    const context = productionSources['../routing/routeFocusContext.ts'];
    expect(coordinator).toBeDefined();
    expect(context).toBeDefined();
    expect(coordinator).not.toMatch(/(?:local|session)Storage/);
    expect(coordinator).not.toMatch(/history\s*\.\s*(?:pushState|replaceState)/);
    expect(context).toMatch(/interface RouteFocusTarget\s*\{[\s\S]*routeId:[\s\S]*headingRef:[\s\S]*ready:/);
    expect(context).not.toMatch(/focusKey|navigationType|locationKey|historyEntry/);
  });
});
