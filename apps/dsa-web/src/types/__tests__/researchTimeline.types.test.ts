// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as ResearchTimeline from '../researchTimeline';
import type {
  ResearchTimelineKind,
  ResearchTimelineLink,
  ResearchTimelineNode,
  ResearchTimelineParams,
  ResearchTimelineResponse,
  ResearchTimelineSources,
} from '../researchTimeline';

type OpenApiResponse = components['schemas']['ResearchTimelineResponse'];
type OpenApiNode = components['schemas']['ResearchTimelineNode'];
type OpenApiLink = components['schemas']['ResearchTimelineLink'];
type OpenApiGetOp =
  operations['get_stock_research_timeline_api_v1_stocks__stock_code__research_timeline_get'];
type OpenApiGet200 = OpenApiGetOp['responses']['200']['content']['application/json'];
type OpenApiPathGet = paths['/api/v1/stocks/{stock_code}/research-timeline']['get'];
type OpenApiGetQuery = NonNullable<OpenApiGetOp['parameters']['query']>;

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
type HasStringIndex<T> = string extends keyof T ? true : false;

type _FourComponents = _Assert<
  ('ResearchTimelineResponse' | 'ResearchTimelineNode' | 'ResearchTimelineLink' | 'ResearchTimelineSources') extends keyof components['schemas'] ? true : false
>;
type _Get200IsComponent = _Assert<OpenApiGet200 extends OpenApiResponse ? true : false>;
type _ComponentIsGet200 = _Assert<OpenApiResponse extends OpenApiGet200 ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiPathGet extends OpenApiGetOp ? true : false>;
type _GetOpHasNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _PathPostNever = _Assert<
  paths['/api/v1/stocks/{stock_code}/research-timeline']['post'] extends never | undefined ? true : false
>;

type _UiHasStockCode = _Assert<'stockCode' extends keyof ResearchTimelineResponse ? true : false>;
type _UiHasOccurredAt = _Assert<'occurredAt' extends keyof ResearchTimelineNode ? true : false>;
type _UiHasAnalysisRun = _Assert<'analysisRun' extends keyof ResearchTimelineSources ? true : false>;
type _UiLacksStockCodeSnake = _Assert<'stock_code' extends keyof ResearchTimelineResponse ? false : true>;
type _UiLacksOccurredAtSnake = _Assert<'occurred_at' extends keyof ResearchTimelineNode ? false : true>;
type _UiLacksAnalysisRunSnake = _Assert<'analysis_run' extends keyof ResearchTimelineSources ? false : true>;
type _GeneratedHasStockCodeSnake = _Assert<'stock_code' extends keyof OpenApiResponse ? true : false>;
type _GeneratedHasOccurredAtSnake = _Assert<'occurred_at' extends keyof OpenApiNode ? true : false>;
type _GeneratedLacksStockCodeCamel = _Assert<'stockCode' extends keyof OpenApiResponse ? false : true>;

type _UiItemsRequired = _Assert<IsOptional<ResearchTimelineResponse, 'items'> extends false ? true : false>;
type _GeneratedItemsOptional = _Assert<IsOptional<OpenApiResponse, 'items'>>;
type _NaiveCamelItemsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiResponse>, 'items'>>;
type _OmitUiItems = _Assert<Omit<ResearchTimelineResponse, 'items'> extends ResearchTimelineResponse ? false : true>;
type _OmitGeneratedItems = _Assert<Omit<OpenApiResponse, 'items'> extends OpenApiResponse ? true : false>;

type _KindClosed = _Assert<ResearchTimelineNode['kind'] extends ResearchTimelineKind ? true : false>;
type _StringKindRejected = _Assert<string extends ResearchTimelineKind ? false : true>;
type _NewsKindRejected = _Assert<'news' extends ResearchTimelineKind ? false : true>;
type _GeneratedKindIsString = _Assert<string extends OpenApiNode['kind'] ? true : false>;
type _NaiveCamelKindIsString = _Assert<string extends CamelizeKeys<OpenApiNode>['kind'] ? true : false>;

