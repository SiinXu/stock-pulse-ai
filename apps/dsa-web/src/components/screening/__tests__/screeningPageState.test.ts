import { describe, expect, it } from 'vitest';
import {
  getScreeningCapabilityState,
  getScreeningResultsEmptyKind,
  isFullSourceUnavailable,
  isPartialDegradedScreen,
} from '../screeningPageState';

describe('screeningPageState', () => {
  it('maps capability from status flags', () => {
    expect(getScreeningCapabilityState({ statusLoading: true, enabled: false, available: false })).toBe('loading');
    expect(getScreeningCapabilityState({ statusLoading: false, enabled: false, available: false })).toBe('disabled');
    expect(getScreeningCapabilityState({ statusLoading: false, enabled: true, available: false })).toBe('unavailable');
    expect(getScreeningCapabilityState({ statusLoading: false, enabled: true, available: true })).toBe('ready');
  });

  it('distinguishes empty kinds', () => {
    expect(getScreeningResultsEmptyKind({ capability: 'ready', loading: false, candidatesCount: 0, screenMeta: null })).toBe('never_run');
    expect(getScreeningResultsEmptyKind({ capability: 'ready', loading: false, candidatesCount: 0, screenMeta: { enabled: true, candidates: [], candidateCount: 0, snapshotCount: 80, afterFilterCount: 0 } })).toBe('no_hits');
    expect(getScreeningResultsEmptyKind({ capability: 'ready', loading: false, candidatesCount: 0, screenMeta: { enabled: true, candidates: [], candidateCount: 0, snapshotCount: 0, sourceErrors: ['tushare: timeout'] } })).toBe('source_unavailable');
    expect(getScreeningResultsEmptyKind({ capability: 'disabled', loading: false, candidatesCount: 0, screenMeta: null })).toBe('blocked');
  });

  it('full source unavailable and partial degraded rules', () => {
    expect(isFullSourceUnavailable({ enabled: true, candidates: [], candidateCount: 0, snapshotCount: 0, sourceErrors: ['x'] })).toBe(true);
    expect(isFullSourceUnavailable({ enabled: true, candidates: [], candidateCount: 0, snapshotCount: 1, sourceErrors: ['x'] })).toBe(false);
    expect(isPartialDegradedScreen({ screenMeta: { enabled: true, candidates: [], candidateCount: 1 }, candidatesCount: 1, alertMessages: ['a'], llmDegraded: false })).toBe(true);
    expect(isPartialDegradedScreen({ screenMeta: { enabled: true, candidates: [], candidateCount: 0 }, candidatesCount: 0, alertMessages: ['a'], llmDegraded: true })).toBe(false);
  });
});
