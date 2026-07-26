// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useMemo, useState } from 'react';
import type React from 'react';
import { RefreshCw } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { securityAuditApi } from '../../api/securityAudit';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import type {
  SecurityAuditEvent,
  SecurityAuditListQuery,
  SecurityAuditOutcome,
} from '../../types/securityAudit';
import { SECURITY_AUDIT_MAX_PAGE_SIZE } from '../../types/securityAudit';
import { getUiLocale } from '../../utils/uiLocale';
import {
  ApiErrorAlert,
  Badge,
  Button,
  EmptyState,
  IconButton,
  Input,
  JsonViewer,
  Pagination,
  Select,
  StatePanel,
} from '../common';
import { SettingsSectionCard } from './SettingsSectionCard';

type SecurityAuditPanelProps = {
  disabled?: boolean;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

const DEFAULT_PAGE_SIZE = 50;

const OUTCOME_OPTIONS: Array<SecurityAuditOutcome | ''> = [
  '',
  'pending',
  'success',
  'denied',
  'failure',
  'accepted',
  'rejected',
];

function formatTimestamp(value: string | null | undefined, language: UiLanguage): string {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(getUiLocale(language), {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  }).format(date);
}

function outcomeVariant(outcome: SecurityAuditOutcome) {
  if (outcome === 'success' || outcome === 'accepted') return 'success' as const;
  if (outcome === 'denied' || outcome === 'failure' || outcome === 'rejected') return 'danger' as const;
  if (outcome === 'pending') return 'warning' as const;
  return 'default' as const;
}

function isAuthRequiredError(error: ParsedApiError | null): boolean {
  // Match the stable API code only — do not treat generic 403/forbidden as this
  // auth-disabled contract (other 403s should keep the generic error panel).
  return Boolean(error && error.code === 'security_audit_auth_required');
}

function buildQuery(
  page: number,
  pageSize: number,
  eventType: string,
  outcome: SecurityAuditOutcome | '',
  correlationId: string,
): SecurityAuditListQuery {
  const trimmedEventType = eventType.trim();
  const trimmedCorrelation = correlationId.trim();
  return {
    page,
    pageSize,
    ...(trimmedEventType ? { eventType: trimmedEventType } : {}),
    ...(outcome ? { outcome } : {}),
    ...(trimmedCorrelation ? { correlationId: trimmedCorrelation } : {}),
  };
}

const SecurityAuditPanel: React.FC<SecurityAuditPanelProps> = ({
  disabled = false,
  t,
  language,
}) => {
  const [items, setItems] = useState<SecurityAuditEvent[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);
  const [eventTypeDraft, setEventTypeDraft] = useState('');
  const [outcomeDraft, setOutcomeDraft] = useState<SecurityAuditOutcome | ''>('');
  const [correlationDraft, setCorrelationDraft] = useState('');
  const [appliedEventType, setAppliedEventType] = useState('');
  const [appliedOutcome, setAppliedOutcome] = useState<SecurityAuditOutcome | ''>('');
  const [appliedCorrelation, setAppliedCorrelation] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(total / Math.max(pageSize, 1))),
    [pageSize, total],
  );

  const loadEvents = useCallback(async (
    mode: 'initial' | 'refresh' = 'initial',
    overrides?: {
      page?: number;
      pageSize?: number;
      eventType?: string;
      outcome?: SecurityAuditOutcome | '';
      correlationId?: string;
    },
  ) => {
    const nextPage = overrides?.page ?? page;
    const nextPageSize = overrides?.pageSize ?? pageSize;
    const nextEventType = overrides?.eventType ?? appliedEventType;
    const nextOutcome = overrides?.outcome ?? appliedOutcome;
    const nextCorrelation = overrides?.correlationId ?? appliedCorrelation;

    setLoadError(null);
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }
    try {
      const response = await securityAuditApi.list(
        buildQuery(nextPage, nextPageSize, nextEventType, nextOutcome, nextCorrelation),
      );
      setItems(response.items);
      setPage(response.page);
      setPageSize(response.pageSize);
      setTotal(response.total);
    } catch (error: unknown) {
      setLoadError(getParsedApiError(error, language));
      setItems([]);
      setTotal(0);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [
    appliedCorrelation,
    appliedEventType,
    appliedOutcome,
    language,
    page,
    pageSize,
  ]);

  useEffect(() => {
    void loadEvents('initial');
    // Initial mount only; subsequent loads are user-driven.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional one-shot mount load
  }, []);

  const applyFilters = () => {
    setAppliedEventType(eventTypeDraft.trim());
    setAppliedOutcome(outcomeDraft);
    setAppliedCorrelation(correlationDraft.trim());
    void loadEvents('refresh', {
      page: 1,
      eventType: eventTypeDraft.trim(),
      outcome: outcomeDraft,
      correlationId: correlationDraft.trim(),
    });
  };

  const handlePageChange = (nextPage: number) => {
    void loadEvents('refresh', { page: nextPage });
  };

  const handlePageSizeChange = (value: string) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 1) {
      return;
    }
    const nextSize = Math.min(SECURITY_AUDIT_MAX_PAGE_SIZE, Math.max(1, Math.trunc(parsed)));
    setPageSize(nextSize);
    void loadEvents('refresh', { page: 1, pageSize: nextSize });
  };

  const outcomeLabel = (value: SecurityAuditOutcome | ''): string => {
    if (value === '') return t('settings.securityAuditOutcomeAll');
    if (value === 'pending') return t('settings.securityAuditOutcomePending');
    if (value === 'success') return t('settings.securityAuditOutcomeSuccess');
    if (value === 'denied') return t('settings.securityAuditOutcomeDenied');
    if (value === 'failure') return t('settings.securityAuditOutcomeFailure');
    if (value === 'accepted') return t('settings.securityAuditOutcomeAccepted');
    return t('settings.securityAuditOutcomeRejected');
  };

  const outcomeSelectOptions = OUTCOME_OPTIONS.map((value) => ({
    value,
    label: outcomeLabel(value),
  }));

  const pageSizeOptions = [
    { value: '25', label: '25' },
    { value: '50', label: '50' },
    { value: String(SECURITY_AUDIT_MAX_PAGE_SIZE), label: String(SECURITY_AUDIT_MAX_PAGE_SIZE) },
  ];

  const authRequired = isAuthRequiredError(loadError);

  return (
    <SettingsSectionCard
      title={t('settings.securityAuditTitle')}
      description={t('settings.securityAuditDescription')}
      contentBordered
      actions={(
        <IconButton
          type="button"
          variant="outline"
          size="compact"
          onClick={() => void loadEvents('refresh')}
          // Keep refresh available after a 403 so operators can retry once auth
          // is enabled without leaving Settings.
          disabled={disabled || isLoading || isRefreshing}
          isLoading={isRefreshing}
          aria-label={t('settings.securityAuditRefresh')}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </IconButton>
      )}
    >
      <p className="mb-3 text-xs leading-5 text-secondary-text">
        {t('settings.securityAuditReadOnlyNote')}
      </p>

      <div
        className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4"
        data-testid="settings-security-audit-filters"
      >
        <Input
          label={t('settings.securityAuditFilterEventType')}
          value={eventTypeDraft}
          onChange={(event) => setEventTypeDraft(event.target.value)}
          placeholder={t('settings.securityAuditFilterEventTypePlaceholder')}
          disabled={disabled || isLoading}
          size="comfortable"
        />
        <Select
          label={t('settings.securityAuditFilterOutcome')}
          value={outcomeDraft}
          onChange={(value) => setOutcomeDraft(value as SecurityAuditOutcome | '')}
          options={outcomeSelectOptions}
          disabled={disabled || isLoading}
          size="comfortable"
        />
        <Input
          label={t('settings.securityAuditFilterCorrelation')}
          value={correlationDraft}
          onChange={(event) => setCorrelationDraft(event.target.value)}
          placeholder={t('settings.securityAuditFilterCorrelationPlaceholder')}
          disabled={disabled || isLoading}
          size="comfortable"
        />
        <Select
          label={t('settings.securityAuditPageSize')}
          value={String(pageSize)}
          onChange={handlePageSizeChange}
          options={pageSizeOptions}
          disabled={disabled || isLoading}
          size="comfortable"
        />
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="comfortable"
          onClick={applyFilters}
          disabled={disabled || isLoading || isRefreshing}
        >
          {t('settings.securityAuditApplyFilters')}
        </Button>
        <p className="text-xs text-muted-text">
          {t('settings.securityAuditTotal', { total })}
        </p>
      </div>

      {authRequired ? (
        <StatePanel
          state="blocked"
          title={t('settings.securityAuditAuthRequiredTitle')}
          description={t('settings.securityAuditAuthRequiredDescription')}
          size="compact"
          titleAs="p"
          data-testid="settings-security-audit-auth-required"
        />
      ) : null}

      {loadError && !authRequired ? (
        <div className="mb-3">
          <ApiErrorAlert error={loadError} />
        </div>
      ) : null}

      {!authRequired && isLoading ? (
        <StatePanel
          state="loading"
          title={t('common.loading')}
          size="compact"
          titleAs="p"
        />
      ) : null}

      {!authRequired && !isLoading && !loadError && items.length === 0 ? (
        <EmptyState
          compact
          title={t('settings.securityAuditEmptyTitle')}
          description={t('settings.securityAuditEmptyDescription')}
        />
      ) : null}

      {!authRequired && !isLoading && items.length > 0 ? (
        <div
          role="region"
          aria-label={t('settings.securityAuditListLabel')}
          data-testid="settings-security-audit-list"
          className="divide-y divide-border/70"
        >
          {items.map((event) => (
            <article
              key={event.id}
              className="space-y-2 py-3"
              data-testid={`settings-security-audit-event-${event.id}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-mono text-sm font-semibold text-foreground">
                      {event.eventType}
                    </p>
                    <Badge variant={outcomeVariant(event.outcome)} size="compact">
                      {event.outcome}
                    </Badge>
                    <Badge variant="history" size="compact">
                      {event.phase}
                    </Badge>
                  </div>
                  <p className="text-xs text-secondary-text">
                    {formatTimestamp(event.occurredAt, language)}
                    {' · '}
                    {event.action}
                    {' · '}
                    {event.reasonCode}
                  </p>
                </div>
                <p className="font-mono text-xxs text-muted-text">
                  #{event.id}
                </p>
              </div>
              <dl className="grid gap-1 text-xs text-secondary-text sm:grid-cols-2">
                <div>
                  <dt className="inline text-muted-text">
                    {t('settings.securityAuditActor')}
                    {': '}
                  </dt>
                  <dd className="inline font-mono">
                    {event.actor.type}/{event.actor.id}
                  </dd>
                </div>
                <div>
                  <dt className="inline text-muted-text">
                    {t('settings.securityAuditTarget')}
                    {': '}
                  </dt>
                  <dd className="inline font-mono">
                    {event.target.type}/{event.target.id}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="inline text-muted-text">
                    {t('settings.securityAuditCorrelation')}
                    {': '}
                  </dt>
                  <dd className="inline break-all font-mono">
                    {event.correlationId}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="inline text-muted-text">
                    {t('settings.securityAuditExecution')}
                    {': '}
                  </dt>
                  <dd className="inline break-all font-mono">
                    {event.executionId}
                  </dd>
                </div>
              </dl>
              {event.metadata && Object.keys(event.metadata).length > 0 ? (
                <details className="rounded-lg border border-border/60 bg-[var(--settings-surface)] p-2">
                  <summary className="cursor-pointer text-xs font-medium text-secondary-text">
                    {t('settings.securityAuditMetadata')}
                  </summary>
                  <div className="mt-2">
                    <JsonViewer data={event.metadata} maxHeight="12rem" />
                  </div>
                </details>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}

      {!authRequired && !isLoading && totalPages > 1 ? (
        <div className="mt-4">
          <Pagination
            currentPage={page}
            totalPages={totalPages}
            onPageChange={handlePageChange}
          />
        </div>
      ) : null}
    </SettingsSectionCard>
  );
};

export default SecurityAuditPanel;
