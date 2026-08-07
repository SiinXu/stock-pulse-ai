// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { scheduledTasksApi } from '../../../api/scheduledTasks';
import { UI_TEXT } from '../../../i18n/uiText';
import ScheduledTasksPanel from '../ScheduledTasksPanel';

vi.mock('../../../api/scheduledTasks', () => ({
  scheduledTasksApi: {
    list: vi.fn(),
    enable: vi.fn(),
    disable: vi.fn(),
    create: vi.fn(),
    getStatus: vi.fn(),
    listRuns: vi.fn(),
  },
}));

const t = (key: keyof typeof UI_TEXT.en, params?: Record<string, string | number>) => {
  const template = UI_TEXT.en[key] ?? String(key);
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    params[name] === undefined ? match : String(params[name])
  ));
};

const scheduledTask = {
  compatibility: 'supported' as const,
  id: 'task-1',
  schemaVersion: 2,
  name: 'AAPL risk check',
  taskType: 'risk_check',
  enabled: true,
  nextRunAt: '2026-07-26T15:00:00Z',
  createdAt: '2026-07-25T10:00:00Z',
  updatedAt: '2026-07-25T10:00:00Z',
};

function buildRun(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    taskId: 'task-1',
    scheduledFor: '2026-07-26T20:30:00Z',
    status: 'succeeded' as const,
    attemptCount: 1,
    dispatchFailureCount: 0,
    executionTaskIds: [`execution-${id}`],
    resultRefs: [`result-${id}`],
    notificationStatus: 'succeeded',
    notificationChannels: ['email'],
    notificationFailedChannels: [],
    errorCode: null,
    nextAttemptAt: null,
    startedAt: '2026-07-26T20:30:01Z',
    finishedAt: '2026-07-26T20:31:00Z',
    createdAt: '2026-07-26T20:30:00Z',
    updatedAt: '2026-07-26T20:31:00Z',
    ...overrides,
  };
}

