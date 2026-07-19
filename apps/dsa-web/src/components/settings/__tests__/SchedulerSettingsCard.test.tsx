import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { systemConfigApi } from '../../../api/systemConfig';
import type { SchedulerStatusResponse, SystemConfigItem } from '../../../types/systemConfig';
import { SchedulerSettingsCard } from '../SchedulerSettingsCard';

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    getSchedulerStatus: vi.fn(),
    runSchedulerNow: vi.fn(),
  },
}));

const items: SystemConfigItem[] = [{
  key: 'SCHEDULE_ENABLED',
  value: 'true',
  rawValueExists: true,
  isMasked: false,
  schema: {
    key: 'SCHEDULE_ENABLED',
    category: 'system',
    dataType: 'boolean',
    uiControl: 'switch',
    isSensitive: false,
    isRequired: false,
    isEditable: true,
    options: [],
    validation: {},
    displayOrder: 1,
  },
}];

const enabledStatus: SchedulerStatusResponse = {
  enabled: true,
  running: false,
  scheduleTimes: [],
  nextRunAt: null,
  lastRunAt: null,
  lastSuccessAt: null,
  lastError: null,
};

function renderCard(overrideResetToken = 'v1:0', statusRefreshToken = 0) {
  return render(
    <SchedulerSettingsCard
      items={items}
      disabled={false}
      issueByKey={{}}
      statusRefreshToken={statusRefreshToken}
      overrideResetToken={overrideResetToken}
      onChange={() => undefined}
      onSchedulerStateChange={() => undefined}
      t={(key) => key}
      language="zh"
    />,
  );
}

describe('SchedulerSettingsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('clears a local switch override when the parent resets its draft', async () => {
    vi.mocked(systemConfigApi.getSchedulerStatus).mockResolvedValue(enabledStatus);
    const { rerender } = renderCard();
    const enabledSwitch = await screen.findByTestId('scheduler-enabled-switch');
    await waitFor(() => expect(enabledSwitch).toBeChecked());

    fireEvent.click(enabledSwitch);
    expect(enabledSwitch).not.toBeChecked();

    rerender(
      <SchedulerSettingsCard
        items={items}
        disabled={false}
        issueByKey={{}}
        statusRefreshToken={0}
        overrideResetToken="v1:1"
        onChange={() => undefined}
        onSchedulerStateChange={() => undefined}
        t={(key) => key}
        language="zh"
      />,
    );

    await waitFor(() => expect(enabledSwitch).toBeChecked());
  });

  it('ignores a stale scheduler status response after a newer refresh resolves', async () => {
    let resolveFirst!: (status: SchedulerStatusResponse) => void;
    let resolveSecond!: (status: SchedulerStatusResponse) => void;
    vi.mocked(systemConfigApi.getSchedulerStatus)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }));

    const { rerender } = renderCard();
    rerender(
      <SchedulerSettingsCard
        items={items}
        disabled={false}
        issueByKey={{}}
        statusRefreshToken={1}
        overrideResetToken="v1:0"
        onChange={() => undefined}
        onSchedulerStateChange={() => undefined}
        t={(key) => key}
        language="zh"
      />,
    );

    await act(async () => {
      resolveSecond({ ...enabledStatus, enabled: false });
    });
    await waitFor(() => expect(screen.getByTestId('scheduler-enabled-switch')).not.toBeChecked());

    await act(async () => {
      resolveFirst(enabledStatus);
    });
    expect(screen.getByTestId('scheduler-enabled-switch')).not.toBeChecked();
  });
});
