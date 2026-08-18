import React, { memo, useCallback, useId, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { Badge, StatusDot, Surface } from '../common';
import { cn } from '../../utils/cn';
import type { ProgressStep } from '../../stores/agentChatStore';
import type { UiTextKey } from '../../i18n/uiText';
import {
  advanceTraceRowModels,
  createTraceRowCache,
  type StageDetail,
  type ToolDetail,
  type TracePresentation,
  type TraceRowCache,
  type TraceRowModel,
  type TraceTranslate,
} from './chatThinkingTrace';

type ChatTraceMode = 'live' | 'history';

type TraceView = {
  steps: ProgressStep[];
  t: TraceTranslate;
  rows: TraceRowModel[];
  cache: TraceRowCache;
};

function createTraceView(steps: ProgressStep[], t: TraceTranslate): TraceView {
  const cache = createTraceRowCache();
  return {
    steps,
    t,
    rows: advanceTraceRowModels(cache, steps, t),
    cache,
  };
}

type ChatTraceRowProps = {
  rowKey: string;
  stepType: string;
  isCurrent: boolean;
  isExpanded: boolean;
  isFailure: boolean;
  presentation: TracePresentation;
  text: string;
  toolDetail: ToolDetail | null;
  stageDetail: StageDetail | null;
  detailId: string;
  t: TraceTranslate;
  onToggle: (rowKey: string) => void;
};

const ChatTraceRow = memo(function ChatTraceRow({
  rowKey,
  stepType,
  isCurrent,
  isExpanded,
  isFailure,
  presentation,
  text,
  toolDetail,
  stageDetail,
  detailId,
  t,
  onToggle,
}: ChatTraceRowProps) {
  const hasDetail = Boolean(toolDetail || stageDetail);
  const rowClassName = cn(
    'rounded-md border px-2 py-1.5 text-xs transition-[background-color,border-color,color] motion-reduce:transition-none',
    presentation.textClassName,
  );
  const content = (
    <>
      <StatusDot
        tone={presentation.tone}
        pulse={isCurrent && !isFailure}
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
      className={rowClassName}
      data-trace-step={stepType}
      data-current={isCurrent ? 'true' : undefined}
    >
      {hasDetail ? (
        <button
          type="button"
          className="control-hit-target flex w-full items-center gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
          aria-expanded={isExpanded}
          aria-controls={detailId}
          aria-label={`${text} · ${t('common.details')}`}
          onClick={() => onToggle(rowKey)}
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
});

export function ChatThinkingDetails({
  steps,
  t,
  mode = 'history',
}: {
  steps: ProgressStep[];
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  mode?: ChatTraceMode;
}): React.ReactElement {
  const detailIdPrefix = useId();
  const [expandedRows, setExpandedRows] = useState<Set<string>>(() => new Set());
  const [traceModel, setTraceModel] = useState(() => createTraceView(steps, t));
  let rows = traceModel.rows;
  if (traceModel.steps !== steps || traceModel.t !== t) {
    rows = advanceTraceRowModels(traceModel.cache, steps, t);
    setTraceModel({ steps, t, rows, cache: traceModel.cache });
  }

  const toggleRow = useCallback((rowKey: string) => {
    setExpandedRows((current) => {
      const next = new Set(current);
      if (next.has(rowKey)) next.delete(rowKey);
      else next.add(rowKey);
      return next;
    });
  }, []);

  return (
    <div className="space-y-1.5 animate-fade-in" data-trace-mode={mode}>
      {rows.map((row, index) => {
        const isCurrent = mode === 'live' && index === rows.length - 1;
        return (
          <ChatTraceRow
            key={row.rowKey}
            rowKey={row.rowKey}
            stepType={row.step.type}
            isCurrent={isCurrent}
            isExpanded={expandedRows.has(row.rowKey)}
            isFailure={row.isFailure}
            presentation={isCurrent ? row.presentationCurrent : row.presentationIdle}
            text={row.text}
            toolDetail={row.toolDetail}
            stageDetail={row.stageDetail}
            detailId={`${detailIdPrefix}-detail-${index}`}
            t={t}
            onToggle={toggleRow}
          />
        );
      })}
    </div>
  );
}
