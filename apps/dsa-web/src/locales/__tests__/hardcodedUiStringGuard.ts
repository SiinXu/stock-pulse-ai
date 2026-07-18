// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import ts from 'typescript';

export type HardcodedUiStringContext =
  | 'jsx-text'
  | 'jsx-expression'
  | 'aria-label'
  | 'aria-description'
  | 'ariaLabel'
  | 'alt'
  | 'placeholder'
  | 'title'
  | 'label'
  | 'message'
  | 'description'
  | 'actionLabel'
  | 'emptyText'
  | 'searchPlaceholder'
  | 'loadingText'
  | 'toast-call'
  | 'notice-call'
  | 'error-call'
  | 'document-title';

export interface HardcodedUiStringCandidate {
  file: string;
  line: number;
  context: HardcodedUiStringContext;
  text: string;
}

export interface HardcodedUiStringAllowance {
  file: string;
  text: string;
  context: HardcodedUiStringContext;
  purpose: string;
}

interface StaticTextPart {
  node: ts.Node;
  text: string;
}

interface StaticValueReference {
  expression: ts.Expression;
  propertyPath: readonly string[];
}

interface ResolvedConstInitializer {
  references: readonly StaticValueReference[];
  resolvingSymbols: ReadonlySet<ts.Symbol>;
}

interface SelectedStaticExpression {
  expression: ts.Expression;
  resolvingSymbols: ReadonlySet<ts.Symbol>;
}

interface ContextualStaticTextPart {
  context: HardcodedUiStringContext;
  part: StaticTextPart;
}

const userFacingAttributes = new Set([
  'aria-label',
  'aria-description',
  'ariaLabel',
  'alt',
  'placeholder',
  'title',
  'label',
  'message',
  'description',
  'actionLabel',
  'emptyText',
  'searchPlaceholder',
  'loadingText',
]);
const userCopyObjectProperties = new Set(['message', 'title', 'description']);
const han = /[\p{Script=Han}]/u;
const latinLetter = /[A-Za-z]/;
const technicalIdentifier = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$/;

