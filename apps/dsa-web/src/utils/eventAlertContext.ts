// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { AlertTriggerItem } from '../types/alerts';
import {
  CORPORATE_EVENT_CATEGORIES,
  type CorporateEventCategory,
  type EventAlertDisplayItem,
  type EventAlertImpactGrade,
} from '../types/eventAlerts';

const GRADE_ORDER: Readonly<Record<EventAlertImpactGrade, number>> = {
  major: 0,
  routine: 1,
  unclassified: 2,
};

export function resolveEventContextsFromTrigger(trigger: AlertTriggerItem) {
  return {
    impactContext: trigger.impactContext ?? null,
    eventContext: trigger.eventContext ?? null,
  };
}

export function isCorporateEventCategory(value: string | null | undefined): value is CorporateEventCategory {
  return Boolean(value && (CORPORATE_EVENT_CATEGORIES as readonly string[]).includes(value));
}

export function isCorporateEventTrigger(trigger: AlertTriggerItem): boolean {
  return trigger.alertType === 'corporate_event' || trigger.dataSource === 'intelligence_items';
}

export function toEventAlertDisplayItem(trigger: AlertTriggerItem): EventAlertDisplayItem {
  const { impactContext, eventContext } = resolveEventContextsFromTrigger(trigger);
  const category = impactContext?.eventCategory ?? eventContext?.eventCategory ?? null;
  const affected = impactContext?.affected ?? null;
  return {
    id: trigger.id,
    ruleId: trigger.ruleId,
    target: trigger.target,
    status: trigger.status,
    reason: trigger.reason,
    dataSource: trigger.dataSource,
    dataTimestamp: trigger.dataTimestamp,
    triggeredAt: trigger.triggeredAt,
    observedValue: trigger.observedValue,
    threshold: trigger.threshold,
    whatHappened: impactContext?.whatHappened ?? eventContext?.whatHappened ?? trigger.reason ?? null,
    whyItMatters: impactContext?.whyItMatters ?? eventContext?.whyItMatters ?? null,
    eventCategory: category,
    impactGrade: trigger.impactResult?.grade ?? 'unclassified',
    impactProvenance: trigger.impactResult?.provenance ?? 'unavailable',
    degraded: Boolean(impactContext?.degraded),
    inWatchlist: Boolean(affected?.inWatchlist),
    inPortfolio: Boolean(affected?.inPortfolio),
    weightPct: affected?.weightPct ?? null,
    relatedAnalysis: impactContext?.relatedAnalysis ?? null,
    matchedCount: impactContext?.matchedCount ?? eventContext?.matchedCount ?? null,
    impactContext,
    eventContext,
    suggestedActionLabel: trigger.suggestedAction?.label ?? null,
    suggestedActionRationale: trigger.suggestedAction?.rationale ?? null,
    suggestedActionLinks: trigger.suggestedAction?.deepLinks ?? null,
    autoAnalysisStatus:
      trigger.suggestedAction?.autoAnalysis?.status
      ?? trigger.autoAnalysis?.status
      ?? null,
  };
}

export function projectCorporateEventAlerts(triggers: AlertTriggerItem[]): EventAlertDisplayItem[] {
  return triggers.filter(isCorporateEventTrigger).map(toEventAlertDisplayItem).sort((a, b) => {
    const gradeOrder = GRADE_ORDER[a.impactGrade] - GRADE_ORDER[b.impactGrade];
    if (gradeOrder !== 0) return gradeOrder;
    return (b.triggeredAt ? Date.parse(b.triggeredAt) : 0) - (a.triggeredAt ? Date.parse(a.triggeredAt) : 0);
  });
}
