// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import ts from 'typescript';
import { isProductionSourcePath } from './productionSourceInventory';

export type SharedControlFindingKind = 'native-button' | 'role-button';

export type SharedControlFinding = {
  file: string;
  line: number;
  kind: SharedControlFindingKind;
  token: string;
};

export type FileAdoption = {
  file: string;
  nativeButtonCount: number;
  roleButtonCount: number;
};

export type SharedControlAdoptionBaseline = {
  version: number;
  files: Record<string, FileAdoption>;
};

export type SharedControlExemption = {
  file: string;
  kind: SharedControlFindingKind;
  token: string;
  count: number;
  reason: string;
};

export type AdoptionDiff = {
  code:
    | 'missing-required-owner'
    | 'lost-owner-file'
    | 'lost-debt-file'
    | 'new-bypass'
    | 'new-owner-file'
    | 'bypass-regression'
    | 'baseline-needs-tightening'
    | 'stale-exemption'
    | 'exemption-overflow'
    | 'file-moved';
  file: string;
  detail: string;
};

/**
 * Shared primitives that must keep a native button. Losing the element is a
 * contract regression, not a baseline edit. Paths are exact so a same-named
 * page file cannot masquerade as the owner.
 */
export const SHARED_CONTROL_REQUIRED_OWNER_FILES = [
  '../common/Button.tsx',
  '../common/IconButton.tsx',
  '../common/Pressable.tsx',
  '../common/SelectionChip.tsx',
] as const;

export const SHARED_CONTROL_REQUIRED_OWNERS = [
  'Button.tsx',
  'IconButton.tsx',
  'Pressable.tsx',
  'SelectionChip.tsx',
] as const;

/**
 * Compound shared controls that own native buttons as part of their primitive.
 * Product pages must not copy these; count changes still require a baseline
 * update so the inventory stays honest.
 */
export const SHARED_CONTROL_COMPOUND_OWNERS: Readonly<Record<string, string>> = {
  '../common/AppliedFilterChips.tsx': 'AppliedFilterChips owns the removable filter-chip command.',
  '../common/Collapsible.tsx': 'Collapsible owns the disclosure trigger.',
  '../common/DataTable.tsx': 'DataTable owns sortable-header buttons.',
  '../common/DatePicker.tsx': 'DatePicker owns calendar triggers and day cells.',
  '../common/JsonViewer.tsx': 'JsonViewer owns the copy command on the highlighted payload.',
  '../common/Pagination.tsx': 'Pagination owns page-number commands.',
  '../common/SearchableSelect.tsx': 'SearchableSelect owns the combobox trigger and clear command.',
  '../common/SegmentedControl.tsx': 'SegmentedControl owns mutually exclusive option buttons.',
  '../common/Select.tsx': 'Select owns the listbox trigger.',
  '../common/Switch.tsx': 'Switch owns the native switch button.',
  '../common/Tabs.tsx': 'Tabs owns tablist buttons.',
  '../common/TimePicker.tsx': 'TimePicker owns clock triggers and hour/minute cells.',
};

/**
 * Reviewed accessibility cases that must stay native. Do not park leftover
 * product-button debt here.
 */
export const SHARED_CONTROL_A11Y_EXEMPTIONS: readonly SharedControlExemption[] = [
  {
    file: '../decision-signals/DecisionSignalTimeline.tsx',
    kind: 'role-button',
    token: 'circle',
    count: 1,
    reason: 'SVG scatter hit targets cannot host an HTML button; the circle keeps a named keyboard target.',
  },
];

/**
 * Inventory exclusions and why they are not product bypasses. Tests, generated
 * code, vendor trees, and the playground are out of the shipped control contract.
 */
export const SHARED_CONTROL_SCAN_EXCLUSIONS = [
  {
    pattern: 'tests / __tests__ / *.test.* / *.spec.* / fixtures',
    reason: 'Harnesses and fixtures may use native buttons; they are not shipped UI.',
  },
  {
    pattern: 'generated / *.generated.*',
    reason: 'Generated snapshots are not author-owned product UI.',
  },
  {
    pattern: 'vendor / node_modules',
    reason: 'Third-party code is outside src/ and is not the product contract.',
  },
  {
    pattern: 'src/dev/**',
    reason: 'Dev-only tooling is gated behind import.meta.env.DEV and tree-shaken from production.',
  },
  {
    pattern: 'playground',
    reason: 'Developer preview harness, not a shipped product route.',
  },
  {
    pattern: 'stories / *.story.* / *.stories.*',
    reason: 'Visual fixtures are not production mounts.',
  },
] as const;

export const SHARED_CONTROL_ADOPTION_BASELINE_VERSION = 1;
export const SHARED_CONTROL_BASELINE_PATH = 'src/design/sharedControlAdoptionBaseline.json';

