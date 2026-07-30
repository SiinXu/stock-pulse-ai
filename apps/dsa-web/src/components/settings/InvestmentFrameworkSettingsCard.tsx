// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Copy, History, RefreshCw } from 'lucide-react';
import { investmentFrameworkApi } from '../../api/investmentFramework';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatDateTime } from '../../utils/format';
import type {
  InvestmentFrameworkContent,
  InvestmentFrameworkHistoryItem,
  InvestmentFrameworkHistoryResponse,
  InvestmentFrameworkResponse,
} from '../../types/investmentFramework';
import {
  ApiErrorAlert,
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  Modal,
  StatePanel,
} from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';
import InvestmentFrameworkStructuredEditor from './InvestmentFrameworkStructuredEditor';
import {
  cloneInvestmentFrameworkContent,
  emptyInvestmentFrameworkContent,
  INVESTMENT_FRAMEWORK_LIMITS,
  validationIssuesFromFrameworkApiDetails,
  validateInvestmentFrameworkContent,
  type InvestmentFrameworkValidationIssue,
} from './investmentFrameworkEditorModel';

function linesToList(value: string): string[] {
  return value.split('\n').map((line) => line.trim()).filter(Boolean);
}

function listToLines(values: string[] | undefined): string {
  return (values ?? []).join('\n');
}

function editableContent(content: InvestmentFrameworkContent): InvestmentFrameworkContent {
  return {
    ...cloneInvestmentFrameworkContent(content),
    schemaVersion: content.schemaVersion ?? 'investment-framework-content-v1',
    title: content.title ?? '',
    description: content.description ?? null,
    rootNodeId: content.rootNodeId ?? null,
    decisionTree: content.decisionTree ?? [],
    evaluationDimensions: content.evaluationDimensions ?? [],
    riskRules: content.riskRules ?? [],
    trackingCriteria: content.trackingCriteria ?? [],
    freeFormRules: content.freeFormRules ?? null,
  };
}

