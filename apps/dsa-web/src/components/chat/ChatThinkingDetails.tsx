import React, { useId, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { Badge, StatusDot, Surface } from '../common';
import { cn } from '../../utils/cn';
import type { ProgressStep } from '../../stores/agentChatStore';
import type { UiTextKey } from '../../i18n/uiText';
import {
  getPipelineBudgetSkippedLabel,
  getStageDoneLabel,
  isProgressStepFailure,
  isStageDoneSuccessful,
} from './chatMessageMeta';

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;
type ChatTraceMode = 'live' | 'history';
type TraceTone = React.ComponentProps<typeof StatusDot>['tone'];
type TraceBadgeVariant = React.ComponentProps<typeof Badge>['variant'];

type TracePresentation = {
  tone: TraceTone;
  textClassName: string;
  badgeVariant?: TraceBadgeVariant;
  badgeKey?: UiTextKey;
};

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

function getStageDetail(step: ProgressStep): {
  stage?: string;
  status?: string;
  duration?: number;
  reason?: string;
  remaining?: number;
  timeout?: number;
  minimum?: number;
} | null {
  if (step.type !== 'stage_start' && step.type !== 'stage_done'
    && step.type !== 'pipeline_timeout' && step.type !== 'pipeline_budget_skipped') {
    return null;
  }
  const detail = {
    ...(typeof step.stage === 'string' ? { stage: step.stage } : {}),
    ...(typeof step.status === 'string' ? { status: step.status } : {}),
    ...(typeof step.duration === 'number' ? { duration: step.duration } : {}),
    ...(typeof step.reason === 'string' ? { reason: step.reason } : {}),
    ...(typeof step.remaining === 'number' ? { remaining: step.remaining } : {}),
    ...(typeof step.timeout === 'number' ? { timeout: step.timeout } : {}),
    ...(typeof step.minimum === 'number' ? { minimum: step.minimum } : {}),
  };
  return Object.keys(detail).length > 0 ? detail : null;
}

function getStepText(step: ProgressStep, t: Translate): string {
  if (step.type === 'thinking') {
    return step.message || t('chat.thinkingStep', { step: step.step || '' });
  }
  if (step.type === 'tool_start') return `${step.display_name || step.tool || ''}...`;
  if (step.type === 'tool_done') {
    const duration = typeof step.duration === 'number' ? ` (${step.duration}s)` : '';
    return `${step.display_name || step.tool || ''}${duration}`;
  }
  if (step.type === 'stage_start') {
    return step.message || `Starting ${step.stage || 'stage'}...`;
  }
  if (step.type === 'stage_done') return getStageDoneLabel(step);
  if (step.type === 'pipeline_timeout') {
    return step.message || `${step.stage || 'pipeline'} timed out`;
  }
  if (step.type === 'pipeline_budget_skipped') {
    return getPipelineBudgetSkippedLabel(step);
  }
  if (step.type === 'generating') return step.message || t('chat.generateAnalysis');
  return step.message || step.type;
}

function getTracePresentation(step: ProgressStep, isCurrent: boolean): TracePresentation {
  if (isProgressStepFailure(step)) {
    return {
      tone: 'danger',
      textClassName: 'border-danger/20 bg-danger/5 text-danger',
      badgeVariant: 'danger',
      badgeKey: step.type === 'pipeline_timeout'
        ? 'runFlow.status.timeout'
        : 'taskPanel.failed',
    };
  }
  if (step.type === 'pipeline_budget_skipped') {
    return {
      tone: 'warning',
      textClassName: 'border-warning/20 bg-warning/5 text-warning',
      badgeVariant: 'warning',
      badgeKey: 'runFlow.status.skipped',
    };
  }
  if (
    (step.type === 'tool_done' && step.success === true)
    || (step.type === 'stage_done' && isStageDoneSuccessful(step.status))
  ) {
    return {
      tone: 'success',
      textClassName: isCurrent
        ? 'border-success/30 bg-success/5 text-secondary-text'
        : 'border-success/15 text-secondary-text',
      badgeVariant: 'success',
      badgeKey: 'taskPanel.completed',
    };
  }
  if (isCurrent) {
    return {
      tone: 'info',
      textClassName: 'border-primary/20 bg-primary/5 text-foreground',
      badgeVariant: 'info',
      badgeKey: 'runFlow.status.running',
    };
  }
  return {
    tone: 'neutral',
    textClassName: 'border-transparent text-secondary-text',
  };
}

function getTraceRowIdentity(step: ProgressStep): string {
  return [
    step.type,
    step.tool ?? '',
    step.display_name ?? '',
    step.stage ?? '',
    step.step ?? '',
    step.success ?? '',
    step.duration ?? '',
    step.status ?? '',
    step.message ?? '',
    step.reason ?? '',
    step.turn_id ?? '',
    step.message_id ?? '',
  ].join('\u0001');
}

function getTraceRowKeys(steps: ProgressStep[]): string[] {
  const seen = new Map<string, number>();
  return steps.map((step) => {
    const base = getTraceRowIdentity(step);
    const next = (seen.get(base) ?? 0) + 1;
    seen.set(base, next);
    return `${base}\u0001${next}`;
  });
}

export function ChatThinkingDetails({
  steps,
  t,
  mode = 'history',
}: {
  steps: ProgressStep[];
  t: Translate;
  mode?: ChatTraceMode;
}): React.ReactElement {
  const detailIdPrefix = useId();
  const [expandedRows, setExpandedRows] = useState<Set<string>>(() => new Set());
  const rowKeys = getTraceRowKeys(steps);

  const toggleRow = (rowKey: string) => {
    setExpandedRows((current) => {
      const next = new Set(current);
      if (next.has(rowKey)) next.delete(rowKey);
      else next.add(rowKey);
      return next;
    });
  };

  return (
    <div className="space-y-1.5 animate-fade-in" data-trace-mode={mode}>
      {steps.map((step, index) => {
        const rowKey = rowKeys[index];
        const isCurrent = mode === 'live' && index === steps.length - 1;
        const presentation = getTracePresentation(step, isCurrent);
        const text = getStepText(step, t);
        const toolDetail = getToolDetail(step);
        const stageDetail = getStageDetail(step);
        const hasDetail = Boolean(toolDetail || stageDetail);
        const isExpanded = expandedRows.has(rowKey);
        const detailId = `${detailIdPrefix}-detail-${index}`;
        const rowClassName = cn(
          'rounded-md border px-2 py-1.5 text-xs transition-[background-color,border-color,color] motion-reduce:transition-none',
          presentation.textClassName,
        );
        const content = (
          <>
            <StatusDot
              tone={presentation.tone}
              pulse={isCurrent && !isProgressStepFailure(step)}
              className="motion-reduce:animate-none"
              aria-label={presentation.badgeKey ? t(presentation.badgeKey) : undefined}
            />
            <span className="min-w-0 flex-1 break-words leading-relaxed">{text}</span>
            {presentation.badgeKey && presentation.badgeVariant ? (
              <Badge
                variant={presentation.badgeVariant}
                className="shrink-0 shadow-none"
                data-trace-status={presentation.badgeVariant}
              >
                {t(presentation.badgeKey)}
              </Badge>
            ) : null}
          </>
        );

        return (
          <div
            key={rowKey}
            className={rowClassName}
            data-trace-step={step.type}
            data-current={isCurrent ? 'true' : undefined}
          >
            {hasDetail ? (
              <button
                type="button"
                className="control-hit-target flex w-full items-center gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
                aria-expanded={isExpanded}
                aria-controls={detailId}
                aria-label={`${text} · ${t('common.details')}`}
                onClick={() => toggleRow(rowKey)}
              >
                {content}
                <ChevronRight
                  className={cn(
                    'h-4 w-4 shrink-0 text-muted-text transition-transform motion-reduce:transition-none',
                    isExpanded && 'rotate-90',
                  )}
                  aria-hidden="true"
                />
              </button>
            ) : (
              <div className="flex min-h-8 items-center gap-2">{content}</div>
            )}

            {isExpanded && toolDetail ? (
              <Surface
                id={detailId}
                level="section"
                padding="sm"
                className="ml-5 mt-1.5 space-y-2 text-xs"
                data-testid="chat-tool-detail"
              >
                {toolDetail.arguments !== undefined ? (
                  <div>
                    <code className="text-muted-text">{t('chat.toolArguments')}</code>
                    <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-hover/60 p-3 text-secondary-text">
                      {JSON.stringify(toolDetail.arguments, null, 2)}
                    </pre>
                  </div>
                ) : null}
                {toolDetail.resultPreview ? (
                  <div>
                    <code className="text-muted-text">{t('chat.toolResultPreview')}</code>
                    <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-hover/60 p-3 text-secondary-text">
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
              </Surface>
            ) : null}

            {isExpanded && stageDetail ? (
              <pre
                id={detailId}
                className="ml-5 mt-1.5 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-hover/60 p-3 text-xs text-secondary-text"
                data-testid="chat-stage-detail"
              >
                {JSON.stringify(stageDetail, null, 2)}
              </pre>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
