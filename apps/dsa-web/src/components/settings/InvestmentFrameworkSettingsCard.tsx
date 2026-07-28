// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { investmentFrameworkApi } from '../../api/investmentFramework';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { InvestmentFrameworkContent, InvestmentFrameworkResponse } from '../../types/investmentFramework';
import { Badge, Button, Modal } from '../common';
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
  const { t } = useUiLanguage();
  const [framework, setFramework] = useState<InvestmentFrameworkResponse | null>(null);
  const [exists, setExists] = useState(false);
  const [draft, setDraft] = useState(emptyDraft);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [error, setError] = useState<string | ParsedApiError | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    setError(null);
    try {
      const current = await investmentFrameworkApi.get();
      setFramework(current);
      setExists(true);
      setDraft(draftFromResponse(current));
    } catch (err) {
      const parsed = getParsedApiError(err);
      if (parsed.status === 404 || parsed.code === 'investment_framework_not_found') {
        setFramework(null);
        setExists(false);
        setDraft(emptyDraft());
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
    const content = contentFromDraft(draft, framework?.content);
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
    const content = contentFromDraft(draft, framework?.content);
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
        setSuccessMessage(t('settings.frameworkCreated'));
      } else {
        const updated = await investmentFrameworkApi.update({
          expectedRevision: framework.revision,
          content,
          changeSummary: draft.changeSummary.trim() || t('settings.frameworkUpdateSummary'),
        });
        setFramework(updated);
        setDraft(draftFromResponse(updated));
        setSuccessMessage(t('settings.frameworkSaved'));
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
      setSuccessMessage(t('settings.frameworkDeactivated'));
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
      setSuccessMessage(t('settings.frameworkDeleted'));
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const fieldClass =
    'w-full rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] px-3 py-2 text-sm text-foreground outline-none transition-[border-color,background-color] focus:border-[var(--settings-border-strong)]';

  return (
    <SettingsSectionCard
      title={t('settings.frameworkTitle')}
      description={t('settings.frameworkDescription')}
      actions={
        <>
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
      }
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
        size="wide"
        closeDisabled={isSubmitting}
      >
        <p className="mb-4 text-xs leading-6 text-muted-text">{t('settings.frameworkDisclaimer')}</p>
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
      </Modal>
    </SettingsSectionCard>
  );
};

export default InvestmentFrameworkSettingsCard;
