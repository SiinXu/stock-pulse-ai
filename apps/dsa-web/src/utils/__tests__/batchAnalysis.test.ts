// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it, vi } from 'vitest';
import { DuplicateTaskError } from '../../api/analysis';
import { getParsedApiError } from '../../api/error';
import type { AnalyzeAsyncResponse } from '../../types/analysis';
import {
  normalizeBatchAnalysisCodes,
  submitBatchAnalysis,
} from '../batchAnalysis';

const accepted = (codes: readonly string[], duplicateCodes: readonly string[] = []): AnalyzeAsyncResponse => ({
  accepted: codes.map((stockCode, index) => ({
    taskId: `task-${index}`,
    stockCode,
    status: 'pending',
  })),
  duplicates: duplicateCodes.map((stockCode, index) => ({
    stockCode,
    existingTaskId: `duplicate-${index}`,
    message: 'Already running',
  })),
  message: 'Accepted',
});

const submit = (
  codes: readonly string[],
  submitChunk: (chunk: string[]) => Promise<AnalyzeAsyncResponse>,
  reconcile = vi.fn().mockResolvedValue(undefined),
) => submitBatchAnalysis({
  codes,
  submitChunk,
  reconcile,
  parseError: getParsedApiError,
  incompleteResponseMessage: (confirmed, requested) => `${confirmed}/${requested} confirmed`,
});

describe('batchAnalysis', () => {
  it('normalizes aliases and removes duplicate or empty symbols', () => {
    expect(normalizeBatchAnalysisCodes([' aapl ', 'AAPL', 'sh600519', '600519.SH', '']))
      .toEqual(['AAPL', 'SH600519']);
  });

  it('chunks requests, counts accepted and duplicate responses, and reconciles once', async () => {
    const codes = Array.from({ length: 51 }, (_, index) => `T${String(index).padStart(3, '0')}`);
    const submitChunk = vi.fn()
      .mockResolvedValueOnce(accepted(codes.slice(0, 49), [codes[49]]))
      .mockResolvedValueOnce(accepted([codes[50]]));
    const reconcile = vi.fn().mockResolvedValue(undefined);

    const result = await submit(codes, submitChunk, reconcile);

    expect(submitChunk).toHaveBeenCalledTimes(2);
    expect(submitChunk.mock.calls.map(([chunk]) => chunk.length)).toEqual([50, 1]);
    expect(result).toMatchObject({ accepted: 50, duplicates: 1, confirmed: 51, unconfirmed: 0 });
    expect(result.submissionError).toBeNull();
    expect(result.reconciliationError).toBeNull();
    expect(reconcile).toHaveBeenCalledTimes(1);
  });

  it('counts a single-symbol duplicate exception as confirmed', async () => {
    const result = await submit(['AAPL'], vi.fn().mockRejectedValue(
      new DuplicateTaskError('AAPL', 'task-existing'),
    ));

    expect(result).toMatchObject({ accepted: 0, duplicates: 1, confirmed: 1, unconfirmed: 0 });
    expect(result.submissionError).toBeNull();
  });

  it('stops on an incomplete response and reports unconfirmed symbols', async () => {
    const submitChunk = vi.fn().mockResolvedValue(accepted(['AAPL']));

    const result = await submit(['AAPL', 'MSFT'], submitChunk);

    expect(result).toMatchObject({ accepted: 1, duplicates: 0, confirmed: 1, unconfirmed: 1 });
    expect(result.submissionError?.rawMessage).toContain('1/2 confirmed');
  });

  it('returns the reconciliation outcome independently from submission', async () => {
    const result = await submit(
      ['AAPL'],
      vi.fn().mockResolvedValue(accepted(['AAPL'])),
      vi.fn().mockRejectedValue(new Error('Task refresh failed')),
    );

    expect(result.submissionError).toBeNull();
    expect(result.reconciliationError?.rawMessage).toContain('Task refresh failed');
  });
});
