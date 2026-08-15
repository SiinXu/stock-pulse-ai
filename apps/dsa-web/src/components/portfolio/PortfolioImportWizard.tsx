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
import {
  ApiErrorAlert,
  Button,
  Card,
  Checkbox,
  DataTable,
  type DataTableColumn,
  DatePicker,
  FileInput,
  IconButton,
  InlineAlert,
  PageHeader,
  SegmentedControl,
  Select,
  StickyActionBar,
  Textarea,
} from '../common';
import type { PortfolioFileText, PortfolioText } from '../../hooks/portfolio/types';
import type { PortfolioImportText } from '../../locales/portfolioImport';

const IMPORT_WIZARD_STEPS = [
  'format',
  'upload',
  'mapping',
  'validate',
  'confirm',
] as const;

type ImportWizardStep = (typeof IMPORT_WIZARD_STEPS)[number];
type PortfolioImportCommitOutcome = 'preview_stale' | void;

type PortfolioImportWizardProps = {
  text: PortfolioText;
  importText: PortfolioImportText;
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
  setFutuAsOf: (asOf: string) => void;
  previewSnapshotId?: string;
  csvDryRun: boolean;
  setCsvDryRun: (value: boolean) => void;
  csvParsing: boolean;
  csvCommitting: boolean;
  csvError: ParsedApiError | null;
  setCsvError: (error: ParsedApiError | null) => void;
  csvParseResult: PortfolioImportParseResponse | null;
  setCsvParseResult: (result: PortfolioImportParseResponse | null) => void;
  csvCommitResult: PortfolioImportCommitResponse | null;
  setCsvCommitResult: (result: PortfolioImportCommitResponse | null) => void;
  onParse: (file?: File) => Promise<void> | void;
  onCommit: () => Promise<PortfolioImportCommitOutcome> | PortfolioImportCommitOutcome;
  onClose: () => void;
  commonCancelLabel: string;
  commonCloseLabel: string;
};

function buildPastedCsvFile(content: string): File {
  return new File([content], 'pasted-import.csv', { type: 'text/csv' });
}

