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

const SELECTION_CHIP_OWNER = '../common/SelectionChip.tsx';

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

function findSelectionChipDeclarations(filename: string, source: string): SourceFinding[] {
  const sourceFile = parseSource(filename, source);
  const findings: SourceFinding[] = [];
  const visit = (node: ts.Node): void => {
    const identifier = declaredIdentifier(node);
    if (identifier?.text === 'SelectionChip' && filename !== SELECTION_CHIP_OWNER) {
      findings.push({ file: filename, line: lineOf(sourceFile, identifier), token: 'SelectionChip' });
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

function staticAttributeValue(attribute: ts.JsxAttribute): string | undefined {
  if (!attribute.initializer) return undefined;
  const expression = ts.isJsxExpression(attribute.initializer)
    ? attribute.initializer.expression
    : attribute.initializer;
  return expression && ts.isStringLiteralLike(expression) ? expression.text : undefined;
}

function isCreateElementCall(node: ts.CallExpression): boolean {
  return (ts.isIdentifier(node.expression) && node.expression.text === 'createElement')
    || (ts.isPropertyAccessExpression(node.expression)
      && node.expression.name.text === 'createElement');
}

function staticPropertyName(property: ts.PropertyName): string | undefined {
  if (ts.isIdentifier(property) || ts.isStringLiteralLike(property)) return property.text;
  return undefined;
}

function hasSelectionChipCreateElementMarker(node: ts.CallExpression): boolean {
  if (!isCreateElementCall(node)) return false;
  const props = node.arguments[1];
  if (!props || !ts.isObjectLiteralExpression(props)) return false;
  return props.properties.some((property) => (
    ts.isPropertyAssignment(property)
    && staticPropertyName(property.name) === 'data-control'
    && ts.isStringLiteralLike(property.initializer)
    && property.initializer.text === 'selection-chip'
  ));
}

function findSelectionChipControlMarkers(filename: string, source: string): SourceFinding[] {
  const sourceFile = parseSource(filename, source);
  const findings: SourceFinding[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const marker = node.attributes.properties.find((property): property is ts.JsxAttribute => (
        ts.isJsxAttribute(property)
        && ts.isIdentifier(property.name)
        && property.name.text === 'data-control'
      ));
      if (marker && staticAttributeValue(marker) === 'selection-chip') {
        findings.push({ file: filename, line: lineOf(sourceFile, node), token: 'selection-chip' });
      }
    } else if (ts.isCallExpression(node) && hasSelectionChipCreateElementMarker(node)) {
      findings.push({ file: filename, line: lineOf(sourceFile, node), token: 'selection-chip' });
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

describe('SelectionChip production guard', () => {
  it('rejects page-local SelectionChip declarations', () => {
    expect(findSelectionChipDeclarations(
      '../../pages/ExamplePage.tsx',
      'const SelectionChip = () => null;',
    )).toEqual([{ file: '../../pages/ExamplePage.tsx', line: 1, token: 'SelectionChip' }]);
  });

  it('recognizes quoted and expression control markers', () => {
    const source = [
      '<button data-control="selection-chip">First</button>;',
      "<button data-control={'selection-chip'}>Second</button>;",
      "React.createElement('button', { 'data-control': 'selection-chip' }, 'Third');",
    ].join('\n');
    expect(findSelectionChipControlMarkers('../../pages/ExamplePage.tsx', source)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'selection-chip' },
      { file: '../../pages/ExamplePage.tsx', line: 2, token: 'selection-chip' },
      { file: '../../pages/ExamplePage.tsx', line: 3, token: 'selection-chip' },
    ]);
  });

  it('keeps one shared owner and no copied production marker', () => {
    const sources = Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename));
    const declarationViolations = sources
      .flatMap(([filename, source]) => findSelectionChipDeclarations(filename, source));
    const markers = sources
      .flatMap(([filename, source]) => findSelectionChipControlMarkers(filename, source));

    expect(declarationViolations).toEqual([]);
    expect(productionSources[SELECTION_CHIP_OWNER]).toMatch(/export const SelectionChip\s*=/);
    expect(markers).toEqual([
      expect.objectContaining({ file: SELECTION_CHIP_OWNER, token: 'selection-chip' }),
    ]);
  });
});
