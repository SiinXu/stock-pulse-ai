// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import {
  CheckCircle2,
  CircleHelp,
  FileUp,
  FlaskConical,
  ListChecks,
  Upload,
} from 'lucide-react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { STOCK_SEARCH_TEXT } from '../../locales/stockSearch';
import { ANALYSIS_WORKBENCH_SEGMENT_VALUES } from '../../routing/routes';
import type { AnalysisPhase } from '../../types/analysis';
import type { ExperienceMode } from '../../utils/onboardingPreferences';
import {
  Button,
  Checkbox,
  FileInput,
  InlineAlert,
  SegmentedControl,
  Select,
  Surface,
  TabPanel,
  Tooltip,
} from '../common';
import { StockAutocomplete } from '../StockAutocomplete';
import { AnalysisPhaseSelect } from './AnalysisPhaseSelect';

const WORKBENCH_TABS_ID = 'analysis-workbench-tabs';
const WORKBENCH_PENDING_REASON_ID = 'analysis-workbench-pending-reason';

export type LaunchImportNotice = {
  variant: 'success' | 'warning' | 'danger';
  message: string;
} | null;

export interface AnalysisWorkbenchLaunchPanelProps {
  activeSegment: string;
  query: string;
  setQuery: (value: string) => void;
  inputError?: string;
  isAnalyzing: boolean;
  isBatchSubmitting: boolean;
  isImporting: boolean;
  isExperienceModeReady: boolean;
  launchBlockedByBusy: boolean;
  experienceMode: ExperienceMode;
  onExperienceModeChange: (mode: ExperienceMode) => void;
  notify: boolean;
  setNotify: (value: boolean) => void;
  selectedStrategyId: string;
  setSelectedStrategyId: (value: string) => void;
  strategyOptions: Array<{ value: string; label: string }>;
  analysisPhase: AnalysisPhase;
  setAnalysisPhase: (value: AnalysisPhase) => void;
  onSubmitAnalysis: (
    stockCode?: string,
    stockName?: string,
    selectionSource?: 'manual' | 'autocomplete' | 'import',
  ) => void | Promise<void>;
  onSubmitWatchlistBatch: (mode: 'all' | 'pending') => void | Promise<void>;
  onSubmitImportedBatch: () => void | Promise<void>;
  onImportFile: (file: File) => void | Promise<void>;
  importedCodes: string[];
  importNotice: LaunchImportNotice;
  watchlistLoading: boolean;
  pendingBlocked: boolean;
  pendingCount: number;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
}

