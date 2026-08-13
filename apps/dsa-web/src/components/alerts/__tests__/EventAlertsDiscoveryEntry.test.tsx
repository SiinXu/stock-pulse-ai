// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { APP_ROUTE_PATHS } from '../../../routing/routes';
import EventAlertsDiscoveryEntry from '../EventAlertsDiscoveryEntry';

function LocationProbe() {
  const location = useLocation();
  const value = `${location.pathname}${location.search}`;
  return <div data-testid="location">{value}</div>;
}

describe('EventAlertsDiscoveryEntry', () => {
  // Reachability-only control; excluded from Playground inventory via default export.
  it('navigates to the Event Alerts production route', () => {
    render(
      <MemoryRouter initialEntries={['/signals']}>
        <UiLanguageProvider initialLanguage="en">
          <Routes>
            <Route
              path="*"
              element={(
                <>
                  <EventAlertsDiscoveryEntry />
                  <LocationProbe />
                </>
              )}
            />
          </Routes>
        </UiLanguageProvider>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('signal-center-open-event-alerts'));
    expect(screen.getByTestId('location')).toHaveTextContent(APP_ROUTE_PATHS.eventAlerts);
  });
});
