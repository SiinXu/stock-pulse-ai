import { useState } from 'react';
import type React from 'react';
import { CheckCircle2, CircleAlert, CircleDashed, Play, RefreshCw, WandSparkles } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import type {
  SetupStatusCheck,
  SetupStatusResponse,
  SystemConfigCategory,
} from '../../types/systemConfig';
import type { UiTextKey } from '../../i18n/uiText';
import { ApiErrorAlert, Button, Loading, Surface } from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';

type FirstRunSetupCardProps = {
  status: SetupStatusResponse | null;
  isLoading: boolean;
  error: ParsedApiError | null;
  firstStockCode: string;
  isSaving: boolean;
  isRunningSmoke: boolean;
  smokeError: ParsedApiError | null;
  smokeSuccess: string;
  onRefresh: () => void | Promise<void>;
  onSelectCategory: (category: SystemConfigCategory) => void;
  onRunSmoke: () => void | Promise<void>;
  showStartWizard: boolean;
  canStartWizard: boolean;
  startWizardLabel: string;
  onStartWizard: () => void;
  listSeparator: string;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

function getSetupCheckIcon(check: SetupStatusCheck) {
  if (check.status === 'configured' || check.status === 'inherited') {
    return <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />;
  }
  if (check.status === 'needs_action') {
    return <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />;
  }
  return <CircleDashed className="mt-0.5 h-4 w-4 shrink-0 text-muted-text" aria-hidden="true" />;
}

function getSetupCheckStatusLabel(
  check: SetupStatusCheck,
  t: (key: UiTextKey, params?: Record<string, string | number>) => string,
) {
  if (check.status === 'configured') return t('settings.setupStatusConfigured');
  if (check.status === 'inherited') return t('settings.setupStatusInherited');
  if (check.status === 'needs_action') return t('settings.setupStatusNeedsAction');
  return t('settings.setupStatusOptional');
}

const FirstRunSetupCard: React.FC<FirstRunSetupCardProps> = ({
  status,
  isLoading,
  error,
  firstStockCode,
  isSaving,
  isRunningSmoke,
  smokeError,
  smokeSuccess,
  onRefresh,
  onSelectCategory,
  onRunSmoke,
  showStartWizard,
  canStartWizard,
  startWizardLabel,
  onStartWizard,
  listSeparator,
  t,
}) => {
  const [isHidden, setIsHidden] = useState(false);
  const requiredMissing = status?.checks.filter((check) => check.required && check.status === 'needs_action') || [];
  const isComplete = Boolean(status?.isComplete);
  const canRunSmoke = Boolean(status?.readyForSmoke && firstStockCode);
  const summaryTitle = !status
    ? error
      ? t('settings.setupGuideUnknownTitle')
      : t('settings.setupGuideCheckingTitle')
    : isComplete
      ? t('settings.setupGuideCompleteTitle')
      : t('settings.setupGuideIncompleteTitle');
  const summaryMessage = !status
    ? error
      ? t('settings.setupGuideUnknownSummary')
      : t('settings.setupGuideCheckingSummary')
    : requiredMissing.length
      ? t('settings.setupGuideMissingSummary', {
        count: requiredMissing.length,
        labels: requiredMissing.slice(0, 3).map((check) => check.title).join(listSeparator),
      })
      : t('settings.setupGuideReadySummary');

  if (isHidden) {
    return (
      <Surface level="interactive" className="px-4 py-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-foreground">{t('settings.setupGuideHiddenTitle')}</p>
            <p className="mt-1 text-xs leading-5 text-muted-text">{t('settings.setupGuideHiddenDescription')}</p>
          </div>
          <Button type="button" variant="secondary" size="default" onClick={() => setIsHidden(false)}>
            {t('settings.setupGuideOpen')}
          </Button>
        </div>
      </Surface>
    );
  }

  return (
    <SettingsSectionCard
      title={t('settings.setupGuideTitle')}
      description={t('settings.setupGuideDescription')}
      contentBordered
    >
      <div data-testid="first-run-setup-card" className="space-y-4">
        <Surface level="interactive" className="flex flex-col gap-3 px-4 py-4 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">
              {summaryTitle}
            </p>
            <p className="mt-1 text-xs leading-6 text-muted-text">
              {summaryMessage}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {showStartWizard ? (
              <Button
                type="button"
                variant="primary"
                size="default"
                disabled={!canStartWizard}
                onClick={onStartWizard}
              >
                <WandSparkles className="h-4 w-4" aria-hidden="true" />
                {startWizardLabel}
              </Button>
            ) : null}
            <Button
              type="button"
              variant="secondary"
              size="default"
              disabled={isLoading}
              isLoading={isLoading}
              loadingText={t('settings.setupGuideRefreshing')}
              onClick={() => void onRefresh()}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              {t('settings.setupGuideRefresh')}
            </Button>
            <Button type="button" variant="secondary" size="default" onClick={() => setIsHidden(true)}>
              {t('settings.setupGuideHide')}
            </Button>
          </div>
        </Surface>

        {error ? <ApiErrorAlert error={error} /> : null}

        {isLoading && !status ? <Loading /> : null}

        {status ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {status.checks.map((check) => (
              <Surface
                key={check.key}
                level="interactive"
                className="px-4 py-3"
              >
                <div className="flex items-start gap-3">
                  {getSetupCheckIcon(check)}
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-foreground">{check.title}</p>
                      <span className="rounded-full border settings-border bg-background/60 px-2 py-0.5 text-xs font-medium text-muted-text">
                        {getSetupCheckStatusLabel(check, t)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-muted-text">{check.message}</p>
                    {check.nextStep ? (
                      <p className="mt-2 text-xs leading-5 text-secondary-text">{check.nextStep}</p>
                    ) : null}
                  </div>
                </div>
              </Surface>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="secondary" size="default" onClick={() => onSelectCategory('ai_model')}>
            {t('settings.setupGuideConfigureLlm')}
          </Button>
          <Button type="button" variant="secondary" size="default" onClick={() => onSelectCategory('base')}>
            {t('settings.setupGuideAddStocks')}
          </Button>
          <Button type="button" variant="secondary" size="default" onClick={() => onSelectCategory('notification')}>
            {t('settings.setupGuideConfigureNotification')}
          </Button>
          <Button
            type="button"
            variant="primary"
            size="default"
            disabled={!canRunSmoke || isSaving || isRunningSmoke}
            isLoading={isRunningSmoke}
            loadingText={t('settings.setupGuideSmokeRunning')}
            title={!firstStockCode ? t('settings.setupGuideSmokeNeedsStock') : undefined}
            onClick={() => void onRunSmoke()}
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            {t('settings.setupGuideRunSmoke')}
          </Button>
        </div>

        {!canRunSmoke && status ? (
          <p className="text-xs leading-6 text-muted-text">
            {firstStockCode ? t('settings.setupGuideSmokeNotReady') : t('settings.setupGuideSmokeNeedsStock')}
          </p>
        ) : null}
        {smokeError ? <ApiErrorAlert error={smokeError} /> : null}
        {!smokeError && smokeSuccess ? (
          <SettingsAlert title={t('settings.actionSuccess')} message={smokeSuccess} variant="success" />
        ) : null}
      </div>
    </SettingsSectionCard>
  );
};

export default FirstRunSetupCard;
