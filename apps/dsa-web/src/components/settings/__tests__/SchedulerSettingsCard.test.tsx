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

describe('SchedulerSettingsCard dual-schedule honesty', () => {
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

  it('labels the card as legacy day-batch and documents process ownership', async () => {
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

    expect(await screen.findByTestId('scheduler-settings-card')).toBeInTheDocument();
    expect(screen.getByText('Legacy day-batch schedule')).toBeInTheDocument();
    expect(screen.getByTestId('scheduler-legacy-track-note')).toBeInTheDocument();
    expect(screen.getByTestId('scheduler-owner-note')).toBeInTheDocument();
    expect(screen.getByText(/DSA_SCHEDULED_TASK_OWNER/)).toBeInTheDocument();
    expect(screen.queryByTestId('scheduler-dual-track-warning')).not.toBeInTheDocument();
  });

  it('shows a dual-track warning when legacy is enabled and a versioned task is enabled', async () => {
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

    expect(await screen.findByTestId('scheduler-dual-track-warning')).toBeInTheDocument();
    expect(scheduledTasksApi.list).toHaveBeenCalledWith({ enabled: true, limit: 1 });
  });

  it('does not invent a dual-track warning when the versioned list probe fails', async () => {
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
    expect(screen.queryByTestId('scheduler-dual-track-warning')).not.toBeInTheDocument();
  });

  it('treats a positive total as dual-track even when items are empty', async () => {
    vi.mocked(scheduledTasksApi.list).mockResolvedValue({
      total: 2,
      items: [],
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

    expect(await screen.findByTestId('scheduler-dual-track-warning')).toBeInTheDocument();
  });
});

