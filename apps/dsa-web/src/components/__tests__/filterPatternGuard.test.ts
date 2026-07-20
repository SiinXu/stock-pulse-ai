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

const FILTER_PATTERN_OWNERS = new Map<string, string>([
  ['AdvancedFilterSheet', '../common/AdvancedFilterSheet.tsx'],
  ['AppliedFilterChips', '../common/AppliedFilterChips.tsx'],
  ['FilterBar', '../common/FilterBar.tsx'],
  ['FilterChip', '../common/AppliedFilterChips.tsx'],
  ['useFilterQueryState', '../common/useFilterQueryState.ts'],
]);

type LegacyHistoryAllowance = {
  file: string;
  line: number;
  method: 'pushState' | 'replaceState';
  owner: 'TRACK-UI1' | 'TRACK-UI2' | 'TRACK-UI3';
  removeBy: string;
};

const LEGACY_HISTORY_ALLOWANCES: readonly LegacyHistoryAllowance[] = [
  {
    file: '../../pages/BacktestPage.tsx',
    line: 75,
    method: 'replaceState',
    owner: 'TRACK-UI2',
    removeBy: 'UI-BT01',
  },
  {
    file: '../../pages/DecisionSignalsPage.tsx',
    line: 256,
    method: 'replaceState',
    owner: 'TRACK-UI2',
    removeBy: 'UI-D01',
  },
  {
    file: '../../pages/StockScreeningPage.tsx',
    line: 102,
    method: 'replaceState',
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
  if (
    (ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node))
    && node.name
  ) {
    return node.name;
  }
  if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) {
    return node.name;
  }
  return undefined;
}

function findFilterPatternOwnershipViolations(filename: string, source: string): SourceFinding[] {
  const sourceFile = parseSource(filename, source);
  const findings: SourceFinding[] = [];
  const visit = (node: ts.Node): void => {
    const identifier = declaredIdentifier(node);
    if (identifier) {
      const expectedOwner = FILTER_PATTERN_OWNERS.get(identifier.text);
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

function findHistoryMutations(filename: string, source: string): SourceFinding[] {
  const sourceFile = parseSource(filename, source);
  const findings: SourceFinding[] = [];
  const visit = (node: ts.Node): void => {
    if (
      ts.isCallExpression(node)
      && ts.isPropertyAccessExpression(node.expression)
      && (node.expression.name.text === 'pushState' || node.expression.name.text === 'replaceState')
    ) {
      findings.push({
        file: filename,
        line: lineOf(sourceFile, node.expression.name),
        token: node.expression.name.text,
      });
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

function findingKey(finding: SourceFinding): string {
  return `${finding.file}:${finding.line}:${finding.token}`;
}

describe('filter pattern production guard', () => {
  it('rejects page-local copies of the shared Filter and Query authorities', () => {
    const fixture = [
      'const FilterBar = () => null;',
      'function useFilterQueryState() { return null; }',
    ].join('\n');
    expect(findFilterPatternOwnershipViolations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'FilterBar' },
      { file: '../../pages/ExamplePage.tsx', line: 2, token: 'useFilterQueryState' },
    ]);
  });

  it('keeps every shared Filter and Query implementation in its declared common owner', () => {
    const violations = Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename))
      .flatMap(([filename, source]) => findFilterPatternOwnershipViolations(filename, source));
    expect(violations).toEqual([]);

    for (const [symbol, owner] of FILTER_PATTERN_OWNERS) {
      const source = productionSources[owner];
      expect(source, `${owner} must remain in the production scan`).toBeDefined();
      expect(source).toMatch(new RegExp(`(?:const|function)\\s+${symbol}\\b`));
    }
  });

  it('rejects new direct history mutations, including mutations through an alias', () => {
    const fixture = [
      'window.history.replaceState({}, "", "?market=us");',
      'const historyAlias = window.history;',
      'historyAlias.pushState({}, "", "?market=cn");',
    ].join('\n');
    expect(findHistoryMutations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 3, token: 'pushState' },
    ]);
  });

  it('keeps legacy history mutations exact, consumable, and assigned to page tracks', () => {
    const actual = Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename))
      .flatMap(([filename, source]) => findHistoryMutations(filename, source))
      .map(findingKey)
      .sort();
    const allowed = LEGACY_HISTORY_ALLOWANCES
      .map(({ file, line, method }) => findingKey({ file, line, token: method }))
      .sort();

    expect(actual).toEqual(allowed);
    for (const allowance of LEGACY_HISTORY_ALLOWANCES) {
      expect(allowance.owner).toMatch(/^TRACK-UI[123]$/);
      expect(allowance.removeBy).toMatch(/^UI-[A-Z0-9]+$/);
      const source = productionSources[allowance.file];
      expect(source, `${allowance.file} must remain in the production scan`).toBeDefined();
      expect(source.split('\n')[allowance.line - 1]).toContain(`window.history.${allowance.method}`);
    }
  });
});
