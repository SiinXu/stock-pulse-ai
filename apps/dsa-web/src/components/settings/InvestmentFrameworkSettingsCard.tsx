// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Copy, History, RefreshCw, X } from 'lucide-react';
import { investmentFrameworkApi } from '../../api/investmentFramework';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type {
  InvestmentFrameworkContent,
  InvestmentFrameworkHistoryItem,
  InvestmentFrameworkHistoryResponse,
  InvestmentFrameworkResponse,
} from '../../types/investmentFramework';
import { formatDateTime } from '../../utils/format';
import { Badge, Button, IconButton } from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';

function linesToList(value: string): string[] {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function listToLines(values: string[] | undefined): string {
  return (values ?? []).join('\n');
}

function emptyDraft(): {
  title: string;
  description: string;
  freeFormRules: string;
  riskRules: string;
  trackingCriteria: string;
  changeSummary: string;
} {
  return {
    title: '',
    description: '',
    freeFormRules: '',
    riskRules: '',
    trackingCriteria: '',
    changeSummary: '',
  };
}

function contentFromDraft(
  draft: ReturnType<typeof emptyDraft>,
  existing?: InvestmentFrameworkContent | null,
): InvestmentFrameworkContent {
  const riskRules = linesToList(draft.riskRules);
  const trackingCriteria = linesToList(draft.trackingCriteria);
  const freeFormRules = draft.freeFormRules.trim() || null;
  // Preserve structured fields the minimal editor does not own so save cannot wipe them.
  return {
    schemaVersion: 'investment-framework-content-v1',
    title: draft.title.trim(),
    description: draft.description.trim() || null,
    rootNodeId: existing?.rootNodeId ?? null,
    decisionTree: existing?.decisionTree ?? [],
    evaluationDimensions: existing?.evaluationDimensions ?? [],
    riskRules,
    trackingCriteria,
    freeFormRules,
  };
}

function draftFromResponse(framework: InvestmentFrameworkResponse) {
  return {
    title: framework.content.title ?? '',
    description: framework.content.description ?? '',
    freeFormRules: framework.content.freeFormRules ?? '',
    riskRules: listToLines(framework.content.riskRules),
    trackingCriteria: listToLines(framework.content.trackingCriteria),
    changeSummary: '',
  };
}

export const InvestmentFrameworkSettingsCard: React.FC = () => {
  const { language, t } = useUiLanguage();
  const [framework, setFramework] = useState<InvestmentFrameworkResponse | null>(null);
  const [exists, setExists] = useState(false);
  const [draft, setDraft] = useState(emptyDraft);
  const [draftSourceContent, setDraftSourceContent] = useState<InvestmentFrameworkContent | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [error, setError] = useState<string | ParsedApiError | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [history, setHistory] = useState<InvestmentFrameworkHistoryResponse | null>(null);
  const [selectedHistoryVersion, setSelectedHistoryVersion] = useState<number | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<ParsedApiError | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    setError(null);
    try {
      const current = await investmentFrameworkApi.get();
      setFramework(current);
      setExists(true);
      setDraft(draftFromResponse(current));
      setDraftSourceContent(null);
    } catch (err) {
      const parsed = getParsedApiError(err);
      if (parsed.status === 404 || parsed.code === 'investment_framework_not_found') {
        setFramework(null);
        setExists(false);
        setDraft(emptyDraft());
        setDraftSourceContent(null);
      } else {
        setLoadError(parsed);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const loadHistory = useCallback(async () => {
    if (!exists) {
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
    } catch (err) {
      setHistoryError(getParsedApiError(err));
    } finally {
      setIsHistoryLoading(false);
    }
  }, [exists]);

  useEffect(() => {
    if (isHistoryOpen) {
      void loadHistory();
    }
  }, [isHistoryOpen, loadHistory]);

  const statusLabel = useMemo(() => {
    if (isLoading) {
      return t('common.loading');
    }
    if (loadError) {
      return loadError.title;
    }
    if (!exists || !framework) {
      return t('settings.frameworkStatusMissing');
    }
    return framework.isActive
      ? t('settings.frameworkStatusActive')
      : t('settings.frameworkStatusInactive');
  }, [exists, framework, isLoading, loadError, t]);

  const validateDraft = (): string | null => {
    if (!draft.title.trim()) {
      return t('settings.frameworkTitleRequired');
    }
    const content = contentFromDraft(draft, draftSourceContent ?? framework?.content);
    const hasStructured = Boolean(
      (content.decisionTree && content.decisionTree.length)
      || (content.evaluationDimensions && content.evaluationDimensions.length),
    );
    if (
      !content.freeFormRules
      && !(content.riskRules && content.riskRules.length)
      && !(content.trackingCriteria && content.trackingCriteria.length)
      && !hasStructured
    ) {
      return t('settings.frameworkCriteriaRequired');
    }
    return null;
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccessMessage(null);
    const validationError = validateDraft();
    if (validationError) {
      setError(validationError);
      return;
    }
    const content = contentFromDraft(draft, draftSourceContent ?? framework?.content);
    setIsSubmitting(true);
    try {
      if (!exists || !framework) {
        const created = await investmentFrameworkApi.create({
          content,
          changeSummary: draft.changeSummary.trim() || t('settings.frameworkInitialSummary'),
        });
        setFramework(created);
        setExists(true);
        setDraft(draftFromResponse(created));
        setDraftSourceContent(null);
        setSuccessMessage(t('settings.frameworkCreated'));
      } else {
        const updated = await investmentFrameworkApi.update({
          expectedRevision: framework.revision,
          content,
          changeSummary: draft.changeSummary.trim() || t('settings.frameworkUpdateSummary'),
        });
        setFramework(updated);
        setDraft(draftFromResponse(updated));
        setDraftSourceContent(null);
        setSuccessMessage(t('settings.frameworkSaved'));
        if (isHistoryOpen) {
          await loadHistory();
        }
      }
    } catch (err) {
      const parsed = getParsedApiError(err);
      setError(parsed);
      if (
        parsed.status === 409
        || parsed.code === 'investment_framework_revision_conflict'
      ) {
        // Refresh server state so the next save uses the current revision.
        await load();
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeactivate = async () => {
    if (!framework) {
      return;
    }
    setError(null);
    setSuccessMessage(null);
    setIsSubmitting(true);
    try {
      const updated = await investmentFrameworkApi.deactivate({
        expectedRevision: framework.revision,
      });
      setFramework(updated);
      setDraft(draftFromResponse(updated));
      setDraftSourceContent(null);
      setSuccessMessage(t('settings.frameworkDeactivated'));
      if (isHistoryOpen) {
        await loadHistory();
      }
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!framework) {
      return;
    }
    if (!window.confirm(t('settings.frameworkDeleteConfirm'))) {
      return;
    }
    setError(null);
    setSuccessMessage(null);
    setIsSubmitting(true);
    try {
      await investmentFrameworkApi.remove(framework.revision);
      setFramework(null);
      setExists(false);
      setDraft(emptyDraft());
      setDraftSourceContent(null);
      setIsHistoryOpen(false);
      setHistory(null);
      setSelectedHistoryVersion(null);
      setHistoryError(null);
      setSuccessMessage(t('settings.frameworkDeleted'));
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const fieldClass =
    'w-full rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] px-3 py-2 text-sm text-foreground outline-none transition-[border-color,background-color] focus:border-[var(--settings-border-strong)]';
  const selectedHistory = history?.items.find(
    (item) => item.version === selectedHistoryVersion,
  ) ?? null;
  const copyHistoryIntoDraft = (item: InvestmentFrameworkHistoryItem) => {
    setDraft({
      title: item.content.title ?? '',
      description: item.content.description ?? '',
      freeFormRules: item.content.freeFormRules ?? '',
      riskRules: listToLines(item.content.riskRules),
      trackingCriteria: listToLines(item.content.trackingCriteria),
      changeSummary: t('settings.frameworkCopiedSummary', { version: item.version }),
    });
    setDraftSourceContent(item.content);
    setError(null);
    setSuccessMessage(t('settings.frameworkCopiedToDraft', { version: item.version }));
  };

  return (
    <SettingsSectionCard
      title={t('settings.frameworkTitle')}
      description={t('settings.frameworkDescription')}
      actions={(
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            variant={loadError ? 'danger' : framework?.isActive ? 'success' : 'default'}
            size="sm"
            className={
              loadError || framework?.isActive
                ? ''
                : 'border-[var(--settings-border)] bg-[var(--settings-surface-hover)] text-secondary-text'
            }
          >
            {statusLabel}
          </Badge>
          <Button
            type="button"
            variant="secondary"
            size="default"
            aria-controls="investment-framework-history-drawer"
            aria-expanded={isHistoryOpen}
            disabled={!exists || isLoading}
            onClick={() => setIsHistoryOpen((current) => !current)}
          >
            <History className="h-3.5 w-3.5" aria-hidden="true" />
            {t('settings.frameworkHistory')}
          </Button>
        </div>
      )}
    >
      <div
        className={
          isHistoryOpen
            ? 'grid max-w-6xl grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]'
            : 'max-w-4xl'
        }
      >
        <div className="min-w-0 space-y-4">
          <p className="text-xs leading-6 text-muted-text">{t('settings.frameworkDisclaimer')}</p>
          {isLoading ? (
            <p className="text-sm text-muted-text">{t('common.loading')}</p>
          ) : loadError ? (
            <SettingsAlert
              title={loadError.title}
              message={loadError.message}
              actionLabel={t('common.retry')}
              onAction={() => void load()}
            />
          ) : (
            <form className="space-y-4" aria-busy={isSubmitting} onSubmit={handleSave}>
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

              <label className="block space-y-1" htmlFor="investment-framework-title">
                <span className="text-sm font-medium text-foreground">{t('settings.frameworkNameLabel')}</span>
                <input
                  id="investment-framework-title"
                  className={fieldClass}
                  value={draft.title}
                  disabled={isSubmitting}
                  onChange={(event) => setDraft((prev) => ({ ...prev, title: event.target.value }))}
                  maxLength={120}
                  required
                />
              </label>

              <label className="block space-y-1" htmlFor="investment-framework-description">
                <span className="text-sm font-medium text-foreground">{t('settings.frameworkDescLabel')}</span>
                <textarea
                  id="investment-framework-description"
                  className={`${fieldClass} min-h-20`}
                  value={draft.description}
                  disabled={isSubmitting}
                  onChange={(event) => setDraft((prev) => ({ ...prev, description: event.target.value }))}
                  maxLength={4000}
                />
              </label>

              <label className="block space-y-1" htmlFor="investment-framework-free-form">
                <span className="text-sm font-medium text-foreground">{t('settings.frameworkFreeFormLabel')}</span>
                <textarea
                  id="investment-framework-free-form"
                  className={`${fieldClass} min-h-28`}
                  value={draft.freeFormRules}
                  disabled={isSubmitting}
                  onChange={(event) => setDraft((prev) => ({ ...prev, freeFormRules: event.target.value }))}
                  maxLength={10000}
                  placeholder={t('settings.frameworkFreeFormPlaceholder')}
                />
              </label>

              <label className="block space-y-1" htmlFor="investment-framework-risk-rules">
                <span className="text-sm font-medium text-foreground">{t('settings.frameworkRiskRulesLabel')}</span>
                <textarea
                  id="investment-framework-risk-rules"
                  className={`${fieldClass} min-h-20`}
                  value={draft.riskRules}
                  disabled={isSubmitting}
                  onChange={(event) => setDraft((prev) => ({ ...prev, riskRules: event.target.value }))}
                  placeholder={t('settings.frameworkListPlaceholder')}
                />
              </label>

              <label className="block space-y-1" htmlFor="investment-framework-tracking">
                <span className="text-sm font-medium text-foreground">{t('settings.frameworkTrackingLabel')}</span>
                <textarea
                  id="investment-framework-tracking"
                  className={`${fieldClass} min-h-20`}
                  value={draft.trackingCriteria}
                  disabled={isSubmitting}
                  onChange={(event) => setDraft((prev) => ({ ...prev, trackingCriteria: event.target.value }))}
                  placeholder={t('settings.frameworkListPlaceholder')}
                />
              </label>

              <label className="block space-y-1" htmlFor="investment-framework-change-summary">
                <span className="text-sm font-medium text-foreground">{t('settings.frameworkChangeSummaryLabel')}</span>
                <input
                  id="investment-framework-change-summary"
                  className={fieldClass}
                  value={draft.changeSummary}
                  disabled={isSubmitting}
                  onChange={(event) => setDraft((prev) => ({ ...prev, changeSummary: event.target.value }))}
                  maxLength={500}
                />
              </label>

              {error ? (
                <SettingsAlert
                  title={t('settings.frameworkSaveFailed')}
                  message={typeof error === 'string' ? error : error.message}
                  variant="error"
                />
              ) : null}
              {successMessage ? (
                <SettingsAlert title={t('settings.actionSuccess')} message={successMessage} variant="success" />
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
                    variant="secondary"
                    disabled={isSubmitting}
                    onClick={() => void handleDelete()}
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
          )}
        </div>

        {isHistoryOpen ? (
          <aside
            id="investment-framework-history-drawer"
            className="min-w-0 self-start rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4 shadow-soft-card"
            aria-label={t('settings.frameworkHistory')}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <History className="h-4 w-4" aria-hidden="true" />
                  {t('settings.frameworkHistory')}
                </h3>
                <p className="mt-1 text-xs leading-5 text-muted-text">
                  {t('settings.frameworkHistoryDescription')}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <IconButton
                  type="button"
                  variant="ghost"
                  size="compact"
                  aria-label={t('settings.frameworkHistoryRefresh')}
                  disabled={isHistoryLoading}
                  onClick={() => void loadHistory()}
                >
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                </IconButton>
                <IconButton
                  type="button"
                  variant="ghost"
                  size="compact"
                  aria-label={t('settings.frameworkHistoryClose')}
                  onClick={() => setIsHistoryOpen(false)}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </IconButton>
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {isHistoryLoading && !history ? (
                <p role="status" className="text-xs text-muted-text">
                  {t('settings.frameworkHistoryLoading')}
                </p>
              ) : null}
              {historyError ? (
                <SettingsAlert
                  title={historyError.title}
                  message={historyError.message}
                  actionLabel={t('common.retry')}
                  onAction={() => void loadHistory()}
                />
              ) : null}
              {!isHistoryLoading && !historyError && (!history || history.items.length === 0) ? (
                <p className="rounded-lg border border-dashed border-[var(--settings-border)] p-3 text-xs text-muted-text">
                  {t('settings.frameworkHistoryEmpty')}
                </p>
              ) : null}
              {history?.items.length ? (
                <div
                  className="max-h-56 space-y-2 overflow-y-auto pr-1"
                  role="list"
                  aria-label={t('settings.frameworkHistory')}
                >
                  {history.items.map((item) => (
                    <div key={item.version} role="listitem">
                      <button
                        type="button"
                        aria-pressed={selectedHistoryVersion === item.version}
                        className="flex w-full items-center justify-between gap-2 rounded-lg border border-[var(--settings-border)] px-3 py-2 text-left transition-colors hover:bg-[var(--settings-surface-hover)]"
                        onClick={() => setSelectedHistoryVersion(item.version)}
                      >
                        <span className="min-w-0">
                          <span className="block text-sm font-medium text-foreground">
                            {t('settings.frameworkHistoryVersion', { version: item.version })}
                          </span>
                          <span className="block truncate text-xs text-muted-text">
                            {item.changeSummary || t('settings.frameworkHistoryNoSummary')}
                          </span>
                          <time className="block text-xs text-muted-text" dateTime={item.createdAt}>
                            {formatDateTime(item.createdAt, language)}
                          </time>
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
                  className="space-y-3 border-t border-[var(--settings-border)] pt-3"
                  aria-label={t('settings.frameworkHistoryDetails')}
                >
                  <div>
                    <p className="text-sm font-semibold text-foreground">
                      {selectedHistory.content.title}
                    </p>
                    <p className="mt-1 text-xs text-muted-text">
                      {selectedHistory.content.description || t('settings.frameworkHistoryNoSummary')}
                    </p>
                  </div>
                  {selectedHistory.content.freeFormRules ? (
                    <div>
                      <h4 className="text-xs font-medium text-secondary-text">
                        {t('settings.frameworkFreeFormLabel')}
                      </h4>
                      <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-muted-text">
                        {selectedHistory.content.freeFormRules}
                      </p>
                    </div>
                  ) : null}
                  {selectedHistory.content.riskRules?.length ? (
                    <div>
                      <h4 className="text-xs font-medium text-secondary-text">
                        {t('settings.frameworkRiskRulesLabel')}
                      </h4>
                      <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5 text-muted-text">
                        {selectedHistory.content.riskRules.map((rule) => (
                          <li key={rule}>{rule}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {selectedHistory.content.trackingCriteria?.length ? (
                    <div>
                      <h4 className="text-xs font-medium text-secondary-text">
                        {t('settings.frameworkTrackingLabel')}
                      </h4>
                      <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5 text-muted-text">
                        {selectedHistory.content.trackingCriteria.map((criterion) => (
                          <li key={criterion}>{criterion}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
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
            </div>
          </aside>
        ) : null}
      </div>
    </SettingsSectionCard>
  );
};

export default InvestmentFrameworkSettingsCard;
