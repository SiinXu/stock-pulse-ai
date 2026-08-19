// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import ts from 'typescript';
import {
  DENSITY_FIXED_GEOMETRY_EXEMPTIONS,
  DENSITY_REQUIRED_OWNERS,
  DENSITY_STRUCTURAL_CSS_VARS,
  DENSITY_STRUCTURAL_UTILITY_CLASSES,
  type DensityFixedGeometryExemption,
} from '../../design/density';

export type DensityFindingKind =
  | 'density-token'
  | 'fixed-spacing'
  | 'computed-spacing';

export type DensityFinding = {
  file: string;
  line: number;
  kind: DensityFindingKind;
  token: string;
};

export type FileAdoption = {
  file: string;
  densityTokenCount: number;
  fixedSpacingCount: number;
};

export type DensityAdoptionBaseline = {
  version: number;
  files: Record<string, FileAdoption>;
};

export type AdoptionDiff = {
  code:
    | 'missing-required-owner'
    | 'lost-density-aware-file'
    | 'new-density-aware-file'
    | 'density-token-regression'
    | 'fixed-spacing-regression'
    | 'baseline-needs-tightening'
    | 'stale-exemption'
    | 'exemption-overflow';
  file: string;
  detail: string;
};

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const DENSITY_CLASS_PATTERN = new RegExp(
  `(?<![a-zA-Z0-9_-])(?:${DENSITY_STRUCTURAL_UTILITY_CLASSES.map(escapeRegExp).join('|')})(?![a-zA-Z0-9_-])`,
  'g',
);
const DENSITY_VAR_PATTERN = new RegExp(
  `(?:${DENSITY_STRUCTURAL_CSS_VARS.map(escapeRegExp).join('|')})`,
  'g',
);
const STRUCTURAL_SPACING_PATTERN = /(?<![a-zA-Z0-9_-])(?:[a-z-]+:)*(?:gap(?:-x|-y)?|space-[xy]|p(?:[xytlrb])?|m(?:[xytlrb])?)-(?:px|auto|\d+(?:\.\d+)?|\[[^\]]+\])(?![a-zA-Z0-9_-])/g;
const COMPUTED_SPACING_PREFIX = /^(?:[a-z-]+:)*(?:gap(?:-x|-y)?|space-[xy]|p(?:[xytlrb])?|m(?:[xytlrb])?)-$/;
const MICRO_OR_RESET_SPACING = /(?:^|:)(?:gap(?:-x|-y)?|space-[xy]|p(?:[xytlrb])?|m(?:[xytlrb])?)-(?:0|0\.5|1|1\.5|px|auto)$/;
const SPACING_CLASS_CANDIDATE = /(?<![a-zA-Z0-9_-])(?:[a-z-]+:)*(?:gap(?:-x|-y)?|space-[xy]|p(?:[xytlrb])?|m(?:[xytlrb])?)-/;
const SPACING_STYLE_CANDIDATE = /(?<![A-Za-z0-9_])(?:padding|margin|rowGap|columnGap|gap)(?![a-z])/;
const SPACING_STYLE_PROPS = new Set([
  'padding',
  'paddingTop',
  'paddingRight',
  'paddingBottom',
  'paddingLeft',
  'paddingInline',
  'paddingInlineStart',
  'paddingInlineEnd',
  'paddingBlock',
  'paddingBlockStart',
  'paddingBlockEnd',
  'margin',
  'marginTop',
  'marginRight',
  'marginBottom',
  'marginLeft',
  'marginInline',
  'marginInlineStart',
  'marginInlineEnd',
  'marginBlock',
  'marginBlockStart',
  'marginBlockEnd',
  'gap',
  'rowGap',
  'columnGap',
]);
const CSS_SPACING_VALUE = /^-?\d+(?:\.\d+)?(?:px|rem|em)$/;
const DENSITY_VAR_VALUE = /^var\(--density-[\w-]+\)$/;
const DENSITY_SCAN_CANDIDATE_PATTERN = new RegExp(
  [
    'data-density',
    ...DENSITY_STRUCTURAL_UTILITY_CLASSES.map(escapeRegExp),
    ...DENSITY_STRUCTURAL_CSS_VARS.map(escapeRegExp),
    SPACING_CLASS_CANDIDATE.source,
    SPACING_STYLE_CANDIDATE.source,
  ].join('|'),
);

