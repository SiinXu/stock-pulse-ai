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

function directHistoryMethod(node: ts.Expression): HistoryMethod | undefined {
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

function historyMethodReference(
  node: ts.Expression,
  aliasFor: (identifier: ts.Identifier) => HistoryMethod | undefined,
): HistoryMethod | undefined {
  const direct = directHistoryMethod(node);
  if (direct) return direct;
  if (ts.isIdentifier(node)) return aliasFor(node);
  if (
    ts.isParenthesizedExpression(node)
    || ts.isAsExpression(node)
    || ts.isTypeAssertionExpression(node)
    || ts.isNonNullExpression(node)
  ) {
    return historyMethodReference(node.expression, aliasFor);
  }
  if (
    ts.isCallExpression(node)
    && ts.isPropertyAccessExpression(node.expression)
    && node.expression.name.text === 'bind'
  ) {
    return historyMethodReference(node.expression.expression, aliasFor);
  }
  if (
    ts.isPropertyAccessExpression(node)
    && (node.name.text === 'call' || node.name.text === 'apply')
  ) {
    return historyMethodReference(node.expression, aliasFor);
  }
  return undefined;
}

type AliasValue = HistoryMethod | null;

type BoundSourceFile = {
  sourceFile: ts.SourceFile;
  checker: ts.TypeChecker;
};

type SourceEntry = readonly [filename: string, source: string];

function createBoundSourceFiles(sources: readonly SourceEntry[]): Map<string, BoundSourceFile> {
  const options: ts.CompilerOptions = {
    jsx: ts.JsxEmit.Preserve,
    module: ts.ModuleKind.ESNext,
    noLib: true,
    noResolve: true,
    target: ts.ScriptTarget.Latest,
  };
  const virtualSources = new Map(sources.map(([filename, source], index) => {
    const extension = filename.endsWith('.tsx') ? 'tsx' : 'ts';
    const virtualFilename = `/page-router-pattern-guard/${index}.${extension}`;
    return [virtualFilename, {
      filename,
      source,
      sourceFile: ts.createSourceFile(
        virtualFilename,
        source,
        ts.ScriptTarget.Latest,
        true,
        extension === 'tsx' ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
      ),
    }] as const;
  }));
  const host = ts.createCompilerHost(options, true);
  host.fileExists = (requested) => virtualSources.has(requested);
  host.readFile = (requested) => virtualSources.get(requested)?.source;
  host.getSourceFile = (requested) => virtualSources.get(requested)?.sourceFile;
  const program = ts.createProgram(Array.from(virtualSources.keys()), options, host);
  const checker = program.getTypeChecker();
  const boundSources = new Map<string, BoundSourceFile>();
  for (const [virtualFilename, entry] of virtualSources) {
    const sourceFile = program.getSourceFile(virtualFilename);
    if (!sourceFile) throw new Error(`Page Router guard could not bind ${entry.filename}.`);
    boundSources.set(entry.filename, { sourceFile, checker });
  }
  return boundSources;
}

function createBoundSourceFile(filename: string, source: string): BoundSourceFile {
  const boundSource = createBoundSourceFiles([[filename, source]]).get(filename);
  if (!boundSource) throw new Error(`Page Router guard could not bind ${filename}.`);
  return boundSource;
}

function findHistoryMutations(
  filename: string,
  source: string,
  boundSource = createBoundSourceFile(filename, source),
): SourceFinding[] {
  const { sourceFile, checker } = boundSource;
  const aliases = new Map<ts.Symbol, AliasValue>();
  const findings: SourceFinding[] = [];

  const symbolFor = (identifier: ts.Identifier): ts.Symbol | undefined => (
    checker.getSymbolAtLocation(identifier)
  );
  const aliasFor = (identifier: ts.Identifier): HistoryMethod | undefined => {
    const symbol = symbolFor(identifier);
    return symbol ? aliases.get(symbol) ?? undefined : undefined;
  };
  const setAlias = (identifier: ts.Identifier, method: HistoryMethod | undefined): boolean => {
    const symbol = symbolFor(identifier);
    if (!symbol) return false;
    const next = method ?? null;
    if (aliases.has(symbol) && aliases.get(symbol) === next) return false;
    aliases.set(symbol, next);
    return true;
  };
  const propertyMethod = (name: ts.PropertyName | undefined): HistoryMethod | undefined => {
    if (!name) return undefined;
    const text = ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)
      ? name.text
      : undefined;
    return text === 'pushState' || text === 'replaceState' ? text : undefined;
  };
  const applyObjectAssignment = (object: ts.ObjectLiteralExpression): void => {
    for (const property of object.properties) {
      if (ts.isPropertyAssignment(property) && ts.isIdentifier(property.initializer)) {
        setAlias(property.initializer, propertyMethod(property.name));
      } else if (ts.isShorthandPropertyAssignment(property)) {
        setAlias(property.name, propertyMethod(property.name));
      }
    }
  };

  const applyVariableDeclaration = (node: ts.VariableDeclaration): boolean => {
    if (ts.isIdentifier(node.name)) {
      return setAlias(
        node.name,
        node.initializer ? historyMethodReference(node.initializer, aliasFor) : undefined,
      );
    }
    let changed = false;
    if (ts.isObjectBindingPattern(node.name)) {
      for (const element of node.name.elements) {
        if (!ts.isIdentifier(element.name)) continue;
        changed = setAlias(element.name, propertyMethod(element.propertyName ?? element.name)) || changed;
      }
    }
    return changed;
  };

  const declarations: ts.VariableDeclaration[] = [];
  const collectDeclarations = (node: ts.Node): void => {
    if (ts.isVariableDeclaration(node)) declarations.push(node);
    ts.forEachChild(node, collectDeclarations);
  };
  collectDeclarations(sourceFile);

  // Resolve declaration initializers before visiting deferred function bodies.
  for (let pass = 0; pass <= declarations.length; pass += 1) {
    let changed = false;
    for (const declaration of declarations) {
      changed = applyVariableDeclaration(declaration) || changed;
    }
    if (!changed) break;
  }

  const visit = (node: ts.Node): void => {
    if (ts.isVariableDeclaration(node)) {
      applyVariableDeclaration(node);
    }
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
      const left = ts.isParenthesizedExpression(node.left) ? node.left.expression : node.left;
      if (ts.isIdentifier(left)) {
        setAlias(left, historyMethodReference(node.right, aliasFor));
      } else if (ts.isObjectLiteralExpression(left)) {
        applyObjectAssignment(left);
      }
    }
    if (ts.isCallExpression(node)) {
      const method = historyMethodReference(node.expression, aliasFor);
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
      'const replace = window.history.replaceState; replace({}, "", "?market=jp");',
      'const { pushState: push } = historyAlias; push({}, "", "?market=us");',
      'const boundReplace = historyAlias.replaceState.bind(historyAlias); boundReplace({}, "", "?market=sg");',
      'historyAlias.pushState.call(historyAlias, {}, "", "?market=uk");',
      'historyAlias.replaceState.apply(historyAlias, [{}, "", "?market=au"]);',
    ].join('\n');

    expect(findHistoryMutations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 3, token: 'pushState' },
      { file: '../../pages/ExamplePage.tsx', line: 4, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 5, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 6, token: 'pushState' },
      { file: '../../pages/ExamplePage.tsx', line: 7, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 8, token: 'pushState' },
      { file: '../../pages/ExamplePage.tsx', line: 9, token: 'replaceState' },
    ]);
  });

  it('detects an alias referenced before its declaration is visited', () => {
    const fixture = [
      'function mutate() { replace({}, "", "?market=us"); }',
      'const replace = window.history.replaceState;',
      'mutate();',
    ].join('\n');

    expect(findHistoryMutations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 1, token: 'replaceState' },
    ]);
  });

  it('tracks assignment aliases without leaking through scopes or stale reassignments', () => {
    const fixture = [
      'let replace;',
      'replace = window.history.replaceState.bind(window.history);',
      'replace({}, "", "?market=jp");',
      '{',
      '  const replace = () => undefined;',
      '  replace({}, "", "?market=de");',
      '}',
      'replace = () => undefined;',
      'replace({}, "", "?market=fr");',
      'let push;',
      '({ pushState: push } = window.history);',
      'push({}, "", "?market=uk");',
    ].join('\n');

    expect(findHistoryMutations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 3, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 12, token: 'pushState' },
    ]);
  });

  it('uses TypeScript symbols for var aliases and lexical shadows', () => {
    const fixture = [
      'const outerReplace = window.history.replaceState;',
      'function parameterShadow(outerReplace) { outerReplace({}, "", "?market=de"); }',
      'try { throw new Error(); } catch (outerReplace) { outerReplace({}, "", "?market=fr"); }',
      'function updateUrl() {',
      '  { var replace; replace = window.history.replaceState.bind(window.history); }',
      '  replace({}, "", "?market=jp");',
      '}',
      'outerReplace({}, "", "?market=us");',
    ].join('\n');

    expect(findHistoryMutations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 6, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 8, token: 'replaceState' },
    ]);
  });

  it('allows only the exact file/method/count migration inventory without line pinning', () => {
    const productionEntries = Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename));
    const boundSources = createBoundSourceFiles(productionEntries);
    const actual = productionEntries.flatMap(([filename, source]) => {
      const boundSource = boundSources.get(filename);
      if (!boundSource) throw new Error(`Page Router guard lost ${filename}.`);
      return findHistoryMutations(filename, source, boundSource);
    });
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