const AnalysisWorkbenchLaunchPanel: React.FC<AnalysisWorkbenchLaunchPanelProps> = ({
  activeSegment,
  query,
  setQuery,
  inputError,
  isAnalyzing,
  isBatchSubmitting,
  isImporting,
  isExperienceModeReady,
  launchBlockedByBusy,
  experienceMode,
  onExperienceModeChange,
  notify,
  setNotify,
  selectedStrategyId,
  setSelectedStrategyId,
  strategyOptions,
  analysisPhase,
  setAnalysisPhase,
  onSubmitAnalysis,
  onSubmitWatchlistBatch,
  onSubmitImportedBatch,
  onImportFile,
  importedCodes,
  importNotice,
  watchlistLoading,
  pendingBlocked,
  pendingCount,
  fileInputRef,
}) => {
  const { language, t } = useUiLanguage();

  return (
    <TabPanel
      tabsId={WORKBENCH_TABS_ID}
      value={ANALYSIS_WORKBENCH_SEGMENT_VALUES.launch}
      activeValue={activeSegment}
    >
      <Surface level="interactive" padding="lg">
        <div className="mx-auto w-full max-w-5xl space-y-6">
          <div className="max-w-2xl">
            <h2 className="text-lg font-semibold text-foreground">
              {t('analysisWorkbench.launch')}
            </h2>
            <p className="mt-1 text-sm text-secondary-text">
              {t('analysisWorkbench.launchDescription')}
            </p>
          </div>

          <div className="grid gap-4 rounded-xl border border-border bg-background/20 p-4 lg:grid-cols-3 lg:items-start">
            <div>
              <div className="mb-1.5 flex h-5 items-center gap-1">
                <label
                  htmlFor="analysis-workbench-stock-search"
                  className="text-xs font-medium text-secondary-text"
                >
                  {STOCK_SEARCH_TEXT[language].inputLabel}
                </label>
                <Tooltip
                  content={(
                    <span className="space-y-1">
                      <span className="block">{STOCK_SEARCH_TEXT[language].suffixExamples}</span>
                      <span className="block">{STOCK_SEARCH_TEXT[language].manualEntryHint}</span>
                    </span>
                  )}
                >
                  <button
                    type="button"
                    data-testid="analysis-stock-search-help"
                    aria-label={`${STOCK_SEARCH_TEXT[language].inputLabel} · ${t('common.details')}`}
                    className="inline-flex h-5 w-5 items-center justify-center rounded-sm text-muted-text hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
                  >
                    <CircleHelp className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </Tooltip>
              </div>
              <div className="[&>div>p]:sr-only">
                <StockAutocomplete
                  id="analysis-workbench-stock-search"
                  value={query}
                  onChange={setQuery}
                  onSubmit={(stockCode, stockName, selectionSource) => {
                    void onSubmitAnalysis(stockCode, stockName, selectionSource);
                  }}
                  placeholder={t('home.placeholder')}
                  disabled={isAnalyzing || !isExperienceModeReady}
                  className={inputError ? 'border-danger/50' : undefined}
                />
              </div>
            </div>
            <Select
              value={selectedStrategyId}
              onChange={setSelectedStrategyId}
              options={strategyOptions}
              label={t('home.strategy')}
              disabled={isAnalyzing || !isExperienceModeReady}
              className="w-full [&>label]:flex [&>label]:h-5 [&>label]:items-center"
              triggerClassName="w-full"
            />
            <AnalysisPhaseSelect
              id="analysis-workbench-phase"
              value={analysisPhase}
              onChange={setAnalysisPhase}
              label={t('analysis.phase')}
              disabled={isAnalyzing || isBatchSubmitting || !isExperienceModeReady}
              labelAction={(
                <Tooltip content={t('analysis.phaseHint')}>
                  <button
                    type="button"
                    data-testid="analysis-phase-help"
                    aria-label={`${t('analysis.phase')} · ${t('common.details')}`}
                    className="inline-flex h-5 w-5 items-center justify-center rounded-sm text-muted-text hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
                  >
                    <CircleHelp className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </Tooltip>
              )}
            />
          </div>

          <div className="flex flex-col gap-3 rounded-xl border border-border bg-background/20 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-3">
              <SegmentedControl
                value={experienceMode}
                onChange={onExperienceModeChange}
                ariaLabel={t('home.experienceModeLabel')}
                semantics="single-select"
                options={[
                  { value: 'beginner', label: t('home.beginnerMode') },
                  { value: 'professional', label: t('home.professionalMode') },
                ]}
              />
              <Checkbox
                checked={notify}
                onChange={(event) => setNotify(event.target.checked)}
                label={t('home.notify')}
              />
            </div>
            <Button
              type="button"
              variant="primary"
              className="shrink-0"
              disabled={!query || isAnalyzing || launchBlockedByBusy || !isExperienceModeReady}
              isLoading={isAnalyzing}
              loadingText={t('home.analyzing')}
              onClick={() => void onSubmitAnalysis()}
            >
              <FlaskConical className="h-4 w-4" aria-hidden="true" />
              {experienceMode === 'beginner' ? t('home.quickAnalyze') : t('home.analyze')}
            </Button>
          </div>

          <div className="rounded-xl border border-border bg-background/20 p-4">
            <p className="text-sm text-secondary-text">
              {t('analysisWorkbench.batchDescription')}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                isLoading={isBatchSubmitting}
                disabled={isBatchSubmitting || launchBlockedByBusy || watchlistLoading || !isExperienceModeReady}
                onClick={() => void onSubmitWatchlistBatch('all')}
              >
                <ListChecks className="h-4 w-4" aria-hidden="true" />
                {t('watchlist.analyzeAll')}
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={(
                  isBatchSubmitting
                  || launchBlockedByBusy
                  || watchlistLoading
                  || !isExperienceModeReady
                  || pendingBlocked
                  || pendingCount === 0
                )}
                aria-describedby={pendingBlocked ? WORKBENCH_PENDING_REASON_ID : undefined}
                onClick={() => void onSubmitWatchlistBatch('pending')}
              >
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                {t('watchlist.analyzePending')}
              </Button>
              <Button
                type="button"
                variant="secondary"
                isLoading={isImporting}
                loadingText={t('analysisWorkbench.importing')}
                disabled={isImporting || isBatchSubmitting}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="h-4 w-4" aria-hidden="true" />
                {t('analysisWorkbench.importAction')}
              </Button>
              {importedCodes.length > 0 ? (
                <Button
                  type="button"
                  variant="secondary"
                  isLoading={isBatchSubmitting}
                  disabled={isImporting || isBatchSubmitting || launchBlockedByBusy || !isExperienceModeReady}
                  onClick={() => void onSubmitImportedBatch()}
                >
                  <FileUp className="h-4 w-4" aria-hidden="true" />
                  {t('analysisWorkbench.analyzeImported', { count: importedCodes.length })}
                </Button>
              ) : null}
              {pendingBlocked ? (
                <p
                  id={WORKBENCH_PENDING_REASON_ID}
                  className="basis-full text-xs text-secondary-text"
                >
                  {t('watchlist.pendingStatusUnavailable')}
                </p>
              ) : null}
              <FileInput
                ref={fileInputRef}
                accept="image/jpeg,image/png,image/webp,image/gif,.csv,.xlsx,.xls,.txt"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void onImportFile(file);
                }}
              />
            </div>
            {importNotice ? (
              <InlineAlert
                className="mt-3"
                variant={importNotice.variant}
                message={importNotice.message}
              />
            ) : null}
          </div>
        </div>
      </Surface>
    </TabPanel>
  );
};

export default AnalysisWorkbenchLaunchPanel;
