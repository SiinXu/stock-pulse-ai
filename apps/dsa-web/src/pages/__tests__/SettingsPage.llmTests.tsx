import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import { loadUiLanguageTranslations } from '../../i18n/translations';
import SettingsPageTestHarness from './SettingsPage.testHarness';

const {
  SettingsPage,
  TEST_CONNECTION_NAME_FIELD,
  TEST_MODELS_FIELD,
  TEST_PROVIDER_ID_FIELD,
  buildSystemConfigState,
  createDeferred,
  defaultItemsByCategory,
  expectConnectionDraftAutosaveBlockedBySchema,
  getLlmAvailableModels,
  getLlmProviderCatalog,
  getSetupStatus,
  load,
  notifySystemConfigChanged,
  resetDraftKeys,
  routerSearchParamsMock,
  save,
  setDraftValue,
  updateSystemConfig,
  useSystemConfigMock,
  withTestConnectionCoreFields,
} = SettingsPageTestHarness;

export function registerSettingsPageLlmTests(): void {
  it('autosaves the llm channel and task-routing draft as one group', async () => {
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));

    expect(screen.queryByRole('button', { name: /保存配置/ })).not.toBeInTheDocument();
    expect(await screen.findByText(/等待自动保存/)).toBeInTheDocument();
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
    const payload = save.mock.calls[0][0];
    expect(payload).toEqual(expect.arrayContaining([
      expect.objectContaining({ key: 'LLM_CHANNELS', value: 'draft,backup' }),
      expect.objectContaining({ key: 'LITELLM_MODEL', value: 'openai/draft-model' }),
    ]));
  });

  it('does not autosave an AI draft before the Catalog establishes schema presence', async () => {
    const catalog = createDeferred<{ providers: Array<Record<string, unknown>> }>();
    getLlmProviderCatalog.mockReturnValueOnce(catalog.promise);
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    vi.useFakeTimers();
    try {
      render(<SettingsPage />);
      fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));

      expect(screen.getByTestId('llm-channel-editor-items')).toHaveAttribute('data-disabled', 'true');
      await act(async () => {
        await vi.advanceTimersByTimeAsync(850);
      });
      expect(save).not.toHaveBeenCalled();

      await act(async () => {
        catalog.resolve({
          providers: [
            { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek' },
          ],
        });
        await catalog.promise;
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(700);
      });
      expect(save).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not autosave a Connection draft under a present empty schema', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema([]);
  });

  it('does not autosave a Connection draft under a models-only schema', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema([TEST_MODELS_FIELD]);
  });

  it('does not autosave a Connection draft when connection_name is missing', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema([
      TEST_PROVIDER_ID_FIELD,
      TEST_MODELS_FIELD,
    ]);
  });

  it('does not autosave a Connection draft when provider_id is missing', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema([
      TEST_CONNECTION_NAME_FIELD,
      TEST_MODELS_FIELD,
    ]);
  });

  it('does not autosave a Connection draft under a read-only identity schema', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema(withTestConnectionCoreFields([
      TEST_CONNECTION_NAME_FIELD,
      {
        ...TEST_PROVIDER_ID_FIELD,
        isRequired: false,
        contract: { requirement: 'inherited' },
      },
      TEST_MODELS_FIELD,
    ]));
  });

  it('does not autosave a Connection draft with an unknown visible required field', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema(withTestConnectionCoreFields([{
      key: 'future_token',
      dataType: 'string',
      isSensitive: false,
      isRequired: true,
      contract: { requirement: 'required' },
    }]));
  });

  it('does not autosave when an unknown required field becomes visible for the draft provider', async () => {
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([{
        key: 'future_token',
        dataType: 'string',
        isSensitive: true,
        isRequired: true,
        contract: {
          requirement: 'required',
          visibleWhen: [{ key: 'provider_id', operator: 'equals', value: 'deepseek' }],
        },
      }]),
    });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    vi.useFakeTimers();
    try {
      render(<SettingsPage />);
      fireEvent.click(screen.getByRole('button', { name: 'emit schema-valid connection draft' }));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(850);
      });
      expect(save).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('autosaves when an unknown required field stays hidden for the draft provider', async () => {
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([{
        key: 'future_token',
        dataType: 'string',
        isSensitive: true,
        isRequired: true,
        contract: {
          requirement: 'required',
          visibleWhen: [{ key: 'provider_id', operator: 'equals', value: 'openai' }],
        },
      }]),
    });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    render(<SettingsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'emit schema-valid connection draft' }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
  });

  it('autosaves when an unknown visible field is optional', async () => {
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([{
        key: 'future_hint',
        dataType: 'string',
        isSensitive: false,
        isRequired: false,
        contract: { requirement: 'optional' },
      }]),
    });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    render(<SettingsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'emit schema-valid connection draft' }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
  });

  it('revalidates the retained Connection payload when an unmounted editor resets child validity', async () => {
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([
        TEST_CONNECTION_NAME_FIELD,
        TEST_PROVIDER_ID_FIELD,
      ]),
    });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    const { rerender } = render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: 'mark llm draft invalid' }));
    fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));

    expect(await screen.findByText(/自动保存失败/, {}, { timeout: 2000 })).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();

    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'raw_config' });
    rerender(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 50));
    });
    expect(save).not.toHaveBeenCalled();
  });

  it('autosaves a payload that satisfies the present Schema and authoritative Catalog', async () => {
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([
        TEST_CONNECTION_NAME_FIELD,
        TEST_PROVIDER_ID_FIELD,
      ]),
    });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: 'emit schema-valid connection draft' }));

    await waitFor(() => expect(save).toHaveBeenCalledWith([
      { key: 'LLM_CHANNELS', value: 'deepseek' },
      { key: 'LLM_DEEPSEEK_PROVIDER', value: 'deepseek' },
    ], { silent: true }), { timeout: 2000 });
  });

  it('keeps existing Connections inspectable but blocks mutations for an unknown schema condition', async () => {
    const connectionFields = withTestConnectionCoreFields([
      TEST_CONNECTION_NAME_FIELD,
      TEST_PROVIDER_ID_FIELD,
      {
        ...TEST_MODELS_FIELD,
        contract: {
          requirement: 'optional' as const,
          enabledWhen: [{ key: 'provider_id', operator: 'futureOperator' as never, value: 'deepseek' }],
        },
      },
    ]);
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields,
    });
    save.mockResolvedValue({ success: true });
    const configState = buildSystemConfigState({ activeCategory: 'ai_model' });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...configState.itemsByCategory,
        ai_model: configState.itemsByCategory.ai_model.map((item) => ({
          ...item,
          schema: {
            ...(item.schema as Record<string, unknown>),
            uiPlacement: 'model_access',
          },
        })),
      },
    }));

    vi.useFakeTimers();
    try {
      render(<SettingsPage />);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      const inspect = screen.getByRole('button', { name: 'inspect existing connection' });
      expect(inspect).toBeEnabled();
      expect(screen.getByRole('button', { name: /添加模型服务/ })).toBeDisabled();
      fireEvent.click(inspect);
      expect(screen.getByRole('dialog', { name: 'existing connection inspection' })).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(850);
      });
      expect(save).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps AI autosave and the editor blocked after a Catalog failure', async () => {
    getLlmProviderCatalog.mockRejectedValueOnce(new Error('catalog failed'));
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    vi.useFakeTimers();
    try {
      render(<SettingsPage />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByTestId('llm-channel-editor-items')).toHaveAttribute('data-catalog-unavailable', 'true');
      fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(850);
      });
      expect(save).not.toHaveBeenCalled();
      expect(screen.getByTestId('llm-channel-editor-items')).toHaveAttribute('data-disabled', 'true');
    } finally {
      vi.useRealTimers();
    }
  });

  it('passes merged generation backend draft items to the backend status panel', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      getChangedItems: () => [
        { key: 'GENERATION_BACKEND', value: 'litellm' },
        { key: 'LLM_CHANNELS', value: 'saved' },
        { key: 'OPENAI_MODEL', value: 'gpt-draft' },
        { key: 'GEMINI_MODEL', value: 'gemini-draft' },
        { key: 'OLLAMA_API_BASE', value: 'http://localhost:11434' },
        { key: 'WECHAT_WEBHOOK_URL', value: 'not-a-url' },
      ],
    }));

    const { rerender } = render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'emit llm draft' }));

    // The status panel lives on the Advanced Backend Status tab (default view).
    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced' });
    rerender(<SettingsPage />);

    const statusItems = await screen.findByTestId('generation-backend-status-items');
    await waitFor(() => {
      expect(statusItems).toHaveTextContent('GENERATION_BACKEND=litellm');
      expect(statusItems).toHaveTextContent('LLM_CHANNELS=draft,backup');
      expect(statusItems).toHaveTextContent('LITELLM_MODEL=openai/draft-model');
      expect(statusItems).not.toHaveTextContent('OPENAI_MODEL=gpt-draft');
      expect(statusItems).not.toHaveTextContent('GEMINI_MODEL=gemini-draft');
      expect(statusItems).not.toHaveTextContent('OLLAMA_API_BASE=http://localhost:11434');
      expect(statusItems).not.toHaveTextContent('GENERATION_BACKEND=codex_cli');
      expect(statusItems).not.toHaveTextContent('WECHAT_WEBHOOK_URL=not-a-url');
    });
  });

  it('clears llm channel draft items after autosave succeeds', async () => {
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    const { rerender } = render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'emit llm draft' }));

    // The status panel lives on the Advanced Backend Status tab (default view).
    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced' });
    rerender(<SettingsPage />);
    expect(await screen.findByTestId('generation-backend-status-items')).toHaveTextContent('LLM_CHANNELS=draft,backup');

    await waitFor(() => {
      expect(screen.getByTestId('generation-backend-status-items')).not.toHaveTextContent('LLM_CHANNELS=draft,backup');
    }, { timeout: 2000 });
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
  });

  it('debounces a group autosave and reports saving then saved', async () => {
    vi.useFakeTimers();
    try {
      const pendingSave = createDeferred<{ success: boolean }>();
      save.mockReturnValueOnce(pendingSave.promise);
      useSystemConfigMock.mockReturnValue(buildSystemConfigState({
        activeCategory: 'system',
        hasDirty: true,
        dirtyCount: 1,
        getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
      }));

      render(<SettingsPage />);

      expect(screen.queryByRole('button', { name: /保存配置/ })).not.toBeInTheDocument();
      expect(screen.getByText(/等待自动保存/)).toBeInTheDocument();
      expect(save).not.toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(700);
      });
      expect(screen.getByText(/自动保存中/)).toBeInTheDocument();
      expect(save).toHaveBeenCalledTimes(1);

      await act(async () => {
        pendingSave.resolve({ success: true });
        await pendingSave.promise;
      });
      expect(screen.getByText(/已自动保存/)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps a failed autosave draft and retries the same group', async () => {
    save
      .mockResolvedValueOnce({ success: false, message: '保存失败' })
      .mockResolvedValueOnce({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    }));

    render(<SettingsPage />);

    expect(await screen.findByText(/自动保存失败/, {}, { timeout: 2000 })).toBeInTheDocument();
    expect(resetDraftKeys).not.toHaveBeenCalled();
    const retryButton = screen.getByRole('button', { name: '重试' });
    expect(retryButton).toHaveClass('min-h-11', 'min-w-11');
    fireEvent.click(retryButton);

    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/已自动保存/)).toBeInTheDocument();
  });

  it('marks a 409 autosave as conflicted and can restore that group', async () => {
    save.mockResolvedValueOnce({ success: false, message: 'config_conflict' });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    }));

    render(<SettingsPage />);

    expect(await screen.findByText(/保存冲突/, {}, { timeout: 2000 })).toBeInTheDocument();
    const restoreButton = screen.getByRole('button', { name: '恢复服务器值' });
    expect(restoreButton).toHaveClass('min-h-11', 'min-w-11');
    fireEvent.click(restoreButton);
    expect(resetDraftKeys).toHaveBeenCalledWith(['WEBUI_PORT']);
  });

  it.each([
    { language: 'de', expectedTitle: 'Liste ausgewählter Aktien', backendTitleVisible: false },
    { language: 'en', expectedTitle: 'Server Watchlist Title', backendTitleVisible: true },
  ] as const)(
    'uses the $language field-title contract in the 409 conflict panel',
    async ({ language, expectedTitle, backendTitleVisible }) => {
      useSystemConfigMock.mockReturnValue(buildSystemConfigState({
        activeCategory: 'base',
        conflictState: {
          fields: [{
            key: 'STOCK_LIST',
            base: 'AAPL',
            server: 'MSFT',
            local: 'NVDA',
            isSensitive: false,
            title: 'Server Watchlist Title',
            category: 'base',
          }],
          serverVersion: 'v2',
        },
        resolveConflictField: vi.fn(),
        resolveAllConflicts: vi.fn(),
      }));
      await loadUiLanguageTranslations(language);

      render(
        <UiLanguageProvider initialLanguage={language}>
          <SettingsPage />
        </UiLanguageProvider>,
      );

      expect(screen.getByText(expectedTitle)).toBeInTheDocument();
      if (backendTitleVisible) {
        expect(screen.getByText('Server Watchlist Title')).toBeInTheDocument();
      } else {
        expect(screen.queryByText('Server Watchlist Title')).not.toBeInTheDocument();
      }
    },
  );

  it('runs the unified post-save effects after a legacy migration applies', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));
    // The migration banner lives on the Advanced Backend Status tab (default view).
    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced' });

    render(<SettingsPage />);

    // Ignore the effects fired during initial mount.
    load.mockClear();
    notifySystemConfigChanged.mockClear();
    getSetupStatus.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'trigger migration' }));

    // Migration must reload config and then run the same post-save flow as Save.
    await waitFor(() => expect(load).toHaveBeenCalled());
    await waitFor(() => expect(notifySystemConfigChanged).toHaveBeenCalled());
    await waitFor(() => expect(getSetupStatus).toHaveBeenCalled());
  });

  it('renders the two-level IA navigation and routes section clicks through the section/view URL', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model', activeSubCategory: 'model' }));

    render(<SettingsPage />);

    // The AI & Models section is active and its second-level view tabs render.
    expect(screen.getByRole('button', { name: /AI 与模型/ })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('tab', { name: '模型接入' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '任务路由' })).toBeInTheDocument();

    // Clicking a first-level section pushes the canonical section/view URL
    // (section is the single source of truth; no legacy params leak).
    fireEvent.click(screen.getByRole('button', { name: /系统与安全/ }));
    const [nextParams, options] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(nextParams?.get('section')).toBe('system_security');
    expect(nextParams?.has('category')).toBe(false);
    expect(nextParams?.has('sub')).toBe(false);
    // Normal navigation must push history (not replace) so Back returns here.
    expect(options?.replace).toBe(false);
  });

  it('round-trips from empty Task Routing through Model Access with an explicit origin', async () => {
    getLlmAvailableModels.mockResolvedValue({ models: [] });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'task_routing' });

    const { rerender } = render(<SettingsPage />);

    fireEvent.click(await screen.findByRole('button', { name: '前往模型接入' }));
    const [modelAccessParams, modelAccessOptions] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(modelAccessParams?.get('section')).toBe('ai_models');
    expect(modelAccessParams?.get('view')).toBe('connections');
    expect(modelAccessParams?.get('from')).toBe('task_routing');
    expect(modelAccessOptions?.replace).toBe(false);

    routerSearchParamsMock.params = new URLSearchParams({
      section: 'ai_models',
      view: 'connections',
      from: 'task_routing',
    });
    rerender(<SettingsPage />);

    fireEvent.click(await screen.findByRole('button', { name: '返回任务路由' }));
    const [returnParams, returnOptions] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(returnParams?.get('section')).toBe('ai_models');
    expect(returnParams?.get('view')).toBe('task_routing');
    expect(returnParams?.has('from')).toBe(false);
    expect(returnOptions?.replace).toBe(false);
  });

  it('does not report task routes as unavailable while the available-model catalog failed', async () => {
    getLlmAvailableModels.mockRejectedValue(new Error('catalog unavailable'));
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'overview' });

    render(<SettingsPage />);

    expect(screen.getByRole('tab', { name: '总览' })).toHaveAttribute('aria-selected', 'true');
    await waitFor(() => expect(getLlmAvailableModels).toHaveBeenCalledTimes(1));
    await expect(getLlmAvailableModels.mock.results[0]?.value).rejects.toThrow('catalog unavailable');
    expect(await screen.findByText('可用模型加载失败')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument();
    expect(screen.queryByText('当前配置不可用')).not.toBeInTheDocument();
  });

  it('moves every referenced task route into the unified draft when replacing a model', async () => {
    const modelField = (key: string, value: string, displayOrder: number) => ({
      key,
      value,
      rawValueExists: true,
      isMasked: false,
      schema: {
        key,
        category: 'ai_model',
        dataType: 'string',
        uiControl: 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder,
        uiPlacement: key === 'LITELLM_FALLBACK_MODELS' ? 'reliability' as const : 'task_routing' as const,
      },
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...defaultItemsByCategory,
        ai_model: [
          ...defaultItemsByCategory.ai_model,
          modelField('LITELLM_MODEL', 'deepseek/shared-model', 2),
          modelField('AGENT_LITELLM_MODEL', 'deepseek/shared-model', 3),
          modelField('VISION_MODEL', 'openai/vision-model', 4),
          modelField('LITELLM_FALLBACK_MODELS', 'deepseek/shared-model,openai/backup-model', 5),
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'connections' });

    render(<SettingsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'replace model references' }));

    expect(setDraftValue).toHaveBeenCalledWith('LITELLM_MODEL', 'openai/replacement-model');
    expect(setDraftValue).toHaveBeenCalledWith('AGENT_LITELLM_MODEL', 'openai/replacement-model');
    expect(setDraftValue).toHaveBeenCalledWith(
      'LITELLM_FALLBACK_MODELS',
      'openai/replacement-model,openai/backup-model',
    );
    expect(setDraftValue).not.toHaveBeenCalledWith('VISION_MODEL', expect.anything());
  });

  it('replaces a historical bare Agent reference using backend-equivalent route identity', async () => {
    getLlmAvailableModels.mockResolvedValue({
      models: [
        { route: 'openai/gpt-4o-mini', display: 'gpt-4o-mini', connection: 'openai', provider: 'openai' },
        { route: 'openai/gpt-5.5', display: 'gpt-5.5', connection: 'openai', provider: 'openai' },
      ],
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...defaultItemsByCategory,
        ai_model: [
          ...defaultItemsByCategory.ai_model,
          {
            key: 'AGENT_LITELLM_MODEL',
            value: 'gpt-4o-mini',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_LITELLM_MODEL',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 3,
              uiPlacement: 'task_routing' as const,
            },
          },
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'connections' });

    render(<SettingsPage />);
    await waitFor(() => expect(getLlmAvailableModels).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'replace bare Agent reference' }));

    expect(setDraftValue).toHaveBeenCalledWith('AGENT_LITELLM_MODEL', 'openai/gpt-5.5');
  });

  it('makes Task Routing the single editor for per-task models and links fallback out to Reliability', async () => {
    const aiField = (key: string, value: string, displayOrder: number) => ({
      key,
      value,
      rawValueExists: Boolean(value),
      isMasked: false,
      schema: {
        key,
        category: 'ai_model',
        dataType: 'string',
        uiControl: 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder,
        // Mirrors the backend registry: task-model keys are owned by the
        // Task Routing surface.
        uiPlacement: 'task_routing' as const,
      },
    });
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: {
        ...configState.itemsByCategory,
        ai_model: [
          aiField('LITELLM_MODEL', 'openai/gpt-4o-mini', 1),
          aiField('AGENT_LITELLM_MODEL', 'openai/gpt-4o', 2),
          aiField('VISION_MODEL', 'gemini/gemini-3-pro', 3),
          aiField('LLM_TEMPERATURE', '0.7', 4),
          aiField('LITELLM_FALLBACK_MODELS', 'deepseek/deepseek-v4-pro', 5),
        ],
      },
    }));
    // Drive the Task Routing view directly (buildSystemConfigState defaults the
    // ai_model tab to the connections view).
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'task_routing' });

    render(<SettingsPage />);

    // Per-task model fields render as strict list selectors (SearchableSelect
    // trigger buttons opening a listbox), not raw text inputs; temperature
    // stays a plain field. Current routes not present in the available-model
    // catalog are surfaced as "unavailable" instead of being silently dropped.
    expect(await screen.findByText('当前配置不可用：openai/gpt-4o-mini')).toBeInTheDocument();
    expect(screen.getByText('当前配置不可用：openai/gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('当前配置不可用：gemini/gemini-3-pro')).toBeInTheDocument();
    const modelTriggers = document.querySelectorAll('button[aria-haspopup="listbox"]');
    expect(modelTriggers.length).toBeGreaterThanOrEqual(3);
    expect(screen.getByTestId('settings-field-LLM_TEMPERATURE')).toBeInTheDocument();
    // Fallback order is NOT an editable field here; it is a read-only summary.
    expect(screen.queryByTestId('settings-field-LITELLM_FALLBACK_MODELS')).not.toBeInTheDocument();
    expect(screen.getByText(/deepseek-v4-pro · deepseek/)).toBeInTheDocument();

    // The jump link routes to the Reliability view (the canonical fallback editor).
    const reliabilityButton = screen.getByRole('button', { name: /前往可靠性设置/ });
    expect(reliabilityButton).toHaveClass('min-h-11', 'min-w-11');
    fireEvent.click(reliabilityButton);
    const [nextParams] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(nextParams?.get('section')).toBe('ai_models');
    expect(nextParams?.get('view')).toBe('reliability');
  });

  it('keeps duplicate runtime routes separate and saves the selected Connection ModelRef', async () => {
    const modelField = {
      key: 'LITELLM_MODEL',
      value: 'openai/gpt-4o',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LITELLM_MODEL',
        category: 'ai_model' as const,
        dataType: 'string' as const,
        uiControl: 'text' as const,
        isSensitive: false,
        isRequired: true,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
        uiPlacement: 'task_routing' as const,
      },
    };
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: { ...configState.itemsByCategory, ai_model: [modelField] },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'task_routing' });
    getLlmAvailableModels.mockResolvedValue({
      models: [
        {
          modelRef: 'modelref:v1:personal:openai%2Fgpt-4o',
          route: 'openai/gpt-4o',
          display: 'gpt-4o',
          connection: 'personal',
          connectionId: 'personal',
          connectionName: 'Personal',
          provider: 'openai',
          providerId: 'openai',
          providerLabel: 'OpenAI',
          available: true,
        },
        {
          modelRef: 'modelref:v1:work:openai%2Fgpt-4o',
          route: 'openai/gpt-4o',
          display: 'gpt-4o',
          connection: 'work',
          connectionId: 'work',
          connectionName: 'Work',
          provider: 'openai',
          providerId: 'openai',
          providerLabel: 'OpenAI',
          available: true,
        },
      ],
    });

    render(<SettingsPage />);

    const trigger = await screen.findByRole('button', { name: '主要模型' });
    expect(setDraftValue).not.toHaveBeenCalledWith('LITELLM_MODEL', expect.stringContaining('modelref:v1:'));
    fireEvent.click(trigger);
    const workOption = screen.getAllByRole('option', { name: /gpt-4o/ })
      .find((option) => option.textContent?.includes('Work'));
    expect(workOption).toBeDefined();
    fireEvent.click(workOption!);

    expect(setDraftValue).toHaveBeenCalledWith(
      'LITELLM_MODEL',
      'modelref:v1:work:openai%2Fgpt-4o',
    );
  });

  it('resolves one legacy route for display without dirtying or saving config on load', async () => {
    const modelField = {
      key: 'LITELLM_MODEL',
      value: 'openai/gpt-4o',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LITELLM_MODEL',
        category: 'ai_model' as const,
        dataType: 'string' as const,
        uiControl: 'text' as const,
        isSensitive: false,
        isRequired: true,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
        uiPlacement: 'task_routing' as const,
      },
    };
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: { ...configState.itemsByCategory, ai_model: [modelField] },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'task_routing' });
    getLlmAvailableModels.mockResolvedValue({
      models: [{
        modelRef: 'modelref:v1:personal:openai%2Fgpt-4o',
        route: 'openai/gpt-4o',
        display: 'GPT-4o',
        connection: 'personal',
        connectionId: 'personal',
        connectionName: 'Personal Connection',
        provider: 'openai',
        providerId: 'openai',
        providerLabel: 'OpenAI',
        available: true,
      }],
    });

    render(<SettingsPage />);

    const trigger = await screen.findByRole('button', { name: '主要模型' });
    await waitFor(() => {
      expect(trigger).toHaveAttribute(
        'data-value',
        'modelref:v1:personal:openai%2Fgpt-4o',
      );
      expect(trigger).toHaveTextContent('GPT-4o');
      expect(trigger).toHaveTextContent('Personal Connection');
    });
    expect(setDraftValue).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
    expect(updateSystemConfig).not.toHaveBeenCalled();
  });

  it('resolves a unique legacy fallback for display without mutating or saving config on load', async () => {
    const fallbackModelRef = 'modelref:v1:personal:openai%2Fgpt-4o';
    const fallbackField = {
      key: 'LITELLM_FALLBACK_MODELS',
      value: 'openai/gpt-4o',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LITELLM_FALLBACK_MODELS',
        category: 'ai_model' as const,
        dataType: 'string' as const,
        uiControl: 'text' as const,
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 2,
        uiPlacement: 'task_routing' as const,
      },
    };
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: { ...configState.itemsByCategory, ai_model: [fallbackField] },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'reliability' });
    getLlmAvailableModels.mockResolvedValue({
      models: [{
        modelRef: fallbackModelRef,
        route: 'openai/gpt-4o',
        display: 'GPT-4o',
        connection: 'personal',
        connectionId: 'personal',
        connectionName: 'Personal Connection',
        provider: 'openai',
        providerId: 'openai',
        providerLabel: 'OpenAI',
        available: true,
      }],
    });

    render(<SettingsPage />);

    expect((await screen.findAllByText('GPT-4o · OpenAI · Personal Connection')).length)
      .toBeGreaterThan(0);
    expect(screen.queryByText('当前配置不可用')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '选择备用模型' }));
    expect(screen.getByRole('checkbox', {
      name: 'GPT-4o · OpenAI · Personal Connection',
    })).toBeChecked();
    expect(setDraftValue).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
    expect(updateSystemConfig).not.toHaveBeenCalled();
  });

  it('decodes a stale ModelRef for display while preserving its stored value', async () => {
    const staleModelRef = 'modelref:v1:retired_connection:openai%2Fretired-model';
    const modelField = {
      key: 'LITELLM_MODEL',
      value: staleModelRef,
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LITELLM_MODEL',
        category: 'ai_model' as const,
        dataType: 'string' as const,
        uiControl: 'text' as const,
        isSensitive: false,
        isRequired: true,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
        uiPlacement: 'task_routing' as const,
      },
    };
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: { ...configState.itemsByCategory, ai_model: [modelField] },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'task_routing' });
    getLlmAvailableModels.mockResolvedValue({
      models: [{
        modelRef: 'modelref:v1:current:openai%2Fgpt-4o',
        route: 'openai/gpt-4o',
        display: 'GPT-4o',
        connection: 'current',
        connectionId: 'current',
        connectionName: 'Current Connection',
        provider: 'openai',
        providerId: 'openai',
        providerLabel: 'OpenAI',
        available: true,
      }],
    });

    render(<SettingsPage />);

    const trigger = await screen.findByRole('button', { name: '主要模型' });
    await waitFor(() => expect(trigger).toHaveTextContent(
      'openai/retired-model · retired_connection',
    ));
    expect(trigger).toHaveAttribute('data-value', staleModelRef);
    expect(screen.getByText(
      '当前配置不可用：openai/retired-model · retired_connection',
    )).toBeInTheDocument();
    expect(setDraftValue).not.toHaveBeenCalled();
  });
}
