// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as ScheduledTasks from '../scheduledTasks';
import type {
  ScheduledTaskCreateRequest,
  ScheduledTaskDefinitionSummary,
  ScheduledTaskListQuery,
  ScheduledTaskListResponse,
  ScheduledTaskResearchPayload,
  ScheduledTaskRunItem,
  ScheduledTaskRunListQuery,
  ScheduledTaskRunListResponse,
  ScheduledTaskStockAnalysisPayload,
  ScheduledTaskTodayItem,
  ScheduledTaskTodayQuery,
  ScheduledTaskTodayResponse,
} from '../scheduledTasks';

type OpenApiCreate = components['schemas']['ScheduledTaskCreateRequest'];
type OpenApiItem = components['schemas']['ScheduledTaskItem'];
type OpenApiUnsupported = components['schemas']['UnsupportedScheduledTaskItem'];
type OpenApiList = components['schemas']['ScheduledTaskListResponse'];
type OpenApiRun = components['schemas']['ScheduledTaskRunItem'];
type OpenApiRunList = components['schemas']['ScheduledTaskRunListResponse'];
type OpenApiStatus = components['schemas']['ScheduledTaskStatusResponse'];
type OpenApiTodayItem = components['schemas']['ScheduledTaskTodayItem'];
type OpenApiToday = components['schemas']['ScheduledTaskTodayResponse'];
type OpenApiSchedule = components['schemas']['DailyScheduleRequest'];
type OpenApiStockPayload = components['schemas']['StockAnalysisScheduledPayload'];
type OpenApiResearchPayload = components['schemas']['ResearchScheduledPayload'];

type OpenApiListOp = operations['list_scheduled_tasks_api_v1_scheduled_tasks_get'];
type OpenApiCreateOp = operations['create_scheduled_task_api_v1_scheduled_tasks_post'];
type OpenApiTodayOp = operations['list_today_scheduled_tasks_api_v1_scheduled_tasks_today_get'];
type OpenApiEnableOp = operations['enable_scheduled_task_api_v1_scheduled_tasks__task_id__enable_post'];
type OpenApiDisableOp = operations['disable_scheduled_task_api_v1_scheduled_tasks__task_id__disable_post'];
type OpenApiRunsOp = operations['list_scheduled_task_runs_api_v1_scheduled_tasks__task_id__runs_get'];
type OpenApiStatusOp = operations['get_scheduled_task_status_api_v1_scheduled_tasks__task_id__status_get'];

type OpenApiListPathGet = paths['/api/v1/scheduled-tasks']['get'];
type OpenApiCreatePathPost = paths['/api/v1/scheduled-tasks']['post'];
type OpenApiTodayPathGet = paths['/api/v1/scheduled-tasks/today']['get'];

type OpenApiListGet200 = OpenApiListOp['responses']['200']['content']['application/json'];
type OpenApiCreatePost201 = OpenApiCreateOp['responses']['201']['content']['application/json'];
type OpenApiCreateBody = OpenApiCreateOp['requestBody']['content']['application/json'];
type OpenApiTodayGet200 = OpenApiTodayOp['responses']['200']['content']['application/json'];
type OpenApiEnablePost200 = OpenApiEnableOp['responses']['200']['content']['application/json'];
type OpenApiDisablePost200 = OpenApiDisableOp['responses']['200']['content']['application/json'];
type OpenApiRunsGet200 = OpenApiRunsOp['responses']['200']['content']['application/json'];
type OpenApiStatusGet200 = OpenApiStatusOp['responses']['200']['content']['application/json'];
type OpenApiListQuery = NonNullable<OpenApiListOp['parameters']['query']>;

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

type _TwelveComponents = _Assert<
  (
    | 'ScheduledTaskCreateRequest'
    | 'ScheduledTaskItem'
    | 'UnsupportedScheduledTaskItem'
    | 'ScheduledTaskListResponse'
    | 'ScheduledTaskRunItem'
    | 'ScheduledTaskRunListResponse'
    | 'ScheduledTaskStatusResponse'
    | 'ScheduledTaskTodayItem'
    | 'ScheduledTaskTodayResponse'
    | 'DailyScheduleRequest'
    | 'StockAnalysisScheduledPayload'
    | 'ResearchScheduledPayload'
  ) extends keyof components['schemas'] ? true : false
