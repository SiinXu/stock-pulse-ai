// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useRef, useState } from 'react';
import type React from 'react';
import {
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  Database,
  RefreshCw,
} from 'lucide-react';
import { systemConfigApi } from '../../api/systemConfig';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type {
  DataProviderHealthStatus,
  DataProviderRuntimeCacheStatus,
  DataProviderRuntimeMarketChain,
  DataProviderRuntimeProviderStatus,
  DataProviderRuntimeStatusResponse,
} from '../../types/systemConfig';
import { ApiErrorAlert, Badge, Button, Surface } from '../common';
import { SettingsSectionCard } from './SettingsSectionCard';

type Translate = ReturnType<typeof useUiLanguage>['t'];

interface DataProviderRuntimeStatusPanelProps {
  disabled?: boolean;
}

function marketLabel(market: string, t: Translate): string {
  if (market === 'cn') return t('settings.dataRuntimeMarketCn');
  if (market === 'hk') return t('settings.dataRuntimeMarketHk');
  if (market === 'us') return t('settings.dataRuntimeMarketUs');
  return market.toUpperCase();
}

function healthLabel(status: DataProviderHealthStatus | string, t: Translate): string {
  switch (status) {
    case 'healthy':
      return t('settings.dataRuntimeHealthHealthy');
    case 'degraded':
      return t('settings.dataRuntimeHealthDegraded');
    case 'unknown':
      return t('settings.dataRuntimeHealthUnknown');
    case 'unavailable':
      return t('settings.dataRuntimeHealthUnavailable');
    case 'not_configured':
      return t('settings.dataRuntimeHealthNotConfigured');
    case 'circuit_open':
      return t('settings.dataRuntimeHealthCircuitOpen');
    case 'failed':
      return t('settings.dataRuntimeHealthFailed');
    default:
      return String(status);
  }
}

function healthVariant(
  status: DataProviderHealthStatus | string,
): 'success' | 'warning' | 'danger' | 'default' | 'history' {
  switch (status) {
    case 'healthy':
      return 'success';
    case 'degraded':
    case 'circuit_open':
    case 'not_configured':
      return 'warning';
    case 'failed':
    case 'unavailable':
      return 'danger';
    case 'unknown':
      return 'history';
    default:
      return 'default';
  }
}

function qualityLabel(quality: string, t: Translate): string {
  switch (quality) {
    case 'ok':
      return t('settings.dataRuntimeQualityOk');
    case 'degraded':
      return t('settings.dataRuntimeQualityDegraded');
    case 'unavailable':
      return t('settings.dataRuntimeQualityUnavailable');
    case 'unknown':
      return t('settings.dataRuntimeQualityUnknown');
    case 'active':
      return t('settings.dataRuntimeCacheActive');
    case 'idle':
      return t('settings.dataRuntimeCacheIdle');
    case 'cold':
      return t('settings.dataRuntimeCacheCold');
    case 'stale':
      return t('settings.dataRuntimeCacheStale');
    case 'local_only':
      return t('settings.dataRuntimeCacheLocalOnly');
    default:
      return quality;
  }
}

function roleLabel(role: string, t: Translate): string {
  if (role === 'baseline') return t('settings.dataRuntimeRoleBaseline');
  if (role === 'enhancer') return t('settings.dataRuntimeRoleEnhancer');
  if (role === 'specialist') return t('settings.dataRuntimeRoleSpecialist');
  return role;
}

function HealthIcon({ status }: { status: string }) {
  if (status === 'healthy') {
    return <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />;
  }
  if (status === 'failed' || status === 'unavailable' || status === 'circuit_open') {
    return <CircleAlert className="h-4 w-4 text-warning" aria-hidden="true" />;
  }
  return <CircleDashed className="h-4 w-4 text-muted-text" aria-hidden="true" />;
}

