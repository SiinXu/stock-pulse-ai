import { describe, expect, it } from 'vitest';
import type { ParsedApiError } from '../../../api/error';
import { SCREENING_TEXT } from '../../../locales/screening';
import { getScreeningDegradationReasons } from '../screeningDegradation';
import {
  getScreeningCapabilityState,
  getScreeningResultsEmptyKind,
  getScreeningRunStatusTitle,
  isFullSourceUnavailable,
} from '../screeningPageState';

const statusError: ParsedApiError = {
  title: 'Request failed',
  message: 'Could not reach the service',
  rawMessage: 'network error',
  category: 'upstream_network',
};

describe('screeningPageState', () => {
  it('keeps capability status failures separate from disabled and unavailable states', () => {
    expect(getScreeningCapabilityState({ statusLoading: true, enabled: false, available: false })).toBe('loading');
    expect(getScreeningCapabilityState({ statusLoading: false, enabled: false, available: false })).toBe('disabled');
    expect(getScreeningCapabilityState({ statusLoading: false, enabled: true, available: false })).toBe('adapter_unavailable');
    expect(getScreeningCapabilityState({ statusLoading: false, enabled: true, available: true })).toBe('ready');
    expect(getScreeningCapabilityState({
      statusLoading: false,
      statusError,
      enabled: false,
      available: false,
    })).toBe('status_error');
  });

  it('distinguishes loading, blocked, no-hit, and full-source empty states', () => {
    expect(getScreeningResultsEmptyKind({ capability: 'loading', loading: false, candidatesCount: 0, screenMeta: null })).toBe('loading');
    expect(getScreeningResultsEmptyKind({ capability: 'ready', loading: false, candidatesCount: 0, screenMeta: null })).toBe('never_run');
    expect(getScreeningResultsEmptyKind({ capability: 'ready', loading: false, candidatesCount: 0, screenMeta: { enabled: true, candidates: [], candidateCount: 0, snapshotCount: 80, afterFilterCount: 0 } })).toBe('no_hits');
    expect(getScreeningResultsEmptyKind({ capability: 'ready', loading: false, candidatesCount: 0, screenMeta: { enabled: true, candidates: [], candidateCount: 0, snapshotCount: 0, sourceErrors: ['tushare: timeout'] } })).toBe('source_unavailable');
    expect(getScreeningResultsEmptyKind({ capability: 'status_error', loading: false, candidatesCount: 0, screenMeta: null })).toBe('blocked');
  });

  it('requires both no snapshot and a source error for full source unavailability', () => {
    expect(isFullSourceUnavailable({ enabled: true, candidates: [], candidateCount: 0, snapshotCount: 0, sourceErrors: ['x'] })).toBe(true);
    expect(isFullSourceUnavailable({ enabled: true, candidates: [], candidateCount: 0, snapshotCount: 1, sourceErrors: ['x'] })).toBe(false);
    expect(isFullSourceUnavailable({ enabled: true, candidates: [], candidateCount: 0, snapshotCount: 0, sourceErrors: [] })).toBe(false);
  });

  it('does not report a failed or fully unavailable attempt as completed', () => {
    const sourceFailure = {
      enabled: true,
      candidates: [],
      candidateCount: 0,
      snapshotCount: 0,
      sourceErrors: ['tushare: timeout'],
    };
    expect(getScreeningRunStatusTitle({
      text: SCREENING_TEXT.en,
      attemptState: 'completed',
      candidatesCount: 2,
      screenMeta: { enabled: true, candidates: [], candidateCount: 2 },
      attemptResult: sourceFailure,
    })).toBe(SCREENING_TEXT.en.callFailed);
    expect(getScreeningRunStatusTitle({
      text: SCREENING_TEXT.en,
      attemptState: 'failed',
      candidatesCount: 2,
      screenMeta: { enabled: true, candidates: [], candidateCount: 2 },
      attemptResult: null,
    })).toBe(SCREENING_TEXT.en.callFailed);
  });

  it('categorizes source, LLM, enrichment, and general degradation independently', () => {
    const reasons = getScreeningDegradationReasons({
      enabled: true,
      candidates: [],
      candidateCount: 0,
      warnings: ['AlphaSift warning', 'LLM ranking failed: malformed response'],
      sourceErrors: ['tushare: timeout'],
      llmParseErrors: ['alphasift_llm_parse_error'],
      dsaEnrichment: { requestedCount: 1, enrichedCount: 0, warnings: ['stock_news_failed'] },
    }, SCREENING_TEXT.zh);

    expect(reasons.general).toEqual(['AlphaSift warning']);
    expect(reasons.source).toEqual(['数据源降级：tushare（请求超时）']);
    expect(reasons.llm).toHaveLength(2);
    expect(reasons.enrichment).toEqual(['数据源暂时不可用']);
  });

  it('does not mislabel LLM-only degradation as a market-data problem', () => {
    const reasons = getScreeningDegradationReasons({
      enabled: true,
      candidates: [],
      candidateCount: 0,
      llmRanked: false,
      warnings: ['LLM ranking failed: timeout'],
    }, SCREENING_TEXT.zh);

    expect(reasons.llm).toHaveLength(1);
    expect(reasons.source).toEqual([]);
  });
});
