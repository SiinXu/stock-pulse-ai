// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { scheduledTasksApi } from '../../../api/scheduledTasks';
import { systemConfigApi } from '../../../api/systemConfig';
import { UI_TEXT } from '../../../i18n/uiText';
import type { SystemConfigItem } from '../../../types/systemConfig';
import SchedulerSettingsCard from '../SchedulerSettingsCard';

vi.mock('../../../api/scheduledTasks', () => ({
  scheduledTasksApi: {
    list: vi.fn(),
  },
}));

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    getSchedulerStatus: vi.fn(),
    runSchedulerNow: vi.fn(),
  },
}));

const t = (key: keyof typeof UI_TEXT.en, params?: Record<string, string | number>) => {
  const template = UI_TEXT.en[key] ?? String(key);
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    params[name] === undefined ? match : String(params[name])
  ));
};

function scheduleItem(key: string, value: string): SystemConfigItem {
  return {
    key,
    value,
    rawValueExists: true,
    isMasked: false,
    schema: {
      key,
      category: 'system',
      dataType: key === 'SCHEDULE_ENABLED' ? 'boolean' : 'string',
      uiControl: key === 'SCHEDULE_ENABLED' ? 'switch' : 'text',
      isSensitive: false,
      isRequired: false,
      isEditable: true,
      options: [],
      validation: {},
      displayOrder: 10,
    },
  };
}

const defaultItems: SystemConfigItem[] = [
  scheduleItem('SCHEDULE_ENABLED', 'true'),
  scheduleItem('SCHEDULE_TIMES', '09:20,15:10'),
];

const idleStatus = {
  enabled: true,
  running: false,
  scheduleTimes: ['09:20', '15:10'],
  nextRunAt: '2026-06-21T09:20:00+08:00',
  lastRunAt: null,
  lastSuccessAt: '2026-06-20T15:10:00+08:00',
  lastError: null,
  lastSkippedAt: null,
  lastSkipReason: null,
};

