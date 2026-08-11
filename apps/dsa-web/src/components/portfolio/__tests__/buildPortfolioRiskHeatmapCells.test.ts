// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import type { PortfolioRiskResponse } from '../../../types/portfolio';
import { buildPortfolioRiskHeatmapCells } from '../buildPortfolioRiskHeatmapCells';

const LABELS = {
  portfolioRow: 'Portfolio',
  weight: 'Weight',
  stopLoss: 'Stop-loss',
  drawdown: 'Drawdown',
};

function makeRisk(overrides: Partial<PortfolioRiskResponse> = {}): PortfolioRiskResponse {
  return {
    asOf: '2026-08-10',
    costMethod: 'fifo',
    currency: 'CNY',
    thresholds: {},
    concentration: {
      totalMarketValue: 100,
      topWeightPct: 40,
      alert: true,
      topPositions: [
        { symbol: '600519', marketValueBase: 40, weightPct: 40, isAlert: true },
        { symbol: '000001', marketValueBase: 20, weightPct: 20, isAlert: false },
      ],
    },
    sectorConcentration: {
      totalMarketValue: 100,
      topWeightPct: 40,
      alert: false,
      topSectors: [],
      coverage: {},
      errors: [],
    },
    drawdown: {
      seriesPoints: 10,
      maxDrawdownPct: 18,
      currentDrawdownPct: 12,
      alert: false,
      fxStale: false,
    },
    stopLoss: {
      nearAlert: true,
      triggeredCount: 1,
      nearCount: 1,
      items: [
        {
          accountId: 1,
          symbol: '600519',
          avgCost: 100,
          lastPrice: 85,
          lossPct: 15,
          nearThresholdPct: 10,
          isTriggered: true,
        },
      ],
    },
    ...overrides,
  };
}

describe('buildPortfolioRiskHeatmapCells', () => {
  it('returns empty cells when risk is missing', () => {
    expect(buildPortfolioRiskHeatmapCells(null, LABELS)).toEqual([]);
    expect(buildPortfolioRiskHeatmapCells(undefined, LABELS)).toEqual([]);
  });

  it('maps weight, stop-loss, and drawdown finite scores', () => {
    const cells = buildPortfolioRiskHeatmapCells(makeRisk(), LABELS);
    expect(cells).toEqual(expect.arrayContaining([
      expect.objectContaining({ rowId: 'portfolio', columnId: 'drawdown', score: 12 }),
      expect.objectContaining({ rowId: 'portfolio', columnId: 'weight', score: 40 }),
      expect.objectContaining({ rowId: 'pos:600519', columnId: 'weight', score: 40 }),
      expect.objectContaining({ rowId: 'pos:600519', columnId: 'stopLoss', score: 15 }),
      expect.objectContaining({ rowId: 'pos:000001', columnId: 'weight', score: 20 }),
    ]));
  });

  it('rejects non-finite and out-of-range scores instead of inventing values', () => {
    const cells = buildPortfolioRiskHeatmapCells(makeRisk({
      drawdown: {
        seriesPoints: 1,
        maxDrawdownPct: Number.POSITIVE_INFINITY,
        currentDrawdownPct: Number.NaN,
        alert: false,
        fxStale: false,
      },
      concentration: {
        totalMarketValue: 100,
        topWeightPct: 150,
        alert: true,
        topPositions: [
          { symbol: 'BAD', marketValueBase: 1, weightPct: Number.NaN, isAlert: false },
          { symbol: 'OK', marketValueBase: 1, weightPct: 12, isAlert: false },
        ],
      },
      stopLoss: {
        nearAlert: false,
        triggeredCount: 0,
        nearCount: 0,
        items: [
          {
            accountId: 1,
            symbol: 'BAD',
            avgCost: 1,
            lastPrice: 1,
            lossPct: -5,
            nearThresholdPct: 1,
            isTriggered: false,
          },
        ],
      },
    }), LABELS);

    expect(cells.find((cell) => cell.columnId === 'drawdown')).toBeUndefined();
    expect(cells.find((cell) => cell.rowId === 'portfolio' && cell.columnId === 'weight')).toBeUndefined();
    expect(cells.find((cell) => cell.rowId === 'pos:BAD' && cell.columnId === 'weight')?.score).toBeNull();
    expect(cells.find((cell) => cell.rowId === 'pos:BAD' && cell.columnId === 'stopLoss')?.score).toBeNull();
    expect(cells.find((cell) => cell.rowId === 'pos:OK' && cell.columnId === 'weight')?.score).toBe(12);
  });
});
