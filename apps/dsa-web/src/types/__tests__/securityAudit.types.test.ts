// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as SecurityAudit from '../securityAudit';
import {
  SECURITY_AUDIT_MAX_PAGE_SIZE,
} from '../securityAudit';
import type {
  SecurityAuditActor,
  SecurityAuditEvent,
  SecurityAuditEventPage,
  SecurityAuditListQuery,
  SecurityAuditOutcome,
  SecurityAuditPhase,
  SecurityAuditTarget,
} from '../securityAudit';

type OpenApiActor = components['schemas']['SecurityAuditActor'];
type OpenApiTarget = components['schemas']['SecurityAuditTarget'];
type OpenApiEvent = components['schemas']['SecurityAuditEvent'];
type OpenApiPage = components['schemas']['SecurityAuditEventPage'];
type OpenApiGet200 =
  operations['list_security_audit_events_api_v1_security_audit_events_get']['responses']['200']['content']['application/json'];
type OpenApiPathGet = paths['/api/v1/security/audit-events']['get'];
type OpenApiOp = operations['list_security_audit_events_api_v1_security_audit_events_get'];
type OpenApiQuery = NonNullable<OpenApiOp['parameters']['query']>;

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type CamelQuery = CamelizeKeys<OpenApiQuery>;

type _Assert<T extends true> = T;
type IsOptional<T, K extends keyof T> = Partial<Pick<T, K>> extends Pick<T, K> ? true : false;

type _Get200IsPage = _Assert<OpenApiGet200 extends OpenApiPage ? true : false>;
type _PageIsGet200 = _Assert<OpenApiPage extends OpenApiGet200 ? true : false>;
type _OpIsPath = _Assert<OpenApiOp extends OpenApiPathGet ? true : false>;
type _PathIsOp = _Assert<OpenApiPathGet extends OpenApiOp ? true : false>;
type _OpHasNeverRequestBody = _Assert<OpenApiOp extends { requestBody?: never } ? true : false>;
type _PathPostNever = _Assert<
  paths['/api/v1/security/audit-events']['post'] extends never | undefined ? true : false
>;
type _Get200IsNotEvent = _Assert<OpenApiGet200 extends OpenApiEvent ? false : true>;

type _UiHasEventType = _Assert<'eventType' extends keyof SecurityAuditEvent ? true : false>;
type _UiHasExecutionId = _Assert<'executionId' extends keyof SecurityAuditEvent ? true : false>;
type _UiHasReasonCode = _Assert<'reasonCode' extends keyof SecurityAuditEvent ? true : false>;
type _UiHasCorrelationId = _Assert<'correlationId' extends keyof SecurityAuditEvent ? true : false>;
type _UiHasSchemaVersion = _Assert<'schemaVersion' extends keyof SecurityAuditEvent ? true : false>;
type _UiHasOccurredAt = _Assert<'occurredAt' extends keyof SecurityAuditEvent ? true : false>;
type _UiHasPageSize = _Assert<'pageSize' extends keyof SecurityAuditEventPage ? true : false>;
type _UiQueryHasPageSize = _Assert<'pageSize' extends keyof SecurityAuditListQuery ? true : false>;
type _UiQueryHasEventType = _Assert<'eventType' extends keyof SecurityAuditListQuery ? true : false>;
type _UiQueryHasCorrelationId = _Assert<'correlationId' extends keyof SecurityAuditListQuery ? true : false>;
type _UiQueryHasOccurredFrom = _Assert<'occurredFrom' extends keyof SecurityAuditListQuery ? true : false>;
type _UiQueryHasOccurredTo = _Assert<'occurredTo' extends keyof SecurityAuditListQuery ? true : false>;

