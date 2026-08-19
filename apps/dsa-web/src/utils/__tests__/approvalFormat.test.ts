// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { APPROVALS_TEXT } from '../../locales/approvals';
import {
  formatApprovalDecisionAction,
  formatApprovalRiskSource,
  formatApprovalRuleAction,
  formatApprovalSignal,
  formatApprovalStatus,
  formatApprovalTarget,
  sanitizeDiagnosticCode,
} from '../approvalFormat';
import type { DecisionActionLabelMap } from '../decisionAction';

const en = APPROVALS_TEXT.en;
const zh = APPROVALS_TEXT.zh;
const englishLabels: DecisionActionLabelMap = {
  buy: 'Buy',
  add: 'Add',
  hold: 'Hold',
  reduce: 'Reduce',
  sell: 'Sell',
  watch: 'Watch',
  avoid: 'Avoid',
  alert: 'Alert',
};
const chineseLabels: DecisionActionLabelMap = {
  buy: '买入',
  add: '加仓',
  hold: '持有',
  reduce: '减仓',
  sell: '卖出',
  watch: '观望',
  avoid: '回避',
  alert: '预警',
};

describe('sanitizeDiagnosticCode', () => {
  it('strips control characters and keeps a bounded raw code', () => {
    expect(sanitizeDiagnosticCode('\u0000evil_status\u0007')).toBe('evil_status');
    expect(sanitizeDiagnosticCode(`mystery_${'x'.repeat(80)}`)).toHaveLength(64);
    expect(sanitizeDiagnosticCode('   \u0000   ')).toBe('—');
  });
});

describe('formatApprovalSignal', () => {
  it('maps known decision actions through the established catalog', () => {
    expect(formatApprovalSignal('buy', englishLabels)).toBe('Buy');
    expect(formatApprovalSignal('hold', englishLabels)).toBe('Hold');
    expect(formatApprovalSignal('sell', englishLabels)).toBe('Sell');
    expect(formatApprovalSignal('buy', chineseLabels)).toBe('买入');
  });

  it('keeps unknown signal codes visible instead of inventing a label', () => {
    expect(formatApprovalSignal('moonshot', englishLabels)).toBe('moonshot');
    expect(formatApprovalSignal('\u0000weird_signal', chineseLabels)).toBe('weird_signal');
    expect(formatApprovalSignal('', englishLabels)).toBe('—');
    expect(formatApprovalSignal(null, englishLabels)).toBe('—');
  });
});

describe('formatApprovalStatus', () => {
  it('maps known approval statuses through APPROVALS_TEXT', () => {
    expect(formatApprovalStatus('pending', en)).toBe('Pending');
    expect(formatApprovalStatus('approved', en)).toBe('Approved');
    expect(formatApprovalStatus('rejected', en)).toBe('Rejected');
    expect(formatApprovalStatus('expired', en)).toBe('Expired');
    expect(formatApprovalStatus('cancelled', en)).toBe('Cancelled');
    expect(formatApprovalStatus('approved', zh)).toBe('已批准');
  });

  it('keeps unknown statuses visible as sanitized diagnostics', () => {
    expect(formatApprovalStatus('mystery_status', en)).toBe('mystery_status');
    expect(formatApprovalStatus('\u0000queued', zh)).toBe('queued');
    expect(formatApprovalStatus('', en)).toBe('—');
  });
});

describe('formatApprovalRiskSource', () => {
  it('maps known risk sources through APPROVALS_TEXT', () => {
    expect(formatApprovalRiskSource('risk_veto', en)).toBe('Risk veto');
    expect(formatApprovalRiskSource('risk_downgrade', en)).toBe('Risk downgrade');
    expect(formatApprovalRiskSource('risk_veto', zh)).toBe('风险否决');
  });

  it('keeps unknown risk sources visible', () => {
    expect(formatApprovalRiskSource('custom_risk', en)).toBe('custom_risk');
    expect(formatApprovalRiskSource('\u0000custom_risk', zh)).toBe('custom_risk');
  });
});

describe('formatApprovalRuleAction', () => {
  it('maps the shipped risk-control bypass action through the rule title', () => {
    expect(formatApprovalRuleAction('risk_control_bypass', en)).toBe('Risk-control bypass rule');
    expect(formatApprovalRuleAction('risk_control_bypass', zh)).toBe('风控绕过规则');
  });

  it('keeps unknown rule actions visible', () => {
    expect(formatApprovalRuleAction('broker_order_release', en)).toBe('broker_order_release');
  });
});

describe('formatApprovalDecisionAction', () => {
  it('reuses existing approve and reject copy', () => {
    expect(formatApprovalDecisionAction('approved', en)).toBe('Approve original signal');
    expect(formatApprovalDecisionAction('rejected', en)).toBe('Reject and use conservative signal');
    expect(formatApprovalDecisionAction('cancelled', en)).toBe('Cancelled');
  });
});

describe('formatApprovalTarget', () => {
  it('keeps a stock code visible and sanitizes empty or hostile values', () => {
    expect(formatApprovalTarget('AAPL')).toBe('AAPL');
    expect(formatApprovalTarget('\u0000600519')).toBe('600519');
    expect(formatApprovalTarget('')).toBe('—');
  });
});
