import type { DecisionAction } from '../types/analysis';
import type {
  DecisionSignalItem,
  DecisionSignalPresentation,
} from '../types/decisionSignals';
import {
  getDecisionActionLabel,
  type DecisionActionLabelMap,
} from './decisionAction';

const hasOwn = (value: object, key: PropertyKey): boolean =>
  Object.prototype.hasOwnProperty.call(value, key);

function presentationValue<K extends keyof DecisionSignalPresentation>(
  item: DecisionSignalItem,
  key: K,
  fallback: DecisionSignalPresentation[K],
): DecisionSignalPresentation[K] {
  const presentation = item.presentation;
  if (presentation && hasOwn(presentation, key)) return presentation[key];
  return fallback;
}

export function getDecisionSignalPresentation(
  item: DecisionSignalItem,
  labels?: Partial<DecisionActionLabelMap>,
): DecisionSignalPresentation {
  const action = presentationValue(item, 'action', item.action) as DecisionAction;
  const serverLabel = presentationValue(item, 'label', item.actionLabel?.trim() || action) as string;
  return {
    action,
    label: getDecisionActionLabel(action, serverLabel, null, serverLabel, labels) ?? serverLabel,
    confidence: presentationValue(item, 'confidence', item.confidence ?? null),
    summary: presentationValue(item, 'summary', item.reason?.trim() || null),
    risk: presentationValue(item, 'risk', item.riskSummary?.trim() || null),
    timestamp: presentationValue(item, 'timestamp', item.createdAt ?? null),
  };
}