export const DENSITY_CATALOG_PATH = '../../design/density.ts';
export const DENSITY_ADOPTION_BASELINE_VERSION = 1;
/** Regression ceiling well below the 30s coverage `testTimeout`. Do not raise the test timeout instead. */
export const DENSITY_PRODUCTION_COLLECT_BUDGET_MS = 12_000;

export type DensityScanStats = {
  cacheHits: number;
  skippedWithoutParse: number;
  parsedFiles: number;
};

type ScanCacheEntry = {
  source: string;
  findings: DensityFinding[];
};

const scanCache = new Map<string, ScanCacheEntry>();
let scanStats: DensityScanStats = {
  cacheHits: 0,
  skippedWithoutParse: 0,
  parsedFiles: 0,
};

export function getDensityScanStats(): DensityScanStats {
  return { ...scanStats };
}

export function resetDensityScanStats(): void {
  scanStats = {
    cacheHits: 0,
    skippedWithoutParse: 0,
    parsedFiles: 0,
  };
}

export function resetDensityScanCache(): void {
  scanCache.clear();
}

export function resetDensityScanAccounting(): void {
  resetDensityScanStats();
  resetDensityScanCache();
}

/**
 * Conservative over-approximation: if this is false, the AST scanner cannot
 * emit a finding because every token/prop it reads is absent from `source`.
 * Comments and type-only strings may still match and force a parse.
 */