type _UiLacksEventTypeSnake = _Assert<'event_type' extends keyof SecurityAuditEvent ? false : true>;
type _UiLacksExecutionIdSnake = _Assert<'execution_id' extends keyof SecurityAuditEvent ? false : true>;
type _UiLacksReasonCodeSnake = _Assert<'reason_code' extends keyof SecurityAuditEvent ? false : true>;
type _UiLacksCorrelationIdSnake = _Assert<'correlation_id' extends keyof SecurityAuditEvent ? false : true>;
type _UiLacksSchemaVersionSnake = _Assert<'schema_version' extends keyof SecurityAuditEvent ? false : true>;
type _UiLacksOccurredAtSnake = _Assert<'occurred_at' extends keyof SecurityAuditEvent ? false : true>;
type _UiLacksPageSizeSnake = _Assert<'page_size' extends keyof SecurityAuditEventPage ? false : true>;
type _UiQueryLacksPageSizeSnake = _Assert<'page_size' extends keyof SecurityAuditListQuery ? false : true>;
type _UiQueryLacksEventTypeSnake = _Assert<'event_type' extends keyof SecurityAuditListQuery ? false : true>;
type _UiQueryLacksCorrelationIdSnake = _Assert<'correlation_id' extends keyof SecurityAuditListQuery ? false : true>;
type _UiQueryLacksOccurredFromSnake = _Assert<'occurred_from' extends keyof SecurityAuditListQuery ? false : true>;
type _UiQueryLacksOccurredToSnake = _Assert<'occurred_to' extends keyof SecurityAuditListQuery ? false : true>;

type _GeneratedHasEventTypeSnake = _Assert<'event_type' extends keyof OpenApiEvent ? true : false>;
type _GeneratedHasExecutionIdSnake = _Assert<'execution_id' extends keyof OpenApiEvent ? true : false>;
type _GeneratedHasReasonCodeSnake = _Assert<'reason_code' extends keyof OpenApiEvent ? true : false>;
type _GeneratedHasCorrelationIdSnake = _Assert<'correlation_id' extends keyof OpenApiEvent ? true : false>;
type _GeneratedHasSchemaVersionSnake = _Assert<'schema_version' extends keyof OpenApiEvent ? true : false>;
type _GeneratedHasOccurredAtSnake = _Assert<'occurred_at' extends keyof OpenApiEvent ? true : false>;
type _GeneratedHasPageSizeSnake = _Assert<'page_size' extends keyof OpenApiPage ? true : false>;
type _GeneratedQueryHasPageSizeSnake = _Assert<'page_size' extends keyof OpenApiQuery ? true : false>;
type _GeneratedQueryHasEventTypeSnake = _Assert<'event_type' extends keyof OpenApiQuery ? true : false>;

type _UiLacksEventTypeCamelOnGenerated = _Assert<'eventType' extends keyof OpenApiEvent ? false : true>;
type _UiLacksPageSizeCamelOnGenerated = _Assert<'pageSize' extends keyof OpenApiPage ? false : true>;
type _UiLacksSchemaVersionCamelOnGenerated = _Assert<'schemaVersion' extends keyof OpenApiEvent ? false : true>;

type _UiSchemaVersionOptional = _Assert<IsOptional<SecurityAuditEvent, 'schemaVersion'>>;
type _GeneratedSchemaVersionRequired = _Assert<
  IsOptional<OpenApiEvent, 'schema_version'> extends false ? true : false
>;
type _UiOccurredAtOptional = _Assert<IsOptional<SecurityAuditEvent, 'occurredAt'>>;
type _GeneratedOccurredAtOptional = _Assert<IsOptional<OpenApiEvent, 'occurred_at'>>;
type _UiMetadataOptional = _Assert<IsOptional<SecurityAuditEvent, 'metadata'>>;
type _GeneratedMetadataOptional = _Assert<IsOptional<OpenApiEvent, 'metadata'>>;
type _UiItemsRequired = _Assert<IsOptional<SecurityAuditEventPage, 'items'> extends false ? true : false>;
type _UiPageRequired = _Assert<IsOptional<SecurityAuditEventPage, 'page'> extends false ? true : false>;
type _UiPageSizeRequired = _Assert<IsOptional<SecurityAuditEventPage, 'pageSize'> extends false ? true : false>;
type _UiTotalRequired = _Assert<IsOptional<SecurityAuditEventPage, 'total'> extends false ? true : false>;
type _UiIdRequired = _Assert<IsOptional<SecurityAuditEvent, 'id'> extends false ? true : false>;
type _UiEventTypeRequired = _Assert<IsOptional<SecurityAuditEvent, 'eventType'> extends false ? true : false>;
type _UiQueryPageOptional = _Assert<IsOptional<SecurityAuditListQuery, 'page'>>;
type _UiQueryPageSizeOptional = _Assert<IsOptional<SecurityAuditListQuery, 'pageSize'>>;
type _UiQueryEventTypeOptional = _Assert<IsOptional<SecurityAuditListQuery, 'eventType'>>;
type _UiQueryOutcomeOptional = _Assert<IsOptional<SecurityAuditListQuery, 'outcome'>>;

