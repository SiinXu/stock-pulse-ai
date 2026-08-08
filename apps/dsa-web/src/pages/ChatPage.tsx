import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { History } from 'lucide-react';
import { agentApi } from '../api/agent';
import { systemConfigApi } from '../api/systemConfig';
import { Button, ConfirmDialog, Drawer, IconButton, InlineAlert, SegmentedControl, Surface, Tooltip, useClipboard } from '../components/common';
import { DeepResearchPanel } from '../components/chat/DeepResearchPanel';
import { ChatMessageList } from '../components/chat/ChatMessageList';
import { ChatSessionSidebar } from '../components/chat/ChatSessionSidebar';
import { ChatComposer } from '../components/chat/ChatComposer';
import {
  resolveActiveStockContextFromMessage,
  restoreActiveStockContextFromMessages,
  type ActiveStockContext,
} from '../components/chat/chatActiveStock';
import { getMessageSkillLabel } from '../components/chat/chatMessageMeta';
import { useChatPageUiState } from '../components/chat/useChatPageUiState';
import { useAgentSetupAvailability } from '../hooks/useAgentSetupAvailability';
import { getParsedApiError } from '../api/error';
import type { SkillInfo } from '../api/agent';
import {
  useAgentChatStore,
  type Message,
} from '../stores/agentChatStore';
import { downloadSession, formatSessionAsMarkdown } from '../utils/chatExport';
import type { ChatFollowUpContext } from '../utils/chatFollowUp';
import {
  buildFollowUpPrompt,
  parseFollowUpRecordId,
  resolveChatFollowUpContext,
  sanitizeFollowUpStockCode,
  sanitizeFollowUpStockName,
} from '../utils/chatFollowUp';
import { isNearBottom } from '../utils/chatScroll';
import { getReportText } from '../utils/reportLanguage';
import { findMatchingStockCode, includesStockCode } from '../utils/stockCode';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import type { UiTextKey } from '../i18n/uiText';
import { getUiListSeparator } from '../utils/uiLocale';
import { getStrategyDisplay } from '../utils/strategyDisplay';
import { getChatMessageDisplayContent } from '../utils/chatMessage';
import { REPORT_ROUTE_QUERY_KEYS } from '../routing/routes';
// Quick question examples shown on empty state
const QUICK_QUESTION_DEFINITIONS: Array<{ labelKey: UiTextKey; skill: string }> = [
  { labelKey: 'chat.quick.chan', skill: 'chan_theory' },
  { labelKey: 'chat.quick.wave', skill: 'wave_theory' },
  { labelKey: 'chat.quick.trend', skill: 'bull_trend' },
  { labelKey: 'chat.quick.box', skill: 'box_oscillation' },
  { labelKey: 'chat.quick.tencent', skill: 'bull_trend' },
  { labelKey: 'chat.quick.emotion', skill: 'emotion_cycle' },
];
const MAX_SELECTED_SKILLS = 3;
const CONTEXT_COMPRESSION_CONFIG_KEY = 'AGENT_CONTEXT_COMPRESSION_ENABLED';
const CHAT_SESSION_QUERY_KEY = 'session';
const CHAT_CONTEXT_STATE_QUERY_KEY = 'context';
const CHAT_ACTIVE_CONTEXT_STATE = 'active';
const CHAT_DESKTOP_RAIL_QUERY = '(min-width: 1280px)';
const ChatPage: React.FC = () => {
  const { language, t } = useUiLanguage();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialUrlSessionIdRef = useRef(
    searchParams.get(CHAT_SESSION_QUERY_KEY)?.trim() || undefined,
  );
  const [input, setInput] = useState('');
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [isSkillsLoading, setIsSkillsLoading] = useState(true);
  const [defaultSkillIds, setDefaultSkillIds] = useState<string[]>([]);
  const [uiState, dispatchUi] = useChatPageUiState();
  const {
    showSkillDesc,
    mobileSkillPickerOpen,
    sessionSearch,
    expandedThinking,
    deleteConfirmId,
    deleteLoading,
    deleteError,
    sidebarOpen,
    sending,
    chatMode,
    showJumpToBottom,
  } = uiState;
  const setShowSkillDesc = useCallback(
    (skillId: string | null) => dispatchUi({ type: 'setShowSkillDesc', skillId }),
    [dispatchUi],
  );
  const setMobileSkillPickerOpen = useCallback(
    (open: boolean) => dispatchUi({ type: 'setMobileSkillPickerOpen', open }),
    [dispatchUi],
  );
  const setSessionSearch = useCallback(
    (value: string) => dispatchUi({ type: 'setSessionSearch', value }),
    [dispatchUi],
  );
  const setDeleteConfirmId = useCallback(
    (sessionId: string | null) => dispatchUi({ type: 'setDeleteConfirmId', sessionId }),
    [dispatchUi],
  );
  const setDeleteLoading = useCallback(
    (loading: boolean) => dispatchUi({ type: 'setDeleteLoading', loading }),
    [dispatchUi],
  );
  const setDeleteError = useCallback(
    (error: string | null) => dispatchUi({ type: 'setDeleteError', error }),
    [dispatchUi],
  );
  const setSending = useCallback(
    (next: boolean) => dispatchUi({ type: 'setSending', sending: next }),
    [dispatchUi],
  );
  const setChatMode = useCallback(
    (mode: 'chat' | 'research') => dispatchUi({ type: 'setChatMode', mode }),
    [dispatchUi],
  );
  const setShowJumpToBottom = useCallback(
    (show: boolean) => dispatchUi({ type: 'setShowJumpToBottom', show }),
    [dispatchUi],
  );
  const sidebarOpenRef = useRef(false);
  const desktopSessionRailRef = useRef<HTMLDivElement>(null);
  const setSidebarPresentationOpen = useCallback((open: boolean) => {
    sidebarOpenRef.current = open;
    dispatchUi({ type: 'setSidebarOpen', open });
  }, [dispatchUi]);
  const closeSidebar = useCallback(() => setSidebarPresentationOpen(false), [setSidebarPresentationOpen]);
  const [isFollowUpContextLoading, setIsFollowUpContextLoading] = useState(false);
  const [sendToast, setSendToast] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);
  const [contextCompressionEnabled, setContextCompressionEnabled] = useState(false);
  const [contextCompressionLoaded, setContextCompressionLoaded] = useState(false);
  const [contextCompressionSaving, setContextCompressionSaving] = useState(false);
  const [contextCompressionConfigVersion, setContextCompressionConfigVersion] = useState('');
  const [contextCompressionMaskToken, setContextCompressionMaskToken] = useState('******');
  const [contextCompressionError, setContextCompressionError] = useState<string | null>(null);
  const agentUnavailable = useAgentSetupAvailability();
  const [copiedMessages, setCopiedMessages] = useState<Set<string>>(new Set());
  const { copyText } = useClipboard();
  const [watchlistCodes, setWatchlistCodes] = useState<string[]>([]);
  const [isWatchlistActioning, setIsWatchlistActioning] = useState(false);
  const [watchlistMessage, setWatchlistMessage] = useState<string | null>(null);
  const [activeStockCode, setActiveStockCode] = useState<string | null>(null);
  const [activeStockContext, setActiveStockContext] = useState<ActiveStockContext | null>(null);
  const activeStockContextRef = useRef<ActiveStockContext | null>(null);
  const watchlistMessageTimerRef = useRef<number | null>(null);
  const copyResetTimerRef = useRef<Partial<Record<string, number>>>({});
  const messagesViewportRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isMountedRef = useRef(true);
  const sendToastTimerRef = useRef<number | null>(null);
  const followUpHydrationTokenRef = useRef(0);
  const lastHydratedFollowUpKeyRef = useRef<string | null>(null);
  const followUpContextRef = useRef<ChatFollowUpContext | null>(null);
  const shouldStickToBottomRef = useRef(true);
  const pendingScrollBehaviorRef = useRef<ScrollBehavior>('auto');
  const skillPickerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!mobileSkillPickerOpen) {
      return undefined;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (skillPickerRef.current && !skillPickerRef.current.contains(event.target as Node)) {
        setMobileSkillPickerOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [mobileSkillPickerOpen, setMobileSkillPickerOpen]);
  const text = getReportText(language);
  // Cleanup timers on unmount
  useEffect(() => {
    const timers = copyResetTimerRef.current;
    return () => {
      if (sendToastTimerRef.current !== null) {
        window.clearTimeout(sendToastTimerRef.current);
      }
      Object.values(timers).forEach((timerId) => {
        if (timerId !== undefined) {
          window.clearTimeout(timerId);
        }
      });
    };
  }, []);
  // Set page title
  useEffect(() => {
    document.title = t('chat.pageTitle');
  }, [t]);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') {
      return undefined;
    }
    const mediaQuery = window.matchMedia(CHAT_DESKTOP_RAIL_QUERY);
    let focusFrame: number | undefined;
    const handleRailPresentationChange = (event: MediaQueryListEvent) => {
      if (!event.matches || !sidebarOpenRef.current) {
        return;
      }
      setSidebarPresentationOpen(false);
      focusFrame = window.requestAnimationFrame(() => {
        const rail = desktopSessionRailRef.current;
        const activeSession = rail?.querySelector<HTMLElement>('[aria-current="page"]');
        (activeSession ?? rail)?.focus();
      });
    };
    mediaQuery.addEventListener('change', handleRailPresentationChange);
    return () => {
      mediaQuery.removeEventListener('change', handleRailPresentationChange);
      if (focusFrame !== undefined) {
        window.cancelAnimationFrame(focusFrame);
      }
    };
  }, [setSidebarPresentationOpen]);
  const loadWatchlist = useCallback(async () => {
    try {
      const codes = await systemConfigApi.getWatchlist();
      if (isMountedRef.current) {
        setWatchlistCodes(codes);
      }
    } catch {
      // ignore error silently
    }
  }, []);
  useEffect(() => {
    void loadWatchlist();
  }, [loadWatchlist]);
  const stockInWatchlist = useCallback(
    (stockCode: string) => includesStockCode(watchlistCodes, stockCode),
    [watchlistCodes],
  );
  const handleToggleWatchlist = useCallback(
    async (stockCode: string) => {
      if (!stockCode || isWatchlistActioning) return;
      setIsWatchlistActioning(true);
      setWatchlistMessage(null);
      try {
        const existingStockCode = findMatchingStockCode(watchlistCodes, stockCode);
        if (existingStockCode) {
          const codes = await systemConfigApi.removeFromWatchlist(existingStockCode);
          if (isMountedRef.current) {
            setWatchlistCodes(codes);
            setWatchlistMessage(t('chat.watchlistRemoved', { stock: stockCode }));
          }
        } else {
          const codes = await systemConfigApi.addToWatchlist(stockCode);
          if (isMountedRef.current) {
            setWatchlistCodes(codes);
            setWatchlistMessage(t('chat.watchlistAdded', { stock: stockCode }));
          }
        }
      } catch {
        if (isMountedRef.current) {
          setWatchlistMessage(t('chat.actionFailed'));
        }
      } finally {
        if (isMountedRef.current) {
          setIsWatchlistActioning(false);
          if (watchlistMessageTimerRef.current !== null) {
            window.clearTimeout(watchlistMessageTimerRef.current);
          }
          watchlistMessageTimerRef.current = window.setTimeout(() => {
            if (isMountedRef.current) {
              setWatchlistMessage(null);
            }
          }, 3000);
        }
      }
    },
    [isWatchlistActioning, t, watchlistCodes],
  );
  const {
    messages,
    selectedSkillIds: sessionSelectedSkillIds,
    loading,
    progressSteps,
    sessionId,
    sessions,
    sessionsLoading,
    sessionsError,
    sessionLoading,
    sessionError,
    hasInitialLoad,
    chatError,
    lastFailedRequest,
    setSelectedSkillIds,
    loadSessions,
    loadInitialSession,
    switchSession,
    startStream,
    retryLastStream,
    stopStream,
    clearCompletionBadge,
  } = useAgentChatStore();
  const selectedSkillIds = sessionSelectedSkillIds ?? defaultSkillIds;
  const setSessionInUrl = useCallback((targetSessionId: string, clearFollowUpContext = false) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set(CHAT_SESSION_QUERY_KEY, targetSessionId);
      if (clearFollowUpContext) {
        next.delete('stock');
        next.delete('name');
        next.delete(REPORT_ROUTE_QUERY_KEYS.recordId);
        next.delete(CHAT_CONTEXT_STATE_QUERY_KEY);
      }
      return next;
    }, { replace: true });
  }, [setSearchParams]);
  const persistActiveContextInUrl = useCallback((context: ActiveStockContext | null) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (!next.get(CHAT_SESSION_QUERY_KEY)) {
        next.set(CHAT_SESSION_QUERY_KEY, sessionId);
      }
      if (!context) {
        next.delete('stock');
        next.delete('name');
        next.delete(REPORT_ROUTE_QUERY_KEYS.recordId);
        next.delete(CHAT_CONTEXT_STATE_QUERY_KEY);
        return next;
      }

      const previousStock = sanitizeFollowUpStockCode(next.get('stock'));
      next.set('stock', context.stock_code);
      if (context.stock_name) next.set('name', context.stock_name);
      else next.delete('name');
      if (previousStock !== context.stock_code) {
        next.delete(REPORT_ROUTE_QUERY_KEYS.recordId);
      }
      next.set(CHAT_CONTEXT_STATE_QUERY_KEY, CHAT_ACTIVE_CONTEXT_STATE);
      return next;
    }, { replace: true });
  }, [sessionId, setSearchParams]);
  useEffect(() => {
    if (!hasInitialLoad) {
      return;
    }
    const urlSessionId = searchParams.get(CHAT_SESSION_QUERY_KEY)?.trim();
    if (!urlSessionId) {
      setSessionInUrl(sessionId);
      return;
    }
    if (urlSessionId !== sessionId) {
      void switchSession(urlSessionId);
    }
  }, [hasInitialLoad, searchParams, sessionId, setSessionInUrl, switchSession]);
  useEffect(() => {
    if (
      activeStockContext
      || messages.length === 0
      || sanitizeFollowUpStockCode(searchParams.get('stock'))
    ) {
      return;
    }
    const restoredContext = restoreActiveStockContextFromMessages(messages);
    if (!restoredContext) {
      return;
    }
    setActiveStockContext(restoredContext);
    activeStockContextRef.current = restoredContext;
    setActiveStockCode(restoredContext.stock_code);
    persistActiveContextInUrl(restoredContext);
  }, [activeStockContext, messages, persistActiveContextInUrl, searchParams, sessionId]);
  const syncScrollState = useCallback(() => {
    const viewport = messagesViewportRef.current;
    if (!viewport) return;
    const nearBottom = isNearBottom({
      scrollTop: viewport.scrollTop,
      clientHeight: viewport.clientHeight,
      scrollHeight: viewport.scrollHeight,
    });
    shouldStickToBottomRef.current = nearBottom;
    if (nearBottom) {
      setShowJumpToBottom(false);
    }
  }, [setShowJumpToBottom]);
  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, []);
  const requestScrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    shouldStickToBottomRef.current = true;
    pendingScrollBehaviorRef.current = behavior;
    setShowJumpToBottom(false);
  }, [setShowJumpToBottom]);
  const handleMessagesScroll = useCallback(() => {
    syncScrollState();
  }, [syncScrollState]);
  useEffect(() => {
    syncScrollState();
  }, [syncScrollState, sessionId]);
  useEffect(() => {
    const behavior = pendingScrollBehaviorRef.current;
    const shouldAutoScroll = shouldStickToBottomRef.current;
    if (!shouldAutoScroll) {
      if (messages.length > 0 || progressSteps.length > 0 || loading) {
        setShowJumpToBottom(true);
      }
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      scrollToBottom(behavior);
      pendingScrollBehaviorRef.current = loading ? 'auto' : 'smooth';
    });

    return () => window.cancelAnimationFrame(frame);
  }, [messages, progressSteps, loading, sessionId, scrollToBottom, setShowJumpToBottom]);
  useEffect(() => {
    if (!loading) {
      pendingScrollBehaviorRef.current = 'smooth';
    }
  }, [loading]);
  useEffect(() => {
    clearCompletionBadge();
  }, [clearCompletionBadge]);
  useEffect(() => {
    void loadInitialSession(initialUrlSessionIdRef.current);
  }, [loadInitialSession]);
  useEffect(() => {
    let active = true;

    void agentApi.getSkills()
      .then((res) => {
        if (!active) {
          return;
        }
        setSkills(res.skills);
        const defaultId =
          res.default_skill_id ||
          res.skills[0]?.id ||
          '';
        setDefaultSkillIds(defaultId ? [defaultId] : []);
      })
      .catch((error) => {
        if (active) {
          console.error('Failed to load chat skills:', error);
        }
      })
      .finally(() => {
        if (active) {
          setIsSkillsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;

    void systemConfigApi.getConfig(false)
      .then((config) => {
        if (!active) {
          return;
        }
        const enabledItem = config.items.find((item) => item.key === CONTEXT_COMPRESSION_CONFIG_KEY);
        setContextCompressionEnabled(String(enabledItem?.value ?? '').trim().toLowerCase() === 'true');
        setContextCompressionConfigVersion(config.configVersion);
        setContextCompressionMaskToken(config.maskToken || '******');
        setContextCompressionLoaded(true);
        setContextCompressionError(null);
      })
      .catch((error) => {
        if (!active) {
          return;
        }
        const parsed = getParsedApiError(error);
        setContextCompressionLoaded(false);
        setContextCompressionError(parsed.message || t('chat.contextCompressionLoadFailed'));
        console.error('Failed to load context compression setting:', error);
      });

    return () => {
      active = false;
    };
  }, [t]);
  const updateContextCompressionEnabled = useCallback(
    async (nextEnabled: boolean) => {
      if (!contextCompressionLoaded || contextCompressionSaving) {
        return;
      }

      const previousEnabled = contextCompressionEnabled;
      setContextCompressionEnabled(nextEnabled);
      setContextCompressionSaving(true);
      setContextCompressionError(null);

      try {
        const result = await systemConfigApi.update({
          configVersion: contextCompressionConfigVersion,
          maskToken: contextCompressionMaskToken,
          reloadNow: true,
          items: [
            {
              key: CONTEXT_COMPRESSION_CONFIG_KEY,
              value: nextEnabled ? 'true' : 'false',
            },
          ],
        });
        setContextCompressionConfigVersion(result.configVersion || contextCompressionConfigVersion);
      } catch (error) {
        const parsed = getParsedApiError(error);
        setContextCompressionEnabled(previousEnabled);
        setContextCompressionError(parsed.message || t('chat.contextCompressionSaveFailed'));
      } finally {
        setContextCompressionSaving(false);
      }
    },
    [
      contextCompressionConfigVersion,
      contextCompressionEnabled,
      contextCompressionLoaded,
      contextCompressionMaskToken,
      contextCompressionSaving,
      t,
    ],
  );
  const availableSkillIds = new Set(skills.map((skill) => skill.id));
  const quickQuestions = QUICK_QUESTION_DEFINITIONS
    .filter((question) => availableSkillIds.size === 0 || availableSkillIds.has(question.skill))
    .map((question) => ({ label: t(question.labelKey), skill: question.skill }));
  const selectedSkillIdSet = new Set(selectedSkillIds);
  const skillLimitReached = selectedSkillIds.length >= MAX_SELECTED_SKILLS;
  const getSkillNames = useCallback(
    (skillIds: string[]) => skillIds.map((id) => {
      const skill = skills.find((item) => item.id === id);
      return skill ? getStrategyDisplay(skill, language).name : id;
    }),
    [language, skills],
  );
  const normalizeSelectedSkillIds = useCallback((skillIds: string[]) => {
    const normalized: string[] = [];
    for (const skillId of skillIds) {
      const cleaned = skillId.trim();
      if (cleaned && !normalized.includes(cleaned)) {
        normalized.push(cleaned);
      }
    }
    return normalized.slice(0, MAX_SELECTED_SKILLS);
  }, []);
  const toggleSkillSelection = useCallback((skillId: string) => {
    if (selectedSkillIds.includes(skillId)) {
      setSelectedSkillIds(selectedSkillIds.filter((id) => id !== skillId));
      return;
    }
    if (selectedSkillIds.length < MAX_SELECTED_SKILLS) {
      setSelectedSkillIds([...selectedSkillIds, skillId]);
    }
  }, [selectedSkillIds, setSelectedSkillIds]);
  const handleStartNewChat = useCallback(() => {
    followUpContextRef.current = null;
    activeStockContextRef.current = null;
    setActiveStockContext(null);
    setActiveStockCode(null);
    requestScrollToBottom('auto');
    const newSessionId = useAgentChatStore.getState().startNewChat();
    setSessionInUrl(newSessionId, true);
    setSidebarPresentationOpen(false);
  }, [requestScrollToBottom, setSessionInUrl, setSidebarPresentationOpen]);
  const handleSwitchSession = useCallback(async (targetSessionId: string) => {
    if (targetSessionId === sessionId) {
      setSidebarPresentationOpen(false);
      return;
    }
    const switched = await switchSession(targetSessionId);
    if (switched !== false) {
      followUpContextRef.current = null;
      activeStockContextRef.current = null;
      setActiveStockContext(null);
      setActiveStockCode(null);
      requestScrollToBottom('auto');
      setSessionInUrl(targetSessionId, true);
      setSidebarPresentationOpen(false);
    }
  }, [requestScrollToBottom, sessionId, setSessionInUrl, setSidebarPresentationOpen, switchSession]);
  const confirmDelete = useCallback(async () => {
    if (!deleteConfirmId || deleteLoading) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await agentApi.deleteChatSession(deleteConfirmId);
      await loadSessions();
      if (deleteConfirmId === sessionId) {
        handleStartNewChat();
      }
      setDeleteConfirmId(null);
    } catch (error) {
      setDeleteError(getParsedApiError(error, language).message);
    } finally {
      setDeleteLoading(false);
    }
  }, [deleteConfirmId, deleteLoading, handleStartNewChat, language, loadSessions, sessionId, setDeleteConfirmId, setDeleteError, setDeleteLoading]);
  // Handle report-page follow-up URLs such as `?stock=600519&name=贵州茅台&recordId=xxx`.
  useEffect(() => {
    const stock = sanitizeFollowUpStockCode(searchParams.get('stock'));
    const name = sanitizeFollowUpStockName(searchParams.get('name'));
    const recordId = parseFollowUpRecordId(searchParams.get(REPORT_ROUTE_QUERY_KEYS.recordId));
    const contextIsActive = searchParams.get(CHAT_CONTEXT_STATE_QUERY_KEY) === CHAT_ACTIVE_CONTEXT_STATE;
    if (!stock) {
      lastHydratedFollowUpKeyRef.current = null;
      return;
    }

    const targetSessionId = searchParams.get(CHAT_SESSION_QUERY_KEY)?.trim() || sessionId;
    const followUpKey = `${targetSessionId}:${stock}:${name ?? ''}:${recordId ?? ''}`;
    if (lastHydratedFollowUpKeyRef.current === followUpKey) {
      return;
    }
    lastHydratedFollowUpKeyRef.current = followUpKey;
    const hydrationToken = ++followUpHydrationTokenRef.current;
    setActiveStockCode(stock);
    const stockContext = {
      stock_code: stock,
      stock_name: name,
    };
    activeStockContextRef.current = stockContext;
    setActiveStockContext(stockContext);
    if (contextIsActive) {
      followUpContextRef.current = stockContext;
      setIsFollowUpContextLoading(false);
      return;
    }

    setInput(buildFollowUpPrompt(stock, name));
    followUpContextRef.current = {
      stock_code: stock,
      stock_name: name,
    };
    if (recordId !== undefined) {
      setIsFollowUpContextLoading(true);
    }
    void resolveChatFollowUpContext({
      stockCode: stock,
      stockName: name,
      recordId,
    }).then((context) => {
      if (!isMountedRef.current || followUpHydrationTokenRef.current !== hydrationToken) {
        return;
      }
      followUpContextRef.current = context;
    }).finally(() => {
      if (isMountedRef.current && followUpHydrationTokenRef.current === hydrationToken) {
        setIsFollowUpContextLoading(false);
      }
    });
  }, [searchParams, sessionId]);
  const handleSend = useCallback(
    async (overrideMessage?: string, overrideSkillIds?: string[]) => {
      const msgText = (overrideMessage ?? input).trim();
      if (!msgText || loading || sessionLoading || isFollowUpContextLoading || isSkillsLoading) return;
      const requestedSkillIds = overrideSkillIds ?? sessionSelectedSkillIds;
      const usedSkillIds = normalizeSelectedSkillIds(
        requestedSkillIds ?? selectedSkillIds,
      );
      const usedSkillNames = usedSkillIds.length > 0 ? getSkillNames(usedSkillIds) : [t('chat.general')];

      let nextActiveStockContext = activeStockContextRef.current;
      let useActiveContextForThisSend = false;
      const stockResolution = resolveActiveStockContextFromMessage(msgText, activeStockContextRef.current);
      if (stockResolution) {
        nextActiveStockContext = stockResolution.context;
        useActiveContextForThisSend = stockResolution.useForCurrentSend;
        activeStockContextRef.current = nextActiveStockContext;
        setActiveStockContext(nextActiveStockContext);
        setActiveStockCode(nextActiveStockContext.stock_code);
      }
      const contextForSend = useActiveContextForThisSend
        ? nextActiveStockContext
        : followUpContextRef.current ?? nextActiveStockContext ?? undefined;
      const payload = {
        message: msgText,
        session_id: sessionId,
        ...(requestedSkillIds !== null
          ? { skills: normalizeSelectedSkillIds(requestedSkillIds) }
          : {}),
        context: contextForSend ?? undefined,
      };
      // Keep stock/name/recordId query params unsent until the stream succeeds so a
      // mid-flight refresh can restore the report→chat draft. Only mark context=active
      // after the backend accepted the turn (startStream outcome === 'completed').
      // Abort/failed/skipped must not stamp context=active or drop the unsent draft.
      const pendingFollowUpContext = followUpContextRef.current;
      const unsentFollowUpParamsPresent = Boolean(
        sanitizeFollowUpStockCode(searchParams.get('stock'))
        && searchParams.get(CHAT_CONTEXT_STATE_QUERY_KEY) !== CHAT_ACTIVE_CONTEXT_STATE,
      );
      followUpHydrationTokenRef.current += 1;
      followUpContextRef.current = null;
      setIsFollowUpContextLoading(false);

      setInput('');
      setMobileSkillPickerOpen(false);
      requestScrollToBottom('smooth');
      const streamOutcome = await startStream(payload, {
        skillNames: usedSkillNames,
        skillName: usedSkillNames.join(getUiListSeparator(language)),
      });

      if (streamOutcome === 'completed') {
        persistActiveContextInUrl(nextActiveStockContext);
        return;
      }

      // Stream failed or was aborted/skipped: restore draft + pending context so refresh can retry.
      followUpContextRef.current = pendingFollowUpContext ?? contextForSend ?? null;
      if (unsentFollowUpParamsPresent || pendingFollowUpContext) {
        setInput(msgText);
      }
    },
    [getSkillNames, input, isFollowUpContextLoading, isSkillsLoading, language, loading, normalizeSelectedSkillIds, persistActiveContextInUrl, requestScrollToBottom, searchParams, selectedSkillIds, sessionId, sessionSelectedSkillIds, sessionLoading, setMobileSkillPickerOpen, startStream, t],
  );
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Ignore the Enter that confirms an IME candidate so CJK input isn't sent
    // mid-composition (isComposing is true, or legacy keyCode 229).
    if (e.nativeEvent.isComposing || e.keyCode === 229) {
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };
  const handleQuickQuestion = (q: (typeof quickQuestions)[0]) => {
    const quickSkillIds = availableSkillIds.has(q.skill) ? [q.skill] : [];
    setSelectedSkillIds(quickSkillIds);
    handleSend(q.label, quickSkillIds);
  };
  const showSendFeedback = useCallback((nextToast: { type: 'success' | 'error'; message: string }, durationMs: number) => {
    if (sendToastTimerRef.current !== null) {
      window.clearTimeout(sendToastTimerRef.current);
    }
    setSendToast(nextToast);
    sendToastTimerRef.current = window.setTimeout(() => {
      setSendToast(null);
      sendToastTimerRef.current = null;
    }, durationMs);
  }, []);
  const toggleThinking = (msgId: string) => {
    dispatchUi({ type: 'toggleThinking', messageId: msgId });
  };
  const copyMessageToClipboard = async (msgId: string, content: string) => {
    if (await copyText(content)) {
      setCopiedMessages((prev) => new Set(prev).add(msgId));
      const existingTimer = copyResetTimerRef.current[msgId];
      if (existingTimer !== undefined) {
        window.clearTimeout(existingTimer);
      }
      copyResetTimerRef.current[msgId] = window.setTimeout(() => {
        setCopiedMessages((prev) => {
          const next = new Set(prev);
          next.delete(msgId);
          return next;
        });
        delete copyResetTimerRef.current[msgId];
      }, 2000);
    } else {
      showSendFeedback({ type: 'error', message: t('common.copyFailed') }, 5000);
    }
  };
  const downloadMessageAsMarkdown = useCallback((msg: Message) => {
    const skillLabel = getMessageSkillLabel(msg);
    const heading = msg.role === 'user'
      ? `# ${t('chat.userMessageHeading')}`
      : `# ${t('chat.aiReplyHeading')}${skillLabel ? ` · ${skillLabel}` : ''}`;
    const content = [heading, '', getChatMessageDisplayContent(msg, language)].join('\n');
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${msg.role === 'user' ? 'user' : 'assistant'}-message-${msg.id}.md`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }, [language, t]);
  const filteredSessions = useMemo(
    () => sessions.filter((session) => session.title.toLocaleLowerCase().includes(sessionSearch.trim().toLocaleLowerCase())),
    [sessions, sessionSearch],
  );
  const selectedSkillSummary = selectedSkillIds.length > 0
    ? getSkillNames(selectedSkillIds).join(getUiListSeparator(language))
    : t('chat.generalAnalysis');

  return (
    <div
      data-testid="chat-workspace"
      className="flex h-[calc(100dvh-5rem)] w-full min-w-0 gap-4 overflow-hidden p-3 sm:h-[calc(100dvh-5.5rem)] lg:h-[calc(100dvh-2rem)]"
    >
      {/* Desktop sidebar */}
      <div
        ref={desktopSessionRailRef}
        tabIndex={-1}
        className="hidden h-full w-64 flex-shrink-0 flex-col overflow-hidden xl:flex"
        data-testid="chat-session-rail"
      >
        <ChatSessionSidebar
          language={language}
          t={t}
          sessionSearch={sessionSearch}
          onSessionSearchChange={setSessionSearch}
          sessions={sessions}
          filteredSessions={filteredSessions}
          sessionsLoading={sessionsLoading}
          sessionsError={sessionsError}
          sessionLoading={sessionLoading}
          sessionId={sessionId}
          onNewChat={handleStartNewChat}
          onRetryLoadSessions={() => void loadSessions()}
          onSwitchSession={(id) => void handleSwitchSession(id)}
          onRequestDelete={(id) => {
            setDeleteConfirmId(id);
            setDeleteError(null);
          }}
        />
      </div>

      {/* Mobile sidebar overlay */}
      <Drawer
        isOpen={sidebarOpen}
        onClose={closeSidebar}
        title={t('chat.history')}
        variant="navigation"
      >
        <ChatSessionSidebar
          language={language}
          t={t}
          sessionSearch={sessionSearch}
          onSessionSearchChange={setSessionSearch}
          sessions={sessions}
          filteredSessions={filteredSessions}
          sessionsLoading={sessionsLoading}
          sessionsError={sessionsError}
          sessionLoading={sessionLoading}
          sessionId={sessionId}
          onNewChat={handleStartNewChat}
          onRetryLoadSessions={() => void loadSessions()}
          onSwitchSession={(id) => void handleSwitchSession(id)}
          onRequestDelete={(id) => {
            setDeleteConfirmId(id);
            setDeleteError(null);
          }}
        />
      </Drawer>

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        isOpen={Boolean(deleteConfirmId)}
        title={t('chat.deleteTitle')}
        message={t('chat.deleteMessage')}
        confirmText={t('common.delete')}
        cancelText={t('common.cancel')}
        isDanger
        confirmDisabled={deleteLoading}
        cancelDisabled={deleteLoading}
        error={deleteError}
        onConfirm={() => void confirmDelete()}
        onCancel={() => {
          setDeleteConfirmId(null);
          setDeleteError(null);
        }}
      />

      {/* Main chat area */}
      <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <header className="mb-4 flex-shrink-0 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
              <IconButton
                onClick={() => setSidebarPresentationOpen(true)}
                size="navigation"
                tooltip={false}
                className="-ml-1 xl:hidden"
                aria-label={t('chat.history')}
                data-testid="chat-session-trigger"
              >
                <History aria-hidden="true" />
              </IconButton>
              <svg
                className="w-6 h-6 text-primary"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                />
              </svg>
              {t('chat.title')}
            </h1>
            {messages.length > 0 && (
              <div className="flex flex-shrink-0 flex-wrap items-center justify-end gap-2">
                <Tooltip content={t('chat.exportSession')}>
                  <span className="inline-flex">
                    <Button
                      variant="secondary"
                      size="default"
                      onClick={() => downloadSession(messages, language)}
                      aria-label={t('chat.exportSession')}
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      {t('chat.exportSessionButton')}
                    </Button>
                  </span>
                </Tooltip>
                <Tooltip content={t('chat.notify')}>
                  <span className="inline-flex">
                    <Button
                      variant="secondary"
                      size="default"
                      disabled={sending}
                      onClick={async () => {
                        if (sending) return;
                        setSending(true);
                        setSendToast(null);
                        try {
                          const content = formatSessionAsMarkdown(messages, language);
                          await agentApi.sendChat(content);
                          showSendFeedback({ type: 'success', message: t('chat.notifySuccess') }, 3000);
                        } catch (err) {
                          const parsed = getParsedApiError(err);
                          showSendFeedback({
                            type: 'error',
                            message: parsed.message || t('chat.notifyFailed'),
                          }, 5000);
                        } finally {
                          setSending(false);
                        }
                      }}
                      aria-label={t('chat.notify')}
                    >
                      {sending ? (
                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                        </svg>
                      )}
                      {t('chat.send')}
                    </Button>
                  </span>
                </Tooltip>
              </div>
            )}
          </div>
          <p className="text-secondary-text text-sm">
            {t('chat.description')}
          </p>
          <div className="mt-1">
            <SegmentedControl
              value={chatMode}
              onChange={(value) => setChatMode(value as 'chat' | 'research')}
              ariaLabel={t('research.modeLabel')}
              semantics="single-select"
              className="dark:!bg-foreground/10 dark:[&_.segmented-control-tab[aria-checked=true]]:!bg-foreground dark:[&_.segmented-control-tab[aria-checked=true]]:text-background dark:[&_.segmented-control-tab[aria-checked=false]]:text-foreground/70"
              options={[
                { value: 'chat', label: t('research.chatMode') },
                { value: 'research', label: t('research.mode') },
              ]}
            />
          </div>
          {sendToast ? (
            <InlineAlert
              variant={sendToast.type === 'success' ? 'success' : 'danger'}
              size="compact"
              title={sendToast.type === 'success' ? t('chat.sendSuccess') : t('chat.sendFailure')}
              message={sendToast.message}
              className="max-w-md"
            />
          ) : null}
        </header>

        {chatMode === 'research' ? (
          <Surface level="section" className="z-10 flex min-h-0 flex-1 flex-col overflow-auto p-4 md:p-6">
            <DeepResearchPanel key={sessionId} sessionId={sessionId} />
          </Surface>
        ) : null}
        <Surface level="canvas" className={chatMode === 'research' ? 'hidden' : 'z-10 flex min-h-0 flex-1 flex-col overflow-hidden'}>
          <ChatMessageList
            language={language}
            t={t}
            text={text}
            messages={messages}
            loading={loading}
            progressSteps={progressSteps}
            agentUnavailable={agentUnavailable}
            quickQuestions={quickQuestions}
            onQuickQuestion={handleQuickQuestion}
            quickQuestionsDisabled={isSkillsLoading || loading || sessionLoading}
            expandedThinking={expandedThinking}
            onToggleThinking={toggleThinking}
            copiedMessages={copiedMessages}
            onCopyMessage={(id, content) => void copyMessageToClipboard(id, content)}
            onDownloadMessage={downloadMessageAsMarkdown}
            messagesViewportRef={messagesViewportRef}
            messagesEndRef={messagesEndRef}
            onScroll={handleMessagesScroll}
          />

          {showJumpToBottom && (
            <div className="pointer-events-none absolute bottom-[5.75rem] right-4 z-20 md:bottom-24 md:right-6">
              <button
                type="button"
                className="pointer-events-auto chat-copy-btn shadow-soft-card"
                onClick={() => {
                  requestScrollToBottom('smooth');
                  scrollToBottom('smooth');
                }}
                aria-label={t('chat.latestMessages')}
              >
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>
                {t('chat.newMessages')}
              </button>
            </div>
          )}

          <ChatComposer
            language={language}
            t={t}
            sessionError={sessionError}
            sessionLoading={sessionLoading}
            chatError={chatError}
            lastFailedRequest={lastFailedRequest}
            onRetryLastStream={() => void retryLastStream()}
            isFollowUpContextLoading={isFollowUpContextLoading}
            contextCompressionEnabled={contextCompressionEnabled}
            contextCompressionLoaded={contextCompressionLoaded}
            contextCompressionSaving={contextCompressionSaving}
            contextCompressionError={contextCompressionError}
            onContextCompressionChange={(next) => void updateContextCompressionEnabled(next)}
            skills={skills}
            selectedSkillIds={selectedSkillIds}
            selectedSkillIdSet={selectedSkillIdSet}
            skillLimitReached={skillLimitReached}
            selectedSkillSummary={selectedSkillSummary}
            mobileSkillPickerOpen={mobileSkillPickerOpen}
            onMobileSkillPickerOpenChange={setMobileSkillPickerOpen}
            skillPickerRef={skillPickerRef}
            showSkillDesc={showSkillDesc}
            onShowSkillDesc={setShowSkillDesc}
            onToggleSkill={toggleSkillSelection}
            onClearSkills={() => setSelectedSkillIds([])}
            activeStockCode={activeStockCode}
            stockInWatchlist={activeStockCode ? stockInWatchlist(activeStockCode) : false}
            isWatchlistActioning={isWatchlistActioning}
            watchlistMessage={watchlistMessage}
            onToggleWatchlist={() => {
              if (activeStockCode) void handleToggleWatchlist(activeStockCode);
            }}
            input={input}
            onInputChange={setInput}
            onKeyDown={handleKeyDown}
            loading={loading}
            isSkillsLoading={isSkillsLoading}
            onStop={() => stopStream()}
            onSend={() => handleSend()}
          />

        </Surface>
      </div>
    </div>
  );
};

export default ChatPage;
