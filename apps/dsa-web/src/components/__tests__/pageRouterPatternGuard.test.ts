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
  const findings: SourceFinding[] = [];
  const reportedMethods = new Map<ts.CallExpression, Set<HistoryMethod>>();
  const functionsBySymbol = new Map<ts.Symbol, ts.SignatureDeclaration>();
  const symbolIds = new Map<ts.Symbol, number>();
  const functionStateResults = new Map<
    ts.SignatureDeclaration,
    Map<string, ReadonlyMap<ts.Symbol, AliasValue>>
  >();

  const symbolFor = (identifier: ts.Identifier): ts.Symbol | undefined => (
    checker.getSymbolAtLocation(identifier)
  );
  const unwrapExpression = (expression: ts.Expression): ts.Expression => {
    let current = expression;
    while (
      ts.isParenthesizedExpression(current)
      || ts.isAsExpression(current)
      || ts.isTypeAssertionExpression(current)
      || ts.isNonNullExpression(current)
    ) {
      current = current.expression;
    }
    return current;
  };
  const functionExpression = (expression: ts.Expression): ts.SignatureDeclaration | undefined => {
    const current = unwrapExpression(expression);
    return ts.isFunctionLike(current) ? current : undefined;
  };
  const registerFunction = (identifier: ts.Identifier, node: ts.SignatureDeclaration): void => {
    const symbol = symbolFor(identifier);
    if (symbol) functionsBySymbol.set(symbol, node);
  };
  const collectFunctions = (node: ts.Node): void => {
    if (
      (ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node))
      && node.name
    ) {
      registerFunction(node.name, node);
    }
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      const initializer = functionExpression(node.initializer);
      if (initializer) registerFunction(node.name, initializer);
    }
    if (
      ts.isBinaryExpression(node)
      && node.operatorToken.kind === ts.SyntaxKind.EqualsToken
      && ts.isIdentifier(node.left)
    ) {
      const assignedFunction = functionExpression(node.right);
      if (assignedFunction) registerFunction(node.left, assignedFunction);
    }
    ts.forEachChild(node, collectFunctions);
  };
  collectFunctions(sourceFile);

  const calledFunction = (expression: ts.Expression): ts.SignatureDeclaration | undefined => {
    const current = unwrapExpression(expression);
    if (ts.isIdentifier(current)) {
      const symbol = symbolFor(current);
      return symbol ? functionsBySymbol.get(symbol) : undefined;
    }
    return ts.isFunctionLike(current) ? current : undefined;
  };
  const aliasStateKey = (aliases: ReadonlyMap<ts.Symbol, AliasValue>): string => (
    Array.from(aliases, ([symbol, value]) => {
      let id = symbolIds.get(symbol);
      if (id === undefined) {
        id = symbolIds.size;
        symbolIds.set(symbol, id);
      }
      return [id, value] as const;
    })
      .sort(([left], [right]) => left - right)
      .map(([id, value]) => `${id}:${value ?? 'none'}`)
      .join('|')
  );
  const propertyMethod = (name: ts.PropertyName | undefined): HistoryMethod | undefined => {
    if (!name) return undefined;
    const text = ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)
      ? name.text
      : undefined;
    return text === 'pushState' || text === 'replaceState' ? text : undefined;
  };

  function scanFunction(
    node: ts.SignatureDeclaration,
    aliases: ReadonlyMap<ts.Symbol, AliasValue>,
  ): ReadonlyMap<ts.Symbol, AliasValue> {
    const stateKey = aliasStateKey(aliases);
    const stateResults = functionStateResults.get(node) ?? new Map();
    const cached = stateResults.get(stateKey);
    if (cached) return cached;

    const provisional = new Map(aliases);
    stateResults.set(stateKey, provisional);
    functionStateResults.set(node, stateResults);
    const result = scanScope(node, aliases);
    stateResults.set(stateKey, result);
    return result;
  }

  function scanScope(
    scope: ts.Node,
    inheritedAliases: ReadonlyMap<ts.Symbol, AliasValue>,
  ): Map<ts.Symbol, AliasValue> {
    const aliases = new Map(inheritedAliases);
    const deferredFunctions: ts.SignatureDeclaration[] = [];
    const aliasFor = (identifier: ts.Identifier): HistoryMethod | undefined => {
      const symbol = symbolFor(identifier);
      return symbol ? aliases.get(symbol) ?? undefined : undefined;
    };
    const setAlias = (identifier: ts.Identifier, method: HistoryMethod | undefined): void => {
      const symbol = symbolFor(identifier);
      if (symbol) aliases.set(symbol, method ?? null);
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
    const applyVariableDeclaration = (node: ts.VariableDeclaration): void => {
      if (ts.isIdentifier(node.name)) {
        setAlias(
          node.name,
          node.initializer ? historyMethodReference(node.initializer, aliasFor) : undefined,
        );
      } else if (ts.isObjectBindingPattern(node.name)) {
        for (const element of node.name.elements) {
          if (!ts.isIdentifier(element.name)) continue;
          setAlias(element.name, propertyMethod(element.propertyName ?? element.name));
        }
      }
    };
    const visit = (node: ts.Node): void => {
      if (node !== scope && ts.isFunctionLike(node)) {
        deferredFunctions.push(node);
        return;
      }
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
        const invokedFunction = calledFunction(node.expression);
        if (invokedFunction) {
          const result = scanFunction(invokedFunction, aliases);
          for (const [symbol, value] of result) {
            if (aliases.has(symbol)) aliases.set(symbol, value);
          }
        }
        const method = historyMethodReference(node.expression, aliasFor);
        if (method) {
          const methods = reportedMethods.get(node) ?? new Set<HistoryMethod>();
          if (!methods.has(method)) {
            methods.add(method);
            reportedMethods.set(node, methods);
            findings.push({
              file: filename,
              line: lineOf(sourceFile, node.expression),
              token: method,
            });
          }
        }
      }
      ts.forEachChild(node, visit);
    };

    visit(scope);
    for (const deferredFunction of deferredFunctions) {
      scanFunction(deferredFunction, aliases);
    }
    return aliases;
  }

  scanScope(sourceFile, new Map());
  return findings.sort((left, right) => left.line - right.line || left.token.localeCompare(right.token));
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

  it('resolves deferred aliases at their invocation points', () => {
    const fixture = [
      'let assignedReplace;',
      'function assignedMutation() { assignedReplace({}, "", "?market=us"); }',
      'assignedReplace = window.history.replaceState;',
      'assignedMutation();',
      'let staleReplace = window.history.replaceState;',
      'function staleMutation() { staleReplace({}, "", "?market=fr"); }',
      'staleReplace = () => undefined;',
      'staleMutation();',
      'let liveReplace = window.history.replaceState;',
      'function liveMutation() { liveReplace({}, "", "?market=au"); }',
      'liveMutation();',
      'liveReplace = () => undefined;',
    ].join('\n');

    expect(findHistoryMutations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 2, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 10, token: 'replaceState' },
    ]);
  });

  it('revisits recursive functions when alias state changes', () => {
    const fixture = [
      'let replace = () => undefined;',
      'function mutate(depth: number) {',
      '  replace({}, "", "?recursive=1");',
      '  replace = window.history.replaceState.bind(window.history);',
      '  if (depth) mutate(depth - 1);',
      '}',
      'mutate(1);',
      'replace = () => undefined;',
      'let push = () => undefined;',
      'function first(depth: number) {',
      '  push({}, "", "?mutual=1");',
      '  push = window.history.pushState.bind(window.history);',
      '  if (depth) second(depth - 1);',
      '}',
      'function second(depth: number) { first(depth); }',
      'first(1);',
      'push = () => undefined;',
    ].join('\n');

    expect(findHistoryMutations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 3, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 11, token: 'pushState' },
    ]);
  });

  it('propagates outer alias changes from direct function calls', () => {
    const fixture = [
      'let replace = () => undefined;',
      'function configure() { replace = window.history.replaceState.bind(window.history); }',
      'function clear() { replace = () => undefined; }',
      'configure();',
      'replace({}, "", "?configured=1");',
      'clear();',
      'replace({}, "", "?cleared=1");',
    ].join('\n');

    expect(findHistoryMutations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 5, token: 'replaceState' },
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
