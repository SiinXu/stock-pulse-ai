import ts from 'typescript';

export type PlaywrightTraceSourceRule = 'trace-option' | 'tracing-access';

export type PlaywrightTraceSourceViolation = {
  file: string;
  line: number;
  rule: PlaywrightTraceSourceRule;
};

type SourceAnalysis = {
  checker: ts.TypeChecker;
  sourceFile: ts.SourceFile;
};

type StaticPrimitive = string | number | boolean | null;

function scriptKind(filename: string): ts.ScriptKind {
  if (/\.tsx$/i.test(filename)) return ts.ScriptKind.TSX;
  if (/\.jsx$/i.test(filename)) return ts.ScriptKind.JSX;
  if (/\.m?js$/i.test(filename)) return ts.ScriptKind.JS;
  return ts.ScriptKind.TS;
}

function analyzeSource(filename: string, sourceText: string): SourceAnalysis {
  const sourceFile = ts.createSourceFile(
    filename,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    scriptKind(filename),
  );
  const compilerOptions: ts.CompilerOptions = {
    allowJs: true,
    jsx: ts.JsxEmit.Preserve,
    noLib: true,
    noResolve: true,
    target: ts.ScriptTarget.Latest,
  };
  const compilerHost: ts.CompilerHost = {
    fileExists: (requestedFilename) => requestedFilename === filename,
    getCanonicalFileName: (requestedFilename) => requestedFilename,
    getCurrentDirectory: () => '/',
    getDefaultLibFileName: () => 'lib.d.ts',
    getNewLine: () => '\n',
    getSourceFile: (requestedFilename) => requestedFilename === filename ? sourceFile : undefined,
    readFile: (requestedFilename) => requestedFilename === filename ? sourceText : undefined,
    useCaseSensitiveFileNames: () => true,
    writeFile: () => undefined,
  };
  const checker = ts.createProgram([filename], compilerOptions, compilerHost).getTypeChecker();
  return { checker, sourceFile };
}

function unwrapExpression(expression: ts.Expression): ts.Expression {
  let current = expression;
  while (
    ts.isParenthesizedExpression(current)
    || ts.isAsExpression(current)
    || ts.isTypeAssertionExpression(current)
    || ts.isSatisfiesExpression(current)
    || ts.isNonNullExpression(current)
    || ts.isAwaitExpression(current)
  ) {
    current = current.expression;
  }
  return current;
}

function constInitializer(
  expression: ts.Identifier,
  checker: ts.TypeChecker,
  resolving: ReadonlySet<ts.Symbol>,
): { expression: ts.Expression; resolving: ReadonlySet<ts.Symbol> } | undefined {
  const symbol = checker.getSymbolAtLocation(expression);
  if (!symbol || resolving.has(symbol)) return undefined;
  const declaration = symbol.valueDeclaration;
  if (
    !declaration
    || !ts.isVariableDeclaration(declaration)
    || !declaration.initializer
    || !ts.isVariableDeclarationList(declaration.parent)
    || !(declaration.parent.flags & ts.NodeFlags.Const)
  ) {
    return undefined;
  }
  return {
    expression: declaration.initializer,
    resolving: new Set([...resolving, symbol]),
  };
}

