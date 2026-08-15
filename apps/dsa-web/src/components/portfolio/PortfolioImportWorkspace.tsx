// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Lazy portfolio import workflow composition.

import type React from 'react';
import { useEffect } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { usePortfolioImportMutationWorkflow } from '../../hooks/portfolio/usePortfolioImportMutationWorkflow';
import { usePortfolioImportSession } from '../../hooks/portfolio/usePortfolioImportSession';
import { PORTFOLIO_FILE_TEXT, PORTFOLIO_TEXT } from '../../locales/portfolio';
import PortfolioImportWizard from './PortfolioImportWizard';
import { usePortfolioImportText } from './usePortfolioImportText';

type PortfolioImportWorkspaceProps = {
  writableAccountId: number | undefined;
  setWriteWarning: (warning: string | null) => void;
  refreshPortfolioData: () => Promise<void>;
  onClose: () => void;
};

const PortfolioImportWorkspace: React.FC<PortfolioImportWorkspaceProps> = ({
  writableAccountId,
  setWriteWarning,
  refreshPortfolioData,
  onClose,
}) => {
  const { language, t } = useUiLanguage();
  const text = PORTFOLIO_TEXT[language];
  const fileText = PORTFOLIO_FILE_TEXT[language];
  const importText = usePortfolioImportText(language);
  const mutation = usePortfolioImportMutationWorkflow({ refreshPortfolioData });
  const session = usePortfolioImportSession({
    text,
    importText,
    writableAccountId,
    setWriteWarning,
    commitCsv: mutation.commitCsv,
    commitFutu: mutation.commitFutu,
  });
  const { loadBrokers } = session;

  useEffect(() => {
    void loadBrokers();
  }, [loadBrokers]);

  return (
    <PortfolioImportWizard
      text={text}
      importText={importText}
      fileText={fileText}
      language={language}
      writableAccountId={writableAccountId}
      importSource={session.source}
      setImportSource={session.setSource}
      brokers={session.brokers}
      selectedBroker={session.selectedBroker}
      setSelectedBroker={session.setSelectedBroker}
      brokerLoadWarning={session.brokerLoadWarning}
      csvFile={session.file}
      setCsvFile={session.setFile}
      csvInputRef={session.fileInputRef}
      futuAsOf={session.futuAsOf}
      setFutuAsOf={session.setFutuAsOf}
      previewSnapshotId={session.previewSnapshotId}
      csvDryRun={session.dryRun}
      setCsvDryRun={session.setDryRun}
      csvParsing={session.isPreviewing}
      csvCommitting={mutation.csvCommitting || mutation.futuCommitting}
      csvError={session.error}
      setCsvError={session.setError}
      csvParseResult={session.previewResult}
      setCsvParseResult={session.setPreviewResult}
      csvCommitResult={session.commitResult}
      setCsvCommitResult={session.setCommitResult}
      onParse={session.handlePreview}
      onCommit={session.handleCommit}
      onClose={() => {
        session.setError(null);
        session.setImportModalOpen(false);
        onClose();
      }}
      commonCancelLabel={t('common.cancel')}
      commonCloseLabel={t('common.close')}
    />
  );
};

export default PortfolioImportWorkspace;
