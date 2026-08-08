import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAgentChatStore } from '../agentChatStore';
import { createDeferred } from '../../test-utils';

vi.mock('../../api/agent', () => ({
  agentApi: {
    getChatSessions: vi.fn(async () => []),
    getChatSessionMessages: vi.fn(async () => []),
    chatStream: vi.fn(),
  },
}));

const { agentApi } = await import('../../api/agent');

const encoder = new TextEncoder();

function createStreamResponse(lines: string[]) {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(lines.join('\n')));
        controller.close();
      },
    }),
    {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    },
  );
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  useAgentChatStore.setState({
    messages: [],
    selectedSkillIds: null,
    loading: false,
    progressSteps: [],
    sessionId: 'session-test',
    sessions: [],
    sessionsLoading: false,
    chatError: null,
    currentRoute: '/chat',
    completionBadge: false,
    hasInitialLoad: true,
    abortController: null,
    lastFailedRequest: null,
  });
  vi.clearAllMocks();
});

describe('agentChatStore session lifecycle', () => {
  it('hydrates the URL session instead of the locally saved session', async () => {
    localStorage.setItem('dsa_chat_session_id', 'session-local');
    useAgentChatStore.setState({
      sessionId: 'session-generated',
      hasInitialLoad: false,
    });
    vi.mocked(agentApi.getChatSessions).mockResolvedValue([
      {
        session_id: 'session-local',
        title: 'Local session',
        message_count: 0,
        created_at: '2026-07-15T00:00:00Z',
        last_active: '2026-07-15T00:00:00Z',
      },
      {
        session_id: 'session-url',
        title: 'Shared session',
        message_count: 1,
        created_at: '2026-07-15T00:00:00Z',
        last_active: '2026-07-15T00:00:00Z',
      },
    ]);
    vi.mocked(agentApi.getChatSessionMessages).mockResolvedValue({
      session_id: 'session-url',
      messages: [
        { id: 'url-message', role: 'assistant', content: 'URL session reply', created_at: null },
      ],
      session_state: { selected_skill_ids: null },
    });

    await useAgentChatStore.getState().loadInitialSession('session-url');

    const state = useAgentChatStore.getState();
    expect(state.sessionId).toBe('session-url');
    expect(state.messages).toEqual([
      { id: 'url-message', role: 'assistant', content: 'URL session reply' },
    ]);
    expect(sessionStorage.getItem('dsa_chat_session_id')).toBe('session-url');
    expect(localStorage.getItem('dsa_chat_session_id')).toBeNull();
  });

  it('returns the new session ID so the router can persist it', () => {
    const sessionId = useAgentChatStore.getState().startNewChat();

    expect(sessionId).toBe(useAgentChatStore.getState().sessionId);
    expect(sessionId).toBe(sessionStorage.getItem('dsa_chat_session_id'));
  });

  it('clears persisted and in-memory chat state for logout', () => {
    const abortController = new AbortController();
    sessionStorage.setItem('dsa_chat_session_id', 'session-private');
    useAgentChatStore.setState({
      sessionId: 'session-private',
      messages: [{ id: 'message-1', role: 'user', content: 'Private draft' }],
      sessions: [{
        session_id: 'session-private',
        title: 'Private session',
        message_count: 1,
        created_at: '2026-07-15T00:00:00Z',
        last_active: '2026-07-15T00:00:00Z',
      }],
      loading: true,
      abortController,
    });

    useAgentChatStore.getState().resetSessionState();

    const state = useAgentChatStore.getState();
    expect(abortController.signal.aborted).toBe(true);
    expect(state.messages).toEqual([]);
    expect(state.sessions).toEqual([]);
    expect(state.loading).toBe(false);
    expect(state.hasInitialLoad).toBe(false);
    expect(state.sessionId).not.toBe('session-private');
    expect(sessionStorage.getItem('dsa_chat_session_id')).toBeNull();
  });
});

