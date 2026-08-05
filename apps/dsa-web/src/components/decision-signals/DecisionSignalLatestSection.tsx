// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Activity } from 'lucide-react';
import type { ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  Badge,
  Card,
  EmptyState,
  Loading,
} from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import { DecisionSignalCard } from './DecisionSignalDisplay';
import type { StockContext } from './decisionSignalsPageModel';

export type DecisionSignalLatestSectionProps = {
  activeStockContext: StockContext | null;
  activeStockLabel: string | null;
  loading: boolean;
  searched: boolean;
  error: ParsedApiError | null;
  items: DecisionSignalItem[];
  selectedId: number | null | undefined;
  onSelect: (item: DecisionSignalItem) => void;
};

export const DecisionSignalLatestSection: React.FC<DecisionSignalLatestSectionProps> = ({
  activeStockContext,
  activeStockLabel,
  loading,
  searched,
  error,
  items,
  selectedId,
  onSelect,
}) => {
  const { t } = useUiLanguage();

  return (
    <Card
      title={t('decisionSignals.latestTitle')}
      subtitle={t('decisionSignals.latestDescription')}
      padding="md"
      headerRight={activeStockContext ? (
        <Badge variant="info" size="sm">{t('decisionSignals.scopeCurrentStock', { stock: activeStockLabel ?? activeStockContext.code })}</Badge>
      ) : undefined}
    >
      {!activeStockContext ? (
        <EmptyState
          compact
          title={t('decisionSignals.stockContextGuideTitle')}
          description={t('decisionSignals.stockContextGuideDescription')}
          icon={<Activity className="h-6 w-6" />}
        />
      ) : null}
      {error ? <ApiErrorAlert className="mt-3" error={error} /> : null}
      {searched && !loading && !error && items.length === 0 ? (
        <EmptyState
          compact
          className="mt-4"
          title={t('decisionSignals.noLatestTitle')}
          description={t('decisionSignals.noLatestDescription')}
          icon={<Activity className="h-6 w-6" />}
        />
      ) : null}
      {loading ? <Loading className="mt-3" /> : null}
      {items.length > 0 ? (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {items.map((item) => (
            <DecisionSignalCard
              key={item.id}
              item={item}
              onSelect={onSelect}
              selected={selectedId === item.id}
            />
          ))}
        </div>
      ) : null}
    </Card>
  );
};
