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

type OpenApiActor = components['schemas']['SecurityAuditActor'];
type OpenApiTarget = components['schemas']['SecurityAuditTarget'];
type OpenApiEvent = components['schemas']['SecurityAuditEvent'];
type OpenApiPage = components['schemas']['SecurityAuditEventPage'];
type OpenApiGet200 =
  operations['list_security_audit_events_api_v1_security_audit_events_get']['responses']['200']['content']['application/json'];
type OpenApiPathGet = paths['/api/v1/security/audit-events']['get'];
type OpenApiOp = operations['list_security_audit_events_api_v1_security_audit_events_get'];

type _Assert<T extends true> = T;
type _Get200IsPage = _Assert<OpenApiGet200 extends OpenApiPage ? true : false>;
type _PageIsGet200 = _Assert<OpenApiPage extends OpenApiGet200 ? true : false>;
type _OpIsPath = _Assert<OpenApiOp extends OpenApiPathGet ? true : false>;
type _PathIsOp = _Assert<OpenApiPathGet extends OpenApiOp ? true : false>;
type _OpHasNeverRequestBody = _Assert<OpenApiOp extends { requestBody?: never } ? true : false>;
type _PathPostNever = _Assert<
  paths['/api/v1/security/audit-events']['post'] extends never | undefined ? true : false
>;
type _Get200IsNotEvent = _Assert<OpenApiGet200 extends OpenApiEvent ? false : true>;

type _OpenApiAnchors = [
  _Get200IsPage,
  _PageIsGet200,
  _OpIsPath,
  _PathIsOp,
  _OpHasNeverRequestBody,
  _PathPostNever,
  _Get200IsNotEvent,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type SecurityAuditPhase = OpenApiEvent['phase'];
export type SecurityAuditOutcome = OpenApiEvent['outcome'];

export type SecurityAuditActor = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiActor>, {
  type: string;
  id: string;
}>>;

export type SecurityAuditTarget = Override<CamelizeKeys<OpenApiTarget>, {
  type: string;
  id: string;
}>;

export type SecurityAuditEvent = Override<CamelizeKeys<OpenApiEvent>, {
  id: number;
  schemaVersion?: 'security-audit-v1' | string;
  occurredAt?: string;
  eventType: string;
  phase: SecurityAuditPhase;
  actor: SecurityAuditActor;
  executionId: string;
  action: string;
  target: SecurityAuditTarget;
  outcome: SecurityAuditOutcome;
  reasonCode: string;
  correlationId: string;
  metadata?: Record<string, unknown>;
}>;

export type SecurityAuditEventPage = Override<CamelizeKeys<OpenApiPage>, {
  items: SecurityAuditEvent[];
  page: number;
  pageSize: number;
  total: number;
}>;

export interface SecurityAuditListQuery {
  page?: number;
  pageSize?: number;
  eventType?: string;
  outcome?: SecurityAuditOutcome;
  correlationId?: string;
  /** ISO-8601 timestamp with timezone (backend requires tz-aware values). */
  occurredFrom?: string;
  /** ISO-8601 timestamp with timezone (backend requires tz-aware values). */
  occurredTo?: string;
}

/** Backend maximum page size for GET /api/v1/security/audit-events. */
export const SECURITY_AUDIT_MAX_PAGE_SIZE = 100;
