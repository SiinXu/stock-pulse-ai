import React from 'react';
import { RefreshCw, Trash2 } from 'lucide-react';
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
}: ChatSessionSidebarProps): React.ReactElement {
  return (
    <>
      <div className="flex items-center justify-between border-b border-subtle bg-subtle-soft p-3.5">
        <h2 className="hidden items-center gap-2 text-sm font-semibold uppercase tracking-[0.2em] text-primary xl:flex">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {t('chat.history')}
        </h2>
        <div className="flex items-center">
          <IconButton
            onClick={onNewChat}
            size="navigation"
            tooltip={false}
            aria-label={t('chat.newConversation')}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </IconButton>
        </div>
      </div>
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
                  variant="danger"
                  size="compact"
                  tooltip={false}
                  className="delete-btn absolute right-1 top-1 z-10 !h-7 !w-7 !rounded-md hover:!border-transparent hover:!bg-transparent focus-visible:!border-transparent focus-visible:!bg-transparent"
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
    </>
  );
}
