import { createParsedApiError } from '../../api/error';
import { TodaysFocusPanel } from '../../components/home/TodaysFocusPanel';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { TodaysFocusResponse } from '../../types/todaysFocus';
import { usePlaygroundScenario } from '../scenarioContext';

const FIXTURE_TODAYS_FOCUS: TodaysFocusResponse = {
  packVersion: 'todays_focus/2.1',
  generatedAt: '2026-08-09T08:00:00Z',
  status: 'ok',
  maxItems: 5,
  itemCount: 1,
  items: [{
    code: '600519',
    name: 'Kweichow Moutai',
    reasonCode: 'alert_triggered',
    reasonDisplay: 'Alert triggered: price above MA',
    priority: 100,
    weightPct: null,
    secondaryReasonCodes: [],
    evidence: {
      type: 'alert',
      triggerId: 7,
      ruleId: 9,
      observedAt: '2026-08-09T07:30:00Z',
      status: 'triggered',
    },
  }],
  emptyReason: null,
  emptyMessage: null,
  sourcesUsed: ['alerts'],
  degradedSources: [],
  temporalPolicy: {
    semantics: 'per_market_local_calendar_day',
    crossMarketRule: 'evidence_uses_target_symbol_market_timezone',
    fallbackTimezone: 'Asia/Shanghai',
    windowEnd: '2026-08-09T08:00:00Z',
    naiveTimestampPolicy: 'assume_utc',
    missingTimestampPolicy: 'exclude',
    nonTradingDayPolicy: 'same_local_day_only',
    markets: [
      {
        market: 'cn',
        timezone: 'Asia/Shanghai',
        localDate: '2026-08-09',
        windowStart: '2026-08-08T16:00:00Z',
        windowEnd: '2026-08-09T08:00:00Z',
        isTradingDay: true,
      },
      {
        market: 'hk',
        timezone: 'Asia/Hong_Kong',
        localDate: '2026-08-09',
        windowStart: '2026-08-08T16:00:00Z',
        windowEnd: '2026-08-09T08:00:00Z',
        isTradingDay: true,
      },
      {
        market: 'us',
        timezone: 'America/New_York',
        localDate: '2026-08-09',
        windowStart: '2026-08-09T04:00:00Z',
        windowEnd: '2026-08-09T08:00:00Z',
        isTradingDay: false,
      },
      {
        market: 'unknown',
        timezone: 'Asia/Shanghai',
        localDate: '2026-08-09',
        windowStart: '2026-08-08T16:00:00Z',
        windowEnd: '2026-08-09T08:00:00Z',
        isTradingDay: null,
      },
    ],
  },
  universeContract: {
    symbolCount: 1,
    hardCap: 1000,
    truncated: false,
    sources: ['watchlist_config'],
    excludedNonFinitePositions: 0,
    dataNotes: [],
  },
  costContract: {
    alertRepositoryCalls: 1,
    portfolioRepositoryCalls: 1,
    analysisHistoryRepositoryCalls: 1,
    eventRepositoryCalls: 0,
    databaseWrites: 0,
    providerCalls: 0,
    analysisRunsTriggered: 0,
    zeroExtraFetch: true,
    readOnly: true,
  },
  presentationBoundary: {
    alertsOwnedBy: 'signal_center',
    focusShows: 'prioritized_symbols_with_evidence_links',
    duplicateAlertUi: false,
  },
};

const TodaysFocusScenario = () => {
  const { scenario } = usePlaygroundScenario();
  const { t } = useUiLanguage();
  const isLoading = scenario === 'loading';
  const isError = scenario === 'error';
  const data = scenario === 'empty'
    ? {
        ...FIXTURE_TODAYS_FOCUS,
        status: 'empty' as const,
        itemCount: 0,
        items: [],
        emptyReason: 'no_fresh_deterministic_signals' as const,
        emptyMessage: 'No symbols need special attention today.',
      }
    : isLoading || isError ? null : FIXTURE_TODAYS_FOCUS;

  return (
    <div className="max-w-xl">
      <TodaysFocusPanel
        data={data}
        isLoading={isLoading}
        error={isError ? createParsedApiError({ title: 'Fixture error', message: 'Unable to load focus.' }) : null}
        onRefresh={() => undefined}
        t={t}
      />
    </div>
  );
};

export default TodaysFocusScenario;
