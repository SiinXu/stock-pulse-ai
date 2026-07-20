// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';
import { productionDesignGuardFixtures } from './fixtures/productionDesignGuardFixtures';

const productionComponents = import.meta.glob('../../**/*.tsx', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>;
const productionStylePaths = import.meta.glob('../../**/*.css');
const productionStyles: Record<string, string> = {
  '../../App.css': fs.readFileSync('src/App.css', 'utf8'),
  '../../index.css': fs.readFileSync('src/index.css', 'utf8'),
};
const productionSources = { ...productionStyles, ...productionComponents };
const PRIMARY_CTA_VARIANTS = new Set([
  'primary',
]);

type DesignRule =
  | 'button-shape'
  | 'button-size-contract'
  | 'button-xl-allowlist'
  | 'button-visual-override'
  | 'button-icon-only'
  | 'control-visual-override'
  | 'hardcoded-hex'
  | 'hardcoded-color'
  | 'legacy-chromatic-token'
  | 'magic-pixel-size'
  | 'primary-cta-gradient'
  | 'primary-cta-shimmer'
  | 'primary-cta-unresolved-class'
  | 'raw-viewport-height'
  | 'glow-effect'
  | 'strong-blur'
  | 'surface-level-contract'
  | 'state-surface-visual-override'
  | 'overlay-component-contract'
  | 'overlay-z-index'
  | 'near-viewport-panel';

type DesignViolation = {
  file: string;
  line: number;
  rule: DesignRule;
  token: string;
};

const BUTTON_OPENING_TAG_PATTERN = /<(?:button|Button)\b(?:=>|[^>])*?>/g;
const PRIMARY_CTA_GRADIENT_PATTERN = /(?<![a-zA-Z0-9_-])(?:-?bg-(?:(?:(?:[a-zA-Z0-9_]+-)*gradient|linear|radial|conic)(?:-[^\s"'`}>]+)?|\[[^\]\r\n]*gradient[^\]\r\n]*\]|\(image:[^)\r\n]*gradient[^)\r\n]*\))|\[(?:background|background-image):[^\]\r\n]*gradient[^\]\r\n]*\])/i;
const PRIMARY_CTA_SHIMMER_PATTERN = /(?<![a-zA-Z0-9_-])(?:animate-\[[^\]\r\n]*shimmer[^\]\r\n]*\]|\[(?:animation|animation-name):[^\]\r\n]*shimmer[^\]\r\n]*\]|(?:[a-zA-Z0-9_-]*-)?shimmer(?:-[a-zA-Z0-9_-]*)?)(?![a-zA-Z0-9_-])/i;
const PRIMARY_INLINE_GRADIENT_PATTERN = /(?:(?:repeating-)?(?:linear|radial|conic)-gradient\s*\(|var\(--[\w-]*gradient[\w-]*\))/i;
const PRIMARY_INLINE_SHIMMER_PATTERN = /shimmer/i;
const PILL_RADIUS_CLASS_PATTERN = /\brounded-(?:[trblse]{1,2}-)?full\b/g;
const BUTTON_RADIUS_CLASS_PATTERN = /^rounded(?:-(?:none|sm|md|lg|xl|2xl|3xl|full|\[[^\]]+\]))?$/;
const BUTTON_CANONICAL_SIZE_HEIGHTS = {
  compact: 'h-7',
  default: 'h-8',
  comfortable: 'h-9',
  primary: 'h-10',
} as const;
const BUTTON_COMPAT_SIZE_HEIGHTS = {
  xl: 'h-10',
} as const;
const BUTTON_LEGACY_SIZE_ALIASES = new Set(['xsm', 'sm', 'md', 'lg']);
const BUTTON_HEIGHT_CLASS_PATTERN = /^h-\d+$/;
type ExactButtonAllowance = {
  line: number;
  removeBy: string;
  tokens: readonly string[];
};
type ExactSourceAllowance = {
  line: number;
  removeBy: string;
  token: string;
};
const BUTTON_XL_ALLOWLIST = new Map<string, readonly ExactButtonAllowance[]>([
  ['../../pages/NotFoundPage.tsx', [{
    line: 34,
    removeBy: 'UI-QA01',
    tokens: ['size="xl"'],
  }]],
]);
const BUTTON_VISUAL_OVERRIDE_PATTERN = /^(?:size-|h-|min-h-|max-h-|p(?:[trblxyse])?-|rounded(?:-|$)|basis-|flex-(?:1|auto|initial|none|\[)|grow(?:-|$)|w-|min-w-|max-w-|\[(?:height|min-height|max-height|width|min-width|max-width|inline-size|min-inline-size|max-inline-size|block-size|min-block-size|max-block-size|padding(?:-(?:top|right|bottom|left|inline(?:-start|-end)?|block(?:-start|-end)?))?|border-radius|flex(?:-basis|-grow|-shrink)?):)/;
const FIELD_CONTROL_VISUAL_OVERRIDE_PATTERN = /^(?:size-|h-|min-h-|max-h-|p(?:[trblxyse])?-|rounded(?:-|$)|\[(?:height|min-height|max-height|padding(?:-(?:top|right|bottom|left|inline(?:-start|-end)?|block(?:-start|-end)?))?|border-radius):)/;
const NON_BUTTON_CONTROL_NAMES = ['Input', 'IconButton', 'Textarea'] as const;
const STATE_SURFACE_COMPONENT_NAMES = [
  'Surface',
  'Section',
  'StatePanel',
  'Alert',
  'EmptyState',
  'Loading',
  'InlineAlert',
  'ApiErrorAlert',
  'Card',
  'SectionCard',
  'StatCard',
  'DashboardStateBlock',
  'SettingsSectionCard',
] as const;
const STATE_SURFACE_VISUAL_OVERRIDE_PATTERN = /^(?:bg-|border(?:-|$)|rounded(?:-|$)|shadow(?:-|$)|ring(?:-|$)|backdrop-|[a-zA-Z0-9_-]*(?:surface|card)[a-zA-Z0-9_-]*|\[(?:background(?:-[a-z-]+)?|border(?:-[a-z-]+)?|border-radius|box-shadow):)/;
const STATE_SURFACE_INLINE_STYLE_PROPERTY_PATTERN = /^(?:background(?:-[a-z-]+)?|border(?:-[a-z-]+)?|box-shadow)$/;
const BUTTON_VISUAL_OVERRIDE_ALLOWLIST = new Map<string, readonly ExactButtonAllowance[]>([
  ['../../pages/DecisionSignalsPage.tsx', [{
    line: 1499,
    removeBy: 'UI-D01',
    tokens: ['h-auto', 'min-h-11', 'rounded-lg', 'py-1.5'],
  }]],
  ['../../pages/PortfolioPage.tsx', [
    ...[1199, 1214, 1226, 1238, 1842, 1845].map((line) => ({
      line,
      removeBy: 'UI-P01',
      tokens: ['flex-1'],
    })),
    ...[1673, 1710, 1754].map((line) => ({
      line,
      removeBy: 'UI-P01',
      tokens: ['w-full'],
    })),
  ]],
  ['../../pages/StockScreeningPage.tsx', [{
    line: 1375,
    removeBy: 'UI-SCR01',
    tokens: ['min-w-40'],
  }]],
]);
const STATE_SURFACE_VISUAL_OVERRIDE_ALLOWLIST = new Map<string, readonly ExactButtonAllowance[]>([
  ['../common/ApiErrorAlert.tsx', [47, 59].map((line) => ({
    line,
    removeBy: 'UI-QA01',
    tokens: ['dynamic:className'],
  }))],
  ['../common/Card.tsx', [{
    line: 43,
    removeBy: 'UI-QA01',
    tokens: ['dynamic:className', 'style:dynamic:style'],
  }]],
  ['../common/EmptyState.tsx', [{
    line: 22,
    removeBy: 'UI-QA01',
    tokens: ['dynamic:className', 'style:dynamic:style spread:props'],
  }]],
  ['../common/InlineAlert.tsx', [{
    line: 26,
    removeBy: 'UI-QA01',
    tokens: ['dynamic:className', 'style:dynamic:style spread:props'],
  }]],
  ['../common/Loading.tsx', [{
    line: 14,
    removeBy: 'UI-QA01',
    tokens: ['dynamic:className'],
  }]],
  ['../common/Section.tsx', [{
    line: 42,
    removeBy: 'UI-QA01',
    tokens: ['dynamic:className', 'style:dynamic:style spread:props'],
  }]],
  ['../common/SectionCard.tsx', [{
    line: 22,
    removeBy: 'UI-QA01',
    tokens: ['dynamic:className', 'style:dynamic:style spread:props'],
  }]],
  ['../common/StatCard.tsx', [{
    line: 37,
    removeBy: 'UI-QA01',
    tokens: ['dynamic:toneStyles[tone]', 'dynamic:className'],
  }]],
  ['../common/StatePanel.tsx', [{
    line: 67,
    removeBy: 'UI-QA01',
    tokens: ['dynamic:className', 'style:dynamic:style spread:props'],
  }]],
  ['../dashboard/DashboardStateBlock.tsx', [{
    line: 30,
    removeBy: 'UI-QA01',
    tokens: ['dynamic:className'],
  }]],
  ['../settings/SettingsSectionCard.tsx', [{
    line: 23,
    removeBy: 'UI-QA01',
    tokens: ['dynamic:className'],
  }]],
  ['../history/StockHistoryTrendDrawer.tsx', [205, 239, 272].map((line) => ({
    line,
    removeBy: 'UI-R02',
    tokens: ['home-panel-card'],
  }))],
  ['../report/AnalysisContextSummary.tsx', [{
    line: 119,
    removeBy: 'UI-R01',
    tokens: ['home-panel-card'],
  }]],
  ['../report/MarketReviewReportView.tsx', [474, 490, 635, 642, 650].map((line) => ({
    line,
    removeBy: 'UI-R01',
    tokens: ['home-panel-card'],
  }))],
  ['../report/ReportDetails.tsx', [{
    line: 91,
    removeBy: 'UI-R02',
    tokens: ['home-panel-card'],
  }]],
  ['../report/ReportDiagnostics.tsx', [{
    line: 209,
    removeBy: 'UI-R02',
    tokens: ['home-panel-card'],
  }]],
  ['../report/ReportNews.tsx', [{
    line: 60,
    removeBy: 'UI-R02',
    tokens: ['home-panel-card'],
  }]],
  ['../report/ReportOverview.tsx', [
    ...[298, 321].map((line) => ({
      line,
      removeBy: 'UI-R01',
      tokens: ['home-panel-card', 'home-insight-card'],
    })),
    ...[345, 363].map((line) => ({
      line,
      removeBy: 'UI-R01',
      tokens: ['home-panel-card'],
    })),
    {
      line: 382,
      removeBy: 'UI-R01',
      tokens: ['home-panel-card', 'home-rail-card'],
    },
  ]],
  ['../report/ReportStrategy.tsx', [{
    line: 72,
    removeBy: 'UI-R01',
    tokens: ['home-panel-card'],
  }]],
  ['../settings/SettingsAlert.tsx', [{
    line: 45,
    removeBy: 'UI-F03',
    tokens: ['dynamic:toastVariantStyles[variant]', 'dynamic:className'],
  }]],
  ['../tasks/TaskPanel.tsx', [{
    line: 218,
    removeBy: 'UI-R03',
    tokens: ['home-panel-card', 'dynamic:className'],
  }]],
]);
const OVERLAY_Z_ALLOWLIST = new Map<string, readonly ExactSourceAllowance[]>([
  ['../common/ToastViewport.tsx', [{ line: 11, removeBy: 'UI-F03B', token: 'z-50' }]],
  ['../../pages/DecisionSignalsPage.tsx', [{ line: 1879, removeBy: 'UI-F03B', token: 'z-[60]' }]],
  ['../../pages/SettingsPage.tsx', [{ line: 3471, removeBy: 'UI-F03B', token: 'z-50' }]],
]);
const HARDCODED_HEX_PATTERN = /#[0-9a-fA-F]{3,8}(?![0-9a-fA-F])/g;
const HARDCODED_COLOR_FUNCTION_PATTERN = /(?<![a-zA-Z0-9])(?:rgb|hsl)a?\(\s*(?!var\(|\$\{)[^)]+\)/gi;
const MAGIC_PIXEL_SIZE_PATTERN = /\b(?:text|size|[wh]|min-[wh]|max-[wh]|basis)-\[[^\]\r\n]*\d(?:\.\d+)?px[^\]\r\n]*\]/g;
const ARBITRARY_RADIUS_PATTERN = /\brounded-\[[^\]\r\n]+\]/g;
const RAW_STATIC_VIEWPORT_HEIGHT = /(^|[^a-zA-Z0-9])100vh([^a-zA-Z0-9]|$)/g;
const LEGACY_CHROMATIC_TOKEN_PATTERN = /\b(?:cyan|purple)(?:-\d+)?(?:\/[\d.]+)?\b/gi;
const RAW_CSS_MAGIC_PIXEL_PATTERN = /(?<![\w-])(?:font-size|width|height|min-width|max-width|min-height|max-height|border-radius|padding(?:-(?:top|right|bottom|left))?|margin(?:-(?:top|right|bottom|left))?|gap|row-gap|column-gap|top|right|bottom|left|inset)\s*:\s*[^;{}\r\n]*?(-?\d+(?:\.\d+)?)px\b/g;
const GLOW_EFFECT_PATTERNS = [
  /\b(?:filter\s*:\s*drop-shadow\(|text-shadow\s*:\s*0\s+0\s+(?!0(?:\D|$))|box-shadow\s*:\s*0\s+0\s+(?!0(?:\D|$)))/g,
  /\b(?:drop-)?shadow-\[(?:inset_)?0_0_(?!0_)[^\]]+\]/g,
  /var\(--[\w-]*glow[\w-]*\)/gi,
  /(?:\.[\w-]*glow[\w-]*|\[data-[^\]]*glow[^\]]*\]|@keyframes\s+[\w-]*glow[\w-]*)/gi,
];
const STRONG_BLUR_CLASS_PATTERN = /\b(?:backdrop-)?blur-(?:md|lg|xl|2xl|3xl)\b/g;
const ARBITRARY_BLUR_CLASS_PATTERN = /\b(?:backdrop-)?blur-\[\s*(\d+(?:\.\d+)?)px\s*\]/g;
const CSS_BLUR_PATTERN = /\b(?:backdrop-filter|filter)\s*:\s*blur\(\s*(\d+(?:\.\d+)?)px\s*\)/g;
const OVERLAY_Z_UTILITY_PATTERN = /(?:\bz-\[[^\]\r\n]+\]|\bz-(?:[5-9]\d|[1-9]\d{2,})\b)/g;
const INLINE_Z_INDEX_PATTERN = /\bzIndex\s*(?::|=)\s*(?:\{\s*)?([^\s,}\r\n]+)/g;
const NEAR_VIEWPORT_PANEL_PATTERN = /\b(?:max-)?w-\[(?:9\d|100)vw\]/g;
const MAX_RESTRAINED_BLUR_PX = 4;
const CSS_RULE_PATTERN = /([^{}]+)\{([^{}]*)\}/g;
const CSS_RADIUS_DECLARATION_PATTERN = /\bborder-radius\s*:\s*([^;{}\r\n]+)/i;
const BUTTON_SELECTOR_PATTERN = /\bbutton\b|\.[\w-]*(?:button|btn)[\w-]*/i;
const PILL_RADIUS_PATTERN = /^(?:9999px|50%|var\(--(?:radius-)?(?:pill|full)\))$/i;
const CLASS_LIKE_TOKEN_PATTERN = /(?<![a-zA-Z0-9_-])([a-zA-Z][a-zA-Z0-9_]*(?:-[a-zA-Z0-9_]+)+)(?![a-zA-Z0-9_-])/g;

function isProductionSource(filename: string): boolean {
  return !filename.includes('/__tests__/')
    && !filename.includes('/__fixtures__/')
    && !filename.includes('/fixtures/')
    && !filename.includes('/generated/')
    && !filename.includes('/stories/')
    && !/\.(?:test|spec)\.(?:css|tsx)$/.test(filename)
    && !/\.(?:story|stories|generated)\.(?:css|tsx)$/.test(filename);
}

function lineNumberAt(source: string, index: number): number {
  return source.slice(0, index).split('\n').length;
}

function isAllowedExactSourceToken(
  allowlist: ReadonlyMap<string, readonly ExactSourceAllowance[]>,
  filename: string,
  source: string,
  index: number,
  token: string,
): boolean {
  const line = lineNumberAt(source, index);
  return allowlist.get(filename)?.some((allowance) => (
    allowance.line === line && allowance.token === token
  )) ?? false;
}

function findCssBlockEnd(source: string, openBraceIndex: number): number {
  let depth = 1;
  for (let index = openBraceIndex + 1; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') depth -= 1;
    if (depth === 0) return index;
  }
  return -1;
}

function isInsideThemeTokenBlock(source: string, index: number): boolean {
  for (const selectorMatch of source.matchAll(/(?:^|\n)\s*(?::root|\.dark)\s*\{/g)) {
    const openBraceIndex = (selectorMatch.index ?? 0) + selectorMatch[0].lastIndexOf('{');
    const closeBraceIndex = findCssBlockEnd(source, openBraceIndex);
    if (index > openBraceIndex && index < closeBraceIndex) return true;
  }
  return false;
}

function isAllowedIndexCssToken(filename: string, source: string, index: number): boolean {
  if (!filename.endsWith('/index.css')) {
    return false;
  }

  const declarationStart = Math.max(
    source.lastIndexOf(';', index),
    source.lastIndexOf('{', index),
  ) + 1;
  const nextSemicolon = source.indexOf(';', index);
  const declarationEnd = nextSemicolon === -1 ? source.length : nextSemicolon;
  const declaration = maskComments(source.slice(declarationStart, declarationEnd));
  return /^\s*--[\w-]+\s*:/.test(declaration)
    && isInsideThemeTokenBlock(source, index);
}

function maskComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, ' '))
    .replace(/(^|[^:])\/\/[^\n]*/gm, (comment) => comment.replace(/[^\n]/g, ' '));
}

