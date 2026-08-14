// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useId } from 'react';
import { SIGNAL_CENTER_SCOPE_VALUES, type SignalCenterScope } from '../../routing/routes';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { SelectionChip } from '../common';

type DecisionSignalScopeControlProps = {
  value: SignalCenterScope;
  onChange: (value: SignalCenterScope) => void;
};

export const DecisionSignalScopeControl: React.FC<DecisionSignalScopeControlProps> = ({
  value,
  onChange,
}) => {
  const { t } = useUiLanguage();
  const labelId = useId();
  const options = [
    { value: SIGNAL_CENTER_SCOPE_VALUES.all, label: t('decisionSignals.scopeAll') },
    { value: SIGNAL_CENTER_SCOPE_VALUES.holdings, label: t('decisionSignals.scopeHoldings') },
    { value: SIGNAL_CENTER_SCOPE_VALUES.watchlist, label: t('decisionSignals.scopeWatchlist') },
  ] as const;

  return (
    <div className="flex flex-wrap items-center gap-2.5">
      <span id={labelId} className="text-xs font-medium text-muted-text">
        {t('decisionSignals.scopeLabel')}
      </span>
      <div role="group" aria-labelledby={labelId} className="flex flex-wrap items-center gap-1">
        {options.map((option) => (
          <SelectionChip
            key={option.value}
            label={option.label}
            selected={value === option.value}
            size="compact"
            showSelectionIndicator={false}
            onClick={() => onChange(option.value)}
          />
        ))}
      </div>
    </div>
  );
};
