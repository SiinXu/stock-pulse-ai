import type {
  ScheduledTaskTodayQuery,
  ScheduledTaskTodayResponse,
} from '../types/scheduledTasks';
import apiClient from './index';
import { toCamelCase } from './utils';

export const scheduledTasksApi = {
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
};