describe('ScheduledTasksPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(scheduledTasksApi.getStatus).mockResolvedValue({
      task: {
        compatibility: 'supported',
        id: 'task-1',
        schemaVersion: 2,
        name: 'AAPL risk check',
        taskType: 'risk_check',
        enabled: true,
        nextRunAt: '2026-07-26T15:00:00Z',
        createdAt: '2026-07-25T10:00:00Z',
        updatedAt: '2026-07-25T10:00:00Z',
      },
      latestRun: null,
    });
  });

  it('lists definitions and toggles enable/disable through the API', async () => {
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({
      total: 1,
      items: [{
        compatibility: 'supported',
        id: 'task-1',
        schemaVersion: 2,
        name: 'AAPL risk check',
        taskType: 'risk_check',
        enabled: true,
        nextRunAt: '2026-07-26T15:00:00Z',
        createdAt: '2026-07-25T10:00:00Z',
        updatedAt: '2026-07-25T10:00:00Z',
      }],
    });
    vi.mocked(scheduledTasksApi.disable).mockResolvedValue({
      compatibility: 'supported',
      id: 'task-1',
      schemaVersion: 2,
      name: 'AAPL risk check',
      taskType: 'risk_check',
      enabled: false,
      nextRunAt: null,
      createdAt: '2026-07-25T10:00:00Z',
      updatedAt: '2026-07-26T10:00:00Z',
    });

    render(<ScheduledTasksPanel t={t} language="en" />);

    const descriptionNote = screen.getByText(UI_TEXT.en['settings.scheduledTasksDescription']);
    expect(descriptionNote).toHaveClass('text-xs', 'text-muted-text');
    expect(descriptionNote.closest('header')).toBeNull();
    expect(await screen.findByText('AAPL risk check')).toBeInTheDocument();
    const toggle = screen.getByRole('switch', { name: /Enable or disable AAPL risk check/i });
    expect(toggle).toBeChecked();

    fireEvent.click(toggle);
    await waitFor(() => {
      expect(scheduledTasksApi.disable).toHaveBeenCalledWith('task-1');
    });
    await waitFor(() => {
      expect(toggle).not.toBeChecked();
    });
  });

  it('disables the toggle for unsupported schema projections', async () => {
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({
      total: 1,
      items: [{
        compatibility: 'unsupported_schema',
        id: 'task-future',
        schemaVersion: 9,
        name: 'Future task',
        enabled: true,
        nextRunAt: null,
        createdAt: '2026-07-25T10:00:00Z',
        updatedAt: '2026-07-25T10:00:00Z',
      }],
    });
    vi.mocked(scheduledTasksApi.getStatus).mockResolvedValue({
      task: {
        compatibility: 'unsupported_schema',
        id: 'task-future',
        schemaVersion: 9,
        name: 'Future task',
        enabled: true,
        nextRunAt: null,
        createdAt: '2026-07-25T10:00:00Z',
        updatedAt: '2026-07-25T10:00:00Z',
      },
      latestRun: null,
    });

    render(<ScheduledTasksPanel t={t} language="en" />);

    expect(await screen.findByText('Future task')).toBeInTheDocument();
    expect(screen.getByText('Unsupported schema')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: /Enable or disable Future task/i })).toBeDisabled();
  });

  it('creates a supported definition through the form and reloads the list', async () => {
    vi.mocked(scheduledTasksApi.list)
      .mockResolvedValueOnce({ total: 0, items: [] })
      .mockResolvedValueOnce({
        total: 1,
        items: [{
          compatibility: 'supported',
          id: 'task-new',
          schemaVersion: 1,
          name: 'Daily AAPL',
          taskType: 'stock_analysis',
          enabled: true,
          nextRunAt: '2026-07-27T20:30:00Z',
          createdAt: '2026-07-26T12:00:00Z',
          updatedAt: '2026-07-26T12:00:00Z',
        }],
      });
    vi.mocked(scheduledTasksApi.create).mockResolvedValue({
      compatibility: 'supported',
      id: 'task-new',
      schemaVersion: 1,
      name: 'Daily AAPL',
      taskType: 'stock_analysis',
      enabled: true,
      nextRunAt: '2026-07-27T20:30:00Z',
      createdAt: '2026-07-26T12:00:00Z',
      updatedAt: '2026-07-26T12:00:00Z',
    });
    vi.mocked(scheduledTasksApi.getStatus).mockResolvedValue({
      task: {
        compatibility: 'supported',
        id: 'task-new',
        schemaVersion: 1,
        name: 'Daily AAPL',
        taskType: 'stock_analysis',
        enabled: true,
        nextRunAt: '2026-07-27T20:30:00Z',
        createdAt: '2026-07-26T12:00:00Z',
        updatedAt: '2026-07-26T12:00:00Z',
      },
      latestRun: null,
    });

    render(<ScheduledTasksPanel t={t} language="en" />);

    expect(await screen.findByText('No schedule definitions yet')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('settings-scheduled-tasks-create'));
    expect(await screen.findByTestId('settings-scheduled-tasks-create-form')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Daily AAPL' } });
    fireEvent.change(screen.getByLabelText('Symbol code'), { target: { value: 'AAPL' } });
    fireEvent.click(screen.getByTestId('settings-scheduled-tasks-create-submit'));

    await waitFor(() => {
      expect(scheduledTasksApi.create).toHaveBeenCalledWith(expect.objectContaining({
        schemaVersion: 1,
        name: 'Daily AAPL',
        taskType: 'stock_analysis',
        payload: expect.objectContaining({
          stockCode: 'AAPL',
          reportType: 'detailed',
          notify: true,
        }),
      }));
    });
    expect(await screen.findByText('Daily AAPL')).toBeInTheDocument();
    expect(await screen.findByText(/Created “Daily AAPL”/)).toBeInTheDocument();
  });

  it('surfaces the latest run status from the status endpoint', async () => {
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({
      total: 1,
      items: [{
        compatibility: 'supported',
        id: 'task-1',
        schemaVersion: 1,
        name: 'Daily AAPL',
        taskType: 'stock_analysis',
        enabled: true,
        nextRunAt: '2026-07-27T20:30:00Z',
        createdAt: '2026-07-26T12:00:00Z',
        updatedAt: '2026-07-26T12:00:00Z',
      }],
    });
    vi.mocked(scheduledTasksApi.getStatus).mockResolvedValue({
      task: {
        compatibility: 'supported',
        id: 'task-1',
        schemaVersion: 1,
        name: 'Daily AAPL',
        taskType: 'stock_analysis',
        enabled: true,
        nextRunAt: '2026-07-27T20:30:00Z',
        createdAt: '2026-07-26T12:00:00Z',
        updatedAt: '2026-07-26T12:00:00Z',
      },
      latestRun: {
        id: 'run-1',
        taskId: 'task-1',
        scheduledFor: '2026-07-26T20:30:00Z',
        status: 'succeeded',
        attemptCount: 1,
        dispatchFailureCount: 0,
        executionTaskIds: [],
        resultRefs: [],
        errorCode: null,
        nextAttemptAt: null,
        startedAt: '2026-07-26T20:30:01Z',
        finishedAt: '2026-07-26T20:31:00Z',
        createdAt: '2026-07-26T20:30:00Z',
        updatedAt: '2026-07-26T20:31:00Z',
      },
    });

    render(<ScheduledTasksPanel t={t} language="en" />);

    expect(await screen.findByText('Daily AAPL')).toBeInTheDocument();
    await waitFor(() => {
      expect(scheduledTasksApi.getStatus).toHaveBeenCalledWith('task-1');
    });
    expect(await screen.findByTestId('settings-scheduled-task-status-task-1')).toHaveTextContent('Succeeded');
    expect(screen.getByText(/Last run: Succeeded/)).toBeInTheDocument();
  });

  it('shows client-side validation when required create fields are empty', async () => {
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({ total: 0, items: [] });

    render(<ScheduledTasksPanel t={t} language="en" />);

    fireEvent.click(await screen.findByTestId('settings-scheduled-tasks-create'));
    fireEvent.click(screen.getByTestId('settings-scheduled-tasks-create-submit'));

    expect(await screen.findByText('Enter a name.')).toBeInTheDocument();
    expect(scheduledTasksApi.create).not.toHaveBeenCalled();
  });

  it('rejects invalid max attempts before calling create', async () => {
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({ total: 0, items: [] });

    render(<ScheduledTasksPanel t={t} language="en" />);

    fireEvent.click(await screen.findByTestId('settings-scheduled-tasks-create'));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Daily AAPL' } });
    fireEvent.change(screen.getByLabelText('Symbol code'), { target: { value: 'AAPL' } });
    fireEvent.change(screen.getByLabelText('Max attempts'), { target: { value: '9' } });
    fireEvent.click(screen.getByTestId('settings-scheduled-tasks-create-submit'));

    expect(await screen.findByText('Max attempts must be an integer from 1 to 3.')).toBeInTheDocument();
    expect(scheduledTasksApi.create).not.toHaveBeenCalled();
  });

  it('loads multiple run records lazily and exposes failure and notification diagnostics', async () => {
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({ total: 1, items: [scheduledTask] });
    vi.mocked(scheduledTasksApi.listRuns).mockResolvedValue({
      total: 2,
      items: [
        buildRun('run-success'),
        buildRun('run-failed', {
          status: 'failed',
          attemptCount: 3,
          dispatchFailureCount: 2,
          executionTaskIds: ['execution-failed'],
          resultRefs: [],
          notificationStatus: 'partial_failure',
          notificationChannels: ['email', 'dingtalk'],
          notificationFailedChannels: ['dingtalk'],
          errorCode: 'analysis_failed',
        }),
      ],
    });

    render(<ScheduledTasksPanel t={t} language="en" />);

    expect(await screen.findByText('AAPL risk check')).toBeInTheDocument();
    expect(scheduledTasksApi.listRuns).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('settings-scheduled-task-history-toggle-task-1'));

    await waitFor(() => expect(scheduledTasksApi.listRuns).toHaveBeenCalledWith(
      'task-1',
      { limit: 10 },
    ));
    expect(await screen.findByTestId('settings-scheduled-task-run-run-success')).toBeInTheDocument();
    const failed = await screen.findByTestId('settings-scheduled-task-run-run-failed');
    expect(failed).toHaveTextContent('Failed');
    expect(failed).toHaveTextContent('3 attempts · 2 dispatch failures');
    expect(failed).toHaveTextContent('execution-failed');
    expect(failed).toHaveTextContent('partial_failure · email, dingtalk');
    expect(failed).toHaveTextContent('dingtalk');
    expect(failed).toHaveTextContent('analysis_failed');
  });

  it('shows an empty history and uses the API limit contract for load more and refresh', async () => {
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({ total: 1, items: [scheduledTask] });
    vi.mocked(scheduledTasksApi.listRuns)
      .mockResolvedValueOnce({ total: 0, items: [] })
      .mockResolvedValueOnce({ total: 11, items: [buildRun('run-1')] })
      .mockResolvedValueOnce({
        total: 2,
        items: [buildRun('run-1'), buildRun('run-2')],
      })
      .mockResolvedValueOnce({
        total: 2,
        items: [buildRun('run-1'), buildRun('run-2')],
      });

    render(<ScheduledTasksPanel t={t} language="en" />);

    await screen.findByText('AAPL risk check');
    fireEvent.click(screen.getByTestId('settings-scheduled-task-history-toggle-task-1'));
    expect(await screen.findByText('No run history')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {
      name: 'Refresh run history for “AAPL risk check”',
    }));
    expect(await screen.findByTestId('settings-scheduled-task-run-run-1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }));
    await waitFor(() => expect(scheduledTasksApi.listRuns).toHaveBeenNthCalledWith(
      3,
      'task-1',
      { limit: 20 },
    ));
    expect(await screen.findByTestId('settings-scheduled-task-run-run-2')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {
      name: 'Refresh run history for “AAPL risk check”',
    }));
    await waitFor(() => expect(scheduledTasksApi.listRuns).toHaveBeenNthCalledWith(
      4,
      'task-1',
      { limit: 20 },
    ));
  });
});
