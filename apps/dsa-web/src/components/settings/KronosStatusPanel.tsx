// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useRef, useState } from 'react';
import type React from 'react';
import { CheckCircle2, CircleAlert, RefreshCw } from 'lucide-react';
import { systemConfigApi } from '../../api/systemConfig';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { KronosStatusResponse } from '../../types/systemConfig';
import { ApiErrorAlert, Badge, Button, Surface } from '../common';
import { SettingsAlert } from './SettingsAlert';
import { SettingsSectionCard } from './SettingsSectionCard';

interface KronosStatusPanelProps {
  disabled?: boolean;
}

function formatBytes(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value) || value < 0) {
    return null;
  }
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export const KronosStatusPanel: React.FC<KronosStatusPanelProps> = ({
  disabled = false,
}) => {
  const { t } = useUiLanguage();
  const [status, setStatus] = useState<KronosStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const requestIdRef = useRef(0);

  const refresh = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);
    try {
      const next = await systemConfigApi.getKronosStatus();
      if (requestIdRef.current !== requestId) {
        return;
      }
      setStatus(next);
    } catch (err: unknown) {
      if (requestIdRef.current !== requestId) {
        return;
      }
      setStatus(null);
      setError(getParsedApiError(err));
    } finally {
      if (requestIdRef.current === requestId) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const sizeLabel = formatBytes(status?.weightsTotalBytes ?? null);

  return (
    <SettingsSectionCard
      title={t('settings.kronosStatusTitle')}
      description={t('settings.kronosStatusDescription')}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="secondary"
          size="default"
          disabled={disabled || isLoading}
          onClick={() => {
            void refresh();
          }}
        >
          <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} aria-hidden="true" />
          {isLoading ? t('settings.kronosStatusRefreshing') : t('settings.kronosStatusRefresh')}
        </Button>
      </div>

      {error ? <ApiErrorAlert error={error} className="mb-3" /> : null}

      {status ? (
        <div className="space-y-3">
          <Surface level="interactive" className="px-4 py-3">
            <div className="flex flex-wrap items-start gap-2">
              {status.ready ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 text-success" aria-hidden="true" />
              ) : (
                <CircleAlert className="mt-0.5 h-4 w-4 text-warning" aria-hidden="true" />
              )}
              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={status.ready ? 'success' : 'warning'} size="sm">
                    {status.ready ? t('settings.kronosReady') : t('settings.kronosNeedsAction')}
                  </Badge>
                  <Badge variant={status.enabled ? 'success' : 'default'} size="sm">
                    {status.enabled
                      ? t('settings.kronosEnabledLabel')
                      : t('settings.kronosDisabledLabel')}
                  </Badge>
                  <Badge variant="default" size="sm">
                    {t('settings.kronosModelSizeLabel')}: {status.modelSize}
                  </Badge>
                  <Badge variant={status.dependenciesInstalled ? 'success' : 'warning'} size="sm">
                    {t('settings.kronosDepsLabel')}:{' '}
                    {status.dependenciesInstalled
                      ? t('settings.kronosDepsInstalled')
                      : t('settings.kronosDepsMissing')}
                  </Badge>
                  <Badge variant={status.weightsPresent ? 'success' : 'warning'} size="sm">
                    {t('settings.kronosWeightsLabel')}:{' '}
                    {status.weightsPresent
                      ? t('settings.kronosWeightsPresent')
                      : t('settings.kronosWeightsMissing')}
                  </Badge>
                </div>
                <p className="text-xs leading-5 text-muted-text">{status.message}</p>
                {status.dependencies.length > 0 ? (
                  <p className="text-xs leading-5 text-muted-text">
                    {status.dependencies
                      .map((item) => `${item.name}${item.available ? '✓' : '✗'}`)
                      .join(' · ')}
                  </p>
                ) : null}
                {sizeLabel || status.weightsModifiedAt ? (
                  <p className="text-xs leading-5 text-muted-text">
                    {sizeLabel
                      ? t('settings.kronosWeightsSize', { size: sizeLabel })
                      : null}
                    {sizeLabel && status.weightsModifiedAt ? ' · ' : null}
                    {status.weightsModifiedAt
                      ? t('settings.kronosWeightsMtime', { time: status.weightsModifiedAt })
                      : null}
                  </p>
                ) : null}
                {status.downloadSizeHint ? (
                  <p className="text-xs leading-5 text-muted-text">{status.downloadSizeHint}</p>
                ) : null}
              </div>
            </div>
          </Surface>

          <SettingsAlert
            variant={status.ready ? 'success' : 'warning'}
            title={t('settings.kronosNextStep')}
            message={status.nextStep}
          />

          {status.packagedDesktop || !status.installSupported ? (
            <SettingsAlert
              variant="warning"
              title={t('settings.kronosNeedsAction')}
              message={t('settings.kronosDesktopUnsupported')}
            />
          ) : null}

          <p className="text-xs leading-5 text-muted-text">{t('settings.kronosDocHint')}</p>
        </div>
      ) : null}
    </SettingsSectionCard>
  );
};
