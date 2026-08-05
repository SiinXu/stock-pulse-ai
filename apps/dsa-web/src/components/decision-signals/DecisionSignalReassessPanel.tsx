// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { RefreshCw, ShieldCheck } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  Button,
  InlineAlert,
  Select,
  Surface,
} from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import type {
  DecisionProfile,
  DecisionSignalReassessBlockedError,
  DecisionSignalReassessResponse,
} from '../../types/decisionSignals';
import { buildDecisionActionLabelMap } from '../../utils/decisionAction';
import {
  isRecord,
  REASSESS_PROFILES,
  STATUS_LABEL_KEYS,
} from './decisionSignalsPageModel';

export type DecisionSignalReassessPanelProps = {
  sourceReportId: number | undefined;
  profile: DecisionProfile;
  onProfileChange: (profile: DecisionProfile) => void;
  response: DecisionSignalReassessResponse | null;
  loading: boolean;
  persisting: boolean;
  persistBlocked: DecisionSignalReassessBlockedError | null;
  error: ParsedApiError | null;
  onPreview: () => void;
  onRequestPersist: () => void;
};

export const DecisionSignalReassessPanel: React.FC<DecisionSignalReassessPanelProps> = ({
  sourceReportId,
  profile,
  onProfileChange,
  response,
  loading,
  persisting,
  persistBlocked,
  error,
  onPreview,
  onRequestPersist,
}) => {
  const { t } = useUiLanguage();
  const actionLabels = buildDecisionActionLabelMap(t);
  const preview = response?.preview ?? null;
  const persistedItem = response?.item ?? null;
  const persistStatus = response?.persistStatus ?? null;
  const terminalExisting = persistStatus === 'existing' && persistedItem?.status !== 'active';
  const persistedAlertVariant = terminalExisting
    ? 'warning'
    : persistStatus === 'existing'
      ? 'info'
      : 'success';
  const persistedTitleKey: UiTextKey = terminalExisting
    ? 'decisionSignals.reassessPersistedTerminalTitle'
    : persistStatus === 'existing'
      ? 'decisionSignals.reassessPersistedExistingTitle'
      : persistStatus === 'refreshed'
        ? 'decisionSignals.reassessPersistedRefreshedTitle'
        : 'decisionSignals.reassessPersistedCreatedTitle';
  const persistedMessageKey: UiTextKey = terminalExisting
    ? 'decisionSignals.reassessPersistedTerminalExisting'
    : persistStatus === 'existing'
      ? 'decisionSignals.reassessPersistedExisting'
      : persistStatus === 'refreshed'
        ? 'decisionSignals.reassessPersistedRefreshed'
        : 'decisionSignals.reassessPersistedCreated';
  const metadata = preview?.metadata ?? {};
  const guardrail = isRecord(metadata.guardrail_result) ? metadata.guardrail_result : null;
  const rawAction = typeof guardrail?.raw_action === 'string' ? guardrail.raw_action : null;
  const finalAction = typeof guardrail?.final_action === 'string' ? guardrail.final_action : null;
  const passed = typeof guardrail?.passed === 'boolean' ? guardrail.passed : null;

  return (
    <Surface level="interactive" padding="sm">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{t('decisionSignals.reassessTitle')}</h3>
          </div>
          <p className="mt-1 text-xs text-secondary-text">
            {sourceReportId
              ? t('decisionSignals.reassessSource', { id: sourceReportId })
              : t('decisionSignals.reassessUnsupported')}
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Select
            value={profile}
            onChange={(value) => onProfileChange(value as DecisionProfile)}
            ariaLabel={t('decisionSignals.reassessProfile')}
            disabled={!sourceReportId || loading || persisting}
            options={REASSESS_PROFILES.map((option) => ({
              value: option,
              label: t(`decisionSignals.profile.${option}` as UiTextKey),
            }))}
          />
          <Button
            type="button"
            variant="secondary"
            size="comfortable"
            onClick={onPreview}
            disabled={!sourceReportId || loading || persisting}
            isLoading={loading}
            loadingText={t('decisionSignals.reassessPreview')}
          >
            <RefreshCw className="h-4 w-4" />
            {t('decisionSignals.reassessPreview')}
          </Button>
        </div>
      </div>

      {!sourceReportId ? (
        <InlineAlert
          className="mt-3"
          variant="warning"
          title={t('decisionSignals.reassessUnsupportedTitle')}
          message={t('decisionSignals.reassessUnsupported')}
        />
      ) : null}
      {error ? <ApiErrorAlert className="mt-3" error={error} /> : null}
      {persistBlocked ? (
        <div className="mt-3 space-y-2">
          <InlineAlert
            variant="danger"
            title={t('decisionSignals.reassessPersistBlockedTitle')}
            message={persistBlocked.blockedReason}
          />
          {persistBlocked.warnings.length ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-secondary-text">
              {persistBlocked.warnings.map((warning, index) => (
                <li key={`${warning.code}-${index}`}>{warning.message || warning.code}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {persistedItem ? (
        <InlineAlert
          className="mt-3"
          variant={persistedAlertVariant}
          title={t(persistedTitleKey)}
          message={t(
            persistedMessageKey,
            {
              id: persistedItem.id,
              status: t(STATUS_LABEL_KEYS[persistedItem.status]),
            },
          )}
        />
      ) : null}
      {preview ? (
        <div className="mt-4 space-y-3">
          {response?.blockedReason ? (
            <InlineAlert
              variant="warning"
              title={t('decisionSignals.reassessBlockedTitle')}
              message={response.blockedReason}
            />
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Surface level="interactive" padding="sm">
              <p className="text-xs text-secondary-text">{t('decisionSignals.action')}</p>
              <p className="mt-1 text-sm font-semibold text-foreground">{actionLabels[preview.action]}</p>
            </Surface>
            <Surface level="interactive" padding="sm">
              <p className="text-xs text-secondary-text">{t('decisionSignals.score')}</p>
              <p className="mt-1 text-sm font-semibold text-foreground">{preview.score ?? '-'}</p>
            </Surface>
            <Surface level="interactive" padding="sm">
              <p className="text-xs text-secondary-text">{t('decisionSignals.confidence')}</p>
              <p className="mt-1 text-sm font-semibold text-foreground">{preview.confidence ?? '-'}</p>
            </Surface>
            <Surface level="interactive" padding="sm">
              <p className="text-xs text-secondary-text">{t('decisionSignals.horizon')}</p>
              <p className="mt-1 text-sm font-semibold text-foreground">{preview.horizon ?? '-'}</p>
            </Surface>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Surface level="interactive" padding="sm">
              <p className="text-xs text-secondary-text">{t('decisionSignals.entryRange')}</p>
              <p className="mt-1 text-sm text-foreground">
                {preview.entryLow || preview.entryHigh
                  ? `${preview.entryLow ?? '-'} ~ ${preview.entryHigh ?? '-'}`
                  : '-'}
              </p>
            </Surface>
            <Surface level="interactive" padding="sm">
              <p className="text-xs text-secondary-text">{t('decisionSignals.stopLoss')}</p>
              <p className="mt-1 text-sm text-foreground">{preview.stopLoss ?? '-'}</p>
            </Surface>
            <Surface level="interactive" padding="sm">
              <p className="text-xs text-secondary-text">{t('decisionSignals.targetPrice')}</p>
              <p className="mt-1 text-sm text-foreground">{preview.targetPrice ?? '-'}</p>
            </Surface>
            <Surface level="interactive" padding="sm">
              <p className="text-xs text-secondary-text">{t('decisionSignals.reassessRawFinal')}</p>
              <p className="mt-1 text-sm text-foreground">{rawAction ?? '-'} {'->'} {finalAction ?? '-'}</p>
            </Surface>
          </div>
          <div className="space-y-2 text-sm text-secondary-text">
            {passed === false ? (
              <p className="font-medium text-warning">{t('decisionSignals.reassessBlockedNote')}</p>
            ) : null}
            {preview.invalidation ? <p><span className="text-foreground">{t('decisionSignals.invalidation')}:</span> {preview.invalidation}</p> : null}
            {preview.reason ? <p><span className="text-foreground">{t('decisionSignals.reason')}:</span> {preview.reason}</p> : null}
            {preview.riskSummary ? <p><span className="text-foreground">{t('decisionSignals.riskSummary')}:</span> {preview.riskSummary}</p> : null}
            {preview.watchConditions ? <p><span className="text-foreground">{t('decisionSignals.watchConditions')}:</span> {preview.watchConditions}</p> : null}
          </div>
          {response?.warnings.length ? (
            <InlineAlert
              variant="warning"
              title={t('decisionSignals.reassessWarnings')}
              message={(
                <ul className="list-disc space-y-1 pl-4">
                  {response.warnings.map((warning, index) => (
                    <li key={`${warning.code}-${index}`}>{warning.message || warning.code}</li>
                  ))}
                </ul>
              )}
            />
          ) : null}
          {passed === true ? (
            <div className="flex justify-end">
              <Button
                type="button"
                variant="primary"
                size="primary"
                onClick={onRequestPersist}
                disabled={loading || persisting}
                isLoading={persisting}
                loadingText={t('decisionSignals.reassessPersisting')}
              >
                <ShieldCheck className="h-4 w-4" />
                {t('decisionSignals.reassessPersist')}
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
      {persistedItem && response?.warnings.length ? (
        <InlineAlert
          className="mt-3"
          variant="warning"
          title={t('decisionSignals.reassessWarnings')}
          message={(
            <ul className="list-disc space-y-1 pl-4">
              {response.warnings.map((warning, index) => (
                <li key={`${warning.code}-${index}`}>{warning.message || warning.code}</li>
              ))}
            </ul>
          )}
        />
      ) : null}
    </Surface>
  );
};
