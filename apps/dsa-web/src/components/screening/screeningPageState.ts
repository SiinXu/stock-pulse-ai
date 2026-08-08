import type { AlphaSiftScreenResponse } from '../../api/alphasift';

export type ScreeningCapabilityState = 'loading' | 'disabled' | 'unavailable' | 'ready';
export type ScreeningResultsEmptyKind = 'never_run' | 'no_hits' | 'source_unavailable' | 'blocked';

export function getScreeningCapabilityState(args: {
  statusLoading: boolean; enabled: boolean; available: boolean;
}): ScreeningCapabilityState {
  if (args.statusLoading) return 'loading';
  if (!args.enabled) return 'disabled';
  if (!args.available) return 'unavailable';
  return 'ready';
}

export function isFullSourceUnavailable(meta: AlphaSiftScreenResponse | null | undefined): boolean {
  if (!meta) return false;
  const candidateCount = Array.isArray(meta.candidates) ? meta.candidates.length : Number(meta.candidateCount ?? 0);
  if (candidateCount > 0) return false;
  const sourceErrors = Array.isArray(meta.sourceErrors) ? meta.sourceErrors.filter(Boolean) : [];
  if (sourceErrors.length === 0) return false;
  const snapshot = meta.snapshotCount;
  return snapshot == null || snapshot === 0;
}

export function getScreeningResultsEmptyKind(args: {
  capability: ScreeningCapabilityState; loading: boolean; candidatesCount: number;
  screenMeta: AlphaSiftScreenResponse | null;
}): ScreeningResultsEmptyKind | null {
  if (args.candidatesCount > 0 || args.loading) return null;
  if (args.capability === 'loading') return null;
  if (args.capability === 'disabled' || args.capability === 'unavailable') return 'blocked';
  if (args.screenMeta) {
    if (isFullSourceUnavailable(args.screenMeta)) return 'source_unavailable';
    return 'no_hits';
  }
  return 'never_run';
}

export function isPartialDegradedScreen(args: {
  screenMeta: AlphaSiftScreenResponse | null; candidatesCount: number;
  alertMessages: string[]; llmDegraded: boolean;
}): boolean {
  if (!args.screenMeta || args.candidatesCount <= 0) return false;
  return args.llmDegraded || args.alertMessages.length > 0;
}
