// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Full-page portfolio CSV import wizard (#872 / #877 surface contract).

import type React from 'react';
import { useMemo, useState } from 'react';
import { X } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import type {
  PortfolioImportBrokerItem,
  PortfolioImportCommitResponse,
  PortfolioImportFailedRow,
  PortfolioImportParseResponse,
  PortfolioImportSource,
  PortfolioImportTradeItem,
} from '../../types/portfolio';
import {
  buildFailedRowsCsv,
  downloadTextFile,
  formatBrokerLabel,
  getCsvCommitVariant,
  getCsvParseVariant,
} from './portfolioImportFailedRows';
import { formatUiText } from '../../i18n/uiText';
import type { UiLanguage } from '../../i18n/uiText';
import { PORTFOLIO_FUTU_IMPORT_TEXT } from '../../locales/portfolioFutuImport';
import {
  ApiErrorAlert,
  Button,
  Card,
  Checkbox,
  DataTable,
  type DataTableColumn,
  FileInput,
  IconButton,
  InlineAlert,
  Input,
  PageHeader,
  SegmentedControl,
  Select,
  StickyActionBar,
  Textarea,
} from '../common';
import type { PortfolioFileText, PortfolioText } from '../../hooks/portfolio/types';

const IMPORT_WIZARD_STEPS = [
  'format',
  'upload',
  'mapping',
  'validate',
  'confirm',
] as const;

type ImportWizardStep = (typeof IMPORT_WIZARD_STEPS)[number];

type PortfolioImportWizardProps = {
  text: PortfolioText;
  fileText: PortfolioFileText;
  language: UiLanguage;
  writableAccountId: number | undefined;
  importSource: PortfolioImportSource;
  setImportSource: (source: PortfolioImportSource) => void;
  brokers: PortfolioImportBrokerItem[];
  selectedBroker: string;
  setSelectedBroker: (broker: string) => void;
  brokerLoadWarning: string | null;
  csvFile: File | null;
  setCsvFile: (file: File | null) => void;
  csvInputRef: React.RefObject<HTMLInputElement | null>;
  futuAsOf: string;
  setFutuAsOf: (value: string) => void;
  importDryRun: boolean;
  setImportDryRun: (value: boolean) => void;
  importParsing: boolean;
  importCommitting: boolean;
  importError: ParsedApiError | null;
  setImportError: (error: ParsedApiError | null) => void;
  importParseResult: PortfolioImportParseResponse | null;
  setImportParseResult: (result: PortfolioImportParseResponse | null) => void;
  importCommitResult: PortfolioImportCommitResponse | null;
  setImportCommitResult: (result: PortfolioImportCommitResponse | null) => void;
  onPreview: (file?: File) => Promise<void> | void;
  onCommit: () => Promise<void> | void;
  onClose: () => void;
  commonCancelLabel: string;
  commonCloseLabel: string;
};

function buildPastedCsvFile(content: string): File {
  return new File([content], 'pasted-import.csv', { type: 'text/csv' });
}