const PortfolioImportWizard: React.FC<PortfolioImportWizardProps> = ({
  text,
  importText,
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
  previewSnapshotId,
  csvDryRun,
  setCsvDryRun,
  csvParsing,
  csvCommitting,
  csvError,
  setCsvError,
  csvParseResult,
  setCsvParseResult,
  csvCommitResult,
  setCsvCommitResult,
  onParse,
  onCommit,
  onClose,
  commonCancelLabel,
  commonCloseLabel,
}) => {
  const [step, setStep] = useState<ImportWizardStep>('format');
  const [pasteText, setPasteText] = useState('');
  const busy = csvParsing || csvCommitting;

  const stepIndex = IMPORT_WIZARD_STEPS.indexOf(step);
  const stepLabels: Record<ImportWizardStep, string> = {
    format: importText.source,
    upload: importSource === 'futu' ? importText.futuAsOf : importText.importWizardStepUpload,
    mapping: importSource === 'futu' ? importText.preview : importText.importWizardStepMapping,
    validate: importText.importWizardStepValidate,
    confirm: importText.importWizardStepConfirm,
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
    () => (csvParseResult?.failedRows && csvParseResult.failedRows.length > 0
      ? csvParseResult.failedRows
      : []),
    [csvParseResult],
  );

  const failedRowColumns = useMemo<DataTableColumn<PortfolioImportFailedRow>[]>(() => [
    {
      id: 'rowNumber',
      header: importText.importWizardFailedRowNumber,
      cell: (row) => String(row.rowNumber),
      width: 'compact',
    },
    {
      id: 'reasonCode',
      header: importText.importWizardFailedRowCode,
      cell: (row) => row.reasonCode,
      width: 'compact',
    },
    {
      id: 'reason',
      header: importText.importWizardFailedRowReason,
      cell: (row) => row.reason,
    },
  ], [
    importText.importWizardFailedRowCode,
    importText.importWizardFailedRowNumber,
    importText.importWizardFailedRowReason,
  ]);

  const canAdvanceFromFormat = importSource === 'futu'
    || (Boolean(selectedBroker) && brokers.length > 0);
  const canAdvanceFromUpload = importSource === 'futu'
    ? Boolean(futuAsOf)
    : Boolean(csvFile) || pasteText.trim().length > 0;
  const hasParseErrors = Boolean(
    csvParseResult
    && (csvParseResult.errorCount > 0 || failedRows.length > 0),
  );
  const hasPartialCommit = Boolean(
    csvCommitResult
    && !csvCommitResult.dryRun
    && csvCommitResult.failedCount > 0
    && csvCommitResult.insertedCount > 0,
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
        void onParse();
        return;
      }
      let fileToParse = csvFile;
      if (!fileToParse && pasteText.trim()) {
        fileToParse = buildPastedCsvFile(pasteText.trim());
        setCsvFile(fileToParse);
        setCsvParseResult(null);
        setCsvCommitResult(null);
      }
      setStep('mapping');
      if (fileToParse) void onParse(fileToParse);
      return;
    }
    if (step === 'mapping') {
      if (!csvParseResult) return;
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
    setCsvParseResult(null);
    setCsvCommitResult(null);
    if (file) setPasteText('');
  };

  const handlePasteChange = (value: string) => {
    setPasteText(value);
    if (value.trim()) {
      setCsvFile(buildPastedCsvFile(value));
      setCsvParseResult(null);
      setCsvCommitResult(null);
      if (csvInputRef.current) csvInputRef.current.value = '';
    } else if (!csvInputRef.current?.files?.length) {
      setCsvFile(null);
      setCsvParseResult(null);
      setCsvCommitResult(null);
    }
  };

  const handleReparse = async () => {
    if (importSource === 'futu') {
      setCsvCommitResult(null);
      await onParse();
      return;
    }
    let fileToParse = csvFile;
    if (!fileToParse && pasteText.trim()) {
      fileToParse = buildPastedCsvFile(pasteText.trim());
      setCsvFile(fileToParse);
    }
    setCsvCommitResult(null);
    await onParse(fileToParse ?? undefined);
  };

  const handleCommit = async () => {
    const outcome = await onCommit();
    if (outcome === 'preview_stale') setStep('mapping');
  };

  return (
    <div
      role="region"
      aria-label={importText.importWizardTitle}
      data-pattern="wizard"
      className="space-y-4"
    >
      <PageHeader
        title={importText.importWizardTitle}
        description={importText.description}
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

      <nav aria-label={importText.importWizardStepsLabel} className="flex flex-wrap gap-2">
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
        {brokerLoadWarning && importSource === 'file' ? (
          <InlineAlert variant="warning" size="compact" message={brokerLoadWarning} />
        ) : null}

        {step === 'format' ? (
          <Card padding="md" className="space-y-3">
            <SegmentedControl
              id="portfolio-import-source"
              value={importSource}
              ariaLabel={importText.source}
              semantics="single-select"
              onChange={setImportSource}
              options={[
                { value: 'file', label: importText.file },
                { value: 'futu', label: importText.futu },
              ]}
            />
            {importSource === 'file' ? (
              <>
                <p className="text-sm text-secondary-text">{importText.importWizardFormatHelp}</p>
                <Select
                  label={text.broker}
                  value={selectedBroker}
                  onChange={setSelectedBroker}
                  disabled={busy || brokers.length === 0}
                  options={brokers.map((item) => ({
                    value: item.broker,
                    label: formatBrokerLabel(item.broker, item.displayName, language),
                  }))}
                />
              </>
            ) : (
              <InlineAlert variant="info" size="compact" message={importText.futuHelp} />
            )}
          </Card>
        ) : null}

        {step === 'upload' ? (
          <Card padding="md" className="space-y-3">
            {importSource === 'futu' ? (
              <>
                <DatePicker
                  id="portfolio-futu-import-as-of"
                  label={importText.futuAsOf}
                  ariaDescribedBy="portfolio-futu-import-as-of-hint"
                  value={futuAsOf}
                  onChange={setFutuAsOf}
                  disabled={busy}
                />
                <p
                  id="portfolio-futu-import-as-of-hint"
                  className="text-xs text-secondary-text"
                >
                  {importText.futuAsOfHint}
                </p>
                <InlineAlert variant="info" size="compact" message={importText.previewRequired} />
              </>
            ) : (
              <>
                <div className="grid gap-1">
                  <span className="block text-xs text-muted-text">{importText.csvFile}</span>
                  <Button
                    type="button"
                    variant="secondary"
                    size="primary"
                    disabled={busy || brokers.length === 0}
                    onClick={() => csvInputRef.current?.click()}
                  >
                    {importText.chooseCsv}
                  </Button>
                  <FileInput
                    ref={csvInputRef}
                    accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    aria-label={importText.chooseCsv}
                    disabled={busy || brokers.length === 0}
                    onChange={(event) => {
                      handleFileChange(
                        event.target.files && event.target.files[0]
                          ? event.target.files[0]
                          : null,
                      );
                    }}
                  />
                  {csvFile && !pasteText ? (
                    <div className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-subtle-soft px-2 py-1.5">
                      <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                        {csvFile.name}
                      </span>
                      <span className="shrink-0 text-xs text-muted-text">
                        {formatUiText(fileText.size, {
                          size: Math.max(0.1, csvFile.size / 1024).toFixed(1),
                        })}
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
                  label={importText.importWizardPasteLabel}
                  hint={importText.importWizardPasteHint}
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
              {importSource === 'futu' ? importText.futuHelp : importText.importWizardMappingHelp}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                size="comfortable"
                disabled={
                  csvCommitting
                  || (importSource === 'file' && (
                    !selectedBroker || (!csvFile && !pasteText.trim())
                  ))
                  || (importSource === 'futu' && !futuAsOf)
                }
                isLoading={csvParsing}
                loadingText={importSource === 'futu' ? importText.previewing : importText.parsing}
                onClick={() => void handleReparse()}
              >
                {importSource === 'futu' ? importText.preview : importText.parseFile}
              </Button>
            </div>
            {csvParseResult ? (
              <>
                <InlineAlert
                  variant={getCsvParseVariant(csvParseResult)}
                  size="compact"
                  title={importSource === 'futu' ? importText.preview : importText.csvParseResult}
                  message={formatUiText(importText.csvParseSummary, {
                    valid: csvParseResult.recordCount,
                    skipped: csvParseResult.skippedCount,
                    errors: csvParseResult.errorCount,
                  })}
                />
                {previewSnapshotId ? (
                  <p className="break-all text-xs text-secondary-text">
                    {importText.snapshot}: {previewSnapshotId}
                  </p>
                ) : null}
                {csvParseResult.records.length > 0 ? (
                  <DataTable<PortfolioImportTradeItem>
                    caption={importText.importWizardMappingTitle}
                    columns={mappingColumns}
                    rows={csvParseResult.records.slice(0, 50)}
                    getRowKey={(row, index) => `${row.dedupHash}-${index}`}
                    emptyState={{
                      title: importText.importWizardMappingEmpty,
                    }}
                    density="compact"
                    minWidth="wide"
                  />
                ) : (
                  <InlineAlert
                    variant="warning"
                    size="compact"
                    message={importText.importWizardMappingEmpty}
                  />
                )}
              </>
            ) : (
              <InlineAlert
                variant="info"
                size="compact"
                message={importText.importWizardMappingEmpty}
              />
            )}
          </Card>
        ) : null}

        {step === 'validate' ? (
          <Card padding="md" className="space-y-3">
            <p className="text-sm text-secondary-text">{importText.importWizardValidateHelp}</p>
            {csvParseResult ? (
              <InlineAlert
                variant={getCsvParseVariant(csvParseResult)}
                size="compact"
                title={importSource === 'futu' ? importText.preview : importText.csvParseResult}
                message={formatUiText(importText.csvParseSummary, {
                  valid: csvParseResult.recordCount,
                  skipped: csvParseResult.skippedCount,
                  errors: csvParseResult.errorCount,
                })}
              />
            ) : null}
            {hasParseErrors && csvParseResult ? (
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-foreground">{importText.importWizardRowErrors}</h3>
                {failedRows.length > 0 ? (
                  <DataTable<PortfolioImportFailedRow>
                    caption={importText.importWizardFailedRowsTitle}
                    columns={failedRowColumns}
                    rows={failedRows.slice(0, 50)}
                    getRowKey={(row) => `${row.rowNumber}-${row.reasonCode}`}
                    emptyState={{ title: importText.importWizardRowErrors }}
                    density="compact"
                    minWidth="wide"
                  />
                ) : null}
                {csvParseResult.errors.length > 0 ? (
                  <ul className="max-h-48 list-disc space-y-1 overflow-auto pl-5 text-xs text-secondary-text">
                    {csvParseResult.errors.map((error) => (
                      <li key={error}>{error}</li>
                    ))}
                  </ul>
                ) : null}
                <InlineAlert
                  variant="warning"
                  size="compact"
                  message={importText.importWizardRetryHint}
                />
                <div className="flex flex-wrap gap-2">
                  {failedRows.length > 0 ? (
                    <Button
                      type="button"
                      variant="secondary"
                      size="comfortable"
                      onClick={downloadFailedRows}
                    >
                      {importText.importWizardDownloadFailedRows}
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    variant="secondary"
                    size="comfortable"
                    onClick={() => setStep('upload')}
                  >
                    {importText.importWizardContinueEdit}
                  </Button>
                </div>
              </div>
            ) : (
              <InlineAlert
                variant="success"
                size="compact"
                message={importText.importWizardNoErrors}
              />
            )}
          </Card>
        ) : null}

        {step === 'confirm' ? (
          <Card padding="md" className="space-y-3">
            <p className="text-sm text-secondary-text">{importText.importWizardConfirmHelp}</p>
            {!writableAccountId ? (
              <InlineAlert variant="warning" size="compact" message={text.selectAccountWrite} />
            ) : null}
            <Checkbox
              id="csv-dry-run"
              checked={csvDryRun}
              onChange={(event) => {
                setCsvDryRun(event.target.checked);
              }}
              containerClassName="min-h-11 text-xs text-secondary"
              label={<span className="text-xs font-normal text-secondary-text">{importText.dryRun}</span>}
            />
            <Button
              type="button"
              variant="secondary"
              size="comfortable"
              disabled={
                !writableAccountId
                || !csvParseResult
                || csvParsing
                || (importSource === 'file' && (!selectedBroker || !csvFile))
                || (importSource === 'futu' && !previewSnapshotId)
              }
              isLoading={csvCommitting}
              loadingText={text.submitting}
              onClick={() => void handleCommit()}
            >
              {importText.commitImport}
            </Button>
            {csvCommitResult ? (
              <>
                <InlineAlert
                  variant={getCsvCommitVariant(csvCommitResult, csvCommitResult.dryRun)}
                  size="compact"
                  title={
                    hasPartialCommit
                      ? importText.importWizardPartialTitle
                      : (csvCommitResult.dryRun ? importText.csvDryResult : importText.csvCommitResult)
                  }
                  message={formatUiText(importText.csvCommitSummary, {
                    mode: csvCommitResult.dryRun ? importText.dryCheck : importText.actualWrite,
                    inserted: csvCommitResult.insertedCount,
                    duplicates: csvCommitResult.duplicateCount,
                    failed: csvCommitResult.failedCount,
                  })}
                />
                {csvCommitResult.errors.length > 0 ? (
                  <ul className="max-h-48 list-disc space-y-1 overflow-auto pl-5 text-xs text-secondary-text">
                    {csvCommitResult.errors.map((error) => (
                      <li key={error}>{error}</li>
                    ))}
                  </ul>
                ) : null}
                {hasPartialCommit ? (
                  <div className="space-y-2">
                    <InlineAlert
                      variant="warning"
                      size="compact"
                      message={importText.importWizardPartialHelp}
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      size="comfortable"
                      onClick={() => setStep('upload')}
                    >
                      {importText.importWizardContinueEdit}
                    </Button>
                  </div>
                ) : null}
              </>
            ) : null}
          </Card>
        ) : null}

        {csvError ? (
          <ApiErrorAlert error={csvError} onDismiss={() => setCsvError(null)} />
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
          {stepIndex === 0 ? commonCancelLabel : importText.importWizardBack}
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
              || (step === 'mapping' && !csvParseResult)
            }
            isLoading={step === 'mapping' && csvParsing}
            loadingText={importSource === 'futu' ? importText.previewing : importText.parsing}
            onClick={goNext}
          >
            {importText.importWizardNext}
          </Button>
        ) : (
          <Button
            type="button"
            variant="primary"
            size="comfortable"
            disabled={busy}
            onClick={onClose}
          >
            {importText.importWizardDone}
          </Button>
        )}
      </StickyActionBar>
    </div>
  );
};

export default PortfolioImportWizard;
