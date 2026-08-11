import { describe, expect, it } from 'vitest';
import type { AlertTriggerItem } from '../../types/alerts';
import { projectCorporateEventAlerts, toEventAlertDisplayItem } from '../eventAlertContext';
const why = 'Earnings events can reprice profit expectations and valuation anchors.';
function trigger(p: Partial<AlertTriggerItem> & Pick<AlertTriggerItem, 'id' | 'target' | 'status'>): AlertTriggerItem {
  return { observedValue: null, threshold: null, reason: null, dataSource: null, ...p };
}
describe('eventAlertContext', () => {
  it('uses only the backend-owned impact grade and provenance', () => {
    const item = toEventAlertDisplayItem(trigger({
      id: 1,
      target: '600519',
      status: 'triggered',
      alertType: 'corporate_event',
      impactContext: { eventCategory: 'earnings' },
      impactResult: { grade: 'major', severity: 'critical', provenance: 'rule_severity' },
    }));
    expect(item.impactGrade).toBe('major');
    expect(item.impactProvenance).toBe('rule_severity');
  });
  it('uses backend why text only', () => {
    const item = toEventAlertDisplayItem(trigger({
      id: 1, target: '600519', status: 'triggered', dataSource: 'intelligence_items',
      impactContext: { whatHappened: 'Q1', whyItMatters: why, eventCategory: 'earnings', affected: { inWatchlist: true } },
    }));
    expect(item.whyItMatters).toBe(why);
    expect(item.inWatchlist).toBe(true);
  });
  it('filters non-corporate', () => {
    expect(projectCorporateEventAlerts([trigger({ id: 9, target: 'x', status: 'triggered', dataSource: 'quote' })])).toEqual([]);
  });
});
