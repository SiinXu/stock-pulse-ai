// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { usePortfolioImportMutationWorkflow } from '../usePortfolioImportMutationWorkflow';

const { commitCsvImport, commitFutuImport } = vi.hoisted(() => ({
  commitCsvImport: vi.fn(),
  commitFutuImport: vi.fn(),
}));

vi.mock('../../../api/portfolio', () => ({
  portfolioApi: { commitCsvImport, commitFutuImport },
}));

function renderWorkflow(refreshPortfolioData = vi.fn().mockResolvedValue(undefined)) {
  return {
    refreshPortfolioData,
    ...renderHook(() => usePortfolioImportMutationWorkflow({ refreshPortfolioData })),
  };
}

const fullResult = {
  accountId: 1,
  recordCount: 1,
  insertedCount: 1,
  duplicateCount: 0,
  failedCount: 0,
  dryRun: false,
  errors: [],
};

describe('usePortfolioImportMutationWorkflow', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('keeps full CSV identity, rotates partial identity, and skips refresh for dry runs', async () => {
    commitCsvImport
      .mockRejectedValueOnce(new Error('csv timeout'))
      .mockResolvedValueOnce(fullResult)
      .mockResolvedValueOnce(fullResult)
      .mockResolvedValueOnce({ ...fullResult, failedCount: 1, errors: ['temporary failure'] })
      .mockResolvedValueOnce(fullResult)
      .mockResolvedValueOnce({ ...fullResult, dryRun: true });
    const workflow = renderWorkflow();
    const file = new File(['header\nrow'], 'trades.csv', { type: 'text/csv' });
    const command = { accountId: 1, broker: 'huatai', file, dryRun: false };
    const onCommitted = vi.fn();

    await act(async () => {
      await expect(workflow.result.current.commitCsv(command, onCommitted))
        .rejects.toThrow('csv timeout');
    });
    const failedOperationId = commitCsvImport.mock.calls[0][3];

    await act(async () => {
      await workflow.result.current.commitCsv(command, onCommitted);
      await workflow.result.current.commitCsv(command, onCommitted);
    });
    expect(commitCsvImport.mock.calls[1][3]).toBe(failedOperationId);
    expect(commitCsvImport.mock.calls[2][3]).toBe(failedOperationId);

    const partialFile = new File(['header\npartial'], 'partial.csv', { type: 'text/csv' });
    const partialCommand = { ...command, file: partialFile };
    await act(async () => {
      await workflow.result.current.commitCsv(partialCommand, onCommitted);
    });
    const partialOperationId = commitCsvImport.mock.calls[3][3];
    await act(async () => {
      await workflow.result.current.commitCsv(partialCommand, onCommitted);
    });
    expect(commitCsvImport.mock.calls[4][3]).not.toBe(partialOperationId);

    await act(async () => {
      await workflow.result.current.commitCsv({ ...command, dryRun: true }, onCommitted);
    });
    expect(workflow.refreshPortfolioData).toHaveBeenCalledTimes(4);
    expect(onCommitted).toHaveBeenCalledTimes(5);
  });

  it('rotates failed CSV attempts when File object identity changes', async () => {
    commitCsvImport.mockRejectedValue(new Error('csv timeout'));
    const workflow = renderWorkflow();
    const onCommitted = vi.fn();
    const firstFile = new File(['AA'], 'same.csv', { type: 'text/csv', lastModified: 1 });
    const secondFile = new File(['BB'], 'same.csv', { type: 'text/csv', lastModified: 1 });
    const command = {
      accountId: 1,
      broker: 'huatai',
      file: firstFile,
      dryRun: false,
    };

    await act(async () => {
      await expect(workflow.result.current.commitCsv(command, onCommitted))
        .rejects.toThrow('csv timeout');
      await expect(workflow.result.current.commitCsv(command, onCommitted))
        .rejects.toThrow('csv timeout');
      await expect(workflow.result.current.commitCsv({ ...command, file: secondFile }, onCommitted))
        .rejects.toThrow('csv timeout');
    });
    expect(firstFile.size).toBe(secondFile.size);
    expect(commitCsvImport.mock.calls[1][3]).toBe(commitCsvImport.mock.calls[0][3]);
    expect(commitCsvImport.mock.calls[2][3]).not.toBe(commitCsvImport.mock.calls[0][3]);
    expect(workflow.refreshPortfolioData).not.toHaveBeenCalled();
  });

  it('binds Futu commits to the preview snapshot and skips refresh for dry runs', async () => {
    commitFutuImport
      .mockResolvedValueOnce(fullResult)
      .mockResolvedValueOnce({ ...fullResult, dryRun: true });
    const workflow = renderWorkflow();
    const onCommitted = vi.fn();
    const command = {
      accountId: 1,
      asOf: '2026-08-15',
      dryRun: false,
      expectedSnapshotId: 'a'.repeat(64),
    };

    await act(async () => {
      await workflow.result.current.commitFutu(command, onCommitted);
    });
    expect(commitFutuImport).toHaveBeenCalledWith(expect.objectContaining({
      ...command,
      operationId: expect.stringMatching(/^portfolio-futu-/),
    }));
    expect(workflow.refreshPortfolioData).toHaveBeenCalledTimes(1);

    await act(async () => {
      await workflow.result.current.commitFutu({ ...command, dryRun: true }, onCommitted);
    });
    expect(workflow.refreshPortfolioData).toHaveBeenCalledTimes(1);
    expect(onCommitted).toHaveBeenCalledTimes(2);
  });
});