export function sourceMayContainDensityFindings(source: string): boolean {
  return DENSITY_SCAN_CANDIDATE_PATTERN.test(source);
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

function shouldSkipTypeSubtree(node: ts.Node): boolean {
  return ts.isTypeNode(node)
    || ts.isTypeAliasDeclaration(node)
    || ts.isInterfaceDeclaration(node)
    || ts.isHeritageClause(node);
}

function lineOf(sourceFile: ts.SourceFile, node: ts.Node): number {
  return sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
}

function parseSource(filename: string, source: string): ts.SourceFile {
  // Parent pointers are unused: type-only subtrees are skipped by node kind.
  return ts.createSourceFile(
    filename,
    source,
    ts.ScriptTarget.Latest,
    false,
    filename.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
}

function propertyName(node: ts.PropertyName | ts.JsxAttributeName): string | undefined {
  if (ts.isIdentifier(node) || ts.isStringLiteral(node) || ts.isNumericLiteral(node)) {
    return node.text;
  }
  if (ts.isPrivateIdentifier(node)) return node.text;
  return undefined;
}

function isStructuralSpacingToken(token: string): boolean {
  if (MICRO_OR_RESET_SPACING.test(token)) return false;
  STRUCTURAL_SPACING_PATTERN.lastIndex = 0;
  return STRUCTURAL_SPACING_PATTERN.test(token);
}

function extractDensityTokens(text: string): string[] {
  const tokens: string[] = [];
  DENSITY_CLASS_PATTERN.lastIndex = 0;
  for (const match of text.matchAll(DENSITY_CLASS_PATTERN)) {
    tokens.push(match[0]);
  }
  DENSITY_VAR_PATTERN.lastIndex = 0;
  for (const match of text.matchAll(DENSITY_VAR_PATTERN)) {
    tokens.push(match[0]);
  }
  return tokens;
}

function extractSpacingTokens(text: string): string[] {
  STRUCTURAL_SPACING_PATTERN.lastIndex = 0;
  return Array.from(text.matchAll(STRUCTURAL_SPACING_PATTERN), (match) => match[0])
    .filter(isStructuralSpacingToken);
}

function pushFinding(
  findings: DensityFinding[],
  file: string,
  line: number,
  kind: DensityFindingKind,
  token: string,
): void {
  findings.push({ file, line, kind, token });
}

function collectFromText(
  findings: DensityFinding[],
  file: string,
  resolveLine: () => number,
  text: string,
): void {
  const densityTokens = extractDensityTokens(text);
  const spacingTokens = extractSpacingTokens(text);
  if (densityTokens.length === 0 && spacingTokens.length === 0) return;
  const line = resolveLine();
  for (const token of densityTokens) {
    pushFinding(findings, file, line, 'density-token', token);
  }
  for (const token of spacingTokens) {
    pushFinding(findings, file, line, 'fixed-spacing', token);
  }
}

function collectFromTemplatePrefix(
  findings: DensityFinding[],
  file: string,
  resolveLine: () => number,
  text: string,
): void {
  const trimmed = text.trim();
  if (!COMPUTED_SPACING_PREFIX.test(trimmed)) return;
  pushFinding(findings, file, resolveLine(), 'computed-spacing', `computed:${trimmed}`);
}

function isResetSpacingValue(text: string): boolean {
  return /^(?:0(?:px|rem|em)?)$/.test(text.trim());
}

function collectStyleValue(
  findings: DensityFinding[],
  file: string,
  line: number,
  prop: string,
  value: ts.Expression,
): void {
  const expression = unwrapExpression(value);
  if (ts.isStringLiteralLike(expression)) {
    const text = expression.text.trim();
    if (isResetSpacingValue(text)) return;
    if (DENSITY_VAR_VALUE.test(text) || extractDensityTokens(text).length > 0) {
      pushFinding(findings, file, line, 'density-token', `style:${prop}:${text}`);
      return;
    }
    if (CSS_SPACING_VALUE.test(text) || extractSpacingTokens(text).length > 0) {
      pushFinding(findings, file, line, 'fixed-spacing', `style:${prop}:${text}`);
    }
    return;
  }
  if (ts.isNumericLiteral(expression)) {
    if (isResetSpacingValue(expression.text)) return;
    pushFinding(findings, file, line, 'fixed-spacing', `style:${prop}:${expression.text}`);
    return;
  }
  if (ts.isConditionalExpression(expression)) {
    collectStyleValue(findings, file, line, prop, expression.whenTrue);
    collectStyleValue(findings, file, line, prop, expression.whenFalse);
    return;
  }
  if (
    ts.isTemplateExpression(expression)
    || ts.isNoSubstitutionTemplateLiteral(expression)
    || ts.isBinaryExpression(expression)
    || ts.isIdentifier(expression)
    || ts.isPropertyAccessExpression(expression)
    || ts.isCallExpression(expression)
  ) {
    pushFinding(findings, file, line, 'computed-spacing', `style:${prop}:computed`);
  }
}

function scanDensityAdoptionAst(filename: string, source: string): DensityFinding[] {
  const sourceFile = parseSource(filename, source);
  const findings: DensityFinding[] = [];
  const visit = (node: ts.Node): void => {
    if (shouldSkipTypeSubtree(node)) {
      return;
    }

    if (ts.isStringLiteralLike(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      collectFromText(findings, filename, () => lineOf(sourceFile, node), node.text);
    } else if (
      node.kind === ts.SyntaxKind.TemplateHead
      || node.kind === ts.SyntaxKind.TemplateMiddle
      || node.kind === ts.SyntaxKind.TemplateTail
    ) {
      const text = (node as ts.TemplateLiteralToken).text;
      const resolveLine = () => lineOf(sourceFile, node);
      collectFromText(findings, filename, resolveLine, text);
      collectFromTemplatePrefix(findings, filename, resolveLine, text);
    }

    if (ts.isJsxAttribute(node) && propertyName(node.name) === 'data-density') {
      pushFinding(findings, filename, lineOf(sourceFile, node), 'density-token', 'data-density');
    }

    if (ts.isPropertyAssignment(node)) {
      const name = propertyName(node.name);
      if (name && SPACING_STYLE_PROPS.has(name)) {
        collectStyleValue(findings, filename, lineOf(sourceFile, node), name, node.initializer);
      }
    }

    if (ts.isShorthandPropertyAssignment(node) && SPACING_STYLE_PROPS.has(node.name.text)) {
      pushFinding(
        findings,
        filename,
        lineOf(sourceFile, node),
        'computed-spacing',
        `style:${node.name.text}:computed`,
      );
    }

    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

export function scanDensityAdoption(filename: string, source: string): DensityFinding[] {
  const cached = scanCache.get(filename);
  if (cached && cached.source === source) {
    scanStats.cacheHits += 1;
    return cached.findings;
  }

  let findings: DensityFinding[];
  if (!sourceMayContainDensityFindings(source)) {
    scanStats.skippedWithoutParse += 1;
    findings = [];
  } else {
    scanStats.parsedFiles += 1;
    findings = scanDensityAdoptionAst(filename, source);
  }
  scanCache.set(filename, { source, findings });
  return findings;
}

export function isDensityCatalogPath(filename: string): boolean {
  return filename === DENSITY_CATALOG_PATH || filename.endsWith('/design/density.ts');
}

export function isPlaygroundPath(filename: string): boolean {
  return filename.includes('/playground/');
}

export function isDensityAware(findings: readonly DensityFinding[]): boolean {
  return findings.some((finding) => finding.kind === 'density-token');
}

function exemptionKey(file: string, token: string): string {
  return `${file}\u0000${token}`;
}

export function applyDensityExemptions(
  findings: readonly DensityFinding[],
  exemptions: readonly DensityFixedGeometryExemption[] = DENSITY_FIXED_GEOMETRY_EXEMPTIONS,
): {
  remaining: DensityFinding[];
  diffs: AdoptionDiff[];
} {
  const remaining: DensityFinding[] = [];
  const used = new Map<string, number>();
  const exemptionByKey = new Map(
    exemptions.map((exemption) => [exemptionKey(exemption.file, exemption.token), exemption]),
  );

  for (const finding of findings) {
    if (finding.kind === 'density-token') {
      remaining.push(finding);
      continue;
    }
    const key = exemptionKey(finding.file, finding.token);
    const exemption = exemptionByKey.get(key);
    if (!exemption) {
      remaining.push(finding);
      continue;
    }
    const next = (used.get(key) ?? 0) + 1;
    used.set(key, next);
    if (next > exemption.count) {
      remaining.push(finding);
    }
  }

  const diffs: AdoptionDiff[] = [];
  for (const exemption of exemptions) {
    const key = exemptionKey(exemption.file, exemption.token);
    const count = used.get(key) ?? 0;
    if (count === 0) {
      diffs.push({
        code: 'stale-exemption',
        file: exemption.file,
        detail: `${exemption.token}: listed but not present; remove it from DENSITY_FIXED_GEOMETRY_EXEMPTIONS.`,
      });
    } else if (count > exemption.count) {
      diffs.push({
        code: 'exemption-overflow',
        file: exemption.file,
        detail: `${exemption.token}: ${count} uses exceed exemption count ${exemption.count}.`,
      });
    }
  }
  return { remaining, diffs };
}

export function summarizeFileAdoption(
  filename: string,
  findings: readonly DensityFinding[],
): FileAdoption {
  return {
    file: filename,
    densityTokenCount: findings.filter((finding) => finding.kind === 'density-token').length,
    fixedSpacingCount: findings.filter((finding) => finding.kind !== 'density-token').length,
  };
}

export function collectDensityAdoption(
  sources: Record<string, string>,
  exemptions: readonly DensityFixedGeometryExemption[] = DENSITY_FIXED_GEOMETRY_EXEMPTIONS,
): {
  files: Record<string, FileAdoption>;
  exemptionDiffs: AdoptionDiff[];
} {
  const files: Record<string, FileAdoption> = {};
  const exemptionDiffs: AdoptionDiff[] = [];
  const allFixed: DensityFinding[] = [];
  const densityAwareFiles = new Set<string>();

  for (const [filename, source] of Object.entries(sources)) {
    if (isDensityCatalogPath(filename) || isPlaygroundPath(filename)) continue;
    const raw = scanDensityAdoption(filename, source);
    if (!isDensityAware(raw)) continue;
    densityAwareFiles.add(filename);
    allFixed.push(...raw.filter((finding) => finding.kind !== 'density-token'));
    const densityTokens = raw.filter((finding) => finding.kind === 'density-token');
    files[filename] = {
      file: filename,
      densityTokenCount: densityTokens.length,
      fixedSpacingCount: 0,
    };
  }

  const scopedExemptions = exemptions.filter((exemption) => densityAwareFiles.has(exemption.file));
  const { remaining, diffs } = applyDensityExemptions(allFixed, scopedExemptions);
  exemptionDiffs.push(...diffs);

  const remainingByFile = new Map<string, number>();
  for (const finding of remaining) {
    remainingByFile.set(finding.file, (remainingByFile.get(finding.file) ?? 0) + 1);
  }
  for (const filename of Object.keys(files)) {
    files[filename] = {
      ...files[filename],
      fixedSpacingCount: remainingByFile.get(filename) ?? 0,
    };
  }

  return { files, exemptionDiffs };
}

export function requiredOwnerBasenames(): readonly string[] {
  return DENSITY_REQUIRED_OWNERS;
}

export function diffDensityAdoption(
  measured: Record<string, FileAdoption>,
  baseline: DensityAdoptionBaseline,
  options: { enforceRequiredOwners?: boolean } = {},
): AdoptionDiff[] {
  const diffs: AdoptionDiff[] = [];
  const measuredFiles = new Set(Object.keys(measured));
  const baselineFiles = new Set(Object.keys(baseline.files));
  const requiredOwners = options.enforceRequiredOwners === false
    ? []
    : DENSITY_REQUIRED_OWNERS;

  for (const owner of requiredOwners) {
    const match = Array.from(measuredFiles).find((filename) => filename.split('/').pop() === owner);
    if (!match) {
      diffs.push({
        code: 'missing-required-owner',
        file: owner,
        detail: 'Required density owner no longer uses density tokens.',
      });
    }
  }

  for (const filename of baselineFiles) {
    if (!measuredFiles.has(filename)) {
      diffs.push({
        code: 'lost-density-aware-file',
        file: filename,
        detail: 'File dropped density tokens; restore them or, if it was never a required owner, remove it from the baseline only after review.',
      });
    }
  }

  for (const filename of measuredFiles) {
    if (!baselineFiles.has(filename)) {
      diffs.push({
        code: 'new-density-aware-file',
        file: filename,
        detail: `Add to densityAdoptionBaseline.json (densityTokenCount=${measured[filename].densityTokenCount}, fixedSpacingCount=${measured[filename].fixedSpacingCount}).`,
      });
      continue;
    }
    const current = measured[filename];
    const expected = baseline.files[filename];
    if (current.densityTokenCount < expected.densityTokenCount) {
      diffs.push({
        code: 'density-token-regression',
        file: filename,
        detail: `density tokens ${current.densityTokenCount} < baseline ${expected.densityTokenCount}.`,
      });
    } else if (current.densityTokenCount > expected.densityTokenCount) {
      diffs.push({
        code: 'baseline-needs-tightening',
        file: filename,
        detail: `density tokens grew to ${current.densityTokenCount}; raise the baseline floor from ${expected.densityTokenCount}.`,
      });
    }
    if (current.fixedSpacingCount > expected.fixedSpacingCount) {
      diffs.push({
        code: 'fixed-spacing-regression',
        file: filename,
        detail: `fixed spacing ${current.fixedSpacingCount} > baseline ${expected.fixedSpacingCount}.`,
      });
    } else if (current.fixedSpacingCount < expected.fixedSpacingCount) {
      diffs.push({
        code: 'baseline-needs-tightening',
        file: filename,
        detail: `fixed spacing shrank to ${current.fixedSpacingCount}; lower the baseline ceiling from ${expected.fixedSpacingCount}.`,
      });
    }
  }

  return diffs;
}

export function serializeAdoptionBaseline(
  files: Record<string, FileAdoption>,
): DensityAdoptionBaseline {
  const ordered = Object.keys(files).sort().map((filename) => files[filename]);
  return {
    version: DENSITY_ADOPTION_BASELINE_VERSION,
    files: Object.fromEntries(ordered.map((entry) => [entry.file, {
      file: entry.file,
      densityTokenCount: entry.densityTokenCount,
      fixedSpacingCount: entry.fixedSpacingCount,
    }])),
  };
}

export function formatAdoptionDiffs(diffs: readonly AdoptionDiff[]): string {
  if (diffs.length === 0) return '';
  return diffs.map((diff) => `[${diff.code}] ${diff.file}: ${diff.detail}`).join('\n');
}
