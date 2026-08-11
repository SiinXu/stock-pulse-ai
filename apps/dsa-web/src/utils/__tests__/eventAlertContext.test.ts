import { describe, expect, it } from 'vitest';
import type { AlertTriggerItem } from '../../types/alerts';
import { gradeEventCategory, projectCorporateEventAlerts, toEventAlertDisplayItem } from '../eventAlertContext';
const why = 'Earnings events can reprice profit expectations and valuation anchors.';
function trigger(p: Partial<AlertTriggerItem> & Pick<AlertTriggerItem, 'id' | 'target' | 'status'>): AlertTriggerItem {
  return { observedValue: null, threshold: null, reason: null, dataSource: null, ...p };
}
describe('eventAlertContext', () => {
  it('grades major vs routine', () => {
    expect(gradeEventCategory('regulatory')).toBe('major');
    expect(gradeEventCategory('earnings')).toBe('routine');
  });
  it('uses backend why text only', () => {
    const item = toEventAlertDisplayItem(trigger({
      id: 1, target: '600519', status: 'triggered', dataSource: 'intelligence_items',
      impactContext: { what_happened: 'Q1', why_it_matters: why, event_category: 'earnings', affected: { in_watchlist: true } },
    }));
    expect(item.whyItMatters).toBe(why);
    expect(item.inWatchlist).toBe(true);
  });
  it('filters non-corporate', () => {
    expect(projectCorporateEventAlerts([trigger({ id: 9, target: 'x', status: 'triggered', dataSource: 'quote' })])).toEqual([]);
  });
});
