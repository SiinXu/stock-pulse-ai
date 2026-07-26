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

  it('creates a stock-analysis definition with snake_case payload fields', async () => {
    post.mockResolvedValueOnce({
      data: {
        compatibility: 'supported',
        id: 'task-new',
        schema_version: 1,
        name: 'US close analysis',
        task_type: 'stock_analysis',
        enabled: true,
        next_run_at: '2026-07-27T20:30:00Z',
        created_at: '2026-07-26T12:00:00Z',
        updated_at: '2026-07-26T12:00:00Z',
      },
    });

    const created = await scheduledTasksApi.create({
      schemaVersion: 1,
      name: 'US close analysis',
      taskType: 'stock_analysis',
      schedule: {
        kind: 'daily',
        time: '16:30',
        timezone: 'America/New_York',
        calendarMarket: 'us',
        nonTradingDayPolicy: 'skip',
      },
      payload: {
        stockCode: 'AAPL',
        reportType: 'brief',
        notify: true,
      },
      enabled: true,
      maxAttempts: 2,
    });

    expect(post).toHaveBeenCalledWith('/api/v1/scheduled-tasks', {
      schema_version: 1,
      name: 'US close analysis',
      task_type: 'stock_analysis',
      schedule: {
        kind: 'daily',
        time: '16:30',
        timezone: 'America/New_York',
        calendar_market: 'us',
        non_trading_day_policy: 'skip',
      },
      payload: {
        stock_code: 'AAPL',
        report_type: 'brief',
        notify: true,
      },
      enabled: true,
      max_attempts: 2,
    });
    expect(created.id).toBe('task-new');
    expect(created.taskType).toBe('stock_analysis');
  });

  it('creates a research definition without report_type and loads status/runs', async () => {
    post.mockResolvedValueOnce({
      data: {
        compatibility: 'supported',
        id: 'task-risk',
        schema_version: 2,
        name: 'AAPL downside review',
        task_type: 'risk_check',
        enabled: true,
        next_run_at: '2026-07-27T13:30:00Z',
        created_at: '2026-07-26T12:00:00Z',
        updated_at: '2026-07-26T12:00:00Z',
      },
    });
    get.mockResolvedValueOnce({
      data: {
        task: {
          compatibility: 'supported',
          id: 'task-risk',
          schema_version: 2,
          name: 'AAPL downside review',
          task_type: 'risk_check',
          enabled: true,
          next_run_at: '2026-07-27T13:30:00Z',
          created_at: '2026-07-26T12:00:00Z',
          updated_at: '2026-07-26T12:00:00Z',
        },
        latest_run: {
          id: 'run-1',
          task_id: 'task-risk',
          scheduled_for: '2026-07-26T13:30:00Z',
          status: 'succeeded',
          attempt_count: 1,
          dispatch_failure_count: 0,
          execution_task_ids: ['analysis-1'],
          result_refs: [],
          error_code: null,
          next_attempt_at: null,
          started_at: '2026-07-26T13:30:01Z',
          finished_at: '2026-07-26T13:31:00Z',
          created_at: '2026-07-26T13:30:00Z',
          updated_at: '2026-07-26T13:31:00Z',
        },
      },
    });
    get.mockResolvedValueOnce({
      data: {
        total: 1,
        items: [{
          id: 'run-1',
          task_id: 'task-risk',
          scheduled_for: '2026-07-26T13:30:00Z',
          status: 'succeeded',
          attempt_count: 1,
          dispatch_failure_count: 0,
          execution_task_ids: ['analysis-1'],
          result_refs: [],
          error_code: null,
          next_attempt_at: null,
          started_at: '2026-07-26T13:30:01Z',
          finished_at: '2026-07-26T13:31:00Z',
          created_at: '2026-07-26T13:30:00Z',
          updated_at: '2026-07-26T13:31:00Z',
        }],
      },
    });

    await scheduledTasksApi.create({
      schemaVersion: 2,
      name: 'AAPL downside review',
      taskType: 'risk_check',
      schedule: {
        kind: 'daily',
        time: '09:30',
        timezone: 'America/New_York',
        calendarMarket: 'us',
        nonTradingDayPolicy: 'skip',
      },
      payload: {
        stockCode: 'AAPL',
        notify: true,
      },
    });

    expect(post).toHaveBeenCalledWith('/api/v1/scheduled-tasks', {
      schema_version: 2,
      name: 'AAPL downside review',
      task_type: 'risk_check',
      schedule: {
        kind: 'daily',
        time: '09:30',
        timezone: 'America/New_York',
        calendar_market: 'us',
        non_trading_day_policy: 'skip',
      },
      payload: {
        stock_code: 'AAPL',
        notify: true,
      },
    });

    const status = await scheduledTasksApi.getStatus('task/with space');
    expect(get).toHaveBeenCalledWith('/api/v1/scheduled-tasks/task%2Fwith%20space/status');
    expect(status.latestRun?.status).toBe('succeeded');
    expect(status.latestRun?.taskId).toBe('task-risk');
    expect(status.latestRun?.finishedAt).toBe('2026-07-26T13:31:00Z');

    const runs = await scheduledTasksApi.listRuns('task-risk', { limit: 5 });
    expect(get).toHaveBeenCalledWith('/api/v1/scheduled-tasks/task-risk/runs', {
      params: { limit: 5 },
    });
    expect(runs.total).toBe(1);
    expect(runs.items[0].status).toBe('succeeded');
  });
});
