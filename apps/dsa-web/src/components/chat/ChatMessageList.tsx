import React from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy, Download } from 'lucide-react';
import { Badge, IconButton, ScrollArea } from '../common';
import { ChatEmptyMessages } from './ChatEmptyMessages';
import {
  ChatThinkingDetails,
  ChatThinkingToggle,
} from './ChatThinkingDetails';
import { getCurrentStageLabel, getMessageSkillLabel } from './chatMessageMeta';
import { contentHasHypotheticalMarker } from './whatIfScenario';
import type { Message, ProgressStep } from '../../stores/agentChatStore';
import { cn } from '../../utils/cn';
import { getChatMessageDisplayContent } from '../../utils/chatMessage';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

export interface ChatMessageListProps {
  language: UiLanguage;
  t: Translate;
  text: { copied: string; copy: string };
  messages: Message[];
  loading: boolean;
  progressSteps: ProgressStep[];
  agentUnavailable: boolean;
  quickQuestions: Array<{ label: string; skill: string }>;
  onQuickQuestion: (question: { label: string; skill: string }) => void;
  quickQuestionsDisabled: boolean;
  expandedThinking: Set<string>;
  onToggleThinking: (messageId: string) => void;
  copiedMessages: Set<string>;
  onCopyMessage: (messageId: string, content: string) => void;
  onDownloadMessage: (message: Message) => void;
  messagesViewportRef: React.RefObject<HTMLDivElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  onScroll: () => void;
}

export function ChatMessageList({
  language,
  t,
  text,
  messages,
  loading,
  progressSteps,
  agentUnavailable,
  quickQuestions,
  onQuickQuestion,
  quickQuestionsDisabled,
  expandedThinking,
  onToggleThinking,
  copiedMessages,
  onCopyMessage,
  onDownloadMessage,
  messagesViewportRef,
  messagesEndRef,
  onScroll,
}: ChatMessageListProps): React.ReactElement {
  return (
    <ScrollArea
      className="relative z-10 flex-1"
      viewportRef={messagesViewportRef}
      onScroll={onScroll}
      viewportClassName="space-y-6 p-4 md:p-6"
      testId="chat-message-scroll"
    >
      {messages.length === 0 && !loading ? (
        <ChatEmptyMessages
          agentUnavailable={agentUnavailable}
          agentUnavailableTitle={t('chat.agentUnavailableTitle')}
          agentUnavailableDescription={t('chat.agentUnavailableDescription')}
          agentUnavailableAction={t('chat.agentUnavailableAction')}
          emptyTitle={t('chat.emptyTitle')}
          emptyDescription={t('chat.emptyDescription')}
          quickQuestions={quickQuestions}
          onQuickQuestion={onQuickQuestion}
          quickQuestionsDisabled={quickQuestionsDisabled}
        />
      ) : (
        messages.map((msg) => {
          const skillLabel = getMessageSkillLabel(msg);
          const displayContent = getChatMessageDisplayContent(msg, language);
          const isHypothetical = contentHasHypotheticalMarker(displayContent)
            || contentHasHypotheticalMarker(msg.content);
          const isExpanded = expandedThinking.has(msg.id);
          const toolSteps = (msg.thinkingSteps || []).filter((s) => s.type === 'tool_done');
          const totalDuration = toolSteps.reduce((sum, s) => sum + (s.duration || 0), 0);
          const thinkingSummary = t('chat.toolCalls', {
            count: toolSteps.length,
            duration: totalDuration.toFixed(1),
          });
          return (
            <div
              key={msg.id}
              className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
            >
              <div
                className={cn(
                  'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold shadow-sm transition-all',
                  msg.role === 'user' ? 'chat-avatar-user' : 'chat-avatar-ai',
                )}
              >
                {msg.role === 'user' ? 'U' : 'AI'}
              </div>
              <div
                className={cn(
                  'group/message min-w-0 w-fit max-w-[min(100%,48rem)] overflow-hidden px-5 py-3.5 transition-colors',
                  msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai',
                  isHypothetical && 'ring-1 ring-warning/40',
                )}
                data-what-if={isHypothetical ? 'true' : undefined}
              >
                {isHypothetical ? (
                  <div className="mb-2" data-testid="chat-what-if-result-badge">
                    <Badge
                      variant="warning"
                      className="shadow-none"
                      aria-label={t('chat.whatIf.resultBadge')}
                    >
                      {t('chat.whatIf.resultBadge')}
                    </Badge>
                  </div>
                ) : null}
                {msg.role === 'assistant' && skillLabel && (
                  <div className="mb-2">
                    <Badge
                      variant="info"
                      className="chat-skill-badge shadow-none"
                      aria-label={t('chat.skill', { name: skillLabel })}
                    >
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                {msg.role === 'assistant' && msg.thinkingSteps && msg.thinkingSteps.length > 0 ? (
                  <ChatThinkingToggle
                    isExpanded={isExpanded}
                    summary={thinkingSummary}
                    onToggle={() => onToggleThinking(msg.id)}
                    thinkingProcessLabel={t('chat.thinkingProcess')}
                  />
                ) : null}
                {msg.role === 'assistant' && isExpanded && msg.thinkingSteps ? (
                  <ChatThinkingDetails steps={msg.thinkingSteps} t={t} />
                ) : null}
                {msg.role === 'assistant' ? (
                  <div>
                    <div className="chat-prose">
                      <Markdown remarkPlugins={[remarkGfm]}>{displayContent}</Markdown>
                    </div>
                    <div className="chat-message-actions">
                      <span
                        data-slot="chat-message-action"
                        className="flex h-11 w-11 items-center justify-center"
                      >
                        <IconButton
                          size="compact"
                          tooltip={false}
                          onClick={() => onCopyMessage(msg.id, displayContent)}
                          aria-label={copiedMessages.has(msg.id) ? text.copied : text.copy}
                        >
                          {copiedMessages.has(msg.id) ? (
                            <Check className="text-success" aria-hidden="true" />
                          ) : (
                            <Copy aria-hidden="true" />
                          )}
                        </IconButton>
                      </span>
                      <span
                        data-slot="chat-message-action"
                        className="flex h-11 w-11 items-center justify-center"
                      >
                        <IconButton
                          size="compact"
                          tooltip={false}
                          onClick={() => onDownloadMessage(msg)}
                          aria-label={t('chat.exportMessage')}
                        >
                          <Download aria-hidden="true" />
                        </IconButton>
                      </span>
                    </div>
                  </div>
                ) : (
                  msg.content.split('\n').map((line, i) => (
                    <p key={i} className="mb-1 last:mb-0 leading-relaxed">
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
          <div className="min-w-50 max-w-[min(100%,48rem)] overflow-hidden rounded-2xl rounded-tl-sm border border-subtle bg-card/72 px-5 py-4">
            <div className="flex items-center gap-2.5 text-sm text-secondary-text">
              <div className="relative w-4 h-4 flex-shrink-0">
                <div className="absolute inset-0 rounded-full border-2 border-primary/20" />
                <div className="absolute inset-0 rounded-full border-2 border-primary border-t-transparent animate-spin" />
              </div>
              <span className="text-secondary-text">
                {getCurrentStageLabel(progressSteps, t)}
              </span>
            </div>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </ScrollArea>
  );
}
