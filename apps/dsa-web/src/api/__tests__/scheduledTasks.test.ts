import { beforeEach, describe, expect, it, vi } from 'vitest';
import { scheduledTasksApi } from '../scheduledTasks';

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get, post },
}));

describe('scheduledTasksApi', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
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

  it('lists definitions and posts enable/disable mutations', async () => {
    get.mockResolvedValueOnce({
      data: {
        total: 1,
        items: [{
          compatibility: 'supported',
          id: 'task-1',
          schema_version: 1,
          name: 'Daily AAPL',
          task_type: 'stock_analysis',
          enabled: false,
          next_run_at: null,
          created_at: '2026-07-24T20:00:00Z',
          updated_at: '2026-07-24T20:00:00Z',
        }],
      },
    });
    post.mockResolvedValueOnce({
      data: {
        compatibility: 'supported',
        id: 'task-1',
        schema_version: 1,
        name: 'Daily AAPL',
        task_type: 'stock_analysis',
        enabled: true,
        next_run_at: '2026-07-26T15:00:00Z',
        created_at: '2026-07-24T20:00:00Z',
        updated_at: '2026-07-26T10:00:00Z',
      },
    });
    post.mockResolvedValueOnce({
      data: {
        compatibility: 'supported',
        id: 'task-1',
        schema_version: 1,
        name: 'Daily AAPL',
        task_type: 'stock_analysis',
        enabled: false,
        next_run_at: null,
        created_at: '2026-07-24T20:00:00Z',
        updated_at: '2026-07-26T11:00:00Z',
      },
    });

    const listed = await scheduledTasksApi.list({ limit: 50 });
    expect(get).toHaveBeenCalledWith('/api/v1/scheduled-tasks', {
      params: { limit: 50 },
    });
    expect(listed.items[0].taskType).toBe('stock_analysis');

    const enabled = await scheduledTasksApi.enable('task-1');
    expect(post).toHaveBeenCalledWith('/api/v1/scheduled-tasks/task-1/enable');
    expect(enabled.enabled).toBe(true);

    const disabled = await scheduledTasksApi.disable('task/with space');
    expect(post).toHaveBeenCalledWith('/api/v1/scheduled-tasks/task%2Fwith%20space/disable');
    expect(disabled.enabled).toBe(false);
  });
});
