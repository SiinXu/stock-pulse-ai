import { beforeEach, describe, expect, it, vi } from 'vitest';
import { scheduledTasksApi } from '../scheduledTasks';

const { get } = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get },
}));

describe('scheduledTasksApi', () => {
  beforeEach(() => {
    get.mockReset();
  });

  it('loads the timezone-aware today projection and camel-cases nested fields', async () => {
    get.mockResolvedValueOnce({
      data: {
        date: '2026-07-25',
        timezone: 'America/Los_Angeles',
        generated_at: '2026-07-25T19:00:00Z',
        total: 1,
        items: [{
          task: {
            compatibility: 'supported',
            id: 'task-1',
            schema_version: 2,
            name: 'AAPL risk check',
            task_type: 'risk_check',
            enabled: true,
            next_run_at: '2026-07-25T10:00:00Z',
            created_at: '2026-07-24T20:00:00Z',
            updated_at: '2026-07-24T20:00:00Z',
          },
          scheduled_for: '2026-07-25T10:00:00Z',
          status: 'scheduled',
          run: null,
        }],
      },
    });

    const result = await scheduledTasksApi.getToday({
      timezone: 'America/Los_Angeles',
    });

    expect(get).toHaveBeenCalledWith('/api/v1/scheduled-tasks/today', {
      params: { timezone: 'America/Los_Angeles' },
    });
    expect(result.generatedAt).toBe('2026-07-25T19:00:00Z');
    expect(result.items[0].scheduledFor).toBe('2026-07-25T10:00:00Z');
    expect(result.items[0].task).toMatchObject({
      schemaVersion: 2,
      taskType: 'risk_check',
      nextRunAt: '2026-07-25T10:00:00Z',
    });
  });
});
