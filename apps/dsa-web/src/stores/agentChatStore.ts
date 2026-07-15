import { create } from 'zustand';
import { agentApi } from '../api/agent';
import type { ChatSessionItem, ChatStreamRequest } from '../api/agent';
import {
  createParsedApiError,
  getParsedApiError,
  isApiRequestError,
  isParsedApiError,
  type ParsedApiError,
} from '../api/error';
import { generateUUID } from '../utils/uuid';

const STORAGE_KEY_SESSION = 'dsa_chat_session_id';

export interface ProgressStep {
  type: string;
  step?: number;
  stage?: string;
  tool?: string;
  display_name?: string;
  status?: string;
  success?: boolean;
  duration?: number;
  elapsed?: number;
  timeout?: number;
  remaining?: number;
  minimum?: number;
  reason?: string;
  message?: string;
  content?: string;
  meta?: Record<string, unknown>;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  skills?: string[];
  skill?: string;
  skillNames?: string[];
  skillName?: string;
  thinkingSteps?: ProgressStep[];
}

export interface StreamMeta {
  skillNames?: string[];
  skillName?: string;
}

type StreamStatus = 'idle' | 'streaming' | 'failed';

type FailedStreamRequest = {
  payload: ChatStreamRequest;
  meta?: StreamMeta;
  sessionId: string;
  userMessageId: string;
};

type StreamFailureEvent = {
  type: string;
  success?: boolean;
  content?: string;
  error?: unknown;
  message?: unknown;
  error_code?: unknown;
  error_params?: unknown;
  details?: unknown;
};

function getFirstMeaningfulStreamError(...candidates: Array<unknown>): unknown {
  for (const candidate of candidates) {
    if (typeof candidate === 'string') {
      if (candidate.trim() !== '') {
        return candidate;
      }
      continue;
    }

    if (candidate != null) {
      return candidate;
    }
  }

  return undefined;
}

function getStreamFailureError(
  event: StreamFailureEvent,
  fallbackMessage: string,
): ParsedApiError {
  if (typeof event.error_code === 'string' && event.error_code.trim()) {
    return getParsedApiError({
      response: {
        data: {
          error: event.error_code,
          message: getFirstMeaningfulStreamError(event.message, fallbackMessage),
          params: event.error_params,
          details: event.details,
        },
      },
    });
  }
  return getParsedApiError(
    getFirstMeaningfulStreamError(
      event.error,
      event.message,
      event.content,
      fallbackMessage,
    ),
  );
}

interface AgentChatState {
  messages: Message[];
  loading: boolean;
  streamStatus: StreamStatus;
  progressSteps: ProgressStep[];
  sessionId: string;
  sessions: ChatSessionItem[];
  sessionsLoading: boolean;
  chatError: ParsedApiError | null;
  currentRoute: string;
  completionBadge: boolean;
  hasInitialLoad: boolean;
  abortController: AbortController | null;
  failedStreamRequest: FailedStreamRequest | null;
  sessionLoadRevision: number;
  sessionsLoadRevision: number;
}

interface AgentChatActions {
  setCurrentRoute: (path: string) => void;
  clearCompletionBadge: () => void;
  loadSessions: () => Promise<void>;
  loadInitialSession: (preferredSessionId?: string) => Promise<void>;
  switchSession: (targetSessionId: string) => Promise<void>;
  startNewChat: () => void;
  startStream: (payload: ChatStreamRequest, meta?: StreamMeta) => Promise<void>;
  retryLastFailedStream: () => Promise<void>;
  stopStream: () => void;
}

const getInitialSessionId = (): string =>
  typeof localStorage !== 'undefined'
    ? localStorage.getItem(STORAGE_KEY_SESSION) || generateUUID()
    : generateUUID();

