// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { APPROVALS_TEXT } from '../locales/approvals';
import type { DecisionAction } from '../types/analysis';
import type { ApprovalDecision } from '../types/approvals';
import {
  DEFAULT_DECISION_ACTION_LABELS,
  getDecisionActionLabel,
  type DecisionActionLabelMap,
} from './decisionAction';

const EMPTY_DISPLAY = '—';
const DIAGNOSTIC_CODE_MAX = 64;
const KNOWN_DECISION_ACTIONS = new Set<string>(Object.keys(DEFAULT_DECISION_ACTION_LABELS));

const STATUS_KEYS = {
  pending: 'statusPending',
  approved: 'statusApproved',
  rejected: 'statusRejected',
  expired: 'statusExpired',
  cancelled: 'statusCancelled',
} as const satisfies Record<string, keyof (typeof APPROVALS_TEXT)['en']>;

const RISK_SOURCE_KEYS = {
  risk_veto: 'riskVeto',
  risk_downgrade: 'riskDowngrade',
} as const satisfies Record<string, keyof (typeof APPROVALS_TEXT)['en']>;

const RULE_ACTION_KEYS = {
  risk_control_bypass: 'ruleTitle',
} as const satisfies Record<string, keyof (typeof APPROVALS_TEXT)['en']>;

type ApprovalsText = (typeof APPROVALS_TEXT)['en'];

function isUnsafeDiagnosticChar(char: string): boolean {
  const code = char.codePointAt(0) ?? 0;
  return code <= 0x1f
    || code === 0x7f
    || (code >= 0x202a && code <= 0x202e)
    || (code >= 0x2066 && code <= 0x2069);
}

export function sanitizeDiagnosticCode(value: string): string {
  const sanitized = Array.from(value)
    .filter((char) => !isUnsafeDiagnosticChar(char))
    .join('')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, DIAGNOSTIC_CODE_MAX);
  return sanitized || EMPTY_DISPLAY;
}

function diagnosticOrEmpty(value: string | null | undefined): string {
  if (value == null || value === '') return EMPTY_DISPLAY;
  return sanitizeDiagnosticCode(value);
}

export function formatApprovalSignal(
  value: string | null | undefined,
  labels: DecisionActionLabelMap,
): string {
  if (value == null || value === '') return EMPTY_DISPLAY;
  if (KNOWN_DECISION_ACTIONS.has(value)) {
    return getDecisionActionLabel(
      value as DecisionAction,
      null,
      null,
      null,
      labels,
    ) ?? sanitizeDiagnosticCode(value);
  }
  return sanitizeDiagnosticCode(value);
}

export function formatApprovalStatus(
  status: string | null | undefined,
  text: ApprovalsText,
): string {
  if (status == null || status === '') return EMPTY_DISPLAY;
  const key = STATUS_KEYS[status as keyof typeof STATUS_KEYS];
  return key ? text[key] : sanitizeDiagnosticCode(status);
}

export function formatApprovalRiskSource(
  source: string | null | undefined,
  text: ApprovalsText,
): string {
  if (source == null || source === '') return EMPTY_DISPLAY;
  const key = RISK_SOURCE_KEYS[source as keyof typeof RISK_SOURCE_KEYS];
  return key ? text[key] : sanitizeDiagnosticCode(source);
}

export function formatApprovalRuleAction(
  action: string | null | undefined,
  text: ApprovalsText,
): string {
  if (action == null || action === '') return EMPTY_DISPLAY;
  const key = RULE_ACTION_KEYS[action as keyof typeof RULE_ACTION_KEYS];
  return key ? text[key] : sanitizeDiagnosticCode(action);
}

export function formatApprovalDecisionAction(
  decision: ApprovalDecision,
  text: ApprovalsText,
): string {
  if (decision === 'approved') return text.approve;
  if (decision === 'rejected') return text.reject;
  return text.statusCancelled;
}

export function formatApprovalTarget(
  stockCode: string | null | undefined,
): string {
  return diagnosticOrEmpty(stockCode);
}
