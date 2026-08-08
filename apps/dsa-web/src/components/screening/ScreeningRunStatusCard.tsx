import type React from 'react';
import { CheckCircle2, CircleAlert } from 'lucide-react';
import type { AlphaSiftScreenResponse } from '../../api/alphasift';
import { formatUiText } from '../../i18n/uiText';
import { Surface } from '../common';
import { formatPercent } from './screeningCandidateModel';
import type { ScreeningCapabilityState } from './screeningPageState';
import type { ScreeningText } from './screeningText';

export type ScreeningRunStatusCardProps = {
  text: ScreeningText; loading: boolean; capability: ScreeningCapabilityState; candidatesCount: number;
  taskMessage: string; taskProgress: number; displayedStrategy: string; marketLabel: string;
  activeTaskId: string | null; screenMeta: AlphaSiftScreenResponse | null;
};

function resolveStatusTitle(args: { text: ScreeningText; loading: boolean; capability: ScreeningCapabilityState; candidatesCount: number; hasScreenMeta: boolean; }): string {
  if (args.loading) return args.text.running;
  if (args.candidatesCount > 0) return args.text.completed;
  if (args.capability !== 'ready') return args.text.waitingRun;
  if (args.hasScreenMeta) return args.text.completed;
  return args.text.waitingRun;
}

export const ScreeningRunStatusCard: React.FC<ScreeningRunStatusCardProps> = ({
  text, loading, capability, candidatesCount, taskMessage, taskProgress, displayedStrategy, marketLabel, activeTaskId, screenMeta,
}) => {
  const isReady = capability === 'ready';
  const title = resolveStatusTitle({ text, loading, capability, candidatesCount, hasScreenMeta: Boolean(screenMeta) });
  return (
    <Surface as="section" level="interactive" padding="md">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className={`grid h-7 w-7 place-items-center rounded-full ${candidatesCount > 0 ? 'text-success' : isReady ? 'text-primary' : 'text-warning'}`}>
            {candidatesCount > 0 ? <CheckCircle2 className="h-5 w-5" /> : <CircleAlert className="h-5 w-5" />}
          </span>
          <div>
            <h2 className="text-sm font-semibold text-foreground">{title}</h2>
            <p className="mt-1 text-xs text-secondary-text">{loading ? `${taskMessage || text.runningTask} · ${taskProgress}%` : formatUiText(text.currentStrategy, { strategy: displayedStrategy, market: marketLabel })}</p>
          </div>
        </div>
        <div className="grid gap-1 text-xs text-secondary-text sm:text-right">
          <span>{formatUiText(text.task, { id: activeTaskId ? activeTaskId.slice(0, 12) : '-' })}</span>
          <span>{formatUiText(text.runId, { id: screenMeta?.runId || '-' })}</span>
          <span>{formatUiText(text.taskStats, { snapshot: screenMeta?.snapshotCount ?? '-', filtered: screenMeta?.afterFilterCount ?? '-', candidates: screenMeta?.candidateCount ?? candidatesCount })}</span>
          <span>{text.llm}: {screenMeta?.llmRanked ? text.reranked : screenMeta ? text.notReranked : '-'}{screenMeta?.llmCoverage != null ? ` · ${formatUiText(text.coverage, { value: formatPercent(screenMeta.llmCoverage) })}` : ''}</span>
          <span>{formatUiText(text.dsaEnrichment, { enriched: screenMeta?.dsaEnrichment?.enrichedCount ?? '-', requested: screenMeta?.dsaEnrichment?.requestedCount ?? '-' })}</span>
        </div>
      </div>
    </Surface>
  );
};
