// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { decisionSignalsApi } from '../../api/decisionSignals';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText, type UiTextKey } from '../../i18n/uiText';
import { DECISION_SIGNAL_WORKSTREAM_TEXT } from '../../locales/decisionSignals';
import type {
  DecisionSignalHorizon,
  DecisionSignalOutcomeEvalStatus,
  DecisionSignalOutcomeItem,
  DecisionSignalOutcomeListParams,
  DecisionSignalOutcomeValue,
} from '../../types/decisionSignals';
import { buildDecisionActionLabelMap } from '../../utils/decisionAction';
import { getDecisionSignalHorizonLabel } from '../../utils/decisionSignalLabels';
import { formatUiDateTime, getUiLocale } from '../../utils/uiLocale';
import {
  ApiErrorAlert,
  Badge,
  Button,
  Card,
  DataTable,
  type DataTableColumn,
  InlineAlert,
  Input,
  Pagination,
  ResponsiveFilterPanel,
  Select,
} from '../common';
import { DecisionSignalOutcomeBadge } from './DecisionSignalDisplay';

const PAGE_SIZE = 20;
const HORIZONS: DecisionSignalHorizon[] = [
  'intraday',
  '1d',
  '3d',
  '5d',
  '10d',
  'swing',
  'long',
];
const OUTCOME_VALUES: DecisionSignalOutcomeValue[] = ['hit', 'miss', 'neutral'];
const EVAL_STATUSES: DecisionSignalOutcomeEvalStatus[] = ['completed', 'unable'];

type OutcomeFilters = {
  horizon: '' | DecisionSignalHorizon;
  outcome: '' | DecisionSignalOutcomeValue;
  evalStatus: '' | DecisionSignalOutcomeEvalStatus;
  engineVersion: string;
  signalId: string;
};

const EMPTY_FILTERS: OutcomeFilters = {
  horizon: '',
  outcome: '',
  evalStatus: '',
  engineVersion: '',
  signalId: '',
};

