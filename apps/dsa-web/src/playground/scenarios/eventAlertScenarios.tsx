/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { EventAlertDetail } from '../../components/event-alerts/EventAlertDetail';
import { EventAlertList } from '../../components/event-alerts/EventAlertList';
import { EventAlertsPanel } from '../../components/event-alerts/EventAlertsPanel';
import type { EventAlertDisplayItem } from '../../types/eventAlerts';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const fixtures: EventAlertDisplayItem[] = [
  {
    id: 901,
    target: '600519',
    status: 'triggered',
    whatHappened: 'Regulatory inquiry disclosed',
    whyItMatters: 'Regulatory events may imply penalties, operating limits, or sentiment shocks.',
    eventCategory: 'regulatory',
    impactGrade: 'major',
    degraded: false,
    inWatchlist: true,
    inPortfolio: true,
    weightPct: 12.5,
    matchedCount: 2,
    triggeredAt: '2026-08-01T09:30:00Z',
  },
  {
    id: 902,
    target: 'AAPL',
    status: 'triggered',
    whatHappened: 'Q1 earnings beat consensus',
    whyItMatters: 'Earnings events can reprice profit expectations and valuation anchors.',
    eventCategory: 'earnings',
    impactGrade: 'routine',
    degraded: true,
    inWatchlist: false,
    inPortfolio: false,
    matchedCount: 1,
    triggeredAt: '2026-08-01T10:15:00Z',
  },
];

const EventAlertListStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <EventAlertList
      items={scenario === 'empty' ? [] : fixtures}
      isLoading={scenario === 'loading'}
      selectedId={fixtures[0]?.id}
    />
  );
};

const EventAlertDetailStory = () => {
  const { scenario } = usePlaygroundScenario();
  return <EventAlertDetail item={scenario === 'empty' ? null : fixtures[0]} />;
};

const EventAlertsPanelStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <EventAlertsPanel
      embedded
      items={scenario === 'empty' ? [] : fixtures}
      isLoading={scenario === 'loading'}
    />
  );
};

export const EVENT_ALERT_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'event-alert-list': EventAlertListStory,
  'event-alert-detail': EventAlertDetailStory,
  'event-alerts-panel': EventAlertsPanelStory,
};
