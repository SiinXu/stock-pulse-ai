// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { stocksApi } from '../../api/stocks';
import { getParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiLanguage } from '../../i18n/uiText';
import { FIELD_TRUST_TEXT } from '../../locales/fieldTrust';
import type {
  FieldTrustAnalysisInput,
  FieldTrustConfidence,
  FieldTrustOrigin,
  FieldTrustProviderHealth,
  FieldTrustProviderStatus,
  FieldTrustStaleness,
  FieldTrustStatus,
  StockFieldTrustResponse,
} from '../../types/stocks';
import { Badge, Button, Card, DataTable, type DataTableColumn, InlineAlert, Loading } from '../common';
import { formatUiNumber } from '../../utils/uiLocale';

export type FieldTrustPanelProps = {
  stockCode: string;
  fetchView?: (stockCode: string) => Promise<StockFieldTrustResponse>;
  initialView?: StockFieldTrustResponse | null;
};

const formatOptionalNumber = (
  value: number | null | undefined,
  language: UiLanguage,
  fallback: string,
): string => {
  if (value === null || value === undefined || !Number.isFinite(value)) return fallback;
  return formatUiNumber(value, language, {
    maximumFractionDigits: 4,
  });
};

const statusVariant = (status: FieldTrustStatus): 'success' | 'warning' | 'danger' => {
  if (status === 'ok') return 'success';
  if (status === 'degraded') return 'warning';
  return 'danger';
};

