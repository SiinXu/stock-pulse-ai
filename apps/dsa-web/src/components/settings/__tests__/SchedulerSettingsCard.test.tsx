// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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

describe('SchedulerSettingsCard legacy migration notice', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(systemConfigApi.getSchedulerStatus).mockResolvedValue({
      enabled: true,
      running: false,
      scheduleTimes: ['09:20', '15:10'],
      nextRunAt: null,
      lastRunAt: null,
      lastSuccessAt: null,
      lastError: null,
    });
  });

  it('labels the card as deprecated legacy day-batch and documents process ownership', async () => {
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({ total: 0, items: [] });

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
    expect(card.querySelector(':scope > div.grid')).not.toHaveClass('xl:grid-cols-2', 'xl:items-start');
    expect(card.querySelector('dl')).toHaveClass('sm:grid-cols-3');
    expect(screen.getByText('Legacy day-batch schedule')).toBeInTheDocument();
    expect(screen.getByTestId('scheduler-legacy-track-note')).toBeInTheDocument();
    expect(screen.getByTestId('scheduler-owner-note')).toBeInTheDocument();
    expect(screen.getByText(/DSA_SCHEDULED_TASK_OWNER/)).toBeInTheDocument();
    const notice = await screen.findByTestId('scheduler-migration-notice');
    expect(notice).toBeInTheDocument();
    expect(notice).toHaveTextContent(/Migrate to versioned scheduled tasks/);
    // Scope to the notice: card description also mentions "Saved schedule definitions".
    expect(notice).toHaveTextContent(/Saved schedule definitions/);
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