const INTRINSIC_BUTTON = 'button';
const ROLE_BUTTON = 'button';
const PREFILTER = 'button';

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

function lineOf(sourceFile: ts.SourceFile, node: ts.Node): number {
  return sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
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

function staticString(expression: ts.Expression | undefined): string | undefined {
  if (!expression) return undefined;
  const value = unwrapExpression(expression);
  if (ts.isStringLiteralLike(value)) return value.text;
  return undefined;
}

function collectButtonAliases(sourceFile: ts.SourceFile): Map<string, string> {
  const aliases = new Map<string, string>();
  const visit = (node: ts.Node): void => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      const value = unwrapExpression(node.initializer);
      if (ts.isStringLiteralLike(value) && value.text === INTRINSIC_BUTTON) {
        aliases.set(node.name.text, INTRINSIC_BUTTON);
      } else if (ts.isIdentifier(value) && aliases.get(value.text) === INTRINSIC_BUTTON) {
        aliases.set(node.name.text, INTRINSIC_BUTTON);
      } else if (ts.isConditionalExpression(value)) {
        const whenTrue = staticString(value.whenTrue);
        const whenFalse = staticString(value.whenFalse);
        if (whenTrue === INTRINSIC_BUTTON || whenFalse === INTRINSIC_BUTTON) {
          aliases.set(node.name.text, INTRINSIC_BUTTON);
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  // Two passes so `const Tag = Inner` sees Inner collected on the first walk.
  visit(sourceFile);
  visit(sourceFile);
  return aliases;
}

function jsxTagName(
  node: ts.JsxOpeningElement | ts.JsxSelfClosingElement,
): string | undefined {
  const tag = node.tagName;
  if (ts.isIdentifier(tag)) return tag.text;
  return undefined;
}

function isCreateElementCall(node: ts.CallExpression): boolean {
  if (ts.isIdentifier(node.expression)) return node.expression.text === 'createElement';
  return ts.isPropertyAccessExpression(node.expression)
    && node.expression.name.text === 'createElement';
}

function resolvedElementName(
  expression: ts.Expression | undefined,
  aliases: ReadonlyMap<string, string>,
): string | undefined {
  if (!expression) return undefined;
  const value = unwrapExpression(expression);
  if (ts.isStringLiteralLike(value)) return value.text;
  if (ts.isIdentifier(value)) return aliases.get(value.text) ?? value.text;
  return undefined;
}

function jsxAttributeValue(attribute: ts.JsxAttribute): string | undefined {
  if (!attribute.initializer) return undefined;
  if (ts.isStringLiteralLike(attribute.initializer)) return attribute.initializer.text;
  if (ts.isJsxExpression(attribute.initializer)) {
    return staticString(attribute.initializer.expression ?? undefined);
  }
  return undefined;
}

function jsxRole(node: ts.JsxOpeningElement | ts.JsxSelfClosingElement): string | undefined {
  for (const property of node.attributes.properties) {
    if (!ts.isJsxAttribute(property)) continue;
    const name = ts.isIdentifier(property.name) ? property.name.text : undefined;
    if (name === 'role') return jsxAttributeValue(property);
  }
  return undefined;
}

function objectLiteralRole(expression: ts.Expression | undefined): string | undefined {
  if (!expression) return undefined;
  const value = unwrapExpression(expression);
  if (!ts.isObjectLiteralExpression(value)) return undefined;
  for (const property of value.properties) {
    if (!ts.isPropertyAssignment(property)) continue;
    const name = ts.isIdentifier(property.name) || ts.isStringLiteralLike(property.name)
      ? property.name.text
      : undefined;
    if (name === 'role') return staticString(property.initializer);
  }
  return undefined;
}

function pushFinding(
  findings: SharedControlFinding[],
  file: string,
  line: number,
  kind: SharedControlFindingKind,
  token: string,
): void {
  findings.push({ file, line, kind, token });
}

export function mayContainSharedControl(source: string): boolean {
  return source.includes(PREFILTER);
}

export function scanSharedControlAdoption(filename: string, source: string): SharedControlFinding[] {
  if (!mayContainSharedControl(source)) return [];
  const sourceFile = parseSource(filename, source);
  const aliases = collectButtonAliases(sourceFile);
  const findings: SharedControlFinding[] = [];

  const visit = (node: ts.Node): void => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = jsxTagName(node);
      const resolved = tag ? (aliases.get(tag) ?? tag) : undefined;
      if (resolved === INTRINSIC_BUTTON) {
        pushFinding(findings, filename, lineOf(sourceFile, node), 'native-button', INTRINSIC_BUTTON);
      } else if (resolved && jsxRole(node) === ROLE_BUTTON && resolved !== INTRINSIC_BUTTON) {
        pushFinding(findings, filename, lineOf(sourceFile, node), 'role-button', resolved);
      }
    }

    if (ts.isCallExpression(node) && isCreateElementCall(node)) {
      const resolved = resolvedElementName(node.arguments[0], aliases);
      const role = objectLiteralRole(node.arguments[1]);
      if (resolved === INTRINSIC_BUTTON) {
        pushFinding(findings, filename, lineOf(sourceFile, node), 'native-button', INTRINSIC_BUTTON);
      } else if (resolved && role === ROLE_BUTTON && resolved !== INTRINSIC_BUTTON) {
        pushFinding(findings, filename, lineOf(sourceFile, node), 'role-button', resolved);
      }
    }

    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

function exemptionKey(file: string, kind: string, token: string): string {
  return `${file}\u0000${kind}\u0000${token}`;
}

export function applySharedControlExemptions(
  findings: readonly SharedControlFinding[],
  exemptions: readonly SharedControlExemption[] = SHARED_CONTROL_A11Y_EXEMPTIONS,
): {
  remaining: SharedControlFinding[];
  diffs: AdoptionDiff[];
} {
  const remaining: SharedControlFinding[] = [];
  const used = new Map<string, number>();
  const exemptionByKey = new Map(
    exemptions.map((exemption) => [
      exemptionKey(exemption.file, exemption.kind, exemption.token),
      exemption,
    ]),
  );

  for (const finding of findings) {
    const key = exemptionKey(finding.file, finding.kind, finding.token);
    const exemption = exemptionByKey.get(key);
    if (!exemption) {
      remaining.push(finding);
      continue;
    }
    const next = (used.get(key) ?? 0) + 1;
    used.set(key, next);
    if (next > exemption.count) remaining.push(finding);
  }

  const diffs: AdoptionDiff[] = [];
  for (const exemption of exemptions) {
    const key = exemptionKey(exemption.file, exemption.kind, exemption.token);
    const count = used.get(key) ?? 0;
    if (count === 0) {
      diffs.push({
        code: 'stale-exemption',
        file: exemption.file,
        detail: `${exemption.kind}:${exemption.token} is listed but not present; remove it from SHARED_CONTROL_A11Y_EXEMPTIONS.`,
      });
    } else if (count > exemption.count) {
      diffs.push({
        code: 'exemption-overflow',
        file: exemption.file,
        detail: `${exemption.kind}:${exemption.token} uses ${count}, exceeding exemption count ${exemption.count}.`,
      });
    }
  }
  return { remaining, diffs };
}

export function isPlaygroundPath(filename: string): boolean {
  return filename.includes('/playground/');
}

export function isOwnerPath(filename: string): boolean {
  return (SHARED_CONTROL_REQUIRED_OWNER_FILES as readonly string[]).includes(filename)
    || Object.prototype.hasOwnProperty.call(SHARED_CONTROL_COMPOUND_OWNERS, filename);
}

export function isScannedSourcePath(filename: string): boolean {
  return isProductionSourcePath(filename) && !isPlaygroundPath(filename);
}

export function summarizeFileAdoption(
  filename: string,
  findings: readonly SharedControlFinding[],
): FileAdoption {
  return {
    file: filename,
    nativeButtonCount: findings.filter((finding) => finding.kind === 'native-button').length,
    roleButtonCount: findings.filter((finding) => finding.kind === 'role-button').length,
  };
}

export function collectSharedControlAdoption(
  sources: Record<string, string>,
  exemptions: readonly SharedControlExemption[] = SHARED_CONTROL_A11Y_EXEMPTIONS,
): {
  files: Record<string, FileAdoption>;
  exemptionDiffs: AdoptionDiff[];
} {
  const files: Record<string, FileAdoption> = {};
  const allFindings: SharedControlFinding[] = [];
  const scannedFiles = new Set<string>();

  for (const [filename, source] of Object.entries(sources)) {
    if (!isScannedSourcePath(filename)) continue;
    scannedFiles.add(filename);
    allFindings.push(...scanSharedControlAdoption(filename, source));
  }

  const scopedExemptions = exemptions.filter((exemption) => scannedFiles.has(exemption.file));
  const { remaining, diffs } = applySharedControlExemptions(allFindings, scopedExemptions);
  const remainingByFile = new Map<string, SharedControlFinding[]>();
  for (const finding of remaining) {
    const list = remainingByFile.get(finding.file) ?? [];
    list.push(finding);
    remainingByFile.set(finding.file, list);
  }
  for (const [filename, findings] of remainingByFile) {
    files[filename] = summarizeFileAdoption(filename, findings);
  }
  return { files, exemptionDiffs: diffs };
}

function basenameOf(filename: string): string {
  return filename.split('/').pop() ?? filename;
}

export function diffSharedControlAdoption(
  measured: Record<string, FileAdoption>,
  baseline: SharedControlAdoptionBaseline,
  options: { enforceRequiredOwners?: boolean } = {},
): AdoptionDiff[] {
  const diffs: AdoptionDiff[] = [];
  const measuredFiles = new Set(Object.keys(measured));
  const baselineFiles = new Set(Object.keys(baseline.files));
  const enforceRequired = options.enforceRequiredOwners !== false;

  if (enforceRequired) {
    for (const owner of SHARED_CONTROL_REQUIRED_OWNER_FILES) {
      const current = measured[owner];
      if (!current || current.nativeButtonCount < 1) {
        diffs.push({
          code: 'missing-required-owner',
          file: owner,
          detail: 'Required shared control no longer renders a native button.',
        });
      }
    }
  }

  const consumedNew = new Set<string>();
  for (const filename of baselineFiles) {
    if (measuredFiles.has(filename)) continue;
    const expected = baseline.files[filename];
    const movedTo = Array.from(measuredFiles).find((candidate) => (
      !baselineFiles.has(candidate)
      && !consumedNew.has(candidate)
      && basenameOf(candidate) === basenameOf(filename)
      && measured[candidate].nativeButtonCount === expected.nativeButtonCount
      && measured[candidate].roleButtonCount === expected.roleButtonCount
    ));
    if (movedTo) {
      consumedNew.add(movedTo);
      diffs.push({
        code: 'file-moved',
        file: filename,
        detail: `Inventory moved to ${movedTo} with the same counts; update ${SHARED_CONTROL_BASELINE_PATH}.`,
      });
      continue;
    }
    diffs.push({
      code: isOwnerPath(filename) ? 'lost-owner-file' : 'lost-debt-file',
      file: filename,
      detail: isOwnerPath(filename)
        ? 'Shared-control owner dropped every native/role button; restore it or remove the owner after review.'
        : `File dropped native/role-button debt; remove it from ${SHARED_CONTROL_BASELINE_PATH}.`,
    });
  }

  for (const filename of measuredFiles) {
    if (consumedNew.has(filename)) continue;
    const current = measured[filename];
    if (!baselineFiles.has(filename)) {
      diffs.push({
        code: isOwnerPath(filename) ? 'new-owner-file' : 'new-bypass',
        file: filename,
        detail: isOwnerPath(filename)
          ? `Add the new owner to ${SHARED_CONTROL_BASELINE_PATH} (nativeButtonCount=${current.nativeButtonCount}, roleButtonCount=${current.roleButtonCount}).`
          : `New unaudited native/role-button usage (nativeButtonCount=${current.nativeButtonCount}, roleButtonCount=${current.roleButtonCount}). Use Button/IconButton/Pressable or a reviewed a11y exemption.`,
      });
      continue;
    }
    const expected = baseline.files[filename];
    const owner = isOwnerPath(filename);
    if (current.nativeButtonCount > expected.nativeButtonCount) {
      diffs.push({
        code: owner ? 'baseline-needs-tightening' : 'bypass-regression',
        file: filename,
        detail: `native buttons ${current.nativeButtonCount} > baseline ${expected.nativeButtonCount}.`,
      });
    } else if (current.nativeButtonCount < expected.nativeButtonCount) {
      diffs.push({
        code: 'baseline-needs-tightening',
        file: filename,
        detail: `native buttons shrank to ${current.nativeButtonCount}; lower the baseline ceiling from ${expected.nativeButtonCount}.`,
      });
    }
    if (current.roleButtonCount > expected.roleButtonCount) {
      diffs.push({
        code: owner ? 'baseline-needs-tightening' : 'bypass-regression',
        file: filename,
        detail: `role=button ${current.roleButtonCount} > baseline ${expected.roleButtonCount}.`,
      });
    } else if (current.roleButtonCount < expected.roleButtonCount) {
      diffs.push({
        code: 'baseline-needs-tightening',
        file: filename,
        detail: `role=button shrank to ${current.roleButtonCount}; lower the baseline ceiling from ${expected.roleButtonCount}.`,
      });
    }
  }

  return diffs;
}

export function serializeAdoptionBaseline(
  files: Record<string, FileAdoption>,
): SharedControlAdoptionBaseline {
  const ordered = Object.keys(files).sort().map((filename) => files[filename]);
  return {
    version: SHARED_CONTROL_ADOPTION_BASELINE_VERSION,
    files: Object.fromEntries(ordered.map((entry) => [entry.file, {
      file: entry.file,
      nativeButtonCount: entry.nativeButtonCount,
      roleButtonCount: entry.roleButtonCount,
    }])),
  };
}

export function formatAdoptionDiffs(diffs: readonly AdoptionDiff[]): string {
  if (diffs.length === 0) return '';
  return diffs.map((diff) => `[${diff.code}] ${diff.file}: ${diff.detail}`).join('\n');
}
