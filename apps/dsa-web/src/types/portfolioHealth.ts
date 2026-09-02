// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations } from './api.generated';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiBand = components['schemas']['PortfolioHealthBand'];
type OpenApiDataQuality = components['schemas']['PortfolioHealthDataQuality'];
type OpenApiDimension = components['schemas']['PortfolioHealthDimension'];
type OpenApiDimensions = components['schemas']['PortfolioHealthDimensions'];
type OpenApiEffectiveWeights = components['schemas']['PortfolioHealthEffectiveWeights'];
type OpenApiInputs = components['schemas']['PortfolioHealthInputs'];
type OpenApiInsight = components['schemas']['PortfolioHealthInsight'];
type OpenApiProvenance = components['schemas']['PortfolioHealthProvenance'];
type OpenApiConfig = components['schemas']['PortfolioHealthResolvedConfig'];
type OpenApiResponse = components['schemas']['PortfolioHealthResponse'];
type OpenApiWeights = components['schemas']['PortfolioHealthWeights'];
type OpenApiGet200 =
  operations['getPortfolioHealth']['responses']['200']['content']['application/json'];
type OpenApiRefresh200 =
  operations['refreshPortfolioHealth']['responses']['200']['content']['application/json'];
type OpenApiGetOp = operations['getPortfolioHealth'];
type OpenApiRefreshOp = operations['refreshPortfolioHealth'];
type OpenApiGetQuery = NonNullable<operations['getPortfolioHealth']['parameters']['query']>;
type OpenApiRefreshQuery = NonNullable<operations['refreshPortfolioHealth']['parameters']['query']>;

type _Assert<T extends true> = T;
type _Get200IsResponse = _Assert<OpenApiGet200 extends OpenApiResponse ? true : false>;
type _ResponseIsGet200 = _Assert<OpenApiResponse extends OpenApiGet200 ? true : false>;
type _Refresh200IsResponse = _Assert<OpenApiRefresh200 extends OpenApiResponse ? true : false>;
type _ResponseIsRefresh200 = _Assert<OpenApiResponse extends OpenApiRefresh200 ? true : false>;
type _GetOpHasNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _RefreshOpHasNeverRequestBody = _Assert<OpenApiRefreshOp extends { requestBody?: never } ? true : false>;
type _GetQueryHasAccountIdSnake = _Assert<'account_id' extends keyof OpenApiGetQuery ? true : false>;
type _GetQueryLacksPersist = _Assert<'persist' extends keyof OpenApiGetQuery ? false : true>;
type _RefreshQueryHasPersist = _Assert<'persist' extends keyof OpenApiRefreshQuery ? true : false>;
type _GetQueryAllowsNullAccount = _Assert<null extends OpenApiGetQuery['account_id'] ? true : false>;

