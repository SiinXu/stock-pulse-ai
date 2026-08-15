// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Feature-private import session shared by file and Futu OpenD sources.

import { useCallback, useRef, useState } from 'react';
import { portfolioApi } from '../../api/portfolio';
import type { ParsedApiError } from '../../api/error';
import { getParsedApiError } from '../../api/error';
import type {
  PortfolioFutuImportPreviewResponse,
  PortfolioImportBrokerItem,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioImportSource,
} from '../../types/portfolio';
import { getTodayIso } from '../../utils/portfolioFormat';
import type { PortfolioText } from './types';
import type { PortfolioImportText } from '../../locales/portfolioImport';
import type { usePortfolioImportMutationWorkflow } from './usePortfolioImportMutationWorkflow';

type MutationWorkflow = ReturnType<typeof usePortfolioImportMutationWorkflow>;

type UsePortfolioImportSessionOptions = {
  text: Pick<PortfolioText, 'selectAccountWrite'>;
  importText: Pick<PortfolioImportText, 'brokerListEmpty' | 'brokerListUnavailable'>;
  writableAccountId: number | undefined;
  setWriteWarning: (warning: string | null) => void;
  commitCsv: MutationWorkflow['commitCsv'];
  commitFutu: MutationWorkflow['commitFutu'];
};

export function usePortfolioImportSession({
  text,
  importText,
  writableAccountId,
  setWriteWarning,
  commitCsv,
  commitFutu,
}: UsePortfolioImportSessionOptions) {
  const [importModalOpen, setImportModalOpenState] = useState(false);
  const [source, setSourceState] = useState<PortfolioImportSource>('file');
  const [brokers, setBrokers] = useState<PortfolioImportBrokerItem[]>([]);
  const [selectedBroker, setSelectedBrokerState] = useState('');
  const [file, setFileState] = useState<File | null>(null);
  const [futuAsOf, setFutuAsOfState] = useState(getTodayIso());
  const [dryRun, setDryRun] = useState(true);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [previewResult, setPreviewResult] = useState<PortfolioImportParseResponse | null>(null);
  const [commitResult, setCommitResult] = useState<PortfolioImportCommitResponse | null>(null);
  const [brokerLoadWarning, setBrokerLoadWarning] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previewGenerationRef = useRef(0);
  const previewPendingRef = useRef(false);

  const invalidatePreview = useCallback(() => {
    previewGenerationRef.current += 1;
    previewPendingRef.current = false;
    setIsPreviewing(false);
    setError(null);
    setPreviewResult(null);
    setCommitResult(null);
  }, []);

  const setImportModalOpen = useCallback((open: boolean) => {
    setImportModalOpenState(open);
    if (!open) invalidatePreview();
  }, [invalidatePreview]);

  const setSource = useCallback((nextSource: PortfolioImportSource) => {
    setSourceState(nextSource);
    invalidatePreview();
  }, [invalidatePreview]);

  const setSelectedBroker = useCallback((broker: string) => {
    setSelectedBrokerState(broker);
    invalidatePreview();
  }, [invalidatePreview]);

  const setFile = useCallback((nextFile: File | null) => {
    setFileState(nextFile);
    invalidatePreview();
  }, [invalidatePreview]);

  const setFutuAsOf = useCallback((asOf: string) => {
    setFutuAsOfState(asOf);
    invalidatePreview();
  }, [invalidatePreview]);

  const loadBrokers = useCallback(async () => {
    try {
      const response = await portfolioApi.listImportBrokers();
      const brokerItems = response.brokers || [];
      if (brokerItems.length === 0) {
        setBrokers([]);
        setBrokerLoadWarning(importText.brokerListEmpty);
        setSelectedBrokerState('');
        return;
      }
      setBrokers(brokerItems);
      setBrokerLoadWarning(null);
      setSelectedBrokerState((current) => (
        brokerItems.some((item) => item.broker === current) ? current : brokerItems[0].broker
      ));
    } catch {
      setBrokers([]);
      setBrokerLoadWarning(importText.brokerListUnavailable);
      setSelectedBrokerState('');
    }
  }, [importText.brokerListEmpty, importText.brokerListUnavailable]);

  const handlePreview = async (fileOverride?: File) => {
    const selectedFile = fileOverride ?? file;
    if (source === 'file' && (!selectedFile || !selectedBroker)) return;
    if (previewPendingRef.current) return;
    const generation = previewGenerationRef.current;
    previewPendingRef.current = true;
    setIsPreviewing(true);
    setError(null);
    try {
      const parsed = source === 'futu'
        ? await portfolioApi.previewFutuImport(futuAsOf || undefined)
        : await portfolioApi.parseCsvImport(selectedBroker, selectedFile!);
      if (previewGenerationRef.current !== generation) return;
      setPreviewResult(parsed);
      setCommitResult(null);
    } catch (previewError) {
      if (previewGenerationRef.current !== generation) return;
      setError(getParsedApiError(previewError));
    } finally {
      if (previewGenerationRef.current === generation) {
        previewPendingRef.current = false;
        setIsPreviewing(false);
      }
    }
  };

  const handleCommit = async (): Promise<'preview_stale' | void> => {
    if (!previewResult) return;
    if (!writableAccountId) {
      setWriteWarning(text.selectAccountWrite);
      return;
    }
    try {
      setWriteWarning(null);
      setError(null);
      if (source === 'futu') {
        const snapshotId = (previewResult as PortfolioFutuImportPreviewResponse).snapshotId;
        if (!snapshotId) return;
        await commitFutu(
          {
            accountId: writableAccountId,
            asOf: futuAsOf || undefined,
            dryRun,
            expectedSnapshotId: snapshotId,
          },
          setCommitResult,
        );
      } else if (file && selectedBroker) {
        await commitCsv(
          {
            accountId: writableAccountId,
            broker: selectedBroker,
            file,
            dryRun,
          },
          setCommitResult,
        );
      }
    } catch (commitError) {
      const parsedError = getParsedApiError(commitError);
      const previewStale = source === 'futu'
        && parsedError.code === 'portfolio_import_preview_stale';
      if (previewStale) {
        invalidatePreview();
      }
      setError(parsedError);
      if (previewStale) return 'preview_stale';
    }
  };

  return {
    importModalOpen,
    setImportModalOpen,
    source,
    setSource,
    brokers,
    selectedBroker,
    setSelectedBroker,
    file,
    setFile,
    futuAsOf,
    setFutuAsOf,
    dryRun,
    setDryRun,
    isPreviewing,
    error,
    setError,
    previewResult,
    previewSnapshotId: source === 'futu'
      ? (previewResult as PortfolioFutuImportPreviewResponse | null)?.snapshotId
      : undefined,
    setPreviewResult,
    commitResult,
    setCommitResult,
    brokerLoadWarning,
    fileInputRef,
    loadBrokers,
    handlePreview,
    handleCommit,
  };
}