type _SchemaVersionWidened = _Assert<
  string extends NonNullable<SecurityAuditEvent['schemaVersion']> ? true : false
>;
type _OmitUiSchemaVersionMatches = _Assert<
  Omit<SecurityAuditEvent, 'schemaVersion'> extends SecurityAuditEvent ? true : false
>;
type _OmitGeneratedSchemaVersionDoesNotMatch = _Assert<
  Omit<OpenApiEvent, 'schema_version'> extends OpenApiEvent ? false : true
>;
type _OmitPageSize = _Assert<Omit<SecurityAuditEventPage, 'pageSize'> extends SecurityAuditEventPage ? false : true>;
type _OmitGeneratedPageSize = _Assert<Omit<OpenApiPage, 'page_size'> extends OpenApiPage ? false : true>;
type _OmitItems = _Assert<Omit<SecurityAuditEventPage, 'items'> extends SecurityAuditEventPage ? false : true>;

type _StringPhaseRejected = _Assert<string extends SecurityAuditPhase ? false : true>;
type _AttemptPhaseAssignable = _Assert<'attempt' extends SecurityAuditPhase ? true : false>;
type _CompletionPhaseAssignable = _Assert<'completion' extends SecurityAuditPhase ? true : false>;
type _StringOutcomeRejected = _Assert<string extends SecurityAuditOutcome ? false : true>;
type _SuccessOutcomeAssignable = _Assert<'success' extends SecurityAuditOutcome ? true : false>;
type _PendingOutcomeAssignable = _Assert<'pending' extends SecurityAuditOutcome ? true : false>;

type _GeneratedQueryAllowsEventTypeNull = _Assert<null extends OpenApiQuery['event_type'] ? true : false>;
type _GeneratedQueryAllowsOutcomeNull = _Assert<null extends OpenApiQuery['outcome'] ? true : false>;
type _CamelQueryAllowsEventTypeNull = _Assert<null extends CamelQuery['eventType'] ? true : false>;
type _UiQueryRejectsEventTypeNull = _Assert<null extends SecurityAuditListQuery['eventType'] ? false : true>;
type _UiQueryRejectsOutcomeNull = _Assert<null extends SecurityAuditListQuery['outcome'] ? false : true>;
type _UiQueryRejectsCorrelationIdNull = _Assert<
  null extends SecurityAuditListQuery['correlationId'] ? false : true
>;

type NarrowActor = {
  type: string;
  id: string;
};
type NarrowEvent = {
  id: number;
  eventType: string;
  phase: 'completion';
  actor: NarrowActor;
  executionId: string;
  action: string;
  target: NarrowActor;
  outcome: 'success';
  reasonCode: string;
  correlationId: string;
};
type FutureSchemaEvent = {
  id: number;
  schemaVersion: 'future-v2';
  eventType: string;
  phase: 'attempt';
  actor: NarrowActor;
  executionId: string;
  action: string;
  target: NarrowActor;
  outcome: 'denied';
  reasonCode: string;
  correlationId: string;
};
type NarrowPage = {
  items: NarrowEvent[];
  page: number;
  pageSize: number;
  total: number;
};
type NarrowQuery = {
  page: number;
  pageSize: number;
  eventType: string;
  outcome: 'success';
  correlationId: string;
  occurredFrom: string;
  occurredTo: string;
};

type _NarrowActorAssignable = _Assert<NarrowActor extends SecurityAuditActor ? true : false>;
type _NarrowTargetAssignable = _Assert<NarrowActor extends SecurityAuditTarget ? true : false>;
type _NarrowEventAssignable = _Assert<NarrowEvent extends SecurityAuditEvent ? true : false>;
type _FutureSchemaAssignable = _Assert<FutureSchemaEvent extends SecurityAuditEvent ? true : false>;
type _NarrowPageAssignable = _Assert<NarrowPage extends SecurityAuditEventPage ? true : false>;
type _NarrowQueryAssignable = _Assert<NarrowQuery extends SecurityAuditListQuery ? true : false>;