describe('agentChatStore.startStream', () => {
  it('appends the user message and final assistant message from the SSE stream', async () => {
    vi.mocked(agentApi.chatStream).mockResolvedValue(
      createStreamResponse([
        'data: {"type":"thinking","step":1,"message":"分析中"}',
        'data: {"type":"tool_done","tool":"quote","display_name":"行情","success":true,"duration":0.3}',
        'data: {"type":"done","success":true,"content":"最终分析结果"}',
      ]),
    );

    await useAgentChatStore
      .getState()
      .startStream({ message: '分析茅台', session_id: 'session-test' }, { skillName: '趋势技能' });

    const state = useAgentChatStore.getState();
    expect(state.loading).toBe(false);
    expect(state.chatError).toBeNull();
    expect(state.messages).toHaveLength(2);
    expect(state.messages[0]).toMatchObject({
      role: 'user',
      content: '分析茅台',
      skillName: '趋势技能',
    });
    expect(state.messages[1]).toMatchObject({
      role: 'assistant',
      content: '最终分析结果',
      skillName: '趋势技能',
    });
    expect(state.messages[1].thinkingSteps).toHaveLength(2);
    expect(state.progressSteps).toEqual([]);
  });

  it('preserves multiple selected skills on streamed user and assistant messages', async () => {
    vi.mocked(agentApi.chatStream).mockResolvedValue(
      createStreamResponse([
        'data: {"type":"done","success":true,"content":"多策略分析结果"}',
      ]),
    );

    await useAgentChatStore
      .getState()
      .startStream(
        {
          message: '分析茅台',
          session_id: 'session-test',
          skills: ['bull_trend', 'ma_golden_cross'],
        },
        {
          skillNames: ['趋势分析', '均线金叉'],
        },
      );

    const state = useAgentChatStore.getState();
    expect(state.messages).toHaveLength(2);
    expect(state.messages[0]).toMatchObject({
      role: 'user',
      skills: ['bull_trend', 'ma_golden_cross'],
      skill: 'bull_trend',
      skillNames: ['趋势分析', '均线金叉'],
      skillName: '趋势分析、均线金叉',
    });
    expect(state.messages[1]).toMatchObject({
      role: 'assistant',
      content: '多策略分析结果',
      skills: ['bull_trend', 'ma_golden_cross'],
      skill: 'bull_trend',
      skillNames: ['趋势分析', '均线金叉'],
      skillName: '趋势分析、均线金叉',
    });
  });

  it('reports an interrupted stream instead of appending an empty assistant message', async () => {
    vi.mocked(agentApi.chatStream).mockResolvedValue(
      createStreamResponse([
        'data: {"type":"thinking","step":1,"message":"分析中"}',
      ]),
    );

    await useAgentChatStore
      .getState()
      .startStream({ message: '分析茅台', session_id: 'session-test' }, { skillName: '趋势技能' });

    const state = useAgentChatStore.getState();
    expect(state.loading).toBe(false);
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]).toMatchObject({
      role: 'user',
      content: '分析茅台',
    });
    expect(state.chatError).toMatchObject({
      title: '回复未完整返回',
      message: 'Agent 流式响应在完成前中断，请重试。',
      category: 'upstream_network',
      rawMessage: 'Agent stream ended before a done event was received.',
    });
  });

  it('preserves parsed error details when done.success is false', async () => {
    vi.mocked(agentApi.chatStream).mockResolvedValue(
      createStreamResponse([
        'data: {"type":"done","success":false,"error":"Agent LLM: no effective primary model configured"}',
      ]),
    );

    await useAgentChatStore
      .getState()
      .startStream({ message: '分析茅台', session_id: 'session-test' }, { skillName: '趋势技能' });

    const state = useAgentChatStore.getState();
    expect(state.loading).toBe(false);
    expect(state.messages).toHaveLength(1);
    expect(state.chatError).toMatchObject({
      title: '系统没有配置可用的 LLM 模型',
      message: '请先在系统设置中配置主要模型、可用连接或相关 API 密钥后再重试。',
      category: 'llm_not_configured',
      rawMessage: 'Agent LLM: no effective primary model configured',
    });
  });

  it('uses the same parser for SSE error events', async () => {
    vi.mocked(agentApi.chatStream).mockResolvedValue(
      createStreamResponse([
        'data: {"type":"error","message":"connect timeout while calling upstream provider"}',
      ]),
    );

    await useAgentChatStore
      .getState()
      .startStream({ message: '分析茅台', session_id: 'session-test' }, { skillName: '趋势技能' });

    const state = useAgentChatStore.getState();
    expect(state.loading).toBe(false);
    expect(state.messages).toHaveLength(1);
    expect(state.chatError).toMatchObject({
      title: '连接上游服务超时',
      message: '服务端访问外部依赖时超时，请稍后重试，或检查当前网络与代理设置。',
      category: 'upstream_timeout',
      rawMessage: 'connect timeout while calling upstream provider',
    });
  });

  it('falls back when SSE error fields are empty strings', async () => {
    vi.mocked(agentApi.chatStream).mockResolvedValue(
      createStreamResponse([
        'data: {"type":"error","error":"","message":"   ","content":""}',
      ]),
    );

    await useAgentChatStore
      .getState()
      .startStream({ message: '分析茅台', session_id: 'session-test' }, { skillName: '趋势技能' });

    const state = useAgentChatStore.getState();
    expect(state.loading).toBe(false);
    expect(state.messages).toHaveLength(1);
    expect(state.chatError).toMatchObject({
      title: '请求失败',
      message: '请求未能完成，请稍后重试。',
      category: 'unknown',
      rawMessage: '分析出错',
    });
  });

  it('retries a failed stream without appending the user message twice', async () => {
    vi.mocked(agentApi.chatStream)
      .mockResolvedValueOnce(createStreamResponse([
        'data: {"type":"error","error":"agent_stream_failed","message":"upstream disconnected"}',
      ]))
      .mockResolvedValueOnce(createStreamResponse([
        'data: {"type":"done","success":true,"content":"重试后的分析结果"}',
      ]));

    await useAgentChatStore
      .getState()
      .startStream({ message: '分析茅台', session_id: 'session-test' }, { skillName: '趋势技能' });

    expect(useAgentChatStore.getState().messages).toHaveLength(1);
    expect(useAgentChatStore.getState().lastFailedRequest).not.toBeNull();

    await useAgentChatStore.getState().retryLastStream();

    const state = useAgentChatStore.getState();
    expect(state.chatError).toBeNull();
    expect(state.lastFailedRequest).toBeNull();
    expect(state.messages).toHaveLength(2);
    expect(state.messages.map((message) => message.role)).toEqual(['user', 'assistant']);
    expect(state.messages[1].content).toBe('重试后的分析结果');
    expect(agentApi.chatStream).toHaveBeenCalledTimes(2);
  });
});

