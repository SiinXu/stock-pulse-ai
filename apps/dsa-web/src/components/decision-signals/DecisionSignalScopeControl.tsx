import { useId } from 'react';
import { SelectionChip } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import {
  SIGNAL_CENTER_SCOPE_VALUES,
  type SignalCenterScope,
} from '../../routing/routes';

type DecisionSignalScopeControlProps = {
  value: SignalCenterScope;
  onChange: (value: SignalCenterScope) => void;
};

const DecisionSignalScopeControl = ({ value, onChange }: DecisionSignalScopeControlProps) => {
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

export default DecisionSignalScopeControl;
