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
  turn_id?: string;
  message_id?: string;
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
  turnId?: string;
}

function fromSessionMessage(message: ChatSessionMessage): Message {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    ...(message.error ? { error: message.error } : {}),
    ...(message.params ? { params: message.params } : {}),
    ...(message.turn_id ? { turnId: message.turn_id } : {}),
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

export type StreamTerminalState = 'completed' | 'failed' | 'aborted' | 'skipped';
export type TurnPersistenceState = 'persisted' | 'not_persisted' | 'unknown';

/** Per-call result kept private to one invocation and its stable turn identity. */
export type StreamOutcome = {
  terminal: StreamTerminalState;
  persistence: TurnPersistenceState;
  turnId: string;
};

async function reconcileTurnPersistence(
  sessionId: string,
  turnId: string,
  expectedContent: string,
): Promise<TurnPersistenceState> {
  try {
    const detail = await agentApi.getChatSessionMessages(sessionId);
    if (detail.turn_identity_supported !== true) {
      return 'unknown';
    }
    const matchingTurn = detail.messages.find((message) => message.turn_id === turnId);
    if (!matchingTurn) {
      return 'not_persisted';
    }
    return matchingTurn.role === 'user' && matchingTurn.content === expectedContent
      ? 'persisted'
      : 'unknown';
  } catch {
    return 'unknown';
  }
}

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
  selectedSkillIds: string[] | null;
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
  setSelectedSkillIds: (skillIds: string[]) => void;
  setCurrentRoute: (path: string) => void;
  clearCompletionBadge: () => void;
  loadSessions: () => Promise<void>;
  loadInitialSession: (preferredSessionId?: string) => Promise<void>;
  switchSession: (targetSessionId: string) => Promise<boolean>;
  startNewChat: () => string;
  startStream: (
    payload: ChatStreamRequest,
    meta?: StreamMeta,
    options?: StartStreamOptions,
  ) => Promise<StreamOutcome>;
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
  selectedSkillIds: null,
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

  setSelectedSkillIds: (skillIds) => set({ selectedSkillIds: skillIds }),

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
          set({ sessionId: newId, selectedSkillIds: null });
          writeSessionItem(CHAT_SESSION_STORAGE_KEY, newId);
        }
        return;
      }

      set({ sessionId: savedId });
      writeSessionItem(CHAT_SESSION_STORAGE_KEY, savedId);
      const detail = await agentApi.getChatSessionMessages(savedId);
      if (
        generation !== sessionHistoryGeneration
        || get().sessionId !== savedId
      ) {
        return;
      }
      set({
        messages: detail.messages.map(fromSessionMessage),
        selectedSkillIds: detail.session_state.selected_skill_ids,
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
      const detail = await agentApi.getChatSessionMessages(targetSessionId);
      if (generation !== sessionHistoryGeneration) {
        return false;
      }
      set({
        sessionId: targetSessionId,
        messages: detail.messages.map(fromSessionMessage),
        selectedSkillIds: detail.session_state.selected_skill_ids,
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
    // reader with AbortError (handled silently). Keep the mutex and controller
    // owned by startStream until its reconciliation and finally block settle.
    const { abortController } = get();
    if (!abortController) return;
    abortController.abort();
    set({ progressSteps: [] });
  },

  resetSessionState: () => {
    get().abortController?.abort();
    sessionHistoryGeneration += 1;
    sessionListGeneration += 1;
    removeSessionItem(CHAT_SESSION_STORAGE_KEY);
    set({
      messages: [],
      selectedSkillIds: null,
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
      selectedSkillIds: null,
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
    // Concurrent-send guard: a stream is already in flight.
    const turnId = payload.turn_id?.trim() || generateUUID();
    if (get().loading) {
      return { terminal: 'skipped', persistence: 'unknown', turnId };
    }
    const { abortController: prevAc, sessionId: storeSessionId } = get();
    prevAc?.abort();

    const ac = new AbortController();
    set({ abortController: ac });

    const streamSessionId = payload.session_id || storeSessionId;
    const identifiedPayload = { ...payload, turn_id: turnId };
    const skillNames = meta?.skillNames?.length
      ? meta.skillNames
      : [meta?.skillName ?? '通用'];
    const skillName = skillNames.join('、');

    const userMessage: Message = {
      id: turnId,
      role: 'user',
      content: payload.message,
      skills: payload.skills,
      skill: payload.skills?.[0],
      skillNames,
      skillName,
      turnId,
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

    // Outcome is local to this invocation so a superseded stream cannot pollute a newer one.
    let terminal: StreamTerminalState = 'completed';
    let turnAcknowledged = false;
    try {
      const response = await agentApi.chatStream(identifiedPayload, { signal: ac.signal });
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let finalContent: string | null = null;
      let receivedDoneEvent = false;
      const currentProgressSteps: ProgressStep[] = [];
      const processLine = (line: string) => {
        if (!line.startsWith('data: ')) return;

        const event = JSON.parse(line.slice(6)) as ProgressStep;
        if (event.type === 'turn_persisted' && event.turn_id === turnId) {
          turnAcknowledged = true;
          return;
        }
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

      // Clean close after user/session abort without an AbortError throw.
      if (ac.signal.aborted) {
        terminal = 'aborted';
      } else {
        terminal = 'completed';
      }

      const {
        sessionId: currentSessionId,
        currentRoute,
        abortController: currentController,
      } = get();
      const shouldAppend =
        currentSessionId === streamSessionId
        && currentController === ac
        && terminal === 'completed';

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

      if (shouldAppend && currentRoute !== APP_ROUTE_PATHS.agent) {
        set({ completionBadge: true });
      }
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        // User-initiated abort: silent, no badge, no retry entry.
        // lastFailedRequest stays null so retryLastStream remains inert after Stop.
        terminal = 'aborted';
      } else if (
        get().sessionId === streamSessionId
        && get().abortController === ac
      ) {
        set({
          chatError: getParsedApiError(error),
          lastFailedRequest: { payload: identifiedPayload, meta },
        });
        const { currentRoute } = get();
        if (currentRoute !== APP_ROUTE_PATHS.agent) {
          set({ completionBadge: true });
        }
        terminal = 'failed';
      } else {
        // Stale non-abort error after session/controller identity no longer matches
        // (superseded stream / switchSession). Not a backend acceptance of this turn.
        terminal = 'failed';
      }
    } finally {
      void get().loadSessions();
    }
    const persistence: TurnPersistenceState = turnAcknowledged
      ? 'persisted'
      : await reconcileTurnPersistence(
        streamSessionId,
        turnId,
        payload.message,
      );
    const invocationStillOwnsUi = (
      get().sessionId === streamSessionId
      && get().abortController === ac
    );
    if (persistence === 'not_persisted' && appendUserMessage && invocationStillOwnsUi) {
      set((state) => ({
        messages: state.messages.filter((message) => message.turnId !== turnId),
      }));
    }
    if (persistence === 'unknown' && invocationStillOwnsUi) {
      set((state) => ({
        lastFailedRequest: state.lastFailedRequest?.payload.turn_id === turnId
          ? null
          : state.lastFailedRequest,
      }));
    }
    const { abortController: currentAc } = get();
    if (currentAc === ac) {
      set({
        loading: false,
        progressSteps: [],
        abortController: null,
      });
    }
    return { terminal, persistence, turnId };
  },

  retryLastStream: async () => {
    const { lastFailedRequest, loading } = get();
    if (!lastFailedRequest || loading) {
      return;
    }
    const failedTurnId = lastFailedRequest.payload.turn_id;
    const turnStillVisible = Boolean(
      failedTurnId
      && get().messages.some((message) => message.turnId === failedTurnId),
    );
    // Ignore StreamOutcome: retry UX is driven by lastFailedRequest / chatError only.
    await get().startStream(
      lastFailedRequest.payload,
      lastFailedRequest.meta,
      { appendUserMessage: !turnStillVisible },
    );
  },
}));