type _UiLinkHasNoIndex = _Assert<HasStringIndex<ResearchTimelineLink> extends false ? true : false>;
type _GeneratedLinkHasIndex = _Assert<HasStringIndex<OpenApiLink>>;
type _NaiveCamelLinkHasIndex = _Assert<HasStringIndex<CamelizeKeys<OpenApiLink>>>;
type _UiLinkKeepsType = _Assert<'type' extends keyof ResearchTimelineLink ? true : false>;
type _UiLinkKeepsStockCode = _Assert<'stockCode' extends keyof ResearchTimelineLink ? true : false>;
type _LinkTypeStaysString = _Assert<string extends ResearchTimelineLink['type'] ? true : false>;
type _SourcesStayString = _Assert<string extends ResearchTimelineSources['hypothesis'] ? true : false>;
type _NextCursorOptional = _Assert<IsOptional<ResearchTimelineResponse, 'nextCursor'>>;
type _MetaOptional = _Assert<IsOptional<ResearchTimelineNode, 'meta'>>;

type _QueryKindsIsString = _Assert<string extends NonNullable<OpenApiGetQuery['kinds']> ? true : false>;
type _ParamsKindsIsArray = _Assert<
  NonNullable<ResearchTimelineParams['kinds']> extends ResearchTimelineKind[] ? true : false
>;
type _ParamsKindsNotString = _Assert<string extends ResearchTimelineParams['kinds'] ? false : true>;

type ConsumerFixture = {
  stockCode: string;
  items: Array<{
    id: string;
    kind: 'analysis_run';
    occurredAt: string;
    title: string;
    link: { type: string; recordId: number; stockCode: string };
  }>;
  nextCursor: null;
  hasMore: boolean;
  limit: number;
  sources: { analysisRun: string; chat: string; signal: string; hypothesis: string };
};
type _ConsumerAssignable = _Assert<ConsumerFixture extends ResearchTimelineResponse ? true : false>;
type MissingItems = Omit<ConsumerFixture, 'items'>;
type _MissingItemsRejected = _Assert<MissingItems extends ResearchTimelineResponse ? false : true>;
type OpenKindNode = { id: string; kind: 'news'; occurredAt: string; title: string; link: { type: string } };
type _OpenKindRejected = _Assert<OpenKindNode extends ResearchTimelineNode ? false : true>;

type SnakeResponse = {
  stock_code: string; has_more: boolean; limit: number;
  sources: { analysis_run: string; chat: string; signal: string; hypothesis: string };
};
type _SnakeMatchesGenerated = _Assert<SnakeResponse extends OpenApiResponse ? true : false>;
type _SnakeDoesNotMatchUi = _Assert<SnakeResponse extends ResearchTimelineResponse ? false : true>;

type _CompileTimePins = [
  _FourComponents,
  _Get200IsComponent,
  _ComponentIsGet200,
  _GetOpIsPath,
  _PathIsGetOp,
  _GetOpHasNeverRequestBody,
  _PathPostNever,
  _UiHasStockCode,
  _UiHasOccurredAt,
  _UiHasAnalysisRun,
  _UiLacksStockCodeSnake,
  _UiLacksOccurredAtSnake,
  _UiLacksAnalysisRunSnake,
  _GeneratedHasStockCodeSnake,
  _GeneratedHasOccurredAtSnake,
  _GeneratedLacksStockCodeCamel,
  _UiItemsRequired,
  _GeneratedItemsOptional,
  _NaiveCamelItemsOptional,
  _OmitUiItems,
  _OmitGeneratedItems,
  _KindClosed,
  _StringKindRejected,
  _NewsKindRejected,
  _GeneratedKindIsString,
  _NaiveCamelKindIsString,
  _UiLinkHasNoIndex,
  _GeneratedLinkHasIndex,
  _NaiveCamelLinkHasIndex,
  _UiLinkKeepsType,
  _UiLinkKeepsStockCode,
  _LinkTypeStaysString,
  _SourcesStayString,
  _NextCursorOptional,
  _MetaOptional,
  _QueryKindsIsString,
  _ParamsKindsIsArray,
  _ParamsKindsNotString,
  _ConsumerAssignable,
  _MissingItemsRejected,
  _OpenKindRejected,
  _SnakeMatchesGenerated,
  _SnakeDoesNotMatchUi,
];

