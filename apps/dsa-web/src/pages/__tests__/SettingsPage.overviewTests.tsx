import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { SetupStatusResponse } from '../../types/systemConfig';
import { APP_ROUTE_PATHS, SETTINGS_ROUTE_QUERY_KEYS, SETTINGS_SECTION_IDS } from '../../routing/routes';
import { resolveWebBuildInfo } from '../../utils/constants';
import SettingsPageTestHarness from './SettingsPage.testHarness';
import type { BlockerArgs } from './SettingsPage.testHarness';

const {
  SettingsPage,
  analyzeAsync,
  buildSystemConfigState,
  createDeferred,
  createDesktopRuntime,
  desktopGetUpdateState,
  getSetupStatus,
  load,
  refreshAfterExternalSave,
  resetDraft,
  resetDraftKeys,
  routerBlockerMock,
  routerSearchParamsMock,
  save,
  settingsPanelErrorBoundary,
  useSystemConfigMock,
  webBuildInfoMock,
} = SettingsPageTestHarness;

export function registerSettingsPageOverviewTests(): void {
  it('embeds TokenUsagePage with one page heading while keeping Settings state mounted', async () => {
    routerSearchParamsMock.params = new URLSearchParams({
      [SETTINGS_ROUTE_QUERY_KEYS.section]: SETTINGS_SECTION_IDS.usage,
    });

    const { rerender } = render(<SettingsPage />);

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1, name: '系统设置' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Token 用量监控' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '用量与成本' }))
      .toHaveAttribute('aria-current', 'page');
    expect(useSystemConfigMock).toHaveBeenCalled();
    expect(routerSearchParamsMock.setParams).not.toHaveBeenCalled();
    expect(await screen.findByRole('heading', {
      level: 3,
      name: '暂无 Token 用量记录',
    })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '概览' }));
    const [nextParams, options] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(nextParams.get(SETTINGS_ROUTE_QUERY_KEYS.section)).toBe('overview');
    expect(nextParams.get(SETTINGS_ROUTE_QUERY_KEYS.view)).toBe('readiness');
    expect(options).toEqual({ replace: false });

    routerSearchParamsMock.params = nextParams as URLSearchParams;
    rerender(<SettingsPage />);
    expect(screen.queryByRole('heading', { name: 'Token 用量监控' })).not.toBeInTheDocument();
    expect(document.title).toBe('系统设置 - StockPulse');
  });

  it('renders category navigation and auth settings modules', async () => {
    // Auth cards live on the Auth & Security tab.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'security' });
    render(<SettingsPage />);

    const heading = await screen.findByRole('heading', { name: '系统设置' });
    expect(heading.closest('[data-pattern="page-header"]')).not.toBeNull();
    expect(heading.closest('[data-pattern="app-page"]')).toHaveClass('settings-page');
    expect(screen.getByText('认证与登录保护')).toBeInTheDocument();
    expect(screen.getByText('修改密码')).toBeInTheDocument();
    expect(load).toHaveBeenCalled();
  });

  it('renders first-run setup checks and routes setup actions', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    expect(await screen.findByTestId('first-run-setup-card')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '首次启动配置检查' })).toBeInTheDocument();
    expect(screen.getByText('自选股')).toBeInTheDocument();
    expect(screen.getAllByText('已配置')).toHaveLength(2);

    const lastSection = () => routerSearchParamsMock.setParams.mock.calls.at(-1)?.[0].get('section');

    fireEvent.click(screen.getByRole('button', { name: '配置模型' }));
    expect(lastSection()).toBe('ai_models');
    fireEvent.click(screen.getByRole('button', { name: '维护自选股' }));
    expect(lastSection()).toBe('overview');
    fireEvent.click(screen.getByRole('button', { name: '配置通知' }));
    expect(lastSection()).toBe('notifications');
  });

  it('keeps first-run setup summary neutral while setup status is loading', async () => {
    getSetupStatus.mockImplementation(() => new Promise(() => undefined));
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    expect(await screen.findByText('正在检查首次启动配置')).toBeInTheDocument();
    expect(screen.getByText('正在读取配置状态，完成后会显示缺失项和试跑入口。')).toBeInTheDocument();
    expect(screen.queryByText('基础配置已满足最小可用分析')).not.toBeInTheDocument();
    expect(screen.queryByText('还有基础配置需要处理')).not.toBeInTheDocument();
    expect(screen.queryByText('所有必需项已就绪，可运行一次简短分析验证链路。')).not.toBeInTheDocument();
  });

  it('keeps first-run setup summary neutral when setup status fails', async () => {
    getSetupStatus.mockRejectedValue(new Error('setup status unavailable'));
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    expect(await screen.findByText('暂无法判断配置状态')).toBeInTheDocument();
    expect(screen.getByText('配置状态读取失败。可先检查或修改设置项，稍后刷新检查结果。')).toBeInTheDocument();
    expect(screen.queryByText('基础配置已满足最小可用分析')).not.toBeInTheDocument();
    expect(screen.queryByText('还有基础配置需要处理')).not.toBeInTheDocument();
    expect(screen.queryByText('所有必需项已就绪，可运行一次简短分析验证链路。')).not.toBeInTheDocument();
  });

  it('keeps the latest first-run setup status when refresh responses resolve out of order', async () => {
    const staleRefresh = createDeferred<SetupStatusResponse>();
    const latestRefresh = createDeferred<SetupStatusResponse>();
    const initialStatus: SetupStatusResponse = {
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      nextStepKey: null,
      checks: [
        {
          key: 'initial-status',
          title: '初始状态',
          category: 'base',
          required: true,
          status: 'configured',
          message: '初始配置状态。',
          nextStep: null,
        },
      ],
    };
    const staleStatus: SetupStatusResponse = {
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LLM_CHANNELS'],
      nextStepKey: 'LLM_CHANNELS',
      checks: [
        {
          key: 'stale-status',
          title: '过期状态',
          category: 'ai_model',
          required: true,
          status: 'needs_action',
          message: '过期的配置状态。',
          nextStep: '这条旧响应不应覆盖最新状态。',
        },
      ],
    };
    const latestStatus: SetupStatusResponse = {
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      nextStepKey: null,
      checks: [
        {
          key: 'latest-status',
          title: '最新状态',
          category: 'base',
          required: true,
          status: 'configured',
          message: '最新配置状态。',
          nextStep: null,
        },
      ],
    };

    getSetupStatus
      .mockResolvedValueOnce(initialStatus)
      .mockImplementationOnce(() => staleRefresh.promise)
      .mockImplementationOnce(() => latestRefresh.promise);
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    expect(await screen.findByText('初始状态')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '刷新检查' }));
    fireEvent.click(screen.getByRole('button', { name: 'merge stock list' }));

    await waitFor(() => expect(getSetupStatus).toHaveBeenCalledTimes(3));

    await act(async () => {
      latestRefresh.resolve(latestStatus);
      await latestRefresh.promise;
    });

    expect(await screen.findByText('最新状态')).toBeInTheDocument();
    expect(screen.queryByText('过期状态')).not.toBeInTheDocument();

    await act(async () => {
      staleRefresh.resolve(staleStatus);
      await staleRefresh.promise;
    });

    await waitFor(() => expect(screen.getByText('最新状态')).toBeInTheDocument());
    expect(screen.queryByText('过期状态')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '简短试跑' })).toBeEnabled();
  });

  it('runs a brief setup smoke analysis with the first watchlist stock', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    await screen.findByText('基础配置已满足最小可用分析');
    fireEvent.click(screen.getByRole('button', { name: '简短试跑' }));

    await waitFor(() => expect(analyzeAsync).toHaveBeenCalledWith({
      stockCode: 'SH600000',
      reportType: 'brief',
      asyncMode: true,
      notify: false,
      originalQuery: 'SH600000',
      selectionSource: 'manual',
    }));
    expect(await screen.findByText(/task-setup-smoke/)).toBeInTheDocument();
  });

  it('allows brief setup smoke when only the Agent channel is incomplete', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: true,
      requiredMissingKeys: ['llm_agent'],
      nextStepKey: 'llm_agent',
      checks: [
        {
          key: 'llm_primary',
          title: 'LLM 主渠道',
          category: 'ai_model',
          required: true,
          status: 'configured',
          message: '已启用 Claude Code CLI 本地生成 Backend（experimental/limited）。',
          nextStep: null,
        },
        {
          key: 'llm_agent',
          title: 'Agent 渠道',
          category: 'agent',
          required: true,
          status: 'needs_action',
          message: 'Agent 工具调用需要 LiteLLM 模型配置；local CLI 主生成方式不会被自动继承。',
          nextStep: '如需使用 Ask-Stock Agent，请配置 LiteLLM 模型。',
        },
        {
          key: 'stock_list',
          title: '自选股',
          category: 'base',
          required: true,
          status: 'configured',
          message: '已配置 1 只股票。',
          nextStep: null,
        },
      ],
    });

    render(<SettingsPage />);

    await screen.findByText('还缺少 1 项：Agent 渠道');
    expect(screen.getByRole('button', { name: '简短试跑' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: '简短试跑' }));

    await waitFor(() => expect(analyzeAsync).toHaveBeenCalledWith({
      stockCode: 'SH600000',
      reportType: 'brief',
      asyncMode: true,
      notify: false,
      originalQuery: 'SH600000',
      selectionSource: 'manual',
    }));
  });

  it('shows missing setup items and lets the user reopen the setup check', async () => {
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LLM_CHANNELS'],
      nextStepKey: 'LLM_CHANNELS',
      checks: [
        {
          key: 'llm_channels',
          title: '模型渠道',
          category: 'ai_model',
          required: true,
          status: 'needs_action',
          message: '还没有配置模型渠道。',
          nextStep: '请先配置模型渠道。',
        },
      ],
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    expect(await screen.findByText('还有基础配置需要处理')).toBeInTheDocument();
    expect(screen.getByText('还缺少 1 项：模型渠道')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '简短试跑' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '暂时隐藏' }));
    expect(screen.getByText('首次启动配置检查已隐藏')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '展开检查' }));
    expect(screen.getByText('首次启动配置检查')).toBeInTheDocument();
  });

  it('renders web build info in system settings', async () => {
    // The version card lives on the Version & Updates tab.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'about' });
    render(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: '版本信息' })).toBeInTheDocument();
    expect(screen.getByText('3.11.0')).toBeInTheDocument();
    expect(screen.getByText('build-20260329-021530Z')).toBeInTheDocument();
    expect(screen.getByText('2026-03-29T02:15:30.000Z')).toBeInTheDocument();
  });

  it('renders desktop app version in system settings during desktop runtime', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };

    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'about' });
    render(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: '版本信息' })).toBeInTheDocument();
    expect(screen.getByText('桌面端版本')).toBeInTheDocument();
    expect(screen.getByText('3.12.0')).toBeInTheDocument();
  });

  it('keeps version grid at three columns when desktop runtime has no usable version', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '   ' };

    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'about' });
    render(<SettingsPage />);

    const section = (await screen.findByRole('heading', { name: '版本信息' })).closest('section');
    const versionGrid = section?.querySelector('div.grid.grid-cols-1.gap-3');

    expect(screen.queryByText('桌面端版本')).not.toBeInTheDocument();
    expect(versionGrid).toHaveClass('md:grid-cols-3');
    expect(versionGrid).not.toHaveClass('md:grid-cols-4');
  });

  it('ignores non-string desktop runtime version values without breaking render', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: 3120 };

    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'about' });
    render(<SettingsPage />);

    const section = (await screen.findByRole('heading', { name: '版本信息' })).closest('section');
    const versionGrid = section?.querySelector('div.grid.grid-cols-1.gap-3');

    expect(screen.queryByText('桌面端版本')).not.toBeInTheDocument();
    expect(versionGrid).toHaveClass('md:grid-cols-3');
  });

  it('normalizes malformed desktop update payloads instead of throwing', async () => {
    desktopGetUpdateState.mockResolvedValue({
      status: 123,
      currentVersion: 3120,
      latestVersion: null,
      releaseUrl: { href: 'https://example.com' },
      checkedAt: ['2026-04-25T01:02:00Z'],
      message: false,
      releaseName: { text: 'v3.13.0' },
      tagName: undefined,
    });
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'about' });
    render(<SettingsPage />);

    await waitFor(() => {
      expect(desktopGetUpdateState).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByRole('button', { name: '检查更新' })).toBeInTheDocument();
    expect(screen.queryByText('检查更新失败')).not.toBeInTheDocument();
    expect(screen.queryByText('发现新版本')).not.toBeInTheDocument();
  });

  it('falls back to build identifier when package version is still placeholder', () => {
    expect(resolveWebBuildInfo({
      packageVersion: '0.0.0',
      buildTimestamp: '2026-03-29T02:15:30.000Z',
    })).toEqual({
      version: 'build-20260329-021530Z',
      rawVersion: '0.0.0',
      buildId: 'build-20260329-021530Z',
      buildTime: '2026-03-29T02:15:30.000Z',
      isFallbackVersion: true,
    });
  });

  it('renders fallback version hint when package version is placeholder', async () => {
    Object.assign(webBuildInfoMock, {
      version: 'build-20260329-021530Z',
      rawVersion: '0.0.0',
      buildId: 'build-20260329-021530Z',
      buildTime: '2026-03-29T02:15:30.000Z',
      isFallbackVersion: true,
    });

    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'about' });
    render(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: '版本信息' })).toBeInTheDocument();
    expect(screen.getByText(/当前 package\.json 仍为占位版本 0\.0\.0/)).toBeInTheDocument();
    expect(screen.getAllByText('build-20260329-021530Z')).toHaveLength(2);
  });

  it('resets only the current autosave group from the page header', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    }));

    render(<SettingsPage />);

    // Clear the initial load call from useEffect
    vi.clearAllMocks();

    // Reset now asks for confirmation before discarding dirty drafts.
    fireEvent.click(screen.getByRole('button', { name: '重置当前分组' }));
    fireEvent.click(screen.getByRole('button', { name: '放弃修改' }));

    expect(resetDraftKeys).toHaveBeenCalledWith(['WEBUI_PORT']);
    expect(resetDraft).not.toHaveBeenCalled();
    expect(load).not.toHaveBeenCalled();
  });

  it('blocks in-app navigation only when there are unsaved changes', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    }));

    render(<SettingsPage />);

    const args: BlockerArgs = {
      currentLocation: { pathname: APP_ROUTE_PATHS.settings },
      nextLocation: { pathname: '/' },
    };
    expect(routerBlockerMock.shouldBlock?.(args)).toBe(true);
    expect(routerBlockerMock.shouldBlock?.({
      currentLocation: { pathname: APP_ROUTE_PATHS.settings },
      nextLocation: { pathname: APP_ROUTE_PATHS.settings },
    } satisfies BlockerArgs)).toBe(false);
  });

  it('does not block navigation without unsaved changes', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ hasDirty: false, dirtyCount: 0 }));

    render(<SettingsPage />);

    expect(routerBlockerMock.shouldBlock?.({
      currentLocation: { pathname: APP_ROUTE_PATHS.settings },
      nextLocation: { pathname: '/' },
    } satisfies BlockerArgs)).toBe(false);
  });

  it('confirms or cancels leaving settings with unsaved changes', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ hasDirty: true, dirtyCount: 2 }));
    routerBlockerMock.state = 'blocked';

    render(<SettingsPage />);

    expect(screen.getByText('离开设置页？')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(routerBlockerMock.reset).toHaveBeenCalledTimes(1);
    expect(routerBlockerMock.proceed).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '离开' }));
    expect(routerBlockerMock.proceed).toHaveBeenCalledTimes(1);
  });

  it('keeps agent execution fields on Agent Behavior but moves Event Monitor to the Alerts section', () => {
    const agentItems = () => buildSystemConfigState({
      activeCategory: 'agent',
      itemsByCategory: {
        ...buildSystemConfigState().itemsByCategory,
        agent: [
          {
            key: 'AGENT_ORCHESTRATOR_TIMEOUT_S',
            value: '600',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_ORCHESTRATOR_TIMEOUT_S',
              category: 'agent',
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
          {
            key: 'AGENT_DEEP_RESEARCH_BUDGET',
            value: '30000',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_DEEP_RESEARCH_BUDGET',
              category: 'agent',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 2,
            },
          },
          {
            key: 'AGENT_EVENT_MONITOR_ENABLED',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_EVENT_MONITOR_ENABLED',
              category: 'agent',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 3,
            },
          },
        ],
      },
    });

    // Agent Behavior section: execution fields only, Event Monitor moved out.
    useSystemConfigMock.mockReturnValue(agentItems());
    const { rerender } = render(<SettingsPage />);
    expect(screen.getByText('AGENT_ORCHESTRATOR_TIMEOUT_S')).toBeInTheDocument();
    expect(screen.getByText('AGENT_DEEP_RESEARCH_BUDGET')).toBeInTheDocument();
    expect(screen.queryByText('AGENT_EVENT_MONITOR_ENABLED')).not.toBeInTheDocument();
    expect(settingsPanelErrorBoundary).toHaveBeenCalledWith('Agent 设置');

    // Alerts Event Monitor tab: the dedicated card renders the agent-category event keys.
    useSystemConfigMock.mockReturnValue(agentItems());
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'events' });
    rerender(<SettingsPage />);
    // The Events view tab shares the card title, so scope to the heading.
    expect(screen.getByRole('heading', { name: '事件监控' })).toBeInTheDocument();
    expect(screen.getByText('AGENT_EVENT_MONITOR_ENABLED')).toBeInTheDocument();
    expect(screen.queryByText('AGENT_ORCHESTRATOR_TIMEOUT_S')).not.toBeInTheDocument();
  });

  it('renders context compression profile labels and blank preset guidance in the Conversation section', () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'agent',
      itemsByCategory: {
        ...configState.itemsByCategory,
        agent: [
          {
            key: 'AGENT_CONTEXT_COMPRESSION_PROFILE',
            value: 'balanced',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_CONTEXT_COMPRESSION_PROFILE',
              category: 'agent',
              dataType: 'string',
              uiControl: 'select',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [
                { label: '成本优先', value: 'cost' },
                { label: '均衡推荐', value: 'balanced' },
                { label: '长上下文原文优先', value: 'long_context_raw_first' },
              ],
              validation: {
                enum: ['cost', 'balanced', 'long_context_raw_first'],
              },
              displayOrder: 72,
            },
          },
          {
            key: 'AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
            value: '',
            rawValueExists: false,
            isMasked: false,
            schema: {
              key: 'AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
              category: 'agent',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: { min: 1000 },
              displayOrder: 73,
              description: '估算历史 token 超过该值时触发摘要；留空则跟随当前上下文压缩策略 profile 默认值。',
            },
          },
          {
            key: 'AGENT_CONTEXT_PROTECTED_TURNS',
            value: '',
            rawValueExists: false,
            isMasked: false,
            schema: {
              key: 'AGENT_CONTEXT_PROTECTED_TURNS',
              category: 'agent',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: { min: 1 },
              displayOrder: 74,
              description: '压缩时最近 N 个用户轮次及其后的回复保持原文；留空则跟随当前上下文压缩策略 profile 默认值。',
            },
          },
        ],
      },
    }));
    // Context compression fields now live under the Conversation section
    // (split out of the Agent category by the field placement map).
    routerSearchParamsMock.params = new URLSearchParams({ section: 'conversation', view: 'context' });

    render(<SettingsPage />);

    expect(screen.getByText('AGENT_CONTEXT_COMPRESSION_PROFILE')).toBeInTheDocument();
    expect(screen.getByText('成本优先')).toBeInTheDocument();
    expect(screen.getByText('均衡推荐')).toBeInTheDocument();
    expect(screen.getByText('长上下文原文优先')).toBeInTheDocument();
    expect(screen.getByText(/估算历史 token 超过该值时触发摘要/)).toHaveTextContent('留空则跟随当前上下文压缩策略 profile 默认值');
    expect(screen.getByText(/压缩时最近 N 个用户轮次及其后的回复保持原文/)).toHaveTextContent('留空则跟随当前上下文压缩策略 profile 默认值');
  });

  it('keeps Agent and Conversation fields inline in their own PR #35 groups', () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'agent',
      itemsByCategory: {
        ...configState.itemsByCategory,
        agent: [
          {
            key: 'AGENT_ORCHESTRATOR_TIMEOUT_S',
            value: '600',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_ORCHESTRATOR_TIMEOUT_S',
              category: 'agent',
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
          {
            key: 'AGENT_CONTEXT_COMPRESSION_PROFILE',
            value: 'balanced',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_CONTEXT_COMPRESSION_PROFILE',
              category: 'agent',
              dataType: 'string',
              uiControl: 'select',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [{ label: '均衡推荐', value: 'balanced' }],
              validation: { enum: ['balanced'] },
              displayOrder: 2,
            },
          },
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'agent_behavior', view: 'execution' });

    const { rerender } = render(<SettingsPage />);

    expect(screen.getByText('运行模式')).toBeInTheDocument();
    expect(screen.getByTestId('settings-field-AGENT_ORCHESTRATOR_TIMEOUT_S')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-AGENT_CONTEXT_COMPRESSION_PROFILE')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /配置.*Agent 设置/ })).not.toBeInTheDocument();

    routerSearchParamsMock.params = new URLSearchParams({ section: 'conversation', view: 'context' });
    rerender(<SettingsPage />);

    expect(screen.getByText('记忆与上下文')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-AGENT_ORCHESTRATOR_TIMEOUT_S')).not.toBeInTheDocument();
    expect(screen.getByTestId('settings-field-AGENT_CONTEXT_COMPRESSION_PROFILE')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /配置.*对话/ })).not.toBeInTheDocument();
  });

  it.each([
    ['agent_behavior', 'agent', 'AGENT_CONTEXT_COMPRESSION_PROFILE'],
    ['conversation', 'agent', 'AGENT_ORCHESTRATOR_TIMEOUT_S'],
    ['reports', 'notification', 'NOTIFICATION_ALERT_CHANNELS'],
    ['alerts', 'notification', 'REPORT_TYPE'],
  ] as const)(
    'shows an explicit empty state for %s when the backend category only contains sibling fields',
    (section, category, siblingKey) => {
      const configState = buildSystemConfigState();
      useSystemConfigMock.mockReturnValue(buildSystemConfigState({
        activeCategory: category,
        itemsByCategory: {
          ...configState.itemsByCategory,
          [category]: [{
            key: siblingKey,
            value: 'configured',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: siblingKey,
              category,
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 1,
            },
          }],
        },
      }));
      routerSearchParamsMock.params = new URLSearchParams({ section });

      render(<SettingsPage />);

      expect(screen.getByText('当前分类下暂无配置项')).toBeInTheDocument();
    },
  );

  it('keeps Advanced operational status and raw configuration in page flow', () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...configState.itemsByCategory,
        ai_model: [{
          key: 'UNPLACED_AI_FIELD',
          value: 'diagnostic-value',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'UNPLACED_AI_FIELD',
            category: 'ai_model',
            dataType: 'string',
            uiControl: 'text',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
          },
        }],
      },
    }));
    // Backend Status tab: mode banner + backend status panel, no raw fields.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'raw_config' });

    const { rerender } = render(<SettingsPage />);

    expect(screen.getByTestId('llm-config-mode-banner')).toBeInTheDocument();
    expect(screen.getByTestId('generation-backend-status-items')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-UNPLACED_AI_FIELD')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /配置.*高级/ })).not.toBeInTheDocument();

    // Developer Diagnostics tab: the aggregated fields render directly, uncollapsed.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'diagnostics' });
    rerender(<SettingsPage />);
    expect(screen.getByTestId('settings-field-UNPLACED_AI_FIELD')).toBeInTheDocument();
    expect(screen.queryByTestId('llm-config-mode-banner')).not.toBeInTheDocument();
  });

  it('keeps regular system configuration visible and editable on the page', () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [{
          key: 'WEBUI_PORT',
          value: '8000',
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
            validation: { min: 1, max: 65535 },
            displayOrder: 1,
          },
        }],
      },
    }));
    // WEBUI_PORT is a web-group field and renders on the Web & Logs tab.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'service' });

    render(<SettingsPage />);

    expect(screen.getByTestId('settings-field-WEBUI_PORT')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /配置.*系统设置/ })).not.toBeInTheDocument();
  });

  it('group reset discards local changes without a network request', () => {
    // Simulate user has unsaved drafts
    const dirtyState = buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    });

    useSystemConfigMock.mockReturnValue(dirtyState);

    render(<SettingsPage />);

    // Clear initial useEffect load call
    vi.clearAllMocks();

    // Click reset button, then confirm discarding drafts.
    fireEvent.click(screen.getByRole('button', { name: '重置当前分组' }));
    fireEvent.click(screen.getByRole('button', { name: '放弃修改' }));

    // Verify semantic: reset should only discard local changes
    // It should NOT trigger a network load
    expect(resetDraftKeys).toHaveBeenCalledWith(['WEBUI_PORT']);
    expect(resetDraft).not.toHaveBeenCalled();
    expect(load).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
  });

  it('refreshes server state after intelligent import merges stock list', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'merge stock list' }));

    expect(refreshAfterExternalSave).toHaveBeenCalledWith(['STOCK_LIST']);
    expect(load).toHaveBeenCalledTimes(1);
  });
}
