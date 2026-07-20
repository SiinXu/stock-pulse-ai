import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, SlidersHorizontal } from 'lucide-react';
import { cn } from '../utils/cn';
import { agentApi } from '../api/agent';
import { systemConfigApi } from '../api/systemConfig';
import { ApiErrorAlert, Badge, Button, Checkbox, ConfirmDialog, Drawer, EmptyState, InlineAlert, ScrollArea, SegmentedControl, Switch, Tooltip, useClipboard } from '../components/common';
import { DeepResearchPanel } from '../components/chat/DeepResearchPanel';
import { getParsedApiError } from '../api/error';
import type { SkillInfo } from '../api/agent';
import { DashboardStateBlock } from '../components/dashboard';
import {
  useAgentChatStore,
  type Message,
  type ProgressStep,
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
import { extractStockCodesFromMessage } from '../utils/chatStockCode';
import { findMatchingStockCode, includesStockCode, normalizeStockCode } from '../utils/stockCode';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import type { UiTextKey } from '../i18n/uiText';
import { formatUiDateTime, getUiListSeparator } from '../utils/uiLocale';
import { getStrategyDisplay } from '../utils/strategyDisplay';
import { getChatMessageDisplayContent } from '../utils/chatMessage';

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
const STRONG_COMPARE_STOCK_MESSAGE_RE = /比较|对比|\bvs\b|和[^，。,.!?！？]{0,40}比/i;
const WEAK_COMPARE_STOCK_MESSAGE_RE = /差异(?!化)|区别|不同|相比|对照|比一比/;
const CHOICE_COMPARE_STOCK_MESSAGE_RE = /哪个|哪只|哪一个|谁更|更值得|更适合|怎么选|选哪|二选一/;
const LINKED_COMPARE_STOCK_MESSAGE_RE = /(?:和|与|跟|同)[^，。,.!?！？]{0,40}(?:差异(?!化)|区别|不同|相比|对照|比一比)/;
const SWITCH_STOCK_MESSAGE_RE = /换成|改看|分析|看看|研究|诊断/;

type ActiveStockContext = Pick<ChatFollowUpContext, 'stock_code' | 'stock_name'>;
type ActiveStockResolution = {
  context: ActiveStockContext;
  useForCurrentSend: boolean;
};

const getMessageSkillNames = (msg: Message): string[] => {
  if (msg.skillNames?.length) return msg.skillNames;
  if (msg.skillName) return [msg.skillName];
  if (msg.skills?.length) return msg.skills;
  if (msg.skill) return [msg.skill];
  return [];
};

const getMessageSkillLabel = (msg: Message): string => getMessageSkillNames(msg).join('、');

const isStageDoneSuccessful = (status?: string): boolean => {
  if (!status) return true;
  const normalized = status.trim().toLowerCase();
  return ['completed', 'success', 'succeeded', 'done'].includes(normalized);
};

const getStageDoneLabel = (step: ProgressStep): string => {
  const stage = step.stage || 'stage';
  if (step.message) return step.message;
  if (isStageDoneSuccessful(step.status)) return `${stage} completed`;
  return `${stage} ${step.status || 'finished'}`;
};

const getPipelineBudgetSkippedLabel = (step: ProgressStep): string => {
  if (step.message) return step.message;
  return `${step.stage || 'pipeline'} skipped: insufficient budget`;
};

const isCompareStockMessage = (
  message: string,
  stockCodes: string[],
  currentStockCode?: string | null,
): boolean => {
  if (STRONG_COMPARE_STOCK_MESSAGE_RE.test(message)) {
    return true;
  }
  const current = currentStockCode ? normalizeStockCode(currentStockCode) : null;
  const newStockCodes = current
    ? stockCodes.filter((code) => code !== current)
    : stockCodes;
  if (newStockCodes.length >= 2) {
    return true;
  }
  if (CHOICE_COMPARE_STOCK_MESSAGE_RE.test(message) && stockCodes.length >= 2) {
    return true;
  }
  if (!WEAK_COMPARE_STOCK_MESSAGE_RE.test(message)) {
    return false;
  }
  if (stockCodes.length >= 2) {
    return true;
  }
  if (!currentStockCode) {
    return false;
  }
  const hasNewStock = stockCodes.some((code) => code !== current);
  return hasNewStock && LINKED_COMPARE_STOCK_MESSAGE_RE.test(message);
};

const resolveActiveStockContextFromMessage = (
  message: string,
  currentContext: ActiveStockContext | null,
): ActiveStockResolution | null => {
  const stockCodes = extractStockCodesFromMessage(message);
  const stockCode = stockCodes[0] ?? null;
  if (!stockCode) {
    return null;
  }

  const isCompare = isCompareStockMessage(message, stockCodes, currentContext?.stock_code);
  const isSwitch = SWITCH_STOCK_MESSAGE_RE.test(message);
  const currentStockCode = currentContext?.stock_code
    ? normalizeStockCode(currentContext.stock_code)
    : null;
  const newStockCodes = currentStockCode
    ? stockCodes.filter((code) => code !== currentStockCode)
    : stockCodes;
  // Explicit switches can mention the old stock; use the single new code when present.
  const targetStockCode = isSwitch && newStockCodes.length === 1
    ? newStockCodes[0]
    : stockCode;
  const isDifferentStock = currentStockCode !== targetStockCode;

  // Compare messages and implicit follow-ups must not rewrite the active stock context.
  if (isCompare || (currentContext && !isSwitch)) {
    return null;
  }

  return {
    context: {
      stock_code: targetStockCode,
      stock_name: currentContext && !isDifferentStock
        ? currentContext.stock_name
        : null,
    },
    // Only explicit switches should affect the context sent with the current request.
    useForCurrentSend: isSwitch && isDifferentStock,
  };
};

const restoreActiveStockContextFromMessages = (messages: Message[]): ActiveStockContext | null => {
  let restoredContext: ActiveStockContext | null = null;
  for (const message of messages) {
    if (message.role !== 'user') {
      continue;
    }
    const resolution = resolveActiveStockContextFromMessage(message.content, restoredContext);
    if (resolution) {
      restoredContext = resolution.context;
    }
  }
  return restoredContext;
};

const ChatPage: React.FC = () => {
  const { language, t } = useUiLanguage();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialUrlSessionIdRef = useRef(
    searchParams.get(CHAT_SESSION_QUERY_KEY)?.trim() || undefined,
  );
  const [input, setInput] = useState('');
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [isSkillsLoading, setIsSkillsLoading] = useState(true);
  const [selectedSkillIds, setSelectedSkillIds] = useState<string[]>([]);
  const [showSkillDesc, setShowSkillDesc] = useState<string | null>(null);
  const [mobileSkillPickerOpen, setMobileSkillPickerOpen] = useState(false);
  const [expandedThinking, setExpandedThinking] = useState<Set<string>>(new Set());
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);
  const [sending, setSending] = useState(false);
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
  const [copiedMessages, setCopiedMessages] = useState<Set<string>>(new Set());
  const { copyText } = useClipboard();
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);
  const [watchlistCodes, setWatchlistCodes] = useState<string[]>([]);
  const [isWatchlistActioning, setIsWatchlistActioning] = useState(false);
  const [watchlistMessage, setWatchlistMessage] = useState<string | null>(null);
  const [activeStockCode, setActiveStockCode] = useState<string | null>(null);
  const [activeStockContext, setActiveStockContext] = useState<ActiveStockContext | null>(null);
  const [chatMode, setChatMode] = useState<'chat' | 'research'>('chat');
  const activeStockContextRef = useRef<ActiveStockContext | null>(null);
  const watchlistMessageTimerRef = useRef<number | null>(null);
  const copyResetTimerRef = useRef<Partial<Record<string, number>>>({});
  const messagesViewportRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isMountedRef = useRef(true);
  const sendToastTimerRef = useRef<number | null>(null);
  const followUpHydrationTokenRef = useRef(0);
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
  }, [mobileSkillPickerOpen]);

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

  useEffect(() => () => {
    isMountedRef.current = false;
  }, []);

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
    loadSessions,
    loadInitialSession,
    switchSession,
    startStream,
    retryLastStream,
    stopStream,
    clearCompletionBadge,
  } = useAgentChatStore();

  useEffect(() => {
    if (activeStockContext || messages.length === 0) {
      return;
    }
    const restoredContext = restoreActiveStockContextFromMessages(messages);
    if (!restoredContext) {
      return;
    }
    setActiveStockContext(restoredContext);
    activeStockContextRef.current = restoredContext;
    setActiveStockCode(restoredContext.stock_code);
  }, [activeStockContext, messages, sessionId]);

  const syncScrollState = useCallback(() => {
    const viewport = messagesViewportRef.current;
    if (!viewport) return;
    const nearBottom = isNearBottom({
      scrollTop: viewport.scrollTop,
      clientHeight: viewport.clientHeight,
      scrollHeight: viewport.scrollHeight,
    });
    shouldStickToBottomRef.current = nearBottom;
    setShowJumpToBottom((prev) => (nearBottom ? false : prev));
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, []);

  const requestScrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    shouldStickToBottomRef.current = true;
    pendingScrollBehaviorRef.current = behavior;
    setShowJumpToBottom(false);
  }, []);

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
  }, [messages, progressSteps, loading, sessionId, scrollToBottom]);

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

  const setSessionInUrl = useCallback((targetSessionId: string) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set(CHAT_SESSION_QUERY_KEY, targetSessionId);
      return next;
    }, { replace: true });
  }, [setSearchParams]);

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
        setSelectedSkillIds(defaultId ? [defaultId] : []);
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
    setSelectedSkillIds((prev) => {
      if (prev.includes(skillId)) {
        return prev.filter((id) => id !== skillId);
      }
      if (prev.length >= MAX_SELECTED_SKILLS) {
        return prev;
      }
      return [...prev, skillId];
    });
  }, []);

  const handleStartNewChat = useCallback(() => {
    followUpContextRef.current = null;
    activeStockContextRef.current = null;
    setActiveStockContext(null);
    setActiveStockCode(null);
    requestScrollToBottom('auto');
    const newSessionId = useAgentChatStore.getState().startNewChat();
    setSessionInUrl(newSessionId);
    setSidebarOpen(false);
  }, [requestScrollToBottom, setSessionInUrl]);

  const handleSwitchSession = useCallback(async (targetSessionId: string) => {
    if (targetSessionId === sessionId) {
      setSidebarOpen(false);
      return;
    }
    const switched = await switchSession(targetSessionId);
    if (switched !== false) {
      followUpContextRef.current = null;
      activeStockContextRef.current = null;
      setActiveStockContext(null);
      setActiveStockCode(null);
      requestScrollToBottom('auto');
      setSessionInUrl(targetSessionId);
      setSidebarOpen(false);
    }
  }, [requestScrollToBottom, sessionId, setSessionInUrl, switchSession]);

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
  }, [deleteConfirmId, deleteLoading, handleStartNewChat, language, loadSessions, sessionId]);

  // Handle follow-up from report page: ?stock=600519&name=贵州茅台&recordId=xxx
  useEffect(() => {
    const stock = sanitizeFollowUpStockCode(searchParams.get('stock'));
    const name = sanitizeFollowUpStockName(searchParams.get('name'));
    const recordId = parseFollowUpRecordId(searchParams.get('recordId'));

    if (!stock) {
      return;
    }

    const hydrationToken = ++followUpHydrationTokenRef.current;
    setInput(buildFollowUpPrompt(stock, name));
    setActiveStockCode(stock);
    const stockContext = {
      stock_code: stock,
      stock_name: name,
    };
    activeStockContextRef.current = stockContext;
    setActiveStockContext(stockContext);
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
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.delete('stock');
      next.delete('name');
      next.delete('recordId');
      if (!next.get(CHAT_SESSION_QUERY_KEY)) {
        next.set(CHAT_SESSION_QUERY_KEY, sessionId);
      }
      return next;
    }, { replace: true });
  }, [searchParams, sessionId, setSearchParams]);

  const handleSend = useCallback(
    async (overrideMessage?: string, overrideSkillIds?: string[]) => {
      const msgText = (overrideMessage ?? input).trim();
      if (!msgText || loading || sessionLoading || isFollowUpContextLoading || isSkillsLoading) return;
      const usedSkillIds = normalizeSelectedSkillIds(overrideSkillIds ?? selectedSkillIds);
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
        ...(usedSkillIds.length > 0 ? { skills: usedSkillIds } : {}),
        context: contextForSend ?? undefined,
      };
      followUpHydrationTokenRef.current += 1;
      followUpContextRef.current = null;
      setIsFollowUpContextLoading(false);

      setInput('');
      setMobileSkillPickerOpen(false);
      requestScrollToBottom('smooth');
      await startStream(payload, {
        skillNames: usedSkillNames,
        skillName: usedSkillNames.join(getUiListSeparator(language)),
      });
    },
    [getSkillNames, input, isFollowUpContextLoading, isSkillsLoading, language, loading, normalizeSelectedSkillIds, requestScrollToBottom, selectedSkillIds, sessionId, sessionLoading, startStream, t],
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
    setExpandedThinking((prev) => {
      const next = new Set(prev);
      if (next.has(msgId)) next.delete(msgId);
      else next.add(msgId);
      return next;
    });
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

  const getCurrentStage = (steps: ProgressStep[]): string => {
    if (steps.length === 0) return t('chat.connecting');
    const last = steps[steps.length - 1];
    if (last.type === 'thinking') return last.message || t('chat.thinking');
    if (last.type === 'tool_start')
      return `${last.display_name || last.tool}...`;
    if (last.type === 'tool_done')
      return t('chat.completed', { name: last.display_name || last.tool || '' });
    if (last.type === 'stage_start')
      return last.message || `Starting ${last.stage || 'stage'}...`;
    if (last.type === 'stage_done')
      return getStageDoneLabel(last);
    if (last.type === 'pipeline_timeout')
      return last.message || `${last.stage || 'pipeline'} timed out`;
    if (last.type === 'pipeline_budget_skipped')
      return getPipelineBudgetSkippedLabel(last);
    if (last.type === 'generating')
      return last.message || t('chat.generating');
    return t('chat.processing');
  };

  const renderThinkingBlock = (msg: Message) => {
    if (!msg.thinkingSteps || msg.thinkingSteps.length === 0) return null;
    const isExpanded = expandedThinking.has(msg.id);
    const toolSteps = msg.thinkingSteps.filter((s) => s.type === 'tool_done');
    const totalDuration = toolSteps.reduce(
      (sum, s) => sum + (s.duration || 0),
      0,
    );
    const summary = t('chat.toolCalls', { count: toolSteps.length, duration: totalDuration.toFixed(1) });

    return (
      <button
        onClick={() => toggleThinking(msg.id)}
        className="flex items-center gap-2 text-xs text-muted-text hover:text-secondary-text transition-colors mb-2 w-full text-left"
      >
        <svg
          className={`w-3 h-3 transition-transform flex-shrink-0 ${isExpanded ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
        <span className="flex items-center gap-1.5">
          <span className="opacity-60">{t('chat.thinkingProcess')}</span>
          <span className="text-muted-text/50">·</span>
          <span className="opacity-50">{summary}</span>
        </span>
      </button>
    );
  };

  const renderThinkingDetails = (steps: ProgressStep[]) => (
    <div className="mb-3 pl-5 border-l border-border/40 space-y-1.5 animate-fade-in">
      {steps.map((step, idx) => {
        let statusClass = 'chat-progress-item-muted';
        let iconClass = 'chat-progress-dot-muted';
        let text = '';
        if (step.type === 'thinking') {
          text = step.message || t('chat.thinkingStep', { step: step.step || '' });
          statusClass = 'chat-progress-item-thinking';
          iconClass = 'chat-progress-dot-thinking';
        } else if (step.type === 'tool_start') {
          text = `${step.display_name || step.tool}...`;
          statusClass = 'chat-progress-item-tool';
          iconClass = 'chat-progress-dot-tool';
        } else if (step.type === 'tool_done') {
          text = `${step.display_name || step.tool} (${step.duration}s)`;
          statusClass = step.success ? 'chat-progress-item-success' : 'chat-progress-item-danger';
          iconClass = step.success ? 'chat-progress-dot-success' : 'chat-progress-dot-danger';
        } else if (step.type === 'stage_start') {
          text = step.message || `Starting ${step.stage || 'stage'}...`;
          statusClass = 'chat-progress-item-thinking';
          iconClass = 'chat-progress-dot-thinking';
        } else if (step.type === 'stage_done') {
          const isSuccess = isStageDoneSuccessful(step.status);
          text = getStageDoneLabel(step);
          statusClass = isSuccess ? 'chat-progress-item-success' : 'chat-progress-item-danger';
          iconClass = isSuccess ? 'chat-progress-dot-success' : 'chat-progress-dot-danger';
        } else if (step.type === 'pipeline_timeout') {
          text = step.message || `${step.stage || 'pipeline'} timed out`;
          statusClass = 'chat-progress-item-danger';
          iconClass = 'chat-progress-dot-danger';
        } else if (step.type === 'pipeline_budget_skipped') {
          text = getPipelineBudgetSkippedLabel(step);
          statusClass = 'chat-progress-item-muted';
          iconClass = 'chat-progress-dot-muted';
        } else if (step.type === 'generating') {
          text = step.message || t('chat.generateAnalysis');
          statusClass = 'chat-progress-item-generating';
          iconClass = 'chat-progress-dot-generating';
        } else {
          text = step.message || step.type;
        }
        return (
          <div
            key={idx}
            className={cn('chat-progress-item', statusClass)}
          >
            <span className={cn('chat-progress-dot', iconClass)} />
            <span className="leading-relaxed">{text}</span>
          </div>
        );
      })}
    </div>
  );

  const sidebarContent = (
    <>
      <div className="flex items-center justify-between border-b border-white/5 bg-white/2 p-3.5">
        <h2 className="hidden text-sm font-semibold text-primary uppercase tracking-[0.2em] md:flex items-center gap-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {t('chat.history')}
        </h2>
        <div className="flex items-center">
          <button
            type="button"
            onClick={handleStartNewChat}
            className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-muted-text transition-all hover:bg-white/10 hover:text-foreground"
            aria-label={t('chat.newConversation')}
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
          </button>
        </div>
      </div>
      <ScrollArea testId="chat-session-list-scroll" viewportClassName="p-3">
        {sessionsLoading ? (
          <DashboardStateBlock
            loading
            compact
            title={t('chat.loadingSessions')}
          />
        ) : sessionsError ? (
          <ApiErrorAlert
            error={sessionsError}
            actionLabel={t('common.retry')}
            onAction={() => void loadSessions()}
          />
        ) : sessions.length === 0 ? (
          <DashboardStateBlock
            compact
            title={t('chat.emptySessionsTitle')}
            description={t('chat.emptySessionsDescription')}
          />
        ) : (
          <div className="space-y-2">
            {sessions.map((s) => (
              <div key={s.session_id} className="session-item-row">
                <button
                  type="button"
                  onClick={() => void handleSwitchSession(s.session_id)}
                  disabled={sessionLoading}
                  className={`session-item ${s.session_id === sessionId ? 'active' : ''}`}
                  aria-label={t('chat.switchSession', { title: s.title })}
                  aria-current={s.session_id === sessionId ? 'page' : undefined}
                >
                  <div className="indicator" />
                  <div className="content">
                    <span className="title">{s.title}</span>
                    <div className="mt-0.5 flex items-center gap-2">
                      <span className="meta">
                        {t('chat.sessionMessages', { count: s.message_count })}
                      </span>
                      {s.last_active && (
                        <>
                          <span className="separator" />
                          <span className="meta">
                            {formatUiDateTime(s.last_active, language, { month: 'short', day: 'numeric' })}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </button>
                <button
                  type="button"
                  className="delete-btn"
                  onClick={() => {
                    setDeleteConfirmId(s.session_id);
                    setDeleteError(null);
                  }}
                  disabled={sessionLoading}
                  aria-label={t('chat.deleteSession', { title: s.title })}
                >
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </>
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
      <div className="hidden h-full w-64 flex-shrink-0 flex-col overflow-hidden rounded-3xl border border-white/8 bg-card/82 shadow-soft-card md:flex">
        {sidebarContent}
      </div>

      {/* Mobile sidebar overlay */}
      <Drawer
        isOpen={sidebarOpen}
        onClose={closeSidebar}
        title={t('chat.history')}
        variant="navigation"
      >
        {sidebarContent}
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
              <button
                type="button"
                onClick={() => setSidebarOpen(true)}
                className="-ml-1 inline-flex h-11 w-11 items-center justify-center rounded-lg text-secondary-text transition-colors hover:bg-hover hover:text-foreground md:hidden"
                aria-label={t('chat.history')}
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 6h16M4 12h16M4 18h16"
                  />
                </svg>
              </button>
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
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                        />
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
                        <svg
                          className="w-4 h-4 animate-spin"
                          fill="none"
                          viewBox="0 0 24 24"
                        >
                          <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="4"
                          />
                          <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                          />
                        </svg>
                      ) : (
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                          />
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
              onChange={(value) => setChatMode(value)}
              ariaLabel={t('research.modeLabel')}
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
          <div className="relative z-10 flex min-h-0 flex-1 flex-col overflow-auto border border-white/6 bg-card/78 glass-card p-4 md:p-6">
            <DeepResearchPanel key={sessionId} sessionId={sessionId} />
          </div>
        ) : null}
        <div className={chatMode === 'research' ? 'hidden' : 'relative z-10 flex min-h-0 flex-1 flex-col overflow-hidden border border-white/6 bg-card/78 glass-card'}>
          {/* Messages */}
          <ScrollArea
            className="relative z-10 flex-1"
            viewportRef={messagesViewportRef}
            onScroll={handleMessagesScroll}
            viewportClassName="space-y-6 p-4 md:p-6"
            testId="chat-message-scroll"
          >
            {messages.length === 0 && !loading ? (
              <div className="flex h-full items-center justify-center">
                <EmptyState
                  title={t('chat.emptyTitle')}
                  description={t('chat.emptyDescription')}
                  className="max-w-2xl"
                  icon={(
                    <svg
                      className="h-8 w-8"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                      />
                    </svg>
                  )}
                  action={(
                    <div className="flex max-w-lg flex-wrap justify-center gap-2">
                      {quickQuestions.map((q, i) => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => handleQuickQuestion(q)}
                          disabled={isSkillsLoading || loading || sessionLoading}
                          className="quick-question-btn"
                        >
                          {q.label}
                        </button>
                      ))}
                    </div>
                  )}
                />
              </div>
            ) : (
              messages.map((msg) => {
                const skillLabel = getMessageSkillLabel(msg);
                const displayContent = getChatMessageDisplayContent(msg, language);
                return (
                <div
                  key={msg.id}
                  className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  <div
                    className={cn(
                      'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold shadow-sm transition-all',
                      msg.role === 'user' ? 'chat-avatar-user' : 'chat-avatar-ai'
                    )}
                  >
                    {msg.role === 'user' ? 'U' : 'AI'}
                  </div>
                  <div
                    className={cn(
                      'group/message min-w-0 w-fit max-w-[min(100%,48rem)] overflow-hidden px-5 py-3.5 transition-colors',
                      msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'
                    )}
                  >
                    {msg.role === 'assistant' && skillLabel && (
                      <div className="mb-2">
                        <Badge variant="info" className="chat-skill-badge shadow-none" aria-label={t('chat.skill', { name: skillLabel })}>
                          <svg
                            className="w-3 h-3"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M13 10V3L4 14h7v7l9-11h-7z"
                            />
                          </svg>
                          {skillLabel}
                        </Badge>
                      </div>
                    )}
                    {msg.role === 'assistant' && renderThinkingBlock(msg)}
                    {msg.role === 'assistant' &&
                      expandedThinking.has(msg.id) &&
                      msg.thinkingSteps &&
                      renderThinkingDetails(msg.thinkingSteps)}
                    {msg.role === 'assistant' ? (
                      <div className="relative">
                        <div className="chat-message-actions">
                          <button
                            type="button"
                            onClick={() => copyMessageToClipboard(msg.id, displayContent)}
                            className="chat-copy-btn"
                            aria-label={copiedMessages.has(msg.id) ? text.copied : text.copy}
                          >
                            {copiedMessages.has(msg.id) ? text.copied : text.copy}
                          </button>
                          <button
                            type="button"
                            onClick={() => downloadMessageAsMarkdown(msg)}
                            className="chat-copy-btn"
                            aria-label={t('chat.exportMessage')}
                          >
                            {t('chat.export')}
                          </button>
                        </div>
                        <div className="chat-prose pr-20 sm:pr-24">
                          <Markdown remarkPlugins={[remarkGfm]}>
                            {displayContent}
                          </Markdown>
                        </div>
                      </div>
                    ) : (
                      msg.content
                        .split('\n')
                        .map((line, i) => (
                          <p
                            key={i}
                            className="mb-1 last:mb-0 leading-relaxed"
                          >
                            {line || '\u00A0'}
                          </p>
                        ))
                    )}
                  </div>
                </div>
                );
              })
            )}

            {loading && (
              <div className="flex gap-4">
                <div className="w-8 h-8 rounded-full bg-elevated text-foreground flex items-center justify-center flex-shrink-0 text-xs font-bold">
                  AI
                </div>
                <div className="min-w-50 max-w-[min(100%,48rem)] overflow-hidden rounded-2xl rounded-tl-sm border border-white/6 bg-card/72 px-5 py-4">
                  <div className="flex items-center gap-2.5 text-sm text-secondary-text">
                    <div className="relative w-4 h-4 flex-shrink-0">
                      <div className="absolute inset-0 rounded-full border-2 border-primary/20" />
                      <div className="absolute inset-0 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                    </div>
                    <span className="text-secondary-text">
                      {getCurrentStage(progressSteps)}
                    </span>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </ScrollArea>

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
                <svg
                  className="h-3.5 w-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 14l-7 7m0 0l-7-7m7 7V3"
                  />
                </svg>
                {t('chat.newMessages')}
              </button>
            </div>
          )}

          {/* Input area */}
          <div className="border-t border-white/6 bg-card/88 p-4 md:p-6 relative z-20">
            <div className="space-y-3">
              {sessionError ? (
                <ApiErrorAlert error={sessionError} />
              ) : null}
              {sessionLoading ? (
                <InlineAlert
                  variant="info"
                  size="compact"
                  title={t('chat.loadingSessions')}
                  message={t('common.loading')}
                />
              ) : null}
              {chatError ? (
                <ApiErrorAlert
                  error={chatError}
                  actionLabel={lastFailedRequest ? t('common.retry') : undefined}
                  onAction={lastFailedRequest ? () => void retryLastStream() : undefined}
                />
              ) : null}
              {isFollowUpContextLoading ? (
                <InlineAlert
                  variant="info"
                  size="compact"
                  title={t('chat.followUpLoadingTitle')}
                  message={t('chat.followUpLoadingMessage')}
                />
              ) : null}
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/6 bg-surface/25 px-3 py-2">
                <div className="min-w-0">
                  <span className="text-sm font-medium text-foreground">{t('chat.contextCompression')}</span>
                  <span className="ml-2 text-xs text-muted-text">{t('chat.contextCompressionDescription')}</span>
                </div>
                <div className="flex items-center gap-2">
                  {contextCompressionSaving ? (
                    <span className="text-xs text-muted-text">{t('chat.saving')}</span>
                  ) : null}
                  <Switch
                    checked={contextCompressionEnabled}
                    onCheckedChange={(next) => void updateContextCompressionEnabled(next)}
                    aria-label={t('chat.contextCompression')}
                    disabled={!contextCompressionLoaded || contextCompressionSaving}
                    visualTestId="context-compression-switch-visual"
                  />
                </div>
              </div>
              {contextCompressionError ? (
                <InlineAlert
                  variant="danger"
                  size="compact"
                  title={t('chat.contextCompressionUnsaved')}
                  message={contextCompressionError}
                />
              ) : null}
              {skills.length > 0 && (
                <div className="relative space-y-2" ref={skillPickerRef}>
                  <button
                    type="button"
                    className="home-surface-button flex h-9 w-full items-center justify-between gap-2 rounded-lg px-2 text-left text-xs text-foreground"
                    aria-label={mobileSkillPickerOpen ? t('chat.collapseStrategies') : t('chat.expandStrategies')}
                    aria-expanded={mobileSkillPickerOpen}
                    aria-controls="chat-skill-picker-panel"
                    onClick={() => setMobileSkillPickerOpen((open) => !open)}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <SlidersHorizontal className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                      <span className="flex-shrink-0 font-medium">{t('chat.strategy')}</span>
                      <span className="truncate text-xs text-muted-text">{selectedSkillSummary}</span>
                    </span>
                    <ChevronDown
                      className={cn(
                        'h-4 w-4 flex-shrink-0 text-muted-text transition-transform',
                        mobileSkillPickerOpen ? 'rotate-180' : '',
                      )}
                      aria-hidden="true"
                    />
                  </button>
                  <div
                    id="chat-skill-picker-panel"
                    data-testid="chat-skill-picker-panel"
                    className={cn(
                      mobileSkillPickerOpen ? 'flex' : 'hidden',
                      'absolute bottom-full left-0 right-0 z-20 mb-2 max-h-60 flex-col gap-y-2 overflow-y-auto rounded-xl border border-border bg-card px-3 py-2.5 shadow-soft-card',
                    )}
                  >
                    <Checkbox
                      name="general-analysis"
                      value=""
                      checked={selectedSkillIds.length === 0}
                      onChange={() => setSelectedSkillIds([])}
                      containerClassName="group min-h-8 gap-1.5 text-sm"
                      label={(
                        <span
                          className={`text-sm transition-colors ${selectedSkillIds.length === 0 ? 'font-medium text-foreground' : 'font-normal text-secondary-text group-hover:text-foreground'}`}
                        >
                          {t('chat.generalAnalysis')}
                        </span>
                      )}
                    />
                    {skills.map((s) => {
                      const checked = selectedSkillIdSet.has(s.id);
                      const disabled = !checked && skillLimitReached;
                      const display = getStrategyDisplay(s, language);
                      return (
                        <div
                          key={s.id}
                          className={`flex min-h-8 items-center gap-1.5 cursor-pointer group relative ${disabled ? 'opacity-60 cursor-not-allowed' : ''}`}
                          onMouseEnter={() => setShowSkillDesc(s.id)}
                          onMouseLeave={() => setShowSkillDesc(null)}
                        >
                          <Checkbox
                            name="skills"
                            value={s.id}
                            checked={checked}
                            disabled={disabled}
                            onChange={() => toggleSkillSelection(s.id)}
                            containerClassName="min-h-8 gap-1.5"
                            label={(
                              <span
                                className={`text-sm transition-colors ${checked ? 'font-medium text-foreground' : 'font-normal text-secondary-text group-hover:text-foreground'}`}
                              >
                                {display.name}
                              </span>
                            )}
                          />
                          {showSkillDesc === s.id && s.description && (
                            <div className="skill-desc-tooltip">
                              <p className="skill-title">{display.name}</p>
                              <p>{display.description}</p>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

            {activeStockCode && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-text font-mono">{activeStockCode}</span>
                <Button
                  variant="secondary"
                  size="compact"
                  isLoading={isWatchlistActioning}
                  onClick={() => void handleToggleWatchlist(activeStockCode)}
                  className="text-xs"
                >
                  {stockInWatchlist(activeStockCode) ? t('chat.removeWatchlist') : t('chat.addWatchlist')}
                </Button>
                {watchlistMessage && (
                  <span className="text-xs text-secondary-text animate-in fade-in">{watchlistMessage}</span>
                )}
              </div>
            )}

              <div className="flex items-end gap-3">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  aria-label={t('chat.messageInput')}
                  placeholder={t('chat.inputPlaceholder')}
                  disabled={loading || sessionLoading}
                  rows={1}
                  className="flex-1 min-h-11 max-h-50 rounded-sm border border-border bg-transparent px-3 py-2 text-base placeholder:text-muted-text transition-colors duration-200 focus:outline-none focus:border-muted-text resize-none disabled:cursor-not-allowed disabled:opacity-60 sm:text-sm"
                  style={{ height: 'auto' }}
                  onInput={(e) => {
                    const t = e.target as HTMLTextAreaElement;
                    t.style.height = 'auto';
                    t.style.height = `${Math.min(t.scrollHeight, 200)}px`;
                  }}
                />
                {loading ? (
                  <Button
                    variant="secondary"
                    onClick={() => stopStream()}
                    aria-label={t('chat.stop')}
                    className="flex-shrink-0"
                  >
                    {t('chat.stop')}
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    onClick={() => handleSend()}
                    disabled={!input.trim() || isFollowUpContextLoading || isSkillsLoading || sessionLoading}
                    className="btn-primary flex-shrink-0"
                  >
                    {t('chat.send')}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatPage;