>;

type _List200IsList = _Assert<OpenApiListGet200 extends OpenApiList ? true : false>;
type _ListIsList200 = _Assert<OpenApiList extends OpenApiListGet200 ? true : false>;
type _ListOpIsPath = _Assert<OpenApiListOp extends OpenApiListPathGet ? true : false>;
type _PathIsListOp = _Assert<OpenApiListPathGet extends OpenApiListOp ? true : false>;
type _ListGetNeverRequestBody = _Assert<OpenApiListOp extends { requestBody?: never } ? true : false>;
type _Create201IsItem = _Assert<OpenApiCreatePost201 extends OpenApiItem ? true : false>;
type _ItemIsCreate201 = _Assert<OpenApiItem extends OpenApiCreatePost201 ? true : false>;
type _CreateOpIsPath = _Assert<OpenApiCreateOp extends OpenApiCreatePathPost ? true : false>;
type _PathIsCreateOp = _Assert<OpenApiCreatePathPost extends OpenApiCreateOp ? true : false>;
type _CreateBodyIsRequest = _Assert<OpenApiCreateBody extends OpenApiCreate ? true : false>;
type _RequestIsCreateBody = _Assert<OpenApiCreate extends OpenApiCreateBody ? true : false>;
type _Today200IsToday = _Assert<OpenApiTodayGet200 extends OpenApiToday ? true : false>;
type _TodayIsToday200 = _Assert<OpenApiToday extends OpenApiTodayGet200 ? true : false>;
type _TodayOpIsPath = _Assert<OpenApiTodayOp extends OpenApiTodayPathGet ? true : false>;
type _PathIsTodayOp = _Assert<OpenApiTodayPathGet extends OpenApiTodayOp ? true : false>;
type _TodayGetNeverRequestBody = _Assert<OpenApiTodayOp extends { requestBody?: never } ? true : false>;
type _Enable200IsItem = _Assert<OpenApiEnablePost200 extends OpenApiItem ? true : false>;
type _Disable200IsItem = _Assert<OpenApiDisablePost200 extends OpenApiItem ? true : false>;
type _EnableNeverRequestBody = _Assert<OpenApiEnableOp extends { requestBody?: never } ? true : false>;
type _DisableNeverRequestBody = _Assert<OpenApiDisableOp extends { requestBody?: never } ? true : false>;
type _Runs200IsRunList = _Assert<OpenApiRunsGet200 extends OpenApiRunList ? true : false>;
type _RunListIsRuns200 = _Assert<OpenApiRunList extends OpenApiRunsGet200 ? true : false>;
type _RunsGetNeverRequestBody = _Assert<OpenApiRunsOp extends { requestBody?: never } ? true : false>;
type _Status200IsStatus = _Assert<OpenApiStatusGet200 extends OpenApiStatus ? true : false>;
type _StatusIsStatus200 = _Assert<OpenApiStatus extends OpenApiStatusGet200 ? true : false>;
type _StatusGetNeverRequestBody = _Assert<OpenApiStatusOp extends { requestBody?: never } ? true : false>;

