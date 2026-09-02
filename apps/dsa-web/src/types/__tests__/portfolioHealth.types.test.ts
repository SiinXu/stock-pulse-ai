// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations } from '../api.generated';
import * as PortfolioHealth from '../portfolioHealth';
import type {
  PortfolioHealthBand,
  PortfolioHealthDimension,
  PortfolioHealthDimensionKey,
  PortfolioHealthDimensionName,
  PortfolioHealthInsight,
  PortfolioHealthQuery,
  PortfolioHealthRefreshQuery,
  PortfolioHealthResponse,
  PortfolioHealthStatus,
  PortfolioHealthSummary,
} from '../portfolioHealth';

type OpenApiBand = components['schemas']['PortfolioHealthBand'];
type OpenApiDataQuality = components['schemas']['PortfolioHealthDataQuality'];
type OpenApiDimension = components['schemas']['PortfolioHealthDimension'];
type OpenApiDimensions = components['schemas']['PortfolioHealthDimensions'];
type OpenApiEffectiveWeights = components['schemas']['PortfolioHealthEffectiveWeights'];
type OpenApiInsight = components['schemas']['PortfolioHealthInsight'];
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

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type _Assert<T extends true> = T;
type IsOptional<T, K extends keyof T> = Partial<Pick<T, K>> extends Pick<T, K> ? true : false;

type _Get200IsResponse = _Assert<OpenApiGet200 extends OpenApiResponse ? true : false>;
type _ResponseIsGet200 = _Assert<OpenApiResponse extends OpenApiGet200 ? true : false>;
type _Refresh200IsResponse = _Assert<OpenApiRefresh200 extends OpenApiResponse ? true : false>;
type _ResponseIsRefresh200 = _Assert<OpenApiResponse extends OpenApiRefresh200 ? true : false>;
type _GetOpHasNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _RefreshOpHasNeverRequestBody = _Assert<OpenApiRefreshOp extends { requestBody?: never } ? true : false>;

type _UiHasAsOf = _Assert<'asOf' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasAccountId = _Assert<'accountId' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasCostMethod = _Assert<'costMethod' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasCoverageRatio = _Assert<'coverageRatio' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasStatusMessage = _Assert<'statusMessage' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasFormulaVersion = _Assert<'formulaVersion' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasPartialScore = _Assert<'partialScore' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasScoreSource = _Assert<'scoreSource' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasUnavailableDimensions = _Assert<'unavailableDimensions' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasDataQuality = _Assert<'dataQuality' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasEffectiveWeights = _Assert<'effectiveWeights' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasLlmCanModifyScore = _Assert<'llmCanModifyScore' extends keyof PortfolioHealthResponse ? true : false>;
type _UiHasMaxExclusive = _Assert<'maxExclusive' extends keyof PortfolioHealthResponse['bands'][number] ? true : false>;
type _UiHasMinInclusive = _Assert<'minInclusive' extends keyof PortfolioHealthResponse['bands'][number] ? true : false>;
type _UiHasFxStale = _Assert<'fxStale' extends keyof PortfolioHealthResponse['dataQuality'] ? true : false>;
type _UiHasMissingPriceSymbols = _Assert<'missingPriceSymbols' extends keyof PortfolioHealthResponse['dataQuality'] ? true : false>;
type _UiHasPartialReasons = _Assert<'partialReasons' extends keyof PortfolioHealthResponse['dataQuality'] ? true : false>;
type _UiHasRiskMetricsStatus = _Assert<'riskMetricsStatus' extends keyof PortfolioHealthResponse['dataQuality'] ? true : false>;
type _UiHasSnapshotDataQuality = _Assert<'snapshotDataQuality' extends keyof PortfolioHealthResponse['dataQuality'] ? true : false>;
type _UiHasRiskExposureKey = _Assert<'riskExposure' extends keyof PortfolioHealthResponse['dimensions'] ? true : false>;
type _UiHasCashRatioKey = _Assert<'cashRatio' extends keyof PortfolioHealthResponse['weights'] ? true : false>;
type _UiHasCalculatedAt = _Assert<'calculatedAt' extends keyof PortfolioHealthResponse['provenance'] ? true : false>;
type _UiHasConfigHash = _Assert<'configHash' extends keyof PortfolioHealthResponse['provenance'] ? true : false>;
type _UiHasCashHighAlertPct = _Assert<'cashHighAlertPct' extends keyof PortfolioHealthResponse['config'] ? true : false>;
type _UiDimensionHasStatusMessage = _Assert<'statusMessage' extends keyof PortfolioHealthDimension ? true : false>;

