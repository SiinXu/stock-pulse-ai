// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo } from 'react';
import { ChevronDown, ListOrdered } from 'lucide-react';
import { Card, Spinner } from '../common';
import { useRunFlowSnapshot } from '../../hooks/useRunFlowSnapshot';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { ProcessTimeline } from '../run-flow/ProcessTimeline';
import { buildProcessTimeline, TRACE_EVENT_SOURCE } from '../run-flow/processTimelineModel';

interface ReportProcessTimelineProps {
  recordId?: number;
  onOpenRunFlow?: (recordId: number) => void;
}

/** Collapsible analysis-process section on report pages (real run-flow agent events only). */
export const ReportProcessTimeline: React.FC<ReportProcessTimelineProps> = ({
  recordId,
  onOpenRunFlow,
}) => {
  const { t } = useUiLanguage();
  const source = useMemo(
    () => (recordId !== undefined ? { type: 'history' as const, recordId } : null),
    [recordId],
  );
  const { snapshot, isLoading, error } = useRunFlowSnapshot({
    source,
    enabled: recordId !== undefined,
  });
  const model = useMemo(
    () => buildProcessTimeline(snapshot, TRACE_EVENT_SOURCE),
    [snapshot],
  );

  if (recordId === undefined) return null;
  if (isLoading && !snapshot) {
    return (
      <Card variant="bordered" padding="none" className="text-left" data-testid="report-process-loading">
        <div className="flex min-h-11 items-center gap-3 px-4 py-3">
          <Spinner size="sm" label={t('runFlow.loadingTitle')} className="h-3.5 w-3.5" />
          <span className="text-sm text-secondary-text">{t('runFlow.loadingTitle')}</span>
        </div>
      </Card>
    );
  }
  if (error && !snapshot) return null;
  if (!model.hasAgentEvents) return null;

  return (
    <Card variant="bordered" padding="none" className="text-left">
      <details data-testid="report-process-timeline" className="group">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <ListOrdered className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="label-uppercase">{t('runFlow.eyebrow')}</span>
              <span className="mt-0.5 block truncate text-base font-semibold text-foreground">
                {t('chat.thinkingProcess')}
              </span>
            </span>
          </div>
          <span className="flex shrink-0 items-center gap-2">
            <span className="text-xs text-muted-text">
              {t('runFlow.events.count', { count: model.items.length })}
            </span>
            <ChevronDown className="h-4 w-4 text-muted-text transition-transform group-open:rotate-180" aria-hidden="true" />
          </span>
        </summary>
        <div className="space-y-3 border-t border-border px-4 pb-4 pt-3">
          {snapshot ? <ProcessTimeline snapshot={snapshot} hideWhenEmpty /> : null}
          {onOpenRunFlow ? (
            <button type="button" className="text-xs text-primary hover:underline" onClick={() => onOpenRunFlow(recordId)}>
              {t('runFlow.open')}
            </button>
          ) : null}
        </div>
      </details>
    </Card>
  );
};

export default ReportProcessTimeline;
