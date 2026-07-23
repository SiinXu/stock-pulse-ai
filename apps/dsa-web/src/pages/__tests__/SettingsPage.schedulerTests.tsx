import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it } from 'vitest';
import SettingsPageTestHarness from './SettingsPage.testHarness';

const {
  SettingsPage,
  alphasiftEnable,
  alphasiftInstall,
  buildSystemConfigState,
  getChangedItems,
  getSchedulerStatus,
  refreshAfterExternalSave,
  runSchedulerNow,
  save,
  setDraftValue,
  updateSystemConfig,
  useSystemConfigMock,
} = SettingsPageTestHarness;

export function registerSettingsPageSchedulerTests(): void {
  it('maps schedule settings to the scheduler card instead of generic raw fields', async () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
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
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIME',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIME',
              category: 'system',
              dataType: 'time',
              uiControl: 'time',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 10,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '09:20,15:10',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
          {
            key: 'SCHEDULE_RUN_IMMEDIATELY',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_RUN_IMMEDIATELY',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 12,
            },
          },
          {
            key: 'LOG_LEVEL',
            value: 'INFO',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'LOG_LEVEL',
              category: 'system',
              dataType: 'string',
              uiControl: 'select',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: ['INFO', 'DEBUG'],
              validation: {},
              displayOrder: 50,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(await screen.findByTestId('scheduler-settings-card')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-SCHEDULE_ENABLED')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-SCHEDULE_TIME')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-SCHEDULE_TIMES')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-SCHEDULE_RUN_IMMEDIATELY')).not.toBeInTheDocument();
    // LOG_LEVEL lives on the Web & Logs tab now, so the Scheduling tab only
    // hosts the scheduler card (WEBUI_PORT coverage renders the service view).
    expect(screen.queryByTestId('settings-field-LOG_LEVEL')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '删除时间' })[0]).toHaveAttribute('data-size', 'default');
    const enabledSwitch = screen.getByTestId('scheduler-enabled-switch');
    expect(enabledSwitch).toHaveAttribute('role', 'switch');
    expect(enabledSwitch).toHaveClass('h-11', 'w-11');
    expect(enabledSwitch.firstElementChild).toHaveClass('h-6', 'w-10');
    const timeInput = screen.getByTestId('scheduler-time-input-0');
    expect(timeInput).toHaveClass('h-9', 'min-h-9');
    expect(timeInput).toHaveAttribute('type', 'button');

    fireEvent.click(timeInput);
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-hour="10"]')!);
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-minute="30"]')!);
    fireEvent.click(screen.getByRole('button', { name: '确定' }));

    expect(setDraftValue).toHaveBeenCalledWith('SCHEDULE_TIMES', '10:30,15:10');

    const callCountBeforeAdd = setDraftValue.mock.calls.length;
    fireEvent.click(screen.getByTestId('scheduler-add-time-button'));
    const newTimeInput = screen.getByTestId('scheduler-new-time-input');
    expect(setDraftValue).toHaveBeenCalledTimes(callCountBeforeAdd);
    await waitFor(() => expect(newTimeInput).toHaveAttribute('aria-expanded', 'true'));
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-hour="18"]')!);
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-minute="30"]')!);
    fireEvent.click(screen.getByRole('button', { name: '确定' }));
    expect(setDraftValue).toHaveBeenLastCalledWith('SCHEDULE_TIMES', '09:20,15:10,18:30');

    fireEvent.click(screen.getByTestId('scheduler-run-now-button'));

    await waitFor(() => expect(runSchedulerNow).toHaveBeenCalledTimes(1));
  });

  it('commits valid values from the shared schedule time picker', async () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
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
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00,15:10',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    const timeInput = await screen.findByTestId('scheduler-time-input-0');

    expect(timeInput).toHaveAttribute('type', 'button');
    fireEvent.click(timeInput);
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-hour="09"]')!);
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-minute="05"]')!);
    fireEvent.click(screen.getByRole('button', { name: '确定' }));
    expect(setDraftValue).toHaveBeenCalledWith('SCHEDULE_TIMES', '09:05,15:10');
  });

  it('shows an error when run-now is rejected because analysis is already running', async () => {
    runSchedulerNow.mockRejectedValueOnce(new Error('A scheduled analysis is already running'));
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
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
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    fireEvent.click(await screen.findByTestId('scheduler-run-now-button'));

    await waitFor(() => expect(runSchedulerNow).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/A scheduled analysis is already running/)).toBeInTheDocument();
  });

  it('does not show a failed run as the last successful scheduler run', async () => {
    const configState = buildSystemConfigState();
    getSchedulerStatus.mockImplementationOnce(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      return {
        enabled: true,
        running: false,
        scheduleTimes: ['18:00'],
        nextRunAt: null,
        lastRunAt: '2026-06-21T17:00:00+08:00',
        lastSuccessAt: null,
        lastError: 'analysis failed',
      };
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
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
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('scheduler-last-success')).toHaveTextContent('-');
      expect(screen.getByTestId('scheduler-last-error')).toHaveTextContent('analysis failed');
    });
  });

  it('shows active runtime scheduler state even when saved schedule flag is false', async () => {
    const configState = buildSystemConfigState();
    getSchedulerStatus.mockImplementationOnce(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      return {
        enabled: true,
        running: false,
        scheduleTimes: ['18:00'],
        nextRunAt: null,
        lastRunAt: null,
        lastSuccessAt: null,
        lastError: null,
      };
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'false',
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
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    const enabledSwitch = await screen.findByTestId('scheduler-enabled-switch');
    await waitFor(() => expect(enabledSwitch).toBeChecked());

    fireEvent.click(enabledSwitch);

    expect(setDraftValue).toHaveBeenCalledWith('SCHEDULE_ENABLED', 'false');
    await waitFor(() => expect(enabledSwitch).not.toBeChecked());
  });

  it('keeps local scheduler toggle edits when runtime and saved states are initially consistent', async () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
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
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));
    render(<SettingsPage />);

    const enabledSwitch = await screen.findByTestId('scheduler-enabled-switch');
    expect(enabledSwitch).toBeChecked();

    fireEvent.click(enabledSwitch);

    expect(setDraftValue).toHaveBeenCalledWith('SCHEDULE_ENABLED', 'false');
    await waitFor(() => expect(screen.getByTestId('scheduler-enabled-switch')).not.toBeChecked());

    const refreshButton = screen.getByTestId('scheduler-refresh-status-button');
    fireEvent.click(refreshButton);
    await waitFor(() => expect(screen.getByTestId('scheduler-enabled-switch')).not.toBeChecked());
  });

  it('can reconcile runtime scheduler state when runtime is enabled but saved value is disabled', async () => {
    save.mockResolvedValue({ success: true });
    getChangedItems.mockReturnValue([]);
    const configState = buildSystemConfigState();
    getSchedulerStatus.mockResolvedValueOnce({
      enabled: true,
      running: false,
      scheduleTimes: ['18:00'],
      nextRunAt: null,
      lastRunAt: null,
      lastSuccessAt: null,
      lastError: null,
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      hasDirty: false,
      dirtyCount: 0,
      getChangedItems: () => [],
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'false',
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
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(screen.queryByRole('button', { name: /保存配置/ })).not.toBeInTheDocument();

    const enabledSwitch = await screen.findByTestId('scheduler-enabled-switch');
    await waitFor(() => expect(enabledSwitch).toBeChecked());
    fireEvent.click(enabledSwitch);

    await waitFor(() => expect(enabledSwitch).not.toBeChecked());
    await waitFor(() => expect(save).toHaveBeenCalledWith(
      [{ key: 'SCHEDULE_ENABLED', value: 'false' }],
      { silent: true },
    ), { timeout: 2000 });
  });

  it('can reconcile runtime scheduler state when runtime is disabled but saved value is enabled', async () => {
    save.mockResolvedValue({ success: true });
    getChangedItems.mockReturnValue([]);
    const configState = buildSystemConfigState();
    getSchedulerStatus.mockResolvedValueOnce({
      enabled: false,
      running: false,
      scheduleTimes: ['18:00'],
      nextRunAt: null,
      lastRunAt: null,
      lastSuccessAt: null,
      lastError: null,
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      hasDirty: false,
      dirtyCount: 0,
      getChangedItems: () => [],
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
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
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(screen.queryByRole('button', { name: /保存配置/ })).not.toBeInTheDocument();

    const enabledSwitch = await screen.findByTestId('scheduler-enabled-switch');
    await waitFor(() => expect(enabledSwitch).not.toBeChecked());
    fireEvent.click(enabledSwitch);

    await waitFor(() => expect(enabledSwitch).toBeChecked());
    await waitFor(() => expect(save).toHaveBeenCalledWith(
      [{ key: 'SCHEDULE_ENABLED', value: 'true' }],
      { silent: true },
    ), { timeout: 2000 });
  });

  it('refreshes scheduler status after autosaving scheduler settings', async () => {
    const configState = buildSystemConfigState();
    getSchedulerStatus
      .mockResolvedValueOnce({
        enabled: false,
        running: false,
        scheduleTimes: [],
        nextRunAt: null,
        lastRunAt: null,
        lastSuccessAt: null,
        lastError: null,
      })
      .mockResolvedValueOnce({
        enabled: true,
        running: false,
        scheduleTimes: ['09:20', '15:10'],
        nextRunAt: '2026-06-21T09:20:00+08:00',
        lastRunAt: null,
        lastSuccessAt: null,
        lastError: null,
      });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'SCHEDULE_ENABLED', value: 'true' }],
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'false',
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
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '09:20,15:10',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(await screen.findByText('未启用')).toBeInTheDocument();

    await waitFor(() => expect(getSchedulerStatus).toHaveBeenCalledTimes(2), { timeout: 2000 });
    expect(await screen.findByText('已启用')).toBeInTheDocument();
  });

  it('refreshes AlphaSift state when the enable flow fails', async () => {
    const configState = buildSystemConfigState();
    alphasiftEnable.mockRejectedValueOnce(new Error('config update failed'));
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      activeSubCategory: 'providers',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: [
          {
            key: 'ALPHASIFT_ENABLED',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'ALPHASIFT_ENABLED',
              category: 'data_source',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 16,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: '开启选股' }));

    await waitFor(() => expect(alphasiftEnable).toHaveBeenCalledTimes(1));
    expect(updateSystemConfig).not.toHaveBeenCalled();
    expect(alphasiftInstall).not.toHaveBeenCalled();
    expect(refreshAfterExternalSave).toHaveBeenCalledWith(['ALPHASIFT_ENABLED']);
  });
}