function normalizeText(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function containsUserCopy(value: string): boolean {
  return han.test(value) || latinLetter.test(value);
}

function constVariableDeclaration(
  declaration: ts.VariableDeclaration | ts.BindingElement,
): ts.VariableDeclaration | undefined {
  if (ts.isVariableDeclaration(declaration)) {
    return ts.isVariableDeclarationList(declaration.parent)
      && declaration.parent.flags & ts.NodeFlags.Const
      ? declaration
      : undefined;
  }

  let current = declaration;
  while (true) {
    const bindingPattern = current.parent;
    if (!ts.isObjectBindingPattern(bindingPattern) && !ts.isArrayBindingPattern(bindingPattern)) {
      return undefined;
    }

    const owner = bindingPattern.parent;
    if (ts.isVariableDeclaration(owner)) {
      return ts.isVariableDeclarationList(owner.parent)
        && owner.parent.flags & ts.NodeFlags.Const
        ? owner
        : undefined;
    }
    if (!ts.isBindingElement(owner)) return undefined;
    current = owner;
  }
}

function bindingElementPropertyName(element: ts.BindingElement): string | undefined {
  if (element.dotDotDotToken) return undefined;

  if (ts.isObjectBindingPattern(element.parent)) {
    const name = element.propertyName ?? (ts.isIdentifier(element.name) ? element.name : undefined);
    return name ? propertyNameText(name) : undefined;
  }

  if (ts.isArrayBindingPattern(element.parent)) {
    const index = element.parent.elements.indexOf(element);
    return index >= 0 ? String(index) : undefined;
  }

  return undefined;
}

function bindingElementReferences(
  declaration: ts.BindingElement,
  variableDeclaration: ts.VariableDeclaration,
): StaticValueReference[] | undefined {
  if (!variableDeclaration.initializer) return undefined;

  const bindingElements: ts.BindingElement[] = [];
  let current = declaration;
  while (true) {
    bindingElements.unshift(current);
    const bindingPattern = current.parent;
    if (!ts.isObjectBindingPattern(bindingPattern) && !ts.isArrayBindingPattern(bindingPattern)) {
      return undefined;
    }

    const owner = bindingPattern.parent;
    if (owner === variableDeclaration) break;
    if (!ts.isBindingElement(owner)) return undefined;
    current = owner;
  }

  const propertyPath = bindingElements.map(bindingElementPropertyName);
  if (propertyPath.some((propertyName) => propertyName === undefined)) return undefined;

  const staticPropertyPath = propertyPath as string[];
  return [
    { expression: variableDeclaration.initializer, propertyPath: staticPropertyPath },
    ...bindingElements.flatMap((element, index) => element.initializer
      ? [{ expression: element.initializer, propertyPath: staticPropertyPath.slice(index + 1) }]
      : []),
  ];
}

function resolveConstSymbolInitializer(
  symbol: ts.Symbol | undefined,
  resolvingSymbols: ReadonlySet<ts.Symbol>,
): ResolvedConstInitializer | undefined {
  if (!symbol || resolvingSymbols.has(symbol)) return undefined;

  const declaration = symbol.valueDeclaration;
  if (!declaration || (!ts.isVariableDeclaration(declaration) && !ts.isBindingElement(declaration))) {
    return undefined;
  }

  const variableDeclaration = constVariableDeclaration(declaration);
  if (!variableDeclaration?.initializer) return undefined;

  const references = ts.isBindingElement(declaration)
    ? bindingElementReferences(declaration, variableDeclaration)
    : [{ expression: variableDeclaration.initializer, propertyPath: [] }];
  if (!references) return undefined;

  return {
    references,
    resolvingSymbols: new Set([...resolvingSymbols, symbol]),
  };
}

function resolveConstInitializer(
  identifier: ts.Identifier,
  checker: ts.TypeChecker,
  resolvingSymbols: ReadonlySet<ts.Symbol>,
): ResolvedConstInitializer | undefined {
  return resolveConstSymbolInitializer(checker.getSymbolAtLocation(identifier), resolvingSymbols);
}

function selectStaticExpressions(
  expression: ts.Expression,
  propertyPath: readonly string[],
  checker: ts.TypeChecker,
  resolvingSymbols: ReadonlySet<ts.Symbol>,
): SelectedStaticExpression[] {
  if (propertyPath.length === 0) return [{ expression, resolvingSymbols }];

  if (
    ts.isParenthesizedExpression(expression)
    || ts.isAsExpression(expression)
    || ts.isTypeAssertionExpression(expression)
    || ts.isSatisfiesExpression(expression)
    || ts.isNonNullExpression(expression)
  ) {
    return selectStaticExpressions(expression.expression, propertyPath, checker, resolvingSymbols);
  }

  if (ts.isIdentifier(expression)) {
    const resolved = resolveConstInitializer(expression, checker, resolvingSymbols);
    return resolved
      ? resolved.references.flatMap((reference) => selectStaticExpressions(
        reference.expression,
        [...reference.propertyPath, ...propertyPath],
        checker,
        resolved.resolvingSymbols,
      ))
      : [];
  }

  if (ts.isPropertyAccessExpression(expression)) {
    return selectStaticExpressions(
      expression.expression,
      [expression.name.text, ...propertyPath],
      checker,
      resolvingSymbols,
    );
  }

  if (
    ts.isElementAccessExpression(expression)
    && expression.argumentExpression
    && (ts.isStringLiteral(expression.argumentExpression) || ts.isNumericLiteral(expression.argumentExpression))
  ) {
    return selectStaticExpressions(
      expression.expression,
      [expression.argumentExpression.text, ...propertyPath],
      checker,
      resolvingSymbols,
    );
  }

  if (ts.isConditionalExpression(expression)) {
    return [
      ...selectStaticExpressions(expression.whenTrue, propertyPath, checker, resolvingSymbols),
      ...selectStaticExpressions(expression.whenFalse, propertyPath, checker, resolvingSymbols),
    ];
  }

  if (ts.isBinaryExpression(expression)) {
    if (expression.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) {
      return selectStaticExpressions(expression.right, propertyPath, checker, resolvingSymbols);
    }
    if ([
      ts.SyntaxKind.BarBarToken,
      ts.SyntaxKind.QuestionQuestionToken,
      ts.SyntaxKind.CommaToken,
    ].includes(expression.operatorToken.kind)) {
      return [
        ...selectStaticExpressions(expression.left, propertyPath, checker, resolvingSymbols),
        ...selectStaticExpressions(expression.right, propertyPath, checker, resolvingSymbols),
      ];
    }
  }

  const [propertyName, ...remainingPropertyPath] = propertyPath;
  if (ts.isObjectLiteralExpression(expression)) {
    return expression.properties.flatMap((property) => {
      if (ts.isSpreadAssignment(property)) {
        return selectStaticExpressions(property.expression, propertyPath, checker, resolvingSymbols);
      }
      if (propertyNameText(property.name) !== propertyName) return [];

      if (ts.isPropertyAssignment(property)) {
        return selectStaticExpressions(
          property.initializer,
          remainingPropertyPath,
          checker,
          resolvingSymbols,
        );
      }
      if (ts.isShorthandPropertyAssignment(property)) {
        const resolved = resolveConstSymbolInitializer(
          checker.getShorthandAssignmentValueSymbol(property),
          resolvingSymbols,
        );
        return resolved
          ? resolved.references.flatMap((reference) => selectStaticExpressions(
            reference.expression,
            [...reference.propertyPath, ...remainingPropertyPath],
            checker,
            resolved.resolvingSymbols,
          ))
          : [];
      }
      return [];
    });
  }

  if (ts.isArrayLiteralExpression(expression) && /^\d+$/.test(propertyName)) {
    const element = expression.elements[Number(propertyName)];
    return element && !ts.isOmittedExpression(element) && !ts.isSpreadElement(element)
      ? selectStaticExpressions(element, remainingPropertyPath, checker, resolvingSymbols)
      : [];
  }

  return [];
}

function collectShorthandStaticTextParts(
  property: ts.ShorthandPropertyAssignment,
  checker: ts.TypeChecker,
  resolvingSymbols: ReadonlySet<ts.Symbol>,
): StaticTextPart[] {
  const resolved = resolveConstSymbolInitializer(
    checker.getShorthandAssignmentValueSymbol(property),
    resolvingSymbols,
  );
  return resolved
    ? resolved.references.flatMap((reference) => selectStaticExpressions(
      reference.expression,
      reference.propertyPath,
      checker,
      resolved.resolvingSymbols,
    ).flatMap((selected) => collectStaticTextParts(
      selected.expression,
      checker,
      selected.resolvingSymbols,
    )))
    : [];
}

function collectStaticObjectPropertyParts(
  expression: ts.Expression,
  propertyName: string,
  checker: ts.TypeChecker,
  resolvingSymbols: ReadonlySet<ts.Symbol>,
): StaticTextPart[] {
  return selectStaticExpressions(
    expression,
    [propertyName],
    checker,
    resolvingSymbols,
  ).flatMap((selected) => collectStaticTextParts(
    selected.expression,
    checker,
    selected.resolvingSymbols,
  ));
}

function collectStaticTextParts(
  expression: ts.Expression,
  checker?: ts.TypeChecker,
  resolvingSymbols: ReadonlySet<ts.Symbol> = new Set(),
): StaticTextPart[] {
  if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) {
    return [{ node: expression, text: expression.text }];
  }

  if (ts.isTemplateExpression(expression)) {
    return [
      { node: expression.head, text: expression.head.text },
      ...expression.templateSpans.flatMap((span) => [
        ...collectStaticTextParts(span.expression, checker, resolvingSymbols),
        { node: span.literal, text: span.literal.text },
      ]),
    ];
  }

  if (
    ts.isParenthesizedExpression(expression)
    || ts.isAsExpression(expression)
    || ts.isTypeAssertionExpression(expression)
    || ts.isSatisfiesExpression(expression)
  ) {
    return collectStaticTextParts(expression.expression, checker, resolvingSymbols);
  }

  if (ts.isNonNullExpression(expression)) {
    return collectStaticTextParts(expression.expression, checker, resolvingSymbols);
  }

  if (checker && ts.isIdentifier(expression)) {
    const resolved = resolveConstInitializer(expression, checker, resolvingSymbols);
    return resolved
      ? resolved.references.flatMap((reference) => selectStaticExpressions(
        reference.expression,
        reference.propertyPath,
        checker,
        resolved.resolvingSymbols,
      ).flatMap((selected) => collectStaticTextParts(
        selected.expression,
        checker,
        selected.resolvingSymbols,
      )))
      : [];
  }

  if (checker && ts.isPropertyAccessExpression(expression)) {
    return collectStaticObjectPropertyParts(
      expression.expression,
      expression.name.text,
      checker,
      resolvingSymbols,
    );
  }

  if (
    checker
    && ts.isElementAccessExpression(expression)
    && expression.argumentExpression
    && (ts.isStringLiteral(expression.argumentExpression) || ts.isNumericLiteral(expression.argumentExpression))
  ) {
    return collectStaticObjectPropertyParts(
      expression.expression,
      expression.argumentExpression.text,
      checker,
      resolvingSymbols,
    );
  }

  if (ts.isConditionalExpression(expression)) {
    return [
      ...collectStaticTextParts(expression.whenTrue, checker, resolvingSymbols),
      ...collectStaticTextParts(expression.whenFalse, checker, resolvingSymbols),
    ];
  }

  if (ts.isBinaryExpression(expression)) {
    if (expression.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) {
      return collectStaticTextParts(expression.right, checker, resolvingSymbols);
    }
    if ([
      ts.SyntaxKind.PlusToken,
      ts.SyntaxKind.BarBarToken,
      ts.SyntaxKind.QuestionQuestionToken,
      ts.SyntaxKind.CommaToken,
    ].includes(expression.operatorToken.kind)) {
      return [
        ...collectStaticTextParts(expression.left, checker, resolvingSymbols),
        ...collectStaticTextParts(expression.right, checker, resolvingSymbols),
      ];
    }
  }

  return [];
}

