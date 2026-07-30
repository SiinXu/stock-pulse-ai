// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useState } from 'react';
import type React from 'react';
import { RotateCcw } from 'lucide-react';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../../api/error';
import { SystemConfigConflictError, systemConfigApi } from '../../api/systemConfig';
import type { UpdateSystemConfigResponse } from '../../types/systemConfig';
import { ApiErrorAlert, Button, ConfirmDialog, Surface } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { SettingsAlert } from './SettingsAlert';

type SystemConfigRollbackCardProps = {
  configVersion: string;
  disabled?: boolean;
  onRolledBack: (result: UpdateSystemConfigResponse) => Promise<void>;
  onReloadLatest: () => Promise<void>;
};

const SystemConfigRollbackCard: React.FC<SystemConfigRollbackCardProps> = ({
  configVersion,
  disabled = false,
  onRolledBack,
  onReloadLatest,
}) => {
  const { t } = useUiLanguage();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [isReloading, setIsReloading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [success, setSuccess] = useState('');

  const reloadLatest = async () => {
    setIsReloading(true);
    setError(null);
    try {
      await onReloadLatest();
    } catch (reloadError: unknown) {
      setError(getParsedApiError(reloadError));
    } finally {
      setIsReloading(false);
    }
  };

  const rollback = async () => {
    if (!configVersion || isRollingBack) {
      return;
    }
    setIsRollingBack(true);
    setError(null);
    setSuccess('');
    try {
      const result = await systemConfigApi.rollback({ configVersion });
      setConfirmOpen(false);
      try {
        await onRolledBack(result);
        setSuccess(t('settings.rollbackSuccess'));
      } catch {
        setError(createParsedApiError({
          title: t('settings.rollbackRefreshFailedTitle'),
          message: t('settings.rollbackRefreshFailedMessage'),
          rawMessage: t('settings.rollbackRefreshFailedMessage'),
          category: 'http_error',
        }));
      }
    } catch (rollbackError: unknown) {
      setConfirmOpen(false);
      if (rollbackError instanceof SystemConfigConflictError) {
        setError(rollbackError.parsedError);
      } else {
        setError(getParsedApiError(rollbackError));
      }
    } finally {
      setIsRollingBack(false);
    }
  };

  return (
    <Surface level="interactive" className="space-y-3 p-4" data-testid="settings-config-rollback">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{t('settings.rollbackTitle')}</h3>
          <p className="mt-1 text-xs leading-5 text-secondary-text">
            {t('settings.rollbackDescription')}
          </p>
          <p className="mt-2 break-all font-mono text-xs text-muted-text">
            {t('settings.rollbackCurrentVersion', { version: configVersion || '—' })}
          </p>
        </div>
        <Button
          type="button"
          variant="danger"
          size="default"
          disabled={disabled || !configVersion || isRollingBack || isReloading}
          isLoading={isRollingBack}
          onClick={() => setConfirmOpen(true)}
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          {t('settings.rollbackAction')}
        </Button>
      </div>

      {error ? (
        <ApiErrorAlert
          error={error}
          actionLabel={error.code === 'config_version_conflict' ? t('settings.rollbackReloadLatest') : undefined}
          onAction={error.code === 'config_version_conflict' ? () => void reloadLatest() : undefined}
        />
      ) : null}
      {!error && success ? (
        <SettingsAlert title={t('settings.actionSuccess')} message={success} variant="success" />
      ) : null}

      <ConfirmDialog
        isOpen={confirmOpen}
        title={t('settings.rollbackConfirmTitle')}
        message={t('settings.rollbackConfirmMessage', { version: configVersion })}
        confirmText={t('settings.rollbackConfirmAction')}
        confirmDisabled={isRollingBack}
        cancelDisabled={isRollingBack}
        isDanger
        onConfirm={() => void rollback()}
        onCancel={() => setConfirmOpen(false)}
      />
    </Surface>
  );
};

export default SystemConfigRollbackCard;
