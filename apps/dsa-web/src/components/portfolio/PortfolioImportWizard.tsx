// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Full-page portfolio CSV import wizard (#872 / #877 surface contract).

import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { X } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import type {
  PortfolioImportBrokerItem,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioImportTradeItem,
} from '../../types/portfolio';
import {
  formatBrokerLabel,
  getCsvCommitVariant,
  getCsvParseVariant,
} from '../../utils/portfolioFormat';
import { formatUiText } from '../../i18n/uiText';
import type { UiLanguage } from '../../i18n/uiText';
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
  PageHeader,
  Select,
  StickyActionBar,
  Textarea,
} from '../common';
import type { PortfolioFileText, PortfolioText } from '../../hooks/portfolio/types';

export const IMPORT_WIZARD_STEPS = [
  'format',
  'upload',
  'mapping',
  'validate',
  'confirm',
] as const;

export type ImportWizardStep = (typeof IMPORT_WIZARD_STEPS)[number];

type PortfolioImportWizardProps = {
  text: PortfolioText;
  fileText: PortfolioFileText;
  language: UiLanguage;
  writableAccountId: number | undefined;
  brokers: PortfolioImportBrokerItem[];
  selectedBroker: string;
  setSelectedBroker: (broker: string) => void;
  brokerLoadWarning: string | null;
  csvFile: File | null;
  setCsvFile: (file: File | null) => void;
  csvInputRef: React.RefObject<HTMLInputElement | null>;
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
  onParse: () => Promise<void> | void;
  onCommit: () => Promise<void> | void;
  onClose: () => void;
  commonCancelLabel: string;
  commonCloseLabel: string;
};

function buildPastedCsvFile(content: string): File {
  return new File([content], 'pasted-import.csv', { type: 'text/csv' });
}

