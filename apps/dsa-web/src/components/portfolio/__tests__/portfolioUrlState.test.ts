// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, it } from 'vitest';
import { readParams, writeParams } from '../../../utils/urlState';
import {
  buildPositionRowKey,
  portfolioUrlSchema,
} from '../portfolioUrlState';

describe('portfolioUrlSchema', () => {
  it('defaults to all accounts, positions tab, no selection, page 1', () => {
    expect(readParams(portfolioUrlSchema, '')).toEqual({
      account: null,
      tab: 'positions',
      view: 'health',
      selected: null,
      page: 1,
    });
  });

  it('parses account, tab, selected row, and ledger page', () => {
    expect(readParams(
      portfolioUrlSchema,
      '?account=7&tab=ledger&selected=7-AAPL-us&page=3&keep=yes',
    )).toEqual({
      account: 7,
      tab: 'ledger',
      view: 'health',
      selected: '7-AAPL-us',
      page: 3,
    });
  });

  it('falls back on invalid tab and non-positive account/page', () => {
    expect(readParams(portfolioUrlSchema, '?account=0&tab=admin&page=abc')).toEqual({
      account: null,
      tab: 'positions',
      view: 'health',
      selected: null,
      page: 1,
    });
  });

  it('round-trips the insights tab and nested view for refresh and Back restoration', () => {
    const written = writeParams(
      portfolioUrlSchema,
      { tab: 'insights', view: 'stress' },
      { search: '?account=7' },
    );
    expect(written.search).toContain('tab=insights');
    expect(written.search).toContain('view=stress');
    expect(readParams(portfolioUrlSchema, written.search)).toMatchObject({
      account: 7,
      tab: 'insights',
      view: 'stress',
    });
  });

  it('writes tab/page with replace and selected with push; preserves unknown keys', () => {
    const tabWrite = writeParams(
      portfolioUrlSchema,
      { tab: 'risk', page: 2 },
      { search: '?account=3&keep=yes' },
    );
    expect(tabWrite.history).toBe('replace');
    expect(tabWrite.search).toContain('tab=risk');
    expect(tabWrite.search).toContain('page=2');
    expect(tabWrite.search).toContain('account=3');
    expect(tabWrite.search).toContain('keep=yes');

    const selectedWrite = writeParams(
      portfolioUrlSchema,
      { selected: '3-600519-cn' },
      { search: '?account=3' },
    );
    expect(selectedWrite.history).toBe('push');
    expect(selectedWrite.search).toContain('selected=3-600519-cn');
  });

  it('omits default tab and page from the URL', () => {
    const result = writeParams(
      portfolioUrlSchema,
      { tab: 'positions', view: 'health', page: 1, account: null, selected: null },
      { search: '?tab=insights&view=stress&page=4&account=9&selected=x' },
    );
    expect(result.search).toBe('');
  });

  it('builds stable position row keys', () => {
    expect(buildPositionRowKey(1, 'AAPL', 'us')).toBe('1-AAPL-us');
  });
});