type _UiHasSchemaVersion = _Assert<'schemaVersion' extends keyof ScheduledTaskCreateRequest ? true : false>;
type _UiHasTaskType = _Assert<'taskType' extends keyof ScheduledTaskCreateRequest ? true : false>;
type _UiHasMaxAttempts = _Assert<'maxAttempts' extends keyof ScheduledTaskDefinitionSummary ? true : false>;
type _UiHasStockCode = _Assert<'stockCode' extends keyof ScheduledTaskResearchPayload ? true : false>;
type _UiHasCalendarMarket = _Assert<'calendarMarket' extends keyof ScheduledTaskCreateRequest['schedule'] ? true : false>;
type _UiLacksSchemaVersionSnake = _Assert<'schema_version' extends keyof ScheduledTaskCreateRequest ? false : true>;
type _UiLacksTaskTypeSnake = _Assert<'task_type' extends keyof ScheduledTaskCreateRequest ? false : true>;
type _UiLacksMaxAttemptsSnake = _Assert<'max_attempts' extends keyof ScheduledTaskDefinitionSummary ? false : true>;
type _UiLacksStockCodeSnake = _Assert<'stock_code' extends keyof ScheduledTaskResearchPayload ? false : true>;
type _UiLacksCalendarMarketSnake = _Assert<'calendar_market' extends keyof ScheduledTaskCreateRequest['schedule'] ? false : true>;
type _GeneratedHasSchemaVersionSnake = _Assert<'schema_version' extends keyof OpenApiCreate ? true : false>;
type _GeneratedHasTaskTypeSnake = _Assert<'task_type' extends keyof OpenApiCreate ? true : false>;
type _GeneratedHasMaxAttemptsSnake = _Assert<'max_attempts' extends keyof OpenApiItem ? true : false>;
type _GeneratedHasStockCodeSnake = _Assert<'stock_code' extends keyof OpenApiResearchPayload ? true : false>;
type _GeneratedHasReportTypeSnake = _Assert<'report_type' extends keyof OpenApiStockPayload ? true : false>;
type _GeneratedHasCalendarMarketSnake = _Assert<'calendar_market' extends keyof OpenApiSchedule ? true : false>;
type _GeneratedLacksSchemaVersionCamel = _Assert<'schemaVersion' extends keyof OpenApiCreate ? false : true>;
type _GeneratedLacksTaskTypeCamel = _Assert<'taskType' extends keyof OpenApiCreate ? false : true>;
type _GeneratedLacksMaxAttemptsCamel = _Assert<'maxAttempts' extends keyof OpenApiItem ? false : true>;
type _GeneratedLacksStockCodeCamel = _Assert<'stockCode' extends keyof OpenApiResearchPayload ? false : true>;
type _GeneratedLacksReportTypeCamel = _Assert<'reportType' extends keyof OpenApiStockPayload ? false : true>;
type _GeneratedLacksCalendarMarketCamel = _Assert<'calendarMarket' extends keyof OpenApiSchedule ? false : true>;

type _UiSummaryLacksPayload = _Assert<'payload' extends keyof ScheduledTaskDefinitionSummary ? false : true>;
type _UiSummaryLacksSchedule = _Assert<'schedule' extends keyof ScheduledTaskDefinitionSummary ? false : true>;
type _NaiveItemHasPayload = _Assert<'payload' extends keyof CamelizeKeys<OpenApiItem> ? true : false>;
type _NaiveItemHasSchedule = _Assert<'schedule' extends keyof CamelizeKeys<OpenApiItem> ? true : false>;

type _UiListItemsRequired = _Assert<IsOptional<ScheduledTaskListResponse, 'items'> extends false ? true : false>;
type _UiTodayItemsRequired = _Assert<IsOptional<ScheduledTaskTodayResponse, 'items'> extends false ? true : false>;
type _UiRunListItemsRequired = _Assert<IsOptional<ScheduledTaskRunListResponse, 'items'> extends false ? true : false>;
type _GeneratedListItemsOptional = _Assert<IsOptional<OpenApiList, 'items'>>;
type _GeneratedTodayItemsOptional = _Assert<IsOptional<OpenApiToday, 'items'>>;
type _GeneratedRunListItemsOptional = _Assert<IsOptional<OpenApiRunList, 'items'>>;
type _NaiveListItemsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiList>, 'items'>>;

type _UiEnabledOptional = _Assert<IsOptional<ScheduledTaskCreateRequest, 'enabled'>>;
type _UiMaxAttemptsOptional = _Assert<IsOptional<ScheduledTaskCreateRequest, 'maxAttempts'>>;
type _UiNotifyOptional = _Assert<IsOptional<ScheduledTaskResearchPayload, 'notify'>>;
type _UiReportTypeOptional = _Assert<IsOptional<ScheduledTaskStockAnalysisPayload, 'reportType'>>;
type _NaiveEnabledRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiCreate>, 'enabled'> extends false ? true : false
>;
type _NaiveMaxAttemptsRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiCreate>, 'maxAttempts'> extends false ? true : false
>;

type _UiNextRunAtRequired = _Assert<
  IsOptional<ScheduledTaskDefinitionSummary, 'nextRunAt'> extends false ? true : false
>;
type _UiRunRequired = _Assert<IsOptional<ScheduledTaskTodayItem, 'run'> extends false ? true : false>;
type _UiErrorCodeRequired = _Assert<IsOptional<ScheduledTaskRunItem, 'errorCode'> extends false ? true : false>;
type _UiExecutionIdsRequired = _Assert<
  IsOptional<ScheduledTaskRunItem, 'executionTaskIds'> extends false ? true : false
