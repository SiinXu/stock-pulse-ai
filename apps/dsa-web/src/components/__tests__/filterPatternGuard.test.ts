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

});
