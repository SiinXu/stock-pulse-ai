import { beforeEach, describe, expect, it } from 'vitest';
import {
  DEFAULT_WHAT_IF_MAX_TURNS,
  HYPOTHETICAL_RESULT_MARKER,
  buildWhatIfContextPayload,
  contentHasHypotheticalMarker,
  countWhatIfTurnsInMessages,
  isWhatIfLimitReached,
  mergeWhatIfIntoContext,
  type WhatIfDraftState,
} from '../whatIfScenario';
import {
  SCENARIO_LIBRARY_STORAGE_KEY,
  SCENARIO_LIBRARY_VERSION,
  applyScenarioToDraft,
  getScenarioById,
  listBuiltinScenarios,
  projectClientSensitivity,
  saveCustomScenario,
} from '../scenarioLibrary';

const baseDraft: WhatIfDraftState = {
  enabled: true, dimension: 'interest_rate', direction: 'down', magnitude: '50', currencyPair: 'USD/CNY', turnCount: 0, scenarioId: null,
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
  it('attaches library scenario metadata to what-if payload', () => {
    expect(buildWhatIfContextPayload({ ...baseDraft, scenarioId: 'rate_hike_100bp' })).toMatchObject({
      scenario_id: 'rate_hike_100bp',
      catalog_version: SCENARIO_LIBRARY_VERSION,
    });
  });
});

describe('scenario library helpers', () => {
  beforeEach(() => {
    window.localStorage.removeItem(SCENARIO_LIBRARY_STORAGE_KEY);
  });

  it('lists rate/fx/industry builtins and changes risk framing by scenario', () => {
    const ids = listBuiltinScenarios().map((item) => item.id);
    expect(ids).toEqual(expect.arrayContaining(['rate_hike_100bp', 'fx_usd_cny_up_5', 'industry_shock_down_15']));
    const rate = projectClientSensitivity(getScenarioById('rate_hike_100bp')!);
    const industry = projectClientSensitivity(getScenarioById('industry_shock_down_15')!);
    expect(rate.catalog_version).toBe(SCENARIO_LIBRARY_VERSION);
    expect(rate.hypothetical).toBe(true);
    expect(rate.risk_framing.position_sizing).toBe('tighter');
    expect(industry.risk_framing.position_sizing).toBe('defensive');
    expect(rate.summary).toContain(HYPOTHETICAL_RESULT_MARKER);
  });

  it('applies preset to draft and saves custom for reuse', () => {
    const preset = getScenarioById('fx_usd_cny_up_5')!;
    const applied = applyScenarioToDraft(preset, baseDraft);
    expect(applied.dimension).toBe('fx_rate');
    expect(applied.scenarioId).toBe('fx_usd_cny_up_5');
    expect(applied.magnitude).toBe('5');
    const saved = saveCustomScenario({
      id: 'my_custom_rate',
      name: 'My custom rate',
      assumptions: [{ dimension: 'interest_rate', direction: 'up', magnitude: 75 }],
    });
    expect(saved.source).toBe('custom');
    expect(getScenarioById('my_custom_rate')?.assumptions[0]?.magnitude).toBe(75);
  });
});
