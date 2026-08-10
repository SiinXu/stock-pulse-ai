// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { RiskHeatmapCell } from '../charts';
import { normalizeRiskScore } from '../charts/chartUtils';
import type { PortfolioRiskResponse } from '../../types/portfolio';

export type PortfolioRiskHeatmapLabels = {
  portfolioRow: string;
  weight: string;
  stopLoss: string;
  drawdown: string;
};

const MAX_POSITION_ROWS = 12;

/**
 * Project the existing portfolio risk API payload into RiskHeatmap cells.
 *
 * Scores are raw finite risk units already expressed on a 0–100 scale by the
 * backend (weight %, unrealized loss %, drawdown %). Non-finite or out-of-range
 * values become null so the heatmap shows Missing instead of painting bad data.
 */
export function buildPortfolioRiskHeatmapCells(
  risk: PortfolioRiskResponse | null | undefined,
  labels: PortfolioRiskHeatmapLabels,
): RiskHeatmapCell[] {
  if (!risk) return [];

  const cells: RiskHeatmapCell[] = [];
  const portfolioRowId = 'portfolio';
  const portfolioRowLabel = labels.portfolioRow.trim() || portfolioRowId;

  const currentDrawdown = normalizeRiskScore(risk.drawdown?.currentDrawdownPct);
  const maxDrawdown = normalizeRiskScore(risk.drawdown?.maxDrawdownPct);
  const drawdownScore = currentDrawdown ?? maxDrawdown;
  if (drawdownScore !== null) {
    cells.push({
      rowId: portfolioRowId,
      rowLabel: portfolioRowLabel,
      columnId: 'drawdown',
      columnLabel: labels.drawdown,
      score: drawdownScore,
    });
  }

  const topWeight = normalizeRiskScore(risk.concentration?.topWeightPct);
  if (topWeight !== null) {
    cells.push({
      rowId: portfolioRowId,
      rowLabel: portfolioRowLabel,
      columnId: 'weight',
      columnLabel: labels.weight,
      score: topWeight,
    });
  }

  const positions = risk.concentration?.topPositions ?? [];
  for (const position of positions.slice(0, MAX_POSITION_ROWS)) {
    const symbol = typeof position.symbol === 'string' ? position.symbol.trim() : '';
    if (!symbol) continue;
    cells.push({
      rowId: `pos:${symbol}`,
      rowLabel: symbol,
      columnId: 'weight',
      columnLabel: labels.weight,
      score: normalizeRiskScore(position.weightPct),
    });
  }

  const stopItems = risk.stopLoss?.items ?? [];
  for (const item of stopItems.slice(0, MAX_POSITION_ROWS)) {
    const symbol = typeof item.symbol === 'string' ? item.symbol.trim() : '';
    if (!symbol) continue;
    cells.push({
      rowId: `pos:${symbol}`,
      rowLabel: symbol,
      columnId: 'stopLoss',
      columnLabel: labels.stopLoss,
      score: normalizeRiskScore(item.lossPct),
    });
  }

  return cells;
}