describe('researchTimeline OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    // ESM namespace objects carry Symbol.toStringTag='Module'; enumerable exports must stay empty.
    expect({ ...ResearchTimeline }).toEqual({});
    expect(Object.keys(ResearchTimeline)).toEqual([]);
    expect(Object.getOwnPropertyNames(ResearchTimeline)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates GET 200 JSON to the generated response component', () => {
    expectTypeOf<OpenApiGet200>().toEqualTypeOf<OpenApiResponse>();
    expectTypeOf<OpenApiGetOp>().toEqualTypeOf<OpenApiPathGet>();
    type HasNeverBody = OpenApiGetOp extends { requestBody?: never } ? true : false;
    expectTypeOf<HasNeverBody>().toEqualTypeOf<true>();
  });

  it('keeps the three UI overrides versus generated optionality, open kind, and link index', () => {
    expectTypeOf<Omit<ResearchTimelineResponse, 'items'>>().not.toMatchTypeOf<ResearchTimelineResponse>();
    expectTypeOf<Omit<OpenApiResponse, 'items'>>().toMatchTypeOf<OpenApiResponse>();
    expectTypeOf<ResearchTimelineNode['kind']>().toEqualTypeOf<ResearchTimelineKind>();
    expectTypeOf<OpenApiNode['kind']>().toEqualTypeOf<string>();
    expectTypeOf<string>().not.toMatchTypeOf<ResearchTimelineKind>();
    expectTypeOf<'news'>().not.toMatchTypeOf<ResearchTimelineKind>();
    type UiIndex = HasStringIndex<ResearchTimelineLink>;
    type GeneratedIndex = HasStringIndex<OpenApiLink>;
    type NaiveIndex = HasStringIndex<CamelizeKeys<OpenApiLink>>;
    expectTypeOf<UiIndex>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedIndex>().toEqualTypeOf<true>();
    expectTypeOf<NaiveIndex>().toEqualTypeOf<true>();
    expectTypeOf<keyof ResearchTimelineLink>().toMatchTypeOf<
      'type' | 'stockCode' | 'recordId' | 'queryId' | 'sessionId' | 'messageId' | 'turnId' | 'signalId' | 'sourceReportId'
    >();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof ResearchTimelineResponse>().not.toMatchTypeOf<'stock_code' | 'next_cursor' | 'has_more'>();
    expectTypeOf<keyof ResearchTimelineNode>().not.toMatchTypeOf<'occurred_at'>();
    expectTypeOf<keyof ResearchTimelineSources>().not.toMatchTypeOf<'analysis_run'>();
    expectTypeOf<keyof OpenApiResponse>().not.toMatchTypeOf<'stockCode' | 'nextCursor' | 'hasMore'>();
    const snake = {
      stock_code: '600519', has_more: false, limit: 20,
      sources: { analysis_run: 'ok', chat: 'empty', signal: 'empty', hypothesis: 'unavailable' },
    };
    expectTypeOf(snake).toMatchTypeOf<OpenApiResponse>();
    expectTypeOf(snake).not.toMatchTypeOf<ResearchTimelineResponse>();
  });

  it('keeps handwritten query params distinct from the generated comma-separated kinds filter', () => {
    expectTypeOf<NonNullable<OpenApiGetQuery['kinds']>>().toEqualTypeOf<string>();
    expectTypeOf<NonNullable<ResearchTimelineParams['kinds']>>().toEqualTypeOf<ResearchTimelineKind[]>();
    expectTypeOf<string>().not.toMatchTypeOf<ResearchTimelineParams['kinds']>();
  });

  it('accepts one consumer-shaped fixture and rejects missing items or an open kind', () => {
    const fixture: ResearchTimelineResponse = {
      stockCode: '600519',
      items: [{
        id: 'analysis_run:1',
        kind: 'analysis_run',
        occurredAt: '2026-08-01T10:00:00+00:00',
        title: 'Buy',
        direction: 'Bullish',
        confidence: 0.72,
        link: { type: 'analysis_history', recordId: 1, stockCode: '600519' },
      }],
      nextCursor: null,
      hasMore: false,
      limit: 20,
      sources: { analysisRun: 'ok', chat: 'empty', signal: 'empty', hypothesis: 'unavailable' },
    };
    expectTypeOf(fixture).toMatchTypeOf<ResearchTimelineResponse>();
    expectTypeOf(fixture.items[0]).toMatchTypeOf<ResearchTimelineNode>();
    expectTypeOf(fixture.items[0].link).toMatchTypeOf<ResearchTimelineLink>();
    expectTypeOf(fixture.sources).toMatchTypeOf<ResearchTimelineSources>();
  });
});
