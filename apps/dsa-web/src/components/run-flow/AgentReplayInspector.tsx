import type React from 'react';
import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, CircleCheck, ShieldAlert, ShieldX } from 'lucide-react';
import { Badge, IconButton, InlineAlert } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { RunFlowSnapshot } from '../../types/runFlow';
import { buildAgentReplayModel, type AgentReplayIntegrityStatus } from './agentReplay';
import { formatDateTime } from './utils';

interface AgentReplayInspectorProps {
  snapshot: RunFlowSnapshot;
  onSelectNode?: (nodeId: string) => void;
}

const INTEGRITY_PRESENTATION: Record<AgentReplayIntegrityStatus, {
  variant: 'success' | 'warning' | 'danger';
  icon: typeof CircleCheck;
}> = {
  complete: { variant: 'success', icon: CircleCheck },
  warning: { variant: 'warning', icon: ShieldAlert },
  invalid: { variant: 'danger', icon: ShieldX },
};

const formatDetail = (value: Record<string, unknown>): string => JSON.stringify(value, null, 2);

const AgentReplayInspector: React.FC<AgentReplayInspectorProps> = ({ snapshot, onSelectNode }) => {
  const { language, t } = useUiLanguage();
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
  const integrityMessage = model.integrity.status === 'complete'
    ? t('runFlow.replay.integrity.completeMessage')
    : model.integrity.status === 'warning'
      ? t('runFlow.replay.integrity.warningMessage', {
        dropped: (model.integrity.capture?.droppedCount ?? 0) + model.integrity.gapCount,
      })
      : t('runFlow.replay.integrity.invalidMessage');

  return (
    <section className="border-y border-border py-3" data-testid="agent-replay-inspector">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="label-uppercase">{t('runFlow.replay.eyebrow')}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-foreground">{t('runFlow.replay.title')}</h3>
            <Badge variant={presentation.variant} data-testid="agent-replay-integrity-badge">
              <IntegrityIcon className="h-3.5 w-3.5" aria-hidden="true" />
              {t(`runFlow.replay.integrity.${model.integrity.status}`)}
            </Badge>
          </div>
        </div>
        {model.entries.length > 0 ? (
          <div className="flex items-center gap-2">
            <IconButton
              aria-label={t('runFlow.replay.previous')}
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
              {t('runFlow.replay.position', { current: activeCursor + 1, total: model.entries.length })}
            </span>
            <IconButton
              aria-label={t('runFlow.replay.next')}
              variant="outline"
              disabled={activeCursor >= model.entries.length - 1}
              onClick={() => moveCursor(activeCursor + 1)}
            >
              <ChevronRight aria-hidden="true" />
            </IconButton>
          </div>
        ) : null}
      </div>

      <InlineAlert
        className="mt-3"
        size="compact"
        variant={presentation.variant}
        title={t(`runFlow.replay.integrity.${model.integrity.status}`)}
        message={integrityMessage}
      />

      {!current ? (
        <div className="mt-3 border-t border-dashed border-border pt-3 text-sm text-secondary-text">
          {t('runFlow.replay.empty')}
        </div>
      ) : (
        <div className="mt-3 grid min-w-0 grid-cols-1 gap-3 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
          <dl className="grid min-w-0 grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-2 text-xs">
            <dt className="text-muted-text">{t('runFlow.replay.sequence')}</dt>
            <dd className="font-mono text-foreground">{current.sequence ?? t('runFlow.valueUnavailable')}</dd>
            <dt className="text-muted-text">{t('runFlow.replay.schema')}</dt>
            <dd className="font-mono text-foreground">{current.schemaVersion ?? '?'}</dd>
            <dt className="text-muted-text">{t('runFlow.replay.event')}</dt>
            <dd className="min-w-0 break-words font-mono text-foreground">{current.event.type}</dd>
            <dt className="text-muted-text">{t('runFlow.replay.status')}</dt>
            <dd className="min-w-0 break-words text-foreground">{current.status ?? current.event.severity}</dd>
            <dt className="text-muted-text">{t('runFlow.replay.time')}</dt>
            <dd className="min-w-0 break-words text-foreground">
              {formatDateTime(current.event.timestamp, language, t)}
            </dd>
            <dt className="text-muted-text">{t('runFlow.replay.trace')}</dt>
            <dd className="min-w-0 break-all font-mono text-foreground">{current.traceId ?? t('runFlow.valueUnavailable')}</dd>
            <dt className="text-muted-text">{t('runFlow.replay.span')}</dt>
            <dd className="min-w-0 break-all font-mono text-foreground">{current.spanId ?? t('runFlow.valueUnavailable')}</dd>
            <dt className="text-muted-text">{t('runFlow.replay.parentSpan')}</dt>
            <dd className="min-w-0 break-all font-mono text-foreground">{current.parentSpanId ?? t('runFlow.valueUnavailable')}</dd>
          </dl>

          <div className="min-w-0 space-y-3">
            <div>
              <p className="text-xs font-medium text-secondary-text">{t('runFlow.replay.attrs')}</p>
              <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all border-l-2 border-border pl-3 font-mono text-xs leading-5 text-foreground">
                {current.attrs ? formatDetail(current.attrs) : t('runFlow.valueUnavailable')}
              </pre>
            </div>
            {current.payload ? (
              <div>
                <p className="text-xs font-medium text-secondary-text">{t('runFlow.replay.payload')}</p>
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all border-l-2 border-border pl-3 font-mono text-xs leading-5 text-foreground">
                  {formatDetail(current.payload)}
                </pre>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
};

export default AgentReplayInspector;
