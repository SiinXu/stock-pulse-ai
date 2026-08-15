// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Sparkles } from 'lucide-react';
import { Button, EmptyState } from '../common';
import { AgentUnavailableEmptyState } from './AgentUnavailableEmptyState';

type QuickQuestion = { label: string; skill: string };

type ChatEmptyMessagesProps = {
  agentUnavailable: boolean;
  agentUnavailableTitle: string;
  agentUnavailableDescription: string;
  agentUnavailableAction: string;
  agentUnavailableLocalAction: string;
  agentUnavailableAnalysisAction: string;
  emptyTitle: string;
  emptyDescription: string;
  quickQuestions: QuickQuestion[];
  onQuickQuestion: (question: QuickQuestion) => void;
  quickQuestionsDisabled: boolean;
};

const ChatEmptyMessages: React.FC<ChatEmptyMessagesProps> = ({
  agentUnavailable,
  agentUnavailableTitle,
  agentUnavailableDescription,
  agentUnavailableAction,
  agentUnavailableLocalAction,
  agentUnavailableAnalysisAction,
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
        localActionLabel={agentUnavailableLocalAction}
        analysisActionLabel={agentUnavailableAnalysisAction}
      />
    ) : (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        className="max-w-2xl"
        icon={(
          <Sparkles className="h-8 w-8" aria-hidden="true" />
        )}
        action={(
          <div className="flex max-w-lg flex-wrap justify-center gap-2">
            {quickQuestions.map((q, i) => (
              <Button
                key={i}
                variant="outline"
                size="comfortable"
                onClick={() => onQuickQuestion(q)}
                disabled={quickQuestionsDisabled}
              >
                {q.label}
              </Button>
            ))}
          </div>
        )}
      />
    )}
  </div>
);

export { ChatEmptyMessages };
