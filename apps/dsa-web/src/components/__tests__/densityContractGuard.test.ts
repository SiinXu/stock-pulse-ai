// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';
import {
  DENSITY_CSS_VARS,
  DENSITY_UTILITY_CLASSES,
  NON_SEMANTIC_ELEVATION_SHADOWS,
  OVERLAY_ELEVATION_OWNERS,
  SURFACE_PADDING_DENSITY_CLASS,
} from '../../design/density';
import {
  assertNonEmptyProductionInventory,
  isTypeScriptModulePath,
  productionCssSources,
  productionTypeScriptSources,
  productionTsxSources,
} from './productionSourceInventory';

const INDEX_CSS = '../../index.css';
const SURFACE_OWNER = '../common/Surface.tsx';

type Finding = {
  file: string;
  line: number;
  token: string;
};

function lineOf(source: string, index: number): number {
  return source.slice(0, index).split('\n').length;
}

function maskComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/gm, (comment) => comment.replace(/[^\n]/g, ' '));
}

function unwrapExpression(expression: ts.Expression): ts.Expression {
  let current = expression;
  while (
    ts.isParenthesizedExpression(current)
    || ts.isAsExpression(current)
    || ts.isTypeAssertionExpression(current)
    || ts.isSatisfiesExpression(current)
    || ts.isNonNullExpression(current)
  ) {
    current = current.expression;
  }
  return current;
}

function findMissingDensityVars(indexCss: string): string[] {
  const source = maskComments(indexCss);
  return DENSITY_CSS_VARS.filter((token) => !source.includes(`${token}:`));
}

function findMissingDensityUtilityClasses(indexCss: string): string[] {
  const source = maskComments(indexCss);
  return DENSITY_UTILITY_CLASSES.filter((className) => !source.includes(`.${className}`));
}