type _UiLacksAsOfSnake = _Assert<'as_of' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksAccountIdSnake = _Assert<'account_id' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksCostMethodSnake = _Assert<'cost_method' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksCoverageRatioSnake = _Assert<'coverage_ratio' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksStatusMessageSnake = _Assert<'status_message' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksFormulaVersionSnake = _Assert<'formula_version' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksPartialScoreSnake = _Assert<'partial_score' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksScoreSourceSnake = _Assert<'score_source' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksUnavailableSnake = _Assert<'unavailable_dimensions' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksDataQualitySnake = _Assert<'data_quality' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksEffectiveWeightsSnake = _Assert<'effective_weights' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksLlmSnake = _Assert<'llm_can_modify_score' extends keyof PortfolioHealthResponse ? false : true>;
type _UiLacksMaxExclusiveSnake = _Assert<'max_exclusive' extends keyof PortfolioHealthResponse['bands'][number] ? false : true>;
type _UiLacksFxStaleSnake = _Assert<'fx_stale' extends keyof PortfolioHealthResponse['dataQuality'] ? false : true>;
type _UiLacksMissingPriceSnake = _Assert<'missing_price_symbols' extends keyof PortfolioHealthResponse['dataQuality'] ? false : true>;
type _UiLacksPartialReasonsSnake = _Assert<'partial_reasons' extends keyof PortfolioHealthResponse['dataQuality'] ? false : true>;
type _UiLacksRiskExposureSnakeKey = _Assert<'risk_exposure' extends keyof PortfolioHealthResponse['dimensions'] ? false : true>;
type _UiLacksCashRatioSnakeKey = _Assert<'cash_ratio' extends keyof PortfolioHealthResponse['weights'] ? false : true>;
type _UiLacksCalculatedAtSnake = _Assert<'calculated_at' extends keyof PortfolioHealthResponse['provenance'] ? false : true>;
type _UiDimensionLacksStatusMessageSnake = _Assert<'status_message' extends keyof PortfolioHealthDimension ? false : true>;

type _GeneratedHasAsOfSnake = _Assert<'as_of' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasAccountIdSnake = _Assert<'account_id' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasCostMethodSnake = _Assert<'cost_method' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasCoverageRatioSnake = _Assert<'coverage_ratio' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasStatusMessageSnake = _Assert<'status_message' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasFormulaVersionSnake = _Assert<'formula_version' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasPartialScoreSnake = _Assert<'partial_score' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasScoreSourceSnake = _Assert<'score_source' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasUnavailableSnake = _Assert<'unavailable_dimensions' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasDataQualitySnake = _Assert<'data_quality' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasEffectiveWeightsSnake = _Assert<'effective_weights' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasLlmSnake = _Assert<'llm_can_modify_score' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasMaxExclusiveSnake = _Assert<'max_exclusive' extends keyof OpenApiBand ? true : false>;
type _GeneratedHasFxStaleSnake = _Assert<'fx_stale' extends keyof OpenApiDataQuality ? true : false>;
type _GeneratedHasMissingPriceSnake = _Assert<'missing_price_symbols' extends keyof OpenApiDataQuality ? true : false>;
type _GeneratedHasPartialReasonsSnake = _Assert<'partial_reasons' extends keyof OpenApiDataQuality ? true : false>;
type _GeneratedHasRiskExposureSnake = _Assert<'risk_exposure' extends keyof OpenApiDimensions ? true : false>;
type _GeneratedHasCashRatioSnake = _Assert<'cash_ratio' extends keyof OpenApiWeights ? true : false>;
type _GeneratedHasCalculatedAtSnake = _Assert<'calculated_at' extends keyof OpenApiResponse['provenance'] ? true : false>;
type _GeneratedDimensionHasStatusMessageSnake = _Assert<'status_message' extends keyof OpenApiDimension ? true : false>;
type _GeneratedInsightHasCode = _Assert<'code' extends keyof OpenApiInsight ? true : false>;
type _GeneratedInsightHasSeverity = _Assert<'severity' extends keyof OpenApiInsight ? true : false>;
type _GeneratedLacksAsOfCamel = _Assert<'asOf' extends keyof OpenApiResponse ? false : true>;
type _GeneratedLacksFormulaCamel = _Assert<'formulaVersion' extends keyof OpenApiResponse ? false : true>;
type _GeneratedLacksRiskExposureCamel = _Assert<'riskExposure' extends keyof OpenApiDimensions ? false : true>;

type _UiBandsRequired = _Assert<IsOptional<PortfolioHealthResponse, 'bands'> extends false ? true : false>;
type _UiInsightsRequired = _Assert<IsOptional<PortfolioHealthResponse, 'insights'> extends false ? true : false>;
type _UiUnavailableRequired = _Assert<
  IsOptional<PortfolioHealthResponse, 'unavailableDimensions'> extends false ? true : false
>;
type _UiDisclaimerOptional = _Assert<IsOptional<PortfolioHealthResponse, 'disclaimer'>>;
type _UiLimitationsRequired = _Assert<
  IsOptional<PortfolioHealthResponse['dataQuality'], 'limitations'> extends false ? true : false
>;
type _UiMissingPriceRequired = _Assert<
  IsOptional<PortfolioHealthResponse['dataQuality'], 'missingPriceSymbols'> extends false ? true : false
>;
type _UiPartialReasonsRequired = _Assert<
  IsOptional<PortfolioHealthResponse['dataQuality'], 'partialReasons'> extends false ? true : false
>;
type _UiEffectiveRiskRequired = _Assert<
  IsOptional<PortfolioHealthResponse['effectiveWeights'], 'riskExposure'> extends false ? true : false