>;
type _UiResultRefsRequired = _Assert<IsOptional<ScheduledTaskRunItem, 'resultRefs'> extends false ? true : false>;
type _GeneratedNextRunAtOptional = _Assert<IsOptional<OpenApiItem, 'next_run_at'>>;
type _GeneratedRunOptional = _Assert<IsOptional<OpenApiTodayItem, 'run'>>;
type _GeneratedErrorCodeOptional = _Assert<IsOptional<OpenApiRun, 'error_code'>>;
type _GeneratedExecutionIdsOptional = _Assert<IsOptional<OpenApiRun, 'execution_task_ids'>>;
type _GeneratedResultRefsOptional = _Assert<IsOptional<OpenApiRun, 'result_refs'>>;

type _QueryEnabledNoNull = _Assert<null extends ScheduledTaskListQuery['enabled'] ? false : true>;
type _GeneratedQueryEnabledNull = _Assert<null extends OpenApiListQuery['enabled'] ? true : false>;
type _TodayQueryHandwritten = _Assert<ScheduledTaskTodayQuery extends { timezone?: string } ? true : false>;
type _RunListQueryHandwritten = _Assert<ScheduledTaskRunListQuery extends { limit?: number } ? true : false>;

type HomeTodayLiteral = {
  task: {
    compatibility: 'supported';
    id: string;
    schemaVersion: number;
    name: string;
    taskType: 'risk_check';
    enabled: true;
    nextRunAt: string;
    createdAt: string;
    updatedAt: string;
  };
  scheduledFor: string;
  status: 'retry_wait';
  run: null;
};
type _HomeTodayAssignable = _Assert<HomeTodayLiteral extends ScheduledTaskTodayItem ? true : false>;
type _HomeSummaryAssignable = _Assert<
  HomeTodayLiteral['task'] extends ScheduledTaskDefinitionSummary ? true : false
>;
type _NaiveHomeTodayRejected = _Assert<HomeTodayLiteral extends CamelizeKeys<OpenApiTodayItem> ? false : true>;

type ResearchCreateLiteral = {
  schemaVersion: 2;
  name: string;
  taskType: 'risk_check';
  schedule: {
    kind: 'daily';
    time: string;
    timezone: string;
    calendarMarket: 'us';
    nonTradingDayPolicy: 'skip';
  };
  payload: { stockCode: string; notify: true };
};
type _ResearchCreateAssignable = _Assert<ResearchCreateLiteral extends ScheduledTaskCreateRequest ? true : false>;
type _NaiveCreateRejected = _Assert<ResearchCreateLiteral extends CamelizeKeys<OpenApiCreate> ? false : true>;

type CreateMissingNotify = {
  schemaVersion: 1;
  name: string;
  taskType: 'stock_analysis';
  schedule: ResearchCreateLiteral['schedule'];
  payload: { stockCode: string };
};
type _MissingNotifyAssignable = _Assert<CreateMissingNotify extends ScheduledTaskCreateRequest ? true : false>;

type PartialFailureRun = {
  id: string;
  taskId: string;
  scheduledFor: string;
  status: 'failed';
  attemptCount: number;
  dispatchFailureCount: number;
  executionTaskIds: string[];
  resultRefs: string[];
  notificationStatus: 'partial_failure';
  errorCode: null;
  createdAt: string;
  updatedAt: string;
};
type _PartialFailureAssignable = _Assert<PartialFailureRun extends ScheduledTaskRunItem ? true : false>;
type _NaivePartialFailureRejected = _Assert<
  PartialFailureRun extends CamelizeKeys<OpenApiRun> ? false : true
>;

type _UnsupportedCompatibility = _Assert<
  'unsupported_schema' extends ScheduledTasks.ScheduledTaskCompatibility ? true : false
>;
type _UnsupportedExists = _Assert<'UnsupportedScheduledTaskItem' extends keyof components['schemas'] ? true : false>;
type _VoidUnsupported = _Assert<OpenApiUnsupported extends { compatibility: 'unsupported_schema' } ? true : false>;