const MarketChainRow: React.FC<{ chain: DataProviderRuntimeMarketChain; t: Translate }> = ({
  chain,
  t,
}) => {
  const primary = chain.primaryProviderId || t('settings.dataRuntimeNoPrimary');
  const fallbacks = (chain.fallbackProviderIds ?? []).join(' → ') || t('settings.dataRuntimeNoFallback');
  return (
    <Surface level="interactive" className="px-4 py-3" data-testid={`data-runtime-market-${chain.market}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-foreground">{marketLabel(chain.market, t)}</span>
        <Badge variant={healthVariant(chain.quality)} size="sm">
          {qualityLabel(chain.quality, t)}
        </Badge>
        <Badge variant="default" size="sm">
          {t('settings.dataRuntimePrimary')}: {primary}
        </Badge>
      </div>
      <p className="mt-2 text-xs leading-5 text-muted-text">
        {t('settings.dataRuntimeFallback')}: {fallbacks}
      </p>
      {(chain.orderedProviderIds ?? []).length > 0 ? (
        <p className="mt-1 text-xs leading-5 text-secondary-text">
          {t('settings.dataRuntimeChain')}: {(chain.orderedProviderIds ?? []).join(' → ')}
        </p>
      ) : null}
    </Surface>
  );
};

const ProviderStatusRow: React.FC<{
  provider: DataProviderRuntimeProviderStatus;
  t: Translate;
}> = ({ provider, t }) => {
  const configuredLabel =
    provider.configured === true
      ? t('settings.providerConfigured')
      : provider.configured === false
        ? t('settings.providerUnconfigured')
        : t('settings.dataRuntimeConfiguredNa');

  return (
    <Surface
      level="interactive"
      className="px-4 py-3"
      data-testid={`data-runtime-provider-${provider.providerId}`}
    >
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <HealthIcon status={provider.healthStatus} />
          <Database className="h-3.5 w-3.5 text-muted-text" aria-hidden="true" />
          <span className="text-sm font-semibold text-foreground">{provider.displayName}</span>
          <Badge variant="default" size="sm">
            {roleLabel(provider.role, t)}
          </Badge>
          <Badge variant={healthVariant(provider.healthStatus)} size="sm">
            {healthLabel(provider.healthStatus, t)}
          </Badge>
          {provider.role !== 'baseline' ? (
            <Badge variant={provider.configured ? 'success' : 'warning'} size="sm">
              {configuredLabel}
            </Badge>
          ) : null}
          <Badge variant={provider.available ? 'success' : 'warning'} size="sm">
            {provider.available
              ? t('settings.dataRuntimeAvailable')
              : t('settings.dataRuntimeUnavailable')}
          </Badge>
        </div>
        {(provider.isPrimaryFor ?? []).length > 0 ? (
          <p className="text-xs leading-5 text-secondary-text">
            {t('settings.dataRuntimePrimaryFor')}: {(provider.isPrimaryFor ?? []).join(', ')}
          </p>
        ) : null}
        {provider.failureReason ? (
          <p className="text-xs leading-5 text-warning" data-testid={`data-runtime-failure-${provider.providerId}`}>
            {provider.failureReason}
          </p>
        ) : null}
      </div>
    </Surface>
  );
};

const CacheStatusBlock: React.FC<{
  cache: DataProviderRuntimeCacheStatus | null | undefined;
  t: Translate;
}> = ({ cache, t }) => {
  if (!cache) {
    return (
      <p className="text-xs leading-5 text-secondary-text" data-testid="data-runtime-cache-empty">
        {t('settings.dataRuntimeCacheUnavailable')}
      </p>
    );
  }
  return (
    <Surface level="interactive" className="px-4 py-3" data-testid="data-runtime-cache">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-foreground">{t('settings.dataRuntimeCacheTitle')}</span>
        <Badge
          variant={cache.quality === 'stale' || cache.quality === 'unknown' ? 'warning' : 'default'}
          size="sm"
        >
          {qualityLabel(cache.quality, t)}
        </Badge>
        {cache.fetchMode ? (
          <Badge variant="default" size="sm">
            {cache.fetchMode}
          </Badge>
        ) : null}
      </div>
      <p className="mt-2 text-xs leading-5 text-muted-text">
        {t('settings.dataRuntimeCacheCounters', {
          hits: cache.hits ?? '—',
          misses: cache.misses ?? '—',
          stale: cache.staleHits ?? '—',
          writes: cache.writes ?? '—',
        })}
      </p>
      {cache.note ? (
        <p className="mt-1 text-xs leading-5 text-secondary-text">{cache.note}</p>
      ) : null}
    </Surface>
  );
};

/** Read-only live projection for Settings → Data sources (Hub overview). */
export const DataProviderRuntimeStatusPanel: React.FC<DataProviderRuntimeStatusPanelProps> = ({
  disabled = false,
}) => {
  const { t } = useUiLanguage();
  const [status, setStatus] = useState<DataProviderRuntimeStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const requestIdRef = useRef(0);

  const refresh = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);
    try {
      const next = await systemConfigApi.getDataProviderRuntimeStatus();
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

  const baselineProviders = (status?.providers ?? []).filter((item) => item.role === 'baseline');
  const enhancerProviders = (status?.providers ?? []).filter(
    (item) => item.role === 'enhancer' || item.role === 'specialist',
  );

  return (
    <SettingsSectionCard
      title={t('settings.dataRuntimeTitle')}
      description={t('settings.dataRuntimeDescription')}
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
          data-testid="data-runtime-refresh"
        >
          <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} aria-hidden="true" />
          {isLoading ? t('settings.dataRuntimeRefreshing') : t('settings.dataRuntimeRefresh')}
        </Button>
        {status?.asOf ? (
          <span className="text-xs text-muted-text" data-testid="data-runtime-as-of">
            {t('settings.dataRuntimeAsOf')}: {status.asOf}
          </span>
        ) : null}
      </div>

      {error ? <ApiErrorAlert error={error} className="mb-3" /> : null}

      {isLoading && !status ? (
        <p className="px-1 text-sm text-secondary-text" role="status" data-testid="data-runtime-loading">
          {t('settings.dataRuntimeLoading')}
        </p>
      ) : null}

      {!isLoading && !error && !status ? (
        <p className="px-1 text-sm text-secondary-text" role="status" data-testid="data-runtime-empty">
          {t('settings.dataRuntimeEmpty')}
        </p>
      ) : null}

      {status ? (
        <div className="space-y-4" data-testid="data-runtime-status">
          {status.partial || status.sourceState !== 'ok' ? (
            <Surface level="interactive" className="border border-warning/40 px-4 py-3" data-testid="data-runtime-partial">
              <div className="flex flex-wrap items-center gap-2">
                <CircleAlert className="h-4 w-4 text-warning" aria-hidden="true" />
                <Badge variant="warning" size="sm">
                  {status.sourceState}
                </Badge>
                {status.errorCode ? (
                  <Badge variant="default" size="sm">
                    {status.errorCode}
                  </Badge>
                ) : null}
              </div>
              {status.errorMessage ? (
                <p className="mt-2 text-xs leading-5 text-warning">{status.errorMessage}</p>
              ) : (
                <p className="mt-2 text-xs leading-5 text-secondary-text">
                  {t('settings.dataRuntimePartialNote')}
                </p>
              )}
            </Surface>
          ) : null}

          <div className="space-y-2">
            <h4 className="px-1 text-sm font-medium text-foreground">
              {t('settings.dataRuntimeMarketsTitle')}
            </h4>
            {(status.markets ?? []).length === 0 ? (
              <p className="px-1 text-xs text-secondary-text" data-testid="data-runtime-markets-empty">
                {t('settings.dataRuntimeMarketsEmpty')}
              </p>
            ) : (
              <div className="space-y-2">
                {(status.markets ?? []).map((chain) => (
                  <MarketChainRow key={`${chain.dataType}:${chain.market}`} chain={chain} t={t} />
                ))}
              </div>
            )}
          </div>

          <CacheStatusBlock cache={status.cache} t={t} />

          <div className="space-y-2">
            <h4 className="px-1 text-sm font-medium text-foreground">
              {t('settings.dataRuntimeBaselineTitle')}
            </h4>
            {baselineProviders.length === 0 ? (
              <p className="px-1 text-xs text-secondary-text" data-testid="data-runtime-baseline-empty">
                {t('settings.dataRuntimeProvidersEmpty')}
              </p>
            ) : (
              <div className="space-y-2">
                {baselineProviders.map((provider) => (
                  <ProviderStatusRow key={provider.providerId} provider={provider} t={t} />
                ))}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <h4 className="px-1 text-sm font-medium text-foreground">
              {t('settings.dataRuntimeEnhancersTitle')}
            </h4>
            <p className="px-1 text-xs leading-5 text-secondary-text">
              {t('settings.dataRuntimeEnhancersDescription')}
            </p>
            {enhancerProviders.length === 0 ? (
              <p className="px-1 text-xs text-secondary-text" data-testid="data-runtime-enhancers-empty">
                {t('settings.dataRuntimeProvidersEmpty')}
              </p>
            ) : (
              <div className="space-y-2">
                {enhancerProviders.map((provider) => (
                  <ProviderStatusRow key={provider.providerId} provider={provider} t={t} />
                ))}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </SettingsSectionCard>
  );
};
