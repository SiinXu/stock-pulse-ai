// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useState } from 'react';
import { alphasiftApi, notifyAlphaSiftConfigChanged } from '../../api/alphasift';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { systemConfigApi } from '../../api/systemConfig';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { ApiErrorAlert, Button, Surface } from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';

export type AlphaSiftSettingsCardProps = {
  enabled: boolean;
  configVersion: string;
  maskToken: string;
  disabled: boolean;
  onViewConfigItems: () => void;
  onAfterChange: () => Promise<void>;
};

/** Data Sources → Providers: AlphaSift enable/disable surface. */
const AlphaSiftSettingsCard: React.FC<AlphaSiftSettingsCardProps> = ({
  enabled,
  configVersion,
  maskToken,
  disabled,
  onViewConfigItems,
  onAfterChange,
}) => {
  const { t } = useUiLanguage();
  const [isUpdating, setIsUpdating] = useState(false);
  const [actionError, setActionError] = useState<ParsedApiError | null>(null);
  const [actionSuccess, setActionSuccess] = useState('');

  const updateEnabled = async (nextEnabled: boolean) => {
    setActionError(null);
    setActionSuccess('');
    setIsUpdating(true);
    try {
      if (nextEnabled) {
        await alphasiftApi.enable();
        await onAfterChange();
        setActionSuccess(t('settings.enabledAlphaSiftSuccess'));
        return;
      }

      await systemConfigApi.update({
        configVersion,
        maskToken,
        reloadNow: true,
        items: [{ key: 'ALPHASIFT_ENABLED', value: 'false' }],
      });
      notifyAlphaSiftConfigChanged();
      await onAfterChange();
      setActionSuccess(t('settings.disabledAlphaSiftSuccess'));
    } catch (error: unknown) {
      setActionError(getParsedApiError(error));
      await onAfterChange();
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <SettingsSectionCard
      title={t('settings.alphaSift')}
      description={t('settings.alphaSiftDescription')}
    >
      <Surface level="interactive" className="flex flex-col gap-4 px-4 py-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <p className="text-sm font-semibold text-foreground">
            {enabled ? t('settings.alphaSiftEnabled') : t('settings.alphaSiftDisabled')}
          </p>
          <p className="mt-1 text-xs leading-6 text-muted-text">
            {t('settings.alphaSiftSummary')}
          </p>
          <p className="mt-2 text-xs leading-6 text-amber-700 dark:text-amber-300">
            {t('settings.alphaSiftRisk')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="secondary" onClick={onViewConfigItems}>
            {t('settings.viewConfigItems')}
          </Button>
          <Button
            type="button"
            variant={enabled ? 'secondary' : 'primary'}
            onClick={() => void updateEnabled(!enabled)}
            disabled={disabled || isUpdating}
            isLoading={isUpdating}
            loadingText={enabled ? t('settings.disablingAlphaSift') : t('settings.enablingAlphaSift')}
          >
            {enabled ? t('settings.disableAlphaSift') : t('settings.enableAlphaSift')}
          </Button>
        </div>
      </Surface>
      {actionError ? (
        <div className="mt-3">
          <ApiErrorAlert error={actionError} />
        </div>
      ) : null}
      {!actionError && actionSuccess ? (
        <div className="mt-3">
          <SettingsAlert title={t('settings.actionSuccess')} message={actionSuccess} variant="success" />
        </div>
      ) : null}
    </SettingsSectionCard>
  );
};

export default AlphaSiftSettingsCard;
