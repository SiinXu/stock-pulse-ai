import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { EventAlertDisplayItem } from '../../../types/eventAlerts';
import { EventAlertsPanel } from '../EventAlertsPanel';
const why = 'Earnings events can reprice profit expectations and valuation anchors.';
const reg = 'Regulatory events may imply penalties, operating limits, or sentiment shocks.';
const fixtures: EventAlertDisplayItem[] = [
  { id: 101, target: '600519', status: 'triggered', whatHappened: 'SEC', whyItMatters: reg, eventCategory: 'regulatory', impactGrade: 'major', degraded: false, inWatchlist: true, inPortfolio: true, weightPct: 8.5, matchedCount: 2, triggeredAt: '2026-08-01T09:00:00Z' },
  { id: 102, target: 'AAPL', status: 'triggered', whatHappened: 'Q1', whyItMatters: why, eventCategory: 'earnings', impactGrade: 'routine', degraded: false, inWatchlist: false, inPortfolio: false, matchedCount: 1, triggeredAt: '2026-08-01T10:00:00Z' },
];
describe('EventAlertsPanel', () => {
  it('renders backend why and selection', async () => {
    const user = userEvent.setup();
    render(<UiLanguageProvider initialLanguage="en"><EventAlertsPanel items={fixtures} embedded /></UiLanguageProvider>);
    expect(screen.getByTestId('event-alert-why-101')).toHaveTextContent(reg);
    await user.click(screen.getByTestId('event-alert-row-102'));
    expect(screen.getByTestId('event-alert-why-it-matters')).toHaveTextContent(why);
  });
  it('empty state', () => {
    render(<UiLanguageProvider initialLanguage="en"><EventAlertsPanel items={[]} embedded /></UiLanguageProvider>);
    expect(screen.getByText('No event alerts')).toBeInTheDocument();
  });
});
