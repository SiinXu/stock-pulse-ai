// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useEffect, useState } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { WEB_BUILD_INFO } from '../../utils/constants';
import { Button, Surface } from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';
import {
  type DesktopUpdateState,
  getDesktopAppVersion,
  getDesktopRuntimeApi,
  getDesktopUpdateNotice,
  normalizeDesktopUpdateState,
} from './desktopUpdateModel';

/** System → About: version cards and desktop update controls. */
const SystemAboutCard: React.FC = () => {
  const { t } = useUiLanguage();
  const desktopRuntimeApi = getDesktopRuntimeApi();
  const canCheckDesktopUpdate = Boolean(
    desktopRuntimeApi?.getUpdateState && desktopRuntimeApi?.checkForUpdates && desktopRuntimeApi?.openReleasePage,
  );
  const desktopAppVersion = getDesktopAppVersion();
  const shouldShowDesktopVersionCard = Boolean(desktopAppVersion);

  const [desktopUpdateState, setDesktopUpdateState] = useState<DesktopUpdateState | null>(null);
  const [isCheckingDesktopUpdate, setIsCheckingDesktopUpdate] = useState(false);

  useEffect(() => {
    if (!canCheckDesktopUpdate) {
      setDesktopUpdateState(null);
      setIsCheckingDesktopUpdate(false);
      return;
    }

    let active = true;

    const syncDesktopUpdateState = async () => {
      try {
        const state = await desktopRuntimeApi?.getUpdateState?.();
        if (active) {
          setDesktopUpdateState(normalizeDesktopUpdateState(state));
        }
      } catch (error: unknown) {
        if (!active) {
          return;
        }
        setDesktopUpdateState({
          status: 'error',
          message: error instanceof Error ? error.message : t('settings.desktopUpdateErrorMessage'),
        });
      }
    };

    void syncDesktopUpdateState();

    const unsubscribe = desktopRuntimeApi?.onUpdateStateChange?.((state) => {
      if (!active) {
        return;
      }
      setDesktopUpdateState(normalizeDesktopUpdateState(state));
      setIsCheckingDesktopUpdate(false);
    });

    return () => {
      active = false;
      if (typeof unsubscribe === 'function') {
        unsubscribe();
      }
    };
  }, [canCheckDesktopUpdate, desktopRuntimeApi, t]);

  const handleDesktopUpdateCheck = async () => {
    if (!desktopRuntimeApi?.checkForUpdates) {
      return;
    }

    setIsCheckingDesktopUpdate(true);
    setDesktopUpdateState((current) => ({
      ...(current || {}),
      status: 'checking',
      message: t('settings.desktopUpdateCheckingMessage'),
    }));

    try {
      const state = await desktopRuntimeApi.checkForUpdates();
      setDesktopUpdateState(normalizeDesktopUpdateState(state));
    } catch (error: unknown) {
      setDesktopUpdateState({
        status: 'error',
        message: error instanceof Error ? error.message : t('settings.desktopUpdateErrorMessage'),
      });
    } finally {
      setIsCheckingDesktopUpdate(false);
    }
  };

  const openDesktopReleasePage = async () => {
    if (!desktopRuntimeApi?.openReleasePage) {
      return;
    }
    await desktopRuntimeApi.openReleasePage(desktopUpdateState?.releaseUrl);
  };

  const installDesktopUpdate = async () => {
    if (!desktopRuntimeApi?.installDownloadedUpdate) {
      setDesktopUpdateState((current) => ({
        ...(current || {}),
        status: 'error',
        message: t('settings.desktopManualUnsupported'),
      }));
      return;
    }

    try {
      setDesktopUpdateState((current) => ({
        ...(current || {}),
        status: 'installing',
        message: t('settings.desktopUpdateInstallingMessage'),
      }));
      await desktopRuntimeApi.installDownloadedUpdate();
    } catch (error: unknown) {
      setDesktopUpdateState((current) => ({
        ...(current || {}),
        status: 'error',
        message: error instanceof Error ? error.message : t('settings.desktopManualUnsupported'),
      }));
    }
  };

  const desktopUpdateNotice = getDesktopUpdateNotice(desktopUpdateState, t);

  return (
    <SettingsSectionCard
      title={t('settings.versionInfo')}
      description={t('settings.versionInfoDescription')}
      contentBordered
    >
      <div
        className={`grid grid-cols-1 gap-3 ${shouldShowDesktopVersionCard ? 'md:grid-cols-4' : 'md:grid-cols-3'}`}
      >
        <Surface level="interactive" className="px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-text">
            {t('settings.versionWebui')}
          </p>
          <p className="mt-2 break-all font-mono text-sm text-foreground">
            {WEB_BUILD_INFO.version}
          </p>
        </Surface>
        <Surface level="interactive" className="px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-text">
            {t('settings.versionBuildId')}
          </p>
          <p className="mt-2 break-all font-mono text-sm text-foreground">
            {WEB_BUILD_INFO.buildId}
          </p>
        </Surface>
        <Surface level="interactive" className="px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-text">
            {t('settings.versionBuildTime')}
          </p>
          <p className="mt-2 break-all font-mono text-sm text-foreground">
            {WEB_BUILD_INFO.buildTime}
          </p>
        </Surface>
        {shouldShowDesktopVersionCard ? (
          <Surface level="interactive" className="px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-text">
              {t('settings.versionDesktop')}
            </p>
            <p className="mt-2 break-all font-mono text-sm text-foreground">
              {desktopAppVersion}
            </p>
          </Surface>
        ) : null}
      </div>
      <p className="text-xs leading-6 text-muted-text">
        {t('settings.updateBuildDescription')}
      </p>
      {canCheckDesktopUpdate ? (
        <Surface level="interactive" className="mt-4 space-y-3 px-4 py-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-medium text-foreground">{t('settings.desktopUpdate')}</p>
              <p className="text-xs leading-6 text-muted-text">
                {t('settings.desktopUpdateDescription')}
              </p>
            </div>
            <Button
              type="button"
              variant="secondary"
              onClick={() => void handleDesktopUpdateCheck()}
              disabled={isCheckingDesktopUpdate}
              isLoading={isCheckingDesktopUpdate}
              loadingText={t('settings.checkingDesktopUpdate')}
            >
              {t('settings.checkDesktopUpdate')}
            </Button>
          </div>
          {desktopUpdateNotice ? (
            <SettingsAlert
              title={desktopUpdateNotice.title}
              message={desktopUpdateNotice.message}
              variant={desktopUpdateNotice.variant}
              actionLabel={desktopUpdateNotice.actionLabel}
              onAction={desktopUpdateNotice.actionLabel ? () => {
                if (desktopUpdateNotice.actionKind === 'install') {
                  void installDesktopUpdate();
                  return;
                }
                void openDesktopReleasePage();
              } : undefined}
            />
          ) : (
            <p className="text-xs leading-6 text-muted-text">
              {t('settings.desktopCurrentNoStatus')}
            </p>
          )}
        </Surface>
      ) : null}
      {WEB_BUILD_INFO.isFallbackVersion ? (
        <p className="text-xs leading-6 text-amber-700 dark:text-amber-300">
          {t('settings.fallbackVersionWarning')}
        </p>
      ) : null}
    </SettingsSectionCard>
  );
};

export default SystemAboutCard;