function propertyNameText(name: ts.PropertyName): string | undefined {
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)) {
    return name.text;
  }
  return undefined;
}

function collectJsxSpreadTextParts(
  expression: ts.Expression,
  checker: ts.TypeChecker,
  resolvingSymbols: ReadonlySet<ts.Symbol> = new Set(),
): ContextualStaticTextPart[] {
  if (
    ts.isParenthesizedExpression(expression)
    || ts.isAsExpression(expression)
    || ts.isTypeAssertionExpression(expression)
    || ts.isSatisfiesExpression(expression)
    || ts.isNonNullExpression(expression)
  ) {
    return collectJsxSpreadTextParts(expression.expression, checker, resolvingSymbols);
  }

  if (ts.isIdentifier(expression)) {
    const resolved = resolveConstInitializer(expression, checker, resolvingSymbols);
    return resolved
      ? resolved.references.flatMap((reference) => selectStaticExpressions(
        reference.expression,
        reference.propertyPath,
        checker,
        resolved.resolvingSymbols,
      ).flatMap((selected) => collectJsxSpreadTextParts(
        selected.expression,
        checker,
        selected.resolvingSymbols,
      )))
      : [];
  }

  if (ts.isConditionalExpression(expression)) {
    return [
      ...collectJsxSpreadTextParts(expression.whenTrue, checker, resolvingSymbols),
      ...collectJsxSpreadTextParts(expression.whenFalse, checker, resolvingSymbols),
    ];
  }

  if (ts.isBinaryExpression(expression)) {
    if (expression.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) {
      return collectJsxSpreadTextParts(expression.right, checker, resolvingSymbols);
    }
    if ([
      ts.SyntaxKind.BarBarToken,
      ts.SyntaxKind.QuestionQuestionToken,
      ts.SyntaxKind.CommaToken,
    ].includes(expression.operatorToken.kind)) {
      return [
        ...collectJsxSpreadTextParts(expression.left, checker, resolvingSymbols),
        ...collectJsxSpreadTextParts(expression.right, checker, resolvingSymbols),
      ];
    }
  }

  if (!ts.isObjectLiteralExpression(expression)) return [];

  return expression.properties.flatMap((property) => {
    if (ts.isSpreadAssignment(property)) {
      return collectJsxSpreadTextParts(property.expression, checker, resolvingSymbols);
    }

    const context = propertyNameText(property.name);
    if (!context || !userFacingAttributes.has(context)) return [];

    const parts = ts.isPropertyAssignment(property)
      ? collectStaticTextParts(property.initializer, checker, resolvingSymbols)
      : ts.isShorthandPropertyAssignment(property)
        ? collectShorthandStaticTextParts(property, checker, resolvingSymbols)
        : [];
    return parts.map((part) => ({
      context: context as HardcodedUiStringContext,
      part,
    }));
  });
}