>;
type _GeneratedBandsOptional = _Assert<IsOptional<OpenApiResponse, 'bands'>>;
type _GeneratedInsightsOptional = _Assert<IsOptional<OpenApiResponse, 'insights'>>;
type _GeneratedUnavailableOptional = _Assert<IsOptional<OpenApiResponse, 'unavailable_dimensions'>>;
type _GeneratedDisclaimerRequired = _Assert<IsOptional<OpenApiResponse, 'disclaimer'> extends false ? true : false>;
type _GeneratedLimitationsOptional = _Assert<IsOptional<OpenApiDataQuality, 'limitations'>>;
type _GeneratedMissingPriceOptional = _Assert<IsOptional<OpenApiDataQuality, 'missing_price_symbols'>>;
type _GeneratedPartialReasonsOptional = _Assert<IsOptional<OpenApiDataQuality, 'partial_reasons'>>;
type _GeneratedEffectiveRiskOptional = _Assert<IsOptional<OpenApiEffectiveWeights, 'risk_exposure'>>;
type _NaiveCamelBandsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiResponse>, 'bands'>>;
type _NaiveCamelDisclaimerRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiResponse>, 'disclaimer'> extends false ? true : false
>;

type _OmitUiBands = _Assert<Omit<PortfolioHealthResponse, 'bands'> extends PortfolioHealthResponse ? false : true>;
type _OmitUiInsights = _Assert<Omit<PortfolioHealthResponse, 'insights'> extends PortfolioHealthResponse ? false : true>;
type _OmitUiUnavailable = _Assert<
  Omit<PortfolioHealthResponse, 'unavailableDimensions'> extends PortfolioHealthResponse ? false : true
>;
type _OmitUiDisclaimer = _Assert<
  Omit<PortfolioHealthResponse, 'disclaimer'> extends PortfolioHealthResponse ? true : false
>;
type _OmitGeneratedBands = _Assert<Omit<OpenApiResponse, 'bands'> extends OpenApiResponse ? true : false>;
type _OmitGeneratedInsights = _Assert<Omit<OpenApiResponse, 'insights'> extends OpenApiResponse ? true : false>;
type _OmitGeneratedUnavailable = _Assert<
  Omit<OpenApiResponse, 'unavailable_dimensions'> extends OpenApiResponse ? true : false
>;
type _OmitGeneratedDisclaimer = _Assert<Omit<OpenApiResponse, 'disclaimer'> extends OpenApiResponse ? false : true>;
type _OmitUiLimitations = _Assert<
  Omit<PortfolioHealthResponse['dataQuality'], 'limitations'> extends PortfolioHealthResponse['dataQuality']
    ? false
    : true
>;
type _OmitGeneratedLimitations = _Assert<
  Omit<OpenApiDataQuality, 'limitations'> extends OpenApiDataQuality ? true : false
>;

type _HealthyAssignable = _Assert<'healthy' extends PortfolioHealthBand ? true : false>;
type _MysteryBandRejected = _Assert<'mystery' extends PortfolioHealthBand ? false : true>;
type _StringBandRejected = _Assert<string extends PortfolioHealthBand ? false : true>;
type _UnavailableStatusAssignable = _Assert<'unavailable' extends PortfolioHealthStatus ? true : false>;
type _MysteryStatusRejected = _Assert<'mystery' extends PortfolioHealthStatus ? false : true>;
type _StringStatusRejected = _Assert<string extends PortfolioHealthStatus ? false : true>;
type _RiskExposureNameAssignable = _Assert<'risk_exposure' extends PortfolioHealthDimensionName ? true : false>;
type _RiskExposureNameCamelRejected = _Assert<'riskExposure' extends PortfolioHealthDimensionName ? false : true>;
type _StringDimensionNameRejected = _Assert<string extends PortfolioHealthDimensionName ? false : true>;
type _RiskExposureKeyAssignable = _Assert<'riskExposure' extends PortfolioHealthDimensionKey ? true : false>;
type _RiskExposureKeySnakeRejected = _Assert<'risk_exposure' extends PortfolioHealthDimensionKey ? false : true>;
type _StringDimensionKeyRejected = _Assert<string extends PortfolioHealthDimensionKey ? false : true>;
type _InsightWarningAssignable = _Assert<'warning' extends PortfolioHealthInsight['severity'] ? true : false>;
type _InsightFatalRejected = _Assert<'fatal' extends PortfolioHealthInsight['severity'] ? false : true>;
type _InsightSourceLiteral = _Assert<'rule+llm_polish' extends PortfolioHealthInsight['source'] ? true : false>;
type _InsightSourceStringRejected = _Assert<string extends PortfolioHealthInsight['source'] ? false : true>;

type _UiFormulaLiteral = _Assert<PortfolioHealthResponse['formulaVersion'] extends 'portfolio_health_v2' ? true : false>;
type _UiFormulaNotString = _Assert<string extends PortfolioHealthResponse['formulaVersion'] ? false : true>;
type _UiLlmFalse = _Assert<PortfolioHealthResponse['llmCanModifyScore'] extends false ? true : false>;
type _UiLlmTrueRejected = _Assert<true extends PortfolioHealthResponse['llmCanModifyScore'] ? false : true>;
type _UiScoreSourceRules = _Assert<PortfolioHealthResponse['scoreSource'] extends 'rules' ? true : false>;
type _UiScoreSourceStringRejected = _Assert<string extends PortfolioHealthResponse['scoreSource'] ? false : true>;
type _UiConfigSource = _Assert<PortfolioHealthResponse['config']['source'] extends 'shared_config' ? true : false>;
type _UiConfigSourceStringRejected = _Assert<string extends PortfolioHealthResponse['config']['source'] ? false : true>;
type _GeneratedFormulaLiteral = _Assert<OpenApiResponse['formula_version'] extends 'portfolio_health_v2' ? true : false>;
type _GeneratedLlmFalse = _Assert<OpenApiResponse['llm_can_modify_score'] extends false ? true : false>;
type _GeneratedScoreSourceRules = _Assert<OpenApiResponse['score_source'] extends 'rules' ? true : false>;