describe('agentChatStore.stopStream', () => {
  it('aborts the in-flight stream and clears transient state, keeping messages', () => {
    const ac = new AbortController();
    useAgentChatStore.setState({
      loading: true,
      progressSteps: [{ type: 'thinking', message: '正在制定分析路径...' }],
      abortController: ac,
      messages: [{ id: 'u1', role: 'user', content: '茅台怎么看' }],
    });

    useAgentChatStore.getState().stopStream();

    const state = useAgentChatStore.getState();
    expect(ac.signal.aborted).toBe(true);
    expect(state.loading).toBe(false);
    expect(state.progressSteps).toEqual([]);
    expect(state.abortController).toBeNull();
    // The user's message is preserved so the transcript is not lost.
    expect(state.messages).toEqual([{ id: 'u1', role: 'user', content: '茅台怎么看' }]);
  });

  it('is a no-op when there is no active stream', () => {
    useAgentChatStore.setState({ loading: false, abortController: null });
    expect(() => useAgentChatStore.getState().stopStream()).not.toThrow();
    expect(useAgentChatStore.getState().loading).toBe(false);
  });

  it('returns aborted from startStream and keeps lastFailedRequest null when stopStream cancels the request', async () => {
    const hang = createDeferred<Response>();
    vi.mocked(agentApi.chatStream).mockImplementation((_payload, options) => {
      const signal = options?.signal;
      if (signal?.aborted) {
        return Promise.reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
      }
      return new Promise<Response>((resolve, reject) => {
        const onAbort = () => {
          reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
        };
        signal?.addEventListener('abort', onAbort, { once: true });
        void hang.promise.then(resolve, reject);
      });
    });

    const outcomePromise = useAgentChatStore
      .getState()
      .startStream({ message: '分析茅台', session_id: 'session-test' }, { skillName: '趋势技能' });

    await vi.waitFor(() => {
      expect(useAgentChatStore.getState().loading).toBe(true);
      expect(useAgentChatStore.getState().abortController).not.toBeNull();
    });

    useAgentChatStore.getState().stopStream();

    await expect(outcomePromise).resolves.toBe('aborted');
    const state = useAgentChatStore.getState();
    expect(state.lastFailedRequest).toBeNull();
    expect(state.chatError).toBeNull();
    expect(state.loading).toBe(false);
  });
});