type MysteryPhaseEvent = {
  id: number;
  eventType: string;
  phase: string;
  actor: NarrowActor;
  executionId: string;
  action: string;
  target: NarrowActor;
  outcome: 'success';
  reasonCode: string;
  correlationId: string;
};
type MysteryOutcomeEvent = {
  id: number;
  eventType: string;
  phase: 'completion';
  actor: NarrowActor;
  executionId: string;
  action: string;
  target: NarrowActor;
  outcome: string;
  reasonCode: string;
  correlationId: string;
};
type _MysteryPhaseRejected = _Assert<MysteryPhaseEvent extends SecurityAuditEvent ? false : true>;
type _MysteryOutcomeRejected = _Assert<MysteryOutcomeEvent extends SecurityAuditEvent ? false : true>;

type SnakePage = {
  items: OpenApiEvent[];
  page: number;
  page_size: number;
  total: number;
};
type SnakeEvent = {
  id: number;
  schema_version: 'security-audit-v1';
  event_type: string;
  phase: 'completion';
  actor: OpenApiActor;
  execution_id: string;
  action: string;
  target: OpenApiTarget;
  outcome: 'success';
  reason_code: string;
  correlation_id: string;
};
type _SnakeEventMatchesGenerated = _Assert<SnakeEvent extends OpenApiEvent ? true : false>;
type _SnakeEventDoesNotMatchUi = _Assert<SnakeEvent extends SecurityAuditEvent ? false : true>;
type _SnakePageMatchesGenerated = _Assert<SnakePage extends OpenApiPage ? true : false>;
type _SnakePageDoesNotMatchUi = _Assert<SnakePage extends SecurityAuditEventPage ? false : true>;
type _UiPageIsNotGeneratedAlias = _Assert<SecurityAuditEventPage extends OpenApiPage ? false : true>;
type _GeneratedPageIsNotUi = _Assert<OpenApiPage extends SecurityAuditEventPage ? false : true>;
type _UiEventIsNotGeneratedAlias = _Assert<SecurityAuditEvent extends OpenApiEvent ? false : true>;

type _CompileTimePins = [
  _Get200IsPage,
  _PageIsGet200,
  _OpIsPath,
  _PathIsOp,
  _OpHasNeverRequestBody,
  _PathPostNever,
  _Get200IsNotEvent,
  _UiHasEventType,
  _UiHasExecutionId,
  _UiHasReasonCode,
  _UiHasCorrelationId,
  _UiHasSchemaVersion,
  _UiHasOccurredAt,
  _UiHasPageSize,
  _UiQueryHasPageSize,
  _UiQueryHasEventType,
  _UiQueryHasCorrelationId,
  _UiQueryHasOccurredFrom,
  _UiQueryHasOccurredTo,
  _UiLacksEventTypeSnake,
  _UiLacksExecutionIdSnake,
  _UiLacksReasonCodeSnake,
  _UiLacksCorrelationIdSnake,
  _UiLacksSchemaVersionSnake,
  _UiLacksOccurredAtSnake,
  _UiLacksPageSizeSnake,
  _UiQueryLacksPageSizeSnake,
  _UiQueryLacksEventTypeSnake,
  _UiQueryLacksCorrelationIdSnake,
  _UiQueryLacksOccurredFromSnake,
  _UiQueryLacksOccurredToSnake,
  _GeneratedHasEventTypeSnake,
  _GeneratedHasExecutionIdSnake,
  _GeneratedHasReasonCodeSnake,
  _GeneratedHasCorrelationIdSnake,
  _GeneratedHasSchemaVersionSnake,
  _GeneratedHasOccurredAtSnake,
  _GeneratedHasPageSizeSnake,
  _GeneratedQueryHasPageSizeSnake,
  _GeneratedQueryHasEventTypeSnake,
  _UiLacksEventTypeCamelOnGenerated,
  _UiLacksPageSizeCamelOnGenerated,
  _UiLacksSchemaVersionCamelOnGenerated,
  _UiSchemaVersionOptional,
  _GeneratedSchemaVersionRequired,
  _UiOccurredAtOptional,
  _GeneratedOccurredAtOptional,
  _UiMetadataOptional,
  _GeneratedMetadataOptional,
  _UiItemsRequired,
  _UiPageRequired,
  _UiPageSizeRequired,
  _UiTotalRequired,
  _UiIdRequired,
  _UiEventTypeRequired,
  _UiQueryPageOptional,
  _UiQueryPageSizeOptional,
  _UiQueryEventTypeOptional,
  _UiQueryOutcomeOptional,
  _SchemaVersionWidened,
  _OmitUiSchemaVersionMatches,
  _OmitGeneratedSchemaVersionDoesNotMatch,
  _OmitPageSize,
  _OmitGeneratedPageSize,
  _OmitItems,
  _StringPhaseRejected,
  _AttemptPhaseAssignable,
  _CompletionPhaseAssignable,
  _StringOutcomeRejected,
  _SuccessOutcomeAssignable,
  _PendingOutcomeAssignable,
  _GeneratedQueryAllowsEventTypeNull,
  _GeneratedQueryAllowsOutcomeNull,
  _CamelQueryAllowsEventTypeNull,
  _UiQueryRejectsEventTypeNull,
  _UiQueryRejectsOutcomeNull,
  _UiQueryRejectsCorrelationIdNull,
  _NarrowActorAssignable,
  _NarrowTargetAssignable,
  _NarrowEventAssignable,
  _FutureSchemaAssignable,
  _NarrowPageAssignable,
  _NarrowQueryAssignable,
  _MysteryPhaseRejected,
  _MysteryOutcomeRejected,
  _SnakeEventMatchesGenerated,
  _SnakeEventDoesNotMatchUi,
  _SnakePageMatchesGenerated,
  _SnakePageDoesNotMatchUi,
  _UiPageIsNotGeneratedAlias,
  _GeneratedPageIsNotUi,
  _UiEventIsNotGeneratedAlias,
];