describe('SchedulerSettingsCard observability', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(systemConfigApi.getSchedulerStatus).mockResolvedValue({ ...idleStatus });
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({ total: 0, items: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows next run with timezone label, process mode, and run-now tracking surface', async () => {
    render(
      <SchedulerSettingsCard
        items={defaultItems}
        disabled={false}
        issueByKey={{}}
        statusRefreshToken={0}
        onChange={vi.fn()}
        t={t}
        language="en"
      />,
    );

    const card = await screen.findByTestId('scheduler-settings-card');
    expect(card.querySelector(':scope > div.grid')).toHaveClass('2xl:grid-cols-2', '2xl:items-start');
    expect(screen.getByText('Legacy day-batch schedule')).toBeInTheDocument();
    expect(screen.queryByText(UI_TEXT.en['settings.schedulerDescription'])).not.toBeInTheDocument();
    expect(screen.queryByTestId('scheduler-legacy-track-note')).not.toBeInTheDocument();

    const nextRun = await screen.findByTestId('scheduler-next-run');
    // Explicit TZ label (marketFormat shortOffset convention); offset may be GMT+8 or local.
    expect(nextRun.textContent).toMatch(/GMT[+-]\d+/i);

    const processMode = screen.getByTestId('scheduler-process-mode');
    expect(processMode).toHaveTextContent(UI_TEXT.en['settings.schedulerProcessMode']);
    expect(screen.getByTestId('scheduler-process-mode-value')).toHaveTextContent(
      UI_TEXT.en['settings.schedulerProcessModeValue'],
    );
    expect(screen.getByTestId('scheduler-owner-note')).toHaveTextContent(/GitHub Actions/i);
    expect(screen.getByTestId('scheduler-owner-note')).toHaveTextContent(/--serve/i);

    const notice = await screen.findByTestId('scheduler-migration-notice');
    expect(notice).toBeInTheDocument();
    expect(notice).toHaveTextContent(/Migrate to versioned scheduled tasks/);
  });

  it('disables run-now while analysis is running and shows busy reason', async () => {
    vi.mocked(systemConfigApi.getSchedulerStatus).mockResolvedValue({
      ...idleStatus,
      running: true,
      nextRunAt: null,
    });

    render(
      <SchedulerSettingsCard
        items={defaultItems}
        disabled={false}
        issueByKey={{}}
        statusRefreshToken={0}
        onChange={vi.fn()}
        t={t}
        language="en"
      />,
    );

    const runNow = await screen.findByTestId('scheduler-run-now-button');
    await waitFor(() => expect(runNow).toBeDisabled());
    expect(screen.getByTestId('scheduler-run-now-busy-reason')).toHaveTextContent(
      /already running/i,
    );
    expect(screen.getByTestId('scheduler-runtime-badge')).toHaveTextContent(
      UI_TEXT.en['settings.schedulerRunning'],
    );
  });

  it('after run-now acceptance shows tracked success and refreshes status (not bare task id)', async () => {
    vi.mocked(systemConfigApi.runSchedulerNow).mockResolvedValue({
      accepted: true,
      running: true,
    });
    vi.mocked(systemConfigApi.getSchedulerStatus)
      .mockResolvedValueOnce({ ...idleStatus })
      .mockResolvedValueOnce({
        ...idleStatus,
        running: true,
        lastRunAt: '2026-06-21T09:00:00+08:00',
      });

    render(
      <SchedulerSettingsCard
        items={defaultItems}
        disabled={false}
        issueByKey={{}}
        statusRefreshToken={0}
        onChange={vi.fn()}
        t={t}
        language="en"
      />,
    );

    await screen.findByTestId('scheduler-run-now-button');
    fireEvent.click(screen.getByTestId('scheduler-run-now-button'));

    await waitFor(() => expect(systemConfigApi.runSchedulerNow).toHaveBeenCalledTimes(1));
    const success = await screen.findByText(UI_TEXT.en['settings.schedulerRunAccepted']);
    expect(success).toBeInTheDocument();
    // Tracked run-now messaging (must not be a bare opaque id alone).
    expect(success).toHaveTextContent(/this process/i);
    expect(success).toHaveTextContent(/Running until complete/i);
    expect(success.textContent).not.toMatch(/^task[_-]?[a-z0-9-]+$/i);
    await waitFor(() => expect(systemConfigApi.getSchedulerStatus).toHaveBeenCalledTimes(2));
  });

  it('shows last skipped from status when present', async () => {
    vi.mocked(systemConfigApi.getSchedulerStatus).mockResolvedValue({
      ...idleStatus,
      lastSkippedAt: '2026-06-21T08:00:00+08:00',
      lastSkipReason: 'analysis_already_running',
    });

    render(
      <SchedulerSettingsCard
        items={defaultItems}
        disabled={false}
        issueByKey={{}}
        statusRefreshToken={0}
        onChange={vi.fn()}
        t={t}
        language="en"
      />,
    );

    const skipped = await screen.findByTestId('scheduler-last-skipped');
    expect(skipped).toHaveTextContent(UI_TEXT.en['settings.schedulerSkipReasonBusy']);
    expect(skipped.textContent).toMatch(/GMT[+-]\d+/i);
  });

  it('uses the both-active migration copy when a versioned task is also enabled', async () => {
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({
      total: 1,
      items: [{
        compatibility: 'supported',
        id: 'task-1',
        schemaVersion: 1,
        name: 'US close',
        taskType: 'stock_analysis',
        enabled: true,
        nextRunAt: '2026-07-26T20:30:00Z',
        createdAt: '2026-07-25T10:00:00Z',
        updatedAt: '2026-07-25T10:00:00Z',
      }],
    });

    render(
      <SchedulerSettingsCard
        items={defaultItems}
        disabled={false}
        issueByKey={{}}
        statusRefreshToken={0}
        onChange={vi.fn()}
        t={t}
        language="en"
      />,
    );

    const notice = await screen.findByTestId('scheduler-migration-notice');
    expect(notice).toBeInTheDocument();
    expect(notice).toHaveTextContent(/both enabled/i);
    expect(scheduledTasksApi.list).toHaveBeenCalledWith({ enabled: true, limit: 1 });
  });

  it('still shows the directional migration notice when the versioned list probe fails', async () => {
    vi.mocked(scheduledTasksApi.list).mockRejectedValue(new Error('network'));

    render(
      <SchedulerSettingsCard
        items={defaultItems}
        disabled={false}
        issueByKey={{}}
        statusRefreshToken={0}
        onChange={vi.fn()}
        t={t}
        language="en"
      />,
    );

    await waitFor(() => {
      expect(scheduledTasksApi.list).toHaveBeenCalled();
    });
    expect(await screen.findByTestId('scheduler-migration-notice')).toBeInTheDocument();
    expect(screen.queryByText(/both enabled/i)).not.toBeInTheDocument();
  });

  it('does not show the migration notice when legacy day-batch is disabled', async () => {
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({ total: 2, items: [] });
    vi.mocked(systemConfigApi.getSchedulerStatus).mockResolvedValue({
      enabled: false,
      running: false,
      scheduleTimes: ['09:20'],
      nextRunAt: null,
      lastRunAt: null,
      lastSuccessAt: null,
      lastError: null,
    });

    render(
      <SchedulerSettingsCard
        items={[
          scheduleItem('SCHEDULE_ENABLED', 'false'),
          scheduleItem('SCHEDULE_TIMES', '09:20'),
        ]}
        disabled={false}
        issueByKey={{}}
        statusRefreshToken={0}
        onChange={vi.fn()}
        t={t}
        language="en"
      />,
    );

    await waitFor(() => {
      expect(systemConfigApi.getSchedulerStatus).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('scheduler-migration-notice')).not.toBeInTheDocument();
  });
});