describe('agentChatStore.switchSession', () => {

  it('clears transient loading state when switching sessions during a stream', async () => {
    const ac = new AbortController();
    vi.mocked(agentApi.getChatSessionMessages).mockResolvedValue({
      session_id: 'session-2',
      messages: [
        { id: 'msg-2', role: 'assistant', content: '历史回复', created_at: null },
      ],
      session_state: { selected_skill_ids: ['risk'] },
    });
    useAgentChatStore.setState({
      loading: true,
      progressSteps: [{ type: 'thinking', message: '正在制定分析路径...' }],
      abortController: ac,
      chatError: {
        title: '请求失败',
        message: '旧错误',
        category: 'unknown',
        rawMessage: '旧错误',
      },
    });

    await useAgentChatStore.getState().switchSession('session-2');

    const state = useAgentChatStore.getState();
    expect(ac.signal.aborted).toBe(true);
    expect(state.sessionId).toBe('session-2');
    expect(state.loading).toBe(false);
    expect(state.progressSteps).toEqual([]);
    expect(state.abortController).toBeNull();
    expect(state.chatError).toBeNull();
    expect(state.messages).toEqual([
      { id: 'msg-2', role: 'assistant', content: '历史回复' },
    ]);
    expect(state.selectedSkillIds).toEqual(['risk']);
  });

  it('preserves stable failure metadata from persisted session history', async () => {
    vi.mocked(agentApi.getChatSessionMessages).mockResolvedValue({
      session_id: 'failed-session',
      messages: [
        {
          id: 'msg-failed',
          role: 'assistant',
          content: 'Agent chat failed',
          created_at: null,
          error: 'agent_chat_failed',
          params: {},
        },
      ],
      session_state: { selected_skill_ids: null },
    });

    await useAgentChatStore.getState().switchSession('failed-session');

    expect(useAgentChatStore.getState().messages).toEqual([{
      id: 'msg-failed',
      role: 'assistant',
      content: 'Agent chat failed',
      error: 'agent_chat_failed',
      params: {},
    }]);
  });

  it('does not let a late session history response overwrite the current session', async () => {
    const sessionA = createDeferred<Awaited<ReturnType<typeof agentApi.getChatSessionMessages>>>();
    const sessionB = createDeferred<Awaited<ReturnType<typeof agentApi.getChatSessionMessages>>>();
    vi.mocked(agentApi.getChatSessionMessages).mockImplementation((targetSessionId: string) => {
      if (targetSessionId === 'session-a') return sessionA.promise;
      if (targetSessionId === 'session-b') return sessionB.promise;
      return Promise.resolve({
        session_id: targetSessionId,
        messages: [],
        session_state: { selected_skill_ids: [] },
      });
    });

    const switchToA = useAgentChatStore.getState().switchSession('session-a');
    const switchToB = useAgentChatStore.getState().switchSession('session-b');

    sessionB.resolve({
      session_id: 'session-b',
      messages: [{ id: 'msg-b', role: 'assistant', content: 'B 回复', created_at: null }],
      session_state: { selected_skill_ids: ['risk'] },
    });
    await switchToB;

    sessionA.resolve({
      session_id: 'session-a',
      messages: [{ id: 'msg-a', role: 'assistant', content: 'A 回复', created_at: null }],
      session_state: { selected_skill_ids: ['technical'] },
    });
    await switchToA;

    const state = useAgentChatStore.getState();
    expect(state.sessionId).toBe('session-b');
    expect(state.messages).toEqual([
      { id: 'msg-b', role: 'assistant', content: 'B 回复' },
    ]);
    expect(state.selectedSkillIds).toEqual(['risk']);
  });
});