export const PortfolioImportWizard: React.FC<PortfolioImportWizardProps> = ({
  text,
  fileText,
  language,
  writableAccountId,
  brokers,
  selectedBroker,
  setSelectedBroker,
  brokerLoadWarning,
  csvFile,
  setCsvFile,
  csvInputRef,
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
    format: text.importWizardStepFormat,
    upload: text.importWizardStepUpload,
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

  const canAdvanceFromFormat = Boolean(selectedBroker) && brokers.length > 0;
  const canAdvanceFromUpload = Boolean(csvFile) || pasteText.trim().length > 0;
  const hasParseErrors = Boolean(csvParseResult && csvParseResult.errorCount > 0);
  const hasPartialCommit = Boolean(
    csvCommitResult
    && !csvCommitResult.dryRun
    && csvCommitResult.failedCount > 0
    && csvCommitResult.insertedCount > 0,
  );

  useEffect(() => {
    if (step !== 'mapping') return;
    if (csvParsing || csvParseResult || !selectedBroker || !csvFile) return;
    void onParse();
  }, [step, csvFile, csvParseResult, csvParsing, selectedBroker, onParse]);

  const goNext = () => {
    if (busy) return;
    if (step === 'format') {
      if (!canAdvanceFromFormat) return;
      setStep('upload');
      return;
    }
    if (step === 'upload') {
      if (!canAdvanceFromUpload) return;
      if (!csvFile && pasteText.trim()) {
        setCsvFile(buildPastedCsvFile(pasteText.trim()));
        setCsvParseResult(null);
        setCsvCommitResult(null);
      }
      setStep('mapping');
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
    if (!csvFile && pasteText.trim()) {
      setCsvFile(buildPastedCsvFile(pasteText.trim()));
    }
    setCsvCommitResult(null);
    await onParse();
  };

  return (
    <div
      data-testid="portfolio-import-wizard"
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
        {brokerLoadWarning ? (
          <InlineAlert variant="warning" size="compact" message={brokerLoadWarning} />
        ) : null}

        {step === 'format' ? (
          <Card padding="md" className="space-y-3">
            <p className="text-sm text-secondary-text">{text.importWizardFormatHelp}</p>
            <Select
              label={text.broker}
              value={selectedBroker}
              onChange={(value) => {
                setSelectedBroker(value);
                setCsvCommitResult(null);
                setCsvParseResult(null);
              }}
              disabled={busy || brokers.length === 0}
              options={brokers.map((item) => ({
                value: item.broker,
                label: formatBrokerLabel(item.broker, item.displayName, language),
              }))}
            />
          </Card>
        ) : null}

        {step === 'upload' ? (
          <Card padding="md" className="space-y-3">
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
                accept=".csv"
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
          </Card>
        ) : null}

        {step === 'mapping' ? (
          <Card padding="md" className="space-y-3">
            <p className="text-sm text-secondary-text">{text.importWizardMappingHelp}</p>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                size="comfortable"
                disabled={!selectedBroker || (!csvFile && !pasteText.trim()) || csvCommitting}
                isLoading={csvParsing}
                loadingText={text.parsing}
                onClick={() => void handleReparse()}
              >
                {text.parseFile}
              </Button>
            </div>
            {csvParseResult ? (
              <>
                <InlineAlert
                  variant={getCsvParseVariant(csvParseResult)}
                  size="compact"
                  title={text.csvParseResult}
                  message={formatUiText(text.csvParseSummary, {
                    valid: csvParseResult.recordCount,
                    skipped: csvParseResult.skippedCount,
                    errors: csvParseResult.errorCount,
                  })}
                />
                {csvParseResult.records.length > 0 ? (
                  <DataTable<PortfolioImportTradeItem>
                    caption={text.importWizardMappingTitle}
                    columns={mappingColumns}
                    rows={csvParseResult.records.slice(0, 50)}
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
                    message={text.importWizardMappingEmpty}
                  />
                )}
              </>
            ) : (
              <InlineAlert
                variant="info"
                size="compact"
                message={text.importWizardMappingEmpty}
              />
            )}
          </Card>
        ) : null}

        {step === 'validate' ? (
          <Card padding="md" className="space-y-3">
            <p className="text-sm text-secondary-text">{text.importWizardValidateHelp}</p>
            {csvParseResult ? (
              <InlineAlert
                variant={getCsvParseVariant(csvParseResult)}
                size="compact"
                title={text.csvParseResult}
                message={formatUiText(text.csvParseSummary, {
                  valid: csvParseResult.recordCount,
                  skipped: csvParseResult.skippedCount,
                  errors: csvParseResult.errorCount,
                })}
              />
            ) : null}
            {hasParseErrors && csvParseResult ? (
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-foreground">{text.importWizardRowErrors}</h3>
                <ul className="max-h-64 list-disc space-y-1 overflow-auto pl-5 text-xs text-secondary-text">
                  {csvParseResult.errors.map((error) => (
                    <li key={error}>{error}</li>
                  ))}
                </ul>
                <InlineAlert
                  variant="warning"
                  size="compact"
                  message={text.importWizardRetryHint}
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
            <Checkbox
              id="csv-dry-run"
              checked={csvDryRun}
              onChange={(event) => {
                setCsvDryRun(event.target.checked);
              }}
              containerClassName="min-h-11 text-xs text-secondary"
              label={<span className="text-xs font-normal text-secondary-text">{text.dryRun}</span>}
            />
            <Button
              type="button"
              variant="secondary"
              size="comfortable"
              disabled={!selectedBroker || !csvFile || !writableAccountId || csvParsing}
              isLoading={csvCommitting}
              loadingText={text.submitting}
              onClick={() => void onCommit()}
            >
              {text.commitImport}
            </Button>
            {csvCommitResult ? (
              <>
                <InlineAlert
                  variant={getCsvCommitVariant(csvCommitResult, csvCommitResult.dryRun)}
                  size="compact"
                  title={
                    hasPartialCommit
                      ? text.importWizardPartialTitle
                      : (csvCommitResult.dryRun ? text.csvDryResult : text.csvCommitResult)
                  }
                  message={formatUiText(text.csvCommitSummary, {
                    mode: csvCommitResult.dryRun ? text.dryCheck : text.actualWrite,
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
                  <InlineAlert
                    variant="warning"
                    size="compact"
                    message={text.importWizardPartialHelp}
                  />
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
              || (step === 'mapping' && !csvParseResult)
            }
            isLoading={step === 'mapping' && csvParsing}
            loadingText={text.parsing}
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
