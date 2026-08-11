// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// CamelCase client types for GET /api/v1/portfolio/risk-metrics (OpenAPI getPortfolioRiskMetrics).

import type { components, operations } from './api.generated';
import type { PortfolioCostMethod } from './portfolio';

type OpenApiRiskMetrics = components['schemas']['PortfolioRiskMetricsResponse'];
type OpenApiAssumptions = components['schemas']['PortfolioRiskAssumptions'];
type OpenApiVaR = components['schemas']['PortfolioHistoricalVaRBlock'];
type OpenApiCorrelation = components['schemas']['PortfolioCorrelationBlock'];
type OpenApiConcentration = components['schemas']['PortfolioConcentrationBlock'];
type OpenApiHistory = components['schemas']['PortfolioRiskHistoryMeta'];
type OpenApiWeight = components['schemas']['PortfolioRiskWeightItem'];
type OpenApiRiskMetricsQuery = NonNullable<
  operations['getPortfolioRiskMetrics']['parameters']['query']
>;

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

export type PortfolioRiskMetricsStatus =
  | 'ok'
  | 'empty_portfolio'
  | 'insufficient_history'
  | 'partial';

export type PortfolioVaRStatus =
  | 'ok'
  | 'insufficient_history'
  | 'unavailable';

export type PortfolioCorrelationStatus = PortfolioVaRStatus;

export type PortfolioConcentrationStatus = 'ok' | 'empty_portfolio';

export type PortfolioRiskBlockStatus =
  | PortfolioVaRStatus
  | PortfolioConcentrationStatus;

export type PortfolioRiskWeightItem = CamelizeKeys<OpenApiWeight>;

export type PortfolioRiskAssumptions = CamelizeKeys<OpenApiAssumptions>;

export type PortfolioHistoricalVaRBlock = Override<CamelizeKeys<OpenApiVaR>, {
  status: PortfolioVaRStatus;
}>;

export type PortfolioCorrelationBlock = Override<CamelizeKeys<OpenApiCorrelation>, {
  status: PortfolioCorrelationStatus;
  symbols: string[];
  matrix: Array<Array<number | null>>;
}>;

export type PortfolioConcentrationBlock = Override<CamelizeKeys<OpenApiConcentration>, {
  status: PortfolioConcentrationStatus;
  weights: PortfolioRiskWeightItem[];
}>;

export type PortfolioRiskHistoryMeta = Override<CamelizeKeys<OpenApiHistory>, {
  priceSeriesSymbols: string[];
}>;

export type PortfolioRiskMetricsResponse = Override<CamelizeKeys<OpenApiRiskMetrics>, {
  costMethod: PortfolioCostMethod;
  status: PortfolioRiskMetricsStatus;
  assumptions: PortfolioRiskAssumptions;
  var: PortfolioHistoricalVaRBlock;
  correlation: PortfolioCorrelationBlock;
  concentration: PortfolioConcentrationBlock;
  history?: PortfolioRiskHistoryMeta | null;
}>;

export type PortfolioRiskMetricsQuery = Override<CamelizeKeys<OpenApiRiskMetricsQuery>, {
  accountId?: number;
  asOf?: string;
  costMethod?: PortfolioCostMethod;
}>;
