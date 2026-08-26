// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { SelectionChip, Surface } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { getDecisionSignalSourceTypeLabel } from '../../utils/decisionSignalLabels';
import { STATUS_LABEL_KEYS, type SelectedSignal } from './decisionSignalsPageModel';

export type DecisionSignalContextChipProps = {
  selected: SelectedSignal | null;
  onOpen: () => void;
};

export const DecisionSignalContextChip: React.FC<DecisionSignalContextChipProps> = ({
  selected,
  onOpen,
}) => {
  const { t } = useUiLanguage();
  if (!selected) return null;

  const item = selected.item;
  const symbol = item.stockName
    ? `${item.stockCode} ${item.stockName}`
    : item.stockCode;
  const sourceLabel = getDecisionSignalSourceTypeLabel(item.sourceType, t);
  const statusLabel = t(STATUS_LABEL_KEYS[item.status]);

  return (
    <Surface
      as="aside"
      level="section"
      padding="sm"
      data-testid="decision-signal-context-chip"
      data-selected-signal-id={String(item.id)}
      aria-label={`${symbol}，${t('decisionSignals.source')} ${sourceLabel}，${t('decisionSignals.status')} ${statusLabel}`}
    >
      <SelectionChip
        selected
        showSelectionIndicator={false}
        label={symbol}
        description={sourceLabel}
        metadata={statusLabel}
        onClick={onOpen}
        aria-label={`${t('common.details')} ${symbol}`}
      />
    </Surface>
  );
};

export default DecisionSignalContextChip;
