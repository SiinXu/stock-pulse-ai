import React, { memo } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy, Download, Sparkles } from 'lucide-react';
import {
  Badge,
  IconButton,
  Progress,
  ScrollArea,
  StatusDot,
  Surface,
} from '../common';
import { ChatEmptyMessages } from './ChatEmptyMessages';
import {
  ChatThinkingDetails,
  ChatThinkingToggle,
} from './ChatThinkingDetails';
import {
  getCurrentStageLabel,
  getMessageSkillLabel,
  isProgressStepFailure,
} from './chatMessageMeta';
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

type ChatMessageBubbleProps = {
  message: Message;
  language: UiLanguage;
  t: Translate;
  text: { copied: string; copy: string };
  isExpanded: boolean;
  isCopied: boolean;
  onToggleThinking: (messageId: string) => void;
  onCopyMessage: (messageId: string, content: string) => void;
  onDownloadMessage: (message: Message) => void;
};

const ChatMessageBubble = memo(function ChatMessageBubble({
  message: msg,
  language,
  t,
  text,
  isExpanded,
  isCopied,
  onToggleThinking,
  onCopyMessage,
  onDownloadMessage,
}: ChatMessageBubbleProps) {
  const skillLabel = getMessageSkillLabel(msg);
  const displayContent = getChatMessageDisplayContent(msg, language);
  const isHypothetical = contentHasHypotheticalMarker(displayContent)
    || contentHasHypotheticalMarker(msg.content);
  const thinkingSteps = msg.thinkingSteps || [];
  const toolSteps = thinkingSteps.filter((s) => s.type === 'tool_done');
  const failureSteps = thinkingSteps.filter(isProgressStepFailure);
  const totalDuration = toolSteps.reduce((sum, s) => sum + (s.duration || 0), 0);
  const thinkingSummary = t('chat.toolCalls', {
    count: toolSteps.length,
    duration: totalDuration.toFixed(1),
  });

  return (
    <div
      className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
      data-chat-message-id={msg.id}
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
          'chat-message group/message relative min-w-0 w-fit max-w-[min(100%,48rem)] transition-colors',
          msg.role === 'user'
            ? 'overflow-hidden px-4 py-2.5 text-sm chat-bubble-user'
            : 'mb-8 overflow-visible px-5 py-3.5 chat-bubble-ai',
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
              <Sparkles className="h-3 w-3" aria-hidden="true" />
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
        {msg.role === 'assistant' && (isExpanded || failureSteps.length > 0) ? (
          <ChatThinkingDetails
            steps={isExpanded ? thinkingSteps : failureSteps}
            t={t}
            mode="history"
          />
        ) : null}
        {msg.role === 'assistant' ? (
          <div>
            <div className="chat-prose">
              <Markdown remarkPlugins={[remarkGfm]}>{displayContent}</Markdown>
            </div>
            <div className="chat-message-actions absolute left-0 top-full z-10 !mt-1">
              <span
                data-slot="chat-message-action"
                className="flex h-8 w-8 items-center justify-center"
              >
                <IconButton
                  size="compact"
                  tooltip={false}
                  onClick={() => onCopyMessage(msg.id, displayContent)}
                  aria-label={isCopied ? text.copied : text.copy}
                >
                  {isCopied ? (
                    <Check className="text-success" aria-hidden="true" />
                  ) : (
                    <Copy aria-hidden="true" />
                  )}
                </IconButton>
              </span>
              <span
                data-slot="chat-message-action"
                className="flex h-8 w-8 items-center justify-center"
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
});

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
  const currentStageLabel = getCurrentStageLabel(progressSteps, t);

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
          agentUnavailableLocalAction={t('firstRun.ctaLocal')}
          agentUnavailableAnalysisAction={t('layout.nav.analysis')}
          emptyTitle={t('chat.emptyTitle')}
          emptyDescription={t('chat.emptyDescription')}
          quickQuestions={quickQuestions}
          onQuickQuestion={onQuickQuestion}
          quickQuestionsDisabled={quickQuestionsDisabled}
        />
      ) : (
        messages.map((msg) => (
          <ChatMessageBubble
            key={msg.id}
            message={msg}
            language={language}
            t={t}
            text={text}
            isExpanded={expandedThinking.has(msg.id)}
            isCopied={copiedMessages.has(msg.id)}
            onToggleThinking={onToggleThinking}
            onCopyMessage={onCopyMessage}
            onDownloadMessage={onDownloadMessage}
          />
        ))
      )}

      {loading && (
        <div className="flex gap-4" data-testid="chat-live-progress">
          <div className="chat-avatar-ai flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold">
            AI
          </div>
          <Surface
            level="interactive"
            padding="sm"
            className="min-w-0 flex-1 max-w-[min(100%,48rem)]"
          >
            <div className="flex items-start gap-2.5">
              <StatusDot
                tone="info"
                pulse
                aria-label={t('runFlow.status.running')}
                className="mt-1 motion-reduce:animate-none"
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="min-w-0 flex-1 text-sm font-medium text-foreground">
                    {currentStageLabel}
                  </span>
                  <Badge variant="info" className="shrink-0 shadow-none">
                    {t('runFlow.status.running')}
                  </Badge>
                </div>
                <Progress
                  className="mt-2 h-1"
                  label={currentStageLabel}
                  valueText={t('runFlow.status.running')}
                  tone="primary"
                />
              </div>
            </div>
            {progressSteps.length > 0 ? (
              <div className="mt-3 border-t border-border/60 pt-3">
                <ChatThinkingDetails steps={progressSteps} t={t} mode="live" />
              </div>
            ) : null}
          </Surface>
        </div>
      )}

      <div ref={messagesEndRef} />
    </ScrollArea>
  );
}
