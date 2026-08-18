import type { ProgressStep } from '../../stores/agentChatStore';
import type { UiTextKey } from '../../i18n/uiText';
import {
  getPipelineBudgetSkippedLabel,
  getStageDoneLabel,
  isProgressStepFailure,
  isStageDoneSuccessful,
} from './chatMessageMeta';

export type TraceTranslate = (
  key: UiTextKey,
  params?: Record<string, string | number>,
) => string;

export type TraceTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';
export type TraceBadgeVariant = 'info' | 'success' | 'warning' | 'danger';

export type TracePresentation = {
  tone: TraceTone;
  textClassName: string;
  badgeVariant?: TraceBadgeVariant;
  badgeKey?: UiTextKey;
};

export type ToolDetail = {
  arguments?: unknown;
  resultPreview?: string;
  cached?: boolean;
  resultLength?: number;
};

export type StageDetail = {
  stage?: string;
  status?: string;
  duration?: number;
  reason?: string;
  remaining?: number;
  timeout?: number;
  minimum?: number;
};

export type DerivedTraceRow = {
  identity: string;
  text: string;
  toolDetail: ToolDetail | null;
  stageDetail: StageDetail | null;
  isFailure: boolean;
  presentationIdle: TracePresentation;
  presentationCurrent: TracePresentation;
};

export type TraceRowModel = DerivedTraceRow & {
  step: ProgressStep;
  rowKey: string;
};

export type ChatThinkingTraceStats = {
  identity: number;
  presentation: number;
  stepText: number;
  toolDetail: number;
  stageDetail: number;
  derive: number;
  rowRenders: number;
};

export const chatThinkingTraceStats: ChatThinkingTraceStats = {
  identity: 0,
  presentation: 0,
  stepText: 0,
  toolDetail: 0,
  stageDetail: 0,
  derive: 0,
  rowRenders: 0,
};

export function resetChatThinkingTraceStats(): void {
  chatThinkingTraceStats.identity = 0;
  chatThinkingTraceStats.presentation = 0;
  chatThinkingTraceStats.stepText = 0;
  chatThinkingTraceStats.toolDetail = 0;
  chatThinkingTraceStats.stageDetail = 0;
  chatThinkingTraceStats.derive = 0;
  chatThinkingTraceStats.rowRenders = 0;
}

export function snapshotChatThinkingTraceStats(): ChatThinkingTraceStats {
  return { ...chatThinkingTraceStats };
}

export function getToolDetail(step: ProgressStep): ToolDetail | null {
  chatThinkingTraceStats.toolDetail += 1;
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

export function getStageDetail(step: ProgressStep): StageDetail | null {
  chatThinkingTraceStats.stageDetail += 1;
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

export function getStepText(step: ProgressStep, t: TraceTranslate): string {
  chatThinkingTraceStats.stepText += 1;
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

export function getTracePresentation(
  step: ProgressStep,
  isCurrent: boolean,
): TracePresentation {
  chatThinkingTraceStats.presentation += 1;
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

export function getTraceRowIdentity(step: ProgressStep): string {
  chatThinkingTraceStats.identity += 1;
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

export function getTraceRowKeys(steps: ProgressStep[]): string[] {
  const seen = new Map<string, number>();
  return steps.map((step) => {
    const base = getTraceRowIdentity(step);
    const next = (seen.get(base) ?? 0) + 1;
    seen.set(base, next);
    return `${base}\u0001${next}`;
  });
}

export function deriveTraceRowStatic(
  step: ProgressStep,
  t: TraceTranslate,
): DerivedTraceRow {
  chatThinkingTraceStats.derive += 1;
  return {
    identity: getTraceRowIdentity(step),
    text: getStepText(step, t),
    toolDetail: getToolDetail(step),
    stageDetail: getStageDetail(step),
    isFailure: isProgressStepFailure(step),
    presentationIdle: getTracePresentation(step, false),
    presentationCurrent: getTracePresentation(step, true),
  };
}

type CachedDerivation = {
  t: TraceTranslate;
  model: DerivedTraceRow;
};

export type TraceRowCache = {
  t: TraceTranslate | null;
  rows: TraceRowModel[];
  seen: Map<string, number>;
  derived: WeakMap<ProgressStep, CachedDerivation>;
};

export function createTraceRowCache(): TraceRowCache {
  return {
    t: null,
    rows: [],
    seen: new Map(),
    derived: new WeakMap(),
  };
}

function getOrDeriveRow(
  cache: TraceRowCache,
  step: ProgressStep,
  t: TraceTranslate,
): DerivedTraceRow {
  const cached = cache.derived.get(step);
  if (cached && cached.t === t) return cached.model;
  const model = deriveTraceRowStatic(step, t);
  cache.derived.set(step, { t, model });
  return model;
}

function appendCachedRow(
  cache: TraceRowCache,
  step: ProgressStep,
  t: TraceTranslate,
): void {
  const model = getOrDeriveRow(cache, step, t);
  const occurrence = (cache.seen.get(model.identity) ?? 0) + 1;
  cache.seen.set(model.identity, occurrence);
  cache.rows.push({
    step,
    rowKey: `${model.identity}\u0001${occurrence}`,
    ...model,
  });
}

function commonPrefixLength(rows: TraceRowModel[], nextSteps: ProgressStep[]): number {
  const limit = Math.min(rows.length, nextSteps.length);
  let prefix = 0;
  while (prefix < limit && rows[prefix].step === nextSteps[prefix]) {
    prefix += 1;
  }
  return prefix;
}

/**
 * Advance a live/history trace model. Appending steps that keep the existing
 * prefix object-identical is O(appended). Structural changes (prepend, replace,
 * language switch) rebuild from the first changed index.
 */
export function advanceTraceRowModels(
  cache: TraceRowCache,
  nextSteps: ProgressStep[],
  t: TraceTranslate,
): TraceRowModel[] {
  if (cache.t !== t) {
    cache.t = t;
    cache.rows = [];
    cache.seen = new Map();
  }

  const prefix = commonPrefixLength(cache.rows, nextSteps);

  if (prefix === cache.rows.length && prefix === nextSteps.length) {
    return cache.rows;
  }

  if (prefix === cache.rows.length && nextSteps.length > prefix) {
    for (let index = prefix; index < nextSteps.length; index += 1) {
      appendCachedRow(cache, nextSteps[index], t);
    }
    return cache.rows;
  }

  cache.rows = cache.rows.slice(0, prefix);
  cache.seen = new Map();
  for (const row of cache.rows) {
    cache.seen.set(row.identity, (cache.seen.get(row.identity) ?? 0) + 1);
  }
  for (let index = prefix; index < nextSteps.length; index += 1) {
    appendCachedRow(cache, nextSteps[index], t);
  }
  return cache.rows;
}
