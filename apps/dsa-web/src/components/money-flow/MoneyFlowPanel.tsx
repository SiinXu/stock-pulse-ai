// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import {
  getStockMoneyFlow,
  type MoneyFlowView,
} from '../../api/moneyFlow';
import { getParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiLanguage } from '../../i18n/uiText';
import { MONEY_FLOW_TEXT } from '../../locales/moneyFlow';
import { Button, Card, InlineAlert, Loading } from '../common';
import { formatUiNumber } from '../../utils/uiLocale';

export type MoneyFlowPanelProps = {
  stockCode: string;
  days?: number;
  fetchView?: (stockCode: string, days: number) => Promise<MoneyFlowView>;
  initialView?: MoneyFlowView | null;
};

const asFiniteNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

const formatRatio = (
  value: unknown,
  language: UiLanguage,
  fallback: string,
): string => {
  const numeric = asFiniteNumber(value);
  if (numeric === undefined) return fallback;
  const body = formatUiNumber(Math.abs(numeric), language, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (numeric > 0) return `+${body}%`;
  if (numeric < 0) return `-${body}%`;
  return `${body}%`;
};

const formatAmount = (
  value: unknown,
  language: UiLanguage,
  fallback: string,
): string => {
  const numeric = asFiniteNumber(value);
  if (numeric === undefined) return fallback;
  const body = formatUiNumber(Math.abs(numeric), language, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  if (numeric > 0) return `+${body}`;
  if (numeric < 0) return `-${body}`;
  return body;
};

const attitudeLabel = (
  attitude: string | undefined,
  text: (typeof MONEY_FLOW_TEXT)['en'],
): string => {
  switch ((attitude || '').toLowerCase()) {
    case 'inflow':
      return text.attitudeInflow;
    case 'outflow':
      return text.attitudeOutflow;
    case 'neutral':
      return text.attitudeNeutral;
    default:
      return text.attitudeUnknown;
  }
};

const isUnavailableStatus = (status: string): boolean =>
  ['not_supported', 'fetch_failed', 'empty'].includes(status);

const isDegradedStatus = (status: string): boolean =>
  ['partial', 'stale', 'fallback'].includes(status);

export const MoneyFlowPanel: React.FC<MoneyFlowPanelProps> = ({
  stockCode,
  days = 5,
  fetchView,
  initialView = null
}) => {
  const { language } = useUiLanguage();
  const text = MONEY_FLOW_TEXT[language] ?? MONEY_FLOW_TEXT.en;
  const titleId = useId();
  const [view, setView] = useState<MoneyFlowView | null>(initialView);
  const [loading, setLoading] = useState(!initialView && Boolean(stockCode.trim()));
  const [error, setError] = useState<string | null>(null);
  /** Monotonic request id so slower/stale fetches never overwrite newer UI state. */
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
      const fetcher = fetchView ?? ((c, d) => getStockMoneyFlow({ stockCode: c, days: d }));
      const payload = await fetcher(code, days);
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
  }, [days, fetchView, stockCode, text.loadFailed]);

  useEffect(() => {
    if (initialView) {
      requestSeqRef.current += 1;
      setView(initialView);
      setLoading(false);
      setError(null);
      return;
    }
    void load();
  }, [initialView, load, stockCode]);

  const snapshot = view?.snapshot ?? null;
  const status = view?.status ?? '';
  const fallback = text.notAvailable;

  return (
    <Card
      data-testid="money-flow-panel"
      aria-labelledby={titleId}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h3 id={titleId} className="text-base font-semibold text-content">
            {text.title}
          </h3>
          <p className="text-sm text-content-muted">{text.description}</p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="compact"
          onClick={() => void load()}
          disabled={!stockCode.trim()}
          data-testid="money-flow-refresh"
        >
          {loading ? text.refreshing : text.refresh}
        </Button>
      </div>

      {loading && !view ? (
        <div className="mt-4" data-testid="money-flow-loading">
          <Loading />
        </div>
      ) : null}

      {error ? (
        <div className="mt-4" data-testid="money-flow-error">
          <InlineAlert variant="danger" message={error} />
        </div>
      ) : null}

      {!loading && !error && view?.status === 'disabled' ? (
        <div className="mt-4 space-y-2" data-testid="money-flow-disabled">
          <InlineAlert
            variant="info"
            message={`${text.disabledTitle}: ${view.message || text.disabledDescription}`}
          />
        </div>
      ) : null}

      {!loading && !error && view && isUnavailableStatus(status) ? (
        <div className="mt-4 space-y-2" data-testid="money-flow-unavailable">
          <InlineAlert
            variant="warning"
            message={`${text.unavailableTitle}: ${view.message || text.unavailableDescription}`}
          />
        </div>
      ) : null}

      {!loading && !error && view && isDegradedStatus(status) ? (
        <div className="mt-4" data-testid="money-flow-degraded">
          <InlineAlert
            variant="warning"
            message={`${text.degradedTitle}: ${view.message || status}`}
          />
        </div>
      ) : null}

      {!loading && !error && view && view.enabled && !snapshot && !isUnavailableStatus(status) ? (
        <div className="mt-4" data-testid="money-flow-empty">
          <InlineAlert
            variant="info"
            message={`${text.emptyTitle}: ${view.message || text.emptyDescription}`}
          />
        </div>
      ) : null}

      {view ? (
        <dl
          className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
          data-testid="money-flow-meta"
        >
          <div>
            <dt className="text-xs text-content-muted">{text.status}</dt>
            <dd className="text-sm font-medium text-content" data-testid="money-flow-status">
              {view.status}
              {view.errorCode ? ` (${view.errorCode})` : ''}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-content-muted">{text.source}</dt>
            <dd className="text-sm font-medium text-content break-all" data-testid="money-flow-source">
              {view.source || fallback}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-content-muted">{text.asOf}</dt>
            <dd className="text-sm font-medium text-content" data-testid="money-flow-as-of">
              {view.asOf || view.fetchedAt || fallback}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-content-muted">{text.providerDate}</dt>
            <dd className="text-sm font-medium text-content" data-testid="money-flow-provider-date">
              {view.providerDate || fallback}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-content-muted">{text.ageDays}</dt>
            <dd className="text-sm font-medium text-content">
              {view.ageDays === null || view.ageDays === undefined
                ? fallback
                : String(view.ageDays)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-content-muted">{text.requestedDays}</dt>
            <dd className="text-sm font-medium text-content">{view.requestedDays}</dd>
          </div>
        </dl>
      ) : null}

      {snapshot ? (
        <div className="mt-4 space-y-3" data-testid="money-flow-snapshot">
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt className="text-xs text-content-muted">{text.attitude}</dt>
              <dd className="text-sm font-medium text-content" data-testid="money-flow-attitude">
                {attitudeLabel(snapshot.attitude, text)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">{text.mainRatio}</dt>
              <dd className="text-sm font-medium text-content" data-testid="money-flow-main-ratio">
                {formatRatio(snapshot.mainNetInflowRatio, language, fallback)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">{text.superLargeRatio}</dt>
              <dd className="text-sm font-medium text-content">
                {formatRatio(snapshot.superLargeNetInflowRatio, language, fallback)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">{text.largeRatio}</dt>
              <dd className="text-sm font-medium text-content">
                {formatRatio(snapshot.largeNetInflowRatio, language, fallback)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">{text.mediumRatio}</dt>
              <dd className="text-sm font-medium text-content">
                {formatRatio(snapshot.mediumNetInflowRatio, language, fallback)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">{text.smallRatio}</dt>
              <dd className="text-sm font-medium text-content">
                {formatRatio(snapshot.smallNetInflowRatio, language, fallback)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">{text.main5d}</dt>
              <dd className="text-sm font-medium text-content">
                {formatAmount(snapshot.mainNetInflow5d, language, fallback)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">{text.main10d}</dt>
              <dd className="text-sm font-medium text-content">
                {formatAmount(snapshot.mainNetInflow10d, language, fallback)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">{text.completeness}</dt>
              <dd className="text-sm font-medium text-content">
                {snapshot.completeness || fallback}
                {snapshot.observedDays != null
                  ? ` (${snapshot.observedDays}/${snapshot.requestedDays ?? view?.requestedDays ?? '?'})`
                  : ''}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">{text.unit}</dt>
              <dd className="text-sm font-medium text-content">{snapshot.unit || fallback}</dd>
            </div>
            <div>
              <dt className="text-xs text-content-muted">{text.amountScale}</dt>
              <dd className="text-sm font-medium text-content">
                {snapshot.amountScale || fallback}
              </dd>
            </div>
          </dl>
          {snapshot.bucketDefinition ? (
            <p className="text-xs text-content-muted break-all" data-testid="money-flow-bucket">
              <span className="font-medium text-content">{text.bucketDefinition}: </span>
              {snapshot.bucketDefinition}
            </p>
          ) : null}
          {snapshot.calibrationNote ? (
            <p className="text-xs text-content-muted" data-testid="money-flow-calibration">
              <span className="font-medium text-content">{text.calibration}: </span>
              {snapshot.calibrationNote}
            </p>
          ) : null}
        </div>
      ) : null}

      {view?.warnings && view.warnings.length > 0 ? (
        <div className="mt-4" data-testid="money-flow-warnings">
          <p className="mb-1 text-xs font-medium text-content">{text.warnings}</p>
          <ul className="list-disc space-y-1 pl-5 text-xs text-content-muted">
            {view.warnings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {view?.disclaimer ? (
        <p className="mt-4 text-xs text-content-muted" data-testid="money-flow-disclaimer">
          {view.disclaimer || text.disclaimer}
        </p>
      ) : (
        <p className="mt-4 text-xs text-content-muted" data-testid="money-flow-disclaimer">
          {text.disclaimer}
        </p>
      )}
    </Card>
  );
};

export default MoneyFlowPanel;