function parseSignalId(value: string): number | undefined {
  const normalized = value.trim();
  if (!normalized) return undefined;
  const parsed = Number(normalized);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function toOutcomeParams(filters: OutcomeFilters, page: number): DecisionSignalOutcomeListParams {
  return {
    signalId: parseSignalId(filters.signalId),
    horizon: filters.horizon || undefined,
    engineVersion: filters.engineVersion.trim() || undefined,
    evalStatus: filters.evalStatus || undefined,
    outcome: filters.outcome || undefined,
    page,
    pageSize: PAGE_SIZE,
  };
}

function formatReturn(value: number | null | undefined, locale: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value)}%`;
}

export interface DecisionSignalOutcomeExplorerProps {
  onOpenSignal: (signalId: number) => Promise<void> | void;
  refreshKey?: number;
}

export const DecisionSignalOutcomeExplorer: React.FC<DecisionSignalOutcomeExplorerProps> = ({
  onOpenSignal,
  refreshKey = 0,
}) => {
  const { language, t } = useUiLanguage();
  const text = DECISION_SIGNAL_WORKSTREAM_TEXT[language];
  const [filters, setFilters] = useState<OutcomeFilters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<OutcomeFilters>(EMPTY_FILTERS);
  const [items, setItems] = useState<DecisionSignalOutcomeItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [filterError, setFilterError] = useState<string | null>(null);
  const [openingSignalId, setOpeningSignalId] = useState<number | null>(null);
  const [openError, setOpenError] = useState<ParsedApiError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const requestIdRef = useRef(0);
  const locale = getUiLocale(language);
  const actionLabels = useMemo(() => buildDecisionActionLabelMap(t), [t]);

  const loadOutcomes = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setError(null);
    try {
      const response = await decisionSignalsApi.listOutcomes(
        toOutcomeParams(appliedFilters, page),
      );
      if (requestIdRef.current !== requestId) return;
      setItems(response.items);
      setTotal(response.total);
      if (response.page !== page) setPage(response.page);
    } catch (requestError) {
      if (requestIdRef.current !== requestId) return;
      setItems([]);
      setTotal(0);
      setError(getParsedApiError(requestError));
    } finally {
      if (requestIdRef.current === requestId) setLoading(false);
    }
  }, [appliedFilters, page]);

  useEffect(() => {
    void loadOutcomes();
    return () => {
      requestIdRef.current += 1;
    };
  }, [loadOutcomes, refreshKey, reloadToken]);

  const applyFilters = () => {
    if (filters.signalId.trim() && parseSignalId(filters.signalId) === undefined) {
      setFilterError(text.outcomeExplorerInvalidSignalId);
      return;
    }
    setFilterError(null);
    setAppliedFilters(filters);
    setPage(1);
    setReloadToken((current) => current + 1);
  };

  const resetFilters = () => {
    setFilterError(null);
    setFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    setPage(1);
    setReloadToken((current) => current + 1);
  };

  const handleOpenSignal = useCallback(async (signalId: number) => {
    if (openingSignalId !== null) return;
    setOpeningSignalId(signalId);
    setOpenError(null);
    try {
      await onOpenSignal(signalId);
    } catch (requestError) {
      setOpenError(getParsedApiError(requestError));
    } finally {
      setOpeningSignalId(null);
    }
  }, [onOpenSignal, openingSignalId]);

  const columns = useMemo<DataTableColumn<DecisionSignalOutcomeItem>[]>(() => [
    {
      id: 'signal',
      header: text.outcomeExplorerSignalId,
      cell: (item) => (
        <div>
          <span className="font-mono text-foreground">#{item.signalId}</span>
          {item.action ? (
            <div className="mt-1 text-xs text-secondary-text">{actionLabels[item.action]}</div>
          ) : null}
        </div>
      ),
    },
    {
      id: 'horizon',
      header: t('decisionSignals.horizon'),
      cell: (item) => getDecisionSignalHorizonLabel(item.horizon, t),
    },
    {
      id: 'outcome',
      header: t('decisionSignals.outcomes'),
      cell: (item) => <DecisionSignalOutcomeBadge item={item} />,
    },
    {
      id: 'evalStatus',
      header: t('decisionSignals.status'),
      cell: (item) => (
        <Badge variant={item.evalStatus === 'completed' ? 'success' : 'warning'}>
          {t(`decisionSignals.outcomeEvalStatus.${item.evalStatus}` as UiTextKey)}
        </Badge>
      ),
    },
    {
      id: 'return',
      header: t('decisionSignals.returnPct'),
      cell: (item) => formatReturn(item.stockReturnPct, locale),
    },
    {
      id: 'engine',
      header: text.outcomeExplorerEngineVersion,
      cell: (item) => <span className="font-mono text-xs">{item.engineVersion}</span>,
    },
    {
      id: 'updated',
      header: text.outcomeExplorerUpdatedAt,
      cell: (item) => formatUiDateTime(
        item.updatedAt ?? item.createdAt,
        language,
        { dateStyle: 'medium', timeStyle: 'short' },
      ),
    },
    {
      id: 'actions',
      header: t('common.details'),
      align: 'end',
      cell: (item) => (
        <Button
          type="button"
          size="compact"
          variant="outline"
          isLoading={openingSignalId === item.signalId}
          loadingText={t('common.loading')}
          disabled={openingSignalId !== null && openingSignalId !== item.signalId}
          aria-label={formatUiText(text.outcomeExplorerOpenSignal, { id: item.signalId })}
          onClick={() => void handleOpenSignal(item.signalId)}
        >
          {t('common.details')}
        </Button>
      ),
    },
  ], [actionLabels, handleOpenSignal, language, locale, openingSignalId, t, text]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const activeFilterCount = [
    filters.horizon,
    filters.outcome,
    filters.evalStatus,
    filters.engineVersion.trim(),
    filters.signalId.trim(),
  ].filter(Boolean).length;

  return (
    <Card
      title={text.outcomeExplorerTitle}
      subtitle={text.outcomeExplorerDescription}
      padding="md"
      variant="bordered"
      headerRight={(
        <Button
          type="button"
          variant="secondary"
          size="comfortable"
          isLoading={loading}
          loadingText={t('common.loading')}
          onClick={() => void loadOutcomes()}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('decisionSignals.refresh')}
        </Button>
      )}
    >
      <ResponsiveFilterPanel
        className="mb-4"
        filterLabel={t('decisionSignals.filter')}
        drawerTitle={text.outcomeExplorerTitle}
        applyLabel={text.outcomeExplorerApplyFilters}
        loadingLabel={t('common.loading')}
        isApplying={loading}
        activeCount={activeFilterCount}
        resetLabel={t('common.clear')}
        onReset={resetFilters}
        onApply={applyFilters}
        basicClassName="sm:grid-cols-2"
        advancedClassName="lg:grid-cols-3"
        drawerAdvancedClassName="content-start"
        basic={(
          <>
            <Select
              label={t('decisionSignals.horizon')}
              value={filters.horizon}
              onChange={(value) => setFilters((current) => ({
                ...current,
                horizon: value as OutcomeFilters['horizon'],
              }))}
              options={[
                { value: '', label: text.outcomeExplorerAllHorizons },
                ...HORIZONS.map((horizon) => ({
                  value: horizon,
                  label: getDecisionSignalHorizonLabel(horizon, t),
                })),
              ]}
            />
            <Select
              label={t('decisionSignals.outcomes')}
              value={filters.outcome}
              onChange={(value) => setFilters((current) => ({
                ...current,
                outcome: value as OutcomeFilters['outcome'],
              }))}
              options={[
                { value: '', label: text.outcomeExplorerAllOutcomes },
                ...OUTCOME_VALUES.map((outcome) => ({
                  value: outcome,
                  label: t(`decisionSignals.outcome.${outcome}` as UiTextKey),
                })),
              ]}
            />
          </>
        )}
        advanced={(
          <>
            <Select
              label={t('decisionSignals.status')}
              value={filters.evalStatus}
              onChange={(value) => setFilters((current) => ({
                ...current,
                evalStatus: value as OutcomeFilters['evalStatus'],
              }))}
              options={[
                { value: '', label: text.outcomeExplorerAllStatuses },
                ...EVAL_STATUSES.map((status) => ({
                  value: status,
                  label: t(`decisionSignals.outcomeEvalStatus.${status}` as UiTextKey),
                })),
              ]}
            />
            <Input
              label={text.outcomeExplorerEngineVersion}
              value={filters.engineVersion}
              onChange={(event) => setFilters((current) => ({
                ...current,
                engineVersion: event.target.value,
              }))}
            />
            <Input
              label={text.outcomeExplorerSignalId}
              type="text"
              inputMode="numeric"
              value={filters.signalId}
              onChange={(event) => setFilters((current) => ({
                ...current,
                signalId: event.target.value,
              }))}
            />
          </>
        )}
      />

      {filterError ? (
        <InlineAlert className="mb-4" variant="danger" urgent message={filterError} />
      ) : null}
      {error ? (
        <ApiErrorAlert
          className="mb-4"
          error={{ ...error, title: text.outcomeExplorerErrorTitle }}
          actionLabel={t('common.retry')}
          onAction={() => void loadOutcomes()}
        />
      ) : null}
      {openError ? (
        <ApiErrorAlert
          className="mb-4"
          error={{ ...openError, title: t('decisionSignals.errorTitle') }}
          onDismiss={() => setOpenError(null)}
        />
      ) : null}

      {!error ? (
        <>
          <div className="mb-3 text-sm text-secondary-text">
            {t('decisionSignals.total', { total })}
          </div>
          <DataTable<DecisionSignalOutcomeItem>
            caption={text.outcomeExplorerTitle}
            columns={columns}
            rows={items}
            getRowKey={(item) => item.id}
            status={loading
              ? {
                  state: 'loading',
                  title: t('common.loading'),
                  description: text.outcomeExplorerDescription,
                }
              : undefined}
            emptyState={{
              icon: <Activity className="h-6 w-6" />,
              title: t('decisionSignals.noOutcomes'),
              description: text.outcomeExplorerEmptyDescription,
            }}
            density="compact"
            minWidth="wide"
          />
          <Pagination
            className="mt-4"
            currentPage={page}
            totalPages={totalPages}
            onPageChange={setPage}
          />
        </>
      ) : null}
    </Card>
  );
};