type _ResponseAssignableToSummary = _Assert<PortfolioHealthResponse extends PortfolioHealthSummary ? true : false>;
type _SummaryNotFullResponse = _Assert<PortfolioHealthSummary extends PortfolioHealthResponse ? false : true>;

type _PublicQueryLacksPersist = _Assert<'persist' extends keyof PortfolioHealthQuery ? false : true>;
type _RefreshHasPersist = _Assert<'persist' extends keyof PortfolioHealthRefreshQuery ? true : false>;
type _PublicQueryLacksSnake = _Assert<'account_id' extends keyof PortfolioHealthQuery ? false : true>;
type _PublicQueryHasAccountId = _Assert<'accountId' extends keyof PortfolioHealthQuery ? true : false>;
type _PublicQueryRejectsNull = _Assert<{ accountId: null } extends PortfolioHealthQuery ? false : true>;
type _GeneratedQueryAcceptsNull = _Assert<{ account_id: null } extends OpenApiGetQuery ? true : false>;
type _CamelizedQueryAcceptsNull = _Assert<{ accountId: null } extends CamelizeKeys<OpenApiGetQuery> ? true : false>;
type _GeneratedGetQueryLacksPersist = _Assert<'persist' extends keyof OpenApiGetQuery ? false : true>;
type _GeneratedRefreshHasPersist = _Assert<'persist' extends keyof OpenApiRefreshQuery ? true : false>;
type _CamelizedQueryIsNotPublic = _Assert<CamelizeKeys<OpenApiGetQuery> extends PortfolioHealthQuery ? false : true>;

type NarrowDimension = {
  status: 'unavailable';
};
type NarrowInsight = {
  code: string;
  message: string;
  severity: 'warning';
  source: 'rule';
};
type NarrowResponse = {
  asOf: string;
  bands: Array<{ maxExclusive: number; minInclusive: number; name: 'poor' }>;
  comparable: boolean;
  config: {
    cashHighAlertPct: number;
    cashLowAlertPct: number;
    concentrationAlertPct: number;
    diversificationAlert: number;
    pnlLossAlertPct: number;
    source: 'shared_config';
    varAlertPct: number;
    weights: {
      concentration: number;
      riskExposure: number;
      diversification: number;
      pnl: number;
      cashRatio: number;
    };
  };
  costMethod: 'fifo';
  coverageRatio: number;
  currency: string;
  dataQuality: {
    fxStale: boolean;
    limitations: string[];
    missingPriceSymbols: string[];
    partialReasons: string[];
    status: 'unavailable';
  };
  dimensions: {
    concentration: NarrowDimension;
    riskExposure: NarrowDimension;
    diversification: NarrowDimension;
    pnl: NarrowDimension;
    cashRatio: NarrowDimension;
  };
  effectiveWeights: {
    concentration: number;
    riskExposure: number;
    diversification: number;
    pnl: number;
    cashRatio: number;
  };
  formulaVersion: 'portfolio_health_v2';
  inputs: {
    totalCash: number;
    totalEquity: number;
    totalMarketValue: number;
  };
  insights: NarrowInsight[];
  llmCanModifyScore: false;
  persisted: boolean;
  provenance: {
    calculatedAt: string;
    configHash: string;
    riskHash: string;
    snapshotHash: string;
  };
  scoreSource: 'rules';
  status: 'unavailable';
  unavailableDimensions: Array<'concentration' | 'risk_exposure' | 'diversification' | 'pnl' | 'cash_ratio'>;
  weights: {
    concentration: number;
    riskExposure: number;
    diversification: number;
    pnl: number;
    cashRatio: number;
  };
};
type _NarrowResponseAssignable = _Assert<NarrowResponse extends PortfolioHealthResponse ? true : false>;
type _NarrowResponseAssignableToSummary = _Assert<NarrowResponse extends PortfolioHealthSummary ? true : false>;

type SnakeResponse = {
  as_of: string;
  comparable: boolean;
  config: OpenApiResponse['config'];
  cost_method: 'fifo';
  coverage_ratio: number;
  currency: string;
  data_quality: OpenApiDataQuality;
  dimensions: OpenApiDimensions;
  disclaimer: string;
  effective_weights: OpenApiEffectiveWeights;
  formula_version: 'portfolio_health_v2';
  inputs: OpenApiResponse['inputs'];
  llm_can_modify_score: false;
  persisted: boolean;
  provenance: OpenApiResponse['provenance'];
  score_source: 'rules';
  status: 'unavailable';
  weights: OpenApiWeights;
};
type _SnakeMatchesGenerated = _Assert<SnakeResponse extends OpenApiResponse ? true : false>;
type _SnakeDoesNotMatchUi = _Assert<SnakeResponse extends PortfolioHealthResponse ? false : true>;

type MysteryBandResponse = Omit<NarrowResponse, 'bands'> & {
  bands: Array<{ maxExclusive: number; minInclusive: number; name: 'mystery' }>;
};
type _MysteryBandResponseRejected = _Assert<MysteryBandResponse extends PortfolioHealthResponse ? false : true>;

type CamelUnavailable = Omit<NarrowResponse, 'unavailableDimensions'> & {
  unavailableDimensions: Array<'riskExposure'>;
};
type _CamelUnavailableRejected = _Assert<CamelUnavailable extends PortfolioHealthResponse ? false : true>;

