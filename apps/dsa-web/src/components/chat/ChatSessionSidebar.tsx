import React from 'react';
import { History, PanelLeftClose, PanelLeftOpen, RefreshCw, Trash2 } from 'lucide-react';
import type { ChatSessionItem } from '../../api/agent';
import type { ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  IconButton,
  ScrollArea,
  SearchInput,
  Tooltip,
} from '../common';
import { Pressable } from '../common/Pressable';
import { DashboardStateBlock } from '../dashboard';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import { formatUiDateTime } from '../../utils/uiLocale';
import { cn } from '../../utils/cn';

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

export interface ChatSessionSidebarProps {
  language: UiLanguage;
  t: Translate;
  sessionSearch: string;
  onSessionSearchChange: (value: string) => void;
  sessions: ChatSessionItem[];
  filteredSessions: ChatSessionItem[];
  sessionsLoading: boolean;
  sessionsError: ParsedApiError | null;
  sessionLoading: boolean;
  sessionId: string;
  onNewChat: () => void;
  onRetryLoadSessions: () => void;
  onSwitchSession: (sessionId: string) => void;
  onRequestDelete: (sessionId: string) => void;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
}

export function ChatSessionSidebar({
  language,
  t,
  sessionSearch,
  onSessionSearchChange,
  sessions,
  filteredSessions,
  sessionsLoading,
  sessionsError,
  sessionLoading,
  sessionId,
  onNewChat,
  onRetryLoadSessions,
  onSwitchSession,
  onRequestDelete,
  collapsed = false,
  onCollapsedChange,
}: ChatSessionSidebarProps): React.ReactElement {
  return (
    <>
      <div
        className={cn(
          'flex',
          collapsed ? 'items-center justify-center p-1.5' : 'items-center justify-between p-3.5',
        )}
      >
        {collapsed && onCollapsedChange ? (
          <IconButton
            onClick={() => onCollapsedChange(false)}
            size="navigation"
            variant="bare"
            className="group/history-toggle"
            aria-label={t('layout.expandSidebar')}
            aria-expanded={false}
            aria-controls="chat-session-sidebar-content"
          >
            <History className="group-hover/history-toggle:hidden group-focus-visible/history-toggle:hidden" aria-hidden="true" />
            <PanelLeftOpen className="hidden group-hover/history-toggle:block group-focus-visible/history-toggle:block" aria-hidden="true" />
          </IconButton>
        ) : (
          <>
            <h2 className="hidden items-center gap-2 text-sm font-semibold uppercase tracking-[0.2em] text-primary xl:flex">
              <History className="h-5 w-5" aria-hidden="true" />
              {t('chat.history')}
            </h2>
            <div className="flex items-center">
              {onCollapsedChange ? (
                <IconButton
                  onClick={() => onCollapsedChange(true)}
                  size="navigation"
                  tooltip={false}
                  aria-label={t('layout.collapseSidebar')}
                  aria-expanded={true}
                  aria-controls="chat-session-sidebar-content"
                >
                  <PanelLeftClose aria-hidden="true" />
                </IconButton>
              ) : null}
              <IconButton
                onClick={onNewChat}
                size="default"
                variant="bare"
                tooltip={false}
                aria-label={t('chat.newConversation')}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
              </IconButton>
            </div>
          </>
        )}
      </div>
      {!collapsed ? (
        <div id="chat-session-sidebar-content" className="contents">
          <div className="px-3 pt-3">
            <SearchInput
              value={sessionSearch}
              onChange={(event) => onSessionSearchChange(event.target.value)}
              aria-label={t('layout.search')}
              placeholder={t('common.searchPlaceholder')}
              wrapperClassName="w-full shadow-none"
            />
          </div>
          <ScrollArea testId="chat-session-list-scroll" viewportClassName="p-3">
            {sessionsLoading ? (
              <DashboardStateBlock loading compact title={t('chat.loadingSessions')} />
            ) : sessionsError ? (
              <div className="relative [&_details]:border-t-0 [&_details]:pt-0">
                <ApiErrorAlert error={sessionsError} className="pr-10" />
                <Tooltip content={t('common.retry')} className="absolute right-2 top-2 z-10">
                  <IconButton
                    variant="danger"
                    size="compact"
                    tooltip={false}
                    aria-label={t('common.retry')}
                    onClick={onRetryLoadSessions}
                  >
                    <RefreshCw aria-hidden="true" />
                  </IconButton>
                </Tooltip>
              </div>
            ) : sessions.length === 0 ? (
              <DashboardStateBlock
                compact
                title={t('chat.emptySessionsTitle')}
                description={t('chat.emptySessionsDescription')}
              />
            ) : filteredSessions.length === 0 ? (
              <DashboardStateBlock compact title={t('common.noMatches')} />
            ) : (
              <div className="space-y-2">
                {filteredSessions.map((s) => (
                  <div key={s.session_id} className="session-item-row relative">
                    <Pressable
                      onClick={() => onSwitchSession(s.session_id)}
                      disabled={sessionLoading}
                      className={`session-item ${s.session_id === sessionId ? 'active' : ''}`}
                      aria-label={t('chat.switchSession', { title: s.title })}
                      aria-current={s.session_id === sessionId ? 'page' : undefined}
                    >
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
                                {formatUiDateTime(s.last_active, language, {
                                  month: 'short',
                                  day: 'numeric',
                                })}
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                    </Pressable>
                    <IconButton
                      variant="bare"
                      size="compact"
                      tooltip={false}
                      className="delete-btn absolute right-1 top-1 z-10 text-danger"
                      onClick={() => onRequestDelete(s.session_id)}
                      disabled={sessionLoading}
                      aria-label={t('chat.deleteSession', { title: s.title })}
                    >
                      <Trash2 aria-hidden="true" />
                    </IconButton>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </div>
      ) : null}
    </>
  );
}
