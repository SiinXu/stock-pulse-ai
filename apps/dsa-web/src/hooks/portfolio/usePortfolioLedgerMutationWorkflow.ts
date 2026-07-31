// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Feature-private mutation policy for the Portfolio route.

import { useCallback, useRef, useState } from 'react';
import { portfolioApi } from '../../api/portfolio';
import type {
  PaperTradeCreateRequest,
  PaperTradeCreatedResponse,
  PortfolioCashLedgerCreateRequest,
  PortfolioCorporateActionCreateRequest,
  PortfolioEventCreatedResponse,
  PortfolioImportCommitResponse,
  PortfolioTradeCreateRequest,
} from '../../types/portfolio';
import { createOperationId } from '../../utils/operationId';

type OperationAttempt = {
  fingerprint: string;
  operationId: string;
};

type MutationKind = 'trade' | 'paperTrade' | 'cash' | 'corporate' | 'csv';
type LedgerMutationKind = Exclude<MutationKind, 'csv'>;
type TradeCommand = Omit<PortfolioTradeCreateRequest, 'operationId'>;
type PaperTradeCommand = Omit<PaperTradeCreateRequest, 'operationId'>;
type CashCommand = Omit<PortfolioCashLedgerCreateRequest, 'operationId'>;
type CorporateCommand = Omit<PortfolioCorporateActionCreateRequest, 'operationId'>;

type CsvCommitCommand = {
  accountId: number;
  broker: string;
  file: File;
  dryRun: boolean;
};

type UsePortfolioLedgerMutationWorkflowOptions = {
  refreshPortfolioData: () => Promise<void>;
  refreshPaperTradeSurfaces: () => Promise<boolean>;
};

type LedgerMutationExecution<TResult> = {
  kind: LedgerMutationKind;
  identity: unknown;
  setSubmitting: (submitting: boolean) => void;
  commit: (operationId: string) => Promise<TResult>;
  onCommitted: (result: TResult) => void;
  refresh: () => Promise<unknown>;
};

const OPERATION_SCOPES: Record<MutationKind, string> = {
  trade: 'portfolio-trade',
  paperTrade: 'portfolio-paper-trade',
  cash: 'portfolio-cash',
  corporate: 'portfolio-corporate',
  csv: 'portfolio-csv',
};

function resolveOperationAttempt(
  current: OperationAttempt | null,
  fingerprint: string,
  scope: string,
): OperationAttempt {
  if (current?.fingerprint === fingerprint) return current;
  return { fingerprint, operationId: createOperationId(scope) };
}

