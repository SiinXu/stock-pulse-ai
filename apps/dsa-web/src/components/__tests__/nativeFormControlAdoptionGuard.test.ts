// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import ts from 'typescript';
import { describe, expect, it } from 'vitest';
import {
  isProductionSourcePath,
  productionTsxSources,
} from './productionSourceInventory';

type NativeFormTag = 'input' | 'select' | 'textarea';

type NativeControlFinding = {
  file: string;
  line: number;
  tag: NativeFormTag;
};

type NativeControlAllowance = {
  tags: Partial<Record<NativeFormTag, number>>;
  reason: string;
  removeWhen?: string;
};

const SHARED_PRIMITIVE_ALLOWANCES = new Map<string, NativeControlAllowance>([
  ['../common/Checkbox.tsx', { tags: { input: 1 }, reason: 'Checkbox owns the native checkbox primitive.' }],
  ['../common/DatePicker.tsx', { tags: { input: 1 }, reason: 'DatePicker owns its calendar text field.' }],
  ['../common/FileInput.tsx', { tags: { input: 1 }, reason: 'FileInput owns the native file picker.' }],
  ['../common/Input.tsx', { tags: { input: 1 }, reason: 'Input owns the shared text-field primitive.' }],
  ['../common/SearchableSelect.tsx', { tags: { input: 1 }, reason: 'SearchableSelect owns its filter field.' }],
  ['../common/SearchInput.tsx', { tags: { input: 1 }, reason: 'SearchInput owns the shared search field.' }],
  ['../common/Textarea.tsx', { tags: { textarea: 1 }, reason: 'Textarea owns the shared multiline primitive.' }],
  ['../common/WorkspaceNavigation.tsx', { tags: { select: 1 }, reason: 'WorkspaceNavigation owns the compact native mobile fallback.' }],
]);

const BUSINESS_NATIVE_CONTROL_DEBT = new Map<string, NativeControlAllowance>([
  ['../charts/KlineChart.tsx', {
    tags: { input: 1 },
    reason: 'The chart range slider is a domain-specific compound control.',
    removeWhen: 'A shared range-slider primitive preserves chart keyboard and pointer behavior.',
  }],
  ['../chat/ChatComposer.tsx', {
    tags: { textarea: 1 },
    reason: 'ChatComposer owns autosize, composition, and submit-key behavior.',
    removeWhen: 'Textarea exposes the composer ref and autosize contract without visual overrides.',
  }],
  ['../StockAutocomplete/StockAutocomplete.tsx', {
    tags: { input: 2 },
    reason: 'StockAutocomplete owns desktop and compact combobox inputs.',
    removeWhen: 'A shared combobox primitive covers both responsive input modes.',
  }],
  ['../../pages/ReportVersionComparePage.tsx', {
    tags: { input: 1 },
    reason: 'The comparison reveal slider is an interactive media control, not a data-entry field.',
    removeWhen: 'A shared before/after reveal primitive owns the range input.',
  }],
]);

const BUSINESS_NATIVE_CONTROL_DEBT_CEILING = 5;

function parseSource(filename: string, source: string): ts.SourceFile {
  return ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
}

function findNativeFormControls(filename: string, source: string): NativeControlFinding[] {
  const sourceFile = parseSource(filename, source);
  const findings: NativeControlFinding[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tagName = ts.isIdentifier(node.tagName) ? node.tagName.text : '';
      if (tagName === 'input' || tagName === 'select' || tagName === 'textarea') {
        findings.push({
          file: filename,
          line: sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1,
          tag: tagName,
        });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return findings;
}

function allowanceViolations(
  findings: readonly NativeControlFinding[],
  allowances: ReadonlyMap<string, NativeControlAllowance>,
): NativeControlFinding[] {
  const seen = new Map<string, number>();
  return findings.filter((finding) => {
    const allowance = allowances.get(finding.file);
    const key = `${finding.file}:${finding.tag}`;
    const nextCount = (seen.get(key) ?? 0) + 1;
    seen.set(key, nextCount);
    return nextCount > (allowance?.tags[finding.tag] ?? 0);
  });
}

describe('native form-control adoption guard', () => {
  it('detects raw business controls outside explicit file-and-tag ceilings', () => {
    const findings = findNativeFormControls(
      '../../pages/ExamplePage.tsx',
      '<input /><select><option /></select><textarea />',
    );
    expect(allowanceViolations(findings, BUSINESS_NATIVE_CONTROL_DEBT)).toEqual(findings);
  });

  it('keeps shared owners explicit and business debt shrink-only', () => {
    const findings = Object.entries(productionTsxSources)
      .filter(([filename]) => isProductionSourcePath(filename) && !filename.includes('/playground/'))
      .flatMap(([filename, source]) => findNativeFormControls(filename, source));
    const sharedFindings = findings.filter((finding) => finding.file.includes('/common/'));
    const businessFindings = findings.filter((finding) => !finding.file.includes('/common/'));

    expect(allowanceViolations(sharedFindings, SHARED_PRIMITIVE_ALLOWANCES)).toEqual([]);
    expect(allowanceViolations(businessFindings, BUSINESS_NATIVE_CONTROL_DEBT)).toEqual([]);
    expect(businessFindings.length).toBeLessThanOrEqual(BUSINESS_NATIVE_CONTROL_DEBT_CEILING);
  });
});
