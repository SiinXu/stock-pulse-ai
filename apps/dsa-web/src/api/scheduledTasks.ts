import type {
  ScheduledTaskDefinitionSummary,
  ScheduledTaskListQuery,
  ScheduledTaskListResponse,
  ScheduledTaskTodayQuery,
  ScheduledTaskTodayResponse,
} from '../types/scheduledTasks';
import apiClient from './index';
import { toCamelCase } from './utils';

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
