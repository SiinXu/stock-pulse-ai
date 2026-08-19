// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  SHARED_CONTROL_A11Y_EXEMPTIONS,
  SHARED_CONTROL_ADOPTION_BASELINE_VERSION,
  SHARED_CONTROL_BASELINE_PATH,
  SHARED_CONTROL_COMPOUND_OWNERS,
  SHARED_CONTROL_REQUIRED_OWNER_FILES,
  SHARED_CONTROL_REQUIRED_OWNERS,
  SHARED_CONTROL_SCAN_EXCLUSIONS,
  applySharedControlExemptions,
  collectSharedControlAdoption,
  diffSharedControlAdoption,
  formatAdoptionDiffs,
  scanSharedControlAdoption,
  serializeAdoptionBaseline,
  type SharedControlAdoptionBaseline,
} from './sharedControlAdoptionRatchet';
import {
  assertNonEmptyProductionInventory,
  productionTypeScriptSources,
} from './productionSourceInventory';

function loadBaseline(): SharedControlAdoptionBaseline {
  return JSON.parse(fs.readFileSync(SHARED_CONTROL_BASELINE_PATH, 'utf8')) as SharedControlAdoptionBaseline;
}

describe('shared-control adoption ratchet fixtures', () => {
  it('follows aliases instead of requiring the tag string at the JSX site', () => {
    const source = `
      const Tag = 'button';
      const Nested = Tag;
      export function Panel({ compact }: { compact: boolean }) {
        const Maybe = compact ? 'button' : 'div';
        return (
          <>
            <Tag type="button">Alias</Tag>
            <Nested type="button">Nested</Nested>
            <Maybe type="button">Maybe</Maybe>
          </>
        );
      }
    `;
    expect(scanSharedControlAdoption('../../pages/AliasPage.tsx', source)).toEqual([
      expect.objectContaining({ kind: 'native-button', line: 8, token: 'button' }),
      expect.objectContaining({ kind: 'native-button', line: 9, token: 'button' }),
      expect.objectContaining({ kind: 'native-button', line: 10, token: 'button' }),
    ]);
  });

  it('detects multiline JSX, spread props, and createElement factories', () => {
    const source = `
      import { createElement } from 'react';
      export function Panel(props: Record<string, unknown>) {
        return (
          <>
            <button
              type="button"
              {...props}
            >
              Multiline
            </button>
            {createElement('button', { type: 'button', ...props }, 'Factory')}
            {React.createElement('button', { type: 'button' }, 'ReactFactory')}
            {document.createElement('button')}
          </>
        );
      }
    `;
    const findings = scanSharedControlAdoption('../../pages/SpreadPage.tsx', source);
    expect(findings).toEqual([
      expect.objectContaining({ kind: 'native-button', line: 6, token: 'button' }),
      expect.objectContaining({ kind: 'native-button', line: 12, token: 'button' }),
      expect.objectContaining({ kind: 'native-button', line: 13, token: 'button' }),
      expect.objectContaining({ kind: 'native-button', line: 14, token: 'button' }),
    ]);
  });

  it('does not treat comments, types, or string copy as native buttons', () => {
    const source = `
      type Native = 'button';
      // <button type="button">comment</button>
      /* role="button" */
      export function Panel() {
        const copy = '<button type="button">string</button>';
        return <div data-hint={copy} role="note" />;
      }
    `;
    expect(scanSharedControlAdoption('../../pages/FalsePositivePage.tsx', source)).toEqual([]);
  });

  it('detects role=button on non-button hosts and ignores selector strings', () => {
    const source = `
      const NESTED = '[role="button"]';
      export function Panel() {
        return (
          <>
            <div role="button">Div</div>
            <circle role={'button'} />
            <button type="button" role="button">Still a button</button>
          </>
        );
      }
    `;
    const findings = scanSharedControlAdoption('../../pages/RolePage.tsx', source);
    expect(findings).toEqual([
      expect.objectContaining({ kind: 'role-button', token: 'div' }),
      expect.objectContaining({ kind: 'role-button', token: 'circle' }),
      expect.objectContaining({ kind: 'native-button', token: 'button' }),
    ]);
  });

  it('honors documented a11y exemptions and rejects undeclared copies', () => {
    const file = '../run-flow/ProcessTimeline.tsx';
    const source = `
      export function Item() {
        return (
          <>
            <summary role="button">Owned</summary>
            <summary role="button">Copy</summary>
          </>
        );
      }
    `;
    const findings = scanSharedControlAdoption(file, source);
    const exemptions = SHARED_CONTROL_A11Y_EXEMPTIONS.filter((entry) => entry.file === file);
    const { remaining, diffs } = applySharedControlExemptions(findings, exemptions);
    expect(remaining.map((finding) => finding.token)).toEqual(['summary']);
    expect(diffs.some((diff) => diff.code === 'exemption-overflow')).toBe(true);
  });

  it('treats dropping debt or adding a bypass as a regression, including file moves', () => {
    const measured = {
      '../../features/OldPage.tsx': {
        file: '../../features/OldPage.tsx',
        nativeButtonCount: 2,
        roleButtonCount: 0,
      },
      '../../pages/WorsePage.tsx': {
        file: '../../pages/WorsePage.tsx',
        nativeButtonCount: 2,
        roleButtonCount: 1,
      },
    };
    const baseline: SharedControlAdoptionBaseline = {
      version: 1,
      files: {
        '../../pages/OldPage.tsx': {
          file: '../../pages/OldPage.tsx',
          nativeButtonCount: 2,
          roleButtonCount: 0,
        },
        '../../pages/WorsePage.tsx': {
          file: '../../pages/WorsePage.tsx',
          nativeButtonCount: 1,
          roleButtonCount: 0,
        },
      },
    };
    const diffs = diffSharedControlAdoption(measured, baseline, { enforceRequiredOwners: false });
    expect(diffs.map((diff) => diff.code).sort()).toEqual([
      'bypass-regression',
      'bypass-regression',
      'file-moved',
    ]);
  });

  it('excludes playground sources from the measured inventory', () => {
    const { files } = collectSharedControlAdoption({
      '../../playground/ComponentPlaygroundPage.tsx': '<button type="button">Play</button>',
      '../common/Button.tsx': '<button type="button">Run</button>',
    });
    expect(files['../../playground/ComponentPlaygroundPage.tsx']).toBeUndefined();
    expect(files['../common/Button.tsx']).toEqual({
      file: '../common/Button.tsx',
      nativeButtonCount: 1,
      roleButtonCount: 0,
    });
  });

  it('requires tightening when measured debt shrinks', () => {
    const measured = {
      '../../pages/HomePage.tsx': {
        file: '../../pages/HomePage.tsx',
        nativeButtonCount: 1,
        roleButtonCount: 0,
      },
    };
    const baseline: SharedControlAdoptionBaseline = {
      version: 1,
      files: {
        '../../pages/HomePage.tsx': {
          file: '../../pages/HomePage.tsx',
          nativeButtonCount: 3,
          roleButtonCount: 0,
        },
      },
    };
    const diffs = diffSharedControlAdoption(measured, baseline, { enforceRequiredOwners: false });
    expect(diffs.map((diff) => diff.code)).toEqual(['baseline-needs-tightening']);
  });
});