function collectUserCopyCallParts(
  argument: ts.Expression,
  checker: ts.TypeChecker,
  objectFieldsOnly: boolean,
  resolvingSymbols: ReadonlySet<ts.Symbol> = new Set(),
): StaticTextPart[] {
  if (
    ts.isParenthesizedExpression(argument)
    || ts.isAsExpression(argument)
    || ts.isTypeAssertionExpression(argument)
    || ts.isSatisfiesExpression(argument)
    || ts.isNonNullExpression(argument)
  ) {
    return collectUserCopyCallParts(argument.expression, checker, objectFieldsOnly, resolvingSymbols);
  }

  if (ts.isIdentifier(argument)) {
    const resolved = resolveConstInitializer(argument, checker, resolvingSymbols);
    return resolved
      ? resolved.references.flatMap((reference) => selectStaticExpressions(
        reference.expression,
        reference.propertyPath,
        checker,
        resolved.resolvingSymbols,
      ).flatMap((selected) => collectUserCopyCallParts(
        selected.expression,
        checker,
        objectFieldsOnly,
        selected.resolvingSymbols,
      )))
      : [];
  }

  if (ts.isConditionalExpression(argument)) {
    return [
      ...collectUserCopyCallParts(argument.whenTrue, checker, objectFieldsOnly, resolvingSymbols),
      ...collectUserCopyCallParts(argument.whenFalse, checker, objectFieldsOnly, resolvingSymbols),
    ];
  }

  if (ts.isBinaryExpression(argument)) {
    if (argument.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) {
      return collectUserCopyCallParts(argument.right, checker, objectFieldsOnly, resolvingSymbols);
    }
    if ([
      ts.SyntaxKind.BarBarToken,
      ts.SyntaxKind.QuestionQuestionToken,
      ts.SyntaxKind.CommaToken,
    ].includes(argument.operatorToken.kind)) {
      return [
        ...collectUserCopyCallParts(argument.left, checker, objectFieldsOnly, resolvingSymbols),
        ...collectUserCopyCallParts(argument.right, checker, objectFieldsOnly, resolvingSymbols),
      ];
    }
  }

  if (!ts.isObjectLiteralExpression(argument)) {
    return objectFieldsOnly ? [] : collectStaticTextParts(argument, checker, resolvingSymbols);
  }

  return argument.properties.flatMap((property) => {
    if (ts.isSpreadAssignment(property)) {
      return collectUserCopyCallParts(property.expression, checker, true, resolvingSymbols);
    }

    const name = propertyNameText(property.name);
    if (!name || !userCopyObjectProperties.has(name)) return [];
    if (ts.isPropertyAssignment(property)) {
      return collectStaticTextParts(property.initializer, checker, resolvingSymbols);
    }
    if (ts.isShorthandPropertyAssignment(property)) {
      return collectShorthandStaticTextParts(property, checker, resolvingSymbols);
    }
    return [];
  });
}