describe('securityAudit OpenAPI type bind', () => {
  it('keeps SECURITY_AUDIT_MAX_PAGE_SIZE as the only enumerable runtime export', () => {
    expect(SECURITY_AUDIT_MAX_PAGE_SIZE).toBe(100);
    expect({ ...SecurityAudit }).toEqual({ SECURITY_AUDIT_MAX_PAGE_SIZE: 100 });
    expect(Object.keys(SecurityAudit)).toEqual(['SECURITY_AUDIT_MAX_PAGE_SIZE']);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path 200 JSON to the generated page component', () => {
    expectTypeOf<OpenApiGet200>().toEqualTypeOf<OpenApiPage>();
    expectTypeOf<OpenApiOp>().toEqualTypeOf<OpenApiPathGet>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof SecurityAuditEvent>().not.toMatchTypeOf<
      'event_type' | 'execution_id' | 'reason_code' | 'correlation_id' | 'schema_version' | 'occurred_at'
    >();
    expectTypeOf<keyof SecurityAuditEventPage>().not.toMatchTypeOf<'page_size'>();
    expectTypeOf<keyof SecurityAuditListQuery>().not.toMatchTypeOf<
      'page_size' | 'event_type' | 'correlation_id' | 'occurred_from' | 'occurred_to'
    >();

    type UiHasEventType = 'eventType' extends keyof SecurityAuditEvent ? true : false;
    type UiHasEventTypeSnake = 'event_type' extends keyof SecurityAuditEvent ? true : false;
    type GeneratedHasEventTypeSnake = 'event_type' extends keyof OpenApiEvent ? true : false;
    type UiHasPageSize = 'pageSize' extends keyof SecurityAuditEventPage ? true : false;
    type UiHasPageSizeSnake = 'page_size' extends keyof SecurityAuditEventPage ? true : false;
    type GeneratedHasPageSizeSnake = 'page_size' extends keyof OpenApiPage ? true : false;

    expectTypeOf<UiHasEventType>().toEqualTypeOf<true>();
    expectTypeOf<UiHasEventTypeSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasEventTypeSnake>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPageSize>().toEqualTypeOf<true>();
    expectTypeOf<UiHasPageSizeSnake>().toEqualTypeOf<false>();
    expectTypeOf<GeneratedHasPageSizeSnake>().toEqualTypeOf<true>();
  });

  it('keeps schemaVersion optional and widened versus the generated required constant', () => {
    expectTypeOf<Omit<SecurityAuditEvent, 'schemaVersion'>>().toMatchTypeOf<SecurityAuditEvent>();
    expectTypeOf<Omit<OpenApiEvent, 'schema_version'>>().not.toMatchTypeOf<OpenApiEvent>();
    expectTypeOf<string>().toMatchTypeOf<NonNullable<SecurityAuditEvent['schemaVersion']>>();
    expectTypeOf<Omit<SecurityAuditEventPage, 'pageSize'>>().not.toMatchTypeOf<SecurityAuditEventPage>();
  });

  it('rejects illegal enum widening on phase and outcome', () => {
    expectTypeOf({
      id: 1,
      eventType: 'auth.login',
      phase: 'mystery' as string,
      actor: { type: 'admin', id: 'local_admin' },
      executionId: 'exec-1',
      action: 'login',
      target: { type: 'session', id: 'web' },
      outcome: 'success' as const,
      reasonCode: 'authenticated',
      correlationId: 'corr',
    }).not.toMatchTypeOf<SecurityAuditEvent>();
    expectTypeOf({
      id: 1,
      eventType: 'auth.login',
      phase: 'completion' as const,
      actor: { type: 'admin', id: 'local_admin' },
      executionId: 'exec-1',
      action: 'login',
      target: { type: 'session', id: 'web' },
      outcome: 'mystery' as string,
      reasonCode: 'authenticated',
      correlationId: 'corr',
    }).not.toMatchTypeOf<SecurityAuditEvent>();
    expectTypeOf<string>().not.toMatchTypeOf<SecurityAuditPhase>();
    expectTypeOf<string>().not.toMatchTypeOf<SecurityAuditOutcome>();
    expectTypeOf<'attempt'>().toMatchTypeOf<SecurityAuditPhase>();
    expectTypeOf<'success'>().toMatchTypeOf<SecurityAuditOutcome>();
  });

  it('still accepts the narrow existing fixtures, including omitted schemaVersion', () => {
    const event: SecurityAuditEvent = {
      id: 7,
      eventType: 'auth.login',
      phase: 'completion',
      actor: { type: 'admin', id: 'local_admin' },
      executionId: 'exec-1',
      action: 'login',
      target: { type: 'session', id: 'web' },
      outcome: 'success',
      reasonCode: 'authenticated',
      correlationId: '0123456789abcdef0123456789abcdef',
    };
    const future: SecurityAuditEvent = {
      ...event,
      schemaVersion: 'future-v2',
    };
    const page: SecurityAuditEventPage = {
      items: [event, future],
      page: 2,
      pageSize: 25,
      total: 51,
    };
    const query: SecurityAuditListQuery = {
      page: 2,
      pageSize: 25,
      eventType: 'auth.login',
      outcome: 'success',
      correlationId: '0123456789abcdef0123456789abcdef',
      occurredFrom: '2026-07-01T00:00:00Z',
      occurredTo: '2026-07-24T23:59:59Z',
    };
    const OUTCOME_OPTIONS: Array<SecurityAuditOutcome | ''> = [
      '',
      'pending',
      'success',
      'denied',
      'failure',
      'accepted',
      'rejected',
    ];
    expectTypeOf(event).toMatchTypeOf<SecurityAuditEvent>();
    expectTypeOf(future).toMatchTypeOf<SecurityAuditEvent>();
    expectTypeOf(page).toMatchTypeOf<SecurityAuditEventPage>();
    expectTypeOf(query).toMatchTypeOf<SecurityAuditListQuery>();
    expectTypeOf(OUTCOME_OPTIONS).toMatchTypeOf<Array<SecurityAuditOutcome | ''>>();
  });

  it('does not re-export generated snake_case as the UI type', () => {
    const snakeEvent = {
      id: 7,
      schema_version: 'security-audit-v1' as const,
      event_type: 'auth.login',
      phase: 'completion' as const,
      actor: { type: 'admin', id: 'local_admin' },
      execution_id: 'exec-1',
      action: 'login',
      target: { type: 'session', id: 'web' },
      outcome: 'success' as const,
      reason_code: 'authenticated',
      correlation_id: 'corr',
    };
    const snakePage = {
      items: [] as OpenApiEvent[],
      page: 1,
      page_size: 25,
      total: 0,
    };
    expectTypeOf(snakeEvent).toMatchTypeOf<OpenApiEvent>();
    expectTypeOf(snakeEvent).not.toMatchTypeOf<SecurityAuditEvent>();
    expectTypeOf(snakePage).toMatchTypeOf<OpenApiPage>();
    expectTypeOf(snakePage).not.toMatchTypeOf<SecurityAuditEventPage>();
  });

  it('does not bind SecurityAuditListQuery from generated query nullability', () => {
    const nullQuery = {
      eventType: null,
      outcome: null,
    };
    expectTypeOf(nullQuery).not.toMatchTypeOf<SecurityAuditListQuery>();
    expectTypeOf<null>().toMatchTypeOf<OpenApiQuery['event_type']>();
    expectTypeOf<null>().not.toMatchTypeOf<SecurityAuditListQuery['eventType']>();
  });
});
