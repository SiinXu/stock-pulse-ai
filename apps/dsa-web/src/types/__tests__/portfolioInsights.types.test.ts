// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations } from '../api.generated';
import * as Insights from '../portfolioInsights';
import type {
  PortfolioBasketRequest,
  PortfolioBasketResponse,
  PortfolioRebalancingResponse,
  PortfolioStressResponse,
  RiskTolerance,
  StressPositionImpact,
  StressScenarioListResponse,
  StressShock,
} from '../portfolioInsights';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type OpenApiBasketRequest = components['schemas']['PortfolioLevelAnalysisRequest'];
type OpenApiBasketResponse = components['schemas']['PortfolioLevelAnalysisResponse'];
type OpenApiScenarioList = components['schemas']['StressScenarioListResponse'];
type OpenApiStressResponse = components['schemas']['PortfolioStressTestResponse'];
type OpenApiRebalanceResponse = components['schemas']['PortfolioRebalancingResponse'];
type OpenApiBasketPost200 = operations['analyzePortfolioLevel']['responses']['200']['content']['application/json'];
type OpenApiScenarioGet200 = operations['listPortfolioStressScenarios']['responses']['200']['content']['application/json'];
type OpenApiStressGet200 = operations['getPortfolioStressTest']['responses']['200']['content']['application/json'];
type OpenApiStressPost200 = operations['postPortfolioStressTest']['responses']['200']['content']['application/json'];
type OpenApiRebalanceGet200 = operations['getPortfolioRebalancingRecommendations']['responses']['200']['content']['application/json'];

describe('portfolioInsights OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...Insights }).toEqual({});
    expect(Object.keys(Insights)).toEqual([]);
    expect(Object.getOwnPropertyNames(Insights)).toEqual([]);
  });

  it('equates path 200 JSON to the generated response components', () => {
    expectTypeOf<OpenApiBasketPost200>().toEqualTypeOf<OpenApiBasketResponse>();
    expectTypeOf<OpenApiScenarioGet200>().toEqualTypeOf<OpenApiScenarioList>();
    expectTypeOf<OpenApiStressGet200>().toEqualTypeOf<OpenApiStressResponse>();
    expectTypeOf<OpenApiStressPost200>().toEqualTypeOf<OpenApiStressResponse>();
    expectTypeOf<OpenApiStressGet200>().toEqualTypeOf<OpenApiStressPost200>();
    expectTypeOf<OpenApiRebalanceGet200>().toEqualTypeOf<OpenApiRebalanceResponse>();
  });

  it('keeps snake_case keys off the UI basket response', () => {
    expectTypeOf<keyof PortfolioBasketResponse>().not.toMatchTypeOf<'formula_version' | 'stock_codes'>();
    type UiHasFormulaVersion = 'formulaVersion' extends keyof PortfolioBasketResponse ? true : false;
    type UiHasFormulaSnake = 'formula_version' extends keyof PortfolioBasketResponse ? true : false;
    type GeneratedHasFormulaSnake = 'formula_version' extends keyof OpenApiBasketResponse ? true : false;
    expectTypeOf<UiHasFormulaVersion>().toEqualTypeOf<true>();
    expectTypeOf<UiHasFormulaSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasFormulaSnake>().toEqualTypeOf<true>();
  });

  it('keeps UI-required arrays required while generated counterparts stay optional', () => {
    expectTypeOf<Omit<PortfolioBasketResponse, 'degradedSymbols'>>().not.toMatchTypeOf<PortfolioBasketResponse>();
    expectTypeOf<Omit<OpenApiBasketResponse, 'degraded_symbols'>>().toMatchTypeOf<OpenApiBasketResponse>();
    expectTypeOf<Omit<StressScenarioListResponse, 'scenarios'>>().not.toMatchTypeOf<StressScenarioListResponse>();
    expectTypeOf<Omit<OpenApiScenarioList, 'scenarios'>>().toMatchTypeOf<OpenApiScenarioList>();
    expectTypeOf<Omit<PortfolioStressResponse, 'positionImpacts'>>().not.toMatchTypeOf<PortfolioStressResponse>();
    expectTypeOf<Omit<OpenApiStressResponse, 'position_impacts'>>().toMatchTypeOf<OpenApiStressResponse>();
  });

  it('still accepts the narrow 14-field stress impact fixture', () => {
    const impact = {
      positionKey: '1-AAPL-us',
      accountId: 1,
      symbol: 'AAPL',
      marketValue: 1000,
      weightPct: 50,
      shockPct: -10,
      pnl: -100,
      stressedMarketValue: 900,
      priceSource: 'history_close',
      priceProvider: 'fixture',
      priceDate: '2026-08-15',
      priceStale: false,
      dataQuality: 'ok' as const,
      limitations: [] as string[],
    };
    expectTypeOf(impact).toMatchTypeOf<StressPositionImpact>();
  });

  it('accepts the current stress assumptions projection', () => {
    const assumptions = { simplifiedAssumptions: [] as string[], dataSource: 'portfolio_snapshot' };
    expectTypeOf(assumptions).toMatchTypeOf<PortfolioStressResponse['assumptions']>();
  });

  it('keeps rebalance autoExecute false and isSuggestionOnly true as literals', () => {
    expectTypeOf<{ autoExecute: false; isSuggestionOnly: true }>().toMatchTypeOf<
      Pick<PortfolioRebalancingResponse, 'autoExecute' | 'isSuggestionOnly'>
    >();
    expectTypeOf<{ autoExecute: true; isSuggestionOnly: false }>().not.toMatchTypeOf<
      Pick<PortfolioRebalancingResponse, 'autoExecute' | 'isSuggestionOnly'>
    >();
  });

  it('discriminates shock factor payloads', () => {
    expectTypeOf({ factor: 'rate' as const, valueBp: 25 }).toMatchTypeOf<StressShock>();
    expectTypeOf({ factor: 'rate' as const, valuePct: -10 }).not.toMatchTypeOf<StressShock>();
    expectTypeOf({ factor: 'market' as const, valuePct: -10 }).toMatchTypeOf<StressShock>();
    expectTypeOf({ factor: 'market' as const, valueBp: 25 }).not.toMatchTypeOf<StressShock>();
  });

  it('keeps handwritten basket request fields optional', () => {
    const request = { stockCodes: ['AAPL'] };
    expectTypeOf(request).toMatchTypeOf<PortfolioBasketRequest>();
    expectTypeOf(request).not.toMatchTypeOf<CamelizeKeys<OpenApiBasketRequest>>();
  });

  it('aliases RiskTolerance to the generated rebalance query enum', () => {
    expectTypeOf<RiskTolerance>().toEqualTypeOf<'conservative' | 'moderate' | 'aggressive'>();
  });
});
