// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Exercises all five mutation paths through the feature-private workflow interface.

import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { usePortfolioLedgerMutationWorkflow } from '../usePortfolioLedgerMutationWorkflow';

const {
  createTrade,
  createPaperTrade,
  createCashLedger,
  createCorporateAction,
  commitCsvImport,
} = vi.hoisted(() => ({
  createTrade: vi.fn(),
  createPaperTrade: vi.fn(),
  createCashLedger: vi.fn(),
  createCorporateAction: vi.fn(),
  commitCsvImport: vi.fn(),
}));

vi.mock('../../../api/portfolio', () => ({
  portfolioApi: {
    createTrade,
    createPaperTrade,
    createCashLedger,
    createCorporateAction,
    commitCsvImport,
  },
}));

function renderWorkflow(
  refreshPortfolioData = vi.fn().mockResolvedValue(undefined),
  refreshPaperTradeSurfaces = vi.fn().mockResolvedValue(true),
) {
  return {
    refreshPortfolioData,
    refreshPaperTradeSurfaces,
    ...renderHook(() => usePortfolioLedgerMutationWorkflow({
      refreshPortfolioData,
      refreshPaperTradeSurfaces,
    })),
  };
}

describe('usePortfolioLedgerMutationWorkflow', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('reuses failed operation IDs and refreshes each committed ledger path', async () => {
    createTrade
      .mockRejectedValueOnce(new Error('trade timeout'))
      .mockResolvedValueOnce({ id: 1 });
    createPaperTrade
      .mockRejectedValueOnce(new Error('paper timeout'))
      .mockResolvedValueOnce({ id: 2, price: 205, priceSource: 'manual' });
    createCashLedger
      .mockRejectedValueOnce(new Error('cash timeout'))
      .mockResolvedValueOnce({ id: 3 });
    createCorporateAction
      .mockRejectedValueOnce(new Error('corporate timeout'))
      .mockResolvedValueOnce({ id: 4 });
    const workflow = renderWorkflow();
    const onCommitted = vi.fn();

    const tradeCommand = {
      accountId: 1,
      symbol: 'AAPL',
      tradeDate: '2026-07-30',
      side: 'buy' as const,
      quantity: 1,
      price: 205,
    };
    await act(async () => {
      await expect(workflow.result.current.submitTrade(tradeCommand, onCommitted))
        .rejects.toThrow('trade timeout');
    });
    const tradeOperationId = createTrade.mock.calls[0][0].operationId;
    await act(async () => {
      await workflow.result.current.submitTrade(tradeCommand, onCommitted);
    });
    expect(createTrade.mock.calls[1][0].operationId).toBe(tradeOperationId);

    const paperCommand = {
      symbol: 'MSFT',
      tradeDate: '2026-07-30',
      side: 'sell' as const,
      quantity: 2,
      price: 510,
    };
    await act(async () => {
      await expect(workflow.result.current.submitPaperTrade(1, paperCommand, onCommitted))
        .rejects.toThrow('paper timeout');
    });
    const paperOperationId = createPaperTrade.mock.calls[0][1].operationId;
    await act(async () => {
      await workflow.result.current.submitPaperTrade(1, paperCommand, onCommitted);
    });
    expect(createPaperTrade.mock.calls[1][1].operationId).toBe(paperOperationId);

    const cashCommand = {
      accountId: 1,
      eventDate: '2026-07-30',
      direction: 'in' as const,
      amount: 1000,
    };
    await act(async () => {
      await expect(workflow.result.current.submitCash(cashCommand, onCommitted))
        .rejects.toThrow('cash timeout');
    });
    const cashOperationId = createCashLedger.mock.calls[0][0].operationId;
    await act(async () => {
      await workflow.result.current.submitCash(cashCommand, onCommitted);
    });
    expect(createCashLedger.mock.calls[1][0].operationId).toBe(cashOperationId);

    const corporateCommand = {
      accountId: 1,
      symbol: 'AAPL',
      effectiveDate: '2026-07-30',
      actionType: 'cash_dividend' as const,
      cashDividendPerShare: 0.25,
    };
    await act(async () => {
      await expect(workflow.result.current.submitCorporateAction(corporateCommand, onCommitted))
        .rejects.toThrow('corporate timeout');
    });
    const corporateOperationId = createCorporateAction.mock.calls[0][0].operationId;
    await act(async () => {
      await workflow.result.current.submitCorporateAction(corporateCommand, onCommitted);
    });
    expect(createCorporateAction.mock.calls[1][0].operationId).toBe(corporateOperationId);

    expect(tradeOperationId).toMatch(/^portfolio-trade-/);
    expect(paperOperationId).toMatch(/^portfolio-paper-trade-/);
    expect(cashOperationId).toMatch(/^portfolio-cash-/);
    expect(corporateOperationId).toMatch(/^portfolio-corporate-/);
    expect(workflow.refreshPortfolioData).toHaveBeenCalledTimes(3);
    expect(workflow.refreshPaperTradeSurfaces).toHaveBeenCalledTimes(1);
    expect(onCommitted).toHaveBeenCalledTimes(4);
  });

  it('keeps full CSV identity, rotates partial identity, and skips refresh for dry runs', async () => {
    const fullResult = {
      accountId: 1,
      recordCount: 1,
      insertedCount: 1,
      duplicateCount: 0,
      failedCount: 0,
      dryRun: false,
      errors: [],
    };
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

  it('rotates failed attempts when command or File object identity changes', async () => {
    createTrade.mockRejectedValue(new Error('trade timeout'));
    commitCsvImport.mockRejectedValue(new Error('csv timeout'));
    const workflow = renderWorkflow();
    const onCommitted = vi.fn();
    const tradeCommand = {
      accountId: 1,
      symbol: 'AAPL',
      tradeDate: '2026-07-30',
      side: 'buy' as const,
      quantity: 1,
      price: 205,
    };

    await act(async () => {
      await expect(workflow.result.current.submitTrade(tradeCommand, onCommitted))
        .rejects.toThrow('trade timeout');
      await expect(workflow.result.current.submitTrade({
        ...tradeCommand,
        quantity: 2,
      }, onCommitted)).rejects.toThrow('trade timeout');
    });
    expect(createTrade.mock.calls[1][0].operationId)
      .not.toBe(createTrade.mock.calls[0][0].operationId);

    const firstFile = new File(['AA'], 'same.csv', {
      type: 'text/csv',
      lastModified: 1,
    });
    const secondFile = new File(['BB'], 'same.csv', {
      type: 'text/csv',
      lastModified: 1,
    });
    const csvCommand = {
      accountId: 1,
      broker: 'huatai',
      file: firstFile,
      dryRun: false,
    };

    await act(async () => {
      await expect(workflow.result.current.commitCsv(csvCommand, onCommitted))
        .rejects.toThrow('csv timeout');
      await expect(workflow.result.current.commitCsv(csvCommand, onCommitted))
        .rejects.toThrow('csv timeout');
      await expect(workflow.result.current.commitCsv({
        ...csvCommand,
        file: secondFile,
      }, onCommitted)).rejects.toThrow('csv timeout');
    });
    expect(firstFile.size).toBe(secondFile.size);
    expect(commitCsvImport.mock.calls[1][3]).toBe(commitCsvImport.mock.calls[0][3]);
    expect(commitCsvImport.mock.calls[2][3]).not.toBe(commitCsvImport.mock.calls[0][3]);
    expect(workflow.refreshPortfolioData).not.toHaveBeenCalled();
  });

  it('keeps a committed paper trade authoritative and retries only its projection refresh', async () => {
    createPaperTrade.mockResolvedValueOnce({ id: 7, price: 205, priceSource: 'manual' });
    const refreshPaperTradeSurfaces = vi.fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    const workflow = renderWorkflow(
      vi.fn().mockResolvedValue(undefined),
      refreshPaperTradeSurfaces,
    );
    const onCommitted = vi.fn();

    await act(async () => {
      await workflow.result.current.submitPaperTrade(1, {
        symbol: 'AAPL',
        tradeDate: '2026-07-30',
        side: 'buy',
        quantity: 1,
        price: 205,
      }, onCommitted);
    });
    expect(onCommitted).toHaveBeenCalledTimes(1);
    expect(workflow.result.current.paperTradeRefreshIncomplete).toBe(true);

    await act(async () => {
      await workflow.result.current.retryPaperTradeRefresh();
    });
    expect(workflow.result.current.paperTradeRefreshIncomplete).toBe(false);
    expect(createPaperTrade).toHaveBeenCalledTimes(1);
    expect(refreshPaperTradeSurfaces).toHaveBeenCalledTimes(2);
  });
});
