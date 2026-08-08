// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
export type OutboundDecision = 'allowed' | 'blocked';
export type LocalOnlyModeStatus = {
  enabled: boolean;
  envKey: string;
  policy: string;
  allowedDestinationClasses: string[];
  blockedErrorReason: string;
};
export type OutboundActivityItem = {
  occurredAt: string;
  decision: OutboundDecision;
  destinationClass: string;
  scheme: string;
  hostType: string;
  reason: string;
  correlationId: string;
  localOnlyMode: boolean;
  allowlisted: boolean;
};
export type OutboundActivityPage = {
  localOnlyMode: boolean;
  items: OutboundActivityItem[];
  limit: number;
  returned: number;
  maxRetained: number;
};
export type OutboundActivityListQuery = { limit?: number };