const PortfolioImportWizard: React.FC<PortfolioImportWizardProps> = ({
  text,
  fileText,
  language,
  writableAccountId,
  importSource,
  setImportSource,
  brokers,
  selectedBroker,
  setSelectedBroker,
  brokerLoadWarning,
  csvFile,
  setCsvFile,
  csvInputRef,
  futuAsOf,
  setFutuAsOf,
  importDryRun,
  setImportDryRun,
  importParsing,
  importCommitting,
  importError,
  setImportError,
  importParseResult,
  setImportParseResult,
  importCommitResult,
  setImportCommitResult,
  onPreview,
  onCommit,
  onClose,
  commonCancelLabel,
  commonCloseLabel,
}) => {
  const [step, setStep] = useState<ImportWizardStep>('format');
  const [pasteText, setPasteText] = useState('');
  const futuText = PORTFOLIO_FUTU_IMPORT_TEXT[language];
  const busy = importParsing || importCommitting;

  const stepIndex = IMPORT_WIZARD_STEPS.indexOf(step);
  const stepLabels: Record<ImportWizardStep, string> = {
    format: text.importWizardStepFormat,
    upload: importSource === 'futu' ? futuText.previewStep : text.importWizardStepUpload,
    mapping: text.importWizardStepMapping,
    validate: text.importWizardStepValidate,
    confirm: text.importWizardStepConfirm,
  };

  const mappingColumns = useMemo<DataTableColumn<PortfolioImportTradeItem>[]>(() => [
    {
      id: 'tradeDate',
      header: text.tradeDate,
      cell: (row) => row.tradeDate,
      width: 'compact',
    },
    {
      id: 'symbol',
      header: text.code,
      cell: (row) => row.symbol,
      width: 'compact',
    },
    {
      id: 'side',
      header: text.side,
      cell: (row) => row.side,
      width: 'compact',
    },
    {
      id: 'quantity',
      header: text.quantity,
      cell: (row) => String(row.quantity),
      width: 'compact',
    },
    {
      id: 'price',
      header: text.tradePrice,
      cell: (row) => String(row.price),
      width: 'compact',
    },
  ], [text.code, text.quantity, text.side, text.tradeDate, text.tradePrice]);

  const failedRows = useMemo<PortfolioImportFailedRow[]>(
    () => (importParseResult?.failedRows && importParseResult.failedRows.length > 0
      ? importParseResult.failedRows
      : []),
    [importParseResult],
  );

  const failedRowColumns = useMemo<DataTableColumn<PortfolioImportFailedRow>[]>(() => [
    {
      id: 'rowNumber',
      header: text.importWizardFailedRowNumber,
      cell: (row) => String(row.rowNumber),
      width: 'compact',
    },
    {
      id: 'reasonCode',
      header: text.importWizardFailedRowCode,
      cell: (row) => row.reasonCode,
      width: 'compact',
    },
    {
      id: 'reason',
      header: text.importWizardFailedRowReason,
      cell: (row) => row.reason,
    },
  ], [
    text.importWizardFailedRowCode,
    text.importWizardFailedRowNumber,
    text.importWizardFailedRowReason,
  ]);

  const canAdvanceFromFormat = importSource === 'futu'
    || (Boolean(selectedBroker) && brokers.length > 0);
  const canAdvanceFromUpload = importSource === 'futu'
    || Boolean(csvFile)
    || pasteText.trim().length > 0;
  const hasParseErrors = Boolean(
    importParseResult
    && (importParseResult.errorCount > 0 || failedRows.length > 0),
  );
  const hasPartialCommit = Boolean(
    importCommitResult
    && !importCommitResult.dryRun
    && importCommitResult.failedCount > 0
    && importCommitResult.insertedCount > 0,
  );
  const canCommitImport = Boolean(
    writableAccountId
    && importParseResult
    && (importSource === 'file' || importParseResult.recordCount > 0)
    && (importSource === 'futu' || (selectedBroker && csvFile)),
  );

  const downloadFailedRows = () => {
    if (failedRows.length === 0) return;
    const csv = buildFailedRowsCsv(failedRows);
    const stamp = new Date().toISOString().slice(0, 10);
    downloadTextFile(`portfolio-import-failed-rows-${stamp}.csv`, csv);
  };

  const goNext = () => {
    if (busy) return;
    if (step === 'format') {
      if (!canAdvanceFromFormat) return;
      setStep('upload');
      return;
    }
    if (step === 'upload') {
      if (!canAdvanceFromUpload) return;
      if (importSource === 'futu') {
        setStep('mapping');
        void onPreview();
        return;
      }
      let fileToParse = csvFile;
      if (!fileToParse && pasteText.trim()) {
        fileToParse = buildPastedCsvFile(pasteText.trim());
        setCsvFile(fileToParse);
        setImportParseResult(null);
        setImportCommitResult(null);
      }
      setStep('mapping');
      if (fileToParse) void onPreview(fileToParse);
      return;
    }
    if (step === 'mapping') {
      if (!importParseResult) return;
      setStep('validate');
      return;
    }
    if (step === 'validate') {
      setStep('confirm');
    }
  };

  const goBack = () => {
    if (busy) return;
    if (stepIndex <= 0) {
      onClose();
      return;
    }
    setStep(IMPORT_WIZARD_STEPS[stepIndex - 1]);
  };

  const handleFileChange = (file: File | null) => {
    setCsvFile(file);
    setImportParseResult(null);
    setImportCommitResult(null);
    if (file) setPasteText('');
  };

  const handlePasteChange = (value: string) => {
    setPasteText(value);
    if (value.trim()) {
      setCsvFile(buildPastedCsvFile(value));
      setImportParseResult(null);
      setImportCommitResult(null);
      if (csvInputRef.current) csvInputRef.current.value = '';
    } else if (!csvInputRef.current?.files?.length) {
      setCsvFile(null);
      setImportParseResult(null);
      setImportCommitResult(null);
    }
  };

  const handleReparse = async () => {
    if (importSource === 'futu') {
      setImportCommitResult(null);
      await onPreview();
      return;
    }
    let fileToParse = csvFile;
    if (!fileToParse && pasteText.trim()) {
      fileToParse = buildPastedCsvFile(pasteText.trim());
      setCsvFile(fileToParse);
    }
    setImportCommitResult(null);
    await onPreview(fileToParse ?? undefined);
  };

  return (
    <div
      role="region"
      aria-label={text.importWizardTitle}
      data-pattern="wizard"
      className="space-y-4"
    >
      <PageHeader
        title={text.importWizardTitle}
        description={text.importWizardDescription}
        actions={(
          <IconButton
            type="button"
            variant="ghost"
            size="default"
            aria-label={commonCloseLabel}
            disabled={busy}
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </IconButton>
        )}
      />

      <nav aria-label={text.importWizardStepsLabel} className="flex flex-wrap gap-2">
        {IMPORT_WIZARD_STEPS.map((id, index) => {
          const active = id === step;
          const done = index < stepIndex;
          return (
            <span
              key={id}
              data-wizard-step={id}
              data-active={active || undefined}
              className={[
                'inline-flex min-h-9 items-center rounded-full border px-3 text-xs font-medium',
                active ? 'border-primary bg-primary/10 text-primary' : '',
                done && !active ? 'border-border bg-subtle-soft text-secondary-text' : '',
                !active && !done ? 'border-border text-muted-text' : '',
              ].filter(Boolean).join(' ')}
            >
              {index + 1}. {stepLabels[id]}
            </span>
          );
        })}
      </nav>

      <fieldset
        disabled={busy}
        aria-busy={busy}
        className="m-0 min-w-0 space-y-3 border-0 p-0"
      >
        {importSource === 'file' && brokerLoadWarning ? (
          <InlineAlert variant="warning" size="compact" message={brokerLoadWarning} />
        ) : null}

        {step === 'format' ? (
          <Card padding="md" className="space-y-3">
            <SegmentedControl
              value={importSource}
              semantics="single-select"
              ariaLabel={futuText.sourceLabel}
              onChange={setImportSource}
              options={[
                { value: 'file', label: futuText.fileSource },
                { value: 'futu', label: futuText.futuSource },
              ]}
            />
            <p className="text-sm text-secondary-text">
              {importSource === 'futu' ? futuText.futuDescription : futuText.fileDescription}
            </p>
            {importSource === 'file' ? (
              <Select
                label={text.broker}
                value={selectedBroker}
                onChange={(value) => {
                  setSelectedBroker(value);
                  setImportCommitResult(null);
                  setImportParseResult(null);
                }}
                disabled={busy || brokers.length === 0}
                options={brokers.map((item) => ({
                  value: item.broker,
                  label: formatBrokerLabel(item.broker, item.displayName, language),
                }))}
              />
            ) : null}
          </Card>
        ) : null}

        {step === 'upload' ? (
          <Card padding="md" className="space-y-3">
            {importSource === 'futu' ? (
              <>
                <p className="text-sm text-secondary-text">{futuText.futuDescription}</p>
                <Input
                  type="date"
                  label={futuText.futuAsOf}
                  hint={futuText.futuAsOfHint}
                  value={futuAsOf}
                  onChange={(event) => {
                    setFutuAsOf(event.target.value);
                    setImportParseResult(null);
                    setImportCommitResult(null);
                  }}
                />
              </>
            ) : (
              <>
            <div className="grid gap-1">
              <span className="block text-xs text-muted-text">{text.csvFile}</span>
              <Button
                type="button"
                variant="secondary"
                size="primary"
                disabled={busy || brokers.length === 0}
                onClick={() => csvInputRef.current?.click()}
              >
                {text.chooseCsv}
              </Button>
              <FileInput
                ref={csvInputRef}
                accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                aria-label={text.chooseCsv}
                disabled={busy || brokers.length === 0}
                onChange={(e) => {
                  handleFileChange(
                    e.target.files && e.target.files[0] ? e.target.files[0] : null,
                  );
                }}
              />
              {csvFile && !pasteText ? (
                <div className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-subtle-soft px-2 py-1.5">
                  <span className="min-w-0 flex-1 truncate text-xs text-foreground">{csvFile.name}</span>
                  <span className="shrink-0 text-xs text-muted-text">
                    {formatUiText(fileText.size, { size: Math.max(0.1, csvFile.size / 1024).toFixed(1) })}
                  </span>
                  <IconButton
                    type="button"
                    variant="ghost"
                    size="default"
                    aria-label={fileText.clear}
                    onClick={() => {
                      handleFileChange(null);
                      if (csvInputRef.current) csvInputRef.current.value = '';
                    }}
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </IconButton>
                </div>
              ) : null}
            </div>
            <Textarea
              label={text.importWizardPasteLabel}
              hint={text.importWizardPasteHint}
              value={pasteText}
              onChange={(event) => handlePasteChange(event.target.value)}
              rows={8}
              className="font-mono text-xs"
            />
              </>
            )}
          </Card>
        ) : null}

        {step === 'mapping' ? (
          <Card padding="md" className="space-y-3">
            <p className="text-sm text-secondary-text">
              {importSource === 'futu' ? futuText.futuDescription : text.importWizardMappingHelp}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                size="comfortable"
                disabled={importSource === 'file'
                  ? (!selectedBroker || (!csvFile && !pasteText.trim()) || importCommitting)
                  : importCommitting}
                isLoading={importParsing}
                loadingText={importSource === 'futu' ? futuText.previewing : text.parsing}
                onClick={() => void handleReparse()}
              >
                {importSource === 'futu' ? futuText.preview : text.parseFile}
              </Button>
            </div>
            {importParseResult ? (
              <>
                <InlineAlert
                  variant={getCsvParseVariant(importParseResult)}
                  size="compact"
                  title={importSource === 'futu' ? futuText.previewResult : text.csvParseResult}
                  message={formatUiText(text.csvParseSummary, {
                    valid: importParseResult.recordCount,
                    skipped: importParseResult.skippedCount,
                    errors: importParseResult.errorCount,
                  })}
                />
                {importParseResult.records.length > 0 ? (
                  <DataTable<PortfolioImportTradeItem>
                    caption={text.importWizardMappingTitle}
                    columns={mappingColumns}
                    rows={importParseResult.records.slice(0, 50)}
                    getRowKey={(row, index) => `${row.dedupHash}-${index}`}
                    emptyState={{
                      title: text.importWizardMappingEmpty,
                    }}
                    density="compact"
                    minWidth="wide"
                  />
                ) : (
                  <InlineAlert
                    variant="warning"
                    size="compact"
                    message={importSource === 'futu' ? futuText.previewEmpty : text.importWizardMappingEmpty}
                  />
                )}
              </>
            ) : (
              <InlineAlert
                variant="info"
                size="compact"
                message={importSource === 'futu' ? futuText.previewRequired : text.importWizardMappingEmpty}
              />
            )}
          </Card>
        ) : null}

        {step === 'validate' ? (
          <Card padding="md" className="space-y-3">
            <p className="text-sm text-secondary-text">{text.importWizardValidateHelp}</p>
            {importParseResult ? (
              <InlineAlert
                variant={getCsvParseVariant(importParseResult)}
                size="compact"
                title={importSource === 'futu' ? futuText.previewResult : text.csvParseResult}
                message={formatUiText(text.csvParseSummary, {
                  valid: importParseResult.recordCount,
                  skipped: importParseResult.skippedCount,
                  errors: importParseResult.errorCount,
                })}
              />
            ) : null}
            {hasParseErrors && importParseResult ? (
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-foreground">{text.importWizardRowErrors}</h3>
                {failedRows.length > 0 ? (
                  <DataTable<PortfolioImportFailedRow>
                    caption={text.importWizardFailedRowsTitle}
                    columns={failedRowColumns}
                    rows={failedRows.slice(0, 50)}
                    getRowKey={(row) => `${row.rowNumber}-${row.reasonCode}`}
                    emptyState={{ title: text.importWizardRowErrors }}
                    density="compact"
                    minWidth="wide"
                  />
                ) : null}
                {importParseResult.errors.length > 0 ? (
                  <ul className="max-h-48 list-disc space-y-1 overflow-auto pl-5 text-xs text-secondary-text">
                    {importParseResult.errors.map((error) => (
                      <li key={error}>{error}</li>
                    ))}
                  </ul>
                ) : null}
                <InlineAlert
                  variant="warning"
                  size="compact"
                  message={text.importWizardRetryHint}
                />
                <div className="flex flex-wrap gap-2">
                  {failedRows.length > 0 ? (
                    <Button
                      type="button"
                      variant="secondary"
                      size="comfortable"
                      onClick={downloadFailedRows}
                    >
                      {text.importWizardDownloadFailedRows}
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    variant="secondary"
                    size="comfortable"
                    onClick={() => setStep('upload')}
                  >
                    {text.importWizardContinueEdit}
                  </Button>
                </div>
              </div>
            ) : importSource === 'futu' && importParseResult?.recordCount === 0 ? (
              <InlineAlert
                variant="warning"
                size="compact"
                message={futuText.previewEmpty}
              />
            ) : (
              <InlineAlert
                variant="success"
                size="compact"
                message={text.importWizardNoErrors}
              />
            )}
          </Card>
        ) : null}

        {step === 'confirm' ? (
          <Card padding="md" className="space-y-3">
            <p className="text-sm text-secondary-text">{text.importWizardConfirmHelp}</p>
            {!writableAccountId ? (
              <InlineAlert variant="warning" size="compact" message={text.selectAccountWrite} />
            ) : null}
            {!importParseResult || (importSource === 'futu' && importParseResult.recordCount <= 0) ? (
              <InlineAlert
                variant="warning"
                size="compact"
                message={importSource === 'futu' ? futuText.previewRequired : text.importWizardMappingEmpty}
              />
            ) : null}
            <Checkbox
              id="import-dry-run"
              checked={importDryRun}
              onChange={(event) => {
                setImportDryRun(event.target.checked);
              }}
              containerClassName="min-h-11 text-xs text-secondary"
              label={<span className="text-xs font-normal text-secondary-text">{text.dryRun}</span>}
            />
            <Button
              type="button"
              variant="secondary"
              size="comfortable"
              disabled={!canCommitImport || importParsing}
              isLoading={importCommitting}
              loadingText={text.submitting}
              onClick={() => void onCommit()}
            >
              {text.commitImport}
            </Button>
            {importCommitResult ? (
              <>
                <InlineAlert
                  variant={getCsvCommitVariant(importCommitResult, importCommitResult.dryRun)}
                  size="compact"
                  title={
                    hasPartialCommit
                      ? text.importWizardPartialTitle
                      : (importCommitResult.dryRun ? text.csvDryResult : text.csvCommitResult)
                  }
                  message={formatUiText(text.csvCommitSummary, {
                    mode: importCommitResult.dryRun ? text.dryCheck : text.actualWrite,
                    inserted: importCommitResult.insertedCount,
                    duplicates: importCommitResult.duplicateCount,
                    failed: importCommitResult.failedCount,
                  })}
                />
                {importCommitResult.errors.length > 0 ? (
                  <ul className="max-h-48 list-disc space-y-1 overflow-auto pl-5 text-xs text-secondary-text">
                    {importCommitResult.errors.map((error) => (
                      <li key={error}>{error}</li>
                    ))}
                  </ul>
                ) : null}
                {hasPartialCommit ? (
                  <div className="space-y-2">
                    <InlineAlert
                      variant="warning"
                      size="compact"
                      message={text.importWizardPartialHelp}
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      size="comfortable"
                      onClick={() => setStep('upload')}
                    >
                      {text.importWizardContinueEdit}
                    </Button>
                  </div>
                ) : null}
              </>
            ) : null}
          </Card>
        ) : null}

        {importError ? (
          <ApiErrorAlert error={importError} onDismiss={() => setImportError(null)} />
        ) : null}
      </fieldset>

      <StickyActionBar>
        <Button
          type="button"
          variant="secondary"
          size="comfortable"
          disabled={busy}
          onClick={goBack}
        >
          {stepIndex === 0 ? commonCancelLabel : text.importWizardBack}
        </Button>
        {step !== 'confirm' ? (
          <Button
            type="button"
            variant="primary"
            size="comfortable"
            disabled={
              busy
              || (step === 'format' && !canAdvanceFromFormat)
              || (step === 'upload' && !canAdvanceFromUpload)
              || (step === 'mapping' && !importParseResult)
            }
            isLoading={step === 'mapping' && importParsing}
            loadingText={importSource === 'futu' ? futuText.previewing : text.parsing}
            onClick={goNext}
          >
            {text.importWizardNext}
          </Button>
        ) : (
          <Button
            type="button"
            variant="primary"
            size="comfortable"
            disabled={busy}
            onClick={onClose}
          >
            {text.importWizardDone}
          </Button>
        )}
      </StickyActionBar>
    </div>
  );
};

export default PortfolioImportWizard;
