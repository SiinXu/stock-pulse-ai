import { z } from 'zod';
import type {
  ScheduledTaskCreateRequest,
  ScheduledTaskDefinitionSummary,
  ScheduledTaskListQuery,
  ScheduledTaskListResponse,
  ScheduledTaskRunListQuery,
  ScheduledTaskRunListResponse,
  ScheduledTaskStatusResponse,
  ScheduledTaskTodayQuery,
  ScheduledTaskTodayResponse,
} from '../types/scheduledTasks';
// Generated OpenAPI components document the backend snake_case contract for
// scheduled-task list/today/create/status/runs responses.
import type { components } from '../types/api.generated';
import apiClient from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';

type OpenApiScheduledTaskListResponse = components['schemas']['ScheduledTaskListResponse'];
type OpenApiScheduledTaskTodayResponse = components['schemas']['ScheduledTaskTodayResponse'];
type OpenApiScheduledTaskItem = components['schemas']['ScheduledTaskItem'];
type OpenApiScheduledTaskRunItem = components['schemas']['ScheduledTaskRunItem'];
type OpenApiScheduledTaskStatusResponse = components['schemas']['ScheduledTaskStatusResponse'];
type OpenApiScheduledTaskRunListResponse = components['schemas']['ScheduledTaskRunListResponse'];

type _AssertListFields = keyof OpenApiScheduledTaskListResponse;
type _AssertTodayFields = keyof OpenApiScheduledTaskTodayResponse;
type _AssertItemFields = keyof OpenApiScheduledTaskItem;
type _AssertRunFields = keyof OpenApiScheduledTaskRunItem;
type _AssertStatusFields = keyof OpenApiScheduledTaskStatusResponse;
type _AssertRunListFields = keyof OpenApiScheduledTaskRunListResponse;
const _listFieldAnchor: _AssertListFields = 'total';
const _todayFieldAnchor: _AssertTodayFields = 'generated_at';
const _itemFieldAnchor: _AssertItemFields = 'schema_version';
const _runFieldAnchor: _AssertRunFields = 'task_id';
const _statusFieldAnchor: _AssertStatusFields = 'task';
const _runListFieldAnchor: _AssertRunListFields = 'total';
void _listFieldAnchor;
void _todayFieldAnchor;
void _itemFieldAnchor;
void _runFieldAnchor;
void _statusFieldAnchor;
void _runListFieldAnchor;

/**
 * Zod schemas mirror the camelCase view of OpenAPI scheduled-task schemas.
 * On success we return the pre-validated toCamelCase object (not schema output) so
 * valid payloads remain byte-identical to the previous unchecked cast path.
 */
const scheduledPayloadSchema = z.object({
  stockCode: z.string(),
  reportType: z.string().optional(),
  notify: z.boolean().optional(),
}).passthrough();

const scheduledScheduleSchema = z.object({
  kind: z.literal('daily'),
  time: z.string(),
  timezone: z.string(),
  calendarMarket: z.string(),
  nonTradingDayPolicy: z.string(),
}).passthrough();

const supportedTaskItemSchema = z.object({
  compatibility: z.literal('supported'),
  id: z.string(),
  schemaVersion: z.number(),
  name: z.string(),
  taskType: z.string(),
  enabled: z.boolean(),
  nextRunAt: z.string().nullable().optional(),
  createdAt: z.string(),
  updatedAt: z.string(),
  maxAttempts: z.number(),
  payload: scheduledPayloadSchema,
  schedule: scheduledScheduleSchema,
}).passthrough();

const unsupportedTaskItemSchema = z.object({
  compatibility: z.literal('unsupported_schema'),
  id: z.string(),
  schemaVersion: z.number(),
  name: z.string(),
  enabled: z.boolean(),
  nextRunAt: z.string().nullable().optional(),
  createdAt: z.string(),
  updatedAt: z.string(),
}).passthrough();

const definitionSummarySchema = z.union([supportedTaskItemSchema, unsupportedTaskItemSchema]);

const scheduledTaskRunItemSchema = z.object({
  id: z.string(),
  taskId: z.string(),
  scheduledFor: z.string(),
  status: z.string(),
  attemptCount: z.number(),
  dispatchFailureCount: z.number(),
  executionTaskIds: z.array(z.string()).optional(),
  resultRefs: z.array(z.string()).optional(),
  notificationStatus: z.string().nullable().optional(),
  notificationChannels: z.array(z.string()).optional(),
  notificationFailedChannels: z.array(z.string()).optional(),
  errorCode: z.string().nullable().optional(),
  nextAttemptAt: z.string().nullable().optional(),
  startedAt: z.string().nullable().optional(),
  finishedAt: z.string().nullable().optional(),
  createdAt: z.string(),
  updatedAt: z.string(),
}).passthrough();

const scheduledTaskListResponseSchema = z.object({
  total: z.number(),
  items: z.array(definitionSummarySchema).optional(),
}).passthrough();

const scheduledTaskTodayItemSchema = z.object({
  task: definitionSummarySchema,
  scheduledFor: z.string(),
  status: z.string(),
  run: scheduledTaskRunItemSchema.nullable().optional(),
}).passthrough();

