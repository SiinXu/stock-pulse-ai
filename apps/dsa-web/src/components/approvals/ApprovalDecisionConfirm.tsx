// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { APPROVALS_TEXT } from '../../locales/approvals';
import type { ApprovalDecision, ApprovalProposal } from '../../types/approvals';
import {
  formatApprovalDecisionAction,
  formatApprovalRiskSource,
  formatApprovalSignal,
  formatApprovalTarget,
} from '../../utils/approvalFormat';
import { buildDecisionActionLabelMap } from '../../utils/decisionAction';

export interface ApprovalDecisionConfirmProps {
  proposal: ApprovalProposal;
  decision: ApprovalDecision;
  deciding: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

const ApprovalDecisionConfirm: React.FC<ApprovalDecisionConfirmProps> = ({
  proposal,
  decision,
  deciding,
  error = null,
  onConfirm,
  onCancel,
}) => {
  const { language, t } = useUiLanguage();
  const text = APPROVALS_TEXT[language];
  const signalLabels = buildDecisionActionLabelMap(t);
  const actionLabel = formatApprovalDecisionAction(decision, text);
  const target = formatApprovalTarget(proposal.context.stockCode);
  const original = formatApprovalSignal(proposal.context.originalSignal, signalLabels);
  const conservative = formatApprovalSignal(proposal.context.conservativeSignal, signalLabels);
  const riskSource = formatApprovalRiskSource(proposal.context.riskSource, text);

  return (
    <ConfirmDialog
      isOpen
      title={actionLabel}
      message={(
        <div data-testid="approval-decision-confirm-target" className="space-y-2">
          <p className="font-mono text-sm font-semibold text-foreground">{target}</p>
          <dl className="space-y-2">
            <div>
              <dt className="text-xs text-secondary-text">{text.originalSignal}</dt>
              <dd className="text-sm text-foreground">{original}</dd>
            </div>
            <div>
              <dt className="text-xs text-secondary-text">{text.conservativeSignal}</dt>
              <dd className="text-sm text-foreground">{conservative}</dd>
            </div>
            <div>
              <dt className="text-xs text-secondary-text">{text.riskSources}</dt>
              <dd className="text-sm text-foreground">{riskSource}</dd>
            </div>
          </dl>
        </div>
      )}
      confirmText={deciding ? text.processing : actionLabel}
      cancelText={t('common.cancel')}
      isDanger={decision === 'rejected'}
      confirmDisabled={deciding}
      cancelDisabled={deciding}
      error={error}
      focusConfirmOnError
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
};

export default ApprovalDecisionConfirm;
