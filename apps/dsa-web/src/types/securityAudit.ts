// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Phase 1 durable security-audit contract (camelCase client projection). */

export type SecurityAuditPhase = 'attempt' | 'completion';

export type SecurityAuditOutcome =
  | 'pending'
  | 'success'
  | 'denied'
  | 'failure'
  | 'accepted'
  | 'rejected';

export interface SecurityAuditActor {
  type: string;
  id: string;
}

export interface SecurityAuditTarget {
  type: string;
  id: string;
}

export interface SecurityAuditEvent {
  id: number;
  schemaVersion: 'security-audit-v1';
  occurredAt: string;
  eventType: string;
  phase: SecurityAuditPhase;
  actor: SecurityAuditActor;
  executionId: string;
  action: string;
  target: SecurityAuditTarget;
  outcome: SecurityAuditOutcome;
  reasonCode: string;
  correlationId: string;
  metadata: Record<string, unknown>;
}

export interface SecurityAuditEventPage {
  items: SecurityAuditEvent[];
  page: number;
  pageSize: number;
  total: number;
}

export interface SecurityAuditListQuery {
  page?: number;
  pageSize?: number;
  eventType?: string;
  outcome?: SecurityAuditOutcome;
  correlationId?: string;
  /** ISO-8601 timestamp with timezone (backend requires tz-aware values). */
  occurredFrom?: string;
  /** ISO-8601 timestamp with timezone (backend requires tz-aware values). */
  occurredTo?: string;
}

/** Backend maximum page size for GET /api/v1/security/audit-events. */
export const SECURITY_AUDIT_MAX_PAGE_SIZE = 100;
