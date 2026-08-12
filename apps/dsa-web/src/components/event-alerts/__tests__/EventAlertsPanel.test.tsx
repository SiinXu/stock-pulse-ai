// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ReactElement } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { APP_ROUTE_PATHS } from '../../../routing/routes';
import type { EventAlertDisplayItem } from '../../../types/eventAlerts';
import EventAlertsPanel from '../EventAlertsPanel';
import { chooseOption } from '../../../test-utils';

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-path">{location.pathname}</div>;
}

function renderPanel(ui: ReactElement) {
  return render(
    <MemoryRouter>
      <UiLanguageProvider initialLanguage="en">
        {ui}
      </UiLanguageProvider>
    </MemoryRouter>,
  );
}

const why = 'Earnings events can reprice profit expectations and valuation anchors.';
const reg = 'Regulatory events may imply penalties, operating limits, or sentiment shocks.';

const fixtures: EventAlertDisplayItem[] = [
  { id: 101, target: '600519', status: 'triggered', whatHappened: 'SEC', whyItMatters: reg, eventCategory: 'regulatory', impactGrade: 'major', impactProvenance: 'rule_severity', degraded: false, inWatchlist: true, inPortfolio: true, weightPct: 8.5, matchedCount: 2, triggeredAt: '2026-08-01T09:00:00Z' },
  { id: 102, target: 'AAPL', status: 'triggered', whatHappened: 'Q1', whyItMatters: why, eventCategory: 'earnings', impactGrade: 'routine', impactProvenance: 'rule_severity', degraded: false, inWatchlist: false, inPortfolio: false, matchedCount: 1, triggeredAt: '2026-08-01T10:00:00Z' },
];

describe('EventAlertsPanel', () => {
  it('renders backend why text and updates detail on row activate', () => {
    renderPanel(<EventAlertsPanel items={fixtures} embedded />);
    expect(screen.getByTestId('event-alert-why-101')).toHaveTextContent(reg);
    expect(screen.getByTestId('event-alert-why-it-matters')).toHaveTextContent(reg);
    fireEvent.click(screen.getByTestId('event-alert-row-102'));
    expect(screen.getByTestId('event-alert-why-it-matters')).toHaveTextContent(why);
  });

  it('shows empty state when there are no event alerts', () => {
    renderPanel(<EventAlertsPanel items={[]} embedded />);
    expect(screen.getByText('No event alerts')).toBeInTheDocument();
  });

  it('moves selection into the filtered dataset', () => {
    renderPanel(<EventAlertsPanel items={fixtures} embedded />);
    fireEvent.click(screen.getByTestId('event-alert-row-102'));
    expect(screen.getByTestId('event-alert-why-it-matters')).toHaveTextContent(why);

    chooseOption(screen.getByLabelText('Status'), 'major');

    expect(screen.queryByTestId('event-alert-row-102')).not.toBeInTheDocument();
    expect(screen.getByTestId('event-alert-why-it-matters')).toHaveTextContent(reg);
  });

  it('mounts a production back-link to the event calendar on the full page', () => {
    render(
      <MemoryRouter initialEntries={[APP_ROUTE_PATHS.eventAlerts]}>
        <UiLanguageProvider initialLanguage="en">
          <Routes>
            <Route
              path={APP_ROUTE_PATHS.eventAlerts}
              element={(
                <>
                  <EventAlertsPanel items={fixtures} />
                  <LocationProbe />
                </>
              )}
            />
            <Route path={APP_ROUTE_PATHS.eventCalendar} element={<LocationProbe />} />
          </Routes>
        </UiLanguageProvider>
      </MemoryRouter>,
    );
    const openCalendar = screen.getByTestId('event-alerts-open-calendar');
    expect(openCalendar).toHaveTextContent('Corporate event calendar');
    expect(screen.getByTestId('event-alerts-panel')).toBeInTheDocument();
    fireEvent.click(openCalendar);
    expect(screen.getByTestId('location-path')).toHaveTextContent(APP_ROUTE_PATHS.eventCalendar);
  });
});