type SnakeDimensionKeys = Omit<NarrowResponse, 'dimensions'> & {
  dimensions: {
    concentration: NarrowDimension;
    risk_exposure: NarrowDimension;
    diversification: NarrowDimension;
    pnl: NarrowDimension;
    cash_ratio: NarrowDimension;
  };
};
type _SnakeDimensionKeysRejected = _Assert<SnakeDimensionKeys extends PortfolioHealthResponse ? false : true>;

type _CompileTimePins = [
  _Get200IsResponse,
  _ResponseIsGet200,
  _Refresh200IsResponse,
  _ResponseIsRefresh200,
  _GetOpHasNeverRequestBody,
  _RefreshOpHasNeverRequestBody,
  _UiHasAsOf,
  _UiHasAccountId,
  _UiHasCostMethod,
  _UiHasCoverageRatio,
  _UiHasStatusMessage,
  _UiHasFormulaVersion,
  _UiHasPartialScore,
  _UiHasScoreSource,
  _UiHasUnavailableDimensions,
  _UiHasDataQuality,
  _UiHasEffectiveWeights,
  _UiHasLlmCanModifyScore,
  _UiHasMaxExclusive,
  _UiHasMinInclusive,
  _UiHasFxStale,
  _UiHasMissingPriceSymbols,
  _UiHasPartialReasons,
  _UiHasRiskMetricsStatus,
  _UiHasSnapshotDataQuality,
  _UiHasRiskExposureKey,
  _UiHasCashRatioKey,
  _UiHasCalculatedAt,
  _UiHasConfigHash,
  _UiHasCashHighAlertPct,
  _UiDimensionHasStatusMessage,
  _UiLacksAsOfSnake,
  _UiLacksAccountIdSnake,
  _UiLacksCostMethodSnake,
  _UiLacksCoverageRatioSnake,
  _UiLacksStatusMessageSnake,
  _UiLacksFormulaVersionSnake,
  _UiLacksPartialScoreSnake,
  _UiLacksScoreSourceSnake,
  _UiLacksUnavailableSnake,
  _UiLacksDataQualitySnake,
  _UiLacksEffectiveWeightsSnake,
  _UiLacksLlmSnake,
  _UiLacksMaxExclusiveSnake,
  _UiLacksFxStaleSnake,
  _UiLacksMissingPriceSnake,
  _UiLacksPartialReasonsSnake,
  _UiLacksRiskExposureSnakeKey,
  _UiLacksCashRatioSnakeKey,
  _UiLacksCalculatedAtSnake,
  _UiDimensionLacksStatusMessageSnake,
  _GeneratedHasAsOfSnake,
  _GeneratedHasAccountIdSnake,
  _GeneratedHasCostMethodSnake,
  _GeneratedHasCoverageRatioSnake,
  _GeneratedHasStatusMessageSnake,
  _GeneratedHasFormulaVersionSnake,
  _GeneratedHasPartialScoreSnake,
  _GeneratedHasScoreSourceSnake,
  _GeneratedHasUnavailableSnake,
  _GeneratedHasDataQualitySnake,
  _GeneratedHasEffectiveWeightsSnake,
  _GeneratedHasLlmSnake,
  _GeneratedHasMaxExclusiveSnake,
  _GeneratedHasFxStaleSnake,
  _GeneratedHasMissingPriceSnake,
  _GeneratedHasPartialReasonsSnake,
  _GeneratedHasRiskExposureSnake,
  _GeneratedHasCashRatioSnake,
  _GeneratedHasCalculatedAtSnake,
  _GeneratedDimensionHasStatusMessageSnake,
  _GeneratedInsightHasCode,
  _GeneratedInsightHasSeverity,
  _GeneratedLacksAsOfCamel,
  _GeneratedLacksFormulaCamel,
  _GeneratedLacksRiskExposureCamel,
  _UiBandsRequired,
  _UiInsightsRequired,
  _UiUnavailableRequired,
  _UiDisclaimerOptional,
  _UiLimitationsRequired,
  _UiMissingPriceRequired,
  _UiPartialReasonsRequired,
  _UiEffectiveRiskRequired,
  _GeneratedBandsOptional,
  _GeneratedInsightsOptional,
  _GeneratedUnavailableOptional,
  _GeneratedDisclaimerRequired,
  _GeneratedLimitationsOptional,
  _GeneratedMissingPriceOptional,
  _GeneratedPartialReasonsOptional,
  _GeneratedEffectiveRiskOptional,
  _NaiveCamelBandsOptional,
  _NaiveCamelDisclaimerRequired,
  _OmitUiBands,
  _OmitUiInsights,
  _OmitUiUnavailable,
  _OmitUiDisclaimer,
  _OmitGeneratedBands,
  _OmitGeneratedInsights,
  _OmitGeneratedUnavailable,
  _OmitGeneratedDisclaimer,
  _OmitUiLimitations,
  _OmitGeneratedLimitations,
  _HealthyAssignable,
  _MysteryBandRejected,
  _StringBandRejected,
  _UnavailableStatusAssignable,
  _MysteryStatusRejected,
  _StringStatusRejected,
  _RiskExposureNameAssignable,
  _RiskExposureNameCamelRejected,
  _StringDimensionNameRejected,
  _RiskExposureKeyAssignable,
  _RiskExposureKeySnakeRejected,
  _StringDimensionKeyRejected,
  _InsightWarningAssignable,
  _InsightFatalRejected,
  _InsightSourceLiteral,
  _InsightSourceStringRejected,
  _UiFormulaLiteral,
  _UiFormulaNotString,
  _UiLlmFalse,
  _UiLlmTrueRejected,
  _UiScoreSourceRules,
  _UiScoreSourceStringRejected,
  _UiConfigSource,
  _UiConfigSourceStringRejected,
  _GeneratedFormulaLiteral,
  _GeneratedLlmFalse,
  _GeneratedScoreSourceRules,
  _ResponseAssignableToSummary,
  _SummaryNotFullResponse,
  _PublicQueryLacksPersist,
  _RefreshHasPersist,
  _PublicQueryLacksSnake,
  _PublicQueryHasAccountId,
  _PublicQueryRejectsNull,
  _GeneratedQueryAcceptsNull,
  _CamelizedQueryAcceptsNull,
  _GeneratedGetQueryLacksPersist,
  _GeneratedRefreshHasPersist,
  _CamelizedQueryIsNotPublic,
  _NarrowResponseAssignable,
  _NarrowResponseAssignableToSummary,
  _SnakeMatchesGenerated,
  _SnakeDoesNotMatchUi,
  _MysteryBandResponseRejected,
  _CamelUnavailableRejected,
  _SnakeDimensionKeysRejected,
];

