// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo } from 'react';
import { ListOrdered } from 'lucide-react';
import { Card, Collapsible } from '../common';
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

  // Progressive disclosure: stay hidden while loading/error/empty so single-pass
  // reports never flash a loading shell for a section that may not apply.
  if (recordId === undefined || isLoading || error || !model.hasAgentEvents || !snapshot) {
    return null;
  }

  return (
    <Card level="interactive" padding="none" className="text-left">
      <div data-testid="report-process-timeline">
        <Collapsible
          title={t('chat.thinkingProcess')}
          defaultOpen={false}
          className="rounded-none border-0 bg-transparent shadow-none hover:border-transparent"
          icon={(
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <ListOrdered className="h-4 w-4" aria-hidden="true" />
            </span>
          )}
          trailing={(
            <span className="text-xs text-muted-text">
              {t('runFlow.events.count', { count: model.items.length })}
            </span>
          )}
        >
          <div className="space-y-3">
            <ProcessTimeline snapshot={snapshot} hideWhenEmpty />
            {onOpenRunFlow ? (
              <button type="button" className="text-xs text-primary hover:underline" onClick={() => onOpenRunFlow(recordId)}>
                {t('runFlow.open')}
              </button>
            ) : null}
          </div>
        </Collapsible>
      </div>
    </Card>
  );
};

export default ReportProcessTimeline;
