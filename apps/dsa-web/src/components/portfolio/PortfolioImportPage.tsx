// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useEffect } from 'react';
import { usePortfolioImportSession } from '../../hooks/portfolio/usePortfolioImportSession';
import type { PortfolioFileText, PortfolioText } from '../../hooks/portfolio/types';
import type { UiLanguage } from '../../i18n/uiText';
import type { usePortfolioLedgerMutationWorkflow } from '../../hooks/portfolio/usePortfolioLedgerMutationWorkflow';
import PortfolioImportWizard from './PortfolioImportWizard';

type MutationWorkflow = ReturnType<typeof usePortfolioLedgerMutationWorkflow>;

type PortfolioImportPageProps = {
  text: PortfolioText;
  fileText: PortfolioFileText;
  language: UiLanguage;
  writableAccountId: number | undefined;
  setWriteWarning: (warning: string | null) => void;
  commitCsv: MutationWorkflow['commitCsv'];
  commitFutu: MutationWorkflow['commitFutu'];
  importCommitting: boolean;
  commonCancelLabel: string;
  commonCloseLabel: string;
  onClose: () => void;
};

const PortfolioImportPage: React.FC<PortfolioImportPageProps> = ({
  text,
  fileText,
  language,
  writableAccountId,
  setWriteWarning,
  commitCsv,
  commitFutu,
  importCommitting,
  commonCancelLabel,
  commonCloseLabel,
  onClose,
}) => {
  const {
    importSource, setImportSource,
    brokers, selectedBroker, setSelectedBroker,
    csvFile, setCsvFile,
    futuAsOf, setFutuAsOf,
    importDryRun, setImportDryRun,
    importParsing, importError, setImportError,
    importParseResult, setImportParseResult,
    importCommitResult, setImportCommitResult,
    brokerLoadWarning, csvInputRef,
    loadBrokers, handlePreviewImport, handleCommitImport,
  } = usePortfolioImportSession({
    text,
    writableAccountId,
    setWriteWarning,
    commitCsv,
    commitFutu,
  });

  useEffect(() => {
    void loadBrokers();
  }, [loadBrokers]);

  return (
    <PortfolioImportWizard
      text={text}
      fileText={fileText}
      language={language}
      writableAccountId={writableAccountId}
      importSource={importSource}
      setImportSource={setImportSource}
      brokers={brokers}
      selectedBroker={selectedBroker}
      setSelectedBroker={setSelectedBroker}
      brokerLoadWarning={brokerLoadWarning}
      csvFile={csvFile}
      setCsvFile={setCsvFile}
      csvInputRef={csvInputRef}
      futuAsOf={futuAsOf}
      setFutuAsOf={setFutuAsOf}
      importDryRun={importDryRun}
      setImportDryRun={setImportDryRun}
      importParsing={importParsing}
      importCommitting={importCommitting}
      importError={importError}
      setImportError={setImportError}
      importParseResult={importParseResult}
      setImportParseResult={setImportParseResult}
      importCommitResult={importCommitResult}
      setImportCommitResult={setImportCommitResult}
      onPreview={handlePreviewImport}
      onCommit={handleCommitImport}
      onClose={() => {
        setImportError(null);
        onClose();
      }}
      commonCancelLabel={commonCancelLabel}
      commonCloseLabel={commonCloseLabel}
    />
  );
};

export default PortfolioImportPage;
