// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export type TodaysFocusReasonCode =
  | 'alert_triggered'
  | 'corporate_event'
  | 'analysis_reversal'
  | 'high_weight_move'
  | string;

export interface TodaysFocusItem {
  code: string;
  name: string;
  reasonCode: TodaysFocusReasonCode;
  reasonDisplay: string;
  priority: number;
  weightPct?: number | null;
  secondaryReasonCodes?: string[];
  evidence?: Record<string, unknown>;
}

export interface TodaysFocusCostContract {
  providerCalls: number;
  analysisRunsTriggered: number;
  zeroExtraFetch: boolean;
}

export interface TodaysFocusResponse {
  packVersion: string;
  generatedAt: string;
  status: 'ok' | 'empty' | string;
  maxItems: number;
  itemCount: number;
  items: TodaysFocusItem[];
  emptyReason?: string | null;
  emptyMessage?: string | null;
  sourcesUsed?: string[];
  costContract?: TodaysFocusCostContract;
  presentationBoundary?: {
    alertsOwnedBy?: string;
    focusShows?: string;
    duplicateAlertUi?: boolean;
  };
}

export interface TodaysFocusQuery {
  maxItems?: number;
  accountId?: number;
  language?: string;
}
