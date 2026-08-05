// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Activity } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  Pagination,
  ResponsiveFilterPanel,
  Select,
} from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import { buildDecisionActionLabelMap } from '../../utils/decisionAction';
import {
  getDecisionSignalMarketLabel,
  getDecisionSignalMarketPhaseLabel,
  getDecisionSignalSourceTypeLabel,
} from '../../utils/decisionSignalLabels';
import { DecisionSignalCard } from './DecisionSignalDisplay';
import {
  ACTION_OPTIONS,
  type ListFilters,
  MARKET_OPTIONS,
  PAGE_SIZE,
  PHASE_OPTIONS,
  SOURCE_OPTIONS,
  STATUS_LABEL_KEYS,
  STATUS_OPTIONS,
} from './decisionSignalsPageModel';

export type DecisionSignalFeedListSectionProps = {
  filters: ListFilters;
  onFiltersChange: (updater: (current: ListFilters) => ListFilters) => void;
  onApplyFilters: () => void;
  advancedFilterCount: number;
  appliedSourceReportId: number | undefined;
  signalScopeLabel: string;
  loading: boolean;
  error: ParsedApiError | null;
  onRetry: () => void;
  total: number;
  items: DecisionSignalItem[];
  selectedId: number | null | undefined;
  onSelect: (item: DecisionSignalItem) => void;
  page: number;
  onPageChange: (page: number) => void;
  reassessPanel: React.ReactNode;
  onCreateFirstRule: () => void;
};

export const DecisionSignalFeedListSection: React.FC<DecisionSignalFeedListSectionProps> = ({
  filters,
  onFiltersChange,
  onApplyFilters,
  advancedFilterCount,
  appliedSourceReportId,
  signalScopeLabel,
  loading,
  error,
  onRetry,
  total,
  items,
  selectedId,
  onSelect,
  page,
  onPageChange,
  reassessPanel,
  onCreateFirstRule,
}) => {
  const { t } = useUiLanguage();
  const actionLabels = buildDecisionActionLabelMap(t);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-5">
      <Card padding="sm" variant="bordered">
        <ResponsiveFilterPanel
          className="xl:grid xl:grid-cols-[minmax(0,3fr)_minmax(0,5fr)] xl:items-end xl:gap-2 xl:space-y-0 [&>div.hidden]:justify-center [&>div.hidden>div]:flex-none"
          filterLabel={t('decisionSignals.filter')}
          drawerTitle={t('decisionSignals.filter')}
          applyLabel={t('decisionSignals.filter')}
          onApply={onApplyFilters}
          applyDisabled={loading}
          isApplying={loading}
          loadingLabel={t('common.loading')}
          activeCount={advancedFilterCount}
          basicClassName="md:grid-cols-3 [&>*]:min-w-0 [&>*]:!w-full [&_[role=combobox]]:min-h-9 [&_input]:h-9"
          advancedClassName="lg:grid-cols-4 [&>*]:min-w-0 [&>*]:!w-full [&_[role=combobox]]:min-h-9 [&_input]:h-9"
          drawerAdvancedClassName="[&>*]:min-w-0 [&>*]:!w-full"
          basic={(
            <>
              <Select
                label={t('decisionSignals.market')}
                value={filters.market}
                onChange={(value) => onFiltersChange((current) => ({ ...current, market: value as ListFilters['market'] }))}
                options={[
                  { value: '', label: t('decisionSignals.allMarkets') },
                  ...MARKET_OPTIONS.map((market) => ({ value: market, label: getDecisionSignalMarketLabel(market, t) })),
                ]}
              />
              <Input
                label={t('decisionSignals.stockCode')}
                value={filters.stockCode}
                onChange={(event) => onFiltersChange((current) => ({ ...current, stockCode: event.target.value }))}
                placeholder={t('decisionSignals.stockCode')}
                aria-label={t('decisionSignals.stockCode')}
              />
              <Select
                label={t('decisionSignals.action')}
                value={filters.action}
                onChange={(value) => onFiltersChange((current) => ({ ...current, action: value as ListFilters['action'] }))}
                options={[
                  { value: '', label: t('decisionSignals.allActions') },
                  ...ACTION_OPTIONS.map((action) => ({ value: action, label: actionLabels[action] })),
                ]}
              />
            </>
          )}
          advanced={(
            <>
              <Select
                label={t('decisionSignals.marketPhase')}
                value={filters.marketPhase}
                onChange={(value) => onFiltersChange((current) => ({ ...current, marketPhase: value as ListFilters['marketPhase'] }))}
                options={[
                  { value: '', label: t('decisionSignals.allPhases') },
                  ...PHASE_OPTIONS.map((phase) => ({ value: phase, label: getDecisionSignalMarketPhaseLabel(phase, t) })),
                ]}
              />
              <Select
                label={t('decisionSignals.source')}
                value={filters.sourceType}
                onChange={(value) => onFiltersChange((current) => ({ ...current, sourceType: value as ListFilters['sourceType'] }))}
                options={[
                  { value: '', label: t('decisionSignals.allSources') },
                  ...SOURCE_OPTIONS.map((source) => ({ value: source, label: getDecisionSignalSourceTypeLabel(source, t) })),
                ]}
              />
              <Input
                label={t('decisionSignals.sourceReportId')}
                value={filters.sourceReportId}
                onChange={(event) => onFiltersChange((current) => ({ ...current, sourceReportId: event.target.value }))}
                placeholder={t('decisionSignals.sourceReportId')}
                aria-label={t('decisionSignals.sourceReportId')}
                inputMode="numeric"
                min={1}
                step={1}
                type="number"
              />
              <Select
                label={t('decisionSignals.status')}
                value={filters.status}
                onChange={(value) => onFiltersChange((current) => ({ ...current, status: value as ListFilters['status'] }))}
                options={[
                  { value: '', label: t('decisionSignals.allStatuses') },
                  ...STATUS_OPTIONS.map((status) => ({ value: status, label: t(STATUS_LABEL_KEYS[status]) })),
                ]}
              />
            </>
          )}
        />
      </Card>

      {!selectedId && appliedSourceReportId ? (
        <Card padding="md">
          {reassessPanel}
        </Card>
      ) : null}

      {error ? (
        <ApiErrorAlert
          error={{ ...error, title: t('decisionSignals.errorTitle') }}
          actionLabel={t('common.retry')}
          onAction={onRetry}
        />
      ) : null}

      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <p className="text-sm text-secondary-text">{t('decisionSignals.total', { total })}</p>
          <Badge variant="default" size="sm">
            {appliedSourceReportId
              ? t('decisionSignals.scopeFromReport', { reportId: appliedSourceReportId })
              : signalScopeLabel}
          </Badge>
        </div>
        {loading ? <span className="text-xs text-secondary-text">{t('common.loading')}...</span> : null}
      </div>

      {!loading && items.length === 0 ? (
        <EmptyState
          title={t('decisionSignals.emptyTitle')}
          description={t('decisionSignals.emptyDescription')}
          icon={<Activity className="h-7 w-7" />}
          action={(
            <Button
              type="button"
              variant="primary"
              size="comfortable"
              onClick={onCreateFirstRule}
            >
              {t('decisionSignals.createFirstRule')}
            </Button>
          )}
        />
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {items.map((item) => (
            <DecisionSignalCard
              key={item.id}
              item={item}
              onSelect={onSelect}
              selected={selectedId === item.id}
            />
          ))}
        </div>
      )}

      <Pagination
        currentPage={page}
        totalPages={totalPages}
        onPageChange={onPageChange}
      />
    </div>
  );
};