export const InvestmentFrameworkSettingsCard: React.FC = () => {
  const { language, t } = useUiLanguage();
  const [framework, setFramework] = useState<InvestmentFrameworkResponse | null>(null);
  const [exists, setExists] = useState(false);
  const [content, setContent] = useState<InvestmentFrameworkContent>(
    emptyInvestmentFrameworkContent,
  );
  const [changeSummary, setChangeSummary] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isConflict, setIsConflict] = useState(false);
  const [showValidation, setShowValidation] = useState(false);
  const [serverValidationIssues, setServerValidationIssues] = useState<
    InvestmentFrameworkValidationIssue[]
  >([]);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  const [history, setHistory] = useState<InvestmentFrameworkHistoryResponse | null>(null);
  const [selectedHistoryVersion, setSelectedHistoryVersion] = useState<number | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<ParsedApiError | null>(null);

  const load = useCallback(async (replaceDraft = true): Promise<boolean> => {
    setIsLoading(true);
    setLoadError(null);
    setError(null);
    try {
      const current = await investmentFrameworkApi.get();
      setFramework(current);
      setExists(true);
      if (replaceDraft) {
        setContent(editableContent(current.content));
        setChangeSummary('');
        setShowValidation(false);
      }
      setIsConflict(false);
      return true;
    } catch (err) {
      const parsed = getParsedApiError(err);
      if (parsed.status === 404 || parsed.code === 'investment_framework_not_found') {
        setFramework(null);
        setExists(false);
        if (replaceDraft) {
          setContent(emptyInvestmentFrameworkContent());
          setChangeSummary('');
          setShowValidation(false);
        }
        setIsConflict(false);
        return true;
      }
      setLoadError(parsed);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async (forceExists = false) => {
    if (!exists && !forceExists) {
      setHistory(null);
      setSelectedHistoryVersion(null);
      setHistoryError(null);
      return;
    }
    setIsHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await investmentFrameworkApi.history();
      const ordered = {
        ...response,
        items: [...response.items].sort((left, right) => right.version - left.version),
      };
      setHistory(ordered);
      setSelectedHistoryVersion((current) => (
        current && ordered.items.some((item) => item.version === current)
          ? current
          : ordered.items[0]?.version ?? null
      ));
    } catch (historyLoadError: unknown) {
      setHistoryError(getParsedApiError(historyLoadError));
    } finally {
      setIsHistoryLoading(false);
    }
  }, [exists]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (isConfigOpen) {
      void loadHistory();
    }
  }, [isConfigOpen, loadHistory]);

  const validationIssues = useMemo(
    () => validateInvestmentFrameworkContent(content),
    [content],
  );

  useEffect(() => {
    setServerValidationIssues([]);
  }, [content]);

  const visibleValidationIssues = useMemo(
    () => (showValidation ? [...validationIssues, ...serverValidationIssues] : []),
    [serverValidationIssues, showValidation, validationIssues],
  );

  const formatValidationIssue = useCallback((issue: InvestmentFrameworkValidationIssue) => {
    const limits: Partial<Record<InvestmentFrameworkValidationIssue['code'], number>> = {
      title_too_long: INVESTMENT_FRAMEWORK_LIMITS.titleLength,
      description_length: INVESTMENT_FRAMEWORK_LIMITS.descriptionLength,
      too_many_nodes: INVESTMENT_FRAMEWORK_LIMITS.nodes,
      invalid_node_id: INVESTMENT_FRAMEWORK_LIMITS.nodeIdLength,
      too_many_branches: INVESTMENT_FRAMEWORK_LIMITS.branchesPerNode,
      too_many_dimensions: INVESTMENT_FRAMEWORK_LIMITS.dimensions,
      dimension_name_too_long: INVESTMENT_FRAMEWORK_LIMITS.dimensionNameLength,
      too_many_dimension_criteria: INVESTMENT_FRAMEWORK_LIMITS.criteriaPerDimension,
      dimension_description_length: INVESTMENT_FRAMEWORK_LIMITS.ruleLength,
      too_many_risk_rules: INVESTMENT_FRAMEWORK_LIMITS.riskRules,
      too_many_tracking_criteria: INVESTMENT_FRAMEWORK_LIMITS.trackingCriteria,
      rule_length: INVESTMENT_FRAMEWORK_LIMITS.ruleLength,
      free_form_rules_length: INVESTMENT_FRAMEWORK_LIMITS.freeFormRulesLength,
    };
    const params = {
      value: issue.value || '—',
      limit: limits[issue.code] ?? INVESTMENT_FRAMEWORK_LIMITS.ruleLength,
    };
    const keys = {
      title_required: 'settings.frameworkValidationTitleRequired',
      title_too_long: 'settings.frameworkValidationTitleTooLong',
      description_length: 'settings.frameworkValidationDescriptionLength',
      criteria_required: 'settings.frameworkValidationCriteriaRequired',
      too_many_nodes: 'settings.frameworkValidationTooManyNodes',
      invalid_node_id: 'settings.frameworkValidationInvalidNodeId',
      duplicate_node_id: 'settings.frameworkValidationDuplicateNodeId',
      node_question_required: 'settings.frameworkValidationNodeQuestion',
      branches_required: 'settings.frameworkValidationBranches',
      too_many_branches: 'settings.frameworkValidationTooManyBranches',
      branch_condition_required: 'settings.frameworkValidationBranchCondition',
      branch_destination: 'settings.frameworkValidationBranchDestination',
      root_required: 'settings.frameworkValidationRootRequired',
      root_unknown: 'settings.frameworkValidationRootUnknown',
      target_unknown: 'settings.frameworkValidationTargetUnknown',
      cycle: 'settings.frameworkValidationCycle',
      unreachable: 'settings.frameworkValidationUnreachable',
      too_many_dimensions: 'settings.frameworkValidationTooManyDimensions',
      dimension_name_required: 'settings.frameworkValidationDimensionName',
      dimension_name_too_long: 'settings.frameworkValidationDimensionNameTooLong',
      duplicate_dimension_name: 'settings.frameworkValidationDuplicateDimension',
      invalid_weight: 'settings.frameworkValidationWeight',
      too_many_dimension_criteria: 'settings.frameworkValidationTooManyCriteria',
      dimension_description_length: 'settings.frameworkValidationDimensionDescriptionLength',
      too_many_risk_rules: 'settings.frameworkValidationTooManyRiskRules',
      too_many_tracking_criteria: 'settings.frameworkValidationTooManyTrackingCriteria',
      rule_length: 'settings.frameworkValidationRuleLength',
      free_form_rules_length: 'settings.frameworkValidationFreeFormLength',
      server_validation: 'settings.frameworkValidationServer',
    } as const;
    return t(keys[issue.code], params);
  }, [t]);

  const statusLabel = useMemo(() => {
    if (isLoading) return t('common.loading');
    if (loadError) return loadError.title;
    if (!exists || !framework) return t('settings.frameworkStatusMissing');
    return framework.isActive
      ? t('settings.frameworkStatusActive')
      : t('settings.frameworkStatusInactive');
  }, [exists, framework, isLoading, loadError, t]);

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccessMessage(null);
    setServerValidationIssues([]);
    setShowValidation(true);
    if (validationIssues.length) {
      return;
    }

    setIsSubmitting(true);
    try {
      if (!exists || !framework) {
        const created = await investmentFrameworkApi.create({
          content,
          changeSummary: changeSummary.trim() || t('settings.frameworkInitialSummary'),
        });
        setFramework(created);
        setExists(true);
        setContent(editableContent(created.content));
        setChangeSummary('');
        setSuccessMessage(t('settings.frameworkCreated'));
      } else {
        const updated = await investmentFrameworkApi.update({
          expectedRevision: framework.revision,
          content,
          changeSummary: changeSummary.trim() || t('settings.frameworkUpdateSummary'),
        });
        setFramework(updated);
        setContent(editableContent(updated.content));
        setChangeSummary('');
        setSuccessMessage(t('settings.frameworkSaved'));
      }
      setShowValidation(false);
      setIsConflict(false);
      await loadHistory(!exists);
    } catch (err) {
      const parsed = getParsedApiError(err);
      if (parsed.status === 422 || parsed.code === 'validation_error') {
        setServerValidationIssues(
          validationIssuesFromFrameworkApiDetails(parsed.details, content),
        );
        setShowValidation(true);
      }
      setError(parsed);
      setIsConflict(
        parsed.status === 409
        || parsed.code === 'investment_framework_revision_conflict',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeactivate = async () => {
    if (!framework) return;
    setError(null);
    setSuccessMessage(null);
    setIsSubmitting(true);
    try {
      const updated = await investmentFrameworkApi.deactivate({
        expectedRevision: framework.revision,
      });
      setFramework(updated);
      setContent(editableContent(updated.content));
      setSuccessMessage(t('settings.frameworkDeactivated'));
      await loadHistory();
    } catch (err) {
      const parsed = getParsedApiError(err);
      setError(parsed);
      setIsConflict(parsed.status === 409);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!framework) return;
    setDeleteConfirmOpen(false);
    setError(null);
    setSuccessMessage(null);
    setIsSubmitting(true);
    try {
      await investmentFrameworkApi.remove(framework.revision);
      setFramework(null);
      setExists(false);
      setContent(emptyInvestmentFrameworkContent());
      setChangeSummary('');
      setHistory(null);
      setSelectedHistoryVersion(null);
      setSuccessMessage(t('settings.frameworkDeleted'));
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedHistory = history?.items.find(
    (item) => item.version === selectedHistoryVersion,
  ) ?? null;
  const riskRuleIssues = visibleValidationIssues.filter((issue) => (
    issue.path.startsWith('riskRules')
  ));
  const trackingCriteriaIssues = visibleValidationIssues.filter((issue) => (
    issue.path.startsWith('trackingCriteria')
  ));

  const copyHistoryIntoDraft = (item: InvestmentFrameworkHistoryItem) => {
    setContent(editableContent(item.content));
    setChangeSummary(t('settings.frameworkCopiedSummary', { version: item.version }));
    setShowValidation(false);
    setError(null);
    setSuccessMessage(t('settings.frameworkCopiedToDraft', { version: item.version }));
  };

  const fieldClass =
    'w-full rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] px-3 py-2 text-sm text-foreground outline-none transition-[border-color,background-color] focus:border-[var(--settings-border-strong)]';

  return (
    <SettingsSectionCard
      title={t('settings.frameworkTitle')}
      description={t('settings.frameworkDescription')}
      actions={(
        <>
          <Badge
            variant={loadError ? 'danger' : framework?.isActive ? 'success' : 'default'}
            size="sm"
          >
            {statusLabel}
          </Badge>
          {!loadError ? (
            <Button
              variant="secondary"
              size="default"
              aria-haspopup="dialog"
              disabled={isLoading}
              onClick={() => setIsConfigOpen(true)}
            >
              {t('settings.openConfigItems')}
            </Button>
          ) : null}
        </>
      )}
    >
      <p className="text-xs leading-6 text-muted-text">{t('settings.frameworkDisclaimer')}</p>
      {loadError ? (
        <SettingsAlert
          title={loadError.title}
          message={loadError.message}
          actionLabel={t('common.retry')}
          onAction={() => void load()}
        />
      ) : null}

      <Modal
        isOpen={isConfigOpen}
        onClose={() => setIsConfigOpen(false)}
        title={t('settings.frameworkTitle')}
        description={t('settings.frameworkDescription')}
        size="fullscreen"
        closeDisabled={isSubmitting}
      >
        <p className="mb-4 text-xs leading-6 text-muted-text">{t('settings.frameworkDisclaimer')}</p>
        {isLoading ? (
          <StatePanel state="loading" title={t('common.loading')} size="compact" titleAs="p" />
        ) : loadError ? (
          <SettingsAlert
            title={loadError.title}
            message={loadError.message}
            actionLabel={t('common.retry')}
            onAction={() => void load()}
          />
        ) : (
          <div className="grid min-w-0 grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
            <form className="min-w-0 space-y-5" aria-busy={isSubmitting} onSubmit={handleSave}>
              {framework ? (
                <div className="grid grid-cols-1 gap-2 text-xs text-secondary-text sm:grid-cols-3">
                  <span>{t('settings.frameworkVersionValue', { version: framework.version })}</span>
                  <span>{t('settings.frameworkRevisionValue', { revision: framework.revision })}</span>
                  <span>
                    {framework.activeVersion == null
                      ? t('settings.frameworkActiveVersionNone')
                      : t('settings.frameworkActiveVersionValue', { version: framework.activeVersion })}
                  </span>
                </div>
              ) : null}

              <section className="space-y-3 rounded-xl border settings-border bg-background/20 p-4">
                <h3 className="text-base font-semibold text-foreground">
                  {t('settings.frameworkBasics')}
                </h3>
                <label className="block space-y-1" htmlFor="investment-framework-title">
                  <span className="text-sm font-medium text-foreground">
                    {t('settings.frameworkNameLabel')}
                  </span>
                  <input
                    id="investment-framework-title"
                    className={fieldClass}
                    value={content.title}
                    disabled={isSubmitting}
                    onChange={(event) => setContent((current) => ({
                      ...current,
                      title: event.target.value,
                    }))}
                    required
                  />
                </label>

                <label className="block space-y-1" htmlFor="investment-framework-description">
                  <span className="text-sm font-medium text-foreground">
                    {t('settings.frameworkDescLabel')}
                  </span>
                  <textarea
                    id="investment-framework-description"
                    className={`${fieldClass} min-h-20`}
                    value={content.description ?? ''}
                    disabled={isSubmitting}
                    onChange={(event) => setContent((current) => ({
                      ...current,
                      description: event.target.value || null,
                    }))}
                  />
                </label>

                <label className="block space-y-1" htmlFor="investment-framework-free-form">
                  <span className="text-sm font-medium text-foreground">
                    {t('settings.frameworkFreeFormLabel')}
                  </span>
                  <textarea
                    id="investment-framework-free-form"
                    className={`${fieldClass} min-h-28`}
                    value={content.freeFormRules ?? ''}
                    disabled={isSubmitting}
                    onChange={(event) => setContent((current) => ({
                      ...current,
                      freeFormRules: event.target.value || null,
                    }))}
                    placeholder={t('settings.frameworkFreeFormPlaceholder')}
                  />
                </label>

                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  <label className="block space-y-1" htmlFor="investment-framework-risk-rules">
                    <span className="text-sm font-medium text-foreground">
                      {t('settings.frameworkRiskRulesLabel')}
                    </span>
                    <span className="block text-xs text-muted-text">
                      {t('settings.frameworkLimitUsage', {
                        current: content.riskRules?.length ?? 0,
                        limit: INVESTMENT_FRAMEWORK_LIMITS.riskRules,
                      })}
                      {' · '}
                      {t('settings.frameworkRuleLengthHint', {
                        limit: INVESTMENT_FRAMEWORK_LIMITS.ruleLength,
                      })}
                    </span>
                    <textarea
                      id="investment-framework-risk-rules"
                      className={`${fieldClass} min-h-20`}
                      aria-label={t('settings.frameworkRiskRulesLabel')}
                      value={listToLines(content.riskRules)}
                      disabled={isSubmitting}
                      onChange={(event) => setContent((current) => ({
                        ...current,
                        riskRules: linesToList(event.target.value),
                      }))}
                      placeholder={t('settings.frameworkListPlaceholder')}
                    />
                    {riskRuleIssues.length ? (
                      <span
                        className="block text-xs text-danger"
                        role="alert"
                        data-testid="framework-risk-rule-errors"
                      >
                        {riskRuleIssues.map(formatValidationIssue).join(' · ')}
                      </span>
                    ) : null}
                  </label>
                  <label className="block space-y-1" htmlFor="investment-framework-tracking">
                    <span className="text-sm font-medium text-foreground">
                      {t('settings.frameworkTrackingLabel')}
                    </span>
                    <span className="block text-xs text-muted-text">
                      {t('settings.frameworkLimitUsage', {
                        current: content.trackingCriteria?.length ?? 0,
                        limit: INVESTMENT_FRAMEWORK_LIMITS.trackingCriteria,
                      })}
                      {' · '}
                      {t('settings.frameworkRuleLengthHint', {
                        limit: INVESTMENT_FRAMEWORK_LIMITS.ruleLength,
                      })}
                    </span>
                    <textarea
                      id="investment-framework-tracking"
                      className={`${fieldClass} min-h-20`}
                      aria-label={t('settings.frameworkTrackingLabel')}
                      value={listToLines(content.trackingCriteria)}
                      disabled={isSubmitting}
                      onChange={(event) => setContent((current) => ({
                        ...current,
                        trackingCriteria: linesToList(event.target.value),
                      }))}
                      placeholder={t('settings.frameworkListPlaceholder')}
                    />
                    {trackingCriteriaIssues.length ? (
                      <span
                        className="block text-xs text-danger"
                        role="alert"
                        data-testid="framework-tracking-criteria-errors"
                      >
                        {trackingCriteriaIssues.map(formatValidationIssue).join(' · ')}
                      </span>
                    ) : null}
                  </label>
                </div>
              </section>

              <InvestmentFrameworkStructuredEditor
                content={content}
                issues={visibleValidationIssues}
                disabled={isSubmitting}
                onChange={setContent}
                formatIssue={formatValidationIssue}
                t={t}
              />

              <label className="block space-y-1" htmlFor="investment-framework-change-summary">
                <span className="text-sm font-medium text-foreground">
                  {t('settings.frameworkChangeSummaryLabel')}
                </span>
                <input
                  id="investment-framework-change-summary"
                  className={fieldClass}
                  value={changeSummary}
                  disabled={isSubmitting}
                  onChange={(event) => setChangeSummary(event.target.value)}
                  maxLength={500}
                />
              </label>

              {visibleValidationIssues.length ? (
                <SettingsAlert
                  title={t('settings.frameworkValidationTitle')}
                  message={visibleValidationIssues.map(formatValidationIssue).join(' · ')}
                  variant="error"
                />
              ) : null}
              {error ? (
                <ApiErrorAlert
                  error={error}
                  actionLabel={isConflict ? t('settings.frameworkLoadLatest') : undefined}
                  onAction={isConflict ? () => void load(true) : undefined}
                />
              ) : null}
              {isConflict ? (
                <p className="text-xs leading-5 text-secondary-text">
                  {t('settings.frameworkConflictDraftPreserved')}
                </p>
              ) : null}
              {successMessage ? (
                <SettingsAlert
                  title={t('settings.actionSuccess')}
                  message={successMessage}
                  variant="success"
                />
              ) : null}

              <div className="flex flex-wrap gap-2">
                <Button type="submit" variant="primary" disabled={isSubmitting || isLoading}>
                  {exists ? t('settings.frameworkSave') : t('settings.frameworkCreate')}
                </Button>
                {exists && framework?.isActive ? (
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={isSubmitting}
                    onClick={() => void handleDeactivate()}
                  >
                    {t('settings.frameworkDeactivate')}
                  </Button>
                ) : null}
                {exists ? (
                  <Button
                    type="button"
                    variant="danger-subtle"
                    disabled={isSubmitting}
                    onClick={() => setDeleteConfirmOpen(true)}
                  >
                    {t('settings.frameworkDelete')}
                  </Button>
                ) : null}
                {isSubmitting ? (
                  <span role="status" className="self-center text-xs text-secondary-text">
                    {t('common.processing')}
                  </span>
                ) : null}
              </div>
            </form>

            <aside className="min-w-0 space-y-3 rounded-xl border settings-border bg-background/20 p-4">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <h3 className="flex items-center gap-2 text-base font-semibold text-foreground">
                    <History className="h-4 w-4" aria-hidden="true" />
                    {t('settings.frameworkHistory')}
                  </h3>
                  <p className="mt-1 text-xs leading-5 text-secondary-text">
                    {t('settings.frameworkHistoryDescription')}
                  </p>
                </div>
                <IconButton
                  type="button"
                  variant="outline"
                  size="compact"
                  disabled={isHistoryLoading || !exists}
                  isLoading={isHistoryLoading}
                  aria-label={t('settings.frameworkHistoryRefresh')}
                  onClick={() => void loadHistory()}
                >
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                </IconButton>
              </div>

              {isHistoryLoading && !history ? (
                <StatePanel
                  state="loading"
                  title={t('settings.frameworkHistoryLoading')}
                  size="compact"
                  titleAs="p"
                />
              ) : null}
              {historyError ? (
                <ApiErrorAlert
                  error={historyError}
                  actionLabel={t('common.retry')}
                  onAction={() => void loadHistory()}
                />
              ) : null}
              {!isHistoryLoading && !historyError && (!history || history.items.length === 0) ? (
                <EmptyState
                  compact
                  title={t('settings.frameworkHistoryEmpty')}
                  description={t('settings.frameworkHistoryEmptyDescription')}
                />
              ) : null}
              {history?.items.length ? (
                <div
                  className="max-h-52 space-y-2 overflow-y-auto pr-1"
                  role="list"
                  aria-label={t('settings.frameworkHistoryList')}
                >
                  {history.items.map((item) => (
                    <div key={item.version} role="listitem">
                      <button
                        type="button"
                        aria-label={t('settings.frameworkHistoryVersion', { version: item.version })}
                        aria-pressed={selectedHistoryVersion === item.version}
                        className="flex w-full items-center justify-between gap-2 rounded-lg border settings-border px-3 py-2 text-left hover:bg-[var(--settings-surface-hover)]"
                        onClick={() => setSelectedHistoryVersion(item.version)}
                      >
                        <span className="min-w-0">
                          <span className="block text-sm font-medium text-foreground">
                            {t('settings.frameworkHistoryVersion', { version: item.version })}
                          </span>
                          <span className="block truncate text-xs text-muted-text">
                            {item.changeSummary || t('settings.frameworkHistoryNoSummary')}
                          </span>
                          <span className="block text-xs text-muted-text">
                            {t('settings.frameworkHistoryCreatedAt')}
                            {': '}
                            <time dateTime={item.createdAt}>
                              {formatDateTime(item.createdAt, language)}
                            </time>
                          </span>
                        </span>
                        {item.isActive ? (
                          <Badge variant="success" size="sm">
                            {t('settings.frameworkHistoryActive')}
                          </Badge>
                        ) : null}
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}

              {selectedHistory ? (
                <section
                  className="space-y-3 border-t border-border/60 pt-3"
                  aria-label={t('settings.frameworkHistoryInspector')}
                  data-testid={`framework-history-inspector-${selectedHistory.version}`}
                >
                  <div>
                    <p className="text-sm font-semibold text-foreground">
                      {selectedHistory.content.title}
                    </p>
                    <p className="mt-1 text-xs text-muted-text">
                      {t('settings.frameworkHistoryReadOnly')}
                    </p>
                  </div>
                  <dl className="grid grid-cols-2 gap-2 text-xs">
                    <div className="col-span-2">
                      <dt className="text-muted-text">
                        {t('settings.frameworkHistoryCreatedAt')}
                      </dt>
                      <dd className="text-secondary-text">
                        <time dateTime={selectedHistory.createdAt}>
                          {formatDateTime(selectedHistory.createdAt, language)}
                        </time>
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-text">{t('settings.frameworkHistoryNodes')}</dt>
                      <dd className="text-secondary-text">
                        {selectedHistory.content.decisionTree?.length ?? 0}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-text">{t('settings.frameworkHistoryDimensions')}</dt>
                      <dd className="text-secondary-text">
                        {selectedHistory.content.evaluationDimensions?.length ?? 0}
                      </dd>
                    </div>
                  </dl>
                  <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-background/50 p-3 text-xs leading-5 text-secondary-text">
                    {JSON.stringify(selectedHistory.content, null, 2)}
                  </pre>
                  <Button
                    type="button"
                    variant="secondary"
                    size="default"
                    disabled={isSubmitting}
                    onClick={() => copyHistoryIntoDraft(selectedHistory)}
                  >
                    <Copy className="h-4 w-4" aria-hidden="true" />
                    {t('settings.frameworkCopyToDraft')}
                  </Button>
                </section>
              ) : null}
            </aside>
          </div>
        )}
      </Modal>

      <ConfirmDialog
        isOpen={deleteConfirmOpen}
        title={t('settings.frameworkDelete')}
        message={t('settings.frameworkDeleteConfirm')}
        confirmText={t('settings.frameworkDelete')}
        isDanger
        confirmDisabled={isSubmitting}
        cancelDisabled={isSubmitting}
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteConfirmOpen(false)}
      />
    </SettingsSectionCard>
  );
};

export default InvestmentFrameworkSettingsCard;
