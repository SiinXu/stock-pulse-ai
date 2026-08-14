// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Feature-private import session state for the Portfolio route.
// Commit identity/operationId scoping stays in usePortfolioLedgerMutationWorkflow.

import { useCallback, useRef, useState } from 'react';
import { portfolioApi } from '../../api/portfolio';
import type { ParsedApiError } from '../../api/error';
import { getParsedApiError } from '../../api/error';
import type {
  PortfolioImportBrokerItem,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioImportSource,
} from '../../types/portfolio';
import type { PortfolioText } from './types';
import type { usePortfolioLedgerMutationWorkflow } from './usePortfolioLedgerMutationWorkflow';

type MutationWorkflow = ReturnType<typeof usePortfolioLedgerMutationWorkflow>;

type UsePortfolioImportSessionOptions = {
  text: PortfolioText;
  writableAccountId: number | undefined;
  setWriteWarning: (warning: string | null) => void;
  commitCsv: MutationWorkflow['commitCsv'];
  commitFutu: MutationWorkflow['commitFutu'];
};

export function usePortfolioImportSession({
  text,
  writableAccountId,
  setWriteWarning,
  commitCsv,
  commitFutu,
}: UsePortfolioImportSessionOptions) {
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importSource, setImportSourceState] = useState<PortfolioImportSource>('file');
  const [brokers, setBrokers] = useState<PortfolioImportBrokerItem[]>([]);
  const [selectedBroker, setSelectedBroker] = useState('');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [futuAsOf, setFutuAsOf] = useState('');
  const [importDryRun, setImportDryRun] = useState(true);
  const [importParsing, setImportParsing] = useState(false);
  const [importError, setImportError] = useState<ParsedApiError | null>(null);
  const [importParseResult, setImportParseResult] = useState<PortfolioImportParseResponse | null>(null);
  const [importCommitResult, setImportCommitResult] = useState<PortfolioImportCommitResponse | null>(null);
  const [brokerLoadWarning, setBrokerLoadWarning] = useState<string | null>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);
  const previewPendingRef = useRef(false);

  const resetImportResults = useCallback(() => {
    setImportError(null);
    setImportParseResult(null);
    setImportCommitResult(null);
  }, []);

  const setImportSource = useCallback((source: PortfolioImportSource) => {
    setImportSourceState(source);
    resetImportResults();
  }, [resetImportResults]);

  const loadBrokers = useCallback(async () => {
    try {
      const response = await portfolioApi.listImportBrokers();
      const brokerItems = response.brokers || [];
      if (brokerItems.length === 0) {
        setBrokers([]);
        setBrokerLoadWarning(text.brokerListEmpty);
        setSelectedBroker('');
        return;
      }
      setBrokers(brokerItems);
      setBrokerLoadWarning(null);
      setSelectedBroker((current) => (
        brokerItems.some((item) => item.broker === current) ? current : brokerItems[0].broker
      ));
    } catch {
      setBrokers([]);
      setBrokerLoadWarning(text.brokerListUnavailable);
      setSelectedBroker('');
    }
  }, [text.brokerListEmpty, text.brokerListUnavailable]);

  const handlePreviewImport = async (fileOverride?: File) => {
    if (previewPendingRef.current) return;
    const file = fileOverride ?? csvFile;
    if (importSource === 'file' && (!file || !selectedBroker)) return;
    previewPendingRef.current = true;
    try {
      setImportParsing(true);
      setImportError(null);
      const parsed = importSource === 'futu'
        ? await portfolioApi.previewFutuImport(futuAsOf || undefined)
        : await portfolioApi.parseCsvImport(selectedBroker, file!);
      setImportParseResult(parsed);
      setImportCommitResult(null);
    } catch (err) {
      setImportParseResult(null);
      setImportError(getParsedApiError(err));
    } finally {
      previewPendingRef.current = false;
      setImportParsing(false);
    }
  };

  const handleCommitImport = async () => {
    if (!importParseResult || (importSource === 'futu' && importParseResult.recordCount <= 0)) return;
    if (!writableAccountId) {
      setWriteWarning(text.selectAccountWrite);
      return;
    }
    try {
      setWriteWarning(null);
      setImportError(null);
      if (importSource === 'futu') {
        await commitFutu(
          {
            accountId: writableAccountId,
            dryRun: importDryRun,
            asOf: futuAsOf || undefined,
          },
          setImportCommitResult,
        );
      } else if (csvFile && selectedBroker) {
        await commitCsv(
          {
            accountId: writableAccountId,
            broker: selectedBroker,
            file: csvFile,
            dryRun: importDryRun,
          },
          setImportCommitResult,
        );
      }
    } catch (err) {
      setImportError(getParsedApiError(err));
    }
  };

  return {
    importModalOpen,
    setImportModalOpen,
    importSource,
    setImportSource,
    brokers,
    selectedBroker,
    setSelectedBroker,
    csvFile,
    setCsvFile,
    futuAsOf,
    setFutuAsOf,
    importDryRun,
    setImportDryRun,
    importParsing,
    importError,
    setImportError,
    importParseResult,
    setImportParseResult,
    importCommitResult,
    setImportCommitResult,
    brokerLoadWarning,
    csvInputRef,
    resetImportResults,
    loadBrokers,
    handlePreviewImport,
    handleCommitImport,
  };
}
