// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export type PortfolioHealthBand = 'healthy' | 'fair' | 'caution' | 'poor';
export type PortfolioHealthStatus = 'ok' | 'partial' | 'empty_portfolio' | 'unavailable';

/** Compact Home-widget projection of GET /api/v1/portfolio/health. */
export type PortfolioHealthSummary = {
  accountId?: number | null;
  asOf: string;
  band?: PortfolioHealthBand | null;
  comparable: boolean;
  costMethod: 'fifo' | 'avg';
  coverageRatio: number;
  currency: string;
  score?: number | null;
  partialScore?: number | null;
  status: PortfolioHealthStatus;
  statusMessage?: string | null;
  disclaimer?: string;
};