type _CompileTimePins = [
  _TwelveComponents,
  _List200IsList,
  _ListIsList200,
  _ListOpIsPath,
  _PathIsListOp,
  _ListGetNeverRequestBody,
  _Create201IsItem,
  _ItemIsCreate201,
  _CreateOpIsPath,
  _PathIsCreateOp,
  _CreateBodyIsRequest,
  _RequestIsCreateBody,
  _Today200IsToday,
  _TodayIsToday200,
  _TodayOpIsPath,
  _PathIsTodayOp,
  _TodayGetNeverRequestBody,
  _Enable200IsItem,
  _Disable200IsItem,
  _EnableNeverRequestBody,
  _DisableNeverRequestBody,
  _Runs200IsRunList,
  _RunListIsRuns200,
  _RunsGetNeverRequestBody,
  _Status200IsStatus,
  _StatusIsStatus200,
  _StatusGetNeverRequestBody,
  _UiHasSchemaVersion,
  _UiHasTaskType,
  _UiHasMaxAttempts,
  _UiHasStockCode,
  _UiHasCalendarMarket,
  _UiLacksSchemaVersionSnake,
  _UiLacksTaskTypeSnake,
  _UiLacksMaxAttemptsSnake,
  _UiLacksStockCodeSnake,
  _UiLacksCalendarMarketSnake,
  _GeneratedHasSchemaVersionSnake,
  _GeneratedHasTaskTypeSnake,
  _GeneratedHasMaxAttemptsSnake,
  _GeneratedHasStockCodeSnake,
  _GeneratedHasReportTypeSnake,
  _GeneratedHasCalendarMarketSnake,
  _GeneratedLacksSchemaVersionCamel,
  _GeneratedLacksTaskTypeCamel,
  _GeneratedLacksMaxAttemptsCamel,
  _GeneratedLacksStockCodeCamel,
  _GeneratedLacksReportTypeCamel,
  _GeneratedLacksCalendarMarketCamel,
  _UiSummaryLacksPayload,
  _UiSummaryLacksSchedule,
  _NaiveItemHasPayload,
  _NaiveItemHasSchedule,
  _UiListItemsRequired,
  _UiTodayItemsRequired,
  _UiRunListItemsRequired,
  _GeneratedListItemsOptional,
  _GeneratedTodayItemsOptional,
  _GeneratedRunListItemsOptional,
  _NaiveListItemsOptional,
  _UiEnabledOptional,
  _UiMaxAttemptsOptional,
  _UiNotifyOptional,
  _UiReportTypeOptional,
  _NaiveEnabledRequired,
  _NaiveMaxAttemptsRequired,
  _UiNextRunAtRequired,
  _UiRunRequired,
  _UiErrorCodeRequired,
  _UiExecutionIdsRequired,
  _UiResultRefsRequired,
  _GeneratedNextRunAtOptional,
  _GeneratedRunOptional,
  _GeneratedErrorCodeOptional,
  _GeneratedExecutionIdsOptional,
  _GeneratedResultRefsOptional,
  _QueryEnabledNoNull,
  _GeneratedQueryEnabledNull,
  _TodayQueryHandwritten,
  _RunListQueryHandwritten,
  _HomeTodayAssignable,
  _HomeSummaryAssignable,
  _NaiveHomeTodayRejected,
  _ResearchCreateAssignable,
  _NaiveCreateRejected,
  _MissingNotifyAssignable,
  _PartialFailureAssignable,
  _NaivePartialFailureRejected,
  _UnsupportedCompatibility,
  _UnsupportedExists,
  _VoidUnsupported,
];

const createBase = {
  schemaVersion: 2 as const,
  name: 'AAPL downside review',
  taskType: 'risk_check' as const,
  schedule: {
    kind: 'daily' as const,
    time: '09:30',
    timezone: 'America/New_York',
    calendarMarket: 'us' as const,
    nonTradingDayPolicy: 'skip' as const,
  },
  payload: {
    stockCode: 'AAPL',
    notify: true,
  },
};

const extraCreate: ScheduledTaskCreateRequest = {
  schemaVersion: 2,
  name: 'AAPL downside review',
  taskType: 'risk_check',
  schedule: createBase.schedule,
  payload: createBase.payload,
  // @ts-expect-error futurePolicy is not a public create field
  futurePolicy: true,
};

const extraPayload: ScheduledTaskCreateRequest = {
  ...createBase,
  // @ts-expect-error futurePayloadFlag is not a public payload field
  payload: { stockCode: 'AAPL', notify: true, futurePayloadFlag: true },
};

