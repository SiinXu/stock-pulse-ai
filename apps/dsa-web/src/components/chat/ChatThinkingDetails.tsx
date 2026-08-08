import React from 'react';
import { cn } from '../../utils/cn';
import type { ProgressStep } from '../../stores/agentChatStore';
import type { UiTextKey } from '../../i18n/uiText';
import {
  getPipelineBudgetSkippedLabel,
  getStageDoneLabel,
  isStageDoneSuccessful,
} from './chatMessageMeta';

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

export function ChatThinkingDetails({
  steps,
  t,
}: {
  steps: ProgressStep[];
  t: Translate;
}): React.ReactElement {
  return (
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
          <div key={idx} className={cn('chat-progress-item', statusClass)}>
            <span className={cn('chat-progress-dot', iconClass)} />
            <span className="leading-relaxed">{text}</span>
          </div>
        );
      })}
    </div>
  );
}

export function ChatThinkingToggle({
  isExpanded,
  summary,
  onToggle,
  thinkingProcessLabel,
}: {
  isExpanded: boolean;
  summary: string;
  onToggle: () => void;
  thinkingProcessLabel: string;
}): React.ReactElement {
  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-2 text-xs text-muted-text hover:text-secondary-text transition-colors mb-2 w-full text-left"
    >
      <svg
        className={`w-3 h-3 transition-transform flex-shrink-0 ${isExpanded ? 'rotate-90' : ''}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
      </svg>
      <span className="flex items-center gap-1.5">
        <span className="opacity-60">{thinkingProcessLabel}</span>
        <span className="text-muted-text/50">·</span>
        <span className="opacity-50">{summary}</span>
      </span>
    </button>
  );
}