const WEIGHTS = {
  concentration: 0.25,
  riskExposure: 0.25,
  diversification: 0.2,
  pnl: 0.15,
  cashRatio: 0.15,
};
const UNAVAILABLE_DIMENSION = {
  formula: null,
  input: {},
  reason: 'negative_equity',
  score: null,
  status: 'unavailable' as const,
  statusMessage: 'Portfolio equity is negative; health scoring is undefined.',
};
const storedUnavailable = {
  accountId: 1,
  asOf: '2026-08-13',
  band: null,
  bands: [] as Array<{ maxExclusive: number; minInclusive: number; name: PortfolioHealthBand }>,
  comparable: false,
  config: {
    cashHighAlertPct: 50,
    cashLowAlertPct: 2,
    concentrationAlertPct: 35,
    diversificationAlert: 0.35,
    pnlLossAlertPct: -15,
    source: 'shared_config' as const,
    varAlertPct: 5,
    weights: WEIGHTS,
  },
  costMethod: 'fifo' as const,
  coverageRatio: 0,
  currency: 'CNY',
  dataQuality: {
    fxStale: false,
    limitations: ['negative_equity'],
    missingPriceSymbols: [] as string[],
    partialReasons: [] as string[],
    status: 'unavailable' as const,
  },
  dimensions: {
    concentration: UNAVAILABLE_DIMENSION,
    riskExposure: UNAVAILABLE_DIMENSION,
    diversification: UNAVAILABLE_DIMENSION,
    pnl: UNAVAILABLE_DIMENSION,
    cashRatio: UNAVAILABLE_DIMENSION,
  },
  effectiveWeights: WEIGHTS,
  formulaVersion: 'portfolio_health_v2' as const,
  inputs: {
    totalCash: 0,
    totalEquity: -1,
    totalMarketValue: 0,
  },
  insights: [] as PortfolioHealthInsight[],
  llmCanModifyScore: false as const,
  partialScore: null,
  persisted: true,
  provenance: {
    calculatedAt: '2026-08-13T12:00:00Z',
    configHash: 'config',
    riskHash: 'risk',
    snapshotHash: 'snapshot',
  },
  score: null,
  scoreSource: 'rules' as const,
  status: 'unavailable' as const,
  statusMessage: 'Portfolio equity is negative; health scoring is undefined.',
  unavailableDimensions: [
    'concentration',
    'risk_exposure',
    'diversification',
    'pnl',
    'cash_ratio',
  ] as PortfolioHealthDimensionName[],
  weights: WEIGHTS,
};

