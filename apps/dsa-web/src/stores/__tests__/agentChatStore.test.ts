import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAgentChatStore } from '../agentChatStore';

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

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  localStorage.clear();
  useAgentChatStore.setState({
    messages: [],
    loading: false,
    streamStatus: 'idle',
    progressSteps: [],
    sessionId: 'session-test',
    sessions: [],
    sessionsLoading: false,
    chatError: null,
    currentRoute: '/chat',
    completionBadge: false,
    hasInitialLoad: true,
    abortController: null,
    failedStreamRequest: null,
    sessionLoadRevision: 0,
    sessionsLoadRevision: 0,
  });
  vi.clearAllMocks();
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
      title: 'Agent 响应中断',
      message: '流式响应未能完成，请重试。',
      category: 'upstream_network',
      code: 'agent_stream_failed',
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
      message: '分析出错',
      category: 'unknown',
      rawMessage: '分析出错',
    });
  });

  it('retries a failed stream without duplicating the user message', async () => {
    vi.mocked(agentApi.chatStream)
      .mockRejectedValueOnce(new Error('connect timeout while calling upstream provider'))
      .mockResolvedValueOnce(createStreamResponse([
        'data: {"type":"done","success":true,"content":"重试成功"}',
      ]));

    await useAgentChatStore.getState().startStream(
      { message: '分析茅台', session_id: 'session-test' },
      { skillName: '趋势技能' },
    );

    expect(useAgentChatStore.getState().messages).toHaveLength(1);
    expect(useAgentChatStore.getState().streamStatus).toBe('failed');
    expect(useAgentChatStore.getState().failedStreamRequest).not.toBeNull();

    await useAgentChatStore.getState().retryLastFailedStream();

    const state = useAgentChatStore.getState();
    expect(agentApi.chatStream).toHaveBeenCalledTimes(2);
    expect(state.messages).toHaveLength(2);
    expect(state.messages.map((message) => message.role)).toEqual(['user', 'assistant']);
    expect(state.messages[1].content).toBe('重试成功');
    expect(state.chatError).toBeNull();
    expect(state.failedStreamRequest).toBeNull();
    expect(state.streamStatus).toBe('idle');
  });

  it('does not let a late stream update a newly selected session', async () => {
    const deferredResponse = createDeferred<Response>();
    vi.mocked(agentApi.chatStream).mockReturnValueOnce(deferredResponse.promise);
    vi.mocked(agentApi.getChatSessionMessages).mockResolvedValueOnce([
      { id: 'msg-new', role: 'assistant', content: '新会话内容', created_at: null },
    ]);

    const oldStream = useAgentChatStore.getState().startStream(
      { message: '旧会话问题', session_id: 'session-test' },
      { skillName: '趋势技能' },
    );
    await useAgentChatStore.getState().switchSession('session-new');

    deferredResponse.resolve(createStreamResponse([
      'data: {"type":"thinking","message":"旧进度"}',
      'data: {"type":"error","message":"old stream failed"}',
    ]));
    await oldStream;

    const state = useAgentChatStore.getState();
    expect(state.sessionId).toBe('session-new');
    expect(state.messages).toEqual([
      { id: 'msg-new', role: 'assistant', content: '新会话内容' },
    ]);
    expect(state.progressSteps).toEqual([]);
    expect(state.chatError).toBeNull();
    expect(state.streamStatus).toBe('idle');
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
});

describe('agentChatStore.switchSession', () => {

  it('clears transient loading state when switching sessions during a stream', async () => {
    const ac = new AbortController();
    vi.mocked(agentApi.getChatSessionMessages).mockResolvedValue([
      { id: 'msg-2', role: 'assistant', content: '历史回复', created_at: null },
    ]);
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
  });

  it('does not let a late session history response overwrite the current session', async () => {
    const sessionA = createDeferred<
      Array<{ id: string; role: 'user' | 'assistant'; content: string; created_at: string | null }>
    >();
    const sessionB = createDeferred<
      Array<{ id: string; role: 'user' | 'assistant'; content: string; created_at: string | null }>
    >();
    vi.mocked(agentApi.getChatSessionMessages).mockImplementation((targetSessionId: string) => {
      if (targetSessionId === 'session-a') return sessionA.promise;
      if (targetSessionId === 'session-b') return sessionB.promise;
      return Promise.resolve([]);
    });

    const switchToA = useAgentChatStore.getState().switchSession('session-a');
    const switchToB = useAgentChatStore.getState().switchSession('session-b');

    sessionB.resolve([{ id: 'msg-b', role: 'assistant', content: 'B 回复', created_at: null }]);
    await switchToB;

    sessionA.resolve([{ id: 'msg-a', role: 'assistant', content: 'A 回复', created_at: null }]);
    await switchToA;

    const state = useAgentChatStore.getState();
    expect(state.sessionId).toBe('session-b');
    expect(state.messages).toEqual([
      { id: 'msg-b', role: 'assistant', content: 'B 回复' },
    ]);
  });
});

describe('agentChatStore.loadInitialSession', () => {
  it('prefers the URL session and hydrates it even when it is outside the recent list', async () => {
    useAgentChatStore.setState({ hasInitialLoad: false });
    vi.mocked(agentApi.getChatSessions).mockResolvedValueOnce([]);
    vi.mocked(agentApi.getChatSessionMessages).mockResolvedValueOnce([
      { id: 'url-message', role: 'assistant', content: '深链会话', created_at: null },
    ]);

    await useAgentChatStore.getState().loadInitialSession('session-from-url');

    const state = useAgentChatStore.getState();
    expect(agentApi.getChatSessionMessages).toHaveBeenCalledWith('session-from-url');
    expect(state.sessionId).toBe('session-from-url');
    expect(state.messages).toEqual([
      { id: 'url-message', role: 'assistant', content: '深链会话' },
    ]);
    expect(localStorage.getItem('dsa_chat_session_id')).toBe('session-from-url');
  });

  it('surfaces a failed URL-session hydration without replacing the requested session', async () => {
    useAgentChatStore.setState({ hasInitialLoad: false });
    vi.mocked(agentApi.getChatSessions).mockResolvedValueOnce([]);
    vi.mocked(agentApi.getChatSessionMessages).mockRejectedValueOnce(new Error('session unavailable'));

    await useAgentChatStore.getState().loadInitialSession('session-from-url');

    const state = useAgentChatStore.getState();
    expect(state.sessionId).toBe('session-from-url');
    expect(state.messages).toEqual([]);
    expect(state.chatError).toMatchObject({ rawMessage: 'session unavailable' });
  });
});
