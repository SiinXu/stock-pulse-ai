// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  DENSITY_FIXED_GEOMETRY_EXEMPTIONS,
  DENSITY_MODES,
  DENSITY_REQUIRED_OWNERS,
} from '../../design/density';
import {
  applyDensityExemptions,
  collectDensityAdoption,
  DENSITY_PRODUCTION_COLLECT_BUDGET_MS,
  diffDensityAdoption,
  formatAdoptionDiffs,
  getDensityScanStats,
  isDensityCatalogPath,
  isPlaygroundPath,
  resetDensityScanAccounting,
  resetDensityScanStats,
  scanDensityAdoption,
  serializeAdoptionBaseline,
  sourceMayContainDensityFindings,
  type DensityAdoptionBaseline,
} from './densityAdoptionRatchet';
import {
  assertNonEmptyProductionInventory,
  productionTypeScriptSources,
} from './productionSourceInventory';

const BASELINE_PATH = 'src/design/densityAdoptionBaseline.json';
const INDEX_CSS_PATH = 'src/index.css';

function loadBaseline(): DensityAdoptionBaseline {
  return JSON.parse(fs.readFileSync(BASELINE_PATH, 'utf8')) as DensityAdoptionBaseline;
}

describe('density adoption ratchet fixtures', () => {
  it('follows aliases instead of requiring the class string at the className site', () => {
    const source = `
      const PAGE_PAD = 'p-4';
      const STACK = compact ? 'gap-4' : 'gap-6';
      export function Panel() {
        return <div className={PAGE_PAD} />;
      }
    `;
    const tokens = scanDensityAdoption('../../pages/AliasPage.tsx', source)
      .filter((finding) => finding.kind === 'fixed-spacing')
      .map((finding) => finding.token)
      .sort();
    expect(tokens).toEqual(['gap-4', 'gap-6', 'p-4']);
  });

  it('detects computed class templates and inline styles', () => {
    const source = `
      const pad = \`p-\${size}\`;
      export function Panel({ compact }: { compact: boolean }) {
        return (
          <div
            className={compact ? 'density-gap-stack' : 'gap-4'}
            style={{ padding: compact ? 'var(--density-stack-gap)' : '16px', gap: 12 }}
          />
        );
      }
    `;
    const findings = scanDensityAdoption('../../pages/ComputedPage.tsx', source);
    expect(findings).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'computed-spacing', token: 'computed:p-' }),
      expect.objectContaining({ kind: 'density-token', token: 'density-gap-stack' }),
      expect.objectContaining({ kind: 'fixed-spacing', token: 'gap-4' }),
      expect.objectContaining({ kind: 'density-token', token: 'style:padding:var(--density-stack-gap)' }),
      expect.objectContaining({ kind: 'fixed-spacing', token: 'style:padding:16px' }),
      expect.objectContaining({ kind: 'fixed-spacing', token: 'style:gap:12' }),
    ]));
  });

  it('does not treat overlay elevation shadows as density spacing adoption', () => {
    const findings = scanDensityAdoption(
      '../theme/ThemeToggle.tsx',
      '<div className="p-4 shadow-elevation-popper" />',
    );
    expect(findings.some((finding) => finding.kind === 'density-token')).toBe(false);
    expect(findings.map((finding) => finding.token)).toEqual(['p-4']);
  });

  it('treats compact/comfortable density classes as compact-aware and p-4 as a revert', () => {
    expect(DENSITY_MODES).toEqual(['comfortable', 'compact']);
    const compactAware = scanDensityAdoption(
      '../common/CompactOwner.tsx',
      '<div data-density="compact" className="density-surface-pad-sm density-gap-stack" />',
    );
    const reverted = scanDensityAdoption(
      '../common/RevertedOwner.tsx',
      '<div className="p-4 gap-4" />',
    );
    expect(compactAware.some((finding) => finding.token === 'data-density')).toBe(true);
    expect(compactAware.some((finding) => finding.kind === 'density-token')).toBe(true);
    expect(reverted.some((finding) => finding.kind === 'density-token')).toBe(false);
    expect(reverted.map((finding) => finding.token).sort()).toEqual(['gap-4', 'p-4']);
  });

  it('honors documented fixed-geometry exemptions and rejects undeclared copies', () => {
    const file = '../common/Drawer.tsx';
    const source = `
      const footer = 'density-overlay-pad-x py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]';
      const extra = 'pb-[calc(0.75rem+env(safe-area-inset-bottom))]';
    `;
    const findings = scanDensityAdoption(file, source);
    const exemptions = DENSITY_FIXED_GEOMETRY_EXEMPTIONS.filter((entry) => entry.file === file);
    const { remaining, diffs } = applyDensityExemptions(
      findings.filter((finding) => finding.kind !== 'density-token'),
      exemptions,
    );
    expect(remaining.map((finding) => finding.token)).toEqual([
      'py-3',
      'pb-[calc(0.75rem+env(safe-area-inset-bottom))]',
    ]);
    expect(diffs.some((diff) => diff.code === 'exemption-overflow')).toBe(true);
  });

  it('ignores comments, types, and micro/reset spacing so the scan is not grep-only', () => {
    const source = `
      type Legacy = 'p-4' | 'gap-4';
      // className="p-4 gap-4"
      /* density-surface-pad-md p-6 */
      export function Panel() {
        return <div className="p-0 mt-1 gap-1.5 m-auto" style={{ padding: 0 }} />;
      }
    `;
    expect(scanDensityAdoption('../../pages/FalsePositivePage.tsx', source)).toEqual([]);
  });

  it('requires tightening when measured debt shrinks or density tokens grow', () => {
    const measured = {
      '../common/Surface.tsx': {
        file: '../common/Surface.tsx',
        densityTokenCount: 4,
        fixedSpacingCount: 0,
      },
    };
    const baseline: DensityAdoptionBaseline = {
      version: 1,
      files: {
        '../common/Surface.tsx': {
          file: '../common/Surface.tsx',
          densityTokenCount: 3,
          fixedSpacingCount: 1,
        },
      },
    };
    const diffs = diffDensityAdoption(measured, baseline, { enforceRequiredOwners: false });
    expect(diffs.map((diff) => diff.code).sort()).toEqual([
      'baseline-needs-tightening',
      'baseline-needs-tightening',
    ]);
  });

  it('treats dropping density tokens or adding fixed spacing as a regression', () => {
    const measured = {
      '../common/Surface.tsx': {
        file: '../common/Surface.tsx',
        densityTokenCount: 2,
        fixedSpacingCount: 2,
      },
    };
    const baseline: DensityAdoptionBaseline = {
      version: 1,
      files: {
        '../common/Surface.tsx': {
          file: '../common/Surface.tsx',
          densityTokenCount: 3,
          fixedSpacingCount: 0,
        },
        '../common/PageHeader.tsx': {
          file: '../common/PageHeader.tsx',
          densityTokenCount: 2,
          fixedSpacingCount: 0,
        },
      },
    };
    const diffs = diffDensityAdoption(measured, baseline, { enforceRequiredOwners: false });
    expect(diffs.map((diff) => diff.code).sort()).toEqual([
      'density-token-regression',
      'fixed-spacing-regression',
      'lost-density-aware-file',
    ]);
  });
});

