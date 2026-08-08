// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
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
    expect(screen.getByTestId('risk-heatmap-cell-600519-vol')).toHaveAttribute('data-risk-level', 'low');
    expect(screen.getByTestId('risk-heatmap-cell-600519-vol')).toHaveTextContent('22');
    expect(screen.getByTestId('risk-heatmap-cell-AAPL-vol')).toHaveAttribute('data-risk-level', 'critical');
    expect(screen.getByTestId('risk-heatmap-cell-AAPL-liq')).toHaveAttribute('data-risk-level', 'missing');
  });
  it('Infinity missing', () => {
    renderH([{ rowId: 'x', rowLabel: 'X', columnId: 'y', columnLabel: 'Y', score: Number.POSITIVE_INFINITY }]);
    expect(screen.getByTestId('risk-heatmap-cell-x-y')).toHaveAttribute('data-risk-level', 'missing');
  });
});