type _OpenApiAnchors = [
  _Get200IsResponse,
  _ResponseIsGet200,
  _Refresh200IsResponse,
  _ResponseIsRefresh200,
  _GetOpHasNeverRequestBody,
  _RefreshOpHasNeverRequestBody,
  _GetQueryHasAccountIdSnake,
  _GetQueryLacksPersist,
  _RefreshQueryHasPersist,
  _GetQueryAllowsNullAccount,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type PortfolioHealthBand = OpenApiBand['name'];
export type PortfolioHealthStatus = OpenApiResponse['status'];
export type PortfolioHealthDimensionName = NonNullable<OpenApiResponse['unavailable_dimensions']>[number];
export type PortfolioHealthDimensionKey = keyof CamelizeKeys<OpenApiDimensions>;

export type PortfolioHealthDimension = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiDimension>, {
  formula?: string | null;
  input?: Record<string, number>;
  reason?: string | null;
  score?: number | null;
  status: OpenApiDimension['status'];
  statusMessage?: string | null;
}>>;

export type PortfolioHealthInsight = Override<CamelizeKeys<OpenApiInsight>, {
  code: string;
  message: string;
  metric?: string | null;
  severity: OpenApiInsight['severity'];
  source: OpenApiInsight['source'];
  symbol?: string | null;
  threshold?: number | null;
  value?: number | null;
}>;

type PortfolioHealthBandSpec = Override<CamelizeKeys<OpenApiBand>, {
  maxExclusive: number;
  minInclusive: number;
  name: PortfolioHealthBand;
}>;

type PortfolioHealthDataQuality = Override<CamelizeKeys<OpenApiDataQuality>, {
  fxStale: boolean;
  limitations: string[];
  missingPriceSymbols: string[];
  partialReasons: string[];
  riskMetricsStatus?: string | null;
  snapshotDataQuality?: string | null;
  status: OpenApiDataQuality['status'];
}>;

type PortfolioHealthInputs = Override<CamelizeKeys<OpenApiInputs>, {
  cashPct?: number | null;
  diversificationScore?: number | null;
  topWeightPct?: number | null;
  totalCash: number;
  totalEquity: number;
  totalMarketValue: number;
  unrealizedPnlPct?: number | null;
  varPct?: number | null;
}>;

type PortfolioHealthProvenance = Override<CamelizeKeys<OpenApiProvenance>, {
  calculatedAt: string;
  configHash: string;
  fxProvenance?: Record<string, unknown>;
  priceProvenance?: Record<string, unknown>;
  riskHash: string;
  riskHistory?: Record<string, unknown>;
  snapshotHash: string;
}>;

type PortfolioHealthDimensions = Override<
  CamelizeKeys<OpenApiDimensions>,
  Record<PortfolioHealthDimensionKey, PortfolioHealthDimension>
>;

type PortfolioHealthWeights = Override<CamelizeKeys<OpenApiWeights>, Record<PortfolioHealthDimensionKey, number>>;

type PortfolioHealthEffectiveWeights = Override<
  CamelizeKeys<OpenApiEffectiveWeights>,
  Record<PortfolioHealthDimensionKey, number | null | undefined>
>;

type PortfolioHealthResolvedConfig = Override<CamelizeKeys<OpenApiConfig>, {
  cashHighAlertPct: number;
  cashLowAlertPct: number;
  concentrationAlertPct: number;
  diversificationAlert: number;
  pnlLossAlertPct: number;
  source: OpenApiConfig['source'];
  varAlertPct: number;
  weights: PortfolioHealthWeights;
}>;

export type PortfolioHealthResponse = Override<CamelizeKeys<OpenApiResponse>, {
  accountId?: number | null;
  asOf: string;
  band?: PortfolioHealthBand | null;
  bands: PortfolioHealthBandSpec[];
  comparable: boolean;
  config: PortfolioHealthResolvedConfig;
  costMethod: OpenApiResponse['cost_method'];
  coverageRatio: number;
  currency: string;
  dataQuality: PortfolioHealthDataQuality;
  dimensions: PortfolioHealthDimensions;
  disclaimer?: string;
  effectiveWeights: PortfolioHealthEffectiveWeights;
  formulaVersion: 'portfolio_health_v2';
  inputs: PortfolioHealthInputs;
  insights: PortfolioHealthInsight[];
  llmCanModifyScore: false;
  partialScore?: number | null;
  persisted: boolean;
  provenance: PortfolioHealthProvenance;
  score?: number | null;
  scoreSource: 'rules';
  status: PortfolioHealthStatus;
  statusMessage?: string | null;
  unavailableDimensions: PortfolioHealthDimensionName[];
  weights: PortfolioHealthWeights;
}>;

export type PortfolioHealthSummary = Pick<PortfolioHealthResponse,
  | 'accountId'
  | 'asOf'
  | 'band'
  | 'comparable'
  | 'costMethod'
  | 'coverageRatio'
  | 'currency'
  | 'score'
  | 'partialScore'
  | 'status'
  | 'statusMessage'
  | 'disclaimer'
>;

export type PortfolioHealthQuery = {
  accountId?: number;
  asOf?: string;
  costMethod?: OpenApiResponse['cost_method'];
};

export type PortfolioHealthRefreshQuery = PortfolioHealthQuery & {
  persist?: boolean;
};
