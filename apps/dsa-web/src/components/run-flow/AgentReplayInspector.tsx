import type React from 'react';
import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, CircleCheck, ShieldAlert, ShieldX } from 'lucide-react';
import { Badge, IconButton } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { RunFlowSnapshot } from '../../types/runFlow';
import { buildAgentReplayModel, type AgentReplayIntegrityStatus } from './agentReplay';

interface AgentReplayInspectorProps {
  snapshot: RunFlowSnapshot;
  onSelectNode?: (nodeId: string) => void;
}

const INTEGRITY_PRESENTATION: Record<AgentReplayIntegrityStatus, {
  variant: 'success' | 'warning' | 'danger';
  icon: typeof CircleCheck;
  label: 'common.complete' | 'common.partial' | 'common.invalid';
}> = {
  complete: { variant: 'success', icon: CircleCheck, label: 'common.complete' },
  warning: { variant: 'warning', icon: ShieldAlert, label: 'common.partial' },
  invalid: { variant: 'danger', icon: ShieldX, label: 'common.invalid' },
};

const formatDetail = (value: Record<string, unknown>): string => JSON.stringify(value, null, 2);

const AgentReplayInspector: React.FC<AgentReplayInspectorProps> = ({ snapshot, onSelectNode }) => {
  const { t } = useUiLanguage();
  const model = useMemo(
    () => buildAgentReplayModel(snapshot.events, snapshot.traceId),
    [snapshot.events, snapshot.traceId],
  );
  const [cursor, setCursor] = useState(0);

  const activeCursor = Math.min(cursor, Math.max(0, model.entries.length - 1));
  const current = model.entries[activeCursor] ?? null;
  const presentation = INTEGRITY_PRESENTATION[model.integrity.status];
  const IntegrityIcon = presentation.icon;
  const moveCursor = (nextCursor: number) => {
    const bounded = Math.max(0, Math.min(nextCursor, model.entries.length - 1));
    setCursor(bounded);
    const nodeId = model.entries[bounded]?.event.nodeId;
    if (nodeId) onSelectNode?.(nodeId);
  };
  const detail = current ? {
    sequence: current.sequence,
    schema_version: current.schemaVersion,
    event_type: current.event.type,
    status: current.status ?? current.event.severity,
    timestamp: current.event.timestamp,
    trace_id: current.traceId,
    span_id: current.spanId,
    parent_span_id: current.parentSpanId,
    ...(current.attrs ? { attrs: current.attrs } : {}),
    ...(current.payload ? { payload: current.payload } : {}),
    integrity: {
      status: model.integrity.status,
      gap_count: model.integrity.gapCount,
      duplicate_count: model.integrity.duplicateCount,
      missing_sequence_count: model.integrity.missingSequenceCount,
      invalid_version_count: model.integrity.invalidVersionCount,
      trace_mismatch_count: model.integrity.traceMismatchCount,
      invalid_detail_count: model.integrity.invalidDetailCount,
      capture_mismatch: model.integrity.captureMismatch,
      capture: model.integrity.capture ? {
        original_count: model.integrity.capture.originalCount,
        returned_count: model.integrity.capture.returnedCount,
        dropped_count: model.integrity.capture.droppedCount,
        truncated: model.integrity.capture.truncated,
      } : null,
    },
  } : null;

  return (
    <section className="border-y border-border py-3" data-testid="agent-replay-inspector">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-foreground">{t('runFlow.replay.title')}</h3>
            <Badge variant={presentation.variant} data-testid="agent-replay-integrity-badge">
              <IntegrityIcon className="h-3.5 w-3.5" aria-hidden="true" />
              {t(presentation.label)}
            </Badge>
          </div>
        </div>
        {model.entries.length > 0 ? (
          <div className="flex items-center gap-2">
            <IconButton
              aria-label={t('common.prevPage')}
              variant="outline"
              disabled={activeCursor === 0}
              onClick={() => moveCursor(activeCursor - 1)}
            >
              <ChevronLeft aria-hidden="true" />
            </IconButton>
            <span
              className="min-w-24 text-center font-mono text-xs text-secondary-text"
              aria-live="polite"
              data-testid="agent-replay-position"
            >
              {activeCursor + 1} / {model.entries.length}
            </span>
            <IconButton
              aria-label={t('common.nextPage')}
              variant="outline"
              disabled={activeCursor >= model.entries.length - 1}
              onClick={() => moveCursor(activeCursor + 1)}
            >
              <ChevronRight aria-hidden="true" />
            </IconButton>
          </div>
        ) : null}
      </div>

      {!current ? (
        <div className="mt-3 border-t border-dashed border-border pt-3 text-sm text-secondary-text">
          {t('runFlow.events.empty')}
        </div>
      ) : (
        <div className="mt-3 min-w-0">
          <p className="text-xs font-medium text-secondary-text">{t('runFlow.nodeDetails.metadata')}</p>
          <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap break-all border-l-2 border-border pl-3 font-mono text-xs leading-5 text-foreground">
            {formatDetail(detail ?? {})}
          </pre>
        </div>
      )}
    </section>
  );
};

export default AgentReplayInspector;
