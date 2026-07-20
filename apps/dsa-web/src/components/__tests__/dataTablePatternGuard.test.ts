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

const DATA_TABLE_OWNER = '../common/DataTable.tsx';

type PageTrack = 'TRACK-UI1' | 'TRACK-UI2' | 'TRACK-UI3';

type LegacyTableAllowance = {
  file: string;
  line: number;
  owner: PageTrack;
  removeBy: string;
};

const LEGACY_TABLE_ALLOWANCES: readonly LegacyTableAllowance[] = [
  { file: '../history/StockHistoryTrendDrawer.tsx', line: 297, owner: 'TRACK-UI1', removeBy: 'UI-R02' },
  { file: '../report/MarketReviewReportView.tsx', line: 536, owner: 'TRACK-UI1', removeBy: 'UI-R01' },
  { file: '../run-flow/RunFlowNodeDetails.tsx', line: 261, owner: 'TRACK-UI1', removeBy: 'UI-R03' },
  { file: '../settings/AiOverviewMatrix.tsx', line: 57, owner: 'TRACK-UI3', removeBy: 'UI-S02' },
  { file: '../../pages/StockScreeningPage.tsx', line: 1474, owner: 'TRACK-UI2', removeBy: 'UI-SCR01' },
  { file: '../../pages/TokenUsagePage.tsx', line: 281, owner: 'TRACK-UI1', removeBy: 'UI-U01' },
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

function findDataTableOwnershipViolations(filename: string, source: string): SourceFinding[] {
  const sourceFile = parseSource(filename, source);
  const findings: SourceFinding[] = [];
  const visit = (node: ts.Node): void => {
    const identifier = declaredIdentifier(node);
    if (identifier?.text === 'DataTable' && filename !== DATA_TABLE_OWNER) {
      findings.push({ file: filename, line: lineOf(sourceFile, identifier), token: 'DataTable' });
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

function isTableTag(node: ts.JsxTagNameExpression): boolean {
  return ts.isIdentifier(node) && node.text === 'table';
}

function isCreateElementTable(node: ts.CallExpression): boolean {
  const expression = node.expression;
  const isCreateElement = (
    ts.isIdentifier(expression) && expression.text === 'createElement'
  ) || (
    ts.isPropertyAccessExpression(expression) && expression.name.text === 'createElement'
  );
  const firstArgument = node.arguments[0];
  return isCreateElement
    && Boolean(firstArgument && ts.isStringLiteral(firstArgument) && firstArgument.text === 'table');
}

function semanticTableRole(node: ts.JsxOpeningLikeElement): string | undefined {
  const role = node.attributes.properties.find((property): property is ts.JsxAttribute => (
    ts.isJsxAttribute(property)
    && ts.isIdentifier(property.name)
    && property.name.text === 'role'
  ));
  if (!role?.initializer) return undefined;
  const expression = ts.isJsxExpression(role.initializer)
    ? role.initializer.expression
    : role.initializer;
  if (!expression || !ts.isStringLiteralLike(expression)) return undefined;
  return expression.text === 'table' || expression.text === 'grid'
    ? expression.text
    : undefined;
}

function findRawTables(filename: string, source: string): SourceFinding[] {
  const sourceFile = parseSource(filename, source);
  const findings: SourceFinding[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isJsxOpeningElement(node) && isTableTag(node.tagName)) {
      findings.push({ file: filename, line: lineOf(sourceFile, node), token: 'table' });
    } else if (ts.isJsxSelfClosingElement(node) && isTableTag(node.tagName)) {
      findings.push({ file: filename, line: lineOf(sourceFile, node), token: 'table' });
    } else if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const role = semanticTableRole(node);
      if (role) findings.push({ file: filename, line: lineOf(sourceFile, node), token: `role=${role}` });
    } else if (ts.isCallExpression(node) && isCreateElementTable(node)) {
      findings.push({ file: filename, line: lineOf(sourceFile, node), token: 'table' });
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

function findingKey(finding: SourceFinding): string {
  return `${finding.file}:${finding.line}:${finding.token}`;
}

describe('DataTable production guard', () => {
  it('rejects page-local DataTable implementations', () => {
    const source = 'const DataTable = () => null;';
    expect(findDataTableOwnershipViolations('../../pages/ExamplePage.tsx', source)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'DataTable' },
    ]);
  });

  it('keeps the shared DataTable implementation in its declared common owner', () => {
    const violations = Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename))
      .flatMap(([filename, source]) => findDataTableOwnershipViolations(filename, source));
    expect(violations).toEqual([]);
    expect(productionSources[DATA_TABLE_OWNER]).toMatch(/export const DataTable\s*=/);
    expect(findRawTables(DATA_TABLE_OWNER, productionSources[DATA_TABLE_OWNER])).toHaveLength(1);
  });

  it('rejects new JSX and createElement raw tables', () => {
    const source = [
      'const first = <table><tbody /></table>;',
      "const second = createElement('table', null);",
      "const third = React.createElement('table', null);",
      'const fourth = <div role="grid" />;',
      "const fifth = <div role={'table'} />;",
      'const sixth = <div role={`grid`} />;',
    ].join('\n');
    expect(findRawTables('../../pages/ExamplePage.tsx', source)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'table' },
      { file: '../../pages/ExamplePage.tsx', line: 2, token: 'table' },
      { file: '../../pages/ExamplePage.tsx', line: 3, token: 'table' },
      { file: '../../pages/ExamplePage.tsx', line: 4, token: 'role=grid' },
      { file: '../../pages/ExamplePage.tsx', line: 5, token: 'role=table' },
      { file: '../../pages/ExamplePage.tsx', line: 6, token: 'role=grid' },
    ]);
  });

  it('keeps legacy raw tables exact, consumable, and assigned to page tracks', () => {
    const actual = Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename) && filename !== DATA_TABLE_OWNER)
      .flatMap(([filename, source]) => findRawTables(filename, source))
      .map(findingKey)
      .sort();
    const allowed = LEGACY_TABLE_ALLOWANCES
      .map(({ file, line }) => findingKey({ file, line, token: 'table' }))
      .sort();

    expect(actual).toEqual(allowed);
    expect(new Set(allowed).size).toBe(allowed.length);
    for (const allowance of LEGACY_TABLE_ALLOWANCES) {
      expect(allowance.owner).toMatch(/^TRACK-UI[123]$/);
      expect(allowance.removeBy).toMatch(/^UI-[A-Z0-9]+$/);
      const source = productionSources[allowance.file];
      expect(source, `${allowance.file} must remain in the production scan`).toBeDefined();
      expect(source.split('\n')[allowance.line - 1]).toContain('<table');
    }
  });
});