function isPillRadius(value: string): boolean {
  return PILL_RADIUS_PATTERN.test(value.trim());
}

function extractButtonClassNames(source: string): Set<string> {
  const classNames = new Set<string>();
  for (const buttonMatch of source.matchAll(BUTTON_OPENING_TAG_PATTERN)) {
    for (const tokenMatch of buttonMatch[0].matchAll(CLASS_LIKE_TOKEN_PATTERN)) {
      classNames.add(tokenMatch[1]);
    }
  }

  return classNames;
}

function escapePattern(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function selectorTargetsButton(selector: string, buttonClassNames: Set<string>): boolean {
  if (BUTTON_SELECTOR_PATTERN.test(selector)) return true;
  return Array.from(buttonClassNames).some((className) => (
    new RegExp(`\\.${escapePattern(className)}(?![a-zA-Z0-9_-])`).test(selector)
  ));
}

function hasGlobalNonPillButtonRule(source: string): boolean {
  for (const ruleMatch of source.matchAll(CSS_RULE_PATTERN)) {
    const selectors = ruleMatch[1].split(',').map((selector) => selector.trim());
    if (!selectors.includes('button')) continue;
    const radius = ruleMatch[2].match(CSS_RADIUS_DECLARATION_PATTERN)?.[1];
    if (radius && !isPillRadius(radius)) return true;
  }
  return false;
}

type StaticClassFragment = {
  index: number;
  text: string;
};

type StaticClassScan = {
  fragments: StaticClassFragment[];
  unresolved: StaticClassFragment[];
};

type StaticInitializerMap = Map<string, ts.Expression | null>;

type SharedButtonBindings = {
  checker: ts.TypeChecker;
};

type PrimaryCtaScan = {
  matchedButtons: number;
  matchedSharedStyles: number;
  matchedSurfaceLevelStyles: number;
  allowlistHits: string[];
  violations: DesignViolation[];
};

type PrimaryCtaEffectScan = {
  classNames: StaticClassScan;
  styles: StaticClassScan;
};

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

function expressionMayResolveToPrimaryCta(expression: ts.Expression): boolean {
  const current = unwrapExpression(expression);
  if (ts.isStringLiteral(current) || ts.isNoSubstitutionTemplateLiteral(current)) {
    return PRIMARY_CTA_VARIANTS.has(current.text);
  }
  if (ts.isConditionalExpression(current)) {
    return expressionMayResolveToPrimaryCta(current.whenTrue)
      || expressionMayResolveToPrimaryCta(current.whenFalse);
  }
  if (ts.isBinaryExpression(current) && [
    ts.SyntaxKind.AmpersandAmpersandToken,
    ts.SyntaxKind.BarBarToken,
    ts.SyntaxKind.QuestionQuestionToken,
    ts.SyntaxKind.CommaToken,
  ].includes(current.operatorToken.kind)) {
    return expressionMayResolveToPrimaryCta(current.left)
      || expressionMayResolveToPrimaryCta(current.right);
  }
  // A dynamic value can still resolve to the default/primary variant.
  return true;
}

function isSharedButtonModuleSpecifier(specifier: string, componentName = 'Button'): boolean {
  if (componentName === 'DashboardStateBlock') {
    return /(?:^|\/)(?:components\/)?dashboard$/.test(specifier)
      || specifier.endsWith('/dashboard/DashboardStateBlock');
  }
  if (componentName === 'SettingsSectionCard') {
    return /(?:^|\/)(?:components\/)?settings$/.test(specifier)
      || /(?:^|\/)SettingsSectionCard$/.test(specifier);
  }
  return /(?:^|\/)(?:components\/)?common$/.test(specifier)
    || specifier.endsWith(`/common/${componentName}`)
    || specifier === `./${componentName}`;
}

function importDeclarationFor(node: ts.Node): ts.ImportDeclaration | undefined {
  let current: ts.Node | undefined = node;
  while (current) {
    if (ts.isImportDeclaration(current)) {
      return current;
    }
    current = current.parent;
  }
  return undefined;
}

function isConstVariableDeclaration(declaration: ts.VariableDeclaration): boolean {
  return ts.isVariableDeclarationList(declaration.parent)
    && (declaration.parent.flags & ts.NodeFlags.Const) !== 0;
}

function symbolDeclaration(symbol: ts.Symbol): ts.Declaration | undefined {
  const declarations = symbol.declarations ?? [];
  return declarations.length === 1 ? declarations[0] : undefined;
}

function isSharedButtonNamespaceExpression(
  expression: ts.Expression,
  bindings: SharedButtonBindings,
  resolving: Set<ts.Symbol>,
  componentName = 'Button',
): boolean {
  const current = unwrapExpression(expression);
  if (!ts.isIdentifier(current)) {
    return false;
  }
  const symbol = bindings.checker.getSymbolAtLocation(current);
  if (!symbol || resolving.has(symbol)) {
    return false;
  }
  const declaration = symbolDeclaration(symbol);
  if (!declaration) {
    return false;
  }
  if (ts.isNamespaceImport(declaration)) {
    const importDeclaration = importDeclarationFor(declaration);
    return Boolean(
      importDeclaration
      && ts.isStringLiteral(importDeclaration.moduleSpecifier)
      && isSharedButtonModuleSpecifier(importDeclaration.moduleSpecifier.text, componentName),
    );
  }
  if (
    ts.isVariableDeclaration(declaration)
    && isConstVariableDeclaration(declaration)
    && declaration.initializer
  ) {
    const nextResolving = new Set(resolving);
    nextResolving.add(symbol);
    return isSharedButtonNamespaceExpression(
      declaration.initializer,
      bindings,
      nextResolving,
      componentName,
    );
  }
  return false;
}

function staticStringCandidates(
  expression: ts.Expression,
  bindings: SharedButtonBindings,
  resolving: Set<ts.Symbol>,
): string[] {
  const current = unwrapExpression(expression);
  if (ts.isStringLiteral(current) || ts.isNoSubstitutionTemplateLiteral(current)) {
    return [current.text];
  }
  if (ts.isIdentifier(current)) {
    const symbol = bindings.checker.getSymbolAtLocation(current);
    if (!symbol || resolving.has(symbol)) {
      return [];
    }
    const declaration = symbolDeclaration(symbol);
    if (
      !declaration
      || !ts.isVariableDeclaration(declaration)
      || !isConstVariableDeclaration(declaration)
      || !declaration.initializer
    ) {
      return [];
    }
    const nextResolving = new Set(resolving);
    nextResolving.add(symbol);
    return staticStringCandidates(declaration.initializer, bindings, nextResolving);
  }
  if (ts.isTemplateExpression(current)) {
    let candidates = [current.head.text];
    for (const span of current.templateSpans) {
      const substitutions = staticStringCandidates(span.expression, bindings, resolving);
      if (substitutions.length === 0 || candidates.length * substitutions.length > 64) {
        return [];
      }
      candidates = candidates.flatMap((prefix) => (
        substitutions.map((substitution) => prefix + substitution + span.literal.text)
      ));
    }
    return candidates;
  }
  if (ts.isConditionalExpression(current)) {
    return [
      ...staticStringCandidates(current.whenTrue, bindings, resolving),
      ...staticStringCandidates(current.whenFalse, bindings, resolving),
    ];
  }
  if (
    ts.isBinaryExpression(current)
    && current.operatorToken.kind === ts.SyntaxKind.PlusToken
  ) {
    const left = staticStringCandidates(current.left, bindings, resolving);
    const right = staticStringCandidates(current.right, bindings, resolving);
    if (left.length === 0 || right.length === 0 || left.length * right.length > 64) {
      return [];
    }
    return left.flatMap((prefix) => right.map((suffix) => prefix + suffix));
  }
  return [];
}

function staticPropertyNameCandidates(
  name: ts.PropertyName,
  bindings: SharedButtonBindings,
  resolving: Set<ts.Symbol>,
): string[] {
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)) {
    return [name.text];
  }
  return ts.isComputedPropertyName(name)
    ? staticStringCandidates(name.expression, bindings, resolving)
    : [];
}

function staticBindingPropertyNameCandidates(
  binding: ts.BindingElement,
  bindings: SharedButtonBindings,
  resolving: Set<ts.Symbol>,
): string[] {
  const name = binding.propertyName
    ?? (ts.isIdentifier(binding.name) ? binding.name : undefined);
  return name ? staticPropertyNameCandidates(name, bindings, resolving) : [];
}

function isSharedButtonExpression(
  expression: ts.Expression,
  bindings: SharedButtonBindings,
  resolving: Set<ts.Symbol>,
  componentName = 'Button',
): boolean {
  const current = unwrapExpression(expression);
  if (ts.isIdentifier(current)) {
    const symbol = bindings.checker.getSymbolAtLocation(current);
    if (!symbol) {
      // Self-test snippets intentionally omit imports for the shared Button shorthand.
      return current.text === componentName;
    }
    if (resolving.has(symbol)) {
      return false;
    }
    const declaration = symbolDeclaration(symbol);
    if (!declaration) {
      return false;
    }
    if (ts.isImportSpecifier(declaration)) {
      const importDeclaration = importDeclarationFor(declaration);
      return (declaration.propertyName ?? declaration.name).text === componentName
        && Boolean(
          importDeclaration
          && ts.isStringLiteral(importDeclaration.moduleSpecifier)
          && isSharedButtonModuleSpecifier(importDeclaration.moduleSpecifier.text, componentName),
        );
    }
    if (ts.isImportClause(declaration)) {
      const importDeclaration = importDeclarationFor(declaration);
      return Boolean(
        importDeclaration
        && ts.isStringLiteral(importDeclaration.moduleSpecifier)
        && importDeclaration.moduleSpecifier.text.endsWith(`/common/${componentName}`)
        && isSharedButtonModuleSpecifier(importDeclaration.moduleSpecifier.text, componentName),
      );
    }
    const nextResolving = new Set(resolving);
    nextResolving.add(symbol);
    if (
      ts.isVariableDeclaration(declaration)
      && isConstVariableDeclaration(declaration)
      && declaration.initializer
    ) {
      return isSharedButtonExpression(
        declaration.initializer,
        bindings,
        nextResolving,
        componentName,
      );
    }
    if (
      ts.isBindingElement(declaration)
      && !declaration.dotDotDotToken
      && staticBindingPropertyNameCandidates(
        declaration,
        bindings,
        nextResolving,
      ).includes(componentName)
      && ts.isObjectBindingPattern(declaration.parent)
      && ts.isVariableDeclaration(declaration.parent.parent)
      && declaration.parent.parent.initializer
    ) {
      return isSharedButtonNamespaceExpression(
        declaration.parent.parent.initializer,
        bindings,
        nextResolving,
        componentName,
      );
    }
    return false;
  }
  if (
    ts.isPropertyAccessExpression(current)
    && current.name.text === componentName
  ) {
    return isSharedButtonNamespaceExpression(
      current.expression,
      bindings,
      resolving,
      componentName,
    );
  }
  if (
    ts.isElementAccessExpression(current)
    && current.argumentExpression
    && staticStringCandidates(current.argumentExpression, bindings, resolving).includes(componentName)
  ) {
    return isSharedButtonNamespaceExpression(
      current.expression,
      bindings,
      resolving,
      componentName,
    );
  }
  return false;
}

function isSharedButtonOpening(
  opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
  bindings: SharedButtonBindings,
  componentName = 'Button',
): boolean {
  const { tagName } = opening;
  if (ts.isIdentifier(tagName)) {
    return isSharedButtonExpression(tagName, bindings, new Set(), componentName);
  }
  return ts.isPropertyAccessExpression(tagName)
    && tagName.name.text === componentName
    && isSharedButtonNamespaceExpression(tagName.expression, bindings, new Set(), componentName);
}

const OVERLAY_COMPONENT_BANNED_PROPS: Record<string, ReadonlySet<string>> = {
  Drawer: new Set([
    'width',
    'maxWidth',
    'zIndex',
    'side',
    'backdropClassName',
    'rootClassName',
    'panelClassName',
    'contentClassName',
    'showHeader',
    'className',
  ]),
  Modal: new Set([
    'width',
    'maxWidth',
    'zIndex',
    'className',
    'bodyClassName',
    'footerClassName',
  ]),
};

function appendOverlayComponentContractViolations(
  filename: string,
  source: string,
  opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
  bindings: SharedButtonBindings,
  violations: DesignViolation[],
): void {
  for (const [componentName, bannedProps] of Object.entries(OVERLAY_COMPONENT_BANNED_PROPS)) {
    if (!isSharedButtonOpening(opening, bindings, componentName)) continue;
    const line = lineNumberAt(source, opening.getStart(opening.getSourceFile()));
    let hasVariant = componentName !== 'Drawer';
    for (const property of opening.attributes.properties) {
      if (ts.isJsxSpreadAttribute(property)) {
        violations.push({
          file: filename,
          line,
          rule: 'overlay-component-contract',
          token: `${componentName} spread:${property.expression.getText(opening.getSourceFile())}`,
        });
        continue;
      }
      const propName = property.name.getText(opening.getSourceFile());
      if (propName === 'variant') hasVariant = true;
      if (bannedProps.has(propName)) {
        violations.push({
          file: filename,
          line,
          rule: 'overlay-component-contract',
          token: `${componentName}.${propName}`,
        });
      }
    }
    if (!hasVariant) {
      violations.push({
        file: filename,
        line,
        rule: 'overlay-component-contract',
        token: 'Drawer.variant',
      });
    }
  }
}

const VISIBLE_BUTTON_TEXT_PATTERN = /[\p{L}\p{N}]/u;

function jsxAttributeText(attribute: ts.JsxAttribute): string | null {
  if (!attribute.initializer) return '';
  if (ts.isStringLiteral(attribute.initializer)) return attribute.initializer.text;
  if (
    ts.isJsxExpression(attribute.initializer)
    && attribute.initializer.expression
    && (
      ts.isStringLiteral(attribute.initializer.expression)
      || ts.isNoSubstitutionTemplateLiteral(attribute.initializer.expression)
    )
  ) {
    return attribute.initializer.expression.text;
  }
  return null;
}

function jsxOpeningHidesVisibleText(
  opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
): boolean {
  for (const property of opening.attributes.properties) {
    if (!ts.isJsxAttribute(property)) continue;
    const name = property.name.getText();
    if (name === 'hidden') return true;
    if (name === 'className') {
      const value = jsxAttributeText(property);
      if (value?.split(/\s+/).includes('sr-only')) return true;
    }
    if (name === 'aria-hidden') {
      const value = jsxAttributeText(property);
      if (value === 'true') return true;
      if (
        property.initializer
        && ts.isJsxExpression(property.initializer)
        && property.initializer.expression?.kind === ts.SyntaxKind.TrueKeyword
      ) {
        return true;
      }
    }
  }
  return false;
}

function jsxExpressionMayRenderVisibleText(
  expression: ts.Expression,
  initializers: StaticInitializerMap,
  resolving = new Set<string>(),
): boolean {
  const current = unwrapExpression(expression);
  if (ts.isStringLiteral(current) || ts.isNoSubstitutionTemplateLiteral(current)) {
    return VISIBLE_BUTTON_TEXT_PATTERN.test(current.text);
  }
  if (ts.isTemplateExpression(current)) {
    return VISIBLE_BUTTON_TEXT_PATTERN.test(current.head.text) || current.templateSpans.length > 0;
  }
  if (ts.isNumericLiteral(current)) return true;
  if (
    current.kind === ts.SyntaxKind.FalseKeyword
    || current.kind === ts.SyntaxKind.TrueKeyword
    || current.kind === ts.SyntaxKind.NullKeyword
  ) {
    return false;
  }
  if (ts.isIdentifier(current)) {
    if (resolving.has(current.text) || !initializers.has(current.text)) return true;
    const initializer = initializers.get(current.text);
    if (!initializer) return true;
    const nextResolving = new Set(resolving);
    nextResolving.add(current.text);
    return jsxExpressionMayRenderVisibleText(initializer, initializers, nextResolving);
  }
  if (ts.isJsxElement(current)) {
    return jsxElementMayRenderVisibleText(current, initializers, resolving);
  }
  if (ts.isJsxSelfClosingElement(current)) {
    return false;
  }
  if (ts.isJsxFragment(current)) {
    return current.children.some((child) => (
      jsxChildMayRenderVisibleText(child, initializers, resolving)
    ));
  }
  if (ts.isConditionalExpression(current)) {
    return jsxExpressionMayRenderVisibleText(current.whenTrue, initializers, resolving)
      || jsxExpressionMayRenderVisibleText(current.whenFalse, initializers, resolving);
  }
  if (ts.isBinaryExpression(current)) {
    if (
      current.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken
      || current.operatorToken.kind === ts.SyntaxKind.CommaToken
    ) {
      return jsxExpressionMayRenderVisibleText(current.right, initializers, resolving);
    }
    if (
      current.operatorToken.kind === ts.SyntaxKind.BarBarToken
      || current.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken
      || current.operatorToken.kind === ts.SyntaxKind.PlusToken
    ) {
      return jsxExpressionMayRenderVisibleText(current.left, initializers, resolving)
        || jsxExpressionMayRenderVisibleText(current.right, initializers, resolving);
    }
  }
  if (ts.isArrayLiteralExpression(current)) {
    return current.elements.some((element) => (
      !ts.isSpreadElement(element)
      && jsxExpressionMayRenderVisibleText(element, initializers, resolving)
    ));
  }

  // Calls and data expressions can render localized or runtime-owned text.
  return true;
}

