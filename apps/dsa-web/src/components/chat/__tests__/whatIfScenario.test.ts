import { describe, expect, it } from 'vitest';
import {
  DEFAULT_WHAT_IF_MAX_TURNS,
  HYPOTHETICAL_RESULT_MARKER,
  buildWhatIfContextPayload,
  buildWhatIfPromoteAnalysisHref,
  contentHasHypotheticalMarker,
  countWhatIfTurnsInMessages,
  isWhatIfLimitReached,
  mergeWhatIfIntoContext,
  type WhatIfDraftState,
} from '../whatIfScenario';
import { APP_ROUTE_PATHS } from '../../../routing/routes';

const baseDraft: WhatIfDraftState = {
  enabled: true, dimension: 'interest_rate', direction: 'down', magnitude: '50', currencyPair: 'USD/CNY', turnCount: 0,
};

describe('whatIfScenario helpers', () => {
  it('builds structured payload', () => {
    expect(buildWhatIfContextPayload(baseDraft)).toEqual({
      enabled: true, turn_index: 1, max_turns: DEFAULT_WHAT_IF_MAX_TURNS,
      assumptions: [{ dimension: 'interest_rate', direction: 'down', magnitude: 50 }],
    });
  });
  it('rejects invalid magnitude', () => {
    expect(buildWhatIfContextPayload({ ...baseDraft, magnitude: '0' })).toBeNull();
  });
  it('enforces turn cap', () => {
    const atLimit = { ...baseDraft, turnCount: DEFAULT_WHAT_IF_MAX_TURNS };
    expect(isWhatIfLimitReached(atLimit)).toBe(true);
    expect(buildWhatIfContextPayload(atLimit)).toBeNull();
  });
  it('merges context', () => {
    expect(mergeWhatIfIntoContext({ stock_code: '600519' }, baseDraft)).toMatchObject({
      stock_code: '600519', what_if: { enabled: true },
    });
  });
  it('detects markers', () => {
    expect(contentHasHypotheticalMarker(`${HYPOTHETICAL_RESULT_MARKER}\nx`)).toBe(true);
  });
  it('counts turns', () => {
    expect(countWhatIfTurnsInMessages([
      { role: 'user', content: '[HYPOTHETICAL ASSUMPTION]\nx' },
      { role: 'user', content: 'plain' },
    ])).toBe(1);
  });
  it('builds promote handoff href from stock only', () => {
    expect(buildWhatIfPromoteAnalysisHref(null)).toBeNull();
    expect(buildWhatIfPromoteAnalysisHref('  ')).toBeNull();
    const href = buildWhatIfPromoteAnalysisHref('600519');
    expect(href).toBe(`${APP_ROUTE_PATHS.researchAnalysis}?stock=600519`);
    // Isolation: never encodes what-if assumptions into the formal analysis URL.
    expect(href).not.toMatch(/what[_-]?if/i);
  });
});