export const useAgentChatStore = create<AgentChatState & AgentChatActions>((set, get) => ({
  messages: [],
  loading: false,
  streamStatus: 'idle',
  progressSteps: [],
  sessionId: getInitialSessionId(),
  sessions: [],
  sessionsLoading: false,
  chatError: null,
  currentRoute: '',
  completionBadge: false,
  hasInitialLoad: false,
  abortController: null,
  failedStreamRequest: null,
  sessionLoadRevision: 0,
  sessionsLoadRevision: 0,

  setCurrentRoute: (path) => set({ currentRoute: path }),

  clearCompletionBadge: () => set({ completionBadge: false }),

  loadSessions: async () => {
    const requestRevision = get().sessionsLoadRevision + 1;
    set({ sessionsLoadRevision: requestRevision, sessionsLoading: true });
    try {
      const sessions = await agentApi.getChatSessions();
      if (get().sessionsLoadRevision === requestRevision) {
        set({ sessions });
      }
    } catch {
      // Ignore load errors
    } finally {
      if (get().sessionsLoadRevision === requestRevision) {
        set({ sessionsLoading: false });
      }
    }
  },

  loadInitialSession: async (preferredSessionId) => {
    const { hasInitialLoad } = get();
    if (hasInitialLoad) return;
    const requestRevision = get().sessionLoadRevision + 1;
    const savedId = localStorage.getItem(STORAGE_KEY_SESSION);
    const initialSessionId = preferredSessionId || savedId || get().sessionId;
    set({
      hasInitialLoad: true,
      sessionsLoading: true,
      sessionLoadRevision: requestRevision,
      sessionId: initialSessionId,
      messages: [],
      chatError: null,
      failedStreamRequest: null,
      streamStatus: 'idle',
    });
    localStorage.setItem(STORAGE_KEY_SESSION, initialSessionId);

    try {
      const sessionList = await agentApi.getChatSessions();
      if (get().sessionLoadRevision !== requestRevision) return;
      set({ sessions: sessionList });

      const shouldLoadHistory = Boolean(preferredSessionId)
        || sessionList.some((session) => session.session_id === initialSessionId);
      if (shouldLoadHistory) {
        const msgs = await agentApi.getChatSessionMessages(initialSessionId);
        if (get().sessionLoadRevision !== requestRevision || get().sessionId !== initialSessionId) return;
        set({
          messages: msgs.map((message) => ({
            id: message.id,
            role: message.role,
            content: message.content,
          })),
        });
      } else if (savedId && !preferredSessionId) {
        const newId = generateUUID();
        set({ sessionId: newId });
        localStorage.setItem(STORAGE_KEY_SESSION, newId);
      }
    } catch (error) {
      if (get().sessionLoadRevision === requestRevision && get().sessionId === initialSessionId) {
        set({ chatError: getParsedApiError(error) });
      }
    } finally {
      if (get().sessionLoadRevision === requestRevision) {
        set({ sessionsLoading: false });
      }
    }
  },

  switchSession: async (targetSessionId) => {
    const { sessionId, messages, abortController } = get();
    if (targetSessionId === sessionId && messages.length > 0) return;

    abortController?.abort();
    const requestRevision = get().sessionLoadRevision + 1;
    set({
      messages: [],
      sessionId: targetSessionId,
      loading: false,
      streamStatus: 'idle',
      progressSteps: [],
      chatError: null,
      abortController: null,
      failedStreamRequest: null,
      sessionsLoading: true,
      sessionLoadRevision: requestRevision,
    });
    localStorage.setItem(STORAGE_KEY_SESSION, targetSessionId);

    try {
      const msgs = await agentApi.getChatSessionMessages(targetSessionId);
      if (get().sessionId !== targetSessionId || get().sessionLoadRevision !== requestRevision) {
        return;
      }
      set({
        messages: msgs.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
        })),
      });
    } catch (error) {
      if (get().sessionId === targetSessionId && get().sessionLoadRevision === requestRevision) {
        set({ chatError: getParsedApiError(error) });
      }
    } finally {
      if (get().sessionId === targetSessionId && get().sessionLoadRevision === requestRevision) {
        set({ sessionsLoading: false });
      }
    }
  },

  stopStream: () => {
    // User-initiated stop of an in-flight generation. Aborting rejects the
    // reader with AbortError (handled silently), and the running startStream's
    // finally would reset state anyway; reset here too for immediate feedback.
    const { abortController } = get();
    if (!abortController) return;
    abortController.abort();
    set({
      loading: false,
      streamStatus: 'idle',
      progressSteps: [],
      abortController: null,
      failedStreamRequest: null,
    });
  },

  startNewChat: () => {
    // Abort any in-flight stream so the old request does not keep running
    get().abortController?.abort();
    const sessionLoadRevision = get().sessionLoadRevision + 1;
    const newId = generateUUID();
    set({
      sessionId: newId,
      messages: [],
      loading: false,
      streamStatus: 'idle',
      progressSteps: [],
      chatError: null,
      abortController: null,
      failedStreamRequest: null,
      sessionLoadRevision,
    });
    localStorage.setItem(STORAGE_KEY_SESSION, newId);
  },

  startStream: async (payload, meta) => {
    if (get().loading) return;
    const { abortController: prevAc, sessionId: storeSessionId } = get();
    prevAc?.abort();

    const ac = new AbortController();
    set({ abortController: ac });

    const streamSessionId = payload.session_id || storeSessionId;
    const skillNames = meta?.skillNames?.length
      ? meta.skillNames
      : [meta?.skillName ?? '通用'];
    const skillName = skillNames.join('、');

    const userMessage: Message = {
      id: generateUUID(),
      role: 'user',
      content: payload.message,
      skills: payload.skills,
      skill: payload.skills?.[0],
      skillNames,
      skillName,
    };

    set((s) => ({
      messages: [...s.messages, userMessage],
      loading: true,
      streamStatus: 'streaming',
      progressSteps: [],
      chatError: null,
      failedStreamRequest: null,
      sessions: s.sessions.some((x) => x.session_id === streamSessionId)
        ? s.sessions
        : [
            {
              session_id: streamSessionId,
              title: payload.message.slice(0, 60),
              message_count: 1,
              created_at: new Date().toISOString(),
              last_active: new Date().toISOString(),
            },
            ...s.sessions,
          ],
    }));

    try {
      const response = await agentApi.chatStream(payload, { signal: ac.signal });
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let finalContent: string | null = null;
      let receivedDoneEvent = false;
      const currentProgressSteps: ProgressStep[] = [];
      const processLine = (line: string) => {
        if (!line.startsWith('data: ')) return;

        const event = JSON.parse(line.slice(6)) as ProgressStep;
        if (event.type === 'done') {
          receivedDoneEvent = true;
          const doneEvent = event as unknown as StreamFailureEvent;
          if (doneEvent.success === false) {
            throw getStreamFailureError(doneEvent, '大模型调用出错，请检查 API Key 配置');
          }
          finalContent = doneEvent.content ?? '';
          return;
        }

        if (event.type === 'error') {
          throw getStreamFailureError(event as unknown as StreamFailureEvent, '分析出错');
        }

        currentProgressSteps.push(event);
        const current = get();
        if (current.sessionId === streamSessionId && current.abortController === ac && !ac.signal.aborted) {
          set((state) => ({ progressSteps: [...state.progressSteps, event] }));
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';

        for (const line of lines) {
          try {
            processLine(line);
          } catch (parseErr: unknown) {
            if (isParsedApiError(parseErr) || isApiRequestError(parseErr)) {
              throw parseErr;
            }
          }
        }
      }

      if (buf.trim().startsWith('data: ')) {
        try {
          processLine(buf.trim());
        } catch (parseErr: unknown) {
          if (isParsedApiError(parseErr) || isApiRequestError(parseErr)) {
            throw parseErr;
          }
        }
      }

      if (!receivedDoneEvent && !ac.signal.aborted) {
        throw createParsedApiError({
          title: '回复未完整返回',
          message: 'Agent 流式响应在完成前中断，请重试。',
          rawMessage: 'Agent stream ended before a done event was received.',
          category: 'upstream_network',
          code: 'agent_stream_failed',
        });
      }

      const { sessionId: currentSessionId, currentRoute } = get();
      const shouldAppend =
        currentSessionId === streamSessionId && !ac.signal.aborted;

      if (shouldAppend) {
        set((s) => ({
          messages: [
            ...s.messages,
            {
              id: (Date.now() + 1).toString(),
              role: 'assistant',
              content: finalContent || '（无内容）',
              skills: payload.skills,
              skill: payload.skills?.[0],
              skillNames,
              skillName,
              thinkingSteps: [...currentProgressSteps],
            },
          ],
          streamStatus: 'idle',
          failedStreamRequest: null,
        }));
      }

      if (currentRoute !== '/chat') {
        set({ completionBadge: true });
      }
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        // User-initiated abort: silent, no badge
      } else if (get().sessionId === streamSessionId && get().abortController === ac) {
        set({
          chatError: getParsedApiError(error),
          streamStatus: 'failed',
          failedStreamRequest: {
            payload: { ...payload, session_id: streamSessionId },
            meta,
            sessionId: streamSessionId,
            userMessageId: userMessage.id,
          },
        });
        const { currentRoute } = get();
        if (currentRoute !== '/chat') {
          set({ completionBadge: true });
        }
      }
    } finally {
      const { abortController: currentAc } = get();
      if (currentAc === ac) {
        set((state) => ({
          loading: false,
          streamStatus: state.streamStatus === 'failed' ? 'failed' : 'idle',
          progressSteps: [],
          abortController: null,
        }));
      }
      await get().loadSessions();
    }
  },

  retryLastFailedStream: async () => {
    const failed = get().failedStreamRequest;
    if (!failed || get().loading || get().sessionId !== failed.sessionId) return;
    set((state) => ({
      messages: state.messages.filter((message) => message.id !== failed.userMessageId),
      chatError: null,
      failedStreamRequest: null,
      streamStatus: 'idle',
    }));
    await get().startStream(failed.payload, failed.meta);
  },
}));
