// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Feature-private CSV import session state for the Portfolio route.
// Commit identity/operationId scoping stays in usePortfolioLedgerMutationWorkflow.

import { useCallback, useRef, useState } from 'react';
import { portfolioApi } from '../../api/portfolio';
import type { ParsedApiError } from '../../api/error';
import { getParsedApiError } from '../../api/error';
import type {
  PortfolioImportBrokerItem,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
} from '../../types/portfolio';
import type { PortfolioText } from './types';
import type { usePortfolioLedgerMutationWorkflow } from './usePortfolioLedgerMutationWorkflow';

type MutationWorkflow = ReturnType<typeof usePortfolioLedgerMutationWorkflow>;

type UsePortfolioCsvImportSessionOptions = {
  text: PortfolioText;
  writableAccountId: number | undefined;
  setWriteWarning: (warning: string | null) => void;
  commitCsv: MutationWorkflow['commitCsv'];
};

export function usePortfolioCsvImportSession({
  text,
  writableAccountId,
  setWriteWarning,
  commitCsv,
}: UsePortfolioCsvImportSessionOptions) {
  const [csvModalOpen, setCsvModalOpen] = useState(false);
  const [brokers, setBrokers] = useState<PortfolioImportBrokerItem[]>([]);
  const [selectedBroker, setSelectedBroker] = useState('');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvDryRun, setCsvDryRun] = useState(true);
  const [csvParsing, setCsvParsing] = useState(false);
  const [csvError, setCsvError] = useState<ParsedApiError | null>(null);
  const [csvParseResult, setCsvParseResult] = useState<PortfolioImportParseResponse | null>(null);
  const [csvCommitResult, setCsvCommitResult] = useState<PortfolioImportCommitResponse | null>(null);
  const [brokerLoadWarning, setBrokerLoadWarning] = useState<string | null>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);

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

  const handleParseCsv = async () => {
    if (!csvFile || !selectedBroker) return;
    try {
      setCsvParsing(true);
      setCsvError(null);
      const parsed = await portfolioApi.parseCsvImport(selectedBroker, csvFile);
      setCsvParseResult(parsed);
      setCsvCommitResult(null);
    } catch (err) {
      setCsvError(getParsedApiError(err));
    } finally {
      setCsvParsing(false);
    }
  };

  const handleCommitCsv = async () => {
    if (!csvFile || !selectedBroker) return;
    if (!writableAccountId) {
      setWriteWarning(text.selectAccountWrite);
      return;
    }
    try {
      setWriteWarning(null);
      setCsvError(null);
      await commitCsv(
        {
          accountId: writableAccountId,
          broker: selectedBroker,
          file: csvFile,
          dryRun: csvDryRun,
        },
        setCsvCommitResult,
      );
    } catch (err) {
      setCsvError(getParsedApiError(err));
    }
  };

  return {
    csvModalOpen,
    setCsvModalOpen,
    brokers,
    selectedBroker,
    setSelectedBroker,
    csvFile,
    setCsvFile,
    csvDryRun,
    setCsvDryRun,
    csvParsing,
    csvError,
    setCsvError,
    csvParseResult,
    setCsvParseResult,
    csvCommitResult,
    setCsvCommitResult,
    brokerLoadWarning,
    csvInputRef,
    loadBrokers,
    handleParseCsv,
    handleCommitCsv,
  };
}
