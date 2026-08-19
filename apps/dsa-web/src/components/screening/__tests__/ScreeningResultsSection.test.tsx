// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { AlphaSiftCandidate } from '../../../api/alphasift';
import { applyPriceDirection } from '../../theme/themeRuntime';
import { SCREENING_TEXT } from '../../../locales/screening';
import { ScreeningResultsSection } from '../ScreeningResultsSection';

const text = SCREENING_TEXT.en;

function candidate(overrides: Partial<AlphaSiftCandidate> = {}): AlphaSiftCandidate {
  return {
    rank: 1,
    code: '600519',
    name: 'Demo Stock',
    industry: 'Consumer',
    price: 1600,
    changePct: 1.2,
    score: 88.5,
    llmScore: 0.82,
    riskLevel: 'low',
    reason: 'Candidate summary.',
    raw: {},
    ...overrides,
  };
}

function renderResults(candidates: AlphaSiftCandidate[]) {
  return render(
    <ScreeningResultsSection
      text={text}
      language="en"
      candidates={candidates}
      expandedCode={null}
      llmDegraded={false}
      onExpandedCodeChange={() => undefined}
    />,
  );
}

describe('ScreeningResultsSection price colors', () => {
  afterEach(() => {
    cleanup();
    applyPriceDirection('cn', { persist: false });
  });

  it('paints finite change percents with price tokens for both preferences', () => {
    applyPriceDirection('cn', { persist: false });
    renderResults([candidate({ changePct: 1.2 }), candidate({ rank: 2, code: 'AAPL', changePct: -0.5 })]);
    const up = screen.getByText('+1.20%');
    const down = screen.getByText('-0.50%');
    expect(up).toHaveStyle({ color: 'var(--price-red)' });
    expect(down).toHaveStyle({ color: 'var(--price-green)' });
    expect(up).not.toHaveClass('text-success');
    expect(down).not.toHaveClass('text-danger');
    cleanup();

    applyPriceDirection('us', { persist: false });
    renderResults([candidate({ changePct: 1.2 }), candidate({ rank: 2, code: 'AAPL', changePct: -0.5 })]);
    expect(screen.getByText('+1.20%')).toHaveStyle({ color: 'var(--price-green)' });
    expect(screen.getByText('-0.50%')).toHaveStyle({ color: 'var(--price-red)' });
  });

  it('leaves zero and missing change percents unpainted', () => {
    renderResults([
      candidate({ changePct: 0 }),
      candidate({ rank: 2, code: '000001', changePct: null }),
    ]);
    expect(screen.getByText('0.00%')).not.toHaveStyle({ color: 'var(--price-red)' });
    expect(screen.getByText('0.00%')).not.toHaveStyle({ color: 'var(--price-green)' });
    expect(screen.getByText('-%')).not.toHaveStyle({ color: 'var(--price-red)' });
    expect(screen.getByText('-%')).not.toHaveStyle({ color: 'var(--price-green)' });
  });
});
