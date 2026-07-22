// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
import ts from 'typescript';
import { describe, expect, it } from 'vitest';
import { productionTypeScriptSources } from './productionSourceInventory';

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

type SourceFinding = {
  file: string;
  line: number;
  token: string;
};

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
  const symbolIds = new Map<ts.Symbol, number>();
  const functionNodeIds = new Map<ts.SignatureDeclaration, number>();
  type ScanState = {
    aliases: ReadonlyMap<ts.Symbol, AliasValue>;
    functions: ReadonlyMap<ts.Symbol, ts.SignatureDeclaration>;
  };
  const functionStateResults = new Map<
    ts.SignatureDeclaration,
    Map<string, ScanState>
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
  const functionBinding = (
    expression: ts.Expression,
    functions: ReadonlyMap<ts.Symbol, ts.SignatureDeclaration>,
  ): ts.SignatureDeclaration | undefined => {
    const current = unwrapExpression(expression);
    if (ts.isIdentifier(current)) {
      const symbol = symbolFor(current);
      return symbol ? functions.get(symbol) : undefined;
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
  const functionStateKey = (
    functions: ReadonlyMap<ts.Symbol, ts.SignatureDeclaration>,
  ): string => (
    Array.from(functions, ([symbol, node]) => {
      let symbolId = symbolIds.get(symbol);
      if (symbolId === undefined) {
        symbolId = symbolIds.size;
        symbolIds.set(symbol, symbolId);
      }
      let nodeId = functionNodeIds.get(node);
      if (nodeId === undefined) {
        nodeId = functionNodeIds.size;
        functionNodeIds.set(node, nodeId);
      }
      return [symbolId, nodeId] as const;
    })
      .sort(([left], [right]) => left - right)
      .map(([symbolId, nodeId]) => `${symbolId}:${nodeId}`)
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
    functions: ReadonlyMap<ts.Symbol, ts.SignatureDeclaration>,
  ): ScanState {
    const stateKey = `${aliasStateKey(aliases)}//${functionStateKey(functions)}`;
    const stateResults = functionStateResults.get(node) ?? new Map();
    const cached = stateResults.get(stateKey);
    if (cached) return cached;

    const provisional = {
      aliases: new Map(aliases),
      functions: new Map(functions),
    };
    stateResults.set(stateKey, provisional);
    functionStateResults.set(node, stateResults);
    const result = scanScope(node, aliases, functions);
    stateResults.set(stateKey, result);
    return result;
  }

  function scanScope(
    scope: ts.Node,
    inheritedAliases: ReadonlyMap<ts.Symbol, AliasValue>,
    inheritedFunctions: ReadonlyMap<ts.Symbol, ts.SignatureDeclaration>,
  ): ScanState {
    const aliases = new Map(inheritedAliases);
    const functions = new Map(inheritedFunctions);
    const ownedSymbols = new Set<ts.Symbol>();
    const deferredFunctions: ts.SignatureDeclaration[] = [];
    const aliasFor = (identifier: ts.Identifier): HistoryMethod | undefined => {
      const symbol = symbolFor(identifier);
      return symbol ? aliases.get(symbol) ?? undefined : undefined;
    };
    const setAlias = (identifier: ts.Identifier, method: HistoryMethod | undefined): void => {
      const symbol = symbolFor(identifier);
      if (symbol) aliases.set(symbol, method ?? null);
    };
    const setFunction = (identifier: ts.Identifier, expression?: ts.Expression): void => {
      const symbol = symbolFor(identifier);
      if (!symbol) return;
      const binding = expression ? functionBinding(expression, functions) : undefined;
      if (binding) functions.set(symbol, binding);
      else functions.delete(symbol);
    };
    const registerHoistedFunction = (
      identifier: ts.Identifier,
      node: ts.SignatureDeclaration,
    ): void => {
      const symbol = symbolFor(identifier);
      if (symbol) {
        ownedSymbols.add(symbol);
        functions.set(symbol, node);
      }
    };
    const isVarDeclaration = (node: ts.VariableDeclaration): boolean => (
      ts.isVariableDeclarationList(node.parent)
      && (node.parent.flags & (ts.NodeFlags.Let | ts.NodeFlags.Const)) === 0
    );
    const collectHoistedBindings = (node: ts.Node): void => {
      if (node !== scope && ts.isFunctionLike(node)) {
        if (ts.isFunctionDeclaration(node) && node.name) {
          registerHoistedFunction(node.name, node);
        }
        return;
      }
      if (ts.isVariableDeclaration(node) && isVarDeclaration(node) && ts.isIdentifier(node.name)) {
        const symbol = symbolFor(node.name);
        if (symbol) {
          ownedSymbols.add(symbol);
          if (!aliases.has(symbol)) aliases.set(symbol, null);
        }
      }
      ts.forEachChild(node, collectHoistedBindings);
    };
    if (
      (ts.isFunctionDeclaration(scope) || ts.isFunctionExpression(scope))
      && scope.name
    ) {
      registerHoistedFunction(scope.name, scope);
    }
    collectHoistedBindings(scope);
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
        const symbol = symbolFor(node.name);
        if (symbol) ownedSymbols.add(symbol);
        if (isVarDeclaration(node) && !node.initializer) return;
        setAlias(
          node.name,
          node.initializer ? historyMethodReference(node.initializer, aliasFor) : undefined,
        );
        setFunction(node.name, node.initializer);
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
          setFunction(left, node.right);
        } else if (ts.isObjectLiteralExpression(left)) {
          applyObjectAssignment(left);
        }
      }
      if (ts.isCallExpression(node)) {
        const invokedFunction = functionBinding(node.expression, functions);
        if (invokedFunction) {
          const callerOwnedSymbols = Array.from(ownedSymbols);
          const result = scanFunction(invokedFunction, aliases, functions);
          for (const [symbol, value] of result.aliases) {
            if (aliases.has(symbol)) aliases.set(symbol, value);
          }
          for (const symbol of callerOwnedSymbols) {
            const binding = result.functions.get(symbol);
            if (binding) functions.set(symbol, binding);
            else functions.delete(symbol);
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
      scanFunction(deferredFunction, aliases, functions);
    }
    return { aliases, functions };
  }

  scanScope(sourceFile, new Map(), new Map());
  return findings.sort((left, right) => left.line - right.line || left.token.localeCompare(right.token));
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
    const violations = Object.entries(productionTypeScriptSources)
      .flatMap(([filename, source]) => findPatternOwnershipViolations(filename, source));
    expect(violations).toEqual([]);

    for (const [symbol, owner] of PAGE_PATTERN_OWNERS) {
      const source = productionTypeScriptSources[owner];
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

  it('uses the function binding active at each call site', () => {
    const fixture = [
      'let replace = () => undefined;',
      'let configure = () => {',
      '  replace = window.history.replaceState.bind(window.history);',
      '};',
      'configure();',
      'configure = () => { replace = () => undefined; };',
      'replace({}, "", "?configured=1");',
      'configure();',
      'replace({}, "", "?cleared=1");',
    ].join('\n');

    expect(findHistoryMutations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 7, token: 'replaceState' },
    ]);
  });

  it('preserves callee assignments across hoisted var declarations', () => {
    const fixture = [
      'function configure() { replace = window.history.replaceState.bind(window.history); }',
      'configure();',
      'var replace;',
      'replace!({}, "", "?configured=1");',
      'function install() { runner = () => { push = window.history.pushState.bind(window.history); }; }',
      'install();',
      'var runner;',
      'var push;',
      'runner!();',
      'push!({}, "", "?installed=1");',
    ].join('\n');

    expect(findHistoryMutations('../../pages/ExamplePage.tsx', fixture)).toEqual([
      { file: '../../pages/ExamplePage.tsx', line: 4, token: 'replaceState' },
      { file: '../../pages/ExamplePage.tsx', line: 10, token: 'pushState' },
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

  it('rejects every direct production history mutation', () => {
    const productionEntries = Object.entries(productionTypeScriptSources);
    const boundSources = createBoundSourceFiles(productionEntries);
    const actual = productionEntries.flatMap(([filename, source]) => {
      const boundSource = boundSources.get(filename);
      if (!boundSource) throw new Error(`Page Router guard lost ${filename}.`);
      return findHistoryMutations(filename, source, boundSource);
    });
    expect(actual).toEqual([]);
  });

  it('keeps route-focus metadata memory-only and outside public target input', () => {
    const coordinator = productionTypeScriptSources['../routing/RouteFocusCoordinator.tsx'];
    const context = productionTypeScriptSources['../../contexts/routeFocusContext.ts'];
    expect(coordinator).toBeDefined();
    expect(context).toBeDefined();
    expect(coordinator).not.toMatch(/(?:local|session)Storage/);
    expect(coordinator).not.toMatch(/history\s*\.\s*(?:pushState|replaceState)/);
    expect(context).toMatch(/interface RouteFocusTarget\s*\{[\s\S]*routeId:[\s\S]*headingRef:[\s\S]*ready:/);
    expect(context).not.toMatch(/focusKey|navigationType|locationKey|historyEntry/);
  });
});
