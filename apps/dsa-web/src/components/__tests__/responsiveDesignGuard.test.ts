// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/// <reference types="vite/client" />
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import tailwindConfigSource from '../../../tailwind.config.js?raw';
import marketReviewSource from '../report/MarketReviewReportView.tsx?raw';
import reportOverviewSource from '../report/ReportOverview.tsx?raw';

const productionSources = import.meta.glob('../../**/*.{css,tsx}', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>;
const indexCssSource = fs.readFileSync('src/index.css', 'utf8');

const RAW_STATIC_VIEWPORT_HEIGHT = /(^|[^a-zA-Z0-9])100vh([^a-zA-Z0-9]|$)/;

function isProductionSource(filename: string): boolean {
  return !filename.includes('/__tests__/')
    && !/\.(?:test|spec|stories|generated)\.tsx$/.test(filename);
}

describe('responsive design guard', () => {
  it('detects static viewport units without rejecting dvh', () => {
    expect('min-height: 100vh').toMatch(RAW_STATIC_VIEWPORT_HEIGHT);
    expect('height: calc(100vh - 2rem)').toMatch(RAW_STATIC_VIEWPORT_HEIGHT);
    expect('min-height: 100dvh').not.toMatch(RAW_STATIC_VIEWPORT_HEIGHT);
  });

  it('keeps raw 100vh out of production CSS and TSX', () => {
    const failures = Object.entries(productionSources)
      .filter(([filename]) => isProductionSource(filename))
      .filter(([, source]) => RAW_STATIC_VIEWPORT_HEIGHT.test(source))
      .map(([filename]) => filename);

    expect(failures).toEqual([]);
  });

  it('defines the report H2 token as exactly 28px and uses it for both headings', () => {
    const headingToken = tailwindConfigSource.match(
      /['"]heading-2['"]:\s*\[\s*['"]([^'"]+)['"]\s*,\s*\{\s*lineHeight:\s*['"]([^'"]+)['"]\s*\}\s*\]/,
    );

    expect(headingToken?.[1]).toBe('1.75rem');
    expect(Number.parseFloat(headingToken?.[1] ?? '') * 16).toBe(28);
    expect(headingToken?.[2]).toBe('1.2');
    expect(reportOverviewSource).toContain('text-heading-2');
    expect(marketReviewSource).toContain('text-heading-2');
    expect(reportOverviewSource).not.toContain('text-3xl');
    expect(marketReviewSource).not.toContain('sm:text-3xl');
  });

  it('keeps sidebar navigation targets at least 44px in every theme', () => {
    expect(indexCssSource.match(/--nav-item-height:\s*2\.75rem;/g) ?? []).toHaveLength(2);
    expect(indexCssSource).not.toContain('--nav-item-height: 2.25rem;');
  });

  it('keeps quick-question buttons at least 44px tall', () => {
    const quickQuestionRule = indexCssSource.match(/\.quick-question-btn\s*\{[^}]+\}/)?.[0];
    expect(quickQuestionRule).toContain('min-height: 2.75rem;');
  });

  it('expands compact control hit targets only for coarse pointers', () => {
    const coarsePointerStart = indexCssSource.indexOf('@media (pointer: coarse)');
    const hitTargetRule = indexCssSource
      .slice(coarsePointerStart)
      .match(/\.control-hit-target::after\s*\{[^}]+\}/)?.[0];

    expect(coarsePointerStart).toBeGreaterThanOrEqual(0);
    expect(hitTargetRule).toContain('min-width: 2.75rem;');
    expect(hitTargetRule).toContain('min-height: 2.75rem;');
  });

  it('gives text-control frames a 44px coarse-pointer target height', () => {
    const coarsePointerStart = indexCssSource.indexOf('@media (pointer: coarse)');
    const inputTargetRule = indexCssSource
      .slice(coarsePointerStart)
      .match(/\.control-input-target\s*\{[^}]+\}/)?.[0];

    expect(inputTargetRule).toContain('min-height: 2.75rem;');
  });
});
