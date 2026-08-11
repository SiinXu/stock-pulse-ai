/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useRef, useState } from 'react';
import type { ParsedApiError } from '../../api/error';
import { PortfolioImportWizard } from '../../components/portfolio/PortfolioImportWizard';
import { ReasoningTraceExportControls } from '../../components/report/ReasoningTraceExportControls';
import { PORTFOLIO_FILE_TEXT, PORTFOLIO_TEXT } from '../../locales/portfolio';
import type {
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
} from '../../types/portfolio';
import type { PlaygroundScenarioRenderer } from '../types';

const PortfolioImportWizardStory = () => {
  const [selectedBroker, setSelectedBroker] = useState('demo');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvDryRun, setCsvDryRun] = useState(true);
  const [csvError, setCsvError] = useState<ParsedApiError | null>(null);
  const [csvParseResult, setCsvParseResult] = useState<PortfolioImportParseResponse | null>(null);
  const [csvCommitResult, setCsvCommitResult] = useState<PortfolioImportCommitResponse | null>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);

  return (
    <PortfolioImportWizard
      text={PORTFOLIO_TEXT.en}
      fileText={PORTFOLIO_FILE_TEXT.en}
      language="en"
      writableAccountId={1}
      brokers={[{ broker: 'demo', aliases: [], displayName: 'Demo broker' }]}
      selectedBroker={selectedBroker}
      setSelectedBroker={setSelectedBroker}
      brokerLoadWarning={null}
      csvFile={csvFile}
      setCsvFile={setCsvFile}
      csvInputRef={csvInputRef}
      csvDryRun={csvDryRun}
      setCsvDryRun={setCsvDryRun}
      csvParsing={false}
      csvCommitting={false}
      csvError={csvError}
      setCsvError={setCsvError}
      csvParseResult={csvParseResult}
      setCsvParseResult={setCsvParseResult}
      csvCommitResult={csvCommitResult}
      setCsvCommitResult={setCsvCommitResult}
      onParse={() => undefined}
      onCommit={() => undefined}
      onClose={() => undefined}
      commonCancelLabel="Cancel"
      commonCloseLabel="Close"
    />
  );
};

const ReasoningTraceExportControlsStory = () => (
  <div className="max-w-2xl">
    <ReasoningTraceExportControls recordId={101} variant="section" disabled />
  </div>
);

export const ADDITIONAL_PRODUCT_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'portfolio-import-wizard': PortfolioImportWizardStory,
  'reasoning-trace-export-controls': ReasoningTraceExportControlsStory,
};
