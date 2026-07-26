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
  },
}));

const t = (key: keyof typeof UI_TEXT.en, params?: Record<string, string | number>) => {
  const template = UI_TEXT.en[key] ?? String(key);
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    params[name] === undefined ? match : String(params[name])
  ));
};

describe('ScheduledTasksPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

    render(<ScheduledTasksPanel t={t} language="en" />);

    expect(await screen.findByText('Future task')).toBeInTheDocument();
    expect(screen.getByText('Unsupported schema')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: /Enable or disable Future task/i })).toBeDisabled();
  });
});
