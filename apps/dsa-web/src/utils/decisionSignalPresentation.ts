import type {
  DecisionSignalItem,
  DecisionSignalPresentation,
} from '../types/decisionSignals';
import {
  getDecisionActionLabel,
  type DecisionActionLabelMap,
} from './decisionAction';

type DecisionSignalPresentationSource = Pick<DecisionSignalItem, 'action'> & Partial<DecisionSignalItem>;

const hasOwn = (value: object, key: PropertyKey): boolean =>
  Object.prototype.hasOwnProperty.call(value, key);

function presentationValue<K extends keyof DecisionSignalPresentation>(
  item: DecisionSignalPresentationSource,
  key: K,
  fallback: DecisionSignalPresentation[K],
): DecisionSignalPresentation[K] {
  const presentation = item.presentation;
  if (presentation && hasOwn(presentation, key)) return presentation[key];
  return fallback;
}

export function getDecisionSignalPresentation(
  item: DecisionSignalPresentationSource,
  labels?: Partial<DecisionActionLabelMap>,
): DecisionSignalPresentation {
  const action = item.action;
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
