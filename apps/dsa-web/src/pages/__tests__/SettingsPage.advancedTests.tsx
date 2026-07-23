import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import SettingsPageTestHarness from './SettingsPage.testHarness';

const {
  SettingsPage,
  buildSystemConfigState,
  createDesktopRuntime,
  desktopCheckForUpdates,
  desktopGetUpdateState,
  desktopInstallDownloadedUpdate,
  desktopOpenReleasePage,
  exportEnv,
  getSchedulerStatus,
  importEnv,
  load,
  mockedAnchorClick,
  refreshStatus,
  routerSearchParamsMock,
  settingsPanelErrorBoundary,
  useAdvancedConfigState,
  useAuthMock,
  useSystemConfigMock,
} = SettingsPageTestHarness;

export function registerSettingsPageAdvancedTests(): void {
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
}