function findParallelDensityDefinitions(
  sources: Record<string, string>,
): Finding[] {
  const findings: Finding[] = [];
  const definitionPattern = /--density-[\w-]+\s*:/g;
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

function findSurfacePaddingContract(surfaceSource: string): Finding[] {
  const sourceFile = ts.createSourceFile(
    SURFACE_OWNER,
    surfaceSource,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const findings: Finding[] = [];
  const expected = new Map(Object.entries(SURFACE_PADDING_DENSITY_CLASS));

  const visit = (node: ts.Node): void => {
    if (
      ts.isVariableDeclaration(node)
      && ts.isIdentifier(node.name)
      && node.name.text === 'SURFACE_PADDING_STYLES'
      && node.initializer
    ) {
      const initializer = unwrapExpression(node.initializer);
      if (!ts.isObjectLiteralExpression(initializer)) return;
      for (const property of initializer.properties) {
        if (!ts.isPropertyAssignment(property)) continue;
        const key = ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)
          ? property.name.text
          : undefined;
        if (!key || !expected.has(key)) continue;
        const expectedClass = expected.get(key) ?? '';
        let actual = '';
        const value = unwrapExpression(property.initializer as ts.Expression);
        if (ts.isStringLiteralLike(value)) {
          actual = value.text;
        }
        if (actual !== expectedClass) {
          findings.push({
            file: SURFACE_OWNER,
            line: sourceFile.getLineAndCharacterOfPosition(property.getStart(sourceFile)).line + 1,
            token: `padding:${key}:expected:${expectedClass || '(empty)'}:actual:${actual || '(empty)'}`,
          });
        }
        expected.delete(key);
      }
      for (const [key, value] of expected) {
        findings.push({
          file: SURFACE_OWNER,
          line: sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1,
          token: `padding:${key}:missing:${value || '(empty)'}`,
        });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

function findSurfaceOverlayElevation(surfaceSource: string): Finding[] {
  const findings: Finding[] = [];
  if (!surfaceSource.includes('shadow-elevation-overlay')) {
    findings.push({
      file: SURFACE_OWNER,
      line: 1,
      token: 'overlay:shadow-elevation-overlay:missing',
    });
  }
  if (/\bshadow-soft-card-strong\b/.test(surfaceSource)) {
    const index = surfaceSource.search(/\bshadow-soft-card-strong\b/);
    findings.push({
      file: SURFACE_OWNER,
      line: lineOf(surfaceSource, index),
      token: 'overlay:legacy-shadow-soft-card-strong',
    });
  }
  return findings;
}

function findNonSemanticOverlayElevation(
  sources: Record<string, string>,
): Finding[] {
  const findings: Finding[] = [];
  const ownerSet = new Set<string>(OVERLAY_ELEVATION_OWNERS);
  for (const [file, raw] of Object.entries(sources)) {
    const basename = file.split('/').pop() ?? file;
    if (!ownerSet.has(basename)) continue;
    const source = maskComments(raw);
    for (const token of NON_SEMANTIC_ELEVATION_SHADOWS) {
      const pattern = new RegExp(`(?<![a-zA-Z0-9_-])${token}(?![a-zA-Z0-9_-])`, 'g');
      for (const match of source.matchAll(pattern)) {
        findings.push({
          file,
          line: lineOf(source, match.index ?? 0),
          token: match[0],
        });
      }
    }
    if (!source.includes('shadow-elevation-overlay')) {
      findings.push({
        file,
        line: 1,
        token: 'shadow-elevation-overlay:missing',
      });
    }
  }
  return findings;
}

describe('density contract guard', () => {
  assertNonEmptyProductionInventory(productionTypeScriptSources, 'productionTypeScriptSources');
  assertNonEmptyProductionInventory(productionCssSources, 'productionCssSources');
  // Read index.css from disk so token inventory checks are not coupled to Vite
  // raw-module transform/caching of productionCssSources.
  const indexCss = fs.readFileSync('src/index.css', 'utf8');
  const surfaceSource = productionTypeScriptSources[SURFACE_OWNER]
    ?? productionTsxSources[SURFACE_OWNER]
    ?? fs.readFileSync('src/components/common/Surface.tsx', 'utf8');
  const productionCssAndTypeScript = {
    ...productionCssSources,
    [INDEX_CSS]: indexCss,
    ...productionTypeScriptSources,
  };

  it('keeps the density token inventory declared in index.css', () => {
    expect(indexCss.includes('--density-space-1:')).toBe(true);
    expect(findMissingDensityVars(indexCss)).toEqual([]);
    expect(findMissingDensityUtilityClasses(indexCss)).toEqual([]);
    expect(indexCss).toContain('[data-density="compact"]');
  });

  it('rejects parallel --density-* definitions outside the token owner', () => {
    expect(findParallelDensityDefinitions(productionCssAndTypeScript)).toEqual([]);
  });

  it('wires Surface padding and overlay elevation to density / elevation tokens', () => {
    expect(findSurfacePaddingContract(surfaceSource)).toEqual([]);
    expect(findSurfaceOverlayElevation(surfaceSource)).toEqual([]);
  });

  it('requires foundation overlay owners to use semantic elevation tokens', () => {
    expect(findNonSemanticOverlayElevation(productionTsxSources)).toEqual([]);
  });

  it('detects contract violations in fixtures without expanding production debt', () => {
    const missingPad = `
      const SURFACE_PADDING_STYLES = {
        none: '',
        sm: 'p-4',
        md: 'density-surface-pad-md',
        lg: 'density-surface-pad-lg',
      } as const;
    `;
    expect(findSurfacePaddingContract(missingPad)).toEqual([
      {
        file: SURFACE_OWNER,
        line: expect.any(Number),
        token: 'padding:sm:expected:density-surface-pad-sm:actual:p-4',
      },
    ]);

    const parallel = findParallelDensityDefinitions({
      '../../pages/ExamplePage.tsx': 'const rules = `--density-stack-gap: 1rem;`;',
    });
    expect(parallel.map(({ token }) => token)).toContain('--density-stack-gap');

    const badOverlay = findNonSemanticOverlayElevation({
      '../common/Modal.tsx': 'className="bg-elevated shadow-2xl"',
    });
    expect(badOverlay.map(({ token }) => token)).toEqual(
      expect.arrayContaining(['shadow-2xl', 'shadow-elevation-overlay:missing']),
    );
  });

  it('fails closed when the TypeScript inventory is empty and still scans .ts modules', () => {
    expect(Object.keys(productionTypeScriptSources).some(isTypeScriptModulePath)).toBe(true);
    expect(() => assertNonEmptyProductionInventory({}, 'productionTypeScriptSources'))
      .toThrow(/empty/);
    const parallel = findParallelDensityDefinitions({
      '../../utils/densityFixture.ts': 'const rules = `--density-stack-gap: 1rem;`;',
    });
    expect(parallel).toEqual([
      expect.objectContaining({
        file: '../../utils/densityFixture.ts',
        token: '--density-stack-gap',
      }),
    ]);
  });
});
