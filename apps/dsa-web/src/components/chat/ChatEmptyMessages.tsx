// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { EmptyState } from '../common';
import { AgentUnavailableEmptyState } from './AgentUnavailableEmptyState';

type QuickQuestion = { label: string };

type ChatEmptyMessagesProps = {
  agentUnavailable: boolean;
  agentUnavailableTitle: string;
  agentUnavailableDescription: string;
  agentUnavailableAction: string;
  emptyTitle: string;
  emptyDescription: string;
  quickQuestions: QuickQuestion[];
  onQuickQuestion: (question: QuickQuestion) => void;
  quickQuestionsDisabled: boolean;
};

export const ChatEmptyMessages: React.FC<ChatEmptyMessagesProps> = ({
  agentUnavailable,
  agentUnavailableTitle,
  agentUnavailableDescription,
  agentUnavailableAction,
  emptyTitle,
  emptyDescription,
  quickQuestions,
  onQuickQuestion,
  quickQuestionsDisabled,
}) => (
  <div className="flex h-full items-center justify-center">
    {agentUnavailable ? (
      <AgentUnavailableEmptyState
        title={agentUnavailableTitle}
        description={agentUnavailableDescription}
        actionLabel={agentUnavailableAction}
      />
    ) : (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        className="max-w-2xl"
        icon={(
          <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                onClick={() => onQuickQuestion(q)}
                disabled={quickQuestionsDisabled}
                className="quick-question-btn"
              >
                {q.label}
              </button>
            ))}
          </div>
        )}
      />
    )}
  </div>
);
