import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { registerSettingsPageIntegrationTests } from './SettingsPage.integrationTests';
import { registerSettingsPageLlmTests } from './SettingsPage.llmTests';
import { registerSettingsPageOverviewTests } from './SettingsPage.overviewTests';
import SettingsPageTestHarness from './SettingsPage.testHarness';

const {
  SettingsPage,
  alphasiftEnable,
  alphasiftInstall,
  buildSystemConfigState,
  createDesktopRuntime,
  desktopCheckForUpdates,
  desktopGetUpdateState,
  desktopInstallDownloadedUpdate,
  desktopOpenReleasePage,
  exportEnv,
  getChangedItems,
  getSchedulerStatus,
  importEnv,
  load,
  mockedAnchorClick,
  refreshAfterExternalSave,
  refreshStatus,
  routerSearchParamsMock,
  runSchedulerNow,
  save,
  setDraftValue,
  settingsPanelErrorBoundary,
  updateSystemConfig,
  useAdvancedConfigState,
  useAuthMock,
  useSystemConfigMock,
  registerSettingsPageBeforeEach,
} = SettingsPageTestHarness;

describe('SettingsPage', () => {
  registerSettingsPageBeforeEach();
  registerSettingsPageOverviewTests();
  registerSettingsPageLlmTests();
  registerSettingsPageIntegrationTests();
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

  it('passes LLM channel support keys to the channel editor without rendering them as generic fields', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...buildSystemConfigState().itemsByCategory,
        ai_model: [
          {
            key: 'LLM_CHANNELS',
            value: 'my_proxy',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'LLM_CHANNELS',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'textarea',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 1,
              uiPlacement: 'model_access' as const,
            },
          },
          {
            key: 'LITELLM_MODEL',
            value: 'gpt-5.0',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'LITELLM_MODEL',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 2,
              uiPlacement: 'task_routing' as const,
            },
          },
          {
            key: 'OPENAI_BASE_URL',
            value: 'https://api.openai.com/v1',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'OPENAI_BASE_URL',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 3,
              uiPlacement: 'hidden_legacy' as const,
            },
          },
          {
            key: 'OPENAI_MODEL',
            value: 'gpt-5.0',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'OPENAI_MODEL',
              category: 'ai_model',
              isMasked: false,
              dataType: 'string',
              uiControl: 'text',
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 4,
              uiPlacement: 'hidden_legacy' as const,
            },
          },
          {
            key: 'LLM_MY_PROXY_API_KEY',
            value: 'sk-test',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'LLM_MY_PROXY_API_KEY',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'password',
              isSensitive: true,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 9000,
              uiPlacement: 'model_access' as const,
            },
          },
          {
            key: 'LLM_MY_PROXY_MODELS',
            value: 'gpt-5.5',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'LLM_MY_PROXY_MODELS',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 9000,
              uiPlacement: 'model_access' as const,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    const llmEditorItems = await screen.findByTestId('llm-channel-editor-items');
    expect(llmEditorItems).toHaveTextContent('LLM_CHANNELS');
    expect(llmEditorItems).toHaveTextContent('LITELLM_MODEL');
    expect(llmEditorItems).toHaveTextContent('OPENAI_BASE_URL');
    expect(llmEditorItems).toHaveTextContent('OPENAI_MODEL');
    expect(llmEditorItems).toHaveTextContent('LLM_MY_PROXY_API_KEY');
    expect(llmEditorItems).toHaveTextContent('LLM_MY_PROXY_MODELS');
    expect(screen.queryByTestId('settings-field-LITELLM_MODEL')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-OPENAI_BASE_URL')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-OPENAI_MODEL')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-LLM_MY_PROXY_API_KEY')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-LLM_MY_PROXY_MODELS')).not.toBeInTheDocument();
  });

  it.each([
    ['missing', undefined],
    ['unknown', 'future_surface'],
  ])('quarantines AI fields with %s uiPlacement in Advanced as read-only diagnostics', async (_case, uiPlacement) => {
    const configState = buildSystemConfigState();
    const unsafeItem = {
      key: 'OPENAI_API_KEY',
      value: 'saved-secret',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'OPENAI_API_KEY',
        category: 'ai_model' as const,
        dataType: 'string' as const,
        uiControl: 'password' as const,
        isSensitive: true,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
        ...(uiPlacement ? { uiPlacement: uiPlacement as never } : {}),
      },
    };
    const unsafeModelAccessItem = {
      ...unsafeItem,
      key: 'LLM_CHANNELS',
      value: 'openai',
      isMasked: false,
      schema: {
        ...unsafeItem.schema,
        key: 'LLM_CHANNELS',
        uiControl: 'textarea' as const,
        isSensitive: false,
      },
    };
    const state = buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: { ...configState.itemsByCategory, ai_model: [unsafeModelAccessItem, unsafeItem] },
    });
    useSystemConfigMock.mockReturnValue(state);
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'connections' });
    const { rerender } = render(<SettingsPage />);
    expect(screen.queryByTestId('settings-field-OPENAI_API_KEY')).not.toBeInTheDocument();
    expect(screen.getByTestId('llm-channel-editor-items')).toHaveAttribute('data-disabled', 'true');

    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'diagnostics' });
    rerender(<SettingsPage />);
    const field = screen.getByTestId('settings-field-OPENAI_API_KEY');
    expect(field).toHaveAttribute('data-readonly', 'true');
    expect(field).toHaveTextContent(`schema_ui_placement_${_case}`);
  });

  it('keeps an unknown schema condition visible but read-only with a diagnostic', () => {
    const configState = buildSystemConfigState();
    const conditionalItem = {
      key: 'LOG_LEVEL',
      value: 'INFO',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LOG_LEVEL',
        category: 'system' as const,
        dataType: 'string' as const,
        uiControl: 'text' as const,
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
        contract: {
          requirement: 'optional' as const,
          visibleWhen: [{ key: 'MODE', operator: 'regex' as never, value: '^safe$' }],
        },
      },
    };
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: { ...configState.itemsByCategory, system: [conditionalItem] },
    }));
    // LOG_LEVEL is a log-group field and renders on the Web & Logs tab.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'service' });

    render(<SettingsPage />);
    const field = screen.getByTestId('settings-field-LOG_LEVEL');
    expect(field).toHaveAttribute('data-readonly', 'true');
    expect(field).toHaveTextContent('schema_condition_unknown');
  });

  it('never renders legacy provider credential fields even without configured channels', async () => {
    // Model Access is the only entry for provider credentials: legacy keys
    // like OPENAI_API_KEY stay backend-compatible but must not surface as
    // generic fields, channels configured or not.
    const legacyProviderItems = ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'AIHUBMIX_KEY'].map((key, index) => ({
      key,
      value: '',
      rawValueExists: false,
      isMasked: false,
      schema: {
        key,
        category: 'ai_model',
        dataType: 'string',
        uiControl: 'password',
        isSensitive: true,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: index + 1,
        // Mirrors the backend registry: legacy provider keys stay
        // backend-compatible but are never rendered as generic fields.
        uiPlacement: 'hidden_legacy' as const,
      },
    }));
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...buildSystemConfigState().itemsByCategory,
        ai_model: legacyProviderItems,
      },
    }));

    render(<SettingsPage />);

    await screen.findByTestId('llm-channel-editor-items');
    for (const item of legacyProviderItems) {
      expect(screen.queryByTestId(`settings-field-${item.key}`)).not.toBeInTheDocument();
    }
    expect(screen.queryByText('模型供应商')).not.toBeInTheDocument();
  });

  it('renders notification test panel before notification fields', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'notification' }));

    render(<SettingsPage />);

    expect(screen.getByText('通知测试面板:WECHAT_WEBHOOK_URL')).toBeInTheDocument();
    expect(screen.getByText('WECHAT_WEBHOOK_URL')).toBeInTheDocument();
    expect(settingsPanelErrorBoundary).toHaveBeenCalledWith('通知测试');
    expect(settingsPanelErrorBoundary).toHaveBeenCalledWith('通知设置');
  });

  it('uses browser and backend logs in settings panel diagnostic hints outside desktop runtime', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'notification' }));

    render(<SettingsPage />);

    expect(screen.getAllByText(/浏览器开发者工具控制台与后端日志/)).toHaveLength(2);
    expect(screen.queryByText('desktop.log')).not.toBeInTheDocument();
  });

  it('uses desktop log in settings panel diagnostic hints during desktop runtime', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'notification' }));
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    render(<SettingsPage />);

    expect(screen.getAllByText('desktop.log')).toHaveLength(2);
    expect(screen.queryByText(/浏览器开发者工具控制台与后端日志/)).not.toBeInTheDocument();
  });

  it('keeps env backup actions in Advanced outside desktop runtime', () => {
    const { rerender } = render(<SettingsPage />);

    expect(screen.queryByRole('heading', { name: '配置备份' })).not.toBeInTheDocument();

    useAdvancedConfigState();
    rerender(<SettingsPage />);

    expect(screen.getByRole('heading', { name: '配置备份' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导出 .env' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导入 .env' })).toBeInTheDocument();
    expect(screen.getByText(/Docker 部署中/)).toHaveTextContent('ENV_FILE');
  });

  it('disables env backup actions when web auth is not enabled', () => {
    useAuthMock.mockReturnValue({
      authEnabled: false,
      passwordChangeable: false,
      refreshStatus,
    });
    useAdvancedConfigState();

    render(<SettingsPage />);

    expect(screen.getByText(/当前 Web 端未开启管理员鉴权/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导出 .env' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '导入 .env' })).toBeDisabled();
  });

  it('uses live auth state for env backup availability instead of loaded config items', () => {
    const configState = buildSystemConfigState();
    useAdvancedConfigState({
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: configState.itemsByCategory.system.map((item) => (
          item.key === 'ADMIN_AUTH_ENABLED' ? { ...item, value: 'false' } : item
        )),
      },
    });
    useAuthMock.mockReturnValue({
      authEnabled: true,
      passwordChangeable: true,
      refreshStatus,
    });

    render(<SettingsPage />);

    expect(screen.queryByText(/当前 Web 端未开启管理员鉴权/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导出 .env' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: '导入 .env' })).not.toBeDisabled();
  });

  it('exports saved env from config backup actions', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };
    useAdvancedConfigState();

    render(<SettingsPage />);

    vi.clearAllMocks();

    fireEvent.click(screen.getByRole('button', { name: '导出 .env' }));

    await waitFor(() => expect(exportEnv).toHaveBeenCalledTimes(1));
    expect(mockedAnchorClick).toHaveBeenCalledTimes(1);
    expect(load).not.toHaveBeenCalled();
  });

  it('asks for confirmation before importing when local drafts exist', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };
    useAdvancedConfigState({
      hasDirty: true,
      dirtyCount: 2,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    });

    render(<SettingsPage />);

    vi.clearAllMocks();

    fireEvent.click(screen.getByRole('button', { name: '导入 .env' }));

    expect(await screen.findByText('导入会覆盖当前草稿')).toBeInTheDocument();
    expect(importEnv).not.toHaveBeenCalled();
  });

  it('reloads config after successful env import', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };
    useAdvancedConfigState();

    render(<SettingsPage />);

    vi.clearAllMocks();

    const input = document.querySelector('input[type="file"]');
    expect(input).not.toBeNull();

    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [new File(['STOCK_LIST=300750\n'], 'desktop-backup.env', { type: 'text/plain' })],
      },
    });

    await waitFor(() => expect(importEnv).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
  });

  it('imports scheduler settings from Advanced without mounting runtime controls', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };
    const configState = buildSystemConfigState();
    importEnv.mockResolvedValueOnce({
      success: true,
      configVersion: 'v2',
      appliedCount: 2,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['SCHEDULE_ENABLED', 'SCHEDULE_TIMES'],
      warnings: [],
    });
    useAdvancedConfigState({
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
    });

    render(<SettingsPage />);

    vi.clearAllMocks();

    const input = document.querySelector('input[type="file"]');
    expect(input).not.toBeNull();

    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [new File(['SCHEDULE_ENABLED=true\nSCHEDULE_TIMES=09:20,15:10\n'], 'desktop-backup.env', { type: 'text/plain' })],
      },
    });

    await waitFor(() => expect(importEnv).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    expect(getSchedulerStatus).not.toHaveBeenCalled();
  });

  it('shows an error when env import succeeds but reload fails', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };
    load.mockResolvedValue(false);
    useAdvancedConfigState();

    render(<SettingsPage />);

    vi.clearAllMocks();
    load.mockResolvedValue(false);

    const input = document.querySelector('input[type="file"]');
    expect(input).not.toBeNull();

    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [new File(['STOCK_LIST=300750\n'], 'desktop-backup.env', { type: 'text/plain' })],
      },
    });

    await waitFor(() => expect(importEnv).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    expect(screen.getByText('配置已导入但刷新失败')).toBeInTheDocument();
    expect(screen.getByText('备份已导入，但重新加载配置失败，请手动重载页面。')).toBeInTheDocument();
    expect(screen.queryByText('已导入 .env 备份并重新加载配置。')).not.toBeInTheDocument();
  });

  it('renders desktop update notice when a newer release is available', async () => {
    desktopGetUpdateState.mockResolvedValue({
      status: 'update-available',
      currentVersion: '3.12.0',
      latestVersion: '3.13.0',
      releaseUrl: 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0',
      message: '发现新版本 3.13.0，可前往 GitHub Releases 下载更新。',
    });
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'about' });
    render(<SettingsPage />);

    expect(await screen.findByText('发现新版本')).toBeInTheDocument();
    expect(screen.getByText(/当前 3\.12\.0，最新 3\.13\.0/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '前往下载' })).toBeInTheDocument();
  });

  it('checks desktop updates on demand and renders the latest-version state', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'about' });
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole('button', { name: '检查更新' }));

    await waitFor(() => expect(desktopCheckForUpdates).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('已是最新版本')).toBeInTheDocument();
    expect(screen.getByText('当前桌面端已是最新版本。')).toBeInTheDocument();
  });

  it('opens GitHub release page from desktop update notice', async () => {
    desktopGetUpdateState.mockResolvedValue({
      status: 'update-available',
      currentVersion: '3.12.0',
      latestVersion: '3.13.0',
      releaseUrl: 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0',
      message: '发现新版本 3.13.0，可前往 GitHub Releases 下载更新。',
    });
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'about' });
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole('button', { name: '前往下载' }));

    await waitFor(() => {
      expect(desktopOpenReleasePage).toHaveBeenCalledWith(
        'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0'
      );
    });
  });

  it('renders downloaded desktop update and starts install on demand', async () => {
    desktopGetUpdateState.mockResolvedValue({
      status: 'update-downloaded',
      updateMode: 'auto',
      currentVersion: '3.12.0',
      latestVersion: '3.13.0',
      releaseUrl: 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0',
      message: '新版本 3.13.0 已下载，可重启应用完成安装。',
      downloadPercent: 100,
    });
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'about' });
    render(<SettingsPage />);

    expect(await screen.findByText('更新已下载')).toBeInTheDocument();
    expect(screen.getByText('新版本 3.13.0 已下载，可重启应用完成安装。')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '重启安装' }));

    await waitFor(() => expect(desktopInstallDownloadedUpdate).toHaveBeenCalledTimes(1));
  });
});