describe('shared-control adoption ratchet production inventory', () => {
  assertNonEmptyProductionInventory(productionTypeScriptSources, 'productionTypeScriptSources');

  it('keeps required owners and ratchets the measured native-button baseline', () => {
    const { files, exemptionDiffs } = collectSharedControlAdoption(productionTypeScriptSources);
    const baseline = loadBaseline();
    const diffs = [
      ...exemptionDiffs,
      ...diffSharedControlAdoption(files, baseline),
    ];
    expect(
      diffs,
      [
        formatAdoptionDiffs(diffs),
        'Measured inventory (write this to src/design/sharedControlAdoptionBaseline.json when tightening):',
        JSON.stringify(serializeAdoptionBaseline(files), null, 2),
      ].join('\n'),
    ).toEqual([]);
    expect(baseline.version).toBe(SHARED_CONTROL_ADOPTION_BASELINE_VERSION);
    expect(SHARED_CONTROL_REQUIRED_OWNERS).toEqual([
      'Button.tsx',
      'IconButton.tsx',
      'Pressable.tsx',
      'SelectionChip.tsx',
    ]);
    expect(SHARED_CONTROL_REQUIRED_OWNER_FILES).toEqual([
      '../common/Button.tsx',
      '../common/IconButton.tsx',
      '../common/Pressable.tsx',
      '../common/SelectionChip.tsx',
    ]);
    expect(SHARED_CONTROL_SCAN_EXCLUSIONS.length).toBeGreaterThan(3);
    for (const [file, reason] of Object.entries(SHARED_CONTROL_COMPOUND_OWNERS)) {
      expect(files[file], `${file} is listed as a compound owner but has no native button`).toBeDefined();
      expect(reason.length).toBeGreaterThan(12);
    }
    for (const exemption of SHARED_CONTROL_A11Y_EXEMPTIONS) {
      expect(
        productionTypeScriptSources[exemption.file],
        `${exemption.file} is listed as an a11y exemption but is not in the production inventory`,
      ).toBeDefined();
      expect(exemption.count).toBeGreaterThan(0);
      expect(exemption.reason.length).toBeGreaterThan(12);
    }
  });
});