const scheduledTaskTodayResponseSchema = z.object({
  date: z.string(),
  timezone: z.string(),
  generatedAt: z.string(),
  total: z.number(),
  items: z.array(scheduledTaskTodayItemSchema).optional(),
}).passthrough();

const scheduledTaskStatusResponseSchema = z.object({
  task: definitionSummarySchema,
  latestRun: scheduledTaskRunItemSchema.nullable().optional(),
}).passthrough();

const scheduledTaskRunListResponseSchema = z.object({
  total: z.number(),
  items: z.array(scheduledTaskRunItemSchema).optional(),
}).passthrough();

function parseCamelCasePayload<T>(
  data: unknown,
  schema: z.ZodTypeAny,
  label: string,
): T {
  const camel = toCamelCase<unknown>(data);
  const result = schema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    if (import.meta.env.DEV) {
      console.error(`[scheduledTasks] response validation failed (${label})`, result.error.issues);
    }
    throw createApiError(
      createParsedApiError({
        title: '响应校验失败',
        message: `接口响应未通过校验（${label}）。${issueSummary}`,
        rawMessage: result.error.message,
        category: 'unknown',
        code: 'api_response_validation_failed',
        params: { label, issues: issueSummary },
        details: result.error.issues,
      }),
    );
  }
  return camel as T;
}

function toSnakeCreatePayload(payload: ScheduledTaskCreateRequest): Record<string, unknown> {
  const requestPayload: Record<string, unknown> = {
    stock_code: payload.payload.stockCode,
  };
  if ('reportType' in payload.payload && payload.payload.reportType !== undefined) {
    requestPayload.report_type = payload.payload.reportType;
  }
  if (payload.payload.notify !== undefined) {
    requestPayload.notify = payload.payload.notify;
  }

  const body: Record<string, unknown> = {
    schema_version: payload.schemaVersion,
    name: payload.name,
    task_type: payload.taskType,
    schedule: {
      kind: payload.schedule.kind,
      time: payload.schedule.time,
      timezone: payload.schedule.timezone,
      calendar_market: payload.schedule.calendarMarket,
      non_trading_day_policy: payload.schedule.nonTradingDayPolicy,
    },
    payload: requestPayload,
  };
  if (payload.enabled !== undefined) {
    body.enabled = payload.enabled;
  }
  if (payload.maxAttempts !== undefined) {
    body.max_attempts = payload.maxAttempts;
  }
  return body;
}

export const scheduledTasksApi = {
  async list(
    query: ScheduledTaskListQuery = {},
  ): Promise<ScheduledTaskListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/scheduled-tasks',
      {
        params: {
          ...(query.enabled === undefined ? {} : { enabled: query.enabled }),
          ...(query.limit === undefined ? {} : { limit: query.limit }),
        },
      },
    );
    return parseCamelCasePayload<ScheduledTaskListResponse>(
      response.data,
      scheduledTaskListResponseSchema,
      'ScheduledTaskListResponse',
    );
  },

  async getToday(
    query: ScheduledTaskTodayQuery = {},
  ): Promise<ScheduledTaskTodayResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/scheduled-tasks/today',
      {
        params: query.timezone ? { timezone: query.timezone } : undefined,
      },
    );
    return parseCamelCasePayload<ScheduledTaskTodayResponse>(
      response.data,
      scheduledTaskTodayResponseSchema,
      'ScheduledTaskTodayResponse',
    );
  },

  async create(
    payload: ScheduledTaskCreateRequest,
  ): Promise<ScheduledTaskDefinitionSummary> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/scheduled-tasks',
      toSnakeCreatePayload(payload),
    );
    return parseCamelCasePayload<ScheduledTaskDefinitionSummary>(
      response.data,
      supportedTaskItemSchema,
      'ScheduledTaskItem',
    );
  },

  async getStatus(taskId: string): Promise<ScheduledTaskStatusResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/scheduled-tasks/${encodeURIComponent(taskId)}/status`,
    );
    return parseCamelCasePayload<ScheduledTaskStatusResponse>(
      response.data,
      scheduledTaskStatusResponseSchema,
      'ScheduledTaskStatusResponse',
    );
  },

  async listRuns(
    taskId: string,
    query: ScheduledTaskRunListQuery = {},
  ): Promise<ScheduledTaskRunListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/scheduled-tasks/${encodeURIComponent(taskId)}/runs`,
      {
        params: query.limit === undefined ? undefined : { limit: query.limit },
      },
    );
    return parseCamelCasePayload<ScheduledTaskRunListResponse>(
      response.data,
      scheduledTaskRunListResponseSchema,
      'ScheduledTaskRunListResponse',
    );
  },

  async enable(taskId: string): Promise<ScheduledTaskDefinitionSummary> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/scheduled-tasks/${encodeURIComponent(taskId)}/enable`,
    );
    return parseCamelCasePayload<ScheduledTaskDefinitionSummary>(
      response.data,
      definitionSummarySchema,
      'ScheduledTaskItem',
    );
  },

  async disable(taskId: string): Promise<ScheduledTaskDefinitionSummary> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/scheduled-tasks/${encodeURIComponent(taskId)}/disable`,
    );
    return parseCamelCasePayload<ScheduledTaskDefinitionSummary>(
      response.data,
      definitionSummarySchema,
      'ScheduledTaskItem',
    );
  },
};
