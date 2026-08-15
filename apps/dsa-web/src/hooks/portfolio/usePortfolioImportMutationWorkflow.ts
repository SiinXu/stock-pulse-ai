// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Feature-private mutation policy for portfolio import sources.

import { useCallback, useRef, useState } from 'react';
import { portfolioApi } from '../../api/portfolio';
import type { PortfolioImportCommitResponse } from '../../types/portfolio';
import { createOperationId } from '../../utils/operationId';

type ImportMutationKind = 'csv' | 'futu';
type OperationAttempt = { fingerprint: string; operationId: string };

export type CsvCommitCommand = {
  accountId: number;
  broker: string;
  file: File;
  dryRun: boolean;
};

export type FutuCommitCommand = {
  accountId: number;
  asOf?: string;
  dryRun: boolean;
  expectedSnapshotId: string;
};

type UsePortfolioImportMutationWorkflowOptions = {
  refreshPortfolioData: () => Promise<void>;
};

const OPERATION_SCOPES: Record<ImportMutationKind, string> = {
  csv: 'portfolio-csv',
  futu: 'portfolio-futu',
};

export function usePortfolioImportMutationWorkflow({
  refreshPortfolioData,
}: UsePortfolioImportMutationWorkflowOptions) {
  const [csvCommitting, setCsvCommitting] = useState(false);
  const [futuCommitting, setFutuCommitting] = useState(false);
  const attemptsRef = useRef<Record<ImportMutationKind, OperationAttempt | null>>({
    csv: null,
    futu: null,
  });
  const pendingRef = useRef<Record<ImportMutationKind, boolean>>({
    csv: false,
    futu: false,
  });
  const csvFileIdentityRef = useRef({
    nextToken: 1,
    tokens: new WeakMap<File, number>(),
  });
  const refreshPortfolioDataRef = useRef(refreshPortfolioData);
  refreshPortfolioDataRef.current = refreshPortfolioData;

  const getAttempt = useCallback((
    kind: ImportMutationKind,
    identity: unknown,
  ): OperationAttempt => {
    const fingerprint = JSON.stringify(identity);
    const current = attemptsRef.current[kind];
    if (current?.fingerprint === fingerprint) return current;
    const attempt = {
      fingerprint,
      operationId: createOperationId(OPERATION_SCOPES[kind]),
    };
    attemptsRef.current[kind] = attempt;
    return attempt;
  }, []);

  const commitCsv = useCallback(async (
    command: CsvCommitCommand,
    onCommitted: (result: PortfolioImportCommitResponse) => void,
  ): Promise<void> => {
    if (pendingRef.current.csv) return;
    pendingRef.current.csv = true;
    let fileToken = csvFileIdentityRef.current.tokens.get(command.file);
    if (fileToken === undefined) {
      fileToken = csvFileIdentityRef.current.nextToken;
      csvFileIdentityRef.current.nextToken += 1;
      csvFileIdentityRef.current.tokens.set(command.file, fileToken);
    }
    const attempt = getAttempt('csv', {
      accountId: command.accountId,
      broker: command.broker,
      dryRun: command.dryRun,
      fileToken,
      file: {
        name: command.file.name,
        size: command.file.size,
        type: command.file.type,
        lastModified: command.file.lastModified,
      },
    });
    setCsvCommitting(true);

    try {
      const result = await portfolioApi.commitCsvImport(
        command.accountId,
        command.broker,
        command.file,
        attempt.operationId,
        command.dryRun,
      );
      onCommitted(result);
      if (result.failedCount > 0) {
        // Partial settlement rotates the request identity; inserted rows remain
        // idempotent through their stable trade identities.
        attemptsRef.current.csv = null;
      }
      if (!command.dryRun) await refreshPortfolioDataRef.current();
    } finally {
      pendingRef.current.csv = false;
      setCsvCommitting(false);
    }
  }, [getAttempt]);

  const commitFutu = useCallback(async (
    command: FutuCommitCommand,
    onCommitted: (result: PortfolioImportCommitResponse) => void,
  ): Promise<void> => {
    if (pendingRef.current.futu) return;
    pendingRef.current.futu = true;
    const attempt = getAttempt('futu', command);
    setFutuCommitting(true);
    try {
      const result = await portfolioApi.commitFutuImport({
        ...command,
        operationId: attempt.operationId,
      });
      attemptsRef.current.futu = null;
      onCommitted(result);
      if (!command.dryRun) await refreshPortfolioDataRef.current();
    } finally {
      pendingRef.current.futu = false;
      setFutuCommitting(false);
    }
  }, [getAttempt]);

  return {
    csvCommitting,
    futuCommitting,
    commitCsv,
    commitFutu,
  };
}
