// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { decisionSignalsUrlSchema } from '../urlState.decisionSignalsSchema';
import {
  booleanParam,
  defineUrlStateSchema,
  enumParam,
  formatSearch,
  numberParam,
  optionalStringParam,
  readParams,
  resolveHistoryMode,
  stringParam,
  writeParams,
} from '../urlState';

const demoSchema = defineUrlStateSchema({
  market: stringParam({ name: 'market', default: '', history: 'replace' }),
  page: numberParam({ name: 'page', default: 1, history: 'replace', min: 1 }),
  tab: enumParam({
    name: 'tab',
    values: ['feed', 'rules', 'history'] as const,
    default: 'feed',
    history: 'replace',
  }),
  signal: numberParam({ name: 'signal', default: null, history: 'push', min: 1 }),
  stock: optionalStringParam({ name: 'stock', history: 'push' }),
  createRule: booleanParam({ name: 'createRule', default: false, history: 'replace' }),
});

describe('urlState readParams', () => {
  it('returns defaults for an empty search string', () => {
    expect(readParams(demoSchema, '')).toEqual({
      market: '',
      page: 1,
      tab: 'feed',
      signal: null,
      stock: null,
      createRule: false,
    });
  });

  it('parses typed values and accepts a leading question mark', () => {
    expect(readParams(demoSchema, '?market=us&page=3&tab=rules&signal=7&stock=AAPL&createRule=1')).toEqual({
      market: 'us',
      page: 3,
      tab: 'rules',
      signal: 7,
      stock: 'AAPL',
      createRule: true,
    });
  });

  it('falls back to defaults for invalid type conversions', () => {
    expect(readParams(demoSchema, 'page=0&page=abc&signal=-1&signal=1.5&tab=admin&createRule=yes')).toEqual({
      market: '',
      page: 1,
      tab: 'feed',
      signal: null,
      stock: null,
      createRule: false,
    });
  });

  it('accepts URLSearchParams input', () => {
    const params = new URLSearchParams({ market: 'hk', page: '2' });
    expect(readParams(demoSchema, params)).toMatchObject({ market: 'hk', page: 2 });
  });
});

describe('urlState writeParams', () => {
  it('serializes non-default values and omits defaults', () => {
    const result = writeParams(demoSchema, {
      market: 'us',
      page: 2,
      tab: 'rules',
      signal: 9,
      stock: '600519',
      createRule: true,
    }, { search: '' });

    expect(result.search).toBe('?market=us&page=2&tab=rules&signal=9&stock=600519&createRule=1');
    expect(result.values).toEqual({
      market: 'us',
      page: 2,
      tab: 'rules',
      signal: 9,
      stock: '600519',
      createRule: true,
    });
  });

  it('uses replace when only filter/tab params are patched', () => {
    const result = writeParams(demoSchema, { market: 'us', page: 2 }, { search: '' });
    expect(result.history).toBe('replace');
  });

  it('uses push when a selection param is patched', () => {
    const result = writeParams(demoSchema, { signal: 12 }, { search: '?market=us' });
    expect(result.history).toBe('push');
    expect(result.search).toBe('?market=us&signal=12');
  });

  it('resolves mixed patches to push when any patched key is push', () => {
    const result = writeParams(demoSchema, { market: 'us', signal: 3 }, { search: '' });
    expect(result.history).toBe('push');
  });

  it('allows the caller to override history mode', () => {
    const result = writeParams(demoSchema, { signal: 3 }, { search: '', history: 'replace' });
    expect(result.history).toBe('replace');
  });

  it('preserves unknown query parameters by default', () => {
    const result = writeParams(demoSchema, { market: 'jp' }, {
      search: '?keep=yes&ref=dashboard&market=us#ignored',
    });
    expect(result.search).toBe('?keep=yes&ref=dashboard&market=jp');
  });

  it('can drop unknown keys when preserveUnknown is false', () => {
    const result = writeParams(demoSchema, { market: 'jp' }, {
      search: '?keep=yes&market=us',
      preserveUnknown: false,
    });
    expect(result.search).toBe('?market=jp');
  });

  it('partial patches leave unpatched schema keys untouched in the URL', () => {
    const result = writeParams(demoSchema, { page: 4 }, {
      search: '?market=us&page=2&signal=7&keep=1',
    });
    expect(result.search).toBe('?keep=1&market=us&signal=7&page=4');
    expect(result.values).toMatchObject({ market: 'us', page: 4, signal: 7 });
  });

  it('null patch values reset fields to defaults and omit them', () => {
    const result = writeParams(demoSchema, { market: null, signal: null, page: null }, {
      search: '?market=us&signal=9&page=3&keep=1',
    });
    expect(result.search).toBe('?keep=1');
    expect(result.values).toMatchObject({ market: '', signal: null, page: 1 });
  });

  it('clears a key when serialize returns null for the default', () => {
    const result = writeParams(demoSchema, { page: 1, tab: 'feed' }, {
      search: '?page=5&tab=rules',
    });
    expect(result.search).toBe('');
  });
});

describe('urlState resolveHistoryMode / formatSearch', () => {
  it('returns replace when no keys or only replace keys are provided', () => {
    expect(resolveHistoryMode(demoSchema, [])).toBe('replace');
    expect(resolveHistoryMode(demoSchema, ['market', 'page'])).toBe('replace');
  });

  it('returns push when any provided key is push', () => {
    expect(resolveHistoryMode(demoSchema, ['market', 'signal'])).toBe('push');
  });

  it('formats empty and non-empty params', () => {
    expect(formatSearch(new URLSearchParams())).toBe('');
    expect(formatSearch(new URLSearchParams({ a: '1' }))).toBe('?a=1');
  });
});

describe('decisionSignalsUrlSchema example', () => {
  it('reads list, timeline, and selection keys used by DecisionSignalsPage', () => {
    const values = readParams(
      decisionSignalsUrlSchema,
      '?market=us&listStock=AAPL&action=buy&phase=intraday&source=agent&status=closed&page=3'
      + '&timelineMarket=us&timelineRange=30d&timelineStatus=active&timelineProfile=conservative'
      + '&stock=600519&view=timeline&signal=7&keep=yes',
    );

    expect(values).toMatchObject({
      market: 'us',
      listStock: 'AAPL',
      action: 'buy',
      phase: 'intraday',
      source: 'agent',
      status: 'closed',
      page: 3,
      timelineMarket: 'us',
      timelineRange: '30d',
      timelineStatus: 'active',
      timelineProfile: 'conservative',
      stock: '600519',
      view: 'timeline',
      signal: 7,
      sourceReportId: null,
    });
  });

  it('writes selection with push and preserves foreign keys', () => {
    const result = writeParams(decisionSignalsUrlSchema, { signal: 42 }, {
      search: '?market=cn&keep=yes',
    });
    expect(result.history).toBe('push');
    expect(result.search).toBe('?keep=yes&market=cn&signal=42');
  });

  it('writes list filters with replace and omits active status / page 1 defaults', () => {
    const result = writeParams(decisionSignalsUrlSchema, {
      market: 'hk',
      status: 'active',
      page: 1,
    }, { search: '?status=closed&page=4&ref=x' });

    expect(result.history).toBe('replace');
    expect(result.search).toBe('?ref=x&market=hk');
  });

  it('parses sourceReportId and invalid signal ids', () => {
    expect(readParams(decisionSignalsUrlSchema, '?sourceReportId=3001&signal=0')).toMatchObject({
      sourceReportId: 3001,
      signal: null,
    });
  });
});
