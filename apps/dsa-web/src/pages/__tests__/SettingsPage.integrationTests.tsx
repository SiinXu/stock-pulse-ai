import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import { loadUiLanguageTranslations } from '../../i18n/translations';
import { getFieldTitle } from '../../utils/systemConfigI18n';
import SettingsPageTestHarness from './SettingsPage.testHarness';

const {
  SettingsPage,
  TEST_CONNECTION_NAME_FIELD,
  TEST_PROVIDER_ID_FIELD,
  alphasiftEnable,
  alphasiftInstall,
  buildSystemConfigState,
  getChangedItems,
  getLlmProviderCatalog,
  getSetupStatus,
  notifyAlphaSiftConfigChanged,
  notifySystemConfigChanged,
  refreshAfterExternalSave,
  routerSearchParamsMock,
  save,
  updateSystemConfig,
  useSystemConfigMock,
  withTestConnectionCoreFields,
} = SettingsPageTestHarness;

export function registerSettingsPageIntegrationTests(): void {
  it('splits notification fields so Reports and Alerts render independent field sets', () => {
    const notifyField = (key: string, uiControl = 'text') => ({
      key,
      value: '',
      rawValueExists: false,
      isMasked: false,
      schema: {
        key,
        category: 'notification',
        dataType: 'string',
        uiControl,
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
      },
    });
    const notificationItems = [
      notifyField('REPORT_TYPE'),
      notifyField('REPORT_LANGUAGE'),
      notifyField('NOTIFICATION_ALERT_CHANNELS'),
      notifyField('NOTIFICATION_QUIET_HOURS'),
      notifyField('WECHAT_WEBHOOK_URL'),
    ];
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'notification',
      itemsByCategory: { ...configState.itemsByCategory, notification: notificationItems },
    }));

    // Reports section: only report-output fields; no delivery-rule or channel fields.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'reports', view: 'output' });
    const { rerender } = render(<SettingsPage />);
    expect(screen.getByTestId('settings-field-REPORT_TYPE')).toBeInTheDocument();
    expect(screen.getByTestId('settings-field-REPORT_LANGUAGE')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-WECHAT_WEBHOOK_URL')).not.toBeInTheDocument();

    // Alerts Push Routing tab: routing fields only; no report-output fields.
    // The retired `rules` view id keeps back-compat by normalizing to routing.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'rules' });
    rerender(<SettingsPage />);
    expect(screen.getByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-NOTIFICATION_QUIET_HOURS')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-REPORT_TYPE')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-WECHAT_WEBHOOK_URL')).not.toBeInTheDocument();

    // Alerts Behavior & Limits tab: rate/quiet-hour fields move here.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'behavior' });
    rerender(<SettingsPage />);
    expect(screen.getByTestId('settings-field-NOTIFICATION_QUIET_HOURS')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS')).not.toBeInTheDocument();
  });

  it('limits channel routing options to configured channels and guides setup when none exist', () => {
    const routingItem = (options: string[]) => ({
      key: 'NOTIFICATION_ALERT_CHANNELS',
      value: '',
      rawValueExists: false,
      isMasked: false,
      schema: {
        key: 'NOTIFICATION_ALERT_CHANNELS',
        category: 'notification',
        dataType: 'array',
        uiControl: 'textarea',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: options.map((option) => ({ label: option, value: option })),
        validation: { allowed_values: options, multi_value: true, delimiter: ',' },
        displayOrder: 1,
      },
    });
    const channelItem = (key: string, value: string) => ({
      key,
      value,
      rawValueExists: value !== '',
      isMasked: false,
      schema: {
        key,
        category: 'notification',
        dataType: 'string',
        uiControl: 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 2,
      },
    });
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'notification',
      configuredNotificationChannels: ['wechat'],
      itemsByCategory: {
        ...configState.itemsByCategory,
        notification: [
          routingItem(['wechat', 'feishu', 'custom']),
          channelItem('WECHAT_WEBHOOK_URL', 'https://wx.example/hook'),
          channelItem('CUSTOM_WEBHOOK_URLS', ''),
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'rules' });

    // Only channels with a configured key stay selectable.
    const { rerender, unmount } = render(<SettingsPage />);
    const field = screen.getByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS');
    expect(within(field).getByText('wechat')).toBeInTheDocument();
    expect(within(field).queryByText('feishu')).not.toBeInTheDocument();
    expect(within(field).queryByText('custom')).not.toBeInTheDocument();

    // With no configured channel at all, the field shows guidance that jumps
    // to the notification channels setup view.
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'notification',
      configuredNotificationChannels: [],
      itemsByCategory: {
        ...configState.itemsByCategory,
        notification: [
          routingItem(['wechat', 'feishu', 'custom']),
          channelItem('WECHAT_WEBHOOK_URL', ''),
        ],
      },
    }));
    // buildSystemConfigState resets the router params; restore the alerts view.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'rules' });
    rerender(<SettingsPage />);
    const emptyField = screen.getByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS');
    expect(within(emptyField).getByText('—')).toBeInTheDocument();
    const emptyBanner = screen.getByTestId('channel-routing-empty-banner');
    expect(within(emptyBanner).getByText('尚未配置任何通知渠道，配置成功后才能在这里选择接收渠道。')).toBeInTheDocument();
    fireEvent.click(within(emptyBanner).getByRole('button', { name: '去配置通知渠道' }));
    const [nextParams] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(nextParams?.get('section')).toBe('notifications');
    expect(nextParams?.get('view')).toBe('channels');

    // During a rolling upgrade an old backend omits the authoritative channel
    // status. Keep the catalog and stored selection usable instead of treating
    // unknown as a confirmed empty set.
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'notification',
      configuredNotificationChannels: null,
      itemsByCategory: {
        ...configState.itemsByCategory,
        notification: [
          { ...routingItem(['wechat', 'feishu', 'custom']), value: 'feishu' },
          channelItem('WECHAT_WEBHOOK_URL', '******'),
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'rules' });
    rerender(<SettingsPage />);
    const unknownField = screen.getByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS');
    expect(within(unknownField).getByText('feishu')).toBeInTheDocument();
    expect(screen.queryByTestId('channel-routing-empty-banner')).not.toBeInTheDocument();
    expect(screen.queryByText('尚未配置任何通知渠道，配置成功后才能在这里选择接收渠道。')).not.toBeInTheDocument();
    expect(within(unknownField).getByText('wechat')).toBeInTheDocument();
    expect(within(unknownField).getByText('custom')).toBeInTheDocument();
    unmount();
  });

  it('keeps masked ntfy and Gotify channels available from the backend routing status', () => {
    const routingItem = {
      key: 'NOTIFICATION_ALERT_CHANNELS',
      value: '',
      rawValueExists: false,
      isMasked: false,
      schema: {
        key: 'NOTIFICATION_ALERT_CHANNELS',
        category: 'notification',
        dataType: 'array',
        uiControl: 'textarea',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: ['ntfy', 'gotify', 'wechat'].map((option) => ({ label: option, value: option })),
        validation: {
          allowed_values: ['ntfy', 'gotify', 'wechat'],
          multi_value: true,
          delimiter: ',',
        },
        displayOrder: 1,
      },
    };
    const maskedChannelItem = (key: string) => ({
      key,
      value: '******',
      rawValueExists: true,
      isMasked: true,
      schema: {
        key,
        category: 'notification',
        dataType: 'string',
        uiControl: 'password',
        isSensitive: true,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 2,
      },
    });
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'notification',
      configuredNotificationChannels: ['ntfy', 'gotify'],
      itemsByCategory: {
        ...configState.itemsByCategory,
        notification: [
          routingItem,
          maskedChannelItem('NTFY_URL'),
          maskedChannelItem('GOTIFY_URL'),
          maskedChannelItem('GOTIFY_TOKEN'),
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'rules' });

    render(<SettingsPage />);

    const field = screen.getByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS');
    expect(within(field).getByText('ntfy')).toBeInTheDocument();
    expect(within(field).getByText('gotify')).toBeInTheDocument();
    expect(within(field).queryByText('wechat')).not.toBeInTheDocument();
  });

  it('lists validation errors and jumps to the errored field section from any section', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      issueByKey: {
        WECHAT_WEBHOOK_URL: [
          { key: 'WECHAT_WEBHOOK_URL', code: 'invalid', message: '企业微信 Webhook 地址格式不正确', severity: 'error' },
        ],
      },
    }));
    // Start on a section that does not own the errored field.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'runtime' });

    render(<SettingsPage />);

    expect(screen.getByText('有 1 项配置需要修正')).toBeInTheDocument();
    expect(screen.getByText('企业微信 Webhook 地址格式不正确')).toBeInTheDocument();

    // Clicking the summary entry navigates to the section that owns the field.
    fireEvent.click(screen.getByRole('button', { name: /前往修正/ }));
    const [nextParams] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(nextParams?.get('section')).toBe('notifications');
    expect(nextParams?.get('view')).toBe('channels');
  });

  it.each(['de', 'ja', 'zh-TW'] as const)(
    'uses the per-field %s title for a known field without a help key in the validation error summary',
    async (language) => {
      const configState = buildSystemConfigState();
      useSystemConfigMock.mockReturnValue(buildSystemConfigState({
        activeCategory: 'system',
        itemsByCategory: {
          ...configState.itemsByCategory,
          ai_model: [
            ...configState.itemsByCategory.ai_model,
            {
              key: 'OPENAI_VISION_MODEL',
              value: 'gpt-4o',
              rawValueExists: true,
              isMasked: false,
              schema: {
                key: 'OPENAI_VISION_MODEL',
                title: 'OpenAI Vision Model',
                category: 'ai_model',
                dataType: 'string',
                uiControl: 'text',
                isSensitive: false,
                isRequired: false,
                isEditable: true,
                options: [],
                validation: {},
                displayOrder: 2,
              },
            },
          ],
        },
        issueByKey: {
          OPENAI_VISION_MODEL: [
            {
              key: 'OPENAI_VISION_MODEL',
              code: 'invalid',
              message: 'Unsupported backend',
              severity: 'error',
            },
          ],
        },
      }));
      routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'runtime' });
      await loadUiLanguageTranslations(language);
      const expectedTitle = getFieldTitle('OPENAI_VISION_MODEL', undefined, language);

      render(
        <UiLanguageProvider initialLanguage={language}>
          <SettingsPage />
        </UiLanguageProvider>,
      );

      expect(expectedTitle).not.toBe('OpenAI Vision Model');
      expect(screen.getByRole('button', { name: `前往修正: ${expectedTitle}` })).toBeInTheDocument();
      expect(screen.queryByText('OpenAI Vision Model')).not.toBeInTheDocument();
    },
  );

  it('routes a dynamic connection error to Model Access and sends an explicit field-focus request', async () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        ai_model: [
          ...configState.itemsByCategory.ai_model,
          {
            key: 'LLM_OPENAI_API_KEY',
            value: '******',
            rawValueExists: true,
            isMasked: true,
            schema: {
              key: 'LLM_OPENAI_API_KEY',
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
        ],
      },
      issueByKey: {
        LLM_OPENAI_API_KEY: [
          { key: 'LLM_OPENAI_API_KEY', code: 'invalid', message: 'API 密钥无效', severity: 'error' },
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'runtime' });

    const { rerender } = render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: /前往修正/ }));

    const [nextParams] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(nextParams?.get('section')).toBe('ai_models');
    expect(nextParams?.get('view')).toBe('connections');

    routerSearchParamsMock.params = nextParams;
    rerender(<SettingsPage />);
    expect(await screen.findByTestId('llm-channel-focus-request')).toHaveTextContent('LLM_OPENAI_API_KEY');
  });

  it('warns that changed restart-required settings need a restart to take effect', () => {
    const restartField = {
      key: 'WEBUI_PORT',
      value: '8001',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'WEBUI_PORT',
        category: 'system',
        dataType: 'integer',
        uiControl: 'number',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 2,
        warningCodes: ['restart_required'],
      },
    };
    const configState = buildSystemConfigState();
    // No dirty restart field -> no notice.
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: { ...configState.itemsByCategory, system: [restartField] },
      dirtyKeys: [],
    }));
    const { rerender } = render(<SettingsPage />);
    expect(screen.queryByText(/部分已修改的配置需要重启服务后才会生效/, { exact: false })).not.toBeInTheDocument();

    // The restart-required field is now dirty -> the page-level notice shows.
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: { ...configState.itemsByCategory, system: [restartField] },
      dirtyKeys: ['WEBUI_PORT'],
    }));
    rerender(<SettingsPage />);
    expect(screen.getByText(/部分已修改的配置需要重启服务后才会生效/, { exact: false })).toBeInTheDocument();
  });

  it('moves internal HMAC keys to the top-level Advanced section, out of Connections', () => {
    const aiField = (key: string, value: string, displayOrder: number, uiControl = 'text') => ({
      key,
      value,
      rawValueExists: Boolean(value),
      isMasked: false,
      schema: {
        key,
        category: 'ai_model',
        dataType: 'string',
        uiControl,
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder,
      },
    });
    const configState = buildSystemConfigState();
    const withAiItems = () => buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: {
        ...configState.itemsByCategory,
        ai_model: [
          aiField('LLM_CHANNELS', 'openai', 1),
          aiField('LLM_USAGE_HMAC_SECRET', '', 9, 'password'),
          aiField('LLM_USAGE_HMAC_KEY_VERSION', '1', 10),
        ],
      },
    });

    // Connections view: the internal HMAC keys no longer clutter it.
    useSystemConfigMock.mockReturnValue(withAiItems());
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'connections' });
    const { rerender } = render(<SettingsPage />);
    expect(screen.queryByTestId('settings-field-LLM_USAGE_HMAC_SECRET')).not.toBeInTheDocument();

    // Advanced Developer Diagnostics tab: renders the aggregated internal keys.
    useSystemConfigMock.mockReturnValue(withAiItems());
    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'diagnostics' });
    rerender(<SettingsPage />);
    expect(screen.getByTestId('settings-field-LLM_USAGE_HMAC_SECRET')).toBeInTheDocument();
    expect(screen.getByTestId('settings-field-LLM_USAGE_HMAC_KEY_VERSION')).toBeInTheDocument();
  });

  it('opens the first-run wizard from Overview and saves its minimal config', async () => {
    save.mockResolvedValue({ success: true });
    // The wizard entry is only the first-time path when setup is incomplete.
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LITELLM_MODEL'],
      checks: [],
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    // The entry button is enabled once the async provider catalog has loaded.
    await waitFor(() => expect(screen.getByRole('button', { name: '启动向导' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '启动向导' }));
    expect(screen.getByRole('dialog', { name: 'first-run-wizard' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'wizard apply' }));

    await waitFor(() => expect(save).toHaveBeenCalledWith([
      { key: 'LLM_CHANNELS', value: 'deepseek' },
      { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-wizard' },
    ]));
    // The wizard closes once the save succeeds.
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'first-run-wizard' })).not.toBeInTheDocument());
  });

  it('rejects a Wizard Connection payload at the page adapter under a partial schema', async () => {
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LITELLM_MODEL'],
      checks: [],
    });
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: [{
        key: 'models',
        dataType: 'array',
        isSensitive: false,
        isRequired: false,
        contract: { requirement: 'optional' },
      }],
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByRole('button', { name: '启动向导' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '启动向导' }));
    fireEvent.click(screen.getByRole('button', { name: 'wizard apply' }));

    await waitFor(() => expect(save).not.toHaveBeenCalled());
  });

  it('rejects a Wizard field that a complete schema marks read-only', async () => {
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LITELLM_MODEL'],
      checks: [],
    });
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([
        TEST_CONNECTION_NAME_FIELD,
        TEST_PROVIDER_ID_FIELD,
        {
          key: 'base_url',
          dataType: 'string',
          isSensitive: false,
          isRequired: false,
          contract: { requirement: 'inherited' },
        },
      ]),
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByRole('button', { name: '启动向导' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '启动向导' }));
    fireEvent.click(screen.getByRole('button', { name: 'wizard inject read-only field' }));

    await waitFor(() => expect(save).not.toHaveBeenCalled());
    expect(screen.getByRole('dialog', { name: 'first-run-wizard' })).toBeInTheDocument();
  });

  it('rejects a Wizard provider identity that is absent from the authoritative Catalog', async () => {
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LITELLM_MODEL'],
      checks: [],
    });
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([
        TEST_CONNECTION_NAME_FIELD,
        { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
        TEST_PROVIDER_ID_FIELD,
        { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
        { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
      ]),
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByRole('button', { name: '启动向导' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '启动向导' }));
    fireEvent.click(screen.getByRole('button', { name: 'wizard apply unknown provider' }));

    await waitFor(() => expect(save).not.toHaveBeenCalled());
    expect(screen.getByRole('dialog', { name: 'first-run-wizard' })).toBeInTheDocument();
  });

  it('hides the first-run wizard entry once setup is complete', async () => {
    getSetupStatus.mockResolvedValue({
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      checks: [],
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    // Configured users no longer see the first-run "Start wizard" entry — they
    // add a service from the model-access cards instead.
    await waitFor(() => expect(getSetupStatus).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '启动向导' })).not.toBeInTheDocument());
  });

  it('routes prompt cache settings to their explicit developer diagnostics placement', () => {
    const aiField = (key: string, displayOrder: number, value = '') => ({
      key,
      value,
      rawValueExists: Boolean(value),
      isMasked: false,
      schema: {
        key,
        category: 'ai_model',
        dataType: 'string',
        uiControl: key === 'LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL' ? 'select' : 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: key === 'LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL' ? ['off', 'basic', 'debug'] : [],
        validation: {},
        displayOrder,
        uiPlacement: 'developer_diagnostics' as const,
      },
    });
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: {
        ...configState.itemsByCategory,
        ai_model: [
          aiField('LITELLM_CONFIG', 10, './litellm.yaml'),
          aiField('LLM_PROMPT_CACHE_TELEMETRY_ENABLED', 20, 'true'),
          aiField('LLM_PROMPT_CACHE_HINTS_ENABLED', 21, 'false'),
          aiField('LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL', 22, 'off'),
        ],
      },
    }));

    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'connections' });
    const { rerender } = render(<SettingsPage />);
    expect(screen.queryByTestId('settings-field-LLM_PROMPT_CACHE_TELEMETRY_ENABLED')).not.toBeInTheDocument();

    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'diagnostics' });
    rerender(<SettingsPage />);
    expect(screen.getByTestId('settings-field-LLM_PROMPT_CACHE_TELEMETRY_ENABLED')).toBeInTheDocument();
    expect(screen.getByTestId('settings-field-LLM_PROMPT_CACHE_HINTS_ENABLED')).toBeInTheDocument();
    expect(screen.getByTestId('settings-field-LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL')).toBeInTheDocument();
  });

  it('notifies alphasift status update after its autosave group is persisted as false', async () => {
    save.mockResolvedValue({ success: true });
    getChangedItems.mockReturnValue([{ key: 'ALPHASIFT_ENABLED', value: 'false' }]);

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'ALPHASIFT_ENABLED', value: 'false' }],
    }));

    render(<SettingsPage />);

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
    expect(notifyAlphaSiftConfigChanged).toHaveBeenCalledTimes(1);
    expect(notifySystemConfigChanged).toHaveBeenCalledTimes(1);
    expect(alphasiftEnable).not.toHaveBeenCalled();
    expect(alphasiftInstall).not.toHaveBeenCalled();
  });

  it('runs the AlphaSift enable flow after autosave persists ALPHASIFT_ENABLED', async () => {
    save.mockResolvedValue({ success: true });
    getChangedItems.mockReturnValue([{ key: 'ALPHASIFT_ENABLED', value: 'true' }]);

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'ALPHASIFT_ENABLED', value: 'true' }],
    }));

    render(<SettingsPage />);

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
    expect(notifySystemConfigChanged).toHaveBeenCalledTimes(1);
    expect(alphasiftEnable).toHaveBeenCalledTimes(1);
    expect(alphasiftInstall).not.toHaveBeenCalled();
    expect(refreshAfterExternalSave).toHaveBeenCalledWith(['ALPHASIFT_ENABLED']);
  });

  it('does not notify alphasift status when another autosave group updates', async () => {
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'LLM_CHANNELS', value: 'primary,backup' }],
    }));

    render(<SettingsPage />);

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
    expect(notifySystemConfigChanged).toHaveBeenCalledTimes(1);
    expect(notifyAlphaSiftConfigChanged).not.toHaveBeenCalled();
  });

  it('runs AlphaSift enable flow from the settings card', async () => {
    const configState = buildSystemConfigState();
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
          {
            key: 'ALPHASIFT_INSTALL_SPEC',
            value: 'git+https://github.com/ZhuLinsen/alphasift.git@2c76b2b6074ae3bae01d52e5e830a4af3e3246b2',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'ALPHASIFT_INSTALL_SPEC',
              category: 'data_source',
              dataType: 'string',
              uiControl: 'password',
              isSensitive: true,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 17,
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

  it('does not render raw AlphaSift install spec in the settings card', () => {
    const privateInstallSpec = 'git+https://user:token@example.com/internal/alphasift.git';
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      activeSubCategory: 'providers',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: [
          {
            key: 'ALPHASIFT_ENABLED',
            value: 'true',
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
          {
            key: 'ALPHASIFT_INSTALL_SPEC',
            value: privateInstallSpec,
            rawValueExists: true,
            isMasked: true,
            schema: {
              key: 'ALPHASIFT_INSTALL_SPEC',
              category: 'data_source',
              dataType: 'string',
              uiControl: 'password',
              isSensitive: true,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 17,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(screen.getByText('启用内置 AlphaSift 实验性质选股能力。')).toBeInTheDocument();
    expect(screen.queryByText(privateInstallSpec)).not.toBeInTheDocument();
    expect(screen.queryByText(/安装来源/)).not.toBeInTheDocument();
  });

  it('maps ALPHASIFT_ENABLED to the AlphaSift card instead of a generic settings field', () => {
    const configState = buildSystemConfigState();
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
          {
            key: 'ALPHASIFT_INSTALL_SPEC',
            value: '******',
            rawValueExists: true,
            isMasked: true,
            schema: {
              key: 'ALPHASIFT_INSTALL_SPEC',
              category: 'data_source',
              dataType: 'string',
              uiControl: 'password',
              isSensitive: true,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 17,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(screen.getByRole('button', { name: '开启选股' })).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-ALPHASIFT_ENABLED')).not.toBeInTheDocument();
    const providersPanel = screen.getByTestId('data-providers-panel');
    expect(within(providersPanel).getByText('ALPHASIFT_INSTALL_SPEC')).toBeInTheDocument();
    expect(within(providersPanel).queryByText('ALPHASIFT_ENABLED')).not.toBeInTheDocument();
  });

  it('keeps data-source configuration visible on the page instead of behind a configuration dialog', () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      activeSubCategory: 'source',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: [
          {
            key: 'NEWS_MAX_AGE_DAYS',
            value: '3',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'NEWS_MAX_AGE_DAYS',
              category: 'data_source',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 1,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(screen.getByTestId('settings-field-NEWS_MAX_AGE_DAYS')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-configuration-card-数据源')).not.toBeInTheDocument();
  });

  it('keeps the provider directory on the page instead of behind a category-wide configuration dialog', () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      activeSubCategory: 'providers',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: [
          {
            key: 'TUSHARE_TOKEN',
            value: '',
            rawValueExists: false,
            isMasked: false,
            schema: {
              key: 'TUSHARE_TOKEN',
              category: 'data_source',
              dataType: 'string',
              uiControl: 'password',
              isSensitive: true,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 1,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(screen.getByTestId('data-providers-panel')).toBeInTheDocument();
    expect(document.querySelector('[data-testid^="settings-configuration-card-"]')).toBeNull();
  });

  it('keeps the notification channel directory inline and delegates each channel editor to its own dialog', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'notification',
      activeSubCategory: 'channels',
    }));

    render(<SettingsPage />);

    expect(screen.getByTestId('notification-channels-panel')).toBeInTheDocument();
    expect(document.querySelector('[data-testid^="settings-configuration-card-"]')).toBeNull();
  });

  it('scopes setup and AlphaSift helper cards to their related categories', async () => {
    const configState = buildSystemConfigState();
    const dataSourceItems = [
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
      {
        key: 'NEWS_MAX_AGE_DAYS',
        value: '3',
        rawValueExists: true,
        isMasked: false,
        schema: {
          key: 'NEWS_MAX_AGE_DAYS',
          category: 'data_source',
          dataType: 'integer',
          uiControl: 'number',
          isSensitive: false,
          isRequired: false,
          isEditable: true,
          options: [],
          validation: {},
          displayOrder: 1,
        },
      },
    ];

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'base',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: dataSourceItems,
      },
    }));

    const { rerender } = render(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: '首次启动配置检查' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'AlphaSift 选股' })).not.toBeInTheDocument();

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: dataSourceItems,
      },
    }));
    rerender(<SettingsPage />);

    expect(screen.queryByRole('heading', { name: '首次启动配置检查' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'AlphaSift 选股' })).not.toBeInTheDocument();

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: dataSourceItems,
      },
    }));
    rerender(<SettingsPage />);

    // The default data_source tab is the source tab; the AlphaSift card
    // lives on the providers tab only.
    expect(screen.queryByRole('heading', { name: 'AlphaSift 选股' })).not.toBeInTheDocument();

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      activeSubCategory: 'providers',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: dataSourceItems,
      },
    }));
    rerender(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: 'AlphaSift 选股' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '首次启动配置检查' })).not.toBeInTheDocument();
  });
}