interface UserCopyCall {
  context: HardcodedUiStringContext;
  objectFieldsOnly?: boolean;
}

function callContext(expression: ts.LeftHandSideExpression): UserCopyCall | undefined {
  if (ts.isIdentifier(expression)) {
    if (expression.text === 'toast') {
      return { context: 'toast-call' };
    }
    if (expression.text === 'notify') {
      return { context: 'notice-call' };
    }
    if (/^(?:set|show|add|push)[A-Za-z0-9]*Toast$/.test(expression.text)) {
      return { context: 'toast-call' };
    }
    if (/^set[A-Za-z0-9]*Error(?:Message)?$/.test(expression.text)) {
      return { context: 'error-call' };
    }
    if (/^set[A-Za-z0-9]*(?:Notice|Feedback|Banner)$/.test(expression.text)) {
      return { context: 'notice-call', objectFieldsOnly: true };
    }
    return undefined;
  }

  if (!ts.isPropertyAccessExpression(expression)) return undefined;
  if (
    ts.isIdentifier(expression.expression)
    && expression.expression.text === 'toast'
    && ['error', 'success', 'warning', 'info'].includes(expression.name.text)
  ) {
    return { context: 'toast-call' };
  }
  return undefined;
}

function isDocumentTitleTarget(expression: ts.Expression): boolean {
  if (!ts.isPropertyAccessExpression(expression) || expression.name.text !== 'title') {
    return false;
  }
  if (ts.isIdentifier(expression.expression)) {
    return expression.expression.text === 'document';
  }
  return (
    ts.isPropertyAccessExpression(expression.expression)
    && expression.expression.name.text === 'document'
    && ts.isIdentifier(expression.expression.expression)
    && ['window', 'globalThis'].includes(expression.expression.expression.text)
  );
}

