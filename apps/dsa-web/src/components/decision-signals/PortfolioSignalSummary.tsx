import type React from 'react';
import { Badge } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import {
  buildDecisionActionLabelMap,
  getDecisionActionTone,
  type DecisionActionTone,
} from '../../utils/decisionAction';
import { getDecisionSignalHorizonLabel } from '../../utils/decisionSignalLabels';
import { getDecisionSignalPresentation } from '../../utils/decisionSignalPresentation';

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'history';

const ACTION_VARIANTS: Record<DecisionActionTone, BadgeVariant> = {
  success: 'success',
  warning: 'warning',
  danger: 'danger',
  default: 'default',
};

function getActionVariant(action: DecisionSignalItem['action']): BadgeVariant {
  return ACTION_VARIANTS[getDecisionActionTone(action, null, null)];
}

type PortfolioSignalSummaryProps = {
  item?: DecisionSignalItem;
  loading?: boolean;
};

export const PortfolioSignalSummary: React.FC<PortfolioSignalSummaryProps> = ({ item, loading = false }) => {
  const { t } = useUiLanguage();
  if (loading && !item) {
    return <span className="text-xs text-secondary-text">{t('decisionSignals.portfolioLoading')}</span>;
  }
  if (!item) {
    return <span className="text-xs text-muted-text">{t('decisionSignals.portfolioEmpty')}</span>;
  }
  const presentation = getDecisionSignalPresentation(item, buildDecisionActionLabelMap(t));
  return (
    <div className="min-w-[11rem] max-w-[18rem] text-left">
      <div className="flex flex-wrap items-center justify-end gap-1.5">
        <Badge variant={getActionVariant(presentation.action)}>{presentation.label}</Badge>
        {item.horizon ? <span className="text-xs text-secondary-text">{getDecisionSignalHorizonLabel(item.horizon, t)}</span> : null}
      </div>
      {presentation.risk ? <p className="mt-1 line-clamp-2 text-xs text-warning">{presentation.risk}</p> : null}
      {item.watchConditions ? <p className="mt-1 line-clamp-2 text-xs text-secondary-text">{item.watchConditions}</p> : null}
    </div>
  );
};
