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
type OpenApiEnablePathPost = paths['/api/v1/scheduled-tasks/{task_id}/enable']['post'];
type OpenApiDisablePathPost = paths['/api/v1/scheduled-tasks/{task_id}/disable']['post'];
type OpenApiRunsPathGet = paths['/api/v1/scheduled-tasks/{task_id}/runs']['get'];
type OpenApiStatusPathGet = paths['/api/v1/scheduled-tasks/{task_id}/status']['get'];

type OpenApiListGet200 = OpenApiListOp['responses']['200']['content']['application/json'];
type OpenApiCreatePost201 = OpenApiCreateOp['responses']['201']['content']['application/json'];
type OpenApiCreateBody = OpenApiCreateOp['requestBody']['content']['application/json'];
type OpenApiTodayGet200 = OpenApiTodayOp['responses']['200']['content']['application/json'];
type OpenApiEnablePost200 = OpenApiEnableOp['responses']['200']['content']['application/json'];
type OpenApiDisablePost200 = OpenApiDisableOp['responses']['200']['content']['application/json'];
type OpenApiRunsGet200 = OpenApiRunsOp['responses']['200']['content']['application/json'];
type OpenApiStatusGet200 = OpenApiStatusOp['responses']['200']['content']['application/json'];

type _Assert<T extends true> = T;
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
type _ItemIsEnable200 = _Assert<OpenApiItem extends OpenApiEnablePost200 ? true : false>;
type _EnableOpIsPath = _Assert<OpenApiEnableOp extends OpenApiEnablePathPost ? true : false>;
type _PathIsEnableOp = _Assert<OpenApiEnablePathPost extends OpenApiEnableOp ? true : false>;
type _EnableNeverRequestBody = _Assert<OpenApiEnableOp extends { requestBody?: never } ? true : false>;
type _Disable200IsItem = _Assert<OpenApiDisablePost200 extends OpenApiItem ? true : false>;
type _ItemIsDisable200 = _Assert<OpenApiItem extends OpenApiDisablePost200 ? true : false>;
type _DisableOpIsPath = _Assert<OpenApiDisableOp extends OpenApiDisablePathPost ? true : false>;
type _PathIsDisableOp = _Assert<OpenApiDisablePathPost extends OpenApiDisableOp ? true : false>;
type _DisableNeverRequestBody = _Assert<OpenApiDisableOp extends { requestBody?: never } ? true : false>;
type _Runs200IsRunList = _Assert<OpenApiRunsGet200 extends OpenApiRunList ? true : false>;
type _RunListIsRuns200 = _Assert<OpenApiRunList extends OpenApiRunsGet200 ? true : false>;
type _RunsOpIsPath = _Assert<OpenApiRunsOp extends OpenApiRunsPathGet ? true : false>;
type _PathIsRunsOp = _Assert<OpenApiRunsPathGet extends OpenApiRunsOp ? true : false>;
type _RunsGetNeverRequestBody = _Assert<OpenApiRunsOp extends { requestBody?: never } ? true : false>;
type _Status200IsStatus = _Assert<OpenApiStatusGet200 extends OpenApiStatus ? true : false>;
type _StatusIsStatus200 = _Assert<OpenApiStatus extends OpenApiStatusGet200 ? true : false>;
type _StatusOpIsPath = _Assert<OpenApiStatusOp extends OpenApiStatusPathGet ? true : false>;
type _PathIsStatusOp = _Assert<OpenApiStatusPathGet extends OpenApiStatusOp ? true : false>;
type _StatusGetNeverRequestBody = _Assert<OpenApiStatusOp extends { requestBody?: never } ? true : false>;

type _OpenApiAnchors = [
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
  _ItemIsEnable200,
  _EnableOpIsPath,
  _PathIsEnableOp,
  _EnableNeverRequestBody,
  _Disable200IsItem,
  _ItemIsDisable200,
  _DisableOpIsPath,
  _PathIsDisableOp,
  _DisableNeverRequestBody,
  _Runs200IsRunList,
  _RunListIsRuns200,
  _RunsOpIsPath,
  _PathIsRunsOp,
  _RunsGetNeverRequestBody,
  _Status200IsStatus,
  _StatusIsStatus200,
  _StatusOpIsPath,
  _PathIsStatusOp,
  _StatusGetNeverRequestBody,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type ScheduledTaskSupportedType = OpenApiCreate['task_type'];
export type ScheduledTaskType = ScheduledTaskSupportedType | string;
export type ScheduledTaskReportType = OpenApiStockPayload['report_type'];
export type ScheduledTaskCalendarMarket = OpenApiSchedule['calendar_market'];
export type ScheduledTaskNonTradingDayPolicy = OpenApiSchedule['non_trading_day_policy'];
export type ScheduledTaskOccurrenceStatus = OpenApiTodayItem['status'];
export type ScheduledTaskRunStatus = OpenApiRun['status'];
export type ScheduledTaskCompatibility =
  OpenApiItem['compatibility'] | OpenApiUnsupported['compatibility'];

export type ScheduledTaskDailySchedule = CamelizeKeys<OpenApiSchedule>;

export type ScheduledTaskStockAnalysisPayload = Override<CamelizeKeys<OpenApiStockPayload>, {
  reportType?: ScheduledTaskReportType;
  notify?: boolean;
}>;

export type ScheduledTaskResearchPayload = Override<CamelizeKeys<OpenApiResearchPayload>, {
  notify?: boolean;
}>;

export type ScheduledTaskCreateRequest = Override<CamelizeKeys<OpenApiCreate>, {
  enabled?: boolean;
  maxAttempts?: number;
  schedule: ScheduledTaskDailySchedule;
  payload: ScheduledTaskStockAnalysisPayload | ScheduledTaskResearchPayload;
}>;

export type ScheduledTaskDefinitionSummary = Override<
  Omit<CamelizeKeys<OpenApiItem>, 'payload' | 'schedule'>,
  {
    compatibility: ScheduledTaskCompatibility;
    nextRunAt: string | null;
    taskType?: ScheduledTaskType;
    maxAttempts?: number;
  }
>;

export type ScheduledTaskListResponse = _BindOpenApiAnchors<Override<CamelizeKeys<OpenApiList>, {
  items: ScheduledTaskDefinitionSummary[];
}>>;

export type ScheduledTaskRunItem = Override<CamelizeKeys<OpenApiRun>, {
  executionTaskIds: string[];
  resultRefs: string[];
  errorCode: string | null;
  notificationStatus?: string | null;
}>;

export type ScheduledTaskRunSummary = Pick<ScheduledTaskRunItem, 'id' | 'status' | 'errorCode'>;

export type ScheduledTaskTodayItem = Override<CamelizeKeys<OpenApiTodayItem>, {
  task: ScheduledTaskDefinitionSummary;
  run: ScheduledTaskRunSummary | null;
  status: ScheduledTaskOccurrenceStatus;
}>;

export type ScheduledTaskTodayResponse = Override<CamelizeKeys<OpenApiToday>, {
  items: ScheduledTaskTodayItem[];
}>;

export type ScheduledTaskStatusResponse = Override<CamelizeKeys<OpenApiStatus>, {
  task: ScheduledTaskDefinitionSummary;
  latestRun: ScheduledTaskRunItem | null;
}>;

export type ScheduledTaskRunListResponse = Override<CamelizeKeys<OpenApiRunList>, {
  items: ScheduledTaskRunItem[];
}>;

export type ScheduledTaskListQuery = { enabled?: boolean; limit?: number };
export type ScheduledTaskTodayQuery = { timezone?: string };
export type ScheduledTaskRunListQuery = { limit?: number };
