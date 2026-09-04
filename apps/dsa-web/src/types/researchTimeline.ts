// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations, paths } from './api.generated';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type StripIndexSignature<T> = {
  [K in keyof T as string extends K ? never : number extends K ? never : K]: T[K];
};

type OpenApiResearchTimelineResponse = components['schemas']['ResearchTimelineResponse'];
type OpenApiResearchTimelineNode = components['schemas']['ResearchTimelineNode'];
type OpenApiResearchTimelineLink = components['schemas']['ResearchTimelineLink'];
type OpenApiResearchTimelineSources = components['schemas']['ResearchTimelineSources'];
type OpenApiGet200 =
  operations['get_stock_research_timeline_api_v1_stocks__stock_code__research_timeline_get']['responses']['200']['content']['application/json'];
type OpenApiGetOp =
  operations['get_stock_research_timeline_api_v1_stocks__stock_code__research_timeline_get'];
type OpenApiPathGet = paths['/api/v1/stocks/{stock_code}/research-timeline']['get'];
type OpenApiGetQuery = NonNullable<OpenApiGetOp['parameters']['query']>;

type _Assert<T extends true> = T;
type _Get200IsComponent = _Assert<OpenApiGet200 extends OpenApiResearchTimelineResponse ? true : false>;
type _ComponentIsGet200 = _Assert<OpenApiResearchTimelineResponse extends OpenApiGet200 ? true : false>;
type _GetOpIsPath = _Assert<OpenApiGetOp extends OpenApiPathGet ? true : false>;
type _PathIsGetOp = _Assert<OpenApiPathGet extends OpenApiGetOp ? true : false>;
type _GetOpHasNeverRequestBody = _Assert<OpenApiGetOp extends { requestBody?: never } ? true : false>;
type _PathPostNever = _Assert<
  paths['/api/v1/stocks/{stock_code}/research-timeline']['post'] extends never | undefined ? true : false
>;
type _PathPutNever = _Assert<
  paths['/api/v1/stocks/{stock_code}/research-timeline']['put'] extends never | undefined ? true : false
>;
type _PathDeleteNever = _Assert<
  paths['/api/v1/stocks/{stock_code}/research-timeline']['delete'] extends never | undefined ? true : false
>;
type _GetQueryHasKinds = _Assert<'kinds' extends keyof OpenApiGetQuery ? true : false>;
type _GetQueryKindsIsString = _Assert<string extends NonNullable<OpenApiGetQuery['kinds']> ? true : false>;
type _GetQueryKindsAllowsNull = _Assert<null extends OpenApiGetQuery['kinds'] ? true : false>;

type _OpenApiAnchors = [
  _Get200IsComponent,
  _ComponentIsGet200,
  _GetOpIsPath,
  _PathIsGetOp,
  _GetOpHasNeverRequestBody,
  _PathPostNever,
  _PathPutNever,
  _PathDeleteNever,
  _GetQueryHasKinds,
  _GetQueryKindsIsString,
  _GetQueryKindsAllowsNull,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type ResearchTimelineKind = 'analysis_run' | 'chat' | 'signal' | 'hypothesis';

export type ResearchTimelineLink = CamelizeKeys<StripIndexSignature<OpenApiResearchTimelineLink>>;

export type ResearchTimelineNode = Override<CamelizeKeys<OpenApiResearchTimelineNode>, {
  kind: ResearchTimelineKind;
  link: ResearchTimelineLink;
}>;

export type ResearchTimelineSources = CamelizeKeys<OpenApiResearchTimelineSources>;

export type ResearchTimelineResponse = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiResearchTimelineResponse>, {
  items: ResearchTimelineNode[];
}>>;

export type ResearchTimelineParams = {
  cursor?: string | null;
  limit?: number;
  kinds?: ResearchTimelineKind[];
};
