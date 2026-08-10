// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export type TodaysFocusReasonCode =
  | 'alert_triggered'
  | 'corporate_event'
  | 'analysis_reversal';

export interface TodaysFocusAlertEvidence {
  type: 'alert';
  triggerId: number;
  ruleId: number | null;
  observedAt: string;
  status: 'triggered';
  source?: string | null;
}

export interface TodaysFocusAnalysisEvidence {
  type: 'analysis';
  recordId: number;
  queryId: string | null;
  observedAt: string;
  previousObservedAt: string;
  previousAction: 'buy' | 'sell' | 'hold';
  latestAction: 'buy' | 'sell' | 'hold';
}

export interface TodaysFocusCorporateEventEvidence {
  type: 'corporate_event';
  eventId: string;
  observedAt: string;
  href: string;
}

export type TodaysFocusEvidence =
  | TodaysFocusAlertEvidence
  | TodaysFocusAnalysisEvidence
  | TodaysFocusCorporateEventEvidence;

export interface TodaysFocusItem {
  code: string;
  name: string;
  reasonCode: TodaysFocusReasonCode;
  reasonDisplay: string;
  priority: number;
  weightPct: number | null;
  secondaryReasonCodes: TodaysFocusReasonCode[];
  evidence: TodaysFocusEvidence;
}

export interface TodaysFocusCostContract {
  alertRepositoryCalls: number;
  portfolioRepositoryCalls: number;
  analysisHistoryRepositoryCalls: number;
  eventRepositoryCalls: number;
  databaseWrites: 0;
  providerCalls: 0;
  analysisRunsTriggered: 0;
  zeroExtraFetch: true;
  readOnly: true;
}

export interface TodaysFocusTemporalPolicy {
  semantics: 'local_calendar_day';
  timezone: string;
  localDate: string;
  windowStart: string;
  windowEnd: string;
  naiveTimestampPolicy: 'assume_utc';
  missingTimestampPolicy: 'exclude';
  nonTradingDayPolicy: 'same_local_day_only';
}

export interface TodaysFocusResponse {
  packVersion: 'todays_focus/2.0';
  generatedAt: string;
  status: 'ok' | 'empty' | 'degraded';
  maxItems: number;
  itemCount: number;
  items: TodaysFocusItem[];
  emptyReason: 'source_unavailable' | 'no_fresh_deterministic_signals' | null;
  emptyMessage: string | null;
  sourcesUsed: (
    | 'alert'
    | 'analysis'
    | 'corporate_event'
    | 'alerts'
    | 'analysis_history'
    | 'corporate_events'
  )[];
  degradedSources: (
    | 'alerts'
    | 'analysis_history'
    | 'corporate_events'
    | 'portfolio_position_cache'
  )[];
  temporalPolicy: TodaysFocusTemporalPolicy;
  universeContract: {
    symbolCount: number;
    hardCap: 1000;
    truncated: boolean;
    sources: (
      | 'injected_evidences'
      | 'portfolio_position_cache'
      | 'request'
      | 'watchlist_config'
    )[];
  };
  costContract: TodaysFocusCostContract;
  presentationBoundary: {
    alertsOwnedBy: 'signal_center';
    focusShows: 'prioritized_symbols_with_evidence_links';
    duplicateAlertUi: false;
  };
}

export interface TodaysFocusQuery {
  maxItems?: number;
  accountId?: number;
  language?: string;
}