describe('portfolioHealth OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...PortfolioHealth }).toEqual({});
    expect(Object.keys(PortfolioHealth)).toEqual([]);
    expect(Object.getOwnPropertyNames(PortfolioHealth)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates both path 200 JSON bodies to the generated response component', () => {
    expectTypeOf<OpenApiGet200>().toEqualTypeOf<OpenApiResponse>();
    expectTypeOf<OpenApiRefresh200>().toEqualTypeOf<OpenApiResponse>();
    expectTypeOf<OpenApiGet200>().toEqualTypeOf<OpenApiRefresh200>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof PortfolioHealthResponse>().not.toMatchTypeOf<
      'as_of' | 'account_id' | 'cost_method' | 'formula_version' | 'unavailable_dimensions' | 'data_quality'
    >();
    expectTypeOf<keyof PortfolioHealthResponse['dimensions']>().not.toMatchTypeOf<'risk_exposure' | 'cash_ratio'>();
    expectTypeOf<keyof OpenApiDimensions>().not.toMatchTypeOf<'riskExposure' | 'cashRatio'>();

    type UiHasAsOf = 'asOf' extends keyof PortfolioHealthResponse ? true : false;
    type UiHasAsOfSnake = 'as_of' extends keyof PortfolioHealthResponse ? true : false;
    type GeneratedHasAsOfSnake = 'as_of' extends keyof OpenApiResponse ? true : false;
    type GeneratedHasAsOfCamel = 'asOf' extends keyof OpenApiResponse ? true : false;
    type UiHasFormula = 'formulaVersion' extends keyof PortfolioHealthResponse ? true : false;
    type UiHasFormulaSnake = 'formula_version' extends keyof PortfolioHealthResponse ? true : false;
    type GeneratedHasFormulaSnake = 'formula_version' extends keyof OpenApiResponse ? true : false;
    type UiHasRiskExposure = 'riskExposure' extends keyof PortfolioHealthResponse['dimensions'] ? true : false;
    type UiHasRiskExposureSnake = 'risk_exposure' extends keyof PortfolioHealthResponse['dimensions'] ? true : false;
    type GeneratedHasRiskExposureSnake = 'risk_exposure' extends keyof OpenApiDimensions ? true : false;
    type GeneratedHasRiskExposureCamel = 'riskExposure' extends keyof OpenApiDimensions ? true : false;

    expectTypeOf<UiHasAsOf>().toEqualTypeOf<true>();
    expectTypeOf<UiHasAsOfSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasAsOfSnake>().toEqualTypeOf<true>();
    expectTypeOf<GeneratedHasAsOfCamel>().toEqualTypeOf<false>();
    expectTypeOf<UiHasFormula>().toEqualTypeOf<true>();
    expectTypeOf<UiHasFormulaSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasFormulaSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRiskExposure>().toEqualTypeOf<true>();
    expectTypeOf<UiHasRiskExposureSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasRiskExposureSnake>().toEqualTypeOf<true>();
    expectTypeOf<GeneratedHasRiskExposureCamel>().toEqualTypeOf<false>();
  });

  it('keeps UI bands, insights, unavailableDimensions, and data-quality arrays required', () => {
    expectTypeOf<Omit<PortfolioHealthResponse, 'bands'>>().not.toMatchTypeOf<PortfolioHealthResponse>();
    expectTypeOf<Omit<OpenApiResponse, 'bands'>>().toMatchTypeOf<OpenApiResponse>();
    expectTypeOf<Omit<PortfolioHealthResponse, 'insights'>>().not.toMatchTypeOf<PortfolioHealthResponse>();
    expectTypeOf<Omit<OpenApiResponse, 'insights'>>().toMatchTypeOf<OpenApiResponse>();
    expectTypeOf<Omit<PortfolioHealthResponse, 'unavailableDimensions'>>().not.toMatchTypeOf<PortfolioHealthResponse>();
    expectTypeOf<Omit<OpenApiResponse, 'unavailable_dimensions'>>().toMatchTypeOf<OpenApiResponse>();
    expectTypeOf<Omit<PortfolioHealthResponse['dataQuality'], 'limitations'>>().not.toMatchTypeOf<
      PortfolioHealthResponse['dataQuality']
    >();
    expectTypeOf<Omit<OpenApiDataQuality, 'limitations'>>().toMatchTypeOf<OpenApiDataQuality>();
    expectTypeOf<Omit<PortfolioHealthResponse['dataQuality'], 'missingPriceSymbols'>>().not.toMatchTypeOf<
      PortfolioHealthResponse['dataQuality']
    >();
    expectTypeOf<Omit<OpenApiDataQuality, 'missing_price_symbols'>>().toMatchTypeOf<OpenApiDataQuality>();
    expectTypeOf<Omit<PortfolioHealthResponse['dataQuality'], 'partialReasons'>>().not.toMatchTypeOf<
      PortfolioHealthResponse['dataQuality']
    >();
    expectTypeOf<Omit<OpenApiDataQuality, 'partial_reasons'>>().toMatchTypeOf<OpenApiDataQuality>();
  });

  it('keeps public disclaimer optional while generated disclaimer stays required', () => {
    expectTypeOf<Omit<PortfolioHealthResponse, 'disclaimer'>>().toMatchTypeOf<PortfolioHealthResponse>();
    expectTypeOf<Omit<OpenApiResponse, 'disclaimer'>>().not.toMatchTypeOf<OpenApiResponse>();
  });

  it('keeps unavailableDimensions snake and dimension object keys camel', () => {
    expectTypeOf<'risk_exposure'>().toMatchTypeOf<PortfolioHealthDimensionName>();
    expectTypeOf<'riskExposure'>().not.toMatchTypeOf<PortfolioHealthDimensionName>();
    expectTypeOf<'riskExposure'>().toMatchTypeOf<PortfolioHealthDimensionKey>();
    expectTypeOf<'risk_exposure'>().not.toMatchTypeOf<PortfolioHealthDimensionKey>();
    expectTypeOf<{ unavailableDimensions: ['risk_exposure'] }>().toMatchTypeOf<
      Pick<PortfolioHealthResponse, 'unavailableDimensions'>
    >();
    expectTypeOf<{ unavailableDimensions: ['riskExposure'] }>().not.toMatchTypeOf<
      Pick<PortfolioHealthResponse, 'unavailableDimensions'>
    >();
    expectTypeOf<{ riskExposure: typeof UNAVAILABLE_DIMENSION }>().toMatchTypeOf<
      Pick<PortfolioHealthResponse['dimensions'], 'riskExposure'>
    >();
    expectTypeOf<{ risk_exposure: typeof UNAVAILABLE_DIMENSION }>().not.toMatchTypeOf<
      PortfolioHealthResponse['dimensions']
    >();
  });

  it('keeps band, status, dimension name, and dimension key unions closed', () => {
    expectTypeOf<'healthy'>().toMatchTypeOf<PortfolioHealthBand>();
    expectTypeOf<'mystery'>().not.toMatchTypeOf<PortfolioHealthBand>();
    expectTypeOf<string>().not.toMatchTypeOf<PortfolioHealthBand>();
    expectTypeOf<'unavailable'>().toMatchTypeOf<PortfolioHealthStatus>();
    expectTypeOf<'mystery'>().not.toMatchTypeOf<PortfolioHealthStatus>();
    expectTypeOf<string>().not.toMatchTypeOf<PortfolioHealthStatus>();
    expectTypeOf<'cash_ratio'>().toMatchTypeOf<PortfolioHealthDimensionName>();
    expectTypeOf<'cashRatio'>().not.toMatchTypeOf<PortfolioHealthDimensionName>();
    expectTypeOf<'cashRatio'>().toMatchTypeOf<PortfolioHealthDimensionKey>();
    expectTypeOf<'cash_ratio'>().not.toMatchTypeOf<PortfolioHealthDimensionKey>();
  });

  it('keeps generated constants closed on the UI type', () => {
    expectTypeOf<'portfolio_health_v2'>().toEqualTypeOf<PortfolioHealthResponse['formulaVersion']>();
    expectTypeOf<false>().toEqualTypeOf<PortfolioHealthResponse['llmCanModifyScore']>();
    expectTypeOf<'rules'>().toEqualTypeOf<PortfolioHealthResponse['scoreSource']>();
    expectTypeOf<'shared_config'>().toEqualTypeOf<PortfolioHealthResponse['config']['source']>();
    expectTypeOf<string>().not.toMatchTypeOf<PortfolioHealthResponse['formulaVersion']>();
    expectTypeOf<true>().not.toMatchTypeOf<PortfolioHealthResponse['llmCanModifyScore']>();
  });

  it('accepts the Home storedUnavailable fixture without disclaimer', () => {
    expectTypeOf(storedUnavailable).toMatchTypeOf<PortfolioHealthResponse>();
    expectTypeOf(storedUnavailable).toMatchTypeOf<PortfolioHealthSummary>();
    expectTypeOf<PortfolioHealthResponse>().toMatchTypeOf<PortfolioHealthSummary>();
  });

  it('does not re-export generated snake_case as the UI type', () => {
    const snakeResponse = {
      as_of: '2026-08-13',
      comparable: false,
      config: {
        cash_high_alert_pct: 50,
        cash_low_alert_pct: 2,
        concentration_alert_pct: 35,
        diversification_alert: 0.35,
        pnl_loss_alert_pct: -15,
        source: 'shared_config' as const,
        var_alert_pct: 5,
        weights: {
          concentration: 0.25,
          risk_exposure: 0.25,
          diversification: 0.2,
          pnl: 0.15,
          cash_ratio: 0.15,
        },
      },
      cost_method: 'fifo' as const,
      coverage_ratio: 0,
      currency: 'CNY',
      data_quality: { fx_stale: false, status: 'unavailable' as const },
      dimensions: {
        cash_ratio: { status: 'unavailable' as const },
        concentration: { status: 'unavailable' as const },
        diversification: { status: 'unavailable' as const },
        pnl: { status: 'unavailable' as const },
        risk_exposure: { status: 'unavailable' as const },
      },
      disclaimer: 'not investment advice',
      effective_weights: {},
      formula_version: 'portfolio_health_v2' as const,
      inputs: { total_cash: 0, total_equity: -1, total_market_value: 0 },
      llm_can_modify_score: false as const,
      persisted: true,
      provenance: {
        calculated_at: '2026-08-13T12:00:00Z',
        config_hash: 'config',
        risk_hash: 'risk',
        snapshot_hash: 'snapshot',
      },
      score_source: 'rules' as const,
      status: 'unavailable' as const,
      weights: {
        concentration: 0.25,
        risk_exposure: 0.25,
        diversification: 0.2,
        pnl: 0.15,
        cash_ratio: 0.15,
      },
    };
    expectTypeOf(snakeResponse).toMatchTypeOf<OpenApiResponse>();
    expectTypeOf(snakeResponse).not.toMatchTypeOf<PortfolioHealthResponse>();
  });

  it('keeps handwritten queries optional-without-null and persist only on refresh', () => {
    const query = { accountId: 1, asOf: '2026-08-13', costMethod: 'fifo' as const };
    expectTypeOf(query).toMatchTypeOf<PortfolioHealthQuery>();
    expectTypeOf(query).toMatchTypeOf<PortfolioHealthRefreshQuery>();
    expectTypeOf({ persist: true }).toMatchTypeOf<PortfolioHealthRefreshQuery>();
    expectTypeOf<'persist'>().not.toMatchTypeOf<keyof PortfolioHealthQuery>();
    expectTypeOf<'persist'>().toMatchTypeOf<keyof PortfolioHealthRefreshQuery>();
    expectTypeOf({ accountId: null }).not.toMatchTypeOf<PortfolioHealthQuery>();
    expectTypeOf({ account_id: null }).toMatchTypeOf<OpenApiGetQuery>();
    expectTypeOf({ accountId: null }).toMatchTypeOf<CamelizeKeys<OpenApiGetQuery>>();
    expectTypeOf<'persist'>().not.toMatchTypeOf<keyof OpenApiGetQuery>();
    expectTypeOf({ persist: true }).toMatchTypeOf<OpenApiRefreshQuery>();
  });
});
