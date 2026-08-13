// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useNavigate } from 'react-router-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { EVENT_ALERT_PAGE_TEXT } from '../../locales/eventAlerts';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import { Button } from '../common';

/**
 * Production discovery entry for the Event Alerts page from Signal Center / Alerts history.
 * Default-only export keeps this helper out of the Playground catalog inventory scan.
 */
const EventAlertsDiscoveryEntry: React.FC = () => {
  const navigate = useNavigate();
  const { language } = useUiLanguage();
  const text = EVENT_ALERT_PAGE_TEXT[language];

  return (
    <div className="flex justify-end">
      <Button
        type="button"
        variant="secondary"
        size="compact"
        data-testid="signal-center-open-event-alerts"
        onClick={() => navigate(APP_ROUTE_PATHS.eventAlerts)}
      >
        {text.title}
      </Button>
    </div>
  );
};

export default EventAlertsDiscoveryEntry;
