import type { AlphaSiftScreenResponse } from '../../api/alphasift';
import type { ParsedApiError } from '../../api/error';
import type { ScreeningRunParameters } from './screeningRunState';
import type { ScreeningText } from './screeningText';

export type ScreeningCapabilityState =
  | 'loading'
  | 'ready'
  | 'disabled'
  | 'adapter_unavailable'
  | 'status_error';

export type ScreeningAttemptState =
  | 'idle'
  | 'submitting'
  | 'running'
  | 'completed'
  | 'failed'
  | 'recoverable_poll_error';

export type ScreeningResultsEmptyKind =
  | 'loading'
  | 'never_run'
  | 'no_hits'
  | 'source_unavailable'
  | 'blocked';

export type ScreeningCapability = {
  state: ScreeningCapabilityState;
  error: ParsedApiError | null;
};

export type ScreeningSuccessfulRun = {
  result: AlphaSiftScreenResponse;
  parameters: ScreeningRunParameters;
};

export function isScreeningAttemptLoading(state: ScreeningAttemptState): boolean {
  return state === 'submitting' || state === 'running' || state === 'recoverable_poll_error';
}

export function getScreeningCapabilityLabel(
  state: ScreeningCapabilityState,
  text: ScreeningText,
): string {
  return {
    loading: text.statusLoading,
    ready: text.enabled,
    adapter_unavailable: text.statusUnavailable,
    disabled: text.disabled,
    status_error: text.callFailed,
  }[state];
}

export function getScreeningCapabilityState(args: {
  statusLoading: boolean;
  statusError?: ParsedApiError | null;
  enabled: boolean;
  available: boolean;
}): ScreeningCapabilityState {
  if (args.statusLoading) return 'loading';
  if (args.statusError) return 'status_error';
  if (!args.enabled) return 'disabled';
  if (!args.available) return 'adapter_unavailable';
  return 'ready';
}

export function isFullSourceUnavailable(
  meta: AlphaSiftScreenResponse | null | undefined,
): boolean {
  if (!meta) return false;
  const candidateCount = Array.isArray(meta.candidates)
    ? meta.candidates.length
    : Number(meta.candidateCount ?? 0);
  if (candidateCount > 0) return false;
  const sourceErrors = Array.isArray(meta.sourceErrors)
    ? meta.sourceErrors.filter(Boolean)
    : [];
  if (sourceErrors.length === 0) return false;
  return meta.snapshotCount == null || meta.snapshotCount === 0;
}

export function getScreeningResultsEmptyKind(args: {
  capability: ScreeningCapabilityState;
  loading: boolean;
  candidatesCount: number;
  screenMeta: AlphaSiftScreenResponse | null;
}): ScreeningResultsEmptyKind | null {
  if (args.candidatesCount > 0) return null;
  if (args.loading || args.capability === 'loading') return 'loading';
  if (args.capability !== 'ready') return 'blocked';
  if (!args.screenMeta) return 'never_run';
  return isFullSourceUnavailable(args.screenMeta) ? 'source_unavailable' : 'no_hits';
}

export function getScreeningRunStatusTitle(args: {
  text: ScreeningText;
  attemptState: ScreeningAttemptState;
  candidatesCount: number;
  screenMeta: AlphaSiftScreenResponse | null;
  attemptResult: AlphaSiftScreenResponse | null;
}): string {
  if (isScreeningAttemptLoading(args.attemptState)) return args.text.running;
  if (isFullSourceUnavailable(args.attemptResult) || args.attemptState === 'failed') {
    return args.text.callFailed;
  }
  if (args.candidatesCount > 0 || args.screenMeta) return args.text.completed;
  return args.text.waitingRun;
}
