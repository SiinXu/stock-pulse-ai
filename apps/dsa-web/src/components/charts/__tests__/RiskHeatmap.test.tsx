// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { MAX_RISK_HEATMAP_COLUMNS, MAX_RISK_HEATMAP_ROWS } from '../chartUtils';
import { RiskHeatmap, type RiskHeatmapCell } from '../RiskHeatmap';

const sample: RiskHeatmapCell[] = [
  { rowId: '600519', rowLabel: 'Moutai', columnId: 'vol', columnLabel: 'Volatility', score: 22 },
  { rowId: '600519', rowLabel: 'Moutai', columnId: 'liq', columnLabel: 'Liquidity', score: 55 },
  { rowId: 'AAPL', rowLabel: 'Apple', columnId: 'vol', columnLabel: 'Volatility', score: 81 },
  { rowId: 'AAPL', rowLabel: 'Apple', columnId: 'liq', columnLabel: 'Liquidity', score: Number.NaN },
];
function renderH(cells: RiskHeatmapCell[] | null) {
  window.localStorage.setItem('dsa.uiLanguage', 'en');
  return render(<UiLanguageProvider><RiskHeatmap cells={cells} /></UiLanguageProvider>);
}
describe('RiskHeatmap', () => {
  it('empty', () => {
    renderH([]);
    expect(screen.getByTestId('risk-heatmap-empty')).toBeInTheDocument();
  });
  it('grid with labels', () => {
    renderH(sample);
    expect(screen.getByRole('table', { name: 'Risk heatmap, 2 rows × 2 columns' })).toBeInTheDocument();
    expect(screen.getByTestId('risk-heatmap-cell-600519-vol')).toHaveAttribute('data-risk-level', 'low');
    expect(screen.getByTestId('risk-heatmap-cell-600519-vol')).toHaveTextContent('22');
    expect(screen.getByTestId('risk-heatmap-cell-600519-vol')).not.toHaveAttribute('title');
    expect(screen.getByTestId('risk-heatmap-cell-AAPL-vol')).toHaveAttribute('data-risk-level', 'critical');
    expect(screen.getByTestId('risk-heatmap-cell-AAPL-liq')).toHaveAttribute('data-risk-level', 'missing');
  });
  it('Infinity missing', () => {
    renderH([{ rowId: 'x', rowLabel: 'X', columnId: 'y', columnLabel: 'Y', score: Number.POSITIVE_INFINITY }]);
    expect(screen.getByTestId('risk-heatmap-cell-x-y')).toHaveAttribute('data-risk-level', 'missing');
  });
  it('keeps sparse and out-of-range scores missing instead of clamping them', () => {
    renderH([
      { rowId: 'x', rowLabel: 'X', columnId: 'a', columnLabel: 'A', score: -1 },
      { rowId: 'x', rowLabel: 'X', columnId: 'b', columnLabel: 'B', score: 101 },
      { rowId: 'y', rowLabel: 'Y', columnId: 'a', columnLabel: 'A', score: 0 },
    ]);
    expect(screen.getByTestId('risk-heatmap-cell-x-a')).toHaveAttribute('data-risk-level', 'missing');
    expect(screen.getByTestId('risk-heatmap-cell-x-b')).toHaveAttribute('data-risk-level', 'missing');
    expect(screen.getByTestId('risk-heatmap-cell-y-b')).toHaveAttribute('data-risk-level', 'missing');
    expect(screen.getByTestId('risk-heatmap-cell-y-a')).toHaveAttribute('data-risk-level', 'low');
  });
  it('uses the last duplicate coordinate deterministically', () => {
    renderH([
      { rowId: 'x', rowLabel: 'X', columnId: 'y', columnLabel: 'Y', score: 10 },
      { rowId: 'x', rowLabel: 'Changed label', columnId: 'y', columnLabel: 'Changed column', score: 90 },
    ]);
    expect(screen.getByTestId('risk-heatmap-cell-x-y')).toHaveTextContent('90');
    expect(screen.getByTestId('risk-heatmap-cell-x-y')).toHaveAttribute('data-risk-level', 'critical');
    expect(screen.getByRole('rowheader', { name: 'X' })).toBeInTheDocument();
  });
  it('keeps delimiter-like row and column ids distinct', () => {
    renderH([
      { rowId: 'a::b', rowLabel: 'First', columnId: 'c', columnLabel: 'C', score: 10 },
      { rowId: 'a', rowLabel: 'Second', columnId: 'b::c', columnLabel: 'BC', score: 90 },
    ]);
    expect(screen.getByTestId('risk-heatmap-cell-a::b-c')).toHaveTextContent('10');
    expect(screen.getByTestId('risk-heatmap-cell-a-b::c')).toHaveTextContent('90');
  });
  it('bounds rendered dimensions', () => {
    const cells = Array.from({ length: MAX_RISK_HEATMAP_ROWS + 5 }, (_, row) => (
      Array.from({ length: MAX_RISK_HEATMAP_COLUMNS + 3 }, (_, column) => ({
        rowId: `r${row}`,
        rowLabel: `Row ${row}`,
        columnId: `c${column}`,
        columnLabel: `Column ${column}`,
        score: 50,
      }))
    )).flat();
    renderH(cells);
    expect(screen.getAllByRole('row')).toHaveLength(MAX_RISK_HEATMAP_ROWS + 1);
    expect(screen.getAllByRole('columnheader')).toHaveLength(MAX_RISK_HEATMAP_COLUMNS + 1);
  });
});