function allowanceMatches(
  candidate: HardcodedUiStringCandidate,
  allowance: HardcodedUiStringAllowance,
): boolean {
  return (
    candidate.file === allowance.file
    && candidate.text === allowance.text
    && candidate.context === allowance.context
  );
}

export function collectHardcodedUiStrings(
  filename: string,
  sourceText: string,
): HardcodedUiStringCandidate[] {
  const source = ts.createSourceFile(filename, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const compilerOptions: ts.CompilerOptions = {
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
    getSourceFile: (requestedFilename) => requestedFilename === filename ? source : undefined,
    readFile: (requestedFilename) => requestedFilename === filename ? sourceText : undefined,
    useCaseSensitiveFileNames: () => true,
    writeFile: () => undefined,
  };
  const checker = ts.createProgram([filename], compilerOptions, compilerHost).getTypeChecker();
  const candidates: HardcodedUiStringCandidate[] = [];
  const seen = new Set<string>();

  const add = (part: StaticTextPart, context: HardcodedUiStringContext) => {
    const text = normalizeText(part.text);
    if (!text || !containsUserCopy(text)) return;
    if (context === 'error-call' && technicalIdentifier.test(text)) return;
    const start = part.node.getStart(source);
    const key = `${start}:${context}:${text}`;
    if (seen.has(key)) return;
    seen.add(key);
    const { line } = source.getLineAndCharacterOfPosition(start);
    candidates.push({ file: filename, line: line + 1, context, text });
  };

  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node)) {
      add({ node, text: node.text }, 'jsx-text');
    } else if (ts.isJsxExpression(node) && node.expression && (
      ts.isJsxElement(node.parent)
      || ts.isJsxFragment(node.parent)
    )) {
      for (const part of collectStaticTextParts(node.expression, checker)) {
        add(part, 'jsx-expression');
      }
    } else if (ts.isJsxAttribute(node) && ts.isIdentifier(node.name)) {
      const context = node.name.text;
      if (userFacingAttributes.has(context) && node.initializer) {
        const parts = ts.isStringLiteral(node.initializer)
          ? [{ node: node.initializer, text: node.initializer.text }]
          : ts.isJsxExpression(node.initializer) && node.initializer.expression
            ? collectStaticTextParts(node.initializer.expression, checker)
            : [];
        for (const part of parts) {
          add(part, context as HardcodedUiStringContext);
        }
      }
    } else if (ts.isJsxSpreadAttribute(node)) {
      for (const { context, part } of collectJsxSpreadTextParts(node.expression, checker)) {
        add(part, context);
      }
    } else if (ts.isCallExpression(node)) {
      const call = callContext(node.expression);
      if (call) {
        for (const argument of node.arguments) {
          for (const part of collectUserCopyCallParts(
            argument,
            checker,
            Boolean(call.objectFieldsOnly),
          )) {
            add(part, call.context);
          }
        }
      }
    } else if (
      ts.isBinaryExpression(node)
      && node.operatorToken.kind === ts.SyntaxKind.EqualsToken
      && isDocumentTitleTarget(node.left)
    ) {
      for (const part of collectStaticTextParts(node.right, checker)) {
        add(part, 'document-title');
      }
    }

    ts.forEachChild(node, visit);
  };

  visit(source);
  return candidates;
}

export function findHardcodedUiStrings(
  filename: string,
  sourceText: string,
  allowances: HardcodedUiStringAllowance[] = [],
): HardcodedUiStringCandidate[] {
  return collectHardcodedUiStrings(filename, sourceText).filter((candidate) => (
    !allowances.some((allowance) => allowanceMatches(candidate, allowance))
  ));
}

export function findUnusedUiStringAllowances(
  candidates: HardcodedUiStringCandidate[],
  allowances: HardcodedUiStringAllowance[],
): HardcodedUiStringAllowance[] {
  return allowances.filter((allowance) => (
    !candidates.some((candidate) => allowanceMatches(candidate, allowance))
  ));
}
