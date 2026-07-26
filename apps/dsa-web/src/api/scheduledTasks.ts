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
import apiClient from './index';
import { toCamelCase } from './utils';

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
    return toCamelCase<ScheduledTaskListResponse>(response.data);
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
    return toCamelCase<ScheduledTaskTodayResponse>(response.data);
  },

  async create(
    payload: ScheduledTaskCreateRequest,
  ): Promise<ScheduledTaskDefinitionSummary> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/scheduled-tasks',
      toSnakeCreatePayload(payload),
    );
    return toCamelCase<ScheduledTaskDefinitionSummary>(response.data);
  },

  async getStatus(taskId: string): Promise<ScheduledTaskStatusResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/scheduled-tasks/${encodeURIComponent(taskId)}/status`,
    );
    return toCamelCase<ScheduledTaskStatusResponse>(response.data);
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
    return toCamelCase<ScheduledTaskRunListResponse>(response.data);
  },

  async enable(taskId: string): Promise<ScheduledTaskDefinitionSummary> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/scheduled-tasks/${encodeURIComponent(taskId)}/enable`,
    );
    return toCamelCase<ScheduledTaskDefinitionSummary>(response.data);
  },

  async disable(taskId: string): Promise<ScheduledTaskDefinitionSummary> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/scheduled-tasks/${encodeURIComponent(taskId)}/disable`,
    );
    return toCamelCase<ScheduledTaskDefinitionSummary>(response.data);
  },
};
