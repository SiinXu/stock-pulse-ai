// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Activity } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import {
  Badge,
  Card,
  EmptyState,
  ResponsiveFilterPanel,
  Select,
} from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import { getDecisionSignalMarketLabel } from '../../utils/decisionSignalLabels';
import { DecisionSignalTimeline } from './DecisionSignalTimeline';
import {
  MARKET_OPTIONS,
  REASSESS_PROFILES,
  type StockContext,
  type TimelineFilters,
  type TimelineRange,
  type TimelineStatusFilter,
} from './decisionSignalsPageModel';

export type DecisionSignalTimelineSectionProps = {
  activeStockContext: StockContext | null;
  activeStockLabel: string | null;
  filters: TimelineFilters;
  onFiltersChange: (updater: (current: TimelineFilters) => TimelineFilters) => void;
  onMarketSourceUser: (hasMarket: boolean) => void;
  onSearch: () => void;
  loading: boolean;
  searched: boolean;
  error: ParsedApiError | null;
  items: DecisionSignalItem[];
  truncated: boolean;
  selectedId: number | null | undefined;
  onSelect: (item: DecisionSignalItem) => void;
};

const DecisionSignalTimelineSection: React.FC<DecisionSignalTimelineSectionProps> = ({
  activeStockContext,
  activeStockLabel,
  filters,
  onFiltersChange,
  onMarketSourceUser,
  onSearch,
  loading,
  searched,
  error,
  items,
  truncated,
  selectedId,
  onSelect,
}) => {
  const { t } = useUiLanguage();

  return (
    <Card
      title={t('decisionSignals.timelineTitle')}
      subtitle={t('decisionSignals.timelineDescription')}
      padding="md"
      headerRight={activeStockContext ? (
        <Badge variant="info" size="sm">{t('decisionSignals.scopeCurrentStock', { stock: activeStockLabel ?? activeStockContext.code })}</Badge>
      ) : undefined}
    >
      <ResponsiveFilterPanel
        className="xl:grid xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] xl:items-end xl:gap-2 xl:space-y-0"
        filterLabel={t('decisionSignals.timelineSearch')}
        drawerTitle={t('decisionSignals.timelineTitle')}
        applyLabel={t('decisionSignals.timelineSearch')}
        onApply={onSearch}
        applyDisabled={loading || !activeStockContext?.code}
        isApplying={loading}
        loadingLabel={t('decisionSignals.timelineSearch')}
        activeCount={Number(filters.status !== 'all') + Number(Boolean(filters.decisionProfile))}
        basicClassName="sm:grid-cols-2 [&>*]:min-w-0 [&>*]:!w-full [&>*>div]:w-full"
        advancedClassName="lg:grid-cols-2 [&>*]:min-w-0 [&>*]:!w-full [&>*>div]:w-full"
        drawerAdvancedClassName="content-start [&>*]:min-w-0 [&>*]:!w-full [&>*>div]:w-full"
        basic={(
          <>
            <Select
              label={t('decisionSignals.timelineMarket')}
              value={filters.market}
              onChange={(value) => {
                const market = value as TimelineFilters['market'];
                onMarketSourceUser(Boolean(market));
                onFiltersChange((current) => ({ ...current, market }));
              }}
              options={[
                { value: '', label: t('decisionSignals.allMarkets') },
                ...MARKET_OPTIONS.map((market) => ({ value: market, label: getDecisionSignalMarketLabel(market, t) })),
              ]}
            />
            <Select
              label={t('decisionSignals.timelineRange')}
              value={filters.range}
              onChange={(value) => onFiltersChange((current) => ({ ...current, range: value as TimelineRange }))}
              options={[
                { value: '30d', label: t('decisionSignals.timelineRange.30d') },
                { value: '90d', label: t('decisionSignals.timelineRange.90d') },
                { value: '180d', label: t('decisionSignals.timelineRange.180d') },
              ]}
            />
          </>
        )}
        advanced={(
          <>
            <Select
              label={t('decisionSignals.timelineStatus')}
              value={filters.status}
              onChange={(value) => onFiltersChange((current) => ({ ...current, status: value as TimelineStatusFilter }))}
              options={[
                { value: 'all', label: t('decisionSignals.timelineStatus.all') },
                { value: 'active', label: t('decisionSignals.timelineStatus.active') },
              ]}
            />
            <Select
              label={t('decisionSignals.timelineProfile')}
              value={filters.decisionProfile}
              onChange={(value) => onFiltersChange((current) => ({
                ...current,
                decisionProfile: value as TimelineFilters['decisionProfile'],
              }))}
              options={[
                { value: '', label: t('decisionSignals.allProfiles') },
                ...REASSESS_PROFILES.map((profile) => ({
                  value: profile,
                  label: t(`decisionSignals.profile.${profile}` as UiTextKey),
                })),
                { value: 'unknown', label: t('decisionSignals.profile.unknown') },
              ]}
            />
          </>
        )}
      />
      <div className="mt-4">
        {!searched ? (
          <EmptyState
            compact
            title={activeStockContext ? t('decisionSignals.timelineGuideTitle') : t('decisionSignals.stockContextGuideTitle')}
            description={activeStockContext ? t('decisionSignals.timelineGuideDescription') : t('decisionSignals.stockContextGuideDescription')}
            icon={<Activity className="h-6 w-6" />}
          />
        ) : (
          <DecisionSignalTimeline
            items={items}
            selectedId={selectedId ?? null}
            loading={loading}
            error={error?.message ?? null}
            truncated={truncated}
            onSelect={onSelect}
          />
        )}
      </div>
    </Card>
  );
};

export default DecisionSignalTimelineSection;