describe('density adoption ratchet production inventory', () => {
  assertNonEmptyProductionInventory(productionTypeScriptSources, 'productionTypeScriptSources');

  const scannableFiles = Object.keys(productionTypeScriptSources).filter((filename) => (
    !isDensityCatalogPath(filename) && !isPlaygroundPath(filename)
  ));

  it('keeps required owners density-aware and ratchets the measured baseline', () => {
    resetDensityScanAccounting();
    const started = performance.now();
    const { files, exemptionDiffs } = collectDensityAdoption(productionTypeScriptSources);
    const elapsedMs = performance.now() - started;
    const cold = getDensityScanStats();
    const baseline = loadBaseline();
    const diffs = [
      ...exemptionDiffs,
      ...diffDensityAdoption(files, baseline),
    ];
    expect(
      diffs,
      [
        formatAdoptionDiffs(diffs),
        'Measured inventory (write this to src/design/densityAdoptionBaseline.json when tightening):',
        JSON.stringify(serializeAdoptionBaseline(files), null, 2),
      ].join('\n'),
    ).toEqual([]);
    expect(baseline.version).toBe(1);
    expect(DENSITY_REQUIRED_OWNERS).toEqual(expect.arrayContaining([
      'Surface.tsx',
      'PageHeader.tsx',
      'Toolbar.tsx',
      'Section.tsx',
      'Modal.tsx',
      'Drawer.tsx',
      'Sheet.tsx',
      'ConfirmDialog.tsx',
    ]));
    for (const exemption of DENSITY_FIXED_GEOMETRY_EXEMPTIONS) {
      expect(
        files[exemption.file],
        `${exemption.file} is listed as an exemption but is not density-aware`,
      ).toBeDefined();
      expect(exemption.count).toBeGreaterThan(0);
      expect(exemption.reason.length).toBeGreaterThan(12);
    }
    expect(scannableFiles.length).toBeGreaterThan(0);
    expect(cold.cacheHits).toBe(0);
    expect(cold.parsedFiles).toBeGreaterThan(0);
    expect(cold.skippedWithoutParse).toBeGreaterThan(0);
    expect(cold.parsedFiles + cold.skippedWithoutParse).toBe(scannableFiles.length);
    expect(
      elapsedMs,
      `collectDensityAdoption took ${elapsedMs.toFixed(1)}ms `
        + `(parsed=${cold.parsedFiles}, skipped=${cold.skippedWithoutParse})`,
    ).toBeLessThan(DENSITY_PRODUCTION_COLLECT_BUDGET_MS);
  }, 30_000);

  it('reuses the production inventory scan cache without a second parse', () => {
    const first = collectDensityAdoption(productionTypeScriptSources);
    resetDensityScanStats();
    const second = collectDensityAdoption(productionTypeScriptSources);
    expect(second).toEqual(first);
    expect(getDensityScanStats()).toEqual({
      cacheHits: scannableFiles.length,
      skippedWithoutParse: 0,
      parsedFiles: 0,
    });
  });

  it('keeps compact mode as a variable retune of the comfortable density scale', () => {
    const css = fs.readFileSync(INDEX_CSS_PATH, 'utf8');
    expect(css).toMatch(/--density-space-4:\s*1rem;/);
    const compact = css.match(/\[data-density="compact"\]\s*\{([^}]+)\}/);
    expect(compact?.[1]).toMatch(/--density-space-4:\s*0\.75rem;/);
    expect(DENSITY_MODES).toEqual(['comfortable', 'compact']);
  });
});