function uniqueStaticPrimitives(values: readonly StaticPrimitive[]): StaticPrimitive[] {
  const seen = new Set<string>();
  const unique: StaticPrimitive[] = [];
  for (const value of values) {
    const key = `${typeof value}:${String(value)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(value);
  }
  return unique;
}

function concatenateStaticCandidates(
  leftValues: readonly StaticPrimitive[],
  rightValues: readonly StaticPrimitive[],
): StaticPrimitive[] {
  const combinations: StaticPrimitive[] = [];
  for (const left of leftValues) {
    for (const right of rightValues) {
      combinations.push(
        typeof left === 'string' || typeof right === 'string'
          ? String(left) + String(right)
          : Number(left) + Number(right),
      );
    }
  }
  return uniqueStaticPrimitives(combinations);
}

function staticPrimitiveCandidates(
  expression: ts.Expression,
  checker: ts.TypeChecker,
  resolving: ReadonlySet<ts.Symbol> = new Set(),
): StaticPrimitive[] {
  const current = unwrapExpression(expression);
  if (ts.isStringLiteral(current) || ts.isNoSubstitutionTemplateLiteral(current)) {
    return [current.text];
  }
  if (ts.isNumericLiteral(current)) return [Number(current.text)];
  if (current.kind === ts.SyntaxKind.TrueKeyword) return [true];
  if (current.kind === ts.SyntaxKind.FalseKeyword) return [false];
  if (current.kind === ts.SyntaxKind.NullKeyword) return [null];

  if (ts.isIdentifier(current)) {
    const initializer = constInitializer(current, checker, resolving);
    return initializer
      ? staticPrimitiveCandidates(initializer.expression, checker, initializer.resolving)
      : [];
  }

  if (ts.isTemplateExpression(current)) {
    let values: StaticPrimitive[] = [current.head.text];
    for (const span of current.templateSpans) {
      const substitutions = staticPrimitiveCandidates(span.expression, checker, resolving)
        .map((value) => String(value) + span.literal.text);
      if (substitutions.length === 0) return [];
      values = concatenateStaticCandidates(values, substitutions);
    }
    return values;
  }

  if (ts.isConditionalExpression(current)) {
    const conditions = staticPrimitiveCandidates(current.condition, checker, resolving);
    const mayBeTrue = conditions.length === 0 || conditions.some(Boolean);
    const mayBeFalse = conditions.length === 0 || conditions.some((value) => !value);
    return uniqueStaticPrimitives([
      ...(mayBeTrue
        ? staticPrimitiveCandidates(current.whenTrue, checker, resolving)
        : []),
      ...(mayBeFalse
        ? staticPrimitiveCandidates(current.whenFalse, checker, resolving)
        : []),
    ]);
  }

  if (ts.isBinaryExpression(current)) {
    if (current.operatorToken.kind === ts.SyntaxKind.PlusToken) {
      return concatenateStaticCandidates(
        staticPrimitiveCandidates(current.left, checker, resolving),
        staticPrimitiveCandidates(current.right, checker, resolving),
      );
    }
    if (current.operatorToken.kind === ts.SyntaxKind.CommaToken) {
      return staticPrimitiveCandidates(current.right, checker, resolving);
    }
    if ([
      ts.SyntaxKind.AmpersandAmpersandToken,
      ts.SyntaxKind.BarBarToken,
      ts.SyntaxKind.QuestionQuestionToken,
    ].includes(current.operatorToken.kind)) {
      const leftValues = staticPrimitiveCandidates(current.left, checker, resolving);
      const rightValues = staticPrimitiveCandidates(current.right, checker, resolving);
      if (leftValues.length === 0) return rightValues;
      const values = leftValues.flatMap((left) => {
        if (current.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) {
          return left ? rightValues : [left];
        }
        if (current.operatorToken.kind === ts.SyntaxKind.BarBarToken) {
          return left ? [left] : rightValues;
        }
        return left === null ? rightValues : [left];
      });
      return uniqueStaticPrimitives(values);
    }
  }

  if (ts.isCallExpression(current)) {
    const target = current.expression;
    if (ts.isPropertyAccessExpression(target) || ts.isElementAccessExpression(target)) {
      const methodNames = ts.isPropertyAccessExpression(target)
        ? [target.name.text]
        : target.argumentExpression
          ? staticPrimitiveCandidates(target.argumentExpression, checker, resolving)
            .map((value) => String(value))
          : [];
      const receiverValues = staticPrimitiveCandidates(target.expression, checker, resolving);
      if (methodNames.includes('concat') && receiverValues.every((value) => (
        typeof value === 'string'
      ))) {
        let values: StaticPrimitive[] = receiverValues;
        for (const argument of current.arguments) {
          const argumentValues = staticPrimitiveCandidates(argument, checker, resolving);
          if (argumentValues.length === 0) return [];
          values = concatenateStaticCandidates(values, argumentValues);
        }
        return values;
      }
    }
  }

  return [];
}

function staticPropertyNames(
  name: ts.PropertyName,
  checker: ts.TypeChecker,
): string[] {
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)) {
    return [name.text];
  }
  if (!ts.isComputedPropertyName(name)) return [];
  return staticPrimitiveCandidates(name.expression, checker).map((value) => String(value));
}

function staticAccessNames(
  expression: ts.PropertyAccessExpression | ts.ElementAccessExpression,
  checker: ts.TypeChecker,
): string[] {
  if (ts.isPropertyAccessExpression(expression)) return [expression.name.text];
  if (!expression.argumentExpression) return [];
  return staticPrimitiveCandidates(expression.argumentExpression, checker)
    .map((value) => String(value));
}

function bindingHasPropertyName(
  binding: ts.BindingElement,
  checker: ts.TypeChecker,
  expected: string,
): boolean {
  const propertyName = binding.propertyName
    ?? (ts.isIdentifier(binding.name) ? binding.name : undefined);
  return propertyName
    ? staticPropertyNames(propertyName, checker).includes(expected)
    : false;
}

function objectElementHasPropertyName(
  element: ts.ObjectLiteralElementLike,
  checker: ts.TypeChecker,
  expected: string,
): boolean {
  if (
    ts.isPropertyAssignment(element)
    || ts.isShorthandPropertyAssignment(element)
    || ts.isMethodDeclaration(element)
    || ts.isGetAccessorDeclaration(element)
    || ts.isSetAccessorDeclaration(element)
  ) {
    return staticPropertyNames(element.name, checker).includes(expected);
  }
  return false;
}

function isLiteralOff(expression: ts.Expression): boolean {
  const current = unwrapExpression(expression);
  return (
    ts.isStringLiteral(current)
    || ts.isNoSubstitutionTemplateLiteral(current)
  ) && current.text === 'off';
}

function isReflectGetCall(call: ts.CallExpression, checker: ts.TypeChecker): boolean {
  const target = call.expression;
  if (!ts.isPropertyAccessExpression(target) && !ts.isElementAccessExpression(target)) {
    return false;
  }
  return ts.isIdentifier(target.expression)
    && target.expression.text === 'Reflect'
    && staticAccessNames(target, checker).includes('get');
}

function symbolAtIdentifier(
  identifier: ts.Identifier,
  checker: ts.TypeChecker,
): ts.Symbol | undefined {
  return checker.getSymbolAtLocation(identifier);
}

function variableInitializer(expression: ts.Identifier, checker: ts.TypeChecker): ts.Expression | undefined {
  const declaration = checker.getSymbolAtLocation(expression)?.valueDeclaration;
  return declaration && ts.isVariableDeclaration(declaration)
    ? declaration.initializer
    : undefined;
}

function importedPlaywrightTestSymbols(
  sourceFile: ts.SourceFile,
  checker: ts.TypeChecker,
): Set<ts.Symbol> {
  const symbols = new Set<ts.Symbol>();
  for (const statement of sourceFile.statements) {
    if (
      !ts.isImportDeclaration(statement)
      || !ts.isStringLiteral(statement.moduleSpecifier)
      || statement.moduleSpecifier.text !== '@playwright/test'
      || !statement.importClause?.namedBindings
      || !ts.isNamedImports(statement.importClause.namedBindings)
    ) {
      continue;
    }
    for (const element of statement.importClause.namedBindings.elements) {
      if ((element.propertyName ?? element.name).text !== 'test') continue;
      const symbol = symbolAtIdentifier(element.name, checker);
      if (symbol) symbols.add(symbol);
    }
  }
  return symbols;
}

function resolvesToPlaywrightTest(
  expression: ts.Expression,
  checker: ts.TypeChecker,
  importedSymbols: ReadonlySet<ts.Symbol>,
  resolving: ReadonlySet<ts.Symbol> = new Set(),
): boolean {
  const current = unwrapExpression(expression);
  if (!ts.isIdentifier(current)) return false;
  const symbol = symbolAtIdentifier(current, checker);
  if (symbol && importedSymbols.has(symbol)) return true;
  if (current.text === 'test' && !symbol?.valueDeclaration) return true;
  if (!symbol || resolving.has(symbol)) return false;
  const initializer = variableInitializer(current, checker);
  return initializer
    ? resolvesToPlaywrightTest(
      initializer,
      checker,
      importedSymbols,
      new Set([...resolving, symbol]),
    )
    : false;
}

function isPlaywrightOptionsCall(
  call: ts.CallExpression,
  checker: ts.TypeChecker,
  importedSymbols: ReadonlySet<ts.Symbol>,
): boolean {
  const resolvesToPlaywrightOptionsMethod = (
    expression: ts.Expression,
    resolving: ReadonlySet<ts.Symbol> = new Set(),
  ): boolean => {
    const target = unwrapExpression(expression);
    if (ts.isPropertyAccessExpression(target) || ts.isElementAccessExpression(target)) {
      return staticAccessNames(target, checker).some((name) => name === 'use' || name === 'extend')
        && resolvesToPlaywrightTest(target.expression, checker, importedSymbols);
    }
    if (!ts.isIdentifier(target)) return false;
    const symbol = symbolAtIdentifier(target, checker);
    const declaration = symbol?.valueDeclaration;
    if (
      declaration
      && ts.isBindingElement(declaration)
      && !declaration.dotDotDotToken
      && ts.isObjectBindingPattern(declaration.parent)
      && (
        bindingHasPropertyName(declaration, checker, 'use')
        || bindingHasPropertyName(declaration, checker, 'extend')
      )
      && ts.isVariableDeclaration(declaration.parent.parent)
      && ts.isVariableDeclarationList(declaration.parent.parent.parent)
      && Boolean(declaration.parent.parent.parent.flags & ts.NodeFlags.Const)
      && declaration.parent.parent.initializer
      && resolvesToPlaywrightTest(
        declaration.parent.parent.initializer,
        checker,
        importedSymbols,
      )
    ) {
      return true;
    }
    const initializer = constInitializer(target, checker, resolving);
    return initializer
      ? resolvesToPlaywrightOptionsMethod(initializer.expression, initializer.resolving)
      : false;
  };

  return resolvesToPlaywrightOptionsMethod(call.expression);
}

function isObjectFromEntriesCall(call: ts.CallExpression, checker: ts.TypeChecker): boolean {
  const target = call.expression;
  if (!ts.isPropertyAccessExpression(target) && !ts.isElementAccessExpression(target)) {
    return false;
  }
  return ts.isIdentifier(unwrapExpression(target.expression))
    && unwrapExpression(target.expression).getText() === 'Object'
    && staticAccessNames(target, checker).includes('fromEntries');
}

function objectFromEntriesHasEnabledTrace(
  call: ts.CallExpression,
  checker: ts.TypeChecker,
): boolean {
  if (!isObjectFromEntriesCall(call, checker)) return false;
  const entries = call.arguments[0] ? unwrapExpression(call.arguments[0]) : undefined;
  if (!entries || !ts.isArrayLiteralExpression(entries)) return false;
  return entries.elements.some((element) => {
    const pair = ts.isSpreadElement(element) ? undefined : unwrapExpression(element);
    if (!pair || !ts.isArrayLiteralExpression(pair) || pair.elements.length < 2) return false;
    const key = pair.elements[0];
    const value = pair.elements[1];
    return !ts.isSpreadElement(key)
      && !ts.isOmittedExpression(key)
      && staticPrimitiveCandidates(key, checker).includes('trace')
      && !ts.isSpreadElement(value)
      && !ts.isOmittedExpression(value)
      && !isLiteralOff(value);
  });
}

type PlaywrightOptionTargets = {
  expressions: Set<ts.Expression>;
  objects: Set<ts.ObjectLiteralExpression>;
  symbols: Set<ts.Symbol>;
};

function collectPlaywrightOptionTargets(
  sourceFile: ts.SourceFile,
  checker: ts.TypeChecker,
  importedSymbols: ReadonlySet<ts.Symbol>,
): PlaywrightOptionTargets {
  const targets: PlaywrightOptionTargets = {
    expressions: new Set(),
    objects: new Set(),
    symbols: new Set(),
  };
  const resolving = new Set<ts.Symbol>();
  const collect = (expression: ts.Expression): void => {
    const current = unwrapExpression(expression);
    targets.expressions.add(current);
    if (ts.isIdentifier(current)) {
      const symbol = symbolAtIdentifier(current, checker);
      if (!symbol || resolving.has(symbol)) return;
      targets.symbols.add(symbol);
      const initializer = variableInitializer(current, checker);
      if (!initializer) return;
      resolving.add(symbol);
      collect(initializer);
      resolving.delete(symbol);
      return;
    }
    if (ts.isObjectLiteralExpression(current)) {
      targets.objects.add(current);
      for (const property of current.properties) {
        if (ts.isSpreadAssignment(property)) collect(property.expression);
      }
      return;
    }
    if (ts.isConditionalExpression(current)) {
      collect(current.whenTrue);
      collect(current.whenFalse);
      return;
    }
    if (ts.isBinaryExpression(current) && [
      ts.SyntaxKind.BarBarToken,
      ts.SyntaxKind.QuestionQuestionToken,
      ts.SyntaxKind.AmpersandAmpersandToken,
      ts.SyntaxKind.CommaToken,
    ].includes(current.operatorToken.kind)) {
      collect(current.left);
      collect(current.right);
    }
  };
  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node) && isPlaywrightOptionsCall(node, checker, importedSymbols)) {
      for (const argument of node.arguments) collect(argument);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);

  let discoveredAlias = true;
  while (discoveredAlias) {
    discoveredAlias = false;
    const visitAliases = (node: ts.Node): void => {
      if (
        ts.isVariableDeclaration(node)
        && ts.isIdentifier(node.name)
        && node.initializer
      ) {
        const initializer = unwrapExpression(node.initializer);
        const initializerSymbol = ts.isIdentifier(initializer)
          ? symbolAtIdentifier(initializer, checker)
          : undefined;
        const aliasSymbol = symbolAtIdentifier(node.name, checker);
        if (
          initializerSymbol
          && targets.symbols.has(initializerSymbol)
          && aliasSymbol
          && !targets.symbols.has(aliasSymbol)
        ) {
          targets.symbols.add(aliasSymbol);
          discoveredAlias = true;
        }
      }
      ts.forEachChild(node, visitAliases);
    };
    visitAliases(sourceFile);
  }
  return targets;
}

function accessRootSymbol(
  expression: ts.PropertyAccessExpression | ts.ElementAccessExpression,
  checker: ts.TypeChecker,
): ts.Symbol | undefined {
  let current = unwrapExpression(expression.expression);
  while (ts.isPropertyAccessExpression(current) || ts.isElementAccessExpression(current)) {
    current = unwrapExpression(current.expression);
  }
  return ts.isIdentifier(current) ? symbolAtIdentifier(current, checker) : undefined;
}

function typeNamesBrowserContext(type: ts.TypeNode | undefined): boolean {
  return Boolean(type?.getText().split(/[^A-Za-z0-9_$]+/).includes('BrowserContext'));
}

function isNewContextExpression(expression: ts.Expression | undefined, checker: ts.TypeChecker): boolean {
  if (!expression) return false;
  const current = unwrapExpression(expression);
  if (!ts.isCallExpression(current)) return false;
  const target = current.expression;
  return (ts.isPropertyAccessExpression(target) || ts.isElementAccessExpression(target))
    && staticAccessNames(target, checker).includes('newContext');
}

function collectBrowserContextSymbols(
  sourceFile: ts.SourceFile,
  checker: ts.TypeChecker,
): Set<ts.Symbol> {
  const symbols = new Set<ts.Symbol>();
  const aliases: Array<{ identifier: ts.Identifier; initializer: ts.Expression }> = [];
  const addIdentifier = (identifier: ts.Identifier, type?: ts.TypeNode, initializer?: ts.Expression): void => {
    if (
      identifier.text !== 'context'
      && identifier.text !== 'browserContext'
      && !typeNamesBrowserContext(type)
      && !isNewContextExpression(initializer, checker)
    ) {
      return;
    }
    const symbol = symbolAtIdentifier(identifier, checker);
    if (symbol) symbols.add(symbol);
  };
  const visit = (node: ts.Node): void => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) {
      addIdentifier(node.name, node.type, node.initializer);
      if (
        node.initializer
        && ts.isVariableDeclarationList(node.parent)
        && Boolean(node.parent.flags & ts.NodeFlags.Const)
      ) {
        aliases.push({ identifier: node.name, initializer: node.initializer });
      }
    } else if (ts.isParameter(node) && ts.isIdentifier(node.name)) {
      addIdentifier(node.name, node.type, node.initializer);
    } else if (
      ts.isBindingElement(node)
      && ts.isIdentifier(node.name)
      && bindingHasPropertyName(node, checker, 'context')
    ) {
      addIdentifier(node.name);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  let addedAlias = true;
  while (addedAlias) {
    addedAlias = false;
    for (const { identifier, initializer } of aliases) {
      const symbol = symbolAtIdentifier(identifier, checker);
      if (
        symbol
        && !symbols.has(symbol)
        && isBrowserContextExpression(initializer, checker, symbols)
      ) {
        symbols.add(symbol);
        addedAlias = true;
      }
    }
  }
  return symbols;
}

function isBrowserContextExpression(
  expression: ts.Expression,
  checker: ts.TypeChecker,
  contextSymbols: ReadonlySet<ts.Symbol>,
): boolean {
  const current = unwrapExpression(expression);
  if (isNewContextExpression(current, checker)) return true;
  if (!ts.isIdentifier(current)) return false;
  if (current.text === 'context' || current.text === 'browserContext') return true;
  const symbol = symbolAtIdentifier(current, checker);
  return Boolean(symbol && contextSymbols.has(symbol));
}

function collectReflectGetAliasSymbols(
  sourceFile: ts.SourceFile,
  checker: ts.TypeChecker,
): Set<ts.Symbol> {
  const symbols = new Set<ts.Symbol>();
  const isReflectGetExpression = (expression: ts.Expression): boolean => {
    const current = unwrapExpression(expression);
    if (ts.isPropertyAccessExpression(current) || ts.isElementAccessExpression(current)) {
      return ts.isIdentifier(unwrapExpression(current.expression))
        && unwrapExpression(current.expression).getText() === 'Reflect'
        && staticAccessNames(current, checker).includes('get');
    }
    if (!ts.isCallExpression(current)) return false;
    const target = current.expression;
    return (ts.isPropertyAccessExpression(target) || ts.isElementAccessExpression(target))
      && staticAccessNames(target, checker).includes('bind')
      && isReflectGetExpression(target.expression);
  };
  const visit = (node: ts.Node): void => {
    if (
      ts.isVariableDeclaration(node)
      && ts.isIdentifier(node.name)
      && node.initializer
      && isReflectGetExpression(node.initializer)
    ) {
      const symbol = symbolAtIdentifier(node.name, checker);
      if (symbol) symbols.add(symbol);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return symbols;
}

export function findPlaywrightTraceSourceViolations(
  filename: string,
  sourceText: string,
): PlaywrightTraceSourceViolation[] {
  const { checker, sourceFile } = analyzeSource(filename, sourceText);
  const violations: PlaywrightTraceSourceViolation[] = [];
  const seen = new Set<string>();
  const testSymbols = importedPlaywrightTestSymbols(sourceFile, checker);
  const optionTargets = collectPlaywrightOptionTargets(sourceFile, checker, testSymbols);
  const contextSymbols = collectBrowserContextSymbols(sourceFile, checker);
  const reflectGetAliases = collectReflectGetAliasSymbols(sourceFile, checker);

  const add = (node: ts.Node, rule: PlaywrightTraceSourceRule): void => {
    const start = node.getStart(sourceFile);
    const key = `${start}:${rule}`;
    if (seen.has(key)) return;
    seen.add(key);
    const { line } = sourceFile.getLineAndCharacterOfPosition(start);
    violations.push({ file: filename, line: line + 1, rule });
  };

  const visit = (node: ts.Node): void => {
    if (
      ts.isPropertyAssignment(node)
      && ts.isObjectLiteralExpression(node.parent)
      && optionTargets.objects.has(node.parent)
      && staticPropertyNames(node.name, checker).includes('trace')
      && !isLiteralOff(node.initializer)
    ) {
      add(node, 'trace-option');
    } else if (
      (
        ts.isShorthandPropertyAssignment(node)
        || ts.isMethodDeclaration(node)
        || ts.isGetAccessorDeclaration(node)
        || ts.isSetAccessorDeclaration(node)
      )
      && ts.isObjectLiteralExpression(node.parent)
      && optionTargets.objects.has(node.parent)
      && staticPropertyNames(node.name, checker).includes('trace')
    ) {
      add(node, 'trace-option');
    }

    if (
      ts.isBinaryExpression(node)
      && node.operatorToken.kind === ts.SyntaxKind.EqualsToken
      && (ts.isPropertyAccessExpression(node.left) || ts.isElementAccessExpression(node.left))
      && staticAccessNames(node.left, checker).includes('trace')
      && !isLiteralOff(node.right)
      && Boolean(
        accessRootSymbol(node.left, checker)
        && optionTargets.symbols.has(accessRootSymbol(node.left, checker)!),
      )
    ) {
      add(node, 'trace-option');
    } else if (
      ts.isCallExpression(node)
      && optionTargets.expressions.has(node)
      && objectFromEntriesHasEnabledTrace(node, checker)
    ) {
      add(node, 'trace-option');
    }

    if (
      (ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node))
      && staticAccessNames(node, checker).includes('tracing')
      && isBrowserContextExpression(node.expression, checker, contextSymbols)
    ) {
      add(node, 'tracing-access');
    } else if (
      ts.isBindingElement(node)
      && ts.isObjectBindingPattern(node.parent)
      && bindingHasPropertyName(node, checker, 'tracing')
      && ts.isVariableDeclaration(node.parent.parent)
      && Boolean(
        node.parent.parent.initializer
        && isBrowserContextExpression(node.parent.parent.initializer, checker, contextSymbols),
      )
    ) {
      add(node, 'tracing-access');
    } else if (
      ts.isCallExpression(node)
      && isReflectGetCall(node, checker)
      && node.arguments[0]
      && isBrowserContextExpression(node.arguments[0], checker, contextSymbols)
      && node.arguments[1]
      && staticPrimitiveCandidates(node.arguments[1], checker).includes('tracing')
    ) {
      add(node, 'tracing-access');
    } else if (
      ts.isCallExpression(node)
      && ts.isIdentifier(unwrapExpression(node.expression))
      && Boolean(
        symbolAtIdentifier(unwrapExpression(node.expression) as ts.Identifier, checker)
        && reflectGetAliases.has(
          symbolAtIdentifier(unwrapExpression(node.expression) as ts.Identifier, checker)!,
        ),
      )
      && node.arguments[0]
      && isBrowserContextExpression(node.arguments[0], checker, contextSymbols)
      && node.arguments[1]
      && staticPrimitiveCandidates(node.arguments[1], checker).includes('tracing')
    ) {
      add(node, 'tracing-access');
    }

    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return violations;
}

function normalizeSourcePath(filename: string): string {
  const parts: string[] = [];
  for (const part of filename.replaceAll('\\', '/').split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') parts.pop();
    else parts.push(part);
  }
  return parts.join('/');
}

function sourceDirectory(filename: string): string {
  const normalized = normalizeSourcePath(filename);
  const separator = normalized.lastIndexOf('/');
  return separator === -1 ? '' : normalized.slice(0, separator);
}

function relativeModuleSpecifiers(filename: string, sourceText: string): string[] {
  const sourceFile = ts.createSourceFile(
    filename,
    sourceText,
    ts.ScriptTarget.Latest,
    true,
    scriptKind(filename),
  );
  const specifiers: string[] = [];
  const visit = (node: ts.Node): void => {
    if (
      (ts.isImportDeclaration(node) || ts.isExportDeclaration(node))
      && node.moduleSpecifier
      && ts.isStringLiteral(node.moduleSpecifier)
      && node.moduleSpecifier.text.startsWith('.')
    ) {
      specifiers.push(node.moduleSpecifier.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return specifiers;
}

function resolveSourceModule(
  importer: string,
  specifier: string,
  sourceNames: ReadonlySet<string>,
): string | undefined {
  const base = normalizeSourcePath(`${sourceDirectory(importer)}/${specifier}`);
  const candidates = [
    base,
    ...['.ts', '.tsx', '.js', '.mjs', '.jsx'].map((extension) => `${base}${extension}`),
    ...['.ts', '.tsx', '.js', '.mjs', '.jsx'].map((extension) => `${base}/index${extension}`),
  ];
  return candidates.find((candidate) => sourceNames.has(candidate));
}

export function findPlaywrightTraceSourceGraphViolations(
  sources: Readonly<Record<string, string>>,
  entryFilenames: readonly string[],
): PlaywrightTraceSourceViolation[] {
  const normalizedSources = new Map(
    Object.entries(sources).map(([filename, source]) => [normalizeSourcePath(filename), source]),
  );
  const sourceNames = new Set(normalizedSources.keys());
  const pending = entryFilenames.map(normalizeSourcePath);
  const visited = new Set<string>();
  const violations: PlaywrightTraceSourceViolation[] = [];
  while (pending.length > 0) {
    const filename = pending.pop()!;
    if (visited.has(filename)) continue;
    visited.add(filename);
    const source = normalizedSources.get(filename);
    if (source === undefined) continue;
    violations.push(...findPlaywrightTraceSourceViolations(filename, source));
    for (const specifier of relativeModuleSpecifiers(filename, source)) {
      const dependency = resolveSourceModule(filename, specifier, sourceNames);
      if (dependency && !visited.has(dependency)) pending.push(dependency);
    }
  }
  return violations.sort((left, right) => (
    left.file.localeCompare(right.file)
    || left.line - right.line
    || left.rule.localeCompare(right.rule)
  ));
}

function objectPropertyInitializer(
  expression: ts.ObjectLiteralExpression,
  propertyName: string,
  checker: ts.TypeChecker,
): ts.Expression | undefined {
  const matches = expression.properties.filter((property) => (
    objectElementHasPropertyName(property, checker, propertyName)
  ));
  if (matches.length !== 1 || !ts.isPropertyAssignment(matches[0])) return undefined;
  return unwrapExpression(matches[0].initializer);
}

function isBooleanLiteral(expression: ts.Expression | undefined, value: boolean): boolean {
  return expression?.kind === (value ? ts.SyntaxKind.TrueKeyword : ts.SyntaxKind.FalseKeyword);
}

function isRuntimePolicyOwnedTraceProperty(
  property: ts.ObjectLiteralElementLike,
  checker: ts.TypeChecker,
): boolean {
  if (
    !ts.isPropertyAssignment(property)
    || !ts.isIdentifier(property.name)
    || property.name.text !== 'trace'
  ) {
    return false;
  }
  const initializer = unwrapExpression(property.initializer);
  if (!ts.isConditionalExpression(initializer)) return false;
  const condition = unwrapExpression(initializer.condition);
  if (
    !ts.isBinaryExpression(condition)
    || condition.operatorToken.kind !== ts.SyntaxKind.EqualsEqualsEqualsToken
    || !ts.isIdentifier(unwrapExpression(condition.left))
    || unwrapExpression(condition.left).getText() !== 'requestedTraceMode'
    || !isLiteralOff(condition.right)
    || !isLiteralOff(initializer.whenTrue)
  ) {
    return false;
  }
  const enabledOptions = unwrapExpression(initializer.whenFalse);
  if (!ts.isObjectLiteralExpression(enabledOptions)) return false;
  const mode = objectPropertyInitializer(enabledOptions, 'mode', checker);
  return Boolean(
    mode
    && (ts.isStringLiteral(mode) || ts.isNoSubstitutionTemplateLiteral(mode))
    && mode.text === 'retain-on-failure'
    && isBooleanLiteral(objectPropertyInitializer(enabledOptions, 'screenshots', checker), false)
    && isBooleanLiteral(objectPropertyInitializer(enabledOptions, 'snapshots', checker), true)
    && isBooleanLiteral(objectPropertyInitializer(enabledOptions, 'sources', checker), true)
    && isBooleanLiteral(objectPropertyInitializer(enabledOptions, 'attachments', checker), false)
  );
}

export function hasOnlyRuntimePolicyOwnedConfigTrace(
  filename: string,
  sourceText: string,
): boolean {
  const { checker, sourceFile } = analyzeSource(filename, sourceText);
  const traceProperties: ts.ObjectLiteralElementLike[] = [];
  let hasConstructedTraceOverride = false;
  const visit = (node: ts.Node): void => {
    if (
      node.parent
      && ts.isObjectLiteralExpression(node.parent)
      && (
        ts.isPropertyAssignment(node)
        || ts.isShorthandPropertyAssignment(node)
        || ts.isMethodDeclaration(node)
        || ts.isGetAccessorDeclaration(node)
        || ts.isSetAccessorDeclaration(node)
      )
      && objectElementHasPropertyName(node, checker, 'trace')
    ) {
      traceProperties.push(node);
    }
    if (ts.isCallExpression(node) && objectFromEntriesHasEnabledTrace(node, checker)) {
      hasConstructedTraceOverride = true;
    }
    if (
      ts.isBinaryExpression(node)
      && node.operatorToken.kind === ts.SyntaxKind.EqualsToken
      && (ts.isPropertyAccessExpression(node.left) || ts.isElementAccessExpression(node.left))
      && staticAccessNames(node.left, checker).includes('trace')
      && !isLiteralOff(node.right)
    ) {
      hasConstructedTraceOverride = true;
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return !hasConstructedTraceOverride
    && traceProperties.length === 1
    && isRuntimePolicyOwnedTraceProperty(traceProperties[0], checker);
}
