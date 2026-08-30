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

type OpenApiLocalOnly = components['schemas']['LocalOnlyModeStatus'];
type OpenApiItem = components['schemas']['OutboundActivityItem'];
type OpenApiPage = components['schemas']['OutboundActivityPage'];
type OpenApiLocalOnlyGet200 =
  operations['get_local_only_mode_status_api_v1_security_local_only_get']['responses']['200']['content']['application/json'];
type OpenApiOutboundGet200 =
  operations['list_outbound_activity_api_v1_security_outbound_activity_get']['responses']['200']['content']['application/json'];

type _Assert<T extends true> = T;
type _LocalOnlyGetIsComponent = _Assert<OpenApiLocalOnlyGet200 extends OpenApiLocalOnly ? true : false>;
type _LocalOnlyComponentIsGet = _Assert<OpenApiLocalOnly extends OpenApiLocalOnlyGet200 ? true : false>;
type _OutboundGetIsComponent = _Assert<OpenApiOutboundGet200 extends OpenApiPage ? true : false>;
type _OutboundComponentIsGet = _Assert<OpenApiPage extends OpenApiOutboundGet200 ? true : false>;

type _OpenApiAnchors = [
  _LocalOnlyGetIsComponent,
  _LocalOnlyComponentIsGet,
  _OutboundGetIsComponent,
  _OutboundComponentIsGet,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type OutboundDecision = 'allowed' | 'blocked';

export type LocalOnlyModeStatus = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiLocalOnly>, {
  enabled: boolean;
  envKey: string;
  policy: string;
  allowedDestinationClasses: string[];
  blockedErrorReason: string;
}>>;

export type OutboundActivityItem = Override<CamelizeKeys<OpenApiItem>, {
  occurredAt: string;
  decision: OutboundDecision;
  destinationClass: string;
  scheme: string;
  hostType: string;
  reason: string;
  correlationId: string;
  localOnlyMode: boolean;
  allowlisted: boolean;
}>;

export type OutboundActivityPage = Override<CamelizeKeys<OpenApiPage>, {
  localOnlyMode: boolean;
  items: OutboundActivityItem[];
  limit: number;
  returned: number;
  maxRetained: number;
}>;

export type OutboundActivityListQuery = { limit?: number };