void extraCreate;
void extraPayload;

describe('scheduledTasks OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...ScheduledTasks }).toEqual({});
    expect(Object.keys(ScheduledTasks)).toEqual([]);
    expect(Object.getOwnPropertyNames(ScheduledTasks)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path 200/201 JSON to the named components and keeps GET requestBody never', () => {
    expectTypeOf<OpenApiListGet200>().toEqualTypeOf<OpenApiList>();
    expectTypeOf<OpenApiCreatePost201>().toEqualTypeOf<OpenApiItem>();
    expectTypeOf<OpenApiCreateBody>().toEqualTypeOf<OpenApiCreate>();
    expectTypeOf<OpenApiTodayGet200>().toEqualTypeOf<OpenApiToday>();
    expectTypeOf<OpenApiEnablePost200>().toEqualTypeOf<OpenApiItem>();
    expectTypeOf<OpenApiDisablePost200>().toEqualTypeOf<OpenApiItem>();
    expectTypeOf<OpenApiRunsGet200>().toEqualTypeOf<OpenApiRunList>();
    expectTypeOf<OpenApiStatusGet200>().toEqualTypeOf<OpenApiStatus>();
    expectTypeOf<OpenApiListOp>().toEqualTypeOf<OpenApiListPathGet>();
    expectTypeOf<OpenApiCreateOp>().toEqualTypeOf<OpenApiCreatePathPost>();
    expectTypeOf<OpenApiTodayOp>().toEqualTypeOf<OpenApiTodayPathGet>();
    type ListNeverBody = OpenApiListOp extends { requestBody?: never } ? true : false;
    type TodayNeverBody = OpenApiTodayOp extends { requestBody?: never } ? true : false;
    type EnableNeverBody = OpenApiEnableOp extends { requestBody?: never } ? true : false;
    type DisableNeverBody = OpenApiDisableOp extends { requestBody?: never } ? true : false;
    expectTypeOf<ListNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<TodayNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<EnableNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<DisableNeverBody>().toEqualTypeOf<true>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof ScheduledTaskCreateRequest>().not.toMatchTypeOf<
      'schema_version' | 'task_type' | 'max_attempts'
    >();
    expectTypeOf<keyof ScheduledTaskResearchPayload>().not.toMatchTypeOf<'stock_code'>();
    expectTypeOf<keyof ScheduledTaskCreateRequest['schedule']>().not.toMatchTypeOf<'calendar_market'>();
    expectTypeOf<keyof OpenApiCreate>().not.toMatchTypeOf<'schemaVersion' | 'taskType' | 'maxAttempts'>();
    expectTypeOf<keyof OpenApiResearchPayload>().not.toMatchTypeOf<'stockCode'>();
    expectTypeOf<keyof OpenApiSchedule>().not.toMatchTypeOf<'calendarMarket'>();
  });

  it('omits payload and schedule from the public summary while naive CamelizeKeys keeps them', () => {
    type UiHasPayload = 'payload' extends keyof ScheduledTaskDefinitionSummary ? true : false;
    type UiHasSchedule = 'schedule' extends keyof ScheduledTaskDefinitionSummary ? true : false;
    type NaiveHasPayload = 'payload' extends keyof CamelizeKeys<OpenApiItem> ? true : false;
    type NaiveHasSchedule = 'schedule' extends keyof CamelizeKeys<OpenApiItem> ? true : false;
    expectTypeOf<UiHasPayload>().toEqualTypeOf<false>();
    expectTypeOf<UiHasSchedule>().toEqualTypeOf<false>();
    expectTypeOf<NaiveHasPayload>().toEqualTypeOf<true>();
    expectTypeOf<NaiveHasSchedule>().toEqualTypeOf<true>();
  });

  it('keeps UI collection items required while generated counterparts stay optional', () => {
    expectTypeOf<Omit<ScheduledTaskListResponse, 'items'>>().not.toMatchTypeOf<ScheduledTaskListResponse>();
    expectTypeOf<Omit<OpenApiList, 'items'>>().toMatchTypeOf<OpenApiList>();
    expectTypeOf<Omit<ScheduledTaskTodayResponse, 'items'>>().not.toMatchTypeOf<ScheduledTaskTodayResponse>();
    expectTypeOf<Omit<OpenApiToday, 'items'>>().toMatchTypeOf<OpenApiToday>();
    expectTypeOf<Omit<ScheduledTaskRunListResponse, 'items'>>().not.toMatchTypeOf<ScheduledTaskRunListResponse>();
    expectTypeOf<Omit<OpenApiRunList, 'items'>>().toMatchTypeOf<OpenApiRunList>();
  });

  it('keeps create enabled, maxAttempts, and payload notify/reportType optional', () => {
    type UiEnabledOptional = IsOptional<ScheduledTaskCreateRequest, 'enabled'>;
    type UiMaxAttemptsOptional = IsOptional<ScheduledTaskCreateRequest, 'maxAttempts'>;
    type NaiveEnabledOptional = IsOptional<CamelizeKeys<OpenApiCreate>, 'enabled'>;
    type NaiveMaxAttemptsOptional = IsOptional<CamelizeKeys<OpenApiCreate>, 'maxAttempts'>;
    expectTypeOf<UiEnabledOptional>().toEqualTypeOf<true>();
    expectTypeOf<UiMaxAttemptsOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaiveEnabledOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveMaxAttemptsOptional>().toEqualTypeOf<false>();
    expectTypeOf(createBase).toMatchTypeOf<ScheduledTaskCreateRequest>();
    expectTypeOf(createBase).not.toMatchTypeOf<CamelizeKeys<OpenApiCreate>>();
    expectTypeOf({ stockCode: 'AAPL' }).toMatchTypeOf<ScheduledTaskStockAnalysisPayload>();
    expectTypeOf({ stockCode: 'AAPL' }).toMatchTypeOf<ScheduledTaskResearchPayload>();
  });

  it('accepts notificationStatus partial_failure on the UI run item and rejects it on naive CamelizeKeys', () => {
    const run = {
      id: 'run-failed',
      taskId: 'task-1',
      scheduledFor: '2026-07-26T20:30:00Z',
      status: 'failed' as const,
      attemptCount: 3,
      dispatchFailureCount: 2,
      executionTaskIds: ['execution-failed'],
      resultRefs: [] as string[],
      notificationStatus: 'partial_failure',
      errorCode: null,
      createdAt: '2026-07-26T20:30:00Z',
      updatedAt: '2026-07-26T20:31:00Z',
    };
    expectTypeOf(run).toMatchTypeOf<ScheduledTaskRunItem>();
    expectTypeOf(run).not.toMatchTypeOf<CamelizeKeys<OpenApiRun>>();
  });

  it('keeps handwritten query bags distinct from generated nullable enabled', () => {
    expectTypeOf<ScheduledTaskListQuery>().toEqualTypeOf<{ enabled?: boolean; limit?: number }>();
    expectTypeOf<null>().not.toMatchTypeOf<ScheduledTaskListQuery['enabled']>();
    expectTypeOf<null>().toMatchTypeOf<OpenApiListQuery['enabled']>();
    expectTypeOf<ScheduledTaskTodayQuery>().toEqualTypeOf<{ timezone?: string }>();
    expectTypeOf<ScheduledTaskRunListQuery>().toEqualTypeOf<{ limit?: number }>();
  });

  it('accepts Home today and research create fixtures without payload, schedule, or generated defaults', () => {
    const homeToday = {
      task: {
        compatibility: 'supported' as const,
        id: 'scheduled-risk-1',
        schemaVersion: 2,
        name: 'AAPL downside review',
        taskType: 'risk_check' as const,
        enabled: true,
        nextRunAt: '2026-07-25T10:00:00Z',
        createdAt: '2026-07-24T20:00:00Z',
        updatedAt: '2026-07-24T20:00:00Z',
      },
      scheduledFor: '2026-07-25T10:00:00Z',
      status: 'retry_wait' as const,
      run: null,
    };
    expectTypeOf(homeToday).toMatchTypeOf<ScheduledTaskTodayItem>();
    expectTypeOf(homeToday.task).toMatchTypeOf<ScheduledTaskDefinitionSummary>();
    expectTypeOf({
      schemaVersion: 1 as const,
      name: 'broken',
      taskType: 'stock_analysis' as const,
      schedule: createBase.schedule,
      payload: { stockCode: 'AAPL' },
    }).toMatchTypeOf<ScheduledTaskCreateRequest>();
  });
});
