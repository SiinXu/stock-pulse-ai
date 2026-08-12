import React from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '../../utils/cn';
import type { ProgressStep } from '../../stores/agentChatStore';
import type { UiTextKey } from '../../i18n/uiText';
import {
  getPipelineBudgetSkippedLabel,
  getStageDoneLabel,
  isStageDoneSuccessful,
} from './chatMessageMeta';

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

function getToolDetail(step: ProgressStep): {
  arguments?: unknown;
  resultPreview?: string;
  cached?: boolean;
  resultLength?: number;
} | null {
  if (step.type !== 'tool_done' || !step.meta) return null;
  const detail = {
    ...(step.meta.arguments !== undefined ? { arguments: step.meta.arguments } : {}),
    ...(typeof step.meta.result_preview === 'string'
      ? { resultPreview: step.meta.result_preview }
      : {}),
    ...(typeof step.meta.cached === 'boolean' ? { cached: step.meta.cached } : {}),
    ...(typeof step.meta.result_length === 'number'
      ? { resultLength: step.meta.result_length }
      : {}),
  };
  return Object.keys(detail).length > 0 ? detail : null;
}

export function ChatThinkingDetails({
  steps,
  t,
}: {
  steps: ProgressStep[];
  t: Translate;
}): React.ReactElement {
  return (
    <div className="mb-3 space-y-1.5 animate-fade-in">
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
        const toolDetail = getToolDetail(step);
        if (toolDetail) {
          return (
            <details key={idx} className="group/tool">
              <summary
                role="button"
                aria-label={`${text} · ${t('common.details')}`}
                className={cn('chat-progress-item cursor-pointer list-none', statusClass)}
              >
                <span className={cn('chat-progress-dot', iconClass)} />
                <span className="min-w-0 flex-1 leading-relaxed">{text}</span>
                <ChevronRight
                  className="h-4 w-4 shrink-0 text-muted-text/70 transition-transform group-open/tool:rotate-90"
                  aria-hidden="true"
                />
              </summary>
              <div className="ml-6 mt-1.5 space-y-2 border-l border-border/50 pl-3 pb-1 text-xs">
                {toolDetail.arguments !== undefined ? (
                  <div>
                    <code className="text-muted-text">{t('chat.toolArguments')}</code>
                    <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words text-secondary-text">
                      {JSON.stringify(toolDetail.arguments, null, 2)}
                    </pre>
                  </div>
                ) : null}
                {toolDetail.resultPreview ? (
                  <div>
                    <code className="text-muted-text">{t('chat.toolResultPreview')}</code>
                    <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-words text-secondary-text">
                      {toolDetail.resultPreview}
                    </pre>
                  </div>
                ) : null}
                <div className="flex flex-wrap gap-x-3 text-muted-text">
                  {toolDetail.cached !== undefined ? (
                    <code>{t('chat.toolCached')}: {String(toolDetail.cached)}</code>
                  ) : null}
                  {toolDetail.resultLength !== undefined ? (
                    <code>{t('chat.toolResultLength')}: {toolDetail.resultLength}</code>
                  ) : null}
                </div>
              </div>
            </details>
          );
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