function jsxElementMayRenderVisibleText(
  element: ts.JsxElement,
  initializers: StaticInitializerMap,
  resolving = new Set<string>(),
): boolean {
  if (jsxOpeningHidesVisibleText(element.openingElement)) return false;
  return element.children.some((child) => (
    jsxChildMayRenderVisibleText(child, initializers, resolving)
  ));
}

function jsxChildMayRenderVisibleText(
  child: ts.JsxChild,
  initializers: StaticInitializerMap,
  resolving = new Set<string>(),
): boolean {
  if (ts.isJsxText(child)) return VISIBLE_BUTTON_TEXT_PATTERN.test(child.text);
  if (ts.isJsxExpression(child)) {
    return Boolean(
      child.expression
      && jsxExpressionMayRenderVisibleText(child.expression, initializers, resolving),
    );
  }
  if (ts.isJsxElement(child)) {
    return jsxElementMayRenderVisibleText(child, initializers, resolving);
  }
  if (ts.isJsxSelfClosingElement(child)) return false;
  return child.children.some((nestedChild) => (
    jsxChildMayRenderVisibleText(nestedChild, initializers, resolving)
  ));
}

function appendButtonIconOnlyViolation(
  filename: string,
  source: string,
  element: ts.JsxElement,
  initializers: StaticInitializerMap,
  bindings: SharedButtonBindings,
  violations: DesignViolation[],
): void {
  if (!isSharedButtonOpening(element.openingElement, bindings)) return;
  if (element.children.some((child) => (
    jsxChildMayRenderVisibleText(child, initializers)
  ))) return;
  violations.push({
    file: filename,
    line: lineNumberAt(source, element.openingElement.getStart(element.getSourceFile())),
    rule: 'button-icon-only',
    token: 'icon-or-symbol-only',
  });
}

function isPrimaryButtonOpening(
  opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
  bindings: SharedButtonBindings,
): boolean {
  if (!isSharedButtonOpening(opening, bindings)) {
    return false;
  }
  let mayResolveToPrimary = true;
  for (const property of opening.attributes.properties) {
    if (ts.isJsxSpreadAttribute(property)) {
      mayResolveToPrimary = true;
      continue;
    }
    if (property.name.getText() !== 'variant') {
      continue;
    }
    if (!property.initializer) {
      mayResolveToPrimary = true;
    } else if (ts.isStringLiteral(property.initializer)) {
      mayResolveToPrimary = PRIMARY_CTA_VARIANTS.has(property.initializer.text);
    } else {
      mayResolveToPrimary = !ts.isJsxExpression(property.initializer)
        || !property.initializer.expression
        || expressionMayResolveToPrimaryCta(property.initializer.expression);
    }
  }
  return mayResolveToPrimary;
}

function spreadMayOverrideButtonSize(
  expression: ts.Expression,
  bindings: SharedButtonBindings,
  resolving = new Set<ts.Symbol>(),
): boolean {
  const current = unwrapExpression(expression);
  if (ts.isIdentifier(current)) {
    const symbol = bindings.checker.getSymbolAtLocation(current);
    if (!symbol || resolving.has(symbol)) return true;
    const declaration = symbolDeclaration(symbol);
    if (
      !declaration
      || !ts.isVariableDeclaration(declaration)
      || !isConstVariableDeclaration(declaration)
      || !declaration.initializer
    ) {
      return true;
    }
    const nextResolving = new Set(resolving);
    nextResolving.add(symbol);
    return spreadMayOverrideButtonSize(declaration.initializer, bindings, nextResolving);
  }
  if (!ts.isObjectLiteralExpression(current)) return true;
  for (const property of current.properties) {
    if (ts.isSpreadAssignment(property)) {
      if (spreadMayOverrideButtonSize(property.expression, bindings, resolving)) return true;
      continue;
    }
    if (!('name' in property) || !property.name) return true;
    const names = staticPropertyNameCandidates(property.name, bindings, resolving);
    if (names.length === 0 || names.includes('size')) return true;
  }
  return false;
}

function appendButtonSizeUsageViolations(
  filename: string,
  source: string,
  opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
  bindings: SharedButtonBindings,
  allowlistHits: string[],
  violations: DesignViolation[],
): void {
  if (!isSharedButtonOpening(opening, bindings)) return;
  let candidates: string[] = [];
  let unresolved: ts.Node | null = null;
  for (const property of opening.attributes.properties) {
    if (ts.isJsxSpreadAttribute(property)) {
      if (spreadMayOverrideButtonSize(property.expression, bindings)) {
        candidates = [];
        unresolved = property;
      }
      continue;
    }
    if (property.name.getText() !== 'size') continue;
    candidates = !property.initializer
      ? []
      : ts.isStringLiteral(property.initializer)
        ? [property.initializer.text]
        : ts.isJsxExpression(property.initializer) && property.initializer.expression
          ? staticStringCandidates(property.initializer.expression, bindings, new Set())
          : [];
    unresolved = candidates.length === 0 ? property : null;
  }
  if (unresolved) {
    violations.push({
      file: filename,
      line: lineNumberAt(source, unresolved.getStart(opening.getSourceFile())),
      rule: 'button-xl-allowlist',
      token: 'size={dynamic}',
    });
  }
  const openingLine = lineNumberAt(source, opening.getStart(opening.getSourceFile()));
  for (const candidate of candidates) {
    if (!BUTTON_LEGACY_SIZE_ALIASES.has(candidate)) continue;
    violations.push({
      file: filename,
      line: openingLine,
      rule: 'button-size-contract',
      token: `size="${candidate}"`,
    });
  }
  if (!candidates.includes('xl')) return;
  if (consumeExactButtonAllowance(
    'button-xl-allowlist',
    BUTTON_XL_ALLOWLIST,
    filename,
    openingLine,
    'size="xl"',
    allowlistHits,
  )) return;
  violations.push({
    file: filename,
    line: openingLine,
    rule: 'button-xl-allowlist',
    token: 'size="xl"',
  });
}

type ExactVisualAllowanceRule = 'button-xl-allowlist' | 'button-visual-override' | 'state-surface-visual-override';

function exactButtonAllowanceKey(
  rule: ExactVisualAllowanceRule,
  filename: string,
  line: number,
  token: string,
): string {
  return `${rule}:${filename}:${line}:${token}`;
}

function consumeExactButtonAllowance(
  rule: ExactVisualAllowanceRule,
  allowlist: Map<string, readonly ExactButtonAllowance[]>,
  filename: string,
  line: number,
  token: string,
  hits: string[],
): boolean {
  const allowance = allowlist.get(filename)?.find((entry) => (
    entry.line === line && entry.tokens.includes(token)
  ));
  if (!allowance) return false;
  const key = exactButtonAllowanceKey(rule, filename, line, token);
  if (hits.includes(key)) return false;
  hits.push(key);
  return true;
}

function exactButtonAllowanceKeys(
  rule: ExactVisualAllowanceRule,
  allowlist: Map<string, readonly ExactButtonAllowance[]>,
): string[] {
  return Array.from(allowlist.entries()).flatMap(([filename, allowances]) => (
    allowances.flatMap(({ line, tokens }) => tokens.map((token) => (
      exactButtonAllowanceKey(rule, filename, line, token)
    )))
  ));
}

function buttonUtilityName(token: string): string {
  let utilityStart = 0;
  let squareDepth = 0;
  let roundDepth = 0;
  let curlyDepth = 0;
  for (let index = 0; index < token.length; index += 1) {
    const character = token[index];
    if (character === '\\') {
      index += 1;
      continue;
    }
    if (character === '[') squareDepth += 1;
    else if (character === ']') squareDepth = Math.max(0, squareDepth - 1);
    else if (character === '(') roundDepth += 1;
    else if (character === ')') roundDepth = Math.max(0, roundDepth - 1);
    else if (character === '{') curlyDepth += 1;
    else if (character === '}') curlyDepth = Math.max(0, curlyDepth - 1);
    else if (
      character === ':'
      && squareDepth === 0
      && roundDepth === 0
      && curlyDepth === 0
    ) {
      utilityStart = index + 1;
    }
  }
  return token.slice(utilityStart).replace(/^!/, '');
}

function appendButtonVisualOverrideViolations(
  filename: string,
  source: string,
  opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
  bindings: SharedButtonBindings,
  allowlistHits: string[],
  violations: DesignViolation[],
): void {
  if (!isSharedButtonOpening(opening, bindings)) return;
  const openingLine = lineNumberAt(source, opening.getStart(opening.getSourceFile()));
  const scan = classNameFragments(opening, sourceFile, initializers);
  for (const fragment of scan.fragments) {
    for (const token of fragment.text.split(/\s+/).filter(Boolean)) {
      if (!BUTTON_VISUAL_OVERRIDE_PATTERN.test(buttonUtilityName(token))) continue;
      if (consumeExactButtonAllowance(
        'button-visual-override',
        BUTTON_VISUAL_OVERRIDE_ALLOWLIST,
        filename,
        openingLine,
        token,
        allowlistHits,
      )) continue;
      violations.push({
        file: filename,
        line: lineNumberAt(source, fragment.index + fragment.text.indexOf(token)),
        rule: 'button-visual-override',
        token,
      });
    }
  }
  for (const unresolved of scan.unresolved) {
    violations.push({
      file: filename,
      line: lineNumberAt(source, unresolved.index),
      rule: 'button-visual-override',
      token: `dynamic:${unresolved.text}`,
    });
  }
}

function appendNonButtonControlVisualOverrideViolations(
  filename: string,
  source: string,
  opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
  bindings: SharedButtonBindings,
  violations: DesignViolation[],
): void {
  const controlName = NON_BUTTON_CONTROL_NAMES.find((name) => (
    isSharedButtonOpening(opening, bindings, name)
  ));
  if (!controlName) return;

  const overridePattern = controlName === 'IconButton'
    ? BUTTON_VISUAL_OVERRIDE_PATTERN
    : FIELD_CONTROL_VISUAL_OVERRIDE_PATTERN;
  const scan = classNameFragments(opening, sourceFile, initializers);
  for (const fragment of scan.fragments) {
    for (const token of fragment.text.split(/\s+/).filter(Boolean)) {
      if (!overridePattern.test(buttonUtilityName(token))) continue;
      violations.push({
        file: filename,
        line: lineNumberAt(source, fragment.index + fragment.text.indexOf(token)),
        rule: 'control-visual-override',
        token: `${controlName}:${token}`,
      });
    }
  }
}

function appendStateSurfaceVisualOverrideViolations(
  filename: string,
  source: string,
  opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
  bindings: SharedButtonBindings,
  allowlistHits: string[],
  violations: DesignViolation[],
): void {
  const componentName = STATE_SURFACE_COMPONENT_NAMES.find((name) => (
    isSharedButtonOpening(opening, bindings, name)
  ));
  if (!componentName) return;

  const openingLine = lineNumberAt(source, opening.getStart(opening.getSourceFile()));
  const scan = classNameFragments(opening, sourceFile, initializers);
  for (const fragment of scan.fragments) {
    for (const token of fragment.text.split(/\s+/).filter(Boolean)) {
      if (!STATE_SURFACE_VISUAL_OVERRIDE_PATTERN.test(buttonUtilityName(token))) continue;
      if (consumeExactButtonAllowance(
        'state-surface-visual-override',
        STATE_SURFACE_VISUAL_OVERRIDE_ALLOWLIST,
        filename,
        openingLine,
        token,
        allowlistHits,
      )) continue;
      violations.push({
        file: filename,
        line: lineNumberAt(source, fragment.index + fragment.text.indexOf(token)),
        rule: 'state-surface-visual-override',
        token: `${componentName}:${token}`,
      });
    }
  }
  for (const unresolved of scan.unresolved) {
    const token = `dynamic:${unresolved.text}`;
    if (consumeExactButtonAllowance(
      'state-surface-visual-override',
      STATE_SURFACE_VISUAL_OVERRIDE_ALLOWLIST,
      filename,
      openingLine,
      token,
      allowlistHits,
    )) continue;
    violations.push({
      file: filename,
      line: lineNumberAt(source, unresolved.index),
      rule: 'state-surface-visual-override',
      token: `${componentName}:${token}`,
    });
  }

  const styleScan = stylePropertyFragments(opening, sourceFile, initializers);
  for (const fragment of styleScan.fragments) {
    const property = fragment.text.replace(/[A-Z]/g, (character) => `-${character.toLowerCase()}`);
    if (!STATE_SURFACE_INLINE_STYLE_PROPERTY_PATTERN.test(property)) continue;
    const token = `style:${fragment.text}`;
    if (consumeExactButtonAllowance(
      'state-surface-visual-override',
      STATE_SURFACE_VISUAL_OVERRIDE_ALLOWLIST,
      filename,
      openingLine,
      token,
      allowlistHits,
    )) continue;
    violations.push({
      file: filename,
      line: lineNumberAt(source, fragment.index),
      rule: 'state-surface-visual-override',
      token: `${componentName}:${token}`,
    });
  }
  for (const unresolved of styleScan.unresolved) {
    const token = `style:dynamic:${unresolved.text}`;
    if (consumeExactButtonAllowance(
      'state-surface-visual-override',
      STATE_SURFACE_VISUAL_OVERRIDE_ALLOWLIST,
      filename,
      openingLine,
      token,
      allowlistHits,
    )) continue;
    violations.push({
      file: filename,
      line: lineNumberAt(source, unresolved.index),
      rule: 'state-surface-visual-override',
      token: `${componentName}:${token}`,
    });
  }
}

function bindingIdentifiers(name: ts.BindingName): ts.Identifier[] {
  if (ts.isIdentifier(name)) {
    return [name];
  }
  return name.elements.flatMap((element) => (
    ts.isOmittedExpression(element) ? [] : bindingIdentifiers(element.name)
  ));
}

