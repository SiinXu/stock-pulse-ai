// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo } from 'react';
import { ChevronRight, ListOrdered } from 'lucide-react';
import { Badge, StatusDot, Surface } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import type { RunFlowSnapshot, RunFlowStatus } from '../../types/runFlow';
import {
  buildProcessTimeline,
  type ProcessTimelineItem,
  type ProcessTimelineStatus,
  TRACE_EVENT_SOURCE,
} from './processTimelineModel';
import {
  formatDateTime,
  getRunFlowStatusLabel,
  RUN_FLOW_STATUS_STYLE,
  type RunFlowT,
} from './utils';

interface ProcessTimelineProps {
  snapshot: RunFlowSnapshot;
  onSelectNode?: (nodeId: string) => void;
  hideWhenEmpty?: boolean;
  className?: string;
}

const STATUS_TO_RUN_FLOW: Record<ProcessTimelineStatus, RunFlowStatus> = {
  running: 'running',
  success: 'success',
  failed: 'failed',
  warning: 'degraded',
  info: 'pending',
  unknown: 'unknown',
};

const kindLabelKey = (kind: ProcessTimelineItem['kind']): UiTextKey => {
  switch (kind) {
    case 'phase':
      return 'runFlow.nodeKind.analysis';
    case 'tool':
      return 'runFlow.nodeDetails.toolSequence';
    case 'model':
      return 'runFlow.nodeKind.model';
    case 'decision':
      return 'runFlow.replay.title';
    default:
      return 'runFlow.events.title';
  }
};

const FieldList: React.FC<{ fields: ProcessTimelineItem['what']; testId: string }> = ({
  fields,
  testId,
}) => {
  if (fields.length === 0) {
    return <p className="text-xs text-muted-text" data-testid={`${testId}-empty`}>—</p>;
  }
  return (
    <dl className="space-y-1" data-testid={testId}>
      {fields.map((field) => (
        <div key={field.key} className="grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)] gap-2 text-xs">
          <dt className="truncate font-mono text-muted-text">{field.key}</dt>
          <dd className="min-w-0 break-all font-mono text-secondary-text">{field.value}</dd>
        </div>
      ))}
    </dl>
  );
};

const TimelineRow: React.FC<{
  item: ProcessTimelineItem;
  language: Parameters<typeof formatDateTime>[1];
  t: RunFlowT;
  onSelectNode?: (nodeId: string) => void;
}> = ({ item, language, t, onSelectNode }) => {
  const runStatus = STATUS_TO_RUN_FLOW[item.status];
  const style = RUN_FLOW_STATUS_STYLE[runStatus] || RUN_FLOW_STATUS_STYLE.unknown;
  const hasLayers = item.what.length > 0 || item.why.length > 0;
  const statusLabel = getRunFlowStatusLabel(runStatus, t);
  const summary = (
    <div className="flex w-full min-w-0 flex-wrap items-center gap-2">
      <Badge variant="default" className="text-muted-text">{t(kindLabelKey(item.kind))}</Badge>
      <Badge variant={style.badge} className="gap-1.5 shadow-none">
        <StatusDot tone={style.tone} className="h-1.5 w-1.5" pulse={style.pulse} />
        {statusLabel}
      </Badge>
      {item.durationMs !== null ? (
        <Badge variant="default" className="text-muted-text" data-testid="process-timeline-duration">
          {t('runFlow.durationMs', { value: item.durationMs })}
        </Badge>
      ) : null}
      <span className="text-xs text-muted-text">{formatDateTime(item.timestamp, language, t)}</span>
      {item.step !== null ? (
        <Badge variant="default" className="font-mono text-muted-text">
          {item.step}
        </Badge>
      ) : null}
    </div>
  );
  const body = (
    <>
      <p className="mt-1.5 text-sm font-medium text-foreground">{item.title}</p>
      {item.message ? <p className="mt-1 text-xs leading-5 text-secondary-text">{item.message}</p> : null}
    </>
  );
  const nodeLink = item.nodeId && onSelectNode ? (
    <button type="button" className="mt-2 text-xs text-primary hover:underline" onClick={() => onSelectNode(item.nodeId!)}>
      {t('runFlow.events.openNode', { title: item.title })}
    </button>
  ) : null;

  if (!hasLayers) {
    return (
      <div className="rounded-lg border border-subtle bg-base/30 px-3 py-2" data-testid="process-timeline-item" data-kind={item.kind}>
        {summary}{body}{nodeLink}
      </div>
    );
  }

  return (
    <details className="group/timeline rounded-lg border border-subtle bg-base/30 px-3 py-2" data-testid="process-timeline-item" data-kind={item.kind}>
      <summary role="button" aria-label={`${item.title} · ${t('common.details')}`} className="flex cursor-pointer list-none items-start gap-2">
        <div className="min-w-0 flex-1">{summary}{body}</div>
        <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-muted-text/70 transition-transform group-open/timeline:rotate-90" aria-hidden="true" />
      </summary>
      <div className="mt-2 space-y-3 border-t border-border/60 pt-2">
        <div>
          <p className="label-uppercase">{t('runFlow.nodeDetails.column.name')}</p>
          <div className="mt-1.5"><FieldList fields={item.what} testId="process-timeline-what" /></div>
        </div>
        {item.why.length > 0 ? (
          <div>
            <p className="label-uppercase">{t('runFlow.nodeDetails.metadata')}</p>
            <div className="mt-1.5"><FieldList fields={item.why} testId="process-timeline-why" /></div>
          </div>
        ) : null}
        {nodeLink}
      </div>
    </details>
  );
};

export const ProcessTimeline: React.FC<ProcessTimelineProps> = ({
  snapshot, onSelectNode, hideWhenEmpty = false, className,
}) => {
  const { language, t } = useUiLanguage();
  const model = useMemo(() => buildProcessTimeline(snapshot, TRACE_EVENT_SOURCE), [snapshot]);

  if (!model.hasAgentEvents) {
    if (hideWhenEmpty) return null;
    return (
      <Surface level="interactive" padding="none" className={`p-3 ${className || ''}`} data-testid="process-timeline-empty">
        <div className="flex items-center gap-2">
          <ListOrdered className="h-4 w-4 text-muted-text" aria-hidden="true" />
          <p className="text-sm text-secondary-text">{t('runFlow.events.empty')}</p>
        </div>
      </Surface>
    );
  }

  return (
    <Surface level="interactive" padding="none" className={`p-3 ${className || ''}`} data-testid="process-timeline" data-trace-source={model.source}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="label-uppercase">{t('chat.thinkingProcess')}</p>
          <p className="mt-1 text-xs text-muted-text">{t('runFlow.events.count', { count: model.items.length })}</p>
        </div>
      </div>
      <ol className="relative mt-3 space-y-2 border-l border-border pl-4">
        {model.items.map((item) => (
          <li key={item.id} className="relative">
            <span className="absolute -left-[1.3rem] top-3 h-2.5 w-2.5 rounded-full border-2 border-background bg-primary/70" aria-hidden="true" />
            <TimelineRow item={item} language={language} t={t} onSelectNode={onSelectNode} />
          </li>
        ))}
      </ol>
    </Surface>
  );
};

export default ProcessTimeline;
