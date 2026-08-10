import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getSkills: vi.fn(),
  chatStream: vi.fn(),
  getChatSessions: vi.fn(),
  getChatSessionMessages: vi.fn(),
  historyDetail: vi.fn(),
  getSetupStatus: vi.fn(),
  getConfig: vi.fn(),
}));

vi.mock('../../api/agent', () => ({
  agentApi: {
    getSkills: mocks.getSkills,
    chatStream: mocks.chatStream,
    getChatSessions: mocks.getChatSessions,
    getChatSessionMessages: mocks.getChatSessionMessages,
    deleteChatSession: vi.fn(),
    sendChat: vi.fn(),
  },
}));

vi.mock('../../api/history', () => ({
  historyApi: { getDetail: mocks.historyDetail },
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getSetupStatus: mocks.getSetupStatus,
    getConfig: mocks.getConfig,
    getWatchlist: vi.fn(async () => []),
    addToWatchlist: vi.fn(async () => []),
    removeFromWatchlist: vi.fn(async () => []),
    update: vi.fn(),
  },
}));

import ChatPage from '../ChatPage';
import { useAgentChatStore } from '../../stores/agentChatStore';

describe('ChatPage turn persistence integration', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn((query: string) => ({
        matches: query === '(prefers-color-scheme: dark)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      writable: true,
      value: vi.fn(),
    });
  });

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
    useAgentChatStore.getState().resetSessionState();
    useAgentChatStore.setState({
      sessionId: 'session-integration',
      messages: [],
      selectedSkillIds: null,
      loading: false,
      progressSteps: [],
      sessions: [],
      sessionsLoading: false,
      sessionsError: null,
      sessionLoading: false,
      sessionError: null,
      chatError: null,
      currentRoute: '/chat',
      completionBadge: false,
      hasInitialLoad: true,
      abortController: null,
      lastFailedRequest: null,
    });
    mocks.getSkills.mockResolvedValue({
      skills: [{ id: 'bull_trend', name: 'Trend', description: 'Trend analysis' }],
      default_skill_id: 'bull_trend',
    });
    mocks.getChatSessions.mockResolvedValue([]);
    mocks.getSetupStatus.mockResolvedValue({
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      nextStepKey: null,
      checks: [],
    });
    mocks.getConfig.mockResolvedValue({
      configVersion: 'cfg-v1',
      maskToken: '******',
      items: [{
        key: 'AGENT_CONTEXT_COMPRESSION_ENABLED',
        value: 'false',
        rawValueExists: true,
        isMasked: false,
      }],
    });
    mocks.historyDetail.mockResolvedValue({
      meta: {
        id: 3,
        queryId: 'q-3',
        stockCode: 'AAPL',
        stockName: 'Apple',
        reportType: 'detailed',
        createdAt: '2026-08-10T00:00:00Z',
      },
      summary: { analysisSummary: 'Stable' },
      strategy: {},
    });
  });

  it('keeps one persisted transcript turn and consumes report context after Stop', async () => {
    mocks.chatStream.mockImplementation(async (payload, options) => {
      const encoder = new TextEncoder();
      return new Response(new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(
            `data: {"type":"turn_persisted","turn_id":"${payload.turn_id}","message_id":"17"}\n\n`,
          ));
          options?.signal?.addEventListener('abort', () => {
            controller.error(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
          }, { once: true });
        },
      }), { status: 200 });
    });

    const router = createMemoryRouter(
      [{ path: '/chat', element: <ChatPage /> }],
      { initialEntries: ['/chat?stock=AAPL&name=Apple&recordId=3'] },
    );
    render(<RouterProvider router={router} />);

    const draft = await screen.findByDisplayValue('请深入分析 Apple(AAPL)');
    await waitFor(() => expect(screen.getByRole('button', { name: '发送' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    fireEvent.click(await screen.findByRole('button', { name: '停止生成' }));

    await waitFor(() => expect(useAgentChatStore.getState().loading).toBe(false));
    expect(useAgentChatStore.getState().messages.filter((message) => message.role === 'user'))
      .toHaveLength(1);
    expect(draft).toHaveValue('');
    expect(screen.queryByDisplayValue('请深入分析 Apple(AAPL)')).not.toBeInTheDocument();
    const params = Object.fromEntries(new URLSearchParams(router.state.location.search));
    expect(params).toMatchObject({
      stock: 'AAPL',
      name: 'Apple',
      session: 'session-integration',
      context: 'active',
    });
    expect(params.recordId).toBe('3');
  });
});