describe('density adoption scanner resource contract', () => {
  it('treats the candidate filter as a conservative over-approximation', () => {
    expect(sourceMayContainDensityFindings("const PAGE_PAD = 'p-4';")).toBe(true);
    expect(sourceMayContainDensityFindings('const pad = `p-${size}`;')).toBe(true);
    expect(sourceMayContainDensityFindings('<div data-density="compact" className="density-gap-stack" />')).toBe(true);
    expect(sourceMayContainDensityFindings("style={{ padding: '16px', gap: 12 }}")).toBe(true);
    expect(sourceMayContainDensityFindings('const box = { paddingTop: 8, rowGap: 4 };')).toBe(true);
    expect(sourceMayContainDensityFindings('export function skipHelp(mapItems: Item[]) { return mapItems; }')).toBe(false);
    expect(sourceMayContainDensityFindings('export const n = 1;\nexport const label = "ok";\n')).toBe(false);

    resetDensityScanAccounting();
    const empty = 'export const n = 1;\n'.repeat(4_000);
    expect(sourceMayContainDensityFindings(empty)).toBe(false);
    expect(scanDensityAdoption('../../utils/NoDensityCandidates.ts', empty)).toEqual([]);
    expect(getDensityScanStats()).toEqual({
      cacheHits: 0,
      skippedWithoutParse: 1,
      parsedFiles: 0,
    });

    const computed = 'const pad = `p-${size}`;';
    expect(scanDensityAdoption('../../pages/ComputedPrefixOnly.ts', computed)).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: 'computed-spacing', token: 'computed:p-' }),
      ]),
    );
    expect(getDensityScanStats().parsedFiles).toBe(1);
  });
});