describe('agentChatStore.loadInitialSession', () => {
  it('does not let late initial hydration overwrite a session selected afterward', async () => {
    const sessions = createDeferred<Awaited<ReturnType<typeof agentApi.getChatSessions>>>();
    useAgentChatStore.setState({ hasInitialLoad: false });
    vi.mocked(agentApi.getChatSessions).mockImplementationOnce(() => sessions.promise);
    vi.mocked(agentApi.getChatSessionMessages).mockResolvedValue({
      session_id: 'url-session',
      messages: [],
      session_state: { selected_skill_ids: [] },
    });

    const initialLoad = useAgentChatStore.getState().loadInitialSession('url-session');
    const switchLoad = useAgentChatStore.getState().switchSession('newer-session');
    sessions.resolve([]);
    await Promise.all([initialLoad, switchLoad]);

    expect(useAgentChatStore.getState().sessionId).toBe('newer-session');
  });
});


describe('agentChatStore session Skill state', () => {
  it('restores the saved Skill selection during the initial session load', async () => {
    const { writeSessionItem, CHAT_SESSION_STORAGE_KEY } = await import('../../utils/sessionPersistence');
    writeSessionItem(CHAT_SESSION_STORAGE_KEY, 'saved-session');
    useAgentChatStore.setState({ hasInitialLoad: false });
    vi.mocked(agentApi.getChatSessions).mockResolvedValue([
      {
        session_id: 'saved-session',
        title: 'saved',
        message_count: 1,
        created_at: null,
        last_active: null,
      },
    ]);
    vi.mocked(agentApi.getChatSessionMessages).mockResolvedValue({
      session_id: 'saved-session',
      messages: [
        { id: 'msg-1', role: 'user', content: '分析 AAPL', created_at: null },
      ],
      session_state: { selected_skill_ids: ['technical', 'risk'] },
    });

    await useAgentChatStore.getState().loadInitialSession();

    expect(useAgentChatStore.getState().selectedSkillIds).toEqual([
      'technical',
      'risk',
    ]);
  });

  it('preserves null when an initial legacy session has no persisted Skill state', async () => {
    const { writeSessionItem, CHAT_SESSION_STORAGE_KEY } = await import('../../utils/sessionPersistence');
    writeSessionItem(CHAT_SESSION_STORAGE_KEY, 'legacy-session');
    useAgentChatStore.setState({ hasInitialLoad: false });
    vi.mocked(agentApi.getChatSessions).mockResolvedValue([
      {
        session_id: 'legacy-session',
        title: 'legacy',
        message_count: 1,
        created_at: null,
        last_active: null,
      },
    ]);
    vi.mocked(agentApi.getChatSessionMessages).mockResolvedValue({
      session_id: 'legacy-session',
      messages: [
        { id: 'msg-1', role: 'user', content: '分析 AAPL', created_at: null },
      ],
      session_state: { selected_skill_ids: null },
    });

    await useAgentChatStore.getState().loadInitialSession();

    expect(useAgentChatStore.getState().selectedSkillIds).toBeNull();
  });

  it('clears the previous session Skill selection for a new chat', () => {
    useAgentChatStore.setState({ selectedSkillIds: ['risk'] });

    useAgentChatStore.getState().startNewChat();

    expect(useAgentChatStore.getState().selectedSkillIds).toBeNull();
  });
});