export function usePortfolioLedgerMutationWorkflow({
  refreshPortfolioData,
  refreshPaperTradeSurfaces,
}: UsePortfolioLedgerMutationWorkflowOptions) {
  const [tradeSubmitting, setTradeSubmitting] = useState(false);
  const [paperTradeSubmitting, setPaperTradeSubmitting] = useState(false);
  const [paperTradeRefreshing, setPaperTradeRefreshing] = useState(false);
  const [paperTradeRefreshIncomplete, setPaperTradeRefreshIncomplete] = useState(false);
  const [cashSubmitting, setCashSubmitting] = useState(false);
  const [corpSubmitting, setCorpSubmitting] = useState(false);
  const [csvCommitting, setCsvCommitting] = useState(false);

  const attemptsRef = useRef<Record<MutationKind, OperationAttempt | null>>({
    trade: null,
    paperTrade: null,
    cash: null,
    corporate: null,
    csv: null,
  });
  const pendingRef = useRef<Record<MutationKind, boolean>>({
    trade: false,
    paperTrade: false,
    cash: false,
    corporate: false,
    csv: false,
  });
  const csvFileIdentityRef = useRef({
    nextToken: 1,
    tokens: new WeakMap<File, number>(),
  });
  const projectionRef = useRef({
    refreshPortfolioData,
    refreshPaperTradeSurfaces,
  });
  projectionRef.current = {
    refreshPortfolioData,
    refreshPaperTradeSurfaces,
  };

  const getAttempt = useCallback((
    kind: MutationKind,
    identity: unknown,
  ): OperationAttempt => {
    const fingerprint = JSON.stringify(identity);
    const attempt = resolveOperationAttempt(
      attemptsRef.current[kind],
      fingerprint,
      OPERATION_SCOPES[kind],
    );
    attemptsRef.current[kind] = attempt;
    return attempt;
  }, []);

  const refreshPaperProjection = useCallback(async (): Promise<boolean> => {
    setPaperTradeRefreshing(true);
    try {
      const fullyRefreshed = await projectionRef.current.refreshPaperTradeSurfaces();
      setPaperTradeRefreshIncomplete(!fullyRefreshed);
      return fullyRefreshed;
    } catch {
      setPaperTradeRefreshIncomplete(true);
      return false;
    } finally {
      setPaperTradeRefreshing(false);
    }
  }, []);

  const commitLedgerMutation = useCallback(async <TResult>({
    kind,
    identity,
    setSubmitting,
    commit,
    onCommitted,
    refresh,
  }: LedgerMutationExecution<TResult>): Promise<void> => {
    if (pendingRef.current[kind]) return;
    pendingRef.current[kind] = true;
    const attempt = getAttempt(kind, identity);
    setSubmitting(true);

    let result: TResult;
    try {
      result = await commit(attempt.operationId);
    } catch (error) {
      pendingRef.current[kind] = false;
      setSubmitting(false);
      throw error;
    }

    attemptsRef.current[kind] = null;
    pendingRef.current[kind] = false;
    setSubmitting(false);
    onCommitted(result);
    await refresh();
  }, [getAttempt]);

  const submitTrade = useCallback(async (
    command: TradeCommand,
    onCommitted: (result: PortfolioEventCreatedResponse) => void,
  ): Promise<void> => {
    await commitLedgerMutation({
      kind: 'trade',
      identity: command,
      setSubmitting: setTradeSubmitting,
      commit: (operationId) => portfolioApi.createTrade({
        ...command,
        operationId,
      }),
      onCommitted,
      refresh: () => projectionRef.current.refreshPortfolioData(),
    });
  }, [commitLedgerMutation]);

  const submitPaperTrade = useCallback(async (
    accountId: number,
    command: PaperTradeCommand,
    onCommitted: (result: PaperTradeCreatedResponse) => void,
  ): Promise<void> => {
    await commitLedgerMutation({
      kind: 'paperTrade',
      identity: { accountId, command },
      setSubmitting: setPaperTradeSubmitting,
      commit: (operationId) => portfolioApi.createPaperTrade(accountId, {
        ...command,
        operationId,
      }),
      onCommitted,
      refresh: refreshPaperProjection,
    });
  }, [commitLedgerMutation, refreshPaperProjection]);

  const submitCash = useCallback(async (
    command: CashCommand,
    onCommitted: (result: PortfolioEventCreatedResponse) => void,
  ): Promise<void> => {
    await commitLedgerMutation({
      kind: 'cash',
      identity: command,
      setSubmitting: setCashSubmitting,
      commit: (operationId) => portfolioApi.createCashLedger({
        ...command,
        operationId,
      }),
      onCommitted,
      refresh: () => projectionRef.current.refreshPortfolioData(),
    });
  }, [commitLedgerMutation]);

  const submitCorporateAction = useCallback(async (
    command: CorporateCommand,
    onCommitted: (result: PortfolioEventCreatedResponse) => void,
  ): Promise<void> => {
    await commitLedgerMutation({
      kind: 'corporate',
      identity: command,
      setSubmitting: setCorpSubmitting,
      commit: (operationId) => portfolioApi.createCorporateAction({
        ...command,
        operationId,
      }),
      onCommitted,
      refresh: () => projectionRef.current.refreshPortfolioData(),
    });
  }, [commitLedgerMutation]);

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
    const identity = {
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
    };
    const attempt = getAttempt('csv', identity);
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
        // A partial settlement needs a fresh server attempt so failed rows can
        // retry; stable trade identities keep already-inserted rows idempotent.
        attemptsRef.current.csv = null;
      }
      if (!command.dryRun) {
        await projectionRef.current.refreshPortfolioData();
      }
    } finally {
      pendingRef.current.csv = false;
      setCsvCommitting(false);
    }
  }, [getAttempt]);

  return {
    tradeSubmitting,
    paperTradeSubmitting,
    paperTradeRefreshing,
    paperTradeRefreshIncomplete,
    cashSubmitting,
    corpSubmitting,
    csvCommitting,
    submitTrade,
    submitPaperTrade,
    submitCash,
    submitCorporateAction,
    commitCsv,
    retryPaperTradeRefresh: refreshPaperProjection,
  };
}