function collectStaticInitializers(sourceFile: ts.SourceFile): StaticInitializerMap {
  const initializers: StaticInitializerMap = new Map();
  const register = (name: string, initializer: ts.Expression | null): void => {
    if (initializers.has(name)) {
      initializers.set(name, null);
      return;
    }
    initializers.set(name, initializer);
  };
  const visit = (node: ts.Node): void => {
    if (ts.isVariableDeclaration(node)) {
      const isUniqueConstInitializer = ts.isIdentifier(node.name)
        && Boolean(node.initializer)
        && ts.isVariableDeclarationList(node.parent)
        && (node.parent.flags & ts.NodeFlags.Const) !== 0;
      for (const identifier of bindingIdentifiers(node.name)) {
        register(
          identifier.text,
          isUniqueConstInitializer ? (node.initializer ?? null) : null,
        );
      }
    } else if (ts.isParameter(node)) {
      for (const identifier of bindingIdentifiers(node.name)) {
        register(identifier.text, null);
      }
    } else if (
      (ts.isFunctionDeclaration(node)
        || ts.isFunctionExpression(node)
        || ts.isClassDeclaration(node)
        || ts.isClassExpression(node)
        || ts.isEnumDeclaration(node))
      && node.name
    ) {
      register(node.name.text, null);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return initializers;
}

function mergeStaticClassScans(...scans: StaticClassScan[]): StaticClassScan {
  return scans.reduce<StaticClassScan>((result, scan) => ({
    fragments: [...result.fragments, ...scan.fragments],
    unresolved: [...result.unresolved, ...scan.unresolved],
  }), { fragments: [], unresolved: [] });
}

function staticClassFragment(
  node: ts.Identifier | ts.StringLiteralLike | ts.NumericLiteral | ts.TemplateLiteralLikeNode,
  sourceFile: ts.SourceFile,
): StaticClassScan {
  return {
    fragments: [{ index: node.getStart(sourceFile) + 1, text: node.text }],
    unresolved: [],
  };
}

function unresolvedClassExpression(
  expression: ts.Node,
  sourceFile: ts.SourceFile,
  label?: string,
): StaticClassScan {
  return {
    fragments: [],
    unresolved: [{
      index: expression.getStart(sourceFile),
      text: label ?? expression.getText(sourceFile),
    }],
  };
}

function unresolvedSpreadExpression(
  expression: ts.Expression,
  sourceFile: ts.SourceFile,
  label: string,
): StaticClassScan {
  return unresolvedClassExpression(
    expression,
    sourceFile,
    `${label}:${expression.getText(sourceFile)}`,
  );
}

function isFunctionScope(node: ts.Node): boolean {
  return ts.isFunctionDeclaration(node)
    || ts.isFunctionExpression(node)
    || ts.isArrowFunction(node)
    || ts.isMethodDeclaration(node)
    || ts.isGetAccessorDeclaration(node)
    || ts.isSetAccessorDeclaration(node)
    || ts.isConstructorDeclaration(node);
}

function nearestBindingScope(
  node: ts.Node,
  predicate: (candidate: ts.Node) => boolean,
): ts.Node | undefined {
  let current = node.parent;
  while (current) {
    if (predicate(current)) {
      return current;
    }
    current = current.parent;
  }
  return undefined;
}

function isBlockBindingScope(node: ts.Node): boolean {
  return ts.isSourceFile(node)
    || ts.isBlock(node)
    || ts.isModuleBlock(node)
    || ts.isCaseBlock(node)
    || ts.isClassStaticBlockDeclaration(node);
}

function bindingScope(node: ts.Node): ts.Node | undefined {
  if (ts.isParameter(node)) {
    return node.parent;
  }
  if (ts.isFunctionExpression(node) || ts.isClassExpression(node)) {
    return node;
  }
  if (
    ts.isFunctionDeclaration(node)
    || ts.isClassDeclaration(node)
    || ts.isEnumDeclaration(node)
  ) {
    return nearestBindingScope(node, isBlockBindingScope);
  }
  if (!ts.isVariableDeclaration(node)) {
    return undefined;
  }
  if (ts.isCatchClause(node.parent)) {
    return node.parent;
  }
  const declarationList = node.parent;
  if (!ts.isVariableDeclarationList(declarationList)) {
    return undefined;
  }
  if ((declarationList.flags & ts.NodeFlags.BlockScoped) === 0) {
    return nearestBindingScope(declarationList, (candidate) => (
      ts.isSourceFile(candidate) || isFunctionScope(candidate)
    ));
  }
  const declarationOwner = declarationList.parent;
  if (
    ts.isForStatement(declarationOwner)
    || ts.isForInStatement(declarationOwner)
    || ts.isForOfStatement(declarationOwner)
  ) {
    return declarationOwner;
  }
  return nearestBindingScope(declarationList, isBlockBindingScope);
}

function declarationBindsIdentifier(node: ts.Node, identifier: string): boolean {
  if (ts.isVariableDeclaration(node) || ts.isParameter(node)) {
    return bindingIdentifiers(node.name).some(({ text }) => text === identifier);
  }
  return (
    ts.isFunctionDeclaration(node)
    || ts.isFunctionExpression(node)
    || ts.isClassDeclaration(node)
    || ts.isClassExpression(node)
    || ts.isEnumDeclaration(node)
  ) && node.name?.text === identifier;
}

function isLexicallyShadowedComposer(
  callee: ts.Identifier,
  sourceFile: ts.SourceFile,
): boolean {
  const callsite = callee.getStart(sourceFile);
  let isShadowed = false;
  const visit = (node: ts.Node): void => {
    if (isShadowed) return;
    if (declarationBindsIdentifier(node, callee.text)) {
      const scope = bindingScope(node);
      if (scope && scope.getStart(sourceFile) <= callsite && callsite < scope.end) {
        isShadowed = true;
        return;
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return isShadowed;
}

function isClassComposerCall(
  expression: ts.CallExpression,
  sourceFile: ts.SourceFile,
): boolean {
  const callee = unwrapExpression(expression.expression);
  if (!ts.isIdentifier(callee) || isLexicallyShadowedComposer(callee, sourceFile)) {
    return false;
  }
  return ['cn', 'clsx', 'classNames', 'classnames', 'twMerge'].includes(callee.text);
}

function combineStaticClassStrings(
  left: string[],
  right: string[],
): string[] | undefined {
  if (left.length * right.length > 64) {
    return undefined;
  }
  return left.flatMap((prefix) => right.map((suffix) => prefix + suffix));
}

function resolveStaticClassStrings(
  expression: ts.Expression,
  initializers: StaticInitializerMap,
  resolving: Set<string>,
): string[] | undefined {
  const current = unwrapExpression(expression);
  if (ts.isStringLiteral(current) || ts.isNoSubstitutionTemplateLiteral(current)) {
    return [current.text];
  }
  if (ts.isIdentifier(current)) {
    const initializer = initializers.get(current.text);
    if (!initializer || resolving.has(current.text)) {
      return undefined;
    }
    const nextResolving = new Set(resolving);
    nextResolving.add(current.text);
    return resolveStaticClassStrings(initializer, initializers, nextResolving);
  }
  if (ts.isTemplateExpression(current)) {
    let results = [current.head.text];
    for (const span of current.templateSpans) {
      const values = resolveStaticClassStrings(span.expression, initializers, resolving);
      if (values === undefined) {
        return undefined;
      }
      const combined = combineStaticClassStrings(
        results,
        values.map((value) => value + span.literal.text),
      );
      if (combined === undefined) {
        return undefined;
      }
      results = combined;
    }
    return results;
  }
  if (ts.isConditionalExpression(current)) {
    const whenTrue = resolveStaticClassStrings(current.whenTrue, initializers, resolving);
    const whenFalse = resolveStaticClassStrings(current.whenFalse, initializers, resolving);
    return whenTrue === undefined || whenFalse === undefined
      ? undefined
      : [...whenTrue, ...whenFalse];
  }
  if (
    ts.isBinaryExpression(current)
    && current.operatorToken.kind === ts.SyntaxKind.PlusToken
  ) {
    const left = resolveStaticClassStrings(current.left, initializers, resolving);
    const right = resolveStaticClassStrings(current.right, initializers, resolving);
    return left === undefined || right === undefined
      ? undefined
      : combineStaticClassStrings(left, right);
  }
  return undefined;
}

function scanObjectClassNames(
  expression: ts.ObjectLiteralExpression,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
  resolving: Set<string>,
): StaticClassScan {
  return mergeStaticClassScans(...expression.properties.map((property) => {
    if (ts.isSpreadAssignment(property)) {
      return unresolvedClassExpression(property.expression, sourceFile);
    }
    if (ts.isShorthandPropertyAssignment(property)) {
      return staticClassFragment(property.name, sourceFile);
    }
    if (ts.isPropertyAssignment(property)) {
      if (ts.isComputedPropertyName(property.name)) {
        return scanStaticClassExpression(
          property.name.expression,
          sourceFile,
          initializers,
          resolving,
        );
      }
      if (
        ts.isIdentifier(property.name)
        || ts.isStringLiteral(property.name)
        || ts.isNumericLiteral(property.name)
      ) {
        return staticClassFragment(property.name, sourceFile);
      }
    }
    return unresolvedClassExpression(property, sourceFile);
  }));
}

function scanStaticClassExpression(
  expression: ts.Expression,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
  resolving: Set<string> = new Set(),
  unresolvedLabel?: string,
): StaticClassScan {
  const current = unwrapExpression(expression);
  const staticStrings = resolveStaticClassStrings(current, initializers, resolving);
  if (staticStrings !== undefined) {
    return {
      fragments: staticStrings.map((text) => ({ index: current.getStart(sourceFile), text })),
      unresolved: [],
    };
  }

  if (ts.isIdentifier(current)) {
    if (current.text === 'undefined') {
      return { fragments: [], unresolved: [] };
    }
    const initializer = initializers.get(current.text);
    if (!initializer || resolving.has(current.text)) {
      return unresolvedClassExpression(current, sourceFile, unresolvedLabel);
    }
    const nextResolving = new Set(resolving);
    nextResolving.add(current.text);
    return scanStaticClassExpression(
      initializer,
      sourceFile,
      initializers,
      nextResolving,
      unresolvedLabel,
    );
  }

  if (ts.isTemplateExpression(current)) {
    return mergeStaticClassScans(
      staticClassFragment(current.head, sourceFile),
      ...current.templateSpans.flatMap((span) => [
        scanStaticClassExpression(span.expression, sourceFile, initializers, resolving),
        staticClassFragment(span.literal, sourceFile),
      ]),
    );
  }

  if (ts.isConditionalExpression(current)) {
    return mergeStaticClassScans(
      scanStaticClassExpression(current.whenTrue, sourceFile, initializers, resolving),
      scanStaticClassExpression(current.whenFalse, sourceFile, initializers, resolving),
    );
  }

  if (ts.isBinaryExpression(current)) {
    if (
      current.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken
      || current.operatorToken.kind === ts.SyntaxKind.CommaToken
    ) {
      return scanStaticClassExpression(current.right, sourceFile, initializers, resolving);
    }
    if ([
      ts.SyntaxKind.BarBarToken,
      ts.SyntaxKind.QuestionQuestionToken,
      ts.SyntaxKind.PlusToken,
    ].includes(current.operatorToken.kind)) {
      return mergeStaticClassScans(
        scanStaticClassExpression(current.left, sourceFile, initializers, resolving),
        scanStaticClassExpression(current.right, sourceFile, initializers, resolving),
      );
    }
    return unresolvedClassExpression(current, sourceFile, unresolvedLabel);
  }

  if (ts.isCallExpression(current)) {
    if (!isClassComposerCall(current, sourceFile)) {
      return unresolvedClassExpression(current, sourceFile, unresolvedLabel);
    }
    return mergeStaticClassScans(...current.arguments.map((argument) => (
      ts.isSpreadElement(argument)
        ? unresolvedClassExpression(argument.expression, sourceFile)
        : scanStaticClassExpression(argument, sourceFile, initializers, resolving)
    )));
  }

  if (ts.isArrayLiteralExpression(current)) {
    return mergeStaticClassScans(...current.elements.map((element) => (
      ts.isOmittedExpression(element)
        ? { fragments: [], unresolved: [] }
        : ts.isSpreadElement(element)
          ? unresolvedClassExpression(element.expression, sourceFile)
          : scanStaticClassExpression(element, sourceFile, initializers, resolving)
    )));
  }

  if (ts.isObjectLiteralExpression(current)) {
    return scanObjectClassNames(current, sourceFile, initializers, resolving);
  }

  if (
    ts.isNumericLiteral(current)
    || ts.isBigIntLiteral(current)
    || current.kind === ts.SyntaxKind.TrueKeyword
    || current.kind === ts.SyntaxKind.FalseKeyword
    || current.kind === ts.SyntaxKind.NullKeyword
    || ts.isPrefixUnaryExpression(current)
    || ts.isVoidExpression(current)
    || ts.isTypeOfExpression(current)
  ) {
    return { fragments: [], unresolved: [] };
  }

  return unresolvedClassExpression(current, sourceFile, unresolvedLabel);
}

function classNameFragments(
  opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
): StaticClassScan {
  const properties = opening.attributes.properties;
  let classNameIndex = -1;
  for (let index = properties.length - 1; index >= 0; index -= 1) {
    const property = properties[index];
    if (ts.isJsxAttribute(property) && property.name.getText() === 'className') {
      classNameIndex = index;
      break;
    }
  }
  let className: ts.JsxAttribute | undefined;
  if (classNameIndex >= 0) {
    const candidate = properties[classNameIndex];
    if (ts.isJsxAttribute(candidate)) {
      className = candidate;
    }
  }
  const trailingSpreads = properties
    .slice(classNameIndex + 1)
    .filter((property): property is ts.JsxSpreadAttribute => ts.isJsxSpreadAttribute(property))
    .map((property) => unresolvedSpreadExpression(property.expression, sourceFile, 'className spread'));
  if (!className) {
    return mergeStaticClassScans(...trailingSpreads);
  }
  let explicitClassName: StaticClassScan;
  if (!className.initializer) {
    explicitClassName = {
      fragments: [],
      unresolved: [{ index: className.getStart(sourceFile), text: 'className' }],
    };
  } else if (ts.isStringLiteral(className.initializer)) {
    explicitClassName = {
      fragments: [{
        index: className.initializer.getStart(sourceFile) + 1,
        text: className.initializer.text,
      }],
      unresolved: [],
    };
  } else if (!ts.isJsxExpression(className.initializer) || !className.initializer.expression) {
    explicitClassName = {
      fragments: [],
      unresolved: [{ index: className.initializer.getStart(sourceFile), text: 'className' }],
    };
  } else {
    explicitClassName = scanStaticClassExpression(
      className.initializer.expression,
      sourceFile,
      initializers,
      new Set(),
      'className',
    );
  }
  return mergeStaticClassScans(explicitClassName, ...trailingSpreads);
}

function scanStaticStyleExpression(
  expression: ts.Expression,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
  resolving: Set<string> = new Set(),
): StaticClassScan {
  const current = unwrapExpression(expression);
  if (ts.isIdentifier(current)) {
    if (current.text === 'undefined') {
      return { fragments: [], unresolved: [] };
    }
    const initializer = initializers.get(current.text);
    if (!initializer || resolving.has(current.text)) {
      return unresolvedClassExpression(current, sourceFile, 'style');
    }
    const nextResolving = new Set(resolving);
    nextResolving.add(current.text);
    return scanStaticStyleExpression(initializer, sourceFile, initializers, nextResolving);
  }
  if (ts.isConditionalExpression(current)) {
    return mergeStaticClassScans(
      scanStaticStyleExpression(current.whenTrue, sourceFile, initializers, resolving),
      scanStaticStyleExpression(current.whenFalse, sourceFile, initializers, resolving),
    );
  }
  if (ts.isObjectLiteralExpression(current)) {
    return mergeStaticClassScans(...current.properties.map((property) => {
      if (ts.isSpreadAssignment(property)) {
        return unresolvedSpreadExpression(property.expression, sourceFile, 'style spread');
      }
      if (ts.isShorthandPropertyAssignment(property)) {
        return scanStaticStyleExpression(property.name, sourceFile, initializers, resolving);
      }
      if (ts.isPropertyAssignment(property)) {
        return scanStaticStyleExpression(property.initializer, sourceFile, initializers, resolving);
      }
      return unresolvedClassExpression(property, sourceFile, 'style');
    }));
  }
  return scanStaticClassExpression(
    current,
    sourceFile,
    initializers,
    resolving,
    'style',
  );
}

function styleFragments(
  opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
): StaticClassScan {
  const properties = opening.attributes.properties;
  let styleIndex = -1;
  for (let index = properties.length - 1; index >= 0; index -= 1) {
    const property = properties[index];
    if (ts.isJsxAttribute(property) && property.name.getText() === 'style') {
      styleIndex = index;
      break;
    }
  }
  const trailingSpreads = properties
    .slice(styleIndex + 1)
    .filter((property): property is ts.JsxSpreadAttribute => ts.isJsxSpreadAttribute(property))
    .map((property) => unresolvedSpreadExpression(property.expression, sourceFile, 'style spread'));
  if (styleIndex < 0) {
    return mergeStaticClassScans(...trailingSpreads);
  }
  const style = properties[styleIndex];
  if (!ts.isJsxAttribute(style) || !style.initializer) {
    return mergeStaticClassScans(
      unresolvedClassExpression(style, sourceFile, 'style'),
      ...trailingSpreads,
    );
  }
  if (ts.isStringLiteral(style.initializer)) {
    return mergeStaticClassScans(
      staticClassFragment(style.initializer, sourceFile),
      ...trailingSpreads,
    );
  }
  if (!ts.isJsxExpression(style.initializer) || !style.initializer.expression) {
    return mergeStaticClassScans(
      unresolvedClassExpression(style.initializer, sourceFile, 'style'),
      ...trailingSpreads,
    );
  }
  return mergeStaticClassScans(
    scanStaticStyleExpression(style.initializer.expression, sourceFile, initializers),
    ...trailingSpreads,
  );
}

function staticStylePropertyFragments(
  name: ts.PropertyName,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
): StaticClassScan {
  const names = propertyNameValues(name, initializers);
  if (!names) {
    return unresolvedClassExpression(name, sourceFile, 'style property');
  }
  return {
    fragments: names.map((text) => ({
      index: name.getStart(sourceFile),
      text,
    })),
    unresolved: [],
  };
}

function scanStaticStylePropertyExpression(
  expression: ts.Expression,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
  resolving: Set<string> = new Set(),
): StaticClassScan {
  const current = unwrapExpression(expression);
  if (ts.isIdentifier(current)) {
    if (current.text === 'undefined') {
      return { fragments: [], unresolved: [] };
    }
    const initializer = initializers.get(current.text);
    if (!initializer || resolving.has(current.text)) {
      return unresolvedClassExpression(current, sourceFile, 'style');
    }
    const nextResolving = new Set(resolving);
    nextResolving.add(current.text);
    return scanStaticStylePropertyExpression(
      initializer,
      sourceFile,
      initializers,
      nextResolving,
    );
  }
  if (ts.isConditionalExpression(current)) {
    return mergeStaticClassScans(
      scanStaticStylePropertyExpression(current.whenTrue, sourceFile, initializers, resolving),
      scanStaticStylePropertyExpression(current.whenFalse, sourceFile, initializers, resolving),
    );
  }
  if (ts.isBinaryExpression(current)) {
    if (
      current.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken
      || current.operatorToken.kind === ts.SyntaxKind.CommaToken
    ) {
      return scanStaticStylePropertyExpression(current.right, sourceFile, initializers, resolving);
    }
    if (
      current.operatorToken.kind === ts.SyntaxKind.BarBarToken
      || current.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken
    ) {
      return mergeStaticClassScans(
        scanStaticStylePropertyExpression(current.left, sourceFile, initializers, resolving),
        scanStaticStylePropertyExpression(current.right, sourceFile, initializers, resolving),
      );
    }
  }
  if (ts.isObjectLiteralExpression(current)) {
    return mergeStaticClassScans(...current.properties.map((property) => {
      if (ts.isSpreadAssignment(property)) {
        return scanStaticStylePropertyExpression(
          property.expression,
          sourceFile,
          initializers,
          resolving,
        );
      }
      if (ts.isShorthandPropertyAssignment(property) || ts.isPropertyAssignment(property)) {
        return staticStylePropertyFragments(property.name, sourceFile, initializers);
      }
      return unresolvedClassExpression(property, sourceFile, 'style property');
    }));
  }
  if (
    current.kind === ts.SyntaxKind.FalseKeyword
    || current.kind === ts.SyntaxKind.NullKeyword
    || ts.isVoidExpression(current)
  ) {
    return { fragments: [], unresolved: [] };
  }
  return unresolvedClassExpression(current, sourceFile, 'style');
}

function stylePropertyFragments(
  opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
): StaticClassScan {
  const properties = opening.attributes.properties;
  let styleIndex = -1;
  for (let index = properties.length - 1; index >= 0; index -= 1) {
    const property = properties[index];
    if (ts.isJsxAttribute(property) && property.name.getText() === 'style') {
      styleIndex = index;
      break;
    }
  }
  const trailingSpreads = properties
    .slice(styleIndex + 1)
    .filter((property): property is ts.JsxSpreadAttribute => ts.isJsxSpreadAttribute(property))
    .map((property) => unresolvedSpreadExpression(property.expression, sourceFile, 'style spread'));
  if (styleIndex < 0) {
    return mergeStaticClassScans(...trailingSpreads);
  }
  const style = properties[styleIndex];
  if (
    !ts.isJsxAttribute(style)
    || !style.initializer
    || !ts.isJsxExpression(style.initializer)
    || !style.initializer.expression
  ) {
    return mergeStaticClassScans(
      unresolvedClassExpression(style, sourceFile, 'style'),
      ...trailingSpreads,
    );
  }
  return mergeStaticClassScans(
    scanStaticStylePropertyExpression(style.initializer.expression, sourceFile, initializers),
    ...trailingSpreads,
  );
}

function primaryButtonEffectFragments(
  root: ts.JsxElement | ts.JsxSelfClosingElement,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
  bindings: SharedButtonBindings,
): PrimaryCtaEffectScan {
  const result: PrimaryCtaEffectScan = {
    classNames: { fragments: [], unresolved: [] },
    styles: { fragments: [], unresolved: [] },
  };
  const append = (opening: ts.JsxOpeningElement | ts.JsxSelfClosingElement): void => {
    const classScan = classNameFragments(opening, sourceFile, initializers);
    const styleScan = styleFragments(opening, sourceFile, initializers);
    result.classNames.fragments.push(...classScan.fragments);
    result.classNames.unresolved.push(...classScan.unresolved);
    result.styles.fragments.push(...styleScan.fragments);
    result.styles.unresolved.push(...styleScan.unresolved);
  };
  const visit = (node: ts.Node, isRoot = false): void => {
    if (ts.isJsxElement(node)) {
      if (!isRoot && isSharedButtonOpening(node.openingElement, bindings)) {
        return;
      }
      append(node.openingElement);
      node.children.forEach((child) => visit(child));
      return;
    }
    if (ts.isJsxSelfClosingElement(node)) {
      if (isRoot || !isSharedButtonOpening(node, bindings)) {
        append(node);
      }
      return;
    }
    ts.forEachChild(node, (child) => visit(child));
  };
  visit(root, true);
  return result;
}

function appendPrimaryClassViolations(
  filename: string,
  source: string,
  fragments: StaticClassFragment[],
  violations: DesignViolation[],
): void {
  for (const fragment of fragments) {
    for (const [rule, pattern] of [
      ['primary-cta-gradient', PRIMARY_CTA_GRADIENT_PATTERN],
      ['primary-cta-shimmer', PRIMARY_CTA_SHIMMER_PATTERN],
    ] as const) {
      const match = fragment.text.match(pattern);
      if (!match) continue;
      violations.push({
        file: filename,
        line: lineNumberAt(source, fragment.index + (match.index ?? 0)),
        rule,
        token: match[0],
      });
    }
  }
}

type ButtonSizeStyleEntry = {
  index: number;
  fragments: StaticClassFragment[];
};

type SurfaceLevelStyleEntry = ButtonSizeStyleEntry;

function surfaceLevelClasses(fragments: StaticClassFragment[]): string[] {
  return Array.from(new Set(
    fragments.flatMap(({ text }) => text.split(/\s+/).filter(Boolean).map(buttonUtilityName)),
  ));
}

function appendSurfaceLevelContractViolations(
  filename: string,
  source: string,
  declarationIndex: number,
  entries: Map<string, SurfaceLevelStyleEntry>,
  violations: DesignViolation[],
): void {
  const report = (level: string, entry: SurfaceLevelStyleEntry | undefined, token: string): void => {
    violations.push({
      file: filename,
      line: lineNumberAt(source, entry?.index ?? declarationIndex),
      rule: 'surface-level-contract',
      token: `${level}:${token}`,
    });
  };
  const classesFor = (level: string): string[] => surfaceLevelClasses(entries.get(level)?.fragments ?? []);
  const semanticClasses = (classes: string[], prefix: 'bg' | 'border' | 'shadow'): string[] => (
    classes.filter((token) => token === prefix || token.startsWith(`${prefix}-`))
  );
  const enforceExactClasses = (
    level: string,
    kind: 'background' | 'border' | 'shadow',
    actual: string[],
    expected: readonly string[],
  ): void => {
    for (const token of expected) {
      if (!actual.includes(token)) report(level, entries.get(level), `${kind}:${token}:missing`);
    }
    for (const token of actual) {
      if (!expected.includes(token)) report(level, entries.get(level), token);
    }
  };

  for (const level of ['canvas', 'section', 'interactive', 'overlay']) {
    if (!entries.has(level)) report(level, undefined, 'missing');
  }

  const canvas = classesFor('canvas');
  enforceExactClasses('canvas', 'background', semanticClasses(canvas, 'bg'), ['bg-transparent']);
  for (const token of canvas.filter((entry) => /^(?:border(?:-|$)|shadow(?:-|$)|rounded(?:-|$))/.test(entry))) {
    report('canvas', entries.get('canvas'), token);
  }

  const section = classesFor('section');
  enforceExactClasses('section', 'background', semanticClasses(section, 'bg'), ['bg-card']);
  enforceExactClasses('section', 'border', semanticClasses(section, 'border'), []);
  enforceExactClasses('section', 'shadow', semanticClasses(section, 'shadow'), []);

  const interactive = classesFor('interactive');
  enforceExactClasses('interactive', 'background', semanticClasses(interactive, 'bg'), ['bg-card']);
  enforceExactClasses('interactive', 'border', semanticClasses(interactive, 'border'), ['border', 'border-border']);
  enforceExactClasses('interactive', 'shadow', semanticClasses(interactive, 'shadow'), []);

  const overlay = classesFor('overlay');
  enforceExactClasses('overlay', 'background', semanticClasses(overlay, 'bg'), ['bg-elevated']);
  enforceExactClasses('overlay', 'border', semanticClasses(overlay, 'border'), ['border', 'border-border']);
  enforceExactClasses('overlay', 'shadow', semanticClasses(overlay, 'shadow'), ['shadow-soft-card-strong']);
}

function buttonHeightClasses(fragments: StaticClassFragment[]): string[] {
  return Array.from(new Set(
    fragments.flatMap(({ text }) => text.split(/\s+/).filter((token) => BUTTON_HEIGHT_CLASS_PATTERN.test(token))),
  ));
}

function buttonRadiusClasses(fragments: StaticClassFragment[]): string[] {
  return Array.from(new Set(
    fragments.flatMap(({ text }) => text.split(/\s+/).filter((token) => BUTTON_RADIUS_CLASS_PATTERN.test(token))),
  ));
}

function appendButtonSizeContractViolations(
  filename: string,
  source: string,
  declarationIndex: number,
  entries: Map<string, ButtonSizeStyleEntry>,
  violations: DesignViolation[],
): void {
  for (const entry of entries.values()) {
    const radii = buttonRadiusClasses(entry.fragments);
    if (radii.length === 1 && radii[0] === 'rounded-lg') continue;
    violations.push({
      file: filename,
      line: lineNumberAt(source, entry.index),
      rule: 'button-shape',
      token: radii.join('|') || 'rounded:missing',
    });
  }

  for (const [size, expectedHeight] of Object.entries(BUTTON_CANONICAL_SIZE_HEIGHTS)) {
    const entry = entries.get(size);
    const heights = entry ? buttonHeightClasses(entry.fragments) : [];
    if (heights.length === 1 && heights[0] === expectedHeight) continue;
    violations.push({
      file: filename,
      line: lineNumberAt(source, entry?.index ?? declarationIndex),
      rule: 'button-size-contract',
      token: `${size}:${heights.join('|') || 'missing'}`,
    });
  }

  for (const [size, entry] of entries) {
    if (size in BUTTON_CANONICAL_SIZE_HEIGHTS) continue;
    const heights = buttonHeightClasses(entry.fragments);
    if (BUTTON_LEGACY_SIZE_ALIASES.has(size)) {
      violations.push({
        file: filename,
        line: lineNumberAt(source, entry.index),
        rule: 'button-size-contract',
        token: `${size}:legacy`,
      });
      continue;
    }
    const compatibleHeight = BUTTON_COMPAT_SIZE_HEIGHTS[
      size as keyof typeof BUTTON_COMPAT_SIZE_HEIGHTS
    ];
    if (compatibleHeight && heights.length === 1 && heights[0] === compatibleHeight) continue;
    violations.push({
      file: filename,
      line: lineNumberAt(source, entry.index),
      rule: 'button-size-contract',
      token: `${size}:${heights.join('|') || 'missing'}`,
    });
  }
}

function appendPrimaryStyleViolations(
  filename: string,
  source: string,
  fragments: StaticClassFragment[],
  violations: DesignViolation[],
): void {
  for (const fragment of fragments) {
    for (const [rule, pattern] of [
      ['primary-cta-gradient', PRIMARY_INLINE_GRADIENT_PATTERN],
      ['primary-cta-shimmer', PRIMARY_INLINE_SHIMMER_PATTERN],
    ] as const) {
      const match = fragment.text.match(pattern);
      if (!match) continue;
      violations.push({
        file: filename,
        line: lineNumberAt(source, fragment.index + (match.index ?? 0)),
        rule,
        token: match[0],
      });
    }
  }
}

function appendUnresolvedPrimaryClassViolations(
  filename: string,
  source: string,
  unresolved: StaticClassFragment[],
  violations: DesignViolation[],
): void {
  for (const expression of unresolved) {
    violations.push({
      file: filename,
      line: lineNumberAt(source, expression.index),
      rule: 'primary-cta-unresolved-class',
      token: expression.text,
    });
  }
}

function propertyNameValues(
  name: ts.PropertyName,
  initializers: StaticInitializerMap,
): string[] | undefined {
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)) {
    return [name.text];
  }
  if (ts.isComputedPropertyName(name)) {
    return resolveStaticClassStrings(name.expression, initializers, new Set());
  }
  return undefined;
}

function scanFinalObjectClassValue(
  expression: ts.ObjectLiteralExpression,
  propertyName: string,
  sourceFile: ts.SourceFile,
  initializers: StaticInitializerMap,
): { matched: boolean; scan: StaticClassScan } {
  const label = `BUTTON_VARIANT_STYLES.${propertyName}`;
  for (let index = expression.properties.length - 1; index >= 0; index -= 1) {
    const property = expression.properties[index];
    if (ts.isSpreadAssignment(property)) {
      return {
        matched: false,
        scan: unresolvedClassExpression(property.expression, sourceFile, label),
      };
    }
    const names = propertyNameValues(property.name, initializers);
    if (names === undefined) {
      return {
        matched: false,
        scan: unresolvedClassExpression(property, sourceFile, label),
      };
    }
    if (!names.includes(propertyName)) {
      continue;
    }
    if (ts.isPropertyAssignment(property)) {
      return {
        matched: true,
        scan: scanStaticClassExpression(
          property.initializer,
          sourceFile,
          initializers,
          new Set(),
          label,
        ),
      };
    }
    if (ts.isShorthandPropertyAssignment(property)) {
      return {
        matched: true,
        scan: scanStaticClassExpression(
          property.name,
          sourceFile,
          initializers,
          new Set(),
          label,
        ),
      };
    }
    return {
      matched: true,
      scan: unresolvedClassExpression(property, sourceFile, label),
    };
  }
  return {
    matched: false,
    scan: unresolvedClassExpression(expression, sourceFile, label),
  };
}

type BoundSourceFile = {
  sourceFile: ts.SourceFile;
  checker: ts.TypeChecker;
};

type SourceEntry = readonly [filename: string, source: string];

function createBoundSourceFiles(sources: readonly SourceEntry[]): Map<string, BoundSourceFile> {
  const compilerOptions = {
    jsx: ts.JsxEmit.Preserve,
    module: ts.ModuleKind.ESNext,
    noLib: true,
    noResolve: true,
    target: ts.ScriptTarget.Latest,
  } satisfies ts.CompilerOptions;
  const virtualSources = new Map(sources.map(([filename, source], index) => {
    const virtualFilename = `/production-design-guard/${index}.tsx`;
    return [virtualFilename, {
      filename,
      source,
      sourceFile: ts.createSourceFile(
        virtualFilename,
        source,
        ts.ScriptTarget.Latest,
        true,
        ts.ScriptKind.TSX,
      ),
    }] as const;
  }));
  const host = ts.createCompilerHost(compilerOptions, true);
  host.fileExists = (filename) => virtualSources.has(filename);
  host.readFile = (filename) => virtualSources.get(filename)?.source;
  host.getSourceFile = (filename) => virtualSources.get(filename)?.sourceFile;
  const program = ts.createProgram(Array.from(virtualSources.keys()), compilerOptions, host);
  const checker = program.getTypeChecker();
  const boundSources = new Map<string, BoundSourceFile>();
  for (const [virtualFilename, entry] of virtualSources) {
    const sourceFile = program.getSourceFile(virtualFilename);
    if (!sourceFile) {
      throw new Error(`Production design guard could not bind ${entry.filename}.`);
    }
    if (boundSources.has(entry.filename)) {
      throw new Error(`Production design guard received duplicate source ${entry.filename}.`);
    }
    boundSources.set(entry.filename, { sourceFile, checker });
  }
  return boundSources;
}

function createBoundSourceFile(source: string): BoundSourceFile {
  const filename = 'fixture.tsx';
  const boundSource = createBoundSourceFiles([[filename, source]]).get(filename);
  if (!boundSource) {
    throw new Error('Production design guard could not bind the source file.');
  }
  return boundSource;
}

function scanPrimaryCtasInBoundSource(
  filename: string,
  source: string,
  { sourceFile, checker }: BoundSourceFile,
): PrimaryCtaScan {
  const initializers = collectStaticInitializers(sourceFile);
  const buttonBindings: SharedButtonBindings = { checker };
  const result: PrimaryCtaScan = {
    matchedButtons: 0,
    matchedSharedStyles: 0,
    matchedSurfaceLevelStyles: 0,
    allowlistHits: [],
    violations: [],
  };
  const appendEffects = (effects: PrimaryCtaEffectScan): void => {
    appendPrimaryClassViolations(
      filename,
      source,
      effects.classNames.fragments,
      result.violations,
    );
    appendPrimaryStyleViolations(
      filename,
      source,
      effects.styles.fragments,
      result.violations,
    );
    appendUnresolvedPrimaryClassViolations(
      filename,
      source,
      [...effects.classNames.unresolved, ...effects.styles.unresolved],
      result.violations,
    );
  };
  const visit = (node: ts.Node): void => {
    if (ts.isJsxElement(node)) {
      appendOverlayComponentContractViolations(
        filename,
        source,
        node.openingElement,
        buttonBindings,
        result.violations,
      );
      appendButtonSizeUsageViolations(
        filename,
        source,
        node.openingElement,
        buttonBindings,
        result.allowlistHits,
        result.violations,
      );
      appendButtonVisualOverrideViolations(
        filename,
        source,
        node.openingElement,
        sourceFile,
        initializers,
        buttonBindings,
        result.allowlistHits,
        result.violations,
      );
      appendNonButtonControlVisualOverrideViolations(
        filename,
        source,
        node.openingElement,
        sourceFile,
        initializers,
        buttonBindings,
        result.violations,
      );
      appendStateSurfaceVisualOverrideViolations(
        filename,
        source,
        node.openingElement,
        sourceFile,
        initializers,
        buttonBindings,
        result.allowlistHits,
        result.violations,
      );
      appendButtonIconOnlyViolation(
        filename,
        source,
        node,
        initializers,
        buttonBindings,
        result.violations,
      );
      if (isPrimaryButtonOpening(node.openingElement, buttonBindings)) {
        result.matchedButtons += 1;
        appendEffects(primaryButtonEffectFragments(node, sourceFile, initializers, buttonBindings));
      }
    } else if (ts.isJsxSelfClosingElement(node)) {
      appendOverlayComponentContractViolations(
        filename,
        source,
        node,
        buttonBindings,
        result.violations,
      );
      appendButtonSizeUsageViolations(
        filename,
        source,
        node,
        buttonBindings,
        result.allowlistHits,
        result.violations,
      );
      appendButtonVisualOverrideViolations(
        filename,
        source,
        node,
        sourceFile,
        initializers,
        buttonBindings,
        result.allowlistHits,
        result.violations,
      );
      appendNonButtonControlVisualOverrideViolations(
        filename,
        source,
        node,
        sourceFile,
        initializers,
        buttonBindings,
        result.violations,
      );
      appendStateSurfaceVisualOverrideViolations(
        filename,
        source,
        node,
        sourceFile,
        initializers,
        buttonBindings,
        result.allowlistHits,
        result.violations,
      );
      if (isPrimaryButtonOpening(node, buttonBindings)) {
        result.matchedButtons += 1;
        appendEffects(primaryButtonEffectFragments(node, sourceFile, initializers, buttonBindings));
      }
    }

    if (
      ts.isVariableDeclaration(node)
      && ts.isIdentifier(node.name)
      && node.name.text === 'BUTTON_VARIANT_STYLES'
      && node.initializer
    ) {
      const initializer = unwrapExpression(node.initializer);
      if (ts.isObjectLiteralExpression(initializer)) {
        for (const variant of PRIMARY_CTA_VARIANTS) {
          const finalValue = scanFinalObjectClassValue(
            initializer,
            variant,
            sourceFile,
            initializers,
          );
          if (finalValue.matched) {
            result.matchedSharedStyles += 1;
          }
          appendPrimaryClassViolations(
            filename,
            source,
            finalValue.scan.fragments,
            result.violations,
          );
          appendUnresolvedPrimaryClassViolations(
            filename,
            source,
            finalValue.scan.unresolved,
            result.violations,
          );
        }
      } else {
        appendUnresolvedPrimaryClassViolations(
          filename,
          source,
          [unresolvedClassExpression(
            initializer,
            sourceFile,
            'BUTTON_VARIANT_STYLES',
          ).unresolved[0]],
          result.violations,
        );
      }
    }
    if (
      ts.isVariableDeclaration(node)
      && ts.isIdentifier(node.name)
      && node.name.text === 'BUTTON_SIZE_STYLES'
      && node.initializer
    ) {
      const initializer = unwrapExpression(node.initializer);
      if (ts.isObjectLiteralExpression(initializer)) {
        const entries = new Map<string, ButtonSizeStyleEntry>();
        for (const property of initializer.properties) {
          if (!ts.isPropertyAssignment(property)) continue;
          const scan = scanStaticClassExpression(
            property.initializer,
            sourceFile,
            initializers,
            new Set(),
            'BUTTON_SIZE_STYLES',
          );
          const names = propertyNameValues(property.name, initializers);
          if (names?.length === 1) {
            entries.set(names[0], {
              index: property.getStart(sourceFile),
              fragments: scan.fragments,
            });
          }
        }
        appendButtonSizeContractViolations(
          filename,
          source,
          node.getStart(sourceFile),
          entries,
          result.violations,
        );
      }
    }
    if (
      ts.isVariableDeclaration(node)
      && ts.isIdentifier(node.name)
      && node.name.text === 'SURFACE_LEVEL_STYLES'
      && node.initializer
    ) {
      result.matchedSurfaceLevelStyles += 1;
      const initializer = unwrapExpression(node.initializer);
      const entries = new Map<string, SurfaceLevelStyleEntry>();
      if (ts.isObjectLiteralExpression(initializer)) {
        for (const property of initializer.properties) {
          if (!ts.isPropertyAssignment(property)) continue;
          const scan = scanStaticClassExpression(
            property.initializer,
            sourceFile,
            initializers,
            new Set(),
            'SURFACE_LEVEL_STYLES',
          );
          const names = propertyNameValues(property.name, initializers);
          if (names?.length === 1) {
            entries.set(names[0], {
              index: property.getStart(sourceFile),
              fragments: scan.fragments,
            });
          }
        }
      }
      appendSurfaceLevelContractViolations(
        filename,
        source,
        node.getStart(sourceFile),
        entries,
        result.violations,
      );
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return result;
}

function scanPrimaryCtas(filename: string, source: string): PrimaryCtaScan {
  return scanPrimaryCtasInBoundSource(filename, source, createBoundSourceFile(source));
}

function scanPrimaryCtaSources(sources: readonly SourceEntry[]): Map<string, PrimaryCtaScan> {
  const boundSources = createBoundSourceFiles(sources);
  return new Map(sources.map(([filename, source]) => {
    const boundSource = boundSources.get(filename);
    if (!boundSource) {
      throw new Error(`Production design guard could not scan ${filename}.`);
    }
    return [filename, scanPrimaryCtasInBoundSource(filename, source, boundSource)] as const;
  }));
}

function findProductionDesignViolations(
  filename: string,
  source: string,
  buttonClassNames: Set<string> = new Set(),
  primaryCtaScan?: PrimaryCtaScan,
): DesignViolation[] {
  const violations: DesignViolation[] = [];

  if (filename.endsWith('.tsx')) {
    violations.push(...(primaryCtaScan ?? scanPrimaryCtas(filename, source)).violations);
  }

  for (const buttonMatch of source.matchAll(BUTTON_OPENING_TAG_PATTERN)) {
    const button = buttonMatch[0];
    const buttonIndex = buttonMatch.index ?? 0;
    for (const radiusMatch of button.matchAll(PILL_RADIUS_CLASS_PATTERN)) {
      violations.push({
        file: filename,
        line: lineNumberAt(source, buttonIndex + (radiusMatch.index ?? 0)),
        rule: 'button-shape',
        token: radiusMatch[0],
      });
    }
  }

  const sourceWithoutComments = maskComments(source);
  if (filename.endsWith('.css')) {
    for (const ruleMatch of sourceWithoutComments.matchAll(CSS_RULE_PATTERN)) {
      const selector = ruleMatch[1];
      if (!selectorTargetsButton(selector, buttonClassNames)) continue;
      const radiusMatch = ruleMatch[2].match(CSS_RADIUS_DECLARATION_PATTERN);
      if (!radiusMatch || !isPillRadius(radiusMatch[1])) continue;
      const ruleIndex = ruleMatch.index ?? 0;
      const radiusIndex = ruleIndex + ruleMatch[0].indexOf(radiusMatch[0]);
      violations.push({
        file: filename,
        line: lineNumberAt(source, radiusIndex),
        rule: 'button-shape',
        token: radiusMatch[0],
      });
    }
  }

  for (const match of sourceWithoutComments.matchAll(HARDCODED_HEX_PATTERN)) {
    const index = match.index ?? 0;
    if (!isAllowedIndexCssToken(filename, source, index)) {
      violations.push({
        file: filename,
        line: lineNumberAt(source, index),
        rule: 'hardcoded-hex',
        token: match[0],
      });
    }
  }

  for (const match of sourceWithoutComments.matchAll(HARDCODED_COLOR_FUNCTION_PATTERN)) {
    const index = match.index ?? 0;
    if (!isAllowedIndexCssToken(filename, source, index)) {
      violations.push({
        file: filename,
        line: lineNumberAt(source, index),
        rule: 'hardcoded-color',
        token: match[0],
      });
    }
  }

  for (const match of source.matchAll(MAGIC_PIXEL_SIZE_PATTERN)) {
    const index = match.index ?? 0;
    violations.push({
      file: filename,
      line: lineNumberAt(source, index),
      rule: 'magic-pixel-size',
      token: match[0],
    });
  }

  for (const match of source.matchAll(ARBITRARY_RADIUS_PATTERN)) {
    const index = match.index ?? 0;
    violations.push({
      file: filename,
      line: lineNumberAt(source, index),
      rule: 'magic-pixel-size',
      token: match[0],
    });
  }

  if (filename.endsWith('.css')) {
    for (const match of sourceWithoutComments.matchAll(RAW_CSS_MAGIC_PIXEL_PATTERN)) {
      const index = match.index ?? 0;
      const declaration = match[0];
      const pixelValue = Number(match[1]);
      const isCanonicalPillRadius = declaration.startsWith('border-radius') && pixelValue === 9999;
      if (!isCanonicalPillRadius) {
        violations.push({
          file: filename,
          line: lineNumberAt(source, index),
          rule: 'magic-pixel-size',
          token: declaration,
        });
      }
    }
  }

  for (const match of source.matchAll(RAW_STATIC_VIEWPORT_HEIGHT)) {
    const index = match.index ?? 0;
    violations.push({
      file: filename,
      line: lineNumberAt(source, index),
      rule: 'raw-viewport-height',
      token: '100vh',
    });
  }

  for (const match of sourceWithoutComments.matchAll(LEGACY_CHROMATIC_TOKEN_PATTERN)) {
    const index = match.index ?? 0;
    if (!isAllowedIndexCssToken(filename, source, index)) {
      violations.push({
        file: filename,
        line: lineNumberAt(source, index),
        rule: 'legacy-chromatic-token',
        token: match[0],
      });
    }
  }

  for (const pattern of GLOW_EFFECT_PATTERNS) {
    for (const match of sourceWithoutComments.matchAll(pattern)) {
      const index = match.index ?? 0;
      if (!isAllowedIndexCssToken(filename, source, index)) {
        violations.push({
          file: filename,
          line: lineNumberAt(source, index),
          rule: 'glow-effect',
          token: match[0],
        });
      }
    }
  }

  for (const match of sourceWithoutComments.matchAll(STRONG_BLUR_CLASS_PATTERN)) {
    const index = match.index ?? 0;
    violations.push({
      file: filename,
      line: lineNumberAt(source, index),
      rule: 'strong-blur',
      token: match[0],
    });
  }

  for (const pattern of [ARBITRARY_BLUR_CLASS_PATTERN, CSS_BLUR_PATTERN]) {
    for (const match of sourceWithoutComments.matchAll(pattern)) {
      const index = match.index ?? 0;
      if (Number(match[1]) > MAX_RESTRAINED_BLUR_PX) {
        violations.push({
          file: filename,
          line: lineNumberAt(source, index),
          rule: 'strong-blur',
          token: match[0],
        });
      }
    }
  }

  for (const match of sourceWithoutComments.matchAll(OVERLAY_Z_UTILITY_PATTERN)) {
    const index = match.index ?? 0;
    if (isAllowedExactSourceToken(OVERLAY_Z_ALLOWLIST, filename, source, index, match[0])) {
      continue;
    }
    violations.push({
      file: filename,
      line: lineNumberAt(source, index),
      rule: 'overlay-z-index',
      token: match[0],
    });
  }

  for (const match of sourceWithoutComments.matchAll(INLINE_Z_INDEX_PATTERN)) {
    const index = match.index ?? 0;
    const numericValue = /^\d+$/.test(match[1]) ? Number(match[1]) : null;
    if (numericValue !== null && numericValue < 40) continue;
    violations.push({
      file: filename,
      line: lineNumberAt(source, index),
      rule: 'overlay-z-index',
      token: match[0],
    });
  }

  for (const match of sourceWithoutComments.matchAll(NEAR_VIEWPORT_PANEL_PATTERN)) {
    const index = match.index ?? 0;
    violations.push({
      file: filename,
      line: lineNumberAt(source, index),
      rule: 'near-viewport-panel',
      token: match[0],
    });
  }

  return violations;
}

describe('production design guard', () => {
  it('explicitly excludes tests, stories, generated sources, and fixtures', () => {
    expect(isProductionSource('../../pages/HomePage.tsx')).toBe(true);
    expect(isProductionSource('../../pages/HomePage.test.tsx')).toBe(false);
    expect(isProductionSource('../../pages/HomePage.spec.tsx')).toBe(false);
    expect(isProductionSource('../../pages/HomePage.stories.tsx')).toBe(false);
    expect(isProductionSource('../../pages/HomePage.story.tsx')).toBe(false);
    expect(isProductionSource('../../pages/HomePage.generated.tsx')).toBe(false);
    expect(isProductionSource('../../pages/__tests__/HomePage.tsx')).toBe(false);
    expect(isProductionSource('../../pages/fixtures/HomePage.tsx')).toBe(false);
    expect(isProductionSource('../../pages/generated/HomePage.tsx')).toBe(false);
    expect(isProductionSource('../../pages/stories/HomePage.tsx')).toBe(false);
    const indexStyles = Object.entries(productionSources)
      .find(([filename]) => filename.endsWith('/index.css'));
    expect(indexStyles, 'root index.css must remain in the production scan').toBeDefined();
    expect(indexStyles?.[1]).toContain('.badge');
    const productionCssPaths = Object.keys(productionStylePaths).filter(isProductionSource).sort();
    expect(Object.keys(productionStyles).sort()).toEqual(productionCssPaths);
  });

  it('self-test detects a pill button shape', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.pillButton))
      .toEqual([expect.objectContaining({ rule: 'button-shape', token: 'rounded-full' })]);
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.pillCssButton))
      .toEqual([expect.objectContaining({ rule: 'button-shape', token: 'border-radius: 9999px' })]);
    expect(findProductionDesignViolations(
      'fixture.css',
      productionDesignGuardFixtures.mappedPillCssButton,
      new Set(['session-item']),
    )).toEqual([expect.objectContaining({ rule: 'button-shape', token: 'border-radius: 50%' })]);
  });

  it('self-test inspects the shared Button size style map', () => {
    const source = `
      const BUTTON_SIZE_STYLES = {
        compact: 'h-7 rounded-full px-2',
        default: 'h-8 rounded-lg px-3',
        comfortable: 'h-9 rounded-lg px-3',
        primary: 'h-10 rounded-lg px-4',
      } as const;
      export const Button = () => <button className={BUTTON_SIZE_STYLES.compact}>Run</button>;
    `;

    expect(findProductionDesignViolations('fixture.tsx', source)).toEqual([
      expect.objectContaining({ rule: 'button-shape', token: 'rounded-full' }),
    ]);
  });

  it('self-test enforces canonical Button tiers and rejects out-of-contract heights', () => {
    const source = `
      const BUTTON_SIZE_STYLES = {
        compact: 'h-8 rounded-lg px-2',
        default: 'h-8 rounded-lg px-3',
        comfortable: 'h-9 rounded-lg px-3',
        primary: 'h-10 rounded-lg px-4',
        xsm: 'h-6 rounded-lg px-2',
      } as const;
      export const Button = () => <button className={BUTTON_SIZE_STYLES.compact}>Run</button>;
    `;

    expect(findProductionDesignViolations('fixture.tsx', source)).toEqual([
      expect.objectContaining({ rule: 'button-size-contract', token: 'compact:h-8' }),
      expect.objectContaining({ rule: 'button-size-contract', token: 'xsm:legacy' }),
    ]);
  });

  it('rejects legacy Button size aliases in both the style map and shared callers', () => {
    const styleSource = `
      const BUTTON_SIZE_STYLES = {
        compact: 'h-7 rounded-lg px-2',
        default: 'h-8 rounded-lg px-3',
        comfortable: 'h-9 rounded-lg px-3',
        primary: 'h-10 rounded-lg px-4',
        xsm: 'h-7 rounded-lg px-2',
        xl: 'h-10 rounded-lg px-5',
      } as const;
      export const Button = () => <button className={BUTTON_SIZE_STYLES.compact}>Run</button>;
    `;

    expect(findProductionDesignViolations('fixture.tsx', styleSource)).toContainEqual(
      expect.objectContaining({ rule: 'button-size-contract', token: 'xsm:legacy' }),
    );
    expect(findProductionDesignViolations(
      'fixture.tsx',
      'import { Button } from "../common"; <Button variant="secondary" size="sm">Run</Button>',
    )).toContainEqual(
      expect.objectContaining({ rule: 'button-size-contract', token: 'size="sm"' }),
    );
    expect(findProductionDesignViolations(
      'fixture.tsx',
      'import { Button as Action } from "../common"; <Action variant="secondary" size="lg">Run</Action>',
    )).toContainEqual(
      expect.objectContaining({ rule: 'button-size-contract', token: 'size="lg"' }),
    );
    expect(findProductionDesignViolations(
      'fixture.tsx',
      'import { Button } from "../common"; <Button variant="secondary" size="default">Run</Button>',
    ).filter(({ rule }) => rule === 'button-size-contract')).toEqual([]);
  });

  it('self-test rejects non-soft radii in the shared Button size map', () => {
    const source = `
      const BUTTON_SIZE_STYLES = {
        compact: 'h-7 rounded-2xl px-2',
        default: 'h-8 rounded-lg px-3',
        comfortable: 'h-9 rounded-lg px-3',
        primary: 'h-10 rounded-lg px-4',
      } as const;
      export const Button = () => <button className={BUTTON_SIZE_STYLES.compact}>Run</button>;
    `;

    expect(findProductionDesignViolations('fixture.tsx', source)).toContainEqual(
      expect.objectContaining({ rule: 'button-shape', token: 'rounded-2xl' }),
    );
  });

  it('self-test rejects xl Button usage outside the exact migration allowlist', () => {
    const source = `
      import { Button } from '../common';
      export const Example = () => <Button variant="primary" size="xl">Continue</Button>;
    `;

    expect(findProductionDesignViolations('fixture.tsx', source)).toContainEqual(
      expect.objectContaining({ rule: 'button-xl-allowlist', token: 'size="xl"' }),
    );
    expect(findProductionDesignViolations('../../pages/NotFoundPage.tsx', source)).toContainEqual(
      expect.objectContaining({ rule: 'button-xl-allowlist', token: 'size="xl"' }),
    );
  });

  it('fails closed for dynamic Button sizes and respects final JSX prop order', () => {
    const sizeViolations = (source: string) => findProductionDesignViolations('fixture.tsx', source)
      .filter(({ rule }) => rule === 'button-xl-allowlist');

    expect(sizeViolations(
      'declare const props: ButtonProps; <Button variant="secondary" size="default" {...props}>Continue</Button>',
    )).toEqual([
      expect.objectContaining({ token: 'size={dynamic}' }),
    ]);
    expect(sizeViolations(
      'declare const size: ButtonSize; <Button variant="secondary" size={size}>Continue</Button>',
    )).toEqual([
      expect.objectContaining({ token: 'size={dynamic}' }),
    ]);
    expect(sizeViolations(
      'declare const props: ButtonProps; <Button variant="secondary" {...props} size="default">Continue</Button>',
    )).toEqual([]);
    expect(sizeViolations(
      '<Button variant="secondary" size={dense ? "default" : "xl"}>Continue</Button>',
    )).toEqual([
      expect.objectContaining({ token: 'size="xl"' }),
    ]);
  });

  it('self-test rejects caller-side Button visual overrides', () => {
    const source = `
      import { Button } from '../common';
      export const Example = () => (
        <Button variant="secondary" className="md:h-12 w-full text-xs">Refresh</Button>
      );
    `;

    expect(findProductionDesignViolations('fixture.tsx', source)).toEqual([
      expect.objectContaining({ rule: 'button-visual-override', token: 'md:h-12' }),
      expect.objectContaining({ rule: 'button-visual-override', token: 'w-full' }),
    ]);

    const directionalSource = `
      import { Button } from '../common';
      export const Example = () => (
        <Button variant="secondary" className="md:pl-4 grow flex-auto flex-none text-xs">Refresh</Button>
      );
    `;
    expect(findProductionDesignViolations('fixture.tsx', directionalSource)).toEqual([
      expect.objectContaining({ rule: 'button-visual-override', token: 'md:pl-4' }),
      expect.objectContaining({ rule: 'button-visual-override', token: 'grow' }),
      expect.objectContaining({ rule: 'button-visual-override', token: 'flex-auto' }),
      expect.objectContaining({ rule: 'button-visual-override', token: 'flex-none' }),
    ]);

    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.buttonSizeOverride,
    )).toEqual([
      expect.objectContaining({ rule: 'button-visual-override', token: 'size-12' }),
    ]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.buttonArbitraryGeometryOverride,
    )).toEqual([
      expect.objectContaining({
        rule: 'button-visual-override',
        token: 'supports-[display:grid]:[height:3rem]',
      }),
      expect.objectContaining({ rule: 'button-visual-override', token: '[width:3rem]' }),
      expect.objectContaining({ rule: 'button-visual-override', token: '[padding-inline:1rem]' }),
      expect.objectContaining({ rule: 'button-visual-override', token: '[border-radius:1rem]' }),
      expect.objectContaining({ rule: 'button-visual-override', token: '[flex-basis:10rem]' }),
      expect.objectContaining({ rule: 'button-visual-override', token: '[flex-shrink:0]' }),
    ]);
  });

  it('rejects shared Button callers whose children are only icons or symbols', () => {
    const iconOnlyViolations = (source: string) => findProductionDesignViolations(
      'fixture.tsx',
      source,
    ).filter(({ rule }) => rule === 'button-icon-only');

    expect(iconOnlyViolations(productionDesignGuardFixtures.iconOnlyButton)).toEqual([
      expect.objectContaining({ rule: 'button-icon-only', token: 'icon-or-symbol-only' }),
    ]);
    expect(iconOnlyViolations(productionDesignGuardFixtures.symbolOnlyButton)).toEqual([
      expect.objectContaining({ rule: 'button-icon-only', token: 'icon-or-symbol-only' }),
    ]);
    expect(iconOnlyViolations(`
      import { Trash2 } from 'lucide-react';
      <Button variant="ghost" aria-label="Delete">
        <Trash2 aria-hidden="true" />
        <span className="sr-only">Delete</span>
      </Button>
    `)).toHaveLength(1);
    expect(iconOnlyViolations(`
      import { Trash2 } from 'lucide-react';
      declare const label: string;
      <Button variant="ghost"><Trash2 aria-hidden="true" />Delete</Button>
      <Button variant="ghost"><Trash2 aria-hidden="true" />{label}</Button>
      <Button variant="ghost"><Trash2 aria-hidden="true" />{t('delete')}</Button>
    `)).toEqual([]);
    expect(iconOnlyViolations(`
      import { Trash2 } from 'lucide-react';
      const icon = <Trash2 aria-hidden="true" />;
      <Button variant="ghost" aria-label="Delete">{icon}</Button>
    `)).toEqual([
      expect.objectContaining({ rule: 'button-icon-only', token: 'icon-or-symbol-only' }),
    ]);
  });

  it('rejects shared field and IconButton geometry overrides without blocking layout width', () => {
    const source = `
      <Input className="h-11 w-24 rounded-full px-4 text-center" />
      <IconButton aria-label="Delete" className="size-12 text-danger"><span>X</span></IconButton>
      <Textarea className="min-h-40 rounded-xl" />
    `;
    const violations = findProductionDesignViolations('fixture.tsx', source);

    expect(violations).toEqual(expect.arrayContaining([
      expect.objectContaining({ rule: 'control-visual-override', token: 'Input:h-11' }),
      expect.objectContaining({ rule: 'control-visual-override', token: 'Input:rounded-full' }),
      expect.objectContaining({ rule: 'control-visual-override', token: 'Input:px-4' }),
      expect.objectContaining({ rule: 'control-visual-override', token: 'IconButton:size-12' }),
      expect.objectContaining({ rule: 'control-visual-override', token: 'Textarea:min-h-40' }),
      expect.objectContaining({ rule: 'control-visual-override', token: 'Textarea:rounded-xl' }),
    ]));
    expect(violations).not.toContainEqual(
      expect.objectContaining({ rule: 'control-visual-override', token: 'Input:w-24' }),
    );
    expect(findProductionDesignViolations('fixture.tsx', `
      import { Input as SharedInput } from '../common';
      <SharedInput className="h-11" />
    `)).toContainEqual(
      expect.objectContaining({ rule: 'control-visual-override', token: 'Input:h-11' }),
    );
  });

  it('self-tests the semantic Surface level boundary contract', () => {
    const source = `
      const SURFACE_LEVEL_STYLES = {
        canvas: 'rounded-xl border bg-transparent bg-card shadow-soft-card',
        section: 'rounded-xl border bg-elevated',
        interactive: 'rounded-xl border border-danger bg-elevated shadow-soft-card',
        overlay: 'rounded-xl border border-border bg-card shadow-lg',
      } as const;
    `;
    const violations = findProductionDesignViolations('fixture.tsx', source)
      .filter(({ rule }) => rule === 'surface-level-contract');

    expect(violations).toEqual(expect.arrayContaining([
      expect.objectContaining({ token: 'canvas:bg-card' }),
      expect.objectContaining({ token: 'canvas:rounded-xl' }),
      expect.objectContaining({ token: 'canvas:border' }),
      expect.objectContaining({ token: 'section:border' }),
      expect.objectContaining({ token: 'section:background:bg-card:missing' }),
      expect.objectContaining({ token: 'section:bg-elevated' }),
      expect.objectContaining({ token: 'interactive:border:border-border:missing' }),
      expect.objectContaining({ token: 'interactive:border-danger' }),
      expect.objectContaining({ token: 'interactive:background:bg-card:missing' }),
      expect.objectContaining({ token: 'interactive:shadow-soft-card' }),
      expect.objectContaining({ token: 'overlay:background:bg-elevated:missing' }),
      expect.objectContaining({ token: 'overlay:bg-card' }),
      expect.objectContaining({ token: 'overlay:shadow:shadow-soft-card-strong:missing' }),
      expect.objectContaining({ token: 'overlay:shadow-lg' }),
    ]));
  });

  it('rejects caller-owned borders, backgrounds, radii, and shadows on state surfaces', () => {
    const source = `
      import { StatePanel as Status, EmptyState } from '../common';
      import * as Common from '../common';
      import { DashboardStateBlock } from '../dashboard';
      declare const dynamicClasses: string;
      <Status state="empty" title="Empty" className="rounded-2xl border border-dashed bg-card shadow-soft-card" />;
      <Status
        state="empty"
        title="Inline styles"
        style={{ background: 'var(--card)', border: '1px solid', borderRadius: '1rem', boxShadow: 'none' }}
      />;
      <EmptyState title="Empty" className="max-w-xl" />;
      <Common.Surface
        level="section"
        className="[background:var(--card)] [border:1px_solid] [border-radius:1rem] [box-shadow:none]"
      >Content</Common.Surface>;
      <Common.Surface level="section" className={dynamicClasses}>Dynamic content</Common.Surface>;
      <DashboardStateBlock title="Empty" className="dashboard-card" />;
    `;
    const violations = findProductionDesignViolations('fixture.tsx', source)
      .filter(({ rule }) => rule === 'state-surface-visual-override');

    expect(violations).toEqual(expect.arrayContaining([
      expect.objectContaining({ token: 'StatePanel:rounded-2xl' }),
      expect.objectContaining({ token: 'StatePanel:border' }),
      expect.objectContaining({ token: 'StatePanel:border-dashed' }),
      expect.objectContaining({ token: 'StatePanel:bg-card' }),
      expect.objectContaining({ token: 'StatePanel:shadow-soft-card' }),
      expect.objectContaining({ token: 'StatePanel:style:background' }),
      expect.objectContaining({ token: 'StatePanel:style:border' }),
      expect.objectContaining({ token: 'StatePanel:style:borderRadius' }),
      expect.objectContaining({ token: 'StatePanel:style:boxShadow' }),
      expect.objectContaining({ token: 'Surface:[background:var(--card)]' }),
      expect.objectContaining({ token: 'Surface:[border:1px_solid]' }),
      expect.objectContaining({ token: 'Surface:[border-radius:1rem]' }),
      expect.objectContaining({ token: 'Surface:[box-shadow:none]' }),
      expect.objectContaining({ token: expect.stringContaining('Surface:dynamic:') }),
      expect.objectContaining({ token: 'DashboardStateBlock:dashboard-card' }),
    ]));
    expect(violations).not.toContainEqual(
      expect.objectContaining({ token: 'EmptyState:max-w-xl' }),
    );
  });

  it('scans compatibility adapter internals for newly owned visual layers', () => {
    const source = `
      import { Surface } from './Surface';
      <Surface level="section" className="shadow-soft-card">Card content</Surface>;
    `;

    expect(findProductionDesignViolations('../common/Card.tsx', source)).toContainEqual(
      expect.objectContaining({
        rule: 'state-surface-visual-override',
        token: 'Surface:shadow-soft-card',
      }),
    );

    const changedForwarding = [
      "import { StatePanel } from './StatePanel';",
      'declare const className: string, otherProps: object;',
      ...Array.from({ length: 19 }, () => ''),
      '<StatePanel state="empty" title="Empty" {...otherProps} className={className} />;',
    ].join('\n');
    const forwardingViolations = findProductionDesignViolations(
      '../common/EmptyState.tsx',
      changedForwarding,
    );
    expect(forwardingViolations).toEqual([
      expect.objectContaining({
        rule: 'state-surface-visual-override',
        token: 'StatePanel:style:dynamic:style spread:otherProps',
      }),
    ]);
  });

  it('keeps Button visual-override exceptions exact, consumable, and expiring', () => {
    const source = `
      import { Button } from '../components/common';
      export const Example = () => (
        <Button variant="secondary" className="flex-1 px-2">Refresh</Button>
      );
    `;

    expect(findProductionDesignViolations('../../pages/PortfolioPage.tsx', source)).toEqual([
      expect.objectContaining({ rule: 'button-visual-override', token: 'flex-1' }),
      expect.objectContaining({ rule: 'button-visual-override', token: 'px-2' }),
    ]);
    const duplicateExactCaller = `${'\n'.repeat(1198)}<Button variant="secondary" className="flex-1">First</Button><Button variant="secondary" className="flex-1">Second</Button>`;
    expect(findProductionDesignViolations(
      '../../pages/PortfolioPage.tsx',
      duplicateExactCaller,
    ).filter(({ rule }) => rule === 'button-visual-override')).toEqual([
      expect.objectContaining({ rule: 'button-visual-override', token: 'flex-1' }),
    ]);
    for (const allowances of [
      ...BUTTON_XL_ALLOWLIST.values(),
      ...BUTTON_VISUAL_OVERRIDE_ALLOWLIST.values(),
      ...STATE_SURFACE_VISUAL_OVERRIDE_ALLOWLIST.values(),
    ]) {
      for (const { line, removeBy, tokens } of allowances) {
        expect(line).toBeGreaterThan(0);
        expect(removeBy).toMatch(/^UI-[A-Z0-9]+$/);
        expect(tokens.length).toBeGreaterThan(0);
      }
    }
  });

  it('keeps temporary overlay z-index exceptions exact, consumable, and expiring', () => {
    for (const [filename, allowances] of OVERLAY_Z_ALLOWLIST) {
      const source = productionSources[filename];
      expect(source, `${filename} must remain in the production scan`).toBeDefined();
      const sourceLines = source.split('\n');
      for (const { line, removeBy, token } of allowances) {
        expect(line).toBeGreaterThan(0);
        expect(removeBy).toMatch(/^UI-[A-Z0-9]+$/);
        expect(sourceLines[line - 1]).toContain(token);
        const shiftedSource = `${'\n'.repeat(line)}<div className="${token}">Overlay</div>`;
        expect(findProductionDesignViolations(filename, shiftedSource)).toEqual(
          expect.arrayContaining([expect.objectContaining({
            rule: 'overlay-z-index',
            token,
          })]),
        );
      }
    }
  });

  it('rejects arbitrary overlay component geometry and requires semantic Drawer variants', () => {
    for (const fixture of [
      productionDesignGuardFixtures.drawerWidthOverride,
      productionDesignGuardFixtures.drawerGeometrySpread,
      productionDesignGuardFixtures.drawerMissingVariant,
      productionDesignGuardFixtures.modalGeometryOverride,
    ]) {
      expect(findProductionDesignViolations('fixture.tsx', fixture)).toEqual(
        expect.arrayContaining([expect.objectContaining({ rule: 'overlay-component-contract' })]),
      );
    }
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import { Drawer as DetailPanel } from '../common'; <DetailPanel variant=\"detail\" width=\"max-w-3xl\">Report</DetailPanel>",
    )).toEqual(expect.arrayContaining([expect.objectContaining({
      rule: 'overlay-component-contract',
      token: 'Drawer.width',
    })]));
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import { Drawer } from './other'; <Drawer width=\"max-w-3xl\">Report</Drawer>",
    )).toEqual([]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Drawer variant="navigation">Routes</Drawer>',
    )).toEqual([]);
  });

  it('rejects local overlay z-index values and near-viewport panels', () => {
    for (const fixture of [
      productionDesignGuardFixtures.arbitraryOverlayZ,
      productionDesignGuardFixtures.highOverlayZ,
      productionDesignGuardFixtures.inlineOverlayZ,
    ]) {
      expect(findProductionDesignViolations('fixture.tsx', fixture)).toEqual(
        expect.arrayContaining([expect.objectContaining({ rule: 'overlay-z-index' })]),
      );
    }
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.localCanvasZ,
    )).toEqual([]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.nearViewportPanel,
    )).toEqual([expect.objectContaining({ rule: 'near-viewport-panel' })]);
  });

  it('self-test detects a hardcoded hex colour', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.hardcodedHex))
      .toEqual([expect.objectContaining({ rule: 'hardcoded-hex', token: '#123456' })]);
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.hardcodedFunctionalColor))
      .toEqual([expect.objectContaining({ rule: 'hardcoded-color', token: 'rgba(0,0,0,0.2)' })]);
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.hardcodedCssFunctionalColor))
      .toEqual([expect.objectContaining({ rule: 'hardcoded-color', token: 'hsl(0 0% 0% / 0.2)' })]);
  });

  it('keeps native buttons soft-rounded when they have no local radius class', () => {
    const indexStyles = Object.entries(productionSources)
      .find(([filename]) => filename.endsWith('/index.css'))?.[1] ?? '';
    expect(hasGlobalNonPillButtonRule(indexStyles)).toBe(true);
  });

  it('allows index.css theme tokens but rejects hex variables outside theme blocks', () => {
    const fixture = ':root {\n  --brand: #123456;\n}\n.card {\n  --leak: #abcdef;\n}';
    expect(findProductionDesignViolations('../../index.css', fixture))
      .toEqual([expect.objectContaining({ rule: 'hardcoded-hex', token: '#abcdef' })]);
  });

  it('self-test detects a magic pixel font size', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.magicPixelFont))
      .toEqual([expect.objectContaining({ rule: 'magic-pixel-size', token: 'text-[13px]' })]);
  });

  it('self-test detects a magic pixel component size', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.magicPixelSize))
      .toEqual([expect.objectContaining({ rule: 'magic-pixel-size', token: 'h-[37px]' })]);
  });

  it('self-test detects a raw CSS magic pixel size', () => {
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.rawCssMagicPixel))
      .toEqual([expect.objectContaining({ rule: 'magic-pixel-size', token: 'border-radius: 6px' })]);
  });

  it('self-test detects raw CSS magic pixel spacing', () => {
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.rawCssMagicSpacing))
      .toEqual([expect.objectContaining({ rule: 'magic-pixel-size', token: 'padding: 3px' })]);
  });

  it('self-test detects raw 100vh without rejecting 100dvh', () => {
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.rawViewportHeight))
      .toEqual([expect.objectContaining({ rule: 'raw-viewport-height', token: '100vh' })]);
    expect(findProductionDesignViolations('fixture.css', '.shell { min-height: 100dvh; }'))
      .toEqual([]);
  });

  it('self-test detects legacy cyan and purple styling tokens', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.legacyCyan))
      .toEqual([expect.objectContaining({ rule: 'legacy-chromatic-token', token: 'cyan' })]);
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.legacyPurple))
      .toEqual([expect.objectContaining({ rule: 'legacy-chromatic-token', token: 'purple' })]);
  });

  it('allows legacy compatibility tokens only in index.css theme declarations', () => {
    const fixture = ':root {\n  --color-cyan: hsl(var(--primary));\n  --login-accent-glow: hsl(var(--primary) / 0.18);\n}';
    expect(findProductionDesignViolations('../../index.css', fixture)).toEqual([]);
  });

  it('self-test detects decorative glow effects', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.glowEffect))
      .toEqual([expect.objectContaining({ rule: 'glow-effect' })]);
  });

  it('self-test rejects gradients and shimmer inside a primary CTA', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryGradientButton,
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryNamedGradientButton,
    )).toEqual([expect.objectContaining({
      rule: 'primary-cta-gradient',
      token: 'bg-primary-gradient',
    })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.implicitPrimaryGradientButton,
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryGradientChild,
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryShimmerChild,
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-shimmer' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button variant={active ? \'primary\' : \'secondary\'} className={active ? \'bg-gradient-to-r\' : \'bg-card\'}>Run</Button>',
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button variant={\'primary\'} className={`bg-[linear-gradient(to_right,var(--primary),transparent)]`}>Run</Button>',
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
  });

  it('rejects Tailwind v4 linear, radial, and conic primary CTA gradients', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button variant="primary" className="bg-linear-to-r">Run</Button>',
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient', token: 'bg-linear-to-r' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button variant="primary"><span className="bg-radial">Run</span></Button>',
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient', token: 'bg-radial' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button variant="primary" className="hover:bg-conic-180">Run</Button>',
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient', token: 'bg-conic-180' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button variant="primary" className="hover:[background-image:linear-gradient(to_right,red,blue)]">Run</Button>',
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button variant="primary" className="bg-(image:--gradient-primary)">Run</Button>',
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
  });

  it('tracks aliases and namespaces imported from the shared Button module', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import { Button as PrimaryButton } from '../common'; <PrimaryButton className=\"bg-linear-to-r\">Run</PrimaryButton>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import * as Common from '../components/common'; <Common.Button className=\"bg-conic\">Run</Common.Button>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import * as Dialog from './dialog'; <Dialog.Button className=\"bg-gradient-to-r\">Run</Dialog.Button>",
    )).toEqual([]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import { Button } from '../common'; const PrimaryButton = Button; <PrimaryButton className=\"bg-gradient-to-r\">Run</PrimaryButton>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import * as Common from '../common'; const UI = Common; const PrimaryButton = UI.Button; <PrimaryButton className=\"bg-conic\">Run</PrimaryButton>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import * as Common from '../common'; const UI = Common; const { Button: PrimaryButton } = UI; <PrimaryButton className=\"bg-radial\">Run</PrimaryButton>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryLocalAliasGradient,
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.unrelatedLocalAliasGradient,
    )).toEqual([]);
  });

  it('resolves shared Button aliases by lexical binding', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryAliasWithUnrelatedShadow,
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.unrelatedShadowOfSharedAliasGradient,
    )).toEqual([]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.unrelatedShadowOfSharedButtonGradient,
    )).toEqual([]);
  });

  it('tracks a shared Button selected through a static namespace bracket alias', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import * as Common from '../common'; const PrimaryButton = Common['Button']; <PrimaryButton className=\"bg-gradient-to-r\">Run</PrimaryButton>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import * as Dialog from './dialog'; const DialogButton = Dialog['Button']; <DialogButton className=\"bg-gradient-to-r\">Run</DialogButton>",
    )).toEqual([]);
  });

  it('tracks a shared Button selected through a const-aliased static namespace key', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import * as Common from '../common'; const key = 'Button'; const PrimaryButton = Common[key]; <PrimaryButton className=\"bg-gradient-to-r\">Run</PrimaryButton>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
  });

  it('tracks a shared Button destructured through a const-aliased static namespace key', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import * as Common from '../common'; const key = 'Button'; const { [key]: PrimaryButton } = Common; <PrimaryButton className=\"bg-gradient-to-r\">Run</PrimaryButton>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
  });

  it('keeps a const-key bracket alias from an unrelated namespace out of the shared Button scan', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import * as Dialog from './dialog'; const key = 'Button'; const DialogButton = Dialog[key]; <DialogButton className=\"bg-gradient-to-r\">Run</DialogButton>",
    )).toEqual([]);
  });

  it('does not treat a named Button import from an unrelated module as shared', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import { Button } from './dialog'; <Button className=\"bg-gradient-to-r\">Dialog</Button>",
    )).toEqual([]);
  });

  it('does not treat a default Button import from an unrelated Button module as shared', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "import Button from './dialog/Button'; <Button className=\"bg-gradient-to-r\">Dialog</Button>",
    )).toEqual([]);
  });

  it('covers every semantic primary CTA variant and fails closed for dynamic variants', () => {
    for (const variant of PRIMARY_CTA_VARIANTS) {
      expect(findProductionDesignViolations(
        'fixture.tsx',
        `<Button variant="${variant}" className="bg-primary-gradient">Run</Button>`,
      )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    }
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primarySecondaryGradient,
    )).toEqual([]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryDynamicVariantClass,
    )).toEqual(expect.arrayContaining([
      expect.objectContaining({ rule: 'primary-cta-unresolved-class' }),
    ]));
    const nonPrimaryViolations = findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryEnumerableNonPrimaryVariant,
    );
    expect(nonPrimaryViolations).toContainEqual(expect.objectContaining({
      rule: 'button-visual-override',
    }));
    expect(nonPrimaryViolations).not.toContainEqual(expect.objectContaining({
      rule: 'primary-cta-gradient',
    }));
  });

  it('joins fully static class expressions before checking primary effects', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "<Button className={'bg-' + 'gradient-to-r'}>Run</Button>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "const suffix = 'gradient-to-r'; <Button className={'bg-' + suffix}>Run</Button>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "const suffix = 'gradient-to-r'; <Button className={`bg-${suffix}`}>Run</Button>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "<Button className={'bg-' + (active ? 'gradient-to-r' : 'card')}>Run</Button>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "<Button className={`bg-${active ? 'gradient-to-r' : 'card'}`}>Run</Button>",
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    for (const fixture of [
      productionDesignGuardFixtures.primaryStaticConcatenatedClass,
      productionDesignGuardFixtures.primaryStaticTemplateClass,
      productionDesignGuardFixtures.primaryComputedObjectClass,
    ]) {
      expect(findProductionDesignViolations('fixture.tsx', fixture))
        .toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    }
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primarySeparatedComposerClasses,
    )).toEqual([]);
  });

  it('does not trust a locally shadowed class composer', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "const cn = (...values: string[]) => values.join(' '); <Button className={cn('bg-card')}>Run</Button>",
    )).toEqual(expect.arrayContaining([
      expect.objectContaining({ rule: 'primary-cta-unresolved-class' }),
    ]));
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "function cn(value: string) { return value; } <Button className={cn('bg-card')}>Run</Button>",
    )).toEqual(expect.arrayContaining([
      expect.objectContaining({ rule: 'primary-cta-unresolved-class' }),
    ]));
  });

  it('keeps class composer shadowing inside its lexical scope', () => {
    const fixture = [
      "import { cn } from '../../utils/cn';",
      "const Safe = () => <Button className={cn('bg-card')}>Run</Button>;",
      'const Other = () => {',
      "  const cn = (value: string) => value;",
      "  return <div className={cn('bg-card')} />;",
      '};',
    ].join('\n');
    const scan = scanPrimaryCtas('fixture.tsx', fixture);

    expect(scan.matchedButtons).toBe(1);
    expect(scan.violations).toEqual([]);
  });

  it('does not resolve a shadowed class binding through an unrelated const', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryShadowedDynamicClass,
    )).toEqual(expect.arrayContaining([expect.objectContaining({
      rule: 'primary-cta-unresolved-class',
      token: 'className',
    })]));
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryUniqueSafeConstClass,
    )).toEqual([]);
  });

  it('uses final JSX prop order when a spread can override the Button variant', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button variant="secondary" {...{ variant: \'primary\' }} className="bg-gradient-to-r">Run</Button>',
    )).toEqual(expect.arrayContaining([
      expect.objectContaining({ rule: 'primary-cta-gradient' }),
    ]));
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button {...{ variant: \'primary\' }} variant="secondary" className="bg-gradient-to-r">Run</Button>',
    )).toEqual([]);
  });

  it('fails closed only when a spread can override the final explicit className', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button variant="primary" className="bg-card" {...props}>Run</Button>',
    )).toEqual(expect.arrayContaining([
      expect.objectContaining({
        rule: 'primary-cta-unresolved-class',
        token: 'className spread:props',
      }),
      expect.objectContaining({
        rule: 'primary-cta-unresolved-class',
        token: 'style spread:props',
      }),
    ]));
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button variant="primary" {...props} className="bg-card" style={{ background: \'var(--background)\' }}>Run</Button>',
    ).filter(({ rule }) => rule !== 'button-xl-allowlist')).toEqual([]);
  });

  it('resolves direct const class expressions for primary callsites and shared styles', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      'const CTA_CLASSES = \'bg-linear-to-r\'; <Button variant="primary" className={CTA_CLASSES}>Run</Button>',
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient', token: 'bg-linear-to-r' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      'const PRIMARY_STYLES = \'bg-conic\'; const BUTTON_VARIANT_STYLES = { primary: PRIMARY_STYLES, \'settings-primary\': \'bg-foreground\', \'action-primary\': \'bg-foreground\', gradient: \'bg-foreground\' };',
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient', token: 'bg-conic' })]);
  });

  it('uses final object property order for shared primary variant styles', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.sharedPrimaryTrailingOverride,
    )).toEqual(expect.arrayContaining([expect.objectContaining({
      rule: 'primary-cta-unresolved-class',
      token: 'BUTTON_VARIANT_STYLES.primary',
    })]));
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.sharedPrimaryExplicitFinalOverride,
    )).toEqual([]);
  });

  it('fails closed when primary class expressions have no static fragments', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      '<Button variant="primary" className={ctaClasses}>Run</Button>',
    )).toEqual(expect.arrayContaining([expect.objectContaining({
      rule: 'primary-cta-unresolved-class',
      token: 'className',
    })]));
    expect(findProductionDesignViolations(
      'fixture.tsx',
      'const BUTTON_VARIANT_STYLES = { primary: getPrimaryStyles(), \'settings-primary\': \'bg-foreground\', \'action-primary\': \'bg-foreground\', gradient: \'bg-foreground\' };',
    )).toEqual([expect.objectContaining({
      rule: 'primary-cta-unresolved-class',
      token: 'BUTTON_VARIANT_STYLES.primary',
    })]);
  });

  it('detects arbitrary shimmer animations without rejecting other animations', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryArbitraryShimmer,
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-shimmer' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryArbitrarySpin,
    )).toEqual([]);
  });

  it('detects inline primary effects and accepts static non-decorative styles', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryInlineGradient,
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-gradient' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryInlineShimmer,
    )).toEqual([expect.objectContaining({ rule: 'primary-cta-shimmer' })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryInlineSafe,
    )).toEqual([]);
  });

  it('rejects a primary CTA inline backgroundImage linear gradient', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "<Button variant=\"primary\" style={{ backgroundImage: 'linear-gradient(to_right,var(--primary),transparent)' }}>Run</Button>",
    )).toEqual([expect.objectContaining({
      rule: 'primary-cta-gradient',
      token: 'linear-gradient(',
    })]);
    expect(findProductionDesignViolations(
      'fixture.tsx',
      "<Button variant=\"primary\" style={{ backgroundImage: 'none' }}>Run</Button>",
    )).toEqual([]);
  });

  it('propagates unresolved operands alongside static primary class fragments', () => {
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryDynamicCnClass,
    )).toEqual(expect.arrayContaining([expect.objectContaining({
      rule: 'primary-cta-unresolved-class',
      token: 'dynamicClasses',
    })]));
    expect(findProductionDesignViolations(
      'fixture.tsx',
      productionDesignGuardFixtures.primaryDynamicTemplateClass,
    )).toEqual(expect.arrayContaining([expect.objectContaining({
      rule: 'primary-cta-unresolved-class',
      token: 'dynamicClasses',
    })]));
  });

  it('accepts fully enumerable primary class expressions', () => {
    for (const fixture of [
      productionDesignGuardFixtures.primaryEnumerableCnClass,
      productionDesignGuardFixtures.primaryEnumerableConditionalClass,
    ]) {
      const scan = scanPrimaryCtas('fixture.tsx', fixture);
      expect(scan.matchedButtons).toBe(1);
      expect(scan.violations).toEqual([]);
    }
  });

  it('retains primary CTA violations when reusing a precomputed production scan', () => {
    const source = '<Button variant="primary" className="bg-gradient-to-r">Run</Button>';
    const primaryCtaScan = scanPrimaryCtas('fixture.tsx', source);

    expect(findProductionDesignViolations(
      'fixture.tsx',
      source,
      new Set(),
      primaryCtaScan,
    )).toEqual([expect.objectContaining({
      rule: 'primary-cta-gradient',
      token: 'bg-gradient-to-r',
    })]);
  });

  it('keeps shared Button bindings isolated across a batched production scan', () => {
    const scans = scanPrimaryCtaSources([
      [
        'shared.tsx',
        "import { Button as Action } from '../common'; <Action className=\"bg-gradient-to-r\">Run</Action>",
      ],
      [
        'unrelated.tsx',
        "import { Button as Action } from './dialog'; <Action className=\"bg-gradient-to-r\">Dialog</Action>",
      ],
    ]);

    expect(scans.get('shared.tsx')?.violations).toEqual([
      expect.objectContaining({ rule: 'primary-cta-gradient' }),
    ]);
    expect(scans.get('unrelated.tsx')?.violations).toEqual([]);
  });

  it('scopes primary CTA effects to className and balanced JSX boundaries', () => {
    const primaryViolations = (source: string) => findProductionDesignViolations('fixture.tsx', source)
      .filter(({ rule }) => rule.startsWith('primary-cta'));

    expect(primaryViolations(
      '<Button variant="secondary" className="bg-gradient-to-r"><span className="animate-[shimmer_1s]" /></Button>',
    )).toEqual([]);
    expect(primaryViolations(
      '<Button variant="primary" aria-label="bg-gradient-to-r">Shimmer report</Button>',
    )).toEqual([]);
    expect(primaryViolations(
      '<Button variant="primary" /> <span className="animate-[shimmer_1s]">Sibling</span>',
    )).toEqual([]);
    expect(primaryViolations(
      '<Button variant="primary"><Button variant="secondary" className="bg-gradient-to-r" /></Button>',
    )).toEqual([]);
    expect(primaryViolations(
      '<Dialog.Button className="bg-gradient-to-r">Dialog action</Dialog.Button>',
    )).toEqual([]);
    expect(primaryViolations(
      '{/* <Button variant="primary" className="bg-gradient-to-r">Old</Button> */}',
    )).toEqual([]);
    expect(primaryViolations('<Button variant="primary" className="bg-foreground">Run</Button>'))
      .toEqual([]);
    expect(primaryViolations('<Button className="bg-foreground">Run</Button>')).toEqual([]);
  });

  it('self-test detects strong class and CSS blur without rejecting restrained blur', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.strongBlurClass))
      .toEqual([expect.objectContaining({ rule: 'strong-blur', token: 'backdrop-blur-xl' })]);
    expect(findProductionDesignViolations('fixture.css', productionDesignGuardFixtures.strongCssBlur))
      .toEqual([expect.objectContaining({ rule: 'strong-blur', token: 'backdrop-filter: blur(12px)' })]);
    expect(findProductionDesignViolations('fixture.tsx', '<div className="backdrop-blur-sm" />'))
      .toEqual([]);
    expect(findProductionDesignViolations('fixture.css', '.surface { filter: blur(4px); }'))
      .toEqual([]);
  });

  it('self-test accepts a tokenized pill button', () => {
    expect(findProductionDesignViolations('fixture.tsx', productionDesignGuardFixtures.compliant))
      .toEqual([]);
  });

  it('keeps every production CSS and TSX source within the enforced rules', () => {
    const scannedSources = Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename));
    const productionTsxSources = scannedSources
      .filter(([filename]) => filename.endsWith('.tsx'));
    const totalMatchedButtonTags = productionTsxSources.reduce(
      (total, [, source]) => total + Array.from(source.matchAll(BUTTON_OPENING_TAG_PATTERN)).length,
      0,
    );
    const primaryScans = scanPrimaryCtaSources(productionTsxSources);
    const allowlistHits = Array.from(primaryScans.values())
      .flatMap((scan) => scan.allowlistHits)
      .sort();
    const expectedAllowlistHits = [
      ...exactButtonAllowanceKeys('button-xl-allowlist', BUTTON_XL_ALLOWLIST),
      ...exactButtonAllowanceKeys(
        'button-visual-override',
        BUTTON_VISUAL_OVERRIDE_ALLOWLIST,
      ),
      ...exactButtonAllowanceKeys(
        'state-surface-visual-override',
        STATE_SURFACE_VISUAL_OVERRIDE_ALLOWLIST,
      ),
    ].sort();
    const totalMatchedPrimaryButtons = Array.from(primaryScans.values()).reduce(
      (total, scan) => total + scan.matchedButtons,
      0,
    );
    const totalMatchedSharedPrimaryStyles = Array.from(primaryScans.values()).reduce(
      (total, scan) => total + scan.matchedSharedStyles,
      0,
    );
    const totalMatchedSurfaceLevelStyles = Array.from(primaryScans.values()).reduce(
      (total, scan) => total + scan.matchedSurfaceLevelStyles,
      0,
    );
    const buttonClassNames = new Set(productionTsxSources
      .flatMap(([, source]) => Array.from(extractButtonClassNames(source))));
    const violations = scannedSources.flatMap(([filename, source]) => (
      findProductionDesignViolations(
        filename,
        source,
        buttonClassNames,
        primaryScans.get(filename),
      )
    ));

    expect(scannedSources.length).toBeGreaterThan(0);
    expect(totalMatchedButtonTags).toBeGreaterThan(0);
    expect(totalMatchedPrimaryButtons).toBeGreaterThan(0);
    expect(totalMatchedSharedPrimaryStyles).toBe(PRIMARY_CTA_VARIANTS.size);
    expect(totalMatchedSurfaceLevelStyles).toBe(1);
    expect(allowlistHits).toEqual(expectedAllowlistHits);
    expect(buttonClassNames.size).toBeGreaterThan(0);
    expect(violations).toEqual([]);
  });

  it('retains the legacy-visual guard for upstream-adapted surfaces', () => {
    const guardedSuffixes = [
      '/watchlist/HomeStockWorkspace.tsx',
      '/report/MarketStructureCard.tsx',
    ];

    for (const suffix of guardedSuffixes) {
      const entry = Object.entries(productionSources)
        .find(([filename]) => filename.endsWith(suffix));
      expect(entry, `${suffix} must remain in the production scan`).toBeDefined();
      const source = entry?.[1] ?? '';
      expect(source).not.toMatch(/\b(?:text|bg|border|ring)-(?:cyan|purple)\b/);
      expect(source).not.toMatch(/pulse-glow|glow-cyan|glow-purple|shadow-glow/);
    }
  });
});