export const FieldTrustPanel: React.FC<FieldTrustPanelProps> = ({
  stockCode,
  fetchView,
  initialView = null,
}) => {
  const { language } = useUiLanguage();
  const text = FIELD_TRUST_TEXT[language] ?? FIELD_TRUST_TEXT.en;
  const titleId = useId();
  const [view, setView] = useState<StockFieldTrustResponse | null>(initialView);
  const [loading, setLoading] = useState(!initialView && Boolean(stockCode.trim()));
  const [error, setError] = useState<string | null>(null);
  const requestSeqRef = useRef(0);

  const load = useCallback(async () => {
    const code = stockCode.trim();
    if (!code) {
      requestSeqRef.current += 1;
      setView(null);
      setLoading(false);
      setError(null);
      return;
    }
    const requestId = requestSeqRef.current + 1;
    requestSeqRef.current = requestId;
    setLoading(true);
    setError(null);
    try {
      const fetcher = fetchView ?? ((nextCode: string) => stocksApi.getFieldTrust(nextCode));
      const payload = await fetcher(code);
      if (requestSeqRef.current !== requestId) return;
      setView(payload);
    } catch (err) {
      if (requestSeqRef.current !== requestId) return;
      const parsed = getParsedApiError(err);
      setError(parsed.message || text.loadFailed);
      setView(null);
    } finally {
      if (requestSeqRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [fetchView, stockCode, text.loadFailed]);

  useEffect(() => {
    if (initialView) {
      setView(initialView);
      setLoading(false);
      setError(null);
      return;
    }
    void load();
  }, [initialView, load]);

  const statusLabel = (status: FieldTrustStatus): string => {
    if (status === 'ok') return text.statusOk;
    if (status === 'degraded') return text.statusDegraded;
    return text.statusUnavailable;
  };

  const stalenessLabel = (value: FieldTrustStaleness): string => {
    if (value === 'fresh') return text.stalenessFresh;
    if (value === 'stale') return text.stalenessStale;
    return text.stalenessUnknown;
  };

  const originLabel = (value: FieldTrustOrigin): string => {
    if (value === 'primary') return text.originPrimary;
    if (value === 'supplement') return text.originSupplement;
    return text.originUnknown;
  };

  const confidenceLabel = (value: FieldTrustConfidence): string => {
    if (value === 'high') return text.confidenceHigh;
    if (value === 'medium') return text.confidenceMedium;
    return text.confidenceLow;
  };

  const healthLabel = (value: FieldTrustProviderStatus): string => {
    if (value === 'ok') return text.healthOk;
    if (value === 'failed') return text.healthFailed;
    if (value === 'empty') return text.healthEmpty;
    return text.healthUnavailable;
  };

  const fieldColumns: DataTableColumn<StockFieldTrustResponse['fields'][number]>[] = [
    { id: 'field', header: text.field, cell: (row) => row.field },
    {
      id: 'value',
      header: text.value,
      cell: (row) => formatOptionalNumber(row.value, language, text.notAvailable),
    },
    { id: 'source', header: text.source, cell: (row) => row.source || text.notAvailable },
    { id: 'origin', header: text.origin, cell: (row) => originLabel(row.origin) },
    { id: 'staleness', header: text.staleness, cell: (row) => stalenessLabel(row.staleness) },
    {
      id: 'conflict',
      header: text.conflict,
      cell: (row) => (row.conflict ? text.yes : text.no),
    },
  ];

  const healthColumns: DataTableColumn<FieldTrustProviderHealth>[] = [
    { id: 'provider', header: text.source, cell: (row) => row.provider },
    { id: 'status', header: text.status, cell: (row) => healthLabel(row.status) },
    {
      id: 'role',
      header: text.origin,
      cell: (row) => {
        if (row.role === 'primary') return text.rolePrimary;
        if (row.role === 'supplement') return text.roleSupplement;
        return text.roleAttempted;
      },
    },
  ];

  const analysis: FieldTrustAnalysisInput | null | undefined = view?.analysisInput;
  const showDegraded = view?.status === 'degraded';
  const showUnavailable = view?.status === 'unavailable';

  return (
    <Card
      title={text.title}
      description={text.description}
      padding="md"
      data-testid="field-trust-panel"
      aria-labelledby={titleId}
      headerRight={
        <Button type="button" variant="secondary" size="compact" onClick={() => void load()} disabled={loading}>
          {loading ? text.refreshing : text.refresh}
        </Button>
      }
    >
      <h3 id={titleId} className="sr-only">
        {text.title}
      </h3>
      {error ? <InlineAlert variant="danger" message={error} data-testid="field-trust-error" /> : null}
      {loading && !view ? <Loading /> : null}
      {view ? (
        <div className="space-y-4">
          {showUnavailable ? (
            <InlineAlert
              variant="danger"
              title={text.unavailableTitle}
              message={view.message || text.unavailableDescription}
              data-testid="field-trust-unavailable"
            />
          ) : null}
          {showDegraded ? (
            <InlineAlert
              variant="warning"
              title={text.degradedTitle}
              message={view.message || text.degradedDescription}
              data-testid="field-trust-degraded"
            />
          ) : null}
          <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-xs text-secondary-text">{text.status}</dt>
              <dd data-testid="field-trust-status">
                <Badge variant={statusVariant(view.status)} size="sm">
                  {statusLabel(view.status)}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-secondary-text">{text.quoteSource}</dt>
              <dd data-testid="field-trust-quote-source">{view.quoteSource || text.notAvailable}</dd>
            </div>
            <div>
              <dt className="text-xs text-secondary-text">{text.lag}</dt>
              <dd data-testid="field-trust-lag">
                {formatOptionalNumber(view.staleSeconds, language, text.notAvailable)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-secondary-text">{text.stale}</dt>
              <dd data-testid="field-trust-stale">
                {view.isStale == null ? text.notAvailable : view.isStale ? text.yes : text.no}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-secondary-text">{text.confidence}</dt>
              <dd data-testid="field-trust-confidence">
                {analysis ? confidenceLabel(analysis.confidence) : text.notAvailable}
              </dd>
            </div>
          </dl>
          {view.fields.length > 0 ? (
            <div data-testid="field-trust-fields">
              <DataTable
                caption={text.title}
                columns={fieldColumns}
                rows={view.fields}
                getRowKey={(row) => row.field}
                emptyState={{ title: text.emptyTitle, description: text.emptyDescription }}
                density="compact"
                minWidth="content"
              />
            </div>
          ) : (
            !showUnavailable && (
              <p className="text-sm text-secondary-text" data-testid="field-trust-empty">
                {text.emptyDescription}
              </p>
            )
          )}
          {view.conflicts.length > 0 ? (
            <div data-testid="field-trust-conflicts">
              <p className="mb-1 text-xs text-secondary-text">{text.conflictValues}</p>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {view.conflicts.map((conflict) => (
                  <li key={conflict.field}>
                    {conflict.field}
                    {': '}
                    {conflict.values
                      .map((item) => `${item.provider}=${formatOptionalNumber(item.value, language, text.notAvailable)}`)
                      .join('; ') || text.notAvailable}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {analysis && analysis.gaps.length > 0 ? (
            <div data-testid="field-trust-gaps">
              <p className="mb-1 text-xs text-secondary-text">{text.gaps}</p>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {analysis.gaps.map((gap, index) => (
                  <li key={`${gap.code}-${gap.field ?? 'none'}-${index}`}>
                    {gap.field ? `${gap.field}: ` : ''}
                    {gap.detail || gap.code}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {view.providerHealth.length > 0 ? (
            <div data-testid="field-trust-provider-health">
              <p className="mb-1 text-xs text-secondary-text">{text.providerHealth}</p>
              <DataTable
                caption={text.providerHealth}
                columns={healthColumns}
                rows={view.providerHealth}
                getRowKey={(row) => `${row.provider}-${row.role}-${row.status}`}
                emptyState={{ title: text.emptyTitle, description: text.emptyDescription }}
                density="compact"
                minWidth="content"
              />
            </div>
          ) : null}
          <p className="text-xs text-secondary-text" data-testid="field-trust-disclaimer">
            {text.disclaimer}
          </p>
        </div>
      ) : null}
    </Card>
  );
};

export default FieldTrustPanel;
