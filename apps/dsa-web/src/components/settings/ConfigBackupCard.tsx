// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useRef, useState } from 'react';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../../api/error';
import { notifySystemConfigChanged } from '../../api/alphasift';
import { systemConfigApi } from '../../api/systemConfig';
import { useAuth } from '../../hooks';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UpdateSystemConfigResponse } from '../../types/systemConfig';
import { ApiErrorAlert, Button, ConfirmDialog, FileInput, Surface } from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';
import SystemConfigRollbackCard from './SystemConfigRollbackCard';
import { getDesktopRuntimeApi } from './desktopUpdateModel';
import { formatEnvBackupFilename } from './envBackupModel';
import { SCHEDULER_SETTING_KEYS } from './settingsFieldPlacement';

export type ConfigBackupCardProps = {
  configVersion: string;
  hasDirty: boolean;
  disabled: boolean;
  load: () => Promise<boolean>;
  onSchedulerKeysImported: () => void;
  onRefreshSetupStatus: () => void;
  onRolledBack: (result: UpdateSystemConfigResponse) => Promise<void>;
  onReloadLatest: () => Promise<void>;
};

/**
 * Advanced → Backup: env export/import and system-config rollback.
 * Preserves the download helper pattern (blob + anchor click).
 */
const ConfigBackupCard: React.FC<ConfigBackupCardProps> = ({
  configVersion,
  hasDirty,
  disabled,
  load,
  onSchedulerKeysImported,
  onRefreshSetupStatus,
  onRolledBack,
  onReloadLatest,
}) => {
  const { authEnabled } = useAuth();
  const { t } = useUiLanguage();
  const isDesktopRuntime = Boolean(getDesktopRuntimeApi());
  const isEnvBackupAllowed = isDesktopRuntime || authEnabled;
  const envBackupImportRef = useRef<HTMLInputElement | null>(null);

  const [envBackupActionError, setEnvBackupActionError] = useState<ParsedApiError | null>(null);
  const [envBackupActionSuccess, setEnvBackupActionSuccess] = useState('');
  const [isExportingEnv, setIsExportingEnv] = useState(false);
  const [isImportingEnv, setIsImportingEnv] = useState(false);
  const [showImportConfirm, setShowImportConfirm] = useState(false);

  const envBackupActionDisabled = disabled || isExportingEnv || isImportingEnv || !isEnvBackupAllowed;

  const downloadEnvBackup = async () => {
    setEnvBackupActionError(null);
    setEnvBackupActionSuccess('');
    setIsExportingEnv(true);
    try {
      const payload = await systemConfigApi.exportEnv();
      const blob = new Blob([payload.content], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = formatEnvBackupFilename(isDesktopRuntime);
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      setEnvBackupActionSuccess(t('settings.envExported'));
    } catch (error: unknown) {
      setEnvBackupActionError(getParsedApiError(error));
    } finally {
      setIsExportingEnv(false);
    }
  };

  const beginEnvBackupImport = () => {
    setEnvBackupActionError(null);
    setEnvBackupActionSuccess('');
    if (hasDirty) {
      setShowImportConfirm(true);
      return;
    }
    envBackupImportRef.current?.click();
  };

  const handleEnvBackupImportFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    setShowImportConfirm(false);
    if (!file) {
      return;
    }

    setEnvBackupActionError(null);
    setEnvBackupActionSuccess('');
    setIsImportingEnv(true);
    try {
      const content = await file.text();
      const importResult = await systemConfigApi.importEnv({
        configVersion,
        content,
        reloadNow: true,
      });
      const reloaded = await load();
      if (!reloaded) {
        setEnvBackupActionError(createParsedApiError({
          title: t('settings.envImportedRefreshFailedTitle'),
          message: t('settings.envImportedRefreshFailedMessage'),
          rawMessage: t('settings.envImportedRefreshFailedRaw'),
          category: 'http_error',
        }));
        return;
      }
      if (importResult.updatedKeys.some((key) => SCHEDULER_SETTING_KEYS.has(key))) {
        onSchedulerKeysImported();
      }
      notifySystemConfigChanged();
      onRefreshSetupStatus();
      setEnvBackupActionSuccess(t('settings.envImported'));
    } catch (error: unknown) {
      setEnvBackupActionError(getParsedApiError(error));
    } finally {
      setIsImportingEnv(false);
    }
  };

  return (
    <>
      <SettingsSectionCard
        title={t('settings.configBackup')}
        description={t('settings.configBackupDescription')}
      >
        <Surface level="interactive" className="space-y-4 p-4">
          {!isEnvBackupAllowed ? (
            <p className="text-xs leading-6 text-amber-700 dark:text-amber-300">
              {t('settings.disabledAuthBackupWarning')}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              variant="secondary"
              onClick={() => void downloadEnvBackup()}
              disabled={envBackupActionDisabled}
              isLoading={isExportingEnv}
              loadingText={t('settings.exportingEnv')}
            >
              {t('settings.exportEnv')}
            </Button>
            <Button
              type="button"
              variant="primary"
              onClick={beginEnvBackupImport}
              disabled={envBackupActionDisabled}
              isLoading={isImportingEnv}
              loadingText={t('settings.importingEnv')}
            >
              {t('settings.importEnv')}
            </Button>
            <FileInput
              ref={envBackupImportRef}
              accept=".env,.txt"
              onChange={(event) => {
                void handleEnvBackupImportFile(event);
              }}
            />
          </div>
          <p className="text-xs leading-6 text-muted-text">
            {t('settings.envExportNote')}
          </p>
          <p className="text-xs leading-6 text-muted-text">
            {t('settings.envDockerNote')}
          </p>
          {envBackupActionError ? (
            <ApiErrorAlert
              error={envBackupActionError}
              actionLabel={envBackupActionError.status === 409 ? t('settings.reload') : undefined}
              onAction={envBackupActionError.status === 409 ? () => void load() : undefined}
            />
          ) : null}
          {!envBackupActionError && envBackupActionSuccess ? (
            <SettingsAlert title={t('settings.actionSuccess')} message={envBackupActionSuccess} variant="success" />
          ) : null}
        </Surface>
        <SystemConfigRollbackCard
          configVersion={configVersion}
          disabled={disabled || isImportingEnv || isExportingEnv}
          onRolledBack={onRolledBack}
          onReloadLatest={onReloadLatest}
        />
      </SettingsSectionCard>
      <ConfirmDialog
        isOpen={showImportConfirm}
        title={t('settings.importConfirmTitle')}
        message={t('settings.importConfirmMessage')}
        confirmText={t('settings.importConfirmContinue')}
        cancelText={t('common.cancel')}
        onConfirm={() => {
          setShowImportConfirm(false);
          envBackupImportRef.current?.click();
        }}
        onCancel={() => {
          setShowImportConfirm(false);
        }}
      />
    </>
  );
};

export default ConfigBackupCard;
