// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PortfolioFutuImportPreviewResponse } from '../../../types/portfolio';
import type { PortfolioText } from '../types';
import type { PortfolioImportText } from '../../../locales/portfolioImport';
import { usePortfolioImportSession } from '../usePortfolioImportSession';

const { listImportBrokers, parseCsvImport, previewFutuImport } = vi.hoisted(() => ({
  listImportBrokers: vi.fn(),
  parseCsvImport: vi.fn(),
  previewFutuImport: vi.fn(),
}));

vi.mock('../../../api/portfolio', () => ({
  portfolioApi: {
    listImportBrokers,
    parseCsvImport,
    previewFutuImport,
  },
}));

const text = {
  selectAccountWrite: 'Select an account',
} satisfies Pick<PortfolioText, 'selectAccountWrite'>;
const importText = {
  brokerListEmpty: 'No brokers',
  brokerListUnavailable: 'Brokers unavailable',
} satisfies Pick<PortfolioImportText, 'brokerListEmpty' | 'brokerListUnavailable'>;

const preview: PortfolioFutuImportPreviewResponse = {
  broker: 'futu',
  recordCount: 1,
  skippedCount: 0,
  errorCount: 0,
  records: [{
    tradeDate: '2026-08-15',
    symbol: 'AAPL',
    side: 'buy',
    quantity: 2,
    price: 200,
    fee: 0,
    tax: 0,
    dedupHash: 'dedup-1',
  }],
  errors: [],
  failedRows: [],
  snapshotId: 'a'.repeat(64),
};

function renderSession() {
  const commitCsv = vi.fn();
  const commitFutu = vi.fn(async (_command, onCommitted) => {
    onCommitted({
      accountId: 7,
      recordCount: 1,
      insertedCount: 1,
      duplicateCount: 0,
      failedCount: 0,
      dryRun: false,
      errors: [],
    });
  });
  const setWriteWarning = vi.fn();
  return {
    commitCsv,
    commitFutu,
    setWriteWarning,
    ...renderHook(() => usePortfolioImportSession({
      text,
      importText,
      writableAccountId: 7,
      setWriteWarning,
      commitCsv,
      commitFutu,
    })),
  };
}

describe('usePortfolioImportSession', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    previewFutuImport.mockResolvedValue(preview);
  });

  it('requires a Futu preview and binds commit to its snapshot', async () => {
    const session = renderSession();

    await act(async () => {
      await session.result.current.handleCommit();
    });
    expect(session.commitFutu).not.toHaveBeenCalled();

    act(() => session.result.current.setSource('futu'));
    await act(async () => {
      await session.result.current.handlePreview();
    });
    expect(session.result.current.previewSnapshotId).toBe('a'.repeat(64));

    await act(async () => {
      await session.result.current.handleCommit();
    });
    expect(session.commitFutu).toHaveBeenCalledWith(
      expect.objectContaining({
        accountId: 7,
        expectedSnapshotId: 'a'.repeat(64),
      }),
      expect.any(Function),
    );
  });

  it('invalidates the snapshot when date, source, or modal lifecycle changes', async () => {
    const session = renderSession();
    act(() => session.result.current.setSource('futu'));
    await act(async () => {
      await session.result.current.handlePreview();
    });

    act(() => session.result.current.setFutuAsOf('2026-08-14'));
    expect(session.result.current.previewSnapshotId).toBeUndefined();
    expect(session.result.current.previewResult).toBeNull();

    await act(async () => {
      await session.result.current.handlePreview();
    });
    act(() => session.result.current.setSource('file'));
    expect(session.result.current.previewResult).toBeNull();

    act(() => session.result.current.setSource('futu'));
    await act(async () => {
      await session.result.current.handlePreview();
    });
    act(() => session.result.current.setImportModalOpen(false));
    expect(session.result.current.previewSnapshotId).toBeUndefined();
  });

  it('blocks duplicate previews and surfaces stale commit failures', async () => {
    let resolvePreview!: (value: PortfolioFutuImportPreviewResponse) => void;
    previewFutuImport.mockReturnValueOnce(new Promise((resolve) => {
      resolvePreview = resolve;
    }));
    const session = renderSession();
    act(() => session.result.current.setSource('futu'));

    act(() => {
      void session.result.current.handlePreview();
      void session.result.current.handlePreview();
    });
    expect(previewFutuImport).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolvePreview(preview);
    });

    session.commitFutu.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          error: 'portfolio_import_preview_stale',
          message: 'Futu position snapshot changed: diagnostic hash mismatch',
          category: 'config_conflict',
          severity: 'warning',
        },
      },
    });
    let outcome: 'preview_stale' | void = undefined;
    await act(async () => {
      outcome = await session.result.current.handleCommit();
    });
    expect(outcome).toBe('preview_stale');
    expect(session.result.current.error?.code).toBe('portfolio_import_preview_stale');
    expect(session.result.current.error?.title).toBe('持仓预览已过期');
    expect(session.result.current.error?.message).toContain('重新预览');
    expect(session.result.current.error?.rawMessage).toContain('diagnostic hash mismatch');
    expect(session.result.current.previewResult).toBeNull();
    expect(session.result.current.previewSnapshotId).toBeUndefined();
  });
});
