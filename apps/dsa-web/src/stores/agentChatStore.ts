import { create } from 'zustand';
import { agentApi } from '../api/agent';
import type { ChatSessionItem, ChatSessionMessage, ChatStreamRequest } from '../api/agent';
import {
  createParsedApiError,
  getParsedApiError,
  isApiRequestError,
  isParsedApiError,
  type ParsedApiError,
} from '../api/error';
import { generateUUID } from '../utils/uuid';
import {
  CHAT_SESSION_STORAGE_KEY,
  readSessionItemWithLegacyLocal,
  removeSessionItem,
  writeSessionItem,
} from '../utils/sessionPersistence';
import { APP_ROUTE_PATHS } from '../routing/routes';

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
  /** Stable server error code for a persisted failure message. */
  error?: string;
  params?: Record<string, unknown>;
}

function fromSessionMessage(message: ChatSessionMessage): Message {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    ...(message.error ? { error: message.error } : {}),
    ...(message.params ? { params: message.params } : {}),
  };
}

export interface StreamMeta {
  skillNames?: string[];
  skillName?: string;
}

type FailedStreamRequest = {
  payload: ChatStreamRequest;
  meta?: StreamMeta;
};

type StartStreamOptions = {
  appendUserMessage?: boolean;
};

type StreamFailureEvent = {
  type: string;
  success?: boolean;
  content?: string;
  error?: unknown;
  message?: unknown;
  params?: unknown;
  details?: unknown;
  trace_id?: unknown;
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
  if (
    typeof event.error === 'string'
    && /^[a-z][a-z0-9_]*$/.test(event.error.trim())
  ) {
    return getParsedApiError({
      error: event.error,
      message: typeof event.message === 'string' ? event.message : fallbackMessage,
      params: event.params,
      details: event.details,
      trace_id: event.trace_id,
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
  progressSteps: ProgressStep[];
  sessionId: string;
  sessions: ChatSessionItem[];
  sessionsLoading: boolean;
  sessionsError: ParsedApiError | null;
  sessionLoading: boolean;
  sessionError: ParsedApiError | null;
  chatError: ParsedApiError | null;
  currentRoute: string;
  completionBadge: boolean;
  hasInitialLoad: boolean;
  abortController: AbortController | null;
  lastFailedRequest: FailedStreamRequest | null;
}

interface AgentChatActions {
  setCurrentRoute: (path: string) => void;
  clearCompletionBadge: () => void;
  loadSessions: () => Promise<void>;
  loadInitialSession: (preferredSessionId?: string) => Promise<void>;
  switchSession: (targetSessionId: string) => Promise<boolean>;
  startNewChat: () => string;
  startStream: (payload: ChatStreamRequest, meta?: StreamMeta, options?: StartStreamOptions) => Promise<void>;
  retryLastStream: () => Promise<void>;
  stopStream: () => void;
  resetSessionState: () => void;
}

const getInitialSessionId = (): string =>
  readSessionItemWithLegacyLocal(CHAT_SESSION_STORAGE_KEY) || generateUUID();

let sessionHistoryGeneration = 0;
let sessionListGeneration = 0;

export const useAgentChatStore = create<AgentChatState & AgentChatActions>((set, get) => ({
  messages: [],
  loading: false,
  progressSteps: [],
  sessionId: getInitialSessionId(),
  sessions: [],
  sessionsLoading: false,
  sessionsError: null,
  sessionLoading: false,
  sessionError: null,
  chatError: null,
  currentRoute: '',
  completionBadge: false,
  hasInitialLoad: false,
  abortController: null,
  lastFailedRequest: null,

  setCurrentRoute: (path) => set({ currentRoute: path }),

  clearCompletionBadge: () => set({ completionBadge: false }),

  loadSessions: async () => {
    const generation = ++sessionListGeneration;
    set({ sessionsLoading: true, sessionsError: null });
    try {
      const sessions = await agentApi.getChatSessions();
      if (generation === sessionListGeneration) {
        set({ sessions });
      }
    } catch (error) {
      if (generation === sessionListGeneration) {
        set({ sessionsError: getParsedApiError(error) });
      }
    } finally {
      if (generation === sessionListGeneration) {
        set({ sessionsLoading: false });
      }
    }
  },

  loadInitialSession: async (preferredSessionId) => {
    const { hasInitialLoad } = get();
    if (hasInitialLoad) return;
    const preferred = preferredSessionId?.trim() || null;
    const persistedSessionId = readSessionItemWithLegacyLocal(CHAT_SESSION_STORAGE_KEY);
    const generation = ++sessionHistoryGeneration;
    if (preferred) {
      writeSessionItem(CHAT_SESSION_STORAGE_KEY, preferred);
    }
    set({
      hasInitialLoad: true,
      sessionsLoading: true,
      sessionsError: null,
      sessionError: null,
      ...(preferred ? { sessionId: preferred } : {}),
    });

    try {
      const sessionList = await agentApi.getChatSessions();
      if (generation !== sessionHistoryGeneration) {
        return;
      }
      set({ sessions: sessionList });

      const savedId = preferred || persistedSessionId;
      if (!savedId) {
        writeSessionItem(CHAT_SESSION_STORAGE_KEY, get().sessionId);
        return;
      }

      const sessionExists = sessionList.some((session) => session.session_id === savedId);
      if (!sessionExists && !preferred) {
        if (generation === sessionHistoryGeneration) {
          const newId = generateUUID();
          set({ sessionId: newId });
          writeSessionItem(CHAT_SESSION_STORAGE_KEY, newId);
        }
        return;
      }

      set({ sessionId: savedId });
      writeSessionItem(CHAT_SESSION_STORAGE_KEY, savedId);
      const msgs = await agentApi.getChatSessionMessages(savedId);
      if (
        generation !== sessionHistoryGeneration
        || get().sessionId !== savedId
      ) {
        return;
      }
      set({
        messages: msgs.map(fromSessionMessage),
      });
    } catch (error) {
      if (generation === sessionHistoryGeneration) {
        const parsedError = getParsedApiError(error);
        set({
          sessionsError: parsedError,
          ...(preferred ? { sessionError: parsedError } : {}),
        });
      }
    } finally {
      if (generation === sessionHistoryGeneration) {
        set({ sessionsLoading: false });
      }
    }
  },

  switchSession: async (targetSessionId) => {
    const { sessionId, messages, abortController } = get();
    if (targetSessionId === sessionId && messages.length > 0) return true;

    const generation = ++sessionHistoryGeneration;
    abortController?.abort();
    set({
      loading: false,
      sessionLoading: true,
      sessionError: null,
      progressSteps: [],
      chatError: null,
      abortController: null,
      lastFailedRequest: null,
    });

    try {
      const msgs = await agentApi.getChatSessionMessages(targetSessionId);
      if (generation !== sessionHistoryGeneration) {
        return false;
      }
      set({
        sessionId: targetSessionId,
        messages: msgs.map(fromSessionMessage),
        sessionError: null,
      });
      writeSessionItem(CHAT_SESSION_STORAGE_KEY, targetSessionId);
      return true;
    } catch (error) {
      if (generation === sessionHistoryGeneration) {
        set({ sessionError: getParsedApiError(error) });
      }
      return false;
    } finally {
      if (generation === sessionHistoryGeneration) {
        set({ sessionLoading: false });
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
    set({ loading: false, progressSteps: [], abortController: null });
  },

  resetSessionState: () => {
    get().abortController?.abort();
    sessionHistoryGeneration += 1;
    sessionListGeneration += 1;
    removeSessionItem(CHAT_SESSION_STORAGE_KEY);
    set({
      messages: [],
      loading: false,
      progressSteps: [],
      sessionId: generateUUID(),
      sessions: [],
      sessionsLoading: false,
      sessionsError: null,
      sessionLoading: false,
      sessionError: null,
      chatError: null,
      currentRoute: '',
      completionBadge: false,
      hasInitialLoad: false,
      abortController: null,
      lastFailedRequest: null,
    });
  },

  startNewChat: () => {
    // Abort any in-flight stream so the old request does not keep running
    get().abortController?.abort();
    sessionHistoryGeneration += 1;
    const newId = generateUUID();
    set({
      sessionId: newId,
      messages: [],
      loading: false,
      sessionsLoading: false,
      sessionLoading: false,
      sessionError: null,
      progressSteps: [],
      chatError: null,
      abortController: null,
      lastFailedRequest: null,
    });
    writeSessionItem(CHAT_SESSION_STORAGE_KEY, newId);
    return newId;
  },

  startStream: async (payload, meta, options) => {
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
      id: Date.now().toString(),
      role: 'user',
      content: payload.message,
      skills: payload.skills,
      skill: payload.skills?.[0],
      skillNames,
      skillName,
    };
    const appendUserMessage = options?.appendUserMessage !== false;

    set((s) => ({
      messages: appendUserMessage ? [...s.messages, userMessage] : s.messages,
      loading: true,
      progressSteps: [],
      chatError: null,
      lastFailedRequest: null,
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
        if (
          get().sessionId === streamSessionId
          && get().abortController === ac
          && !ac.signal.aborted
        ) {
          set((s) => ({ progressSteps: [...s.progressSteps, event] }));
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
        }));
      }

      if (currentRoute !== APP_ROUTE_PATHS.agent) {
        set({ completionBadge: true });
      }
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        // User-initiated abort: silent, no badge
      } else if (
        get().sessionId === streamSessionId
        && get().abortController === ac
      ) {
        set({
          chatError: getParsedApiError(error),
          lastFailedRequest: { payload, meta },
        });
        const { currentRoute } = get();
        if (currentRoute !== APP_ROUTE_PATHS.agent) {
          set({ completionBadge: true });
        }
      }
    } finally {
      const { abortController: currentAc } = get();
      if (currentAc === ac) {
        set({
          loading: false,
          progressSteps: [],
          abortController: null,
        });
      }
      await get().loadSessions();
    }
  },

  retryLastStream: async () => {
    const { lastFailedRequest, loading } = get();
    if (!lastFailedRequest || loading) {
      return;
    }
    await get().startStream(
      lastFailedRequest.payload,
      lastFailedRequest.meta,
      { appendUserMessage: false },
    );
  },
}));
